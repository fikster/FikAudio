#include "plugin.hpp"

#include <osdialog.h>

#include <atomic>
#include <cstdio>
#include <memory>
#include <thread>

#include "AudioFile.hpp"
#include "PanelText.hpp"
#include "PaulstretchExpander.hpp"
#include "PaulstretchCore.hpp"

// Resamples one channel with Rack's (Speex) resampler, giving exactly
// round(n * outRate / inRate) samples aligned with the input.
static std::vector<float> resampleChannel(const float* in, int64_t n, float inRate, float outRate) {
    const int64_t outLength = (int64_t)std::llround(n * (double)outRate / inRate);
    std::vector<float> out(outLength);
    if ((int)std::lround(inRate) == (int)std::lround(outRate)) {
        std::copy(in, in + std::min(n, outLength), out.begin());
        return out;
    }
    dsp::SampleRateConverter<1> src;
    src.setQuality(SPEEX_RESAMPLER_QUALITY_DESKTOP);
    src.setRates((int)std::lround(inRate), (int)std::lround(outRate));
    // the resampler's output starts this many samples late; drop them
    int64_t skip = src.st ? speex_resampler_get_output_latency(src.st) : 0;
    const int block = 65536;
    std::vector<float> zeros(block, 0.f), tmp(block * 4 + 16);
    int64_t consumed = 0, produced = 0;
    while (produced < outLength) {
        const bool tail = consumed >= n;
        int inFrames = tail ? block : (int)std::min<int64_t>(block, n - consumed);
        int outFrames = (int)tmp.size();
        src.process(tail ? zeros.data() : in + consumed, 1, &inFrames, tmp.data(), 1, &outFrames);
        if (!tail) consumed += inFrames;
        int i = 0;
        for (; i < outFrames && skip > 0; i++) skip--;
        for (; i < outFrames && produced < outLength; i++) out[produced++] = tmp[i];
        if (inFrames == 0 && outFrames == 0) break;
    }
    return out;
}

// Audio for the buffer, prepared away from the audio thread.
struct LoadedAudio {
    std::vector<float> buffer[2];
    int64_t length = 0;
    bool stereo = false;
    float rate = 0.f;
    bool truncated = false;
    std::string path;
    std::string error;
};

// Records audio into a buffer, or loads a WAV or AIFF file into it, and plays
// it back stretched with Paulstretch. A recording is kept with the patch, in
// the module's patch storage folder; a loaded file is kept as its path.
struct Paulstretch : Module {
    // new ids go at the end, so saved patches keep their settings and cables
    enum ParamId { STRETCH_PARAM, WINDOW_PARAM, START_PARAM, REC_PARAM, FREEZE_PARAM, PITCH_PARAM, REVERSE_PARAM, PARAMS_LEN };
    enum InputId {
        STRETCH_INPUT,
        SCAN_INPUT,
        RESET_INPUT,
        FREEZE_INPUT,
        REC_INPUT,
        IN_L_INPUT,
        IN_R_INPUT,
        PITCH_INPUT,
        REVERSE_INPUT,
        INPUTS_LEN
    };
    enum OutputId { OUT_L_OUTPUT, OUT_R_OUTPUT, OUTPUTS_LEN };
    enum LightId { REC_LIGHT, FREEZE_LIGHT, REVERSE_LIGHT, LIGHTS_LEN };

    static constexpr float MAX_SECONDS = 60.f;        // recording
    static constexpr float MAX_FILE_SECONDS = 600.f;  // loaded file
    static constexpr float MAX_STRETCH_LOG2 = 13.f;   // 8192x
    static constexpr float MAX_SEMITONES = 48.f;      // pitch shift, either way
    static constexpr const char* RECORDING_FILE = "recording.f32";

    PaulstretchCore core;
    std::vector<float> buffer[2];
    float bufferRate = 0.f;  // sample rate the buffer holds
    int64_t length = 0;      // samples per channel in use
    bool stereo = false;
    bool recording = false;
    bool recordingFull = false;  // ran out of room; wait for REC to be released
    bool dirty = false;          // recording changed since the file was written
    bool fromFile = false;       // the buffer holds a loaded file, not a recording
    double pos = 0.0;
    bool frozen = false;
    bool reversed = false;
    bool scanning = false;  // SCAN is patched, so the position doesn't run on its own
    std::atomic<bool> clearRequested{false};  // set from the context menu

    // File loading. The UI thread starts a load thread, which fills `pending`
    // and sets READY; process() swaps it into the buffer and sets INSTALLED;
    // the UI thread (pollLoad) then frees the old buffer and goes back to IDLE.
    enum LoadState { IDLE, LOADING, READY, INSTALLED, FAILED };
    std::atomic<int> loadState{IDLE};
    std::unique_ptr<LoadedAudio> pending;
    std::thread loadThread;
    // UI thread only
    std::string filePath;
    bool fileTruncated = false;
    std::string loadError;
    double loadErrorTime = -1e9;
    // Store a copy of the loaded file inside the patch (context menu). The
    // copy is made when the patch is saved, and reopening prefers it.
    bool storeFile = false;
    bool resetAllHeads = false;  // context menu: RESET also sends every head to its START
    std::string copiedFrom;  // the file the stored copy was made from
    std::string copyError;
    std::string loadedFrom;  // where the audio was actually read: the file or its stored copy

