#pragma once
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

// Reads WAV (RIFF) and AIFF/AIFC files into float channels, -1..1.
// Integer PCM of 8 to 32 bits and 32/64-bit float. Files with more than two
// channels give their first two.
struct AudioFileData {
    std::vector<float> channels[2];
    int numChannels = 0;  // 1 or 2
    float sampleRate = 0.f;
    int64_t frames = 0;
    bool truncated = false;  // longer than maxSeconds
    int sourceChannels = 0;  // channels in the file, before keeping the first two
    int bits = 16;           // the file's sample size
    bool isFloat = false;
};

#if defined ARCH_WIN
#include <rack.hpp>  // for string::UTF8toUTF16
#endif

namespace audiofile {

// Opens a file by its UTF-8 path, as Rack gives paths. On Windows, fopen reads
// the path in the local code page, so file names with other characters need
// _wfopen.
inline FILE* openFile(const std::string& path, const char* mode) {
#if defined ARCH_WIN
    return _wfopen(rack::string::UTF8toUTF16(path).c_str(), rack::string::UTF8toUTF16(mode).c_str());
#else
    return std::fopen(path.c_str(), mode);
#endif
}

inline uint32_t le32(const uint8_t* p) { return p[0] | p[1] << 8 | p[2] << 16 | (uint32_t)p[3] << 24; }
inline uint16_t le16(const uint8_t* p) { return p[0] | p[1] << 8; }
inline uint32_t be32(const uint8_t* p) { return (uint32_t)p[0] << 24 | p[1] << 16 | p[2] << 8 | p[3]; }
inline uint16_t be16(const uint8_t* p) { return p[0] << 8 | p[1]; }

// 80-bit IEEE extended, as AIFF stores its sample rate
inline double extended80(const uint8_t* p) {
    const int exponent = ((p[0] & 0x7f) << 8 | p[1]) - 16383 - 63;
    uint64_t mantissa = 0;
    for (int i = 0; i < 8; i++) mantissa = mantissa << 8 | p[2 + i];
    const double v = std::ldexp((double)mantissa, exponent);
    return (p[0] & 0x80) ? -v : v;
}

struct Format {
    int channels = 0;
    int bytes = 0;  // per sample
    bool isFloat = false;
    bool bigEndian = false;
    bool unsigned8 = false;  // WAV's 8-bit samples are unsigned
    double sampleRate = 0.0;
    int64_t dataOffset = -1;
    int64_t dataBytes = 0;
};

inline float decodeSample(const uint8_t* p, const Format& f) {
    uint8_t b[8];
    // put the bytes in little-endian order
    for (int i = 0; i < f.bytes; i++) b[i] = f.bigEndian ? p[f.bytes - 1 - i] : p[i];
    if (f.isFloat) {
        if (f.bytes == 4) {
            float v;
            std::memcpy(&v, b, 4);
            return std::isfinite(v) ? v : 0.f;
        }
        double v;
        std::memcpy(&v, b, 8);
        return std::isfinite(v) ? (float)v : 0.f;
    }
    if (f.bytes == 1) return f.unsigned8 ? (b[0] - 128) / 128.f : (int8_t)b[0] / 128.f;
    uint32_t v = 0;
    for (int i = 0; i < f.bytes; i++) v |= (uint32_t)b[i] << (8 * (4 - f.bytes + i));
    return (int32_t)v / 2147483648.f;
}

inline bool parseWav(FILE* file, int64_t fileSize, Format& f, std::string& error) {
    uint8_t h[8];
    bool haveFmt = false;
    int64_t pos = 12;
    while (pos + 8 <= fileSize) {
        std::fseek(file, (long)pos, SEEK_SET);
        if (std::fread(h, 1, 8, file) != 8) break;
        const int64_t size = le32(h + 4);
        if (!std::memcmp(h, "fmt ", 4)) {
            uint8_t c[40] = {};
            if (std::fread(c, 1, std::min<int64_t>(size, 40), file) < 16) break;
            int tag = le16(c);
            if (tag == 0xfffe && size >= 26) tag = le16(c + 24);  // WAVE_FORMAT_EXTENSIBLE sub-format
            f.channels = le16(c + 2);
            f.sampleRate = le32(c + 4);
            const int bits = le16(c + 14);
            f.bytes = (bits + 7) / 8;
            if (tag == 1) {
                f.isFloat = false;
                f.unsigned8 = f.bytes == 1;
                if (f.bytes < 1 || f.bytes > 4) {
                    error = "unsupported bit depth " + std::to_string(bits);
                    return false;
                }
            } else if (tag == 3) {
                f.isFloat = true;
                if (f.bytes != 4 && f.bytes != 8) {
                    error = "unsupported float size " + std::to_string(bits);
                    return false;
                }
            } else {
                error = "compressed WAV (format " + std::to_string(tag) + ") isn't supported";
                return false;
            }
            haveFmt = true;
        } else if (!std::memcmp(h, "data", 4)) {
            f.dataOffset = pos + 8;
            // some writers leave the size at 0 or 0xffffffff when streaming
            f.dataBytes = (size == 0 || pos + 8 + size > fileSize) ? fileSize - (pos + 8) : size;
            if (haveFmt) return true;
        }
        pos += 8 + size + (size & 1);
    }
    if (!haveFmt) error = "no fmt chunk";
    else if (f.dataOffset < 0) error = "no audio data";
    return haveFmt && f.dataOffset >= 0;
}

inline bool parseAiff(FILE* file, int64_t fileSize, bool aifc, Format& f, std::string& error) {
    uint8_t h[8];
    bool haveComm = false;
    int64_t pos = 12;
    f.bigEndian = true;
    while (pos + 8 <= fileSize) {
        std::fseek(file, (long)pos, SEEK_SET);
        if (std::fread(h, 1, 8, file) != 8) break;
        const int64_t size = be32(h + 4);
        if (!std::memcmp(h, "COMM", 4)) {
            uint8_t c[22] = {};
            if (std::fread(c, 1, std::min<int64_t>(size, 22), file) < 18) break;
            f.channels = be16(c);
            const int bits = be16(c + 6);
            f.bytes = (bits + 7) / 8;
            f.sampleRate = extended80(c + 8);
            if (aifc && size >= 22) {
                if (!std::memcmp(c + 18, "sowt", 4)) {
                    f.bigEndian = false;
                } else if (!std::memcmp(c + 18, "fl32", 4) || !std::memcmp(c + 18, "FL32", 4)) {
                    f.isFloat = true;
                    f.bytes = 4;
                } else if (!std::memcmp(c + 18, "fl64", 4) || !std::memcmp(c + 18, "FL64", 4)) {
                    f.isFloat = true;
                    f.bytes = 8;
                } else if (std::memcmp(c + 18, "NONE", 4) && std::memcmp(c + 18, "twos", 4)) {
                    error = "compressed AIFF (" + std::string((const char*)c + 18, 4) + ") isn't supported";
                    return false;
                }
            }
            if (!f.isFloat && (f.bytes < 1 || f.bytes > 4)) {
                error = "unsupported bit depth " + std::to_string(bits);
                return false;
            }
            haveComm = true;
        } else if (!std::memcmp(h, "SSND", 4)) {
            uint8_t s[8];
            if (std::fread(s, 1, 8, file) != 8) break;
            f.dataOffset = pos + 16 + be32(s);
            f.dataBytes = std::min<int64_t>(size - 8 - be32(s), fileSize - f.dataOffset);
        }
        pos += 8 + size + (size & 1);
    }
    if (!haveComm) error = "no COMM chunk";
    else if (f.dataOffset < 0) error = "no audio data";
    return haveComm && f.dataOffset >= 0;
}

}  // namespace audiofile

