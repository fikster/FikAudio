#pragma once
#include <dsp/fft.hpp>

#include <cmath>
#include <cstdint>
#include <memory>
#include <vector>

// Paulstretch, written from Nasca Octavian Paul's public-domain
// paulstretch_stereo.py (github.com/paulnasca/paulstretch_python).
//
// Each frame takes a window of the source, keeps the FFT magnitudes, gives
// every bin a random phase and overlap-adds the result. The output hop is
// fixed at half a window; the source read position moves on by hop / stretch
// per frame, so a stretch of 8 plays the source 8 times slower.
//
// Pitch shift: before the phases are randomised, the magnitude of bin k moves
// to k * pitch. That usually falls between two bins, so its power is split
// between them in proportion to how close each is: rounding to the nearest bin
// instead puts small windows audibly out of tune (T022). Power that lands in
// the same bin adds up, so the level holds.
// The idea (not the code) comes from Paul's GPL C++ program; the Python
// version has no pitch shift. Written independently: see PROVENANCE.md.
//
// Staggering: a frame is a lot of work done at once (over a millisecond at
// the largest window). Each voice therefore works out its next frame early,
// at its own slot within the half window it is playing, and switches to it
// on time. Voices given different slots (setSlot) never do their work in the
// same moment, so several voices don't make one large spike.
struct PaulstretchCore {
    static constexpr int NUM_SIZES = 7;
    static constexpr int MIN_SIZE_LOG2 = 10;  // window sizes 1024 .. 65536
    static constexpr int MAX_SIZE = 1 << (MIN_SIZE_LOG2 + NUM_SIZES - 1);
    static constexpr int CHANNELS = 2;

    static int sizeForIndex(int index) { return 1 << (MIN_SIZE_LOG2 + index); }

    PaulstretchCore() {
        for (int i = 0; i < NUM_SIZES; i++) ffts_[i].reset(new rack::dsp::RealFFT(sizeForIndex(i)));
        window_.resize(MAX_SIZE);
        hinv_.resize(MAX_SIZE / 2);
        frame_.resize(MAX_SIZE);
        spectrum_.resize(MAX_SIZE);
        work_.resize(MAX_SIZE);
        mag_.resize(MAX_SIZE / 2 + 1);
        shifted_.resize(MAX_SIZE / 2 + 1);
        for (int c = 0; c < CHANNELS; c++) {
            prev_[c].assign(MAX_SIZE, 0.f);
            nextFrame_[c].assign(MAX_SIZE, 0.f);
            chunk_[c].assign(MAX_SIZE / 2, 0.f);
            nextChunk_[c].assign(MAX_SIZE / 2, 0.f);
        }
        setSize(4);
        reset();
    }

    // Silences the output and forgets the overlap tail. Sound starts again at
    // this voice's slot: at once for slot 0, a little later for the others,
    // so voices reset together don't all do their first frame at once.
    void reset() {
        for (int c = 0; c < CHANNELS; c++) {
            std::fill(prev_[c].begin(), prev_[c].end(), 0.f);
            std::fill(chunk_[c].begin(), chunk_[c].end(), 0.f);
        }
        pendingReady_ = false;
        chunkLen_ = slotOffset(size_ / 2);
        chunkPos_ = 0;
        computeAt_ = chunkLen_;  // the first frame is worked out when the silence ends
    }

    // This voice's place among `slots` voices sharing the work: its frames
    // are worked out `slot / slots` of the way through each half window.
    void setSlot(int slot, int slots) {
        slots_ = slots > 0 ? slots : 1;
        slot_ = slot < 0 ? 0 : slot % slots_;
    }

    int size() const { return size_; }

    // Voices on the same source need their own phases, or they'd add up
    // coherently.
    void seed(uint32_t s) { rng_ = s ? s : 0x9e3779b9; }