    // the expander's heads, run here because this module owns the buffer
    PaulstretchCore heads[paulstretch::HEADS];
    double headPos[paulstretch::HEADS] = {};
    float headStart[paulstretch::HEADS] = {};
    bool headActive[paulstretch::HEADS] = {};
    bool headReversed[paulstretch::HEADS] = {};  // for the display's arrows
    bool headFrozen[paulstretch::HEADS] = {};

    // read from the patch in dataFromJson, used by onAdd
    int64_t savedLength = 0;
    float savedRate = 0.f;
    std::string savedPath;
    std::string savedCopy;
    double savedHeadPos[paulstretch::HEADS] = {};
    bool haveSavedHeadPos = false;

    dsp::SchmittTrigger recGate, freezeGate, reverseGate, resetTrigger;

    Paulstretch() {
        config(PARAMS_LEN, INPUTS_LEN, OUTPUTS_LEN, LIGHTS_LEN);
        configParam(STRETCH_PARAM, 0.f, MAX_STRETCH_LOG2, 3.f, "Stretch", "x", 2.f);
        configSwitch(WINDOW_PARAM, 0.f, PaulstretchCore::NUM_SIZES - 1, 4.f, "Window size",
                     {"1024 samples", "2048 samples", "4096 samples", "8192 samples", "16384 samples",
                      "32768 samples", "65536 samples"});
        getParamQuantity(WINDOW_PARAM)->smoothEnabled = false;
        configParam(START_PARAM, 0.f, 1.f, 0.f, "Start position", "%", 0.f, 100.f);
        configSwitch(REC_PARAM, 0.f, 1.f, 0.f, "Record", {"Off", "On"});
        configSwitch(FREEZE_PARAM, 0.f, 1.f, 0.f, "Freeze", {"Off", "On"});
        configInput(STRETCH_INPUT, "Stretch CV (1 V doubles the stretch)");
        configInput(SCAN_INPUT, "Scan position (0-10 V across the buffer)");
        configInput(RESET_INPUT, "Reset to start position");
        configInput(FREEZE_INPUT, "Freeze gate");
        configInput(REC_INPUT, "Record gate");
        configInput(IN_L_INPUT, "Left / mono audio");
        configInput(IN_R_INPUT, "Right audio (normalled to left)");
        configOutput(OUT_L_OUTPUT, "Left audio (mono mix when right is unpatched)");
        configOutput(OUT_R_OUTPUT, "Right audio");
        configParam(PITCH_PARAM, -24.f, 24.f, 0.f, "Pitch", " semitones");
        getParamQuantity(PITCH_PARAM)->snapEnabled = true;
        configInput(PITCH_INPUT, "Pitch (1 V/oct)");
        configSwitch(REVERSE_PARAM, 0.f, 1.f, 0.f, "Reverse", {"Off", "On"});
        configInput(REVERSE_INPUT, "Reverse gate (flips the direction while high)");
        configBypass(IN_L_INPUT, OUT_L_OUTPUT);
        configBypass(IN_R_INPUT, OUT_R_OUTPUT);

        allocate(APP->engine->getSampleRate());
        // every voice does its frame work at its own moment (see PaulstretchCore)
        core.setSlot(0, paulstretch::HEADS + 1);
        for (int h = 0; h < paulstretch::HEADS; h++) {
            heads[h].seed(0x51ed270bu * uint32_t(h + 2));  // unsigned: wraps instead of overflowing
            heads[h].setSlot(h + 1, paulstretch::HEADS + 1);
        }
        rightExpander.producerMessage = new paulstretch::ToMain;
        rightExpander.consumerMessage = new paulstretch::ToMain;
    }

    ~Paulstretch() override {
        if (loadThread.joinable()) loadThread.join();
        delete (paulstretch::ToMain*)rightExpander.producerMessage;
        delete (paulstretch::ToMain*)rightExpander.consumerMessage;
    }

    // Sends every head back to its start, after the buffer changed.
    void restartHeads() {
        for (int h = 0; h < paulstretch::HEADS; h++) {
            headPos[h] = headStart[h] * length;
            heads[h].reset();
        }
    }

    static double pitchRatio(float semitones) {
        return std::exp2(clamp(semitones, -MAX_SEMITONES, MAX_SEMITONES) / 12.f);
    }

    int64_t capacity() const { return (int64_t)buffer[0].size(); }

    void allocate(float rate) {
        bufferRate = rate;
        const size_t n = (size_t)(MAX_SECONDS * rate);
        for (auto& b : buffer) b.assign(n, 0.f);
        length = 0;
    }

    // Moves the buffer to a new sample rate so it keeps its pitch.
    void resample(float newRate) {
        const float oldRate = bufferRate;
        std::vector<float> old[2] = {std::move(buffer[0]), std::move(buffer[1])};
        const int64_t oldLength = length;
        allocate(newRate);
        if (oldLength <= 0 || oldRate <= 0.f) return;
        for (int c = 0; c < 2; c++) {
            std::vector<float> r = resampleChannel(old[c].data(), oldLength, oldRate, newRate);
            if ((int64_t)r.size() > capacity()) buffer[c].resize(r.size());
            std::copy(r.begin(), r.end(), buffer[c].begin());
            length = (int64_t)r.size();
        }
        pos = pos * newRate / oldRate;
        for (double& p : headPos) p = p * newRate / oldRate;
        if (!fromFile) dirty = true;
    }

