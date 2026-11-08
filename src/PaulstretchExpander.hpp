#pragma once

// Messages between Paulstretch and the Paulstretch Heads expanders on its
// right. Up to MAX_EXPANDERS Heads modules can sit in a row, each passing
// messages on to the next. The heads' DSP runs in Paulstretch, which owns the
// buffer; the expanders only send their controls and receive audio. Both go
// through Rack's expander message flip, so each step along the row adds one
// sample of latency and nothing is shared between threads.
namespace paulstretch {

constexpr int HEADS_PER_MODULE = 4;
constexpr int MAX_EXPANDERS = 3;
constexpr int HEADS = HEADS_PER_MODULE * MAX_EXPANDERS;

struct HeadControl {
    float stretchLog2 = 3.f;
    float semitones = 0.f;
    float start = 0.f;
    bool freeze = false;
    bool reverse = false;
    bool reset = false;   // RESET trigger arrived this sample
    bool scanning = false;  // SCAN is patched: the position follows `scan`
    float scan = 0.f;       // volts, 0-10 V across the buffer from `start`
    bool active = false;  // an output needs this head; otherwise it isn't computed
};

// towards Paulstretch. Each expander fills in its own heads and passes on
// those of the expanders further right.
struct ToMain {
    HeadControl heads[HEADS];
    bool valid = false;
};

// away from Paulstretch. `depth` tells each expander its place in the row:
// 0 for the one next to Paulstretch.
struct ToHeads {
    float out[HEADS][2] = {};  // volts
    bool stereo = false;
    bool valid = false;
    int depth = 0;
    // for the expanders' displays
    float pos[HEADS] = {};  // each head's read position, 0-1 across the buffer
    float window = 0.f;     // the window's length, 0-1 of the buffer
};

// Each head's colour, by its column on the expander: its number and its
// column on the expander's display. Every expander uses the same four, since
// each shows only its own heads. (Include after rack.hpp.)
inline NVGcolor headColor(int h) {
    static const NVGcolor colors[HEADS_PER_MODULE] = {nvgRGB(0x40, 0xc8, 0xe0), nvgRGB(0xb0, 0x80, 0xf0),
                                                      nvgRGB(0x70, 0xd0, 0x70), nvgRGB(0xf0, 0x70, 0xa8)};
    return colors[(h < 0 ? 0 : h) % HEADS_PER_MODULE];
}

}  // namespace paulstretch