    // Produces one output sample per channel into `out`.
    // `source` holds `channels` arrays of `length` samples. `pos` is the read
    // position in samples; when `advance` is set it moves on by hop / stretch
    // at each new frame (back by that much when `reverse` is set) and wraps
    // round the source. Each frame's own samples needn't be reversed: a
    // frame played backwards has the same magnitudes, and the phases are
    // random anyway, so only the order of the frames changes. With `wrap` off, samples
    // past the end of the source read as silence (used while recording).
    // `pitch` is a frequency ratio (2 = an octave up).
    void next(const float* const* source, int channels, int64_t length, double& pos, double stretch,
              double pitch, bool advance, bool reverse, bool wrap, int sizeIndex, float* out) {
        if (chunkPos_ >= chunkLen_) {
            // normally the next frame is ready by now; if not, work it out late
            if (!pendingReady_) prepare(source, channels, length, pos, stretch, pitch, advance, reverse, wrap, sizeIndex);
            for (int c = 0; c < CHANNELS; c++) {
                std::swap(chunk_[c], nextChunk_[c]);
                std::swap(prev_[c], nextFrame_[c]);
            }
            chunkLen_ = nextLen_;
            chunkPos_ = 0;
            pendingReady_ = false;
            computeAt_ = slotOffset(chunkLen_);
        }
        if (!pendingReady_ && chunkPos_ >= computeAt_)
            prepare(source, channels, length, pos, stretch, pitch, advance, reverse, wrap, sizeIndex);
        for (int c = 0; c < channels; c++) out[c] = chunk_[c][chunkPos_];
        chunkPos_++;
    }

    // Number of frames worked out so far (for tests).
    int64_t framesComputed() const { return framesComputed_; }

   private:
    int slotOffset(int len) const { return (int)((int64_t)len * slot_ / slots_); }

    // Works out the frame that follows the one playing now, and moves the
    // read position on.
    void prepare(const float* const* source, int channels, int64_t length, double& pos, double stretch,
                 double pitch, bool advance, bool reverse, bool wrap, int sizeIndex) {
        pitch_ = pitch;
        if (sizeIndex != sizeIndex_) setSize(sizeIndex);
        computeFrame(source, channels, length, pos, wrap);
        nextLen_ = size_ / 2;
        if (advance && length > 0) {
            pos += (reverse ? -nextLen_ : nextLen_) / stretch;
            pos = std::fmod(pos, (double)length);
            if (pos < 0.0) pos += length;
        }
        pendingReady_ = true;
        framesComputed_++;
    }

    void setSize(int index) {
        sizeIndex_ = index;
        size_ = sizeForIndex(index);
        const int half = size_ / 2;
        // window = (1 - x^2)^1.25 with x running -1..1 inclusive. In double
        // and clamped: under Rack's fast-math flags the float version rounded
        // the last x past 1 at size 4096, and pow() of a negative gave NaN.
        for (int i = 0; i < size_; i++) {
            const double x = -1.0 + 2.0 * i / (size_ - 1);
            window_[i] = (float)std::pow(std::max(0.0, 1.0 - x * x), 1.25);
        }
        // evens out the amplitude ripple of the overlapped windows
        const float h = (1.f + std::sqrt(0.5f)) * 0.5f;
        for (int i = 0; i < half; i++) hinv_[i] = h - (1.f - h) * std::cos(i * 2.f * float(M_PI) / half);
        // The original loses about 4.5 dB. With random phases the frames add in
        // power, so scale for an average output power equal to the input's.
        double meanW2 = 0.0, power = 0.0;
        for (int i = 0; i < size_; i++) meanW2 += window_[i] * window_[i];
        meanW2 /= size_;
        for (int i = 0; i < half; i++) {
            const double a = window_[i], b = window_[half + i];
            power += meanW2 * (a * a + b * b) * hinv_[i] * hinv_[i];
        }
        const float gain = (float)(1.0 / std::sqrt(power / half));
        for (int i = 0; i < half; i++) hinv_[i] *= gain;
        for (int c = 0; c < CHANNELS; c++) std::fill(prev_[c].begin(), prev_[c].end(), 0.f);
    }

    float randomPhase() {
        rng_ ^= rng_ << 13;
        rng_ ^= rng_ >> 17;
        rng_ ^= rng_ << 5;
        return (rng_ >> 8) * (2.f * float(M_PI) / 16777216.f);
    }