    // Reads `path` and resamples it to `rate`. Safe off the audio thread.
    static bool loadAudio(const std::string& path, float rate, LoadedAudio& out) {
        AudioFileData file;
        out.path = path;
        if (!readAudioFile(path, MAX_FILE_SECONDS, file, out.error)) return false;
        out.stereo = file.numChannels == 2;
        out.truncated = file.truncated;
        out.rate = rate;
        for (int c = 0; c < file.numChannels; c++) {
            out.buffer[c] = resampleChannel(file.channels[c].data(), file.frames, file.sampleRate, rate);
            std::vector<float>().swap(file.channels[c]);
        }
        if (!out.stereo) out.buffer[1] = out.buffer[0];
        out.length = (int64_t)out.buffer[0].size();
        // leave room to record over it later
        const size_t room = std::max((size_t)out.length, (size_t)(MAX_SECONDS * rate));
        for (auto& b : out.buffer) b.resize(room, 0.f);
        return out.length > 0;
    }

    // Puts loaded audio into the buffer. The old buffer ends up in `a`.
    void install(LoadedAudio& a, float rate) {
        for (int c = 0; c < 2; c++) std::swap(buffer[c], a.buffer[c]);
        length = a.length;
        stereo = a.stereo;
        bufferRate = a.rate;
        recording = false;
        params[REC_PARAM].setValue(0.f);
        fromFile = true;
        dirty = false;
        pos = params[START_PARAM].getValue() * length;
        core.reset();
        if (rate != bufferRate) resample(rate);
        restartHeads();
    }

    // UI thread: starts loading a file in the background.
    void startLoad(const std::string& path) {
        if (loadState != IDLE) return;
        if (loadThread.joinable()) loadThread.join();
        pending.reset(new LoadedAudio);
        const float rate = APP->engine->getSampleRate();
        loadState = LOADING;
        loadThread = std::thread([this, path, rate]() {
            const bool ok = loadAudio(path, rate, *pending);
            loadState = ok ? READY : FAILED;
        });
    }

    // UI thread: finishes a load once process() has taken it, or reports a failure.
    void pollLoad() {
        const int state = loadState;
        if (state != INSTALLED && state != FAILED) return;
        if (loadThread.joinable()) loadThread.join();
        if (state == INSTALLED) {
            filePath = pending->path;
            loadedFrom = pending->path;
            fileTruncated = pending->truncated;
            loadError.clear();
        } else {
            loadError = system::getFilename(pending->path) + ": " + pending->error;
            loadErrorTime = system::getTime();
            WARN("Paulstretch: can't load %s: %s", pending->path.c_str(), pending->error.c_str());
        }
        pending.reset();  // frees the buffer that was swapped out
        loadState = IDLE;
    }

    void clearRecording() {
        recording = false;
        fromFile = false;
        length = 0;
        pos = 0.0;
        core.reset();
        restartHeads();
        dirty = true;
    }

    void onSampleRateChange(const SampleRateChangeEvent& e) override {
        if (e.sampleRate != bufferRate) resample(e.sampleRate);
    }

    void onReset(const ResetEvent& e) override {
        Module::onReset(e);
        clearRecording();
    }