// Returns false with `error` set if the file can't be read.
// Reads at most `maxSeconds` of audio.
inline bool readAudioFile(const std::string& path, double maxSeconds, AudioFileData& out, std::string& error) {
    using namespace audiofile;
    FILE* file = audiofile::openFile(path, "rb");
    if (!file) {
        error = "can't open the file";
        return false;
    }
    std::fseek(file, 0, SEEK_END);
    const int64_t fileSize = std::ftell(file);
    std::fseek(file, 0, SEEK_SET);
    uint8_t h[12] = {};
    Format f;
    bool ok = false;
    if (std::fread(h, 1, 12, file) == 12) {
        if (!std::memcmp(h, "RIFF", 4) && !std::memcmp(h + 8, "WAVE", 4)) {
            ok = parseWav(file, fileSize, f, error);
        } else if (!std::memcmp(h, "FORM", 4) && (!std::memcmp(h + 8, "AIFF", 4) || !std::memcmp(h + 8, "AIFC", 4))) {
            ok = parseAiff(file, fileSize, !std::memcmp(h + 8, "AIFC", 4), f, error);
        } else if (!std::memcmp(h, "RF64", 4)) {
            error = "RF64 WAV files aren't supported";
        } else {
            error = "not a WAV or AIFF file";
        }
    } else {
        error = "file too short";
    }
    if (ok && (f.channels < 1 || f.sampleRate < 1000.0 || f.sampleRate > 768000.0)) {
        error = "bad channel count or sample rate";
        ok = false;
    }
    if (!ok) {
        std::fclose(file);
        return false;
    }

    const int frameBytes = f.channels * f.bytes;
    int64_t frames = f.dataBytes / frameBytes;
    const int64_t maxFrames = (int64_t)(maxSeconds * f.sampleRate);
    out.truncated = frames > maxFrames;
    frames = std::min(frames, maxFrames);
    out.numChannels = std::min(f.channels, 2);
    out.sourceChannels = f.channels;
    out.bits = f.bytes * 8;
    out.isFloat = f.isFloat;
    out.sampleRate = (float)f.sampleRate;
    for (int c = 0; c < out.numChannels; c++) out.channels[c].resize(frames);

    std::fseek(file, (long)f.dataOffset, SEEK_SET);
    const int64_t block = 65536;
    std::vector<uint8_t> bytes(block * frameBytes);
    int64_t done = 0;
    while (done < frames) {
        const int64_t want = std::min(block, frames - done);
        const int64_t got = (int64_t)std::fread(bytes.data(), frameBytes, want, file);
        for (int64_t i = 0; i < got; i++) {
            const uint8_t* p = bytes.data() + i * frameBytes;
            for (int c = 0; c < out.numChannels; c++) out.channels[c][done + i] = decodeSample(p + c * f.bytes, f);
        }
        done += got;
        if (got < want) break;
    }
    std::fclose(file);
    out.frames = done;
    for (int c = 0; c < out.numChannels; c++) out.channels[c].resize(done);
    if (done == 0) {
        error = "no audio data";
        return false;
    }
    return true;
}