    void computeFrame(const float* const* source, int channels, int64_t length, double pos, bool wrap) {
        const int n = size_;
        const int half = n / 2;
        rack::dsp::RealFFT& fft = *ffts_[sizeIndex_];
        float* frame = frame_.data();
        float* spec = spectrum_.data();

        for (int c = 0; c < channels; c++) {
            float* chunk = nextChunk_[c].data();   // the next half window of output
            const float* prev = prev_[c].data();   // the frame playing now, for the overlap
            float* keep = nextFrame_[c].data();    // this frame, for the overlap after

            if (length <= 0) {
                std::fill(chunk, chunk + half, 0.f);
                std::fill(keep, keep + n, 0.f);
                continue;
            }

            int64_t idx = (int64_t)std::floor(pos) % length;
            if (idx < 0) idx += length;
            const float* src = source[c];
            for (int i = 0; i < n; i++) {
                frame[i] = (idx < length) ? src[idx] * window_[i] : 0.f;
                if (++idx >= length && wrap) idx = 0;
            }

            // pass PFFFT a work buffer, or it puts one on the (small) engine thread stack
            pffft_transform_ordered(fft.setup, frame, spec, work_.data(), PFFFT_FORWARD);
            // spec[0] is DC and spec[1] Nyquist, both real; then (re, im) pairs
            float* mag = mag_.data();
            mag[0] = std::fabs(spec[0]);
            mag[half] = std::fabs(spec[1]);
            for (int k = 1; k < half; k++) {
                const float re = spec[2 * k], im = spec[2 * k + 1];
                mag[k] = std::sqrt(re * re + im * im);
            }
            if (pitch_ != 1.0) {
                float* shifted = shifted_.data();
                std::fill(shifted, shifted + half + 1, 0.f);
                for (int k = 0; k <= half; k++) {
                    const double x = k * pitch_;
                    const long j = (long)x;
                    if (j > half) break;
                    const float frac = (float)(x - j), power = mag[k] * mag[k];
                    shifted[j] += power * (1.f - frac);
                    if (j < half) shifted[j + 1] += power * frac;
                }
                for (int k = 0; k <= half; k++) mag[k] = std::sqrt(shifted[k]);
            }
            spec[0] = mag[0] * std::cos(randomPhase());
            spec[1] = mag[half] * std::cos(randomPhase());
            for (int k = 1; k < half; k++) {
                const float ph = randomPhase();
                spec[2 * k] = mag[k] * std::cos(ph);
                spec[2 * k + 1] = mag[k] * std::sin(ph);
            }
            pffft_transform_ordered(fft.setup, spec, frame, work_.data(), PFFFT_BACKWARD);

            const float scale = 1.f / n;
            for (int i = 0; i < n; i++) frame[i] *= window_[i] * scale;
            for (int i = 0; i < half; i++) chunk[i] = (frame[i] + prev[half + i]) * hinv_[i];
            // A non-finite sample would spread through every later frame via
            // the overlap, so drop the frame rather than jam the output.
            float sum = 0.f;
            for (int i = 0; i < half; i++) sum += chunk[i];
            if (!std::isfinite(sum)) {
                std::fill(chunk, chunk + half, 0.f);
                std::fill(frame, frame + n, 0.f);
            }
            std::copy(frame, frame + n, keep);
        }
    }

    std::unique_ptr<rack::dsp::RealFFT> ffts_[NUM_SIZES];
    int sizeIndex_ = -1;
    int size_ = 0;
    std::vector<float> window_, hinv_, frame_, spectrum_, work_;
    std::vector<float> mag_, shifted_;  // bin magnitudes, before and after the pitch shift
    double pitch_ = 1.0;
    std::vector<float> prev_[CHANNELS];   // last windowed IFFT output, for the overlap
    std::vector<float> chunk_[CHANNELS];  // finished output, half a window long
    std::vector<float> nextChunk_[CHANNELS], nextFrame_[CHANNELS];  // worked out ahead
    int chunkLen_ = 0;
    int chunkPos_ = 0;
    int nextLen_ = 0;
    bool pendingReady_ = false;
    int computeAt_ = 0;
    int slot_ = 0, slots_ = 1;
    int64_t framesComputed_ = 0;
    uint32_t rng_ = 0x9e3779b9;
};