    void process(const ProcessArgs& args) override {
        if (clearRequested.exchange(false)) clearRecording();
        if (loadState == READY) {
            install(*pending, args.sampleRate);
            loadState = INSTALLED;
        }

        // record: the button latches, the gate records while high
        recGate.process(inputs[REC_INPUT].getVoltage(), 0.1f, 1.f);
        const bool recWanted = params[REC_PARAM].getValue() > 0.5f || recGate.isHigh();
        if (!recWanted) recordingFull = false;
        if (recWanted && !recording && !recordingFull) {
            recording = true;
            fromFile = false;
            stereo = inputs[IN_R_INPUT].isConnected();
            length = 0;
            pos = 0.0;
            core.reset();
            restartHeads();
        } else if (!recWanted && recording) {
            recording = false;
            dirty = true;
        }
        if (recording) {
            if (length < capacity()) {
                const float l = inputs[IN_L_INPUT].getVoltage() / 5.f;
                buffer[0][length] = l;
                buffer[1][length] = stereo ? inputs[IN_R_INPUT].getVoltage() / 5.f : l;
                length++;
            } else {
                recording = false;
                recordingFull = true;
                dirty = true;
                params[REC_PARAM].setValue(0.f);
            }
        }

        freezeGate.process(inputs[FREEZE_INPUT].getVoltage(), 0.1f, 1.f);
        frozen = params[FREEZE_PARAM].getValue() > 0.5f || freezeGate.isHigh();

        const float start = params[START_PARAM].getValue();
        if (resetTrigger.process(inputs[RESET_INPUT].getVoltage(), 0.1f, 1.f)) {
            pos = start * length;
            if (resetAllHeads)
                for (int h = 0; h < paulstretch::HEADS; h++) headPos[h] = headStart[h] * length;
        }

        reverseGate.process(inputs[REVERSE_INPUT].getVoltage(), 0.1f, 1.f);
        reversed = (params[REVERSE_PARAM].getValue() > 0.5f) != reverseGate.isHigh();

        bool advance = !frozen;
        scanning = inputs[SCAN_INPUT].isConnected();
        if (scanning) {
            float scan = start + inputs[SCAN_INPUT].getVoltage() / 10.f;
            scan -= std::floor(scan);
            pos = scan * length;
            advance = false;
        }

        const float stretchLog2 =
            clamp(params[STRETCH_PARAM].getValue() + inputs[STRETCH_INPUT].getVoltage(), 0.f, MAX_STRETCH_LOG2);
        const double stretch = std::exp2(stretchLog2);
        const int sizeIndex = clamp((int)std::round(params[WINDOW_PARAM].getValue()), 0, PaulstretchCore::NUM_SIZES - 1);
        const double pitch = pitchRatio(params[PITCH_PARAM].getValue() + inputs[PITCH_INPUT].getVoltage() * 12.f);

        const float* source[2] = {buffer[0].data(), buffer[1].data()};
        const int channels = stereo ? 2 : 1;
        float out[2] = {};
        core.next(source, channels, length, pos, stretch, pitch, advance, reversed, !recording, sizeIndex, out);
        if (!stereo) out[1] = out[0];
        // OUT L carries a mono mix when OUT R is unpatched. The channels have
        // independent random phases, so they add in power: scale by 1/sqrt(2).
        float left = out[0];
        if (stereo && !outputs[OUT_R_OUTPUT].isConnected()) left = (out[0] + out[1]) * float(M_SQRT1_2);

        outputs[OUT_L_OUTPUT].setVoltage(clamp(left * 5.f, -10.f, 10.f));
        outputs[OUT_R_OUTPUT].setVoltage(clamp(out[1] * 5.f, -10.f, 10.f));

        processHeads(source, channels, sizeIndex);

        lights[REC_LIGHT].setBrightnessSmooth(recording ? 1.f : 0.f, args.sampleTime);
        lights[FREEZE_LIGHT].setBrightnessSmooth(frozen ? 1.f : 0.f, args.sampleTime);
        lights[REVERSE_LIGHT].setBrightnessSmooth(reversed ? 1.f : 0.f, args.sampleTime);
    }

    // Runs the heads for a Paulstretch Heads expander on the right, if there is one.
    void processHeads(const float* const* source, int channels, int sizeIndex) {
        Module* expander = rightExpander.module;
        if (!expander || expander->model != modelPaulstretchHeads) {
            for (bool& a : headActive) a = false;
            return;
        }
        const auto* control = (const paulstretch::ToMain*)rightExpander.consumerMessage;
        auto* audio = (paulstretch::ToHeads*)expander->leftExpander.producerMessage;
        for (int h = 0; h < paulstretch::HEADS; h++) {
            const paulstretch::HeadControl& c = control->heads[h];
            float out[2] = {};
            if (control->valid && c.active) {
                if (!headActive[h]) heads[h].reset();
                headStart[h] = c.start;
                if (c.reset) headPos[h] = c.start * length;
                // SCAN sets the position directly, as on the main voice
                if (c.scanning && length > 0) {
                    double scan = c.start + c.scan / 10.0;
                    scan -= std::floor(scan);
                    headPos[h] = scan * length;
                }
                const double stretch = std::exp2(clamp(c.stretchLog2, 0.f, MAX_STRETCH_LOG2));
                heads[h].next(source, channels, length, headPos[h], stretch, pitchRatio(c.semitones), !c.freeze && !c.scanning, c.reverse,
                              !recording, sizeIndex, out);
                if (!stereo) out[1] = out[0];
            }
            headActive[h] = control->valid && c.active;
            headReversed[h] = c.reverse;
            headFrozen[h] = c.freeze || c.scanning;  // standing still: no arrow
            audio->out[h][0] = clamp(out[0] * 5.f, -10.f, 10.f);
            audio->out[h][1] = clamp(out[1] * 5.f, -10.f, 10.f);
        }
        audio->stereo = stereo;
        audio->valid = true;
        audio->depth = 0;
        for (int h = 0; h < paulstretch::HEADS; h++) audio->pos[h] = length > 0 ? (float)(headPos[h] / length) : 0.f;
        audio->window = length > 0 ? std::min(1.f, (float)heads[0].size() / length) : 0.f;
        expander->leftExpander.requestMessageFlip();
    }

    json_t* dataToJson() override {
        json_t* root = json_object();
        const bool file = fromFile && !filePath.empty();
        json_object_set_new(root, "length", json_integer(recording || file ? 0 : length));
        json_object_set_new(root, "stereo", json_boolean(stereo));
        json_object_set_new(root, "sampleRate", json_real(bufferRate));
        json_object_set_new(root, "position", json_real(pos));
        if (file) json_object_set_new(root, "path", json_string(filePath.c_str()));
        json_object_set_new(root, "storeFile", json_boolean(storeFile));
        json_object_set_new(root, "resetAllHeads", json_boolean(resetAllHeads));
        if (file && storeFile) json_object_set_new(root, "storedCopy", json_string(STORED_COPY));
        json_t* heads = json_array();
        for (double p : headPos) json_array_append_new(heads, json_real(p));
        json_object_set_new(root, "headPositions", heads);
        return root;
    }