// Writes `data` as a WAV file at its own sample rate, with the same sample size
// it was read with (64-bit float is written as 32-bit float, which holds
// everything the module uses). Returns false with `error` set on failure.
inline bool writeWavFile(const std::string& path, const AudioFileData& data, std::string& error) {
    const int channels = data.numChannels;
    const bool isFloat = data.isFloat;
    const int bytes = isFloat ? 4 : std::max(1, std::min(4, data.bits / 8));
    const uint64_t dataBytes = (uint64_t)data.frames * channels * bytes;
    if (channels < 1 || dataBytes > 0xffffffffull - 64) {
        error = "nothing to write, or too long for a WAV file";
        return false;
    }
    FILE* file = audiofile::openFile(path, "wb");
    if (!file) {
        error = "can't create the file";
        return false;
    }
    auto u32 = [&](uint32_t v) { uint8_t b[4] = {(uint8_t)v, (uint8_t)(v >> 8), (uint8_t)(v >> 16), (uint8_t)(v >> 24)}; std::fwrite(b, 1, 4, file); };
    auto u16 = [&](uint16_t v) { uint8_t b[2] = {(uint8_t)v, (uint8_t)(v >> 8)}; std::fwrite(b, 1, 2, file); };
    const uint32_t rate = (uint32_t)std::lround(data.sampleRate);
    std::fwrite("RIFF", 1, 4, file);
    u32((uint32_t)(36 + dataBytes + (dataBytes & 1)));
    std::fwrite("WAVEfmt ", 1, 8, file);
    u32(16);
    u16(isFloat ? 3 : 1);
    u16((uint16_t)channels);
    u32(rate);
    u32(rate * channels * bytes);
    u16((uint16_t)(channels * bytes));
    u16((uint16_t)(bytes * 8));
    std::fwrite("data", 1, 4, file);
    u32((uint32_t)dataBytes);
    std::vector<uint8_t> block;
    const int64_t chunk = 65536;
    for (int64_t start = 0; start < data.frames; start += chunk) {
        const int64_t n = std::min(chunk, data.frames - start);
        block.assign((size_t)(n * channels * bytes), 0);
        uint8_t* p = block.data();
        for (int64_t i = 0; i < n; i++) {
            for (int c = 0; c < channels; c++, p += bytes) {
                const float x = data.channels[c][start + i];
                if (isFloat) {
                    std::memcpy(p, &x, 4);
                } else if (bytes == 1) {
                    p[0] = (uint8_t)std::lround(std::max(-128.f, std::min(127.f, x * 128.f)) + 128.f);
                } else {
                    const double scale = std::ldexp(1.0, bytes * 8 - 1);
                    const double v = std::max(-scale, std::min(scale - 1.0, std::round((double)x * scale)));
                    const int32_t iv = (int32_t)v;
                    for (int k = 0; k < bytes; k++) p[k] = (uint8_t)(iv >> (8 * k));
                }
            }
        }
        std::fwrite(block.data(), 1, block.size(), file);
    }
    if (dataBytes & 1) std::fputc(0, file);
    const bool ok = std::fflush(file) == 0 && !std::ferror(file);
    std::fclose(file);
    if (!ok) error = "couldn't write the file";
    return ok;
}