    void dataFromJson(json_t* root) override {
        if (json_t* j = json_object_get(root, "length")) savedLength = json_integer_value(j);
        if (json_t* j = json_object_get(root, "stereo")) stereo = json_boolean_value(j);
        if (json_t* j = json_object_get(root, "sampleRate")) savedRate = json_number_value(j);
        if (json_t* j = json_object_get(root, "position")) pos = json_number_value(j);
        if (json_t* j = json_object_get(root, "path")) savedPath = json_string_value(j);
        if (json_t* j = json_object_get(root, "storeFile")) storeFile = json_boolean_value(j);
        if (json_t* j = json_object_get(root, "resetAllHeads")) resetAllHeads = json_boolean_value(j);
        if (json_t* j = json_object_get(root, "storedCopy")) savedCopy = json_string_value(j);
        if (json_t* j = json_object_get(root, "headPositions")) {
            for (int h = 0; h < paulstretch::HEADS && h < (int)json_array_size(j); h++)
                savedHeadPos[h] = json_number_value(json_array_get(j, h));
            haveSavedHeadPos = true;
        }
    }

    // The stored copy's name in the patch storage folder. It is a WAV file
    // holding what the module uses: at most the first 10 minutes and the first
    // two channels, at the file's own sample rate and sample size.
    static constexpr const char* STORED_COPY = "audio.wav";

    // Puts the heads back where the patch left them.
    void restoreHeadPositions() {
        if (!haveSavedHeadPos || length <= 0) return;
        for (int h = 0; h < paulstretch::HEADS; h++)
            headPos[h] = std::fmod(std::max(savedHeadPos[h], 0.0), (double)length);
    }

    // A loaded file is read again from the copy stored in the patch if there is
    // one, else from its path. A recording is stored as raw 32-bit floats: the
    // left channel, then the right if it's stereo.
    void onAdd(const AddEvent& e) override {
        const double savedPos = pos;
        if (!savedPath.empty()) {
            LoadedAudio a;
            bool ok = false;
            const std::string copy =
                savedCopy.empty() ? "" : system::join(getPatchStorageDirectory(), savedCopy);
            if (!copy.empty() && system::isFile(copy)) {
                ok = loadAudio(copy, APP->engine->getSampleRate(), a);
                if (ok) copiedFrom = savedPath, loadedFrom = copy;
                else WARN("Paulstretch: can't load the stored copy %s: %s", copy.c_str(), a.error.c_str());
            }
            if (!ok && (ok = loadAudio(savedPath, APP->engine->getSampleRate(), a))) loadedFrom = savedPath;
            if (ok) {
                install(a, APP->engine->getSampleRate());
                filePath = savedPath;
                fileTruncated = a.truncated;
                pos = (length > 0) ? std::fmod(std::max(savedPos, 0.0), (double)length) : 0.0;
                restoreHeadPositions();
            } else {
                loadError = system::getFilename(savedPath) + ": " + a.error;
                loadErrorTime = system::getTime();
                WARN("Paulstretch: can't load %s: %s", savedPath.c_str(), a.error.c_str());
            }
            return;
        }
        if (savedLength <= 0 || savedRate <= 0.f) return;
        const std::string path = system::join(getPatchStorageDirectory(), RECORDING_FILE);
        FILE* f = audiofile::openFile(path, "rb");
        if (!f) {
            WARN("Paulstretch: recording file %s is missing", path.c_str());
            return;
        }
        const float rate = APP->engine->getSampleRate();
        bufferRate = savedRate;
        const size_t n = std::max((size_t)(MAX_SECONDS * savedRate), (size_t)savedLength);
        for (auto& b : buffer) b.assign(n, 0.f);
        size_t got = std::fread(buffer[0].data(), sizeof(float), savedLength, f);
        if (stereo) {
            got = std::min(got, std::fread(buffer[1].data(), sizeof(float), savedLength, f));
        } else {
            std::copy(buffer[0].begin(), buffer[0].begin() + savedLength, buffer[1].begin());
        }
        std::fclose(f);
        length = (int64_t)got;
        pos = (length > 0) ? std::fmod(std::max(savedPos, 0.0), (double)length) : 0.0;
        restoreHeadPositions();
        dirty = false;
        if (rate != bufferRate) resample(rate);
    }

    void onSave(const SaveEvent& e) override {
        const std::string dir = createPatchStorageDirectory();
        saveFileCopy(dir);
        const std::string path = system::join(dir, RECORDING_FILE);
        const int64_t n = (recording || fromFile) ? 0 : length;
        if (n <= 0) {
            system::remove(path);
            return;
        }
        if (!dirty && system::isFile(path)) return;
        FILE* f = audiofile::openFile(path, "wb");
        if (!f) {
            WARN("Paulstretch: can't write %s", path.c_str());
            return;
        }
        std::fwrite(buffer[0].data(), sizeof(float), n, f);
        if (stereo) std::fwrite(buffer[1].data(), sizeof(float), n, f);
        std::fclose(f);
        dirty = false;
    }

    // Keeps the stored copy in step with the loaded file: writes one for a
    // newly loaded file, and removes it when it's no longer wanted.
    void saveFileCopy(const std::string& dir) {
        const bool want = storeFile && fromFile && !filePath.empty();
        const std::string dest = system::join(dir, STORED_COPY);
        if (want && !(copiedFrom == filePath && system::isFile(dest))) {
            // from the original, or from an older stored copy if the original is gone
            const std::string src = system::isFile(filePath) ? filePath : loadedFrom;
            AudioFileData data;
            std::string error;
            const std::string tmp = system::join(dir, "audio.tmp");
            if (src.empty() || !system::isFile(src)) {
                copyError = "the original file wasn't found";
            } else if (!readAudioFile(src, MAX_FILE_SECONDS, data, error) || !writeWavFile(tmp, data, error) ||
                       !system::rename(tmp, dest)) {
                copyError = error.empty() ? "couldn't write it" : error;
            } else {
                copiedFrom = filePath;
                loadedFrom = dest;
                copyError.clear();
            }
            system::remove(tmp);
            if (!copyError.empty()) {
                WARN("Paulstretch: can't store a copy of %s: %s", filePath.c_str(), copyError.c_str());
                return;  // keep whatever copy there is
            }
        }
        // remove copies that aren't wanted (including older ones under other names)
        for (const std::string& entry : system::getEntries(dir)) {
            const std::string name = system::getFilename(entry);
            if (name.rfind("audio", 0) == 0 && !(want && name == STORED_COPY)) system::remove(entry);
        }
        if (!want) {
            if (loadedFrom.rfind(dir, 0) == 0) loadedFrom = filePath;
            copiedFrom.clear();
            copyError.clear();
        }
    }
};

// "1:05" from a minute up, else "12.3 s"
static std::string formatDuration(double seconds) {
    if (seconds < 60.0) return string::f("%.1f s", seconds);
    const int s = (int)seconds;
    return string::f("%d:%02d", s / 60, s % 60);
}

// Shows the buffer: the stretch window's place in it while playing, or how
// full it is while recording, with the loaded file's name.
struct PaulstretchDisplay : TransparentWidget {
    Paulstretch* module = nullptr;

    void drawLayer(const DrawArgs& args, int layer) override {
        if (layer != 1) return;
        const float w = box.size.x, h = box.size.y;
        nvgBeginPath(args.vg);
        nvgRoundedRect(args.vg, 0, 0, w, h, 2.f);
        nvgFillColor(args.vg, nvgRGB(0x10, 0x10, 0x14));
        nvgFill(args.vg);
        if (!module) return;

        const int64_t length = module->length;
        const float rate = module->bufferRate;
        std::string text;
        if (module->recording) {
            const float fill = (float)length / std::max<int64_t>(1, module->capacity());
            nvgBeginPath(args.vg);
            nvgRect(args.vg, 1, 1, (w - 2) * fill, h - 2);
            nvgFillColor(args.vg, nvgRGBA(0xe0, 0x30, 0x30, 0xa0));
            nvgFill(args.vg);
            text = string::f("REC %.1f s", length / rate);
        } else if (length > 0) {
            // The main voice's window is a block, its centre (the part heard
            // most) a line, with an arrow for the direction. The heads have
            // their own displays on the expanders.
            const float iw = w - 2;
            const double size = module->core.size();
            const float span = std::min(1.f, (float)(size / length)) * iw;
            auto xAt = [&](double p) {
                const double f = std::fmod(p, (double)length) / length;
                return (float)((f < 0 ? f + 1 : f) * iw) + 1.f;
            };
            const NVGcolor amber = nvgRGB(0xf0, 0xb0, 0x40);
            const float x = xAt(module->pos);
            nvgBeginPath(args.vg);
            nvgRect(args.vg, x, 1, std::min(span, w - 1 - x), h - 2);
            if (x + span > w - 1) nvgRect(args.vg, 1, 1, x + span - (w - 1), h - 2);
            nvgFillColor(args.vg, nvgTransRGBAf(amber, 0.3f));
            nvgFill(args.vg);
            const float cx = xAt(module->pos + size / 2);
            nvgBeginPath(args.vg);
            nvgRect(args.vg, cx - 0.5f, 1, 1.f, h - 2);
            nvgFillColor(args.vg, amber);
            nvgFill(args.vg);
            if (!module->frozen && !module->scanning) {
                const float d = module->reversed ? -1.f : 1.f;
                nvgBeginPath(args.vg);
                nvgMoveTo(args.vg, cx + d * 1.f, 1.5f);
                nvgLineTo(args.vg, cx + d * 4.f, 3.5f);
                nvgLineTo(args.vg, cx + d * 1.f, 5.5f);
                nvgClosePath(args.vg);
                nvgFillColor(args.vg, amber);
                nvgFill(args.vg);
            }
            text = formatDuration(length / rate);
        } else {
            text = "EMPTY";
        }
        std::string name;
        if (module->loadState == Paulstretch::LOADING) {
            text = "LOADING";
        } else if (system::getTime() - module->loadErrorTime < 4.0) {
            text = "LOAD FAILED";
        } else if (module->fromFile && !module->recording) {
            name = system::getStem(module->filePath);
            if (name.size() > 13) name = name.substr(0, 12) + "~";
        }

        std::shared_ptr<Font> font = APP->window->loadFont(asset::system("res/fonts/ShareTechMono-Regular.ttf"));
        if (!font) return;
        nvgFontFaceId(args.vg, font->handle);
        nvgFontSize(args.vg, 10.f);
        nvgTextAlign(args.vg, NVG_ALIGN_RIGHT | NVG_ALIGN_MIDDLE);
        // a dark halo first, so the text reads over the blocks
        for (int pass = 0; pass < 2; pass++) {
            nvgFontBlur(args.vg, pass == 0 ? 2.f : 0.f);
            nvgFillColor(args.vg, pass == 0 ? nvgRGB(0x10, 0x10, 0x14) : nvgRGB(0xe8, 0xe8, 0xe8));
            for (int k = 0; k < (pass == 0 ? 3 : 1); k++) {
                nvgTextAlign(args.vg, NVG_ALIGN_RIGHT | NVG_ALIGN_MIDDLE);
                nvgText(args.vg, w - 3, h / 2, text.c_str(), nullptr);
                if (!name.empty()) {
                    nvgTextAlign(args.vg, NVG_ALIGN_LEFT | NVG_ALIGN_MIDDLE);
                    nvgText(args.vg, 3, h / 2, name.c_str(), nullptr);
                }
            }
        }
        nvgFontBlur(args.vg, 0.f);
    }
};


// The window sizes printed round the WINDOW knob, the selected one lit.
struct WindowScale : TransparentWidget {
    Paulstretch* module = nullptr;
    float radius = 0.f;  // px

    void drawLayer(const DrawArgs& args, int layer) override {
        if (layer != 1) return;
        std::shared_ptr<Font> font = APP->window->uiFont;
        if (!font) return;
        const int selected = module ? (int)module->params[Paulstretch::WINDOW_PARAM].getValue() : 4;
        nvgFontFaceId(args.vg, font->handle);
        nvgFontSize(args.vg, 7.5f);
        nvgTextAlign(args.vg, NVG_ALIGN_CENTER | NVG_ALIGN_MIDDLE);
        const int n = PaulstretchCore::NUM_SIZES;
        for (int i = 0; i < n; i++) {
            // same sweep as Rack's knobs: -150 to +150 degrees from the top
            const float a = math::rescale((float)i, 0.f, n - 1.f, -0.83f * M_PI, 0.83f * M_PI);
            const std::string text = string::f("%dk", PaulstretchCore::sizeForIndex(i) / 1024);
            nvgFillColor(args.vg, i == selected ? nvgRGB(0xf0, 0xb0, 0x40) : nvgRGB(0x90, 0x92, 0x9a));
            nvgText(args.vg, radius * std::sin(a), -radius * std::cos(a), text.c_str(), nullptr);
        }
    }
};

struct PaulstretchWidget : ModuleWidget {
    PaulstretchWidget(Paulstretch* module) {
        setModule(module);
        setPanel(createPanel(asset::plugin(pluginInstance, "res/Paulstretch.svg")));

        addChild(createWidget<ScrewSilver>(Vec(RACK_GRID_WIDTH, 0)));
        addChild(createWidget<ScrewSilver>(Vec(box.size.x - 2 * RACK_GRID_WIDTH, 0)));
        addChild(createWidget<ScrewSilver>(Vec(RACK_GRID_WIDTH, RACK_GRID_HEIGHT - RACK_GRID_WIDTH)));
        addChild(createWidget<ScrewSilver>(Vec(box.size.x - 2 * RACK_GRID_WIDTH, RACK_GRID_HEIGHT - RACK_GRID_WIDTH)));

        addText(25.4f, 9.f, "PAULSTRETCH", 12.f);
        // build stamp, so it's clear which build Rack has loaded
        addText(25.4f, 124.8f, "v" + pluginInstance->version + " " + std::string(__DATE__).substr(0, 6) + " " + std::string(__TIME__).substr(0, 5), 6.f,
                nvgRGB(0x90, 0x92, 0x9a));

        addParam(createParamCentered<RoundBigBlackKnob>(mm2px(Vec(13.f, 26.f)), module, Paulstretch::STRETCH_PARAM));
        addText(13.f, 39.5f, "STRETCH");
        addParam(createParamCentered<RoundLargeBlackKnob>(mm2px(Vec(37.f, 26.f)), module, Paulstretch::WINDOW_PARAM));
        auto* scale = createWidget<WindowScale>(mm2px(Vec(37.f, 26.f)));
        scale->module = module;
        scale->radius = mm2px(10.f);
        addChild(scale);
        addText(37.f, 39.5f, "WINDOW");

        addParam(createParamCentered<RoundSmallBlackKnob>(mm2px(Vec(7.6f, 48.f)), module, Paulstretch::START_PARAM));
        addText(7.6f, 54.2f, "START");
        addParam(createParamCentered<RoundSmallBlackKnob>(mm2px(Vec(19.2f, 48.f)), module, Paulstretch::PITCH_PARAM));
        addText(19.2f, 54.2f, "PITCH");
        addParam(createLightParamCentered<VCVLightLatch<MediumSimpleLight<RedLight>>>(
            mm2px(Vec(31.2f, 48.f)), module, Paulstretch::REC_PARAM, Paulstretch::REC_LIGHT));
        addText(31.2f, 54.2f, "REC");
        addParam(createLightParamCentered<VCVLightLatch<MediumSimpleLight<BlueLight>>>(
            mm2px(Vec(43.2f, 48.f)), module, Paulstretch::FREEZE_PARAM, Paulstretch::FREEZE_LIGHT));
        addText(43.2f, 54.2f, "FREEZE");

        auto* display = createWidget<PaulstretchDisplay>(mm2px(Vec(4.f, 58.5f)));
        display->box.size = mm2px(Vec(42.8f, 8.5f));
        display->module = module;
        addChild(display);

        const float x[4] = {7.6f, 19.2f, 31.2f, 43.2f};
        addJack(x[0], 81.f, "STRETCH", Paulstretch::STRETCH_INPUT);
        addJack(x[1], 81.f, "SCAN", Paulstretch::SCAN_INPUT);
        addJack(x[2], 81.f, "RESET", Paulstretch::RESET_INPUT);
        addJack(x[3], 81.f, "FREEZE", Paulstretch::FREEZE_INPUT);
        addJack(x[0], 97.f, "REC", Paulstretch::REC_INPUT);
        addJack(x[2], 97.f, "IN L", Paulstretch::IN_L_INPUT);
        addJack(x[3], 97.f, "IN R", Paulstretch::IN_R_INPUT);
        addJack(x[1], 97.f, "V/OCT", Paulstretch::PITCH_INPUT);
        addJack(x[0], 113.f, "REV", Paulstretch::REVERSE_INPUT);
        addParam(createLightParamCentered<VCVLightLatch<MediumSimpleLight<YellowLight>>>(
            mm2px(Vec(x[1], 113.f)), module, Paulstretch::REVERSE_PARAM, Paulstretch::REVERSE_LIGHT));
        addText(x[1], 106.6f, "REVERSE", 7.f);
        addOutput(createOutputCentered<PJ301MPort>(mm2px(Vec(x[2], 113.f)), module, Paulstretch::OUT_L_OUTPUT));
        addText(x[2], 106.6f, "OUT L", 7.f, nvgRGB(0x20, 0x20, 0x24));
        addOutput(createOutputCentered<PJ301MPort>(mm2px(Vec(x[3], 113.f)), module, Paulstretch::OUT_R_OUTPUT));
        addText(x[3], 106.6f, "OUT R", 7.f, nvgRGB(0x20, 0x20, 0x24));
    }

    void addJack(float x, float y, const std::string& name, int inputId) {
        addInput(createInputCentered<PJ301MPort>(mm2px(Vec(x, y)), module, inputId));
        addText(x, y - 6.4f, name, 7.f);
    }

    // text centred on (x, y) in mm
    void addText(float x, float y, const std::string& text, float fontSize = 8.f,
                 NVGcolor color = nvgRGB(0xe8, 0xe8, 0xe8)) {
        auto* t = createWidget<PanelText>(mm2px(Vec(x, y)));
        t->text = text;
        t->fontSize = fontSize;
        t->color = color;
        addChild(t);
    }

    void step() override {
        if (auto* m = getModule<Paulstretch>()) m->pollLoad();
        ModuleWidget::step();
    }

    void onPathDrop(const PathDropEvent& e) override {
        auto* m = getModule<Paulstretch>();
        if (!m || e.paths.empty()) return;
        m->startLoad(e.paths[0]);
        e.consume(this);
    }

    void loadDialog(Paulstretch* m) {
        const std::string dir = m->filePath.empty() ? "" : system::getDirectory(m->filePath);
        // no commas in the name: osdialog splits on them and asserts
        osdialog_filters* filters = osdialog_filters_parse("WAV and AIFF audio:wav,wave,aif,aiff,aifc");
        char* path = osdialog_file(OSDIALOG_OPEN, dir.empty() ? nullptr : dir.c_str(), nullptr, filters);
        osdialog_filters_free(filters);
        if (!path) return;
        m->startLoad(path);
        std::free(path);
    }

    void appendContextMenu(Menu* menu) override {
        auto* module = getModule<Paulstretch>();
        menu->addChild(new MenuSeparator);
        menu->addChild(createMenuItem("Load audio file…", "WAV, AIFF", [=]() { loadDialog(module); }));
        if (module->fromFile && !module->filePath.empty()) {
            menu->addChild(createMenuLabel("File: " + system::getFilename(module->filePath) +
                                           (module->fileTruncated ? " (first 10 minutes)" : "")));
        }
        if (!module->loadError.empty()) menu->addChild(createMenuLabel("Couldn't load " + module->loadError));
        menu->addChild(createBoolPtrMenuItem("Store a copy of the file in the patch", "", &module->storeFile));
        if (module->storeFile && module->fromFile && !module->filePath.empty()) {
            if (!module->copyError.empty()) {
                menu->addChild(createMenuLabel("Couldn't store a copy: " + module->copyError));
            } else if (module->copiedFrom == module->filePath) {
                menu->addChild(createMenuLabel("Stored in the patch"));
            } else {
                menu->addChild(createMenuLabel("Stored when the patch is next saved"));
            }
            if (!system::isFile(module->filePath))
                menu->addChild(createMenuLabel("The original file is missing: keep this on"));
        }
        menu->addChild(createMenuItem("Clear buffer", "", [=]() { module->clearRequested = true; }));
        menu->addChild(new MenuSeparator);
        menu->addChild(createBoolPtrMenuItem("RESET also resets all heads", "", &module->resetAllHeads));
    }
};

Model* modelPaulstretch = createModel<Paulstretch, PaulstretchWidget>("Paulstretch");
