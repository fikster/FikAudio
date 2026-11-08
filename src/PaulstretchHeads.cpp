#include "plugin.hpp"

#include "PanelText.hpp"
#include "PaulstretchExpander.hpp"

using paulstretch::HEADS_PER_MODULE;
using paulstretch::MAX_EXPANDERS;

// Four more read heads on a Paulstretch's buffer. Place it directly to the
// right of a Paulstretch, or of another Paulstretch Heads: up to three in a
// row, for heads 1-4, 5-8 and 9-12. Each head has its own stretch, pitch,
// start, freeze, reverse and scan, and its own outputs. The stretching itself runs in the Paulstretch
// module (see PaulstretchExpander.hpp); this module passes messages along the
// row in both directions.
struct PaulstretchHeads : Module {
    static constexpr int PER = HEADS_PER_MODULE;
    enum ParamId {
        ENUMS(STRETCH_PARAM, PER),
        ENUMS(PITCH_PARAM, PER),
        ENUMS(START_PARAM, PER),
        ENUMS(LEVEL_PARAM, PER),  // no longer used; kept so later ids stay the same in saved patches
        ENUMS(FREEZE_PARAM, PER),
        ENUMS(REVERSE_PARAM, PER),
        PARAMS_LEN
    };
    enum InputId {
        ENUMS(STRETCH_INPUT, PER),
        ENUMS(PITCH_INPUT, PER),
        ENUMS(FREEZE_INPUT, PER),
        RESET_INPUT,
        ENUMS(REVERSE_INPUT, PER),
        ENUMS(SCAN_INPUT, PER),
        INPUTS_LEN
    };
    enum OutputId { ENUMS(OUT_L_OUTPUT, PER), ENUMS(OUT_R_OUTPUT, PER), OUTPUTS_LEN };
    enum LightId { ENUMS(FREEZE_LIGHT, PER), LINK_LIGHT, ENUMS(REVERSE_LIGHT, PER), LIGHTS_LEN };

    dsp::SchmittTrigger freezeGate[PER], reverseGate[PER], resetTrigger;
    bool scanning[PER] = {};
    // for the display: read by the UI thread, written here
    float dispPos[PER] = {};
    float dispWindow = 0.f;
    bool dispActive[PER] = {}, dispReversed[PER] = {}, dispStill[PER] = {};
    bool linked = false;
    std::atomic<int> index{-1};  // place in the row (0 next to Paulstretch), -1 when not linked

    PaulstretchHeads() {
        config(PARAMS_LEN, INPUTS_LEN, OUTPUTS_LEN, LIGHTS_LEN);
        for (int h = 0; h < PER; h++) {
            const std::string n = "Head " + std::to_string(h + 1) + " ";
            // defaults an octave of stretch apart, so the heads differ from the start
            configParam(STRETCH_PARAM + h, 0.f, 13.f, 3.f + h, n + "stretch", "x", 2.f);
            configParam(PITCH_PARAM + h, -24.f, 24.f, 0.f, n + "pitch", " semitones");
            getParamQuantity(PITCH_PARAM + h)->snapEnabled = true;
            configParam(START_PARAM + h, 0.f, 1.f, 0.f, n + "start position", "%", 0.f, 100.f);
            configSwitch(FREEZE_PARAM + h, 0.f, 1.f, 0.f, n + "freeze", {"Off", "On"});
            configInput(STRETCH_INPUT + h, n + "stretch CV (1 V doubles the stretch)");
            configInput(PITCH_INPUT + h, n + "pitch (1 V/oct)");
            configInput(FREEZE_INPUT + h, n + "freeze gate");
            configSwitch(REVERSE_PARAM + h, 0.f, 1.f, 0.f, n + "reverse", {"Off", "On"});
            configInput(REVERSE_INPUT + h, n + "reverse gate (flips the direction while high)");
            configInput(SCAN_INPUT + h, n + "scan position (0-10 V across the buffer from START)");
            configOutput(OUT_L_OUTPUT + h, n + "left (mono mix when right is unpatched)");
            configOutput(OUT_R_OUTPUT + h, n + "right");
        }
        configInput(RESET_INPUT, "Reset this expander's heads to their start positions");
        configLight(LINK_LIGHT, "Linked to a Paulstretch on the left (directly, or through up to two more Heads)");

        leftExpander.producerMessage = new paulstretch::ToHeads;
        leftExpander.consumerMessage = new paulstretch::ToHeads;
        rightExpander.producerMessage = new paulstretch::ToMain;
        rightExpander.consumerMessage = new paulstretch::ToMain;
    }

    ~PaulstretchHeads() override {
        delete (paulstretch::ToHeads*)leftExpander.producerMessage;
        delete (paulstretch::ToHeads*)leftExpander.consumerMessage;
        delete (paulstretch::ToMain*)rightExpander.producerMessage;
        delete (paulstretch::ToMain*)rightExpander.consumerMessage;
    }

    // left, or the two channels mixed into it when right is unpatched; a mono
    // source already has the same in both
    static float leftOrMix(float l, float r, bool rightPatched, bool stereo) {
        return (rightPatched || !stereo) ? l : (l + r) * float(M_SQRT1_2);
    }

    void process(const ProcessArgs& args) override {
        const bool reset = resetTrigger.process(inputs[RESET_INPUT].getVoltage(), 0.1f, 1.f);

        // our place in the row comes with the audio from the left
        Module* left = leftExpander.module;
        const bool leftOk = left && (left->model == modelPaulstretch || left->model == modelPaulstretchHeads);
        const auto* down = (const paulstretch::ToHeads*)leftExpander.consumerMessage;
        const int depth = (leftOk && down->valid) ? down->depth : -1;
        linked = depth >= 0 && depth < MAX_EXPANDERS;
        index = linked ? depth : -1;
        lights[LINK_LIGHT].setBrightnessSmooth(linked ? 1.f : 0.f, args.sampleTime);
        const int base = linked ? depth * PER : 0;
        dispWindow = linked ? down->window : 0.f;
        const bool stereo = linked && down->stereo;

        // controls towards Paulstretch: ours, plus those of the expanders further right
        Module* right = rightExpander.module;
        const bool rightOk = right && right->model == modelPaulstretchHeads;
        auto* up = leftOk ? (paulstretch::ToMain*)left->rightExpander.producerMessage : nullptr;
        if (up) {
            const auto* fromRight = (const paulstretch::ToMain*)rightExpander.consumerMessage;
            const bool relay = linked && rightOk && fromRight->valid;
            for (int i = 0; i < paulstretch::HEADS; i++)
                up->heads[i] = (relay && i >= base + PER) ? fromRight->heads[i] : paulstretch::HeadControl();
            up->valid = linked;
        }

        for (int h = 0; h < PER; h++) {
            freezeGate[h].process(inputs[FREEZE_INPUT + h].getVoltage(), 0.1f, 1.f);
            const bool frozen = params[FREEZE_PARAM + h].getValue() > 0.5f || freezeGate[h].isHigh();
            lights[FREEZE_LIGHT + h].setBrightnessSmooth(frozen ? 1.f : 0.f, args.sampleTime);
            reverseGate[h].process(inputs[REVERSE_INPUT + h].getVoltage(), 0.1f, 1.f);
            const bool reversed = (params[REVERSE_PARAM + h].getValue() > 0.5f) != reverseGate[h].isHigh();
            lights[REVERSE_LIGHT + h].setBrightnessSmooth(reversed ? 1.f : 0.f, args.sampleTime);
            scanning[h] = inputs[SCAN_INPUT + h].isConnected();
            const bool outL = outputs[OUT_L_OUTPUT + h].isConnected();
            const bool outR = outputs[OUT_R_OUTPUT + h].isConnected();

            if (up && linked) {
                paulstretch::HeadControl& c = up->heads[base + h];
                c.stretchLog2 = params[STRETCH_PARAM + h].getValue() + inputs[STRETCH_INPUT + h].getVoltage();
                c.semitones = params[PITCH_PARAM + h].getValue() + inputs[PITCH_INPUT + h].getVoltage() * 12.f;
                c.start = params[START_PARAM + h].getValue();
                c.freeze = frozen;
                c.reverse = reversed;
                c.reset = reset;
                c.scanning = scanning[h];
                c.scan = inputs[SCAN_INPUT + h].getVoltage();
                c.active = outL || outR;
            }

            dispActive[h] = linked && (outL || outR);
            dispPos[h] = linked ? down->pos[base + h] : 0.f;
            dispReversed[h] = reversed;
            dispStill[h] = frozen || scanning[h];

            const float l = linked ? down->out[base + h][0] : 0.f;
            const float r = linked ? down->out[base + h][1] : 0.f;
            outputs[OUT_L_OUTPUT + h].setVoltage(leftOrMix(l, r, outR, stereo));
            outputs[OUT_R_OUTPUT + h].setVoltage(r);
        }

        if (up) left->rightExpander.requestMessageFlip();

        // audio on to the next expander, which learns its place from `depth`
        if (rightOk) {
            auto* fwd = (paulstretch::ToHeads*)right->leftExpander.producerMessage;
            if (linked) {
                *fwd = *down;
                fwd->depth = depth + 1;
            } else {
                fwd->valid = false;
            }
            right->leftExpander.requestMessageFlip();
        }
    }
};

// This expander's heads on the buffer, which runs from top to bottom: one
// column per head, in its colour. Each head's window is a dim block, its
// centre (the part heard most) a line, and an arrow shows the direction.
struct HeadsDisplay : TransparentWidget {
    PaulstretchHeads* module = nullptr;

    void drawLayer(const DrawArgs& args, int layer) override {
        if (layer != 1) return;
        const float w = box.size.x, h = box.size.y;
        nvgBeginPath(args.vg);
        nvgRoundedRect(args.vg, 0, 0, w, h, 2.f);
        nvgFillColor(args.vg, nvgRGB(0x10, 0x10, 0x14));
        nvgFill(args.vg);
        const int per = PaulstretchHeads::PER;
        const float lw = (w - 2) / per, ih = h - 2;
        for (int i = 1; i < per; i++) {
            nvgBeginPath(args.vg);
            nvgRect(args.vg, 1 + i * lw - 0.25f, 1, 0.5f, ih);
            nvgFillColor(args.vg, nvgRGBA(0xff, 0xff, 0xff, 0x14));
            nvgFill(args.vg);
        }
        if (!module || !module->linked) return;
        const int base = std::max(0, module->index.load()) * per;
        const float span = std::min(1.f, module->dispWindow) * ih;
        auto yAt = [&](float f) {
            f -= std::floor(f);
            return 1 + f * ih;
        };
        for (int i = 0; i < per; i++) {
            if (!module->dispActive[i]) continue;
            const NVGcolor color = paulstretch::headColor(base + i);
            const float x = 1 + i * lw + 0.5f, cw = lw - 1;
            const float y = yAt(module->dispPos[i]);
            nvgBeginPath(args.vg);
            nvgRect(args.vg, x, y, cw, std::min(span, h - 1 - y));
            if (y + span > h - 1) nvgRect(args.vg, x, 1, cw, y + span - (h - 1));
            nvgFillColor(args.vg, nvgTransRGBAf(color, 0.3f));
            nvgFill(args.vg);
            const float cy = yAt(module->dispPos[i] + module->dispWindow / 2);
            nvgBeginPath(args.vg);
            nvgRect(args.vg, x, cy - 0.5f, cw, 1.f);
            nvgFillColor(args.vg, color);
            nvgFill(args.vg);
            if (!module->dispStill[i]) {
                const float d = module->dispReversed[i] ? -1.f : 1.f, mx = x + cw / 2;
                nvgBeginPath(args.vg);
                nvgMoveTo(args.vg, mx - cw * 0.35f, cy + d * 1.f);
                nvgLineTo(args.vg, mx + cw * 0.35f, cy + d * 1.f);
                nvgLineTo(args.vg, mx, cy + d * (1.f + cw * 0.5f));
                nvgClosePath(args.vg);
                nvgFill(args.vg);
            }
        }
    }
};

struct PaulstretchHeadsWidget : ModuleWidget {
    PaulstretchHeadsWidget(PaulstretchHeads* module) {
        setModule(module);
        setPanel(createPanel(asset::plugin(pluginInstance, "res/PaulstretchHeads.svg")));

        addChild(createWidget<ScrewSilver>(Vec(RACK_GRID_WIDTH, 0)));
        addChild(createWidget<ScrewSilver>(Vec(box.size.x - 2 * RACK_GRID_WIDTH, 0)));
        addChild(createWidget<ScrewSilver>(Vec(RACK_GRID_WIDTH, RACK_GRID_HEIGHT - RACK_GRID_WIDTH)));
        addChild(createWidget<ScrewSilver>(Vec(box.size.x - 2 * RACK_GRID_WIDTH, RACK_GRID_HEIGHT - RACK_GRID_WIDTH)));

        addText(40.64f, 9.f, "PAULSTRETCH HEADS", 11.f);

        // one column per head, row names down the left, shared jacks on the right
        const float col[PaulstretchHeads::PER] = {21.f, 34.5f, 48.f, 61.5f};
        const float shared = 74.5f, names = 7.f;

        // knob rows, then jack rows, then the outputs in the light box
        const float kStretch = 25.f, kPitch = 34.f, kStart = 42.f, kFreeze = 49.5f, kReverse = 56.5f;
        const float jStretch = 67.f, jPitch = 76.f, jScan = 85.f, jFreeze = 94.f, jReverse = 103.f, jOutL = 112.f, jOutR = 121.f;

        addText(names, kStretch, "STRETCH", 7.f);
        addText(names, kPitch, "PITCH", 7.f);
        addText(names, kStart, "START", 7.f);
        addText(names, kFreeze, "FREEZE", 7.f);
        addText(names, kReverse, "REVERSE", 7.f);
        addText(names, jStretch, "STR CV", 7.f);
        addText(names, jPitch, "V/OCT", 7.f);
        addText(names, jScan, "SCAN", 7.f);
        addText(names, jFreeze, "FRZ GATE", 7.f);
        addText(names, jReverse, "REV GATE", 7.f);
        addText(names, jOutL, "OUT L", 7.f);
        addText(names, jOutR, "OUT R", 7.f);

        for (int h = 0; h < PaulstretchHeads::PER; h++) {
            const float x = col[h];
            numbers[h] = addText(x, 17.f, std::to_string(h + 1), 10.f, paulstretch::headColor(h));
            addParam(createParamCentered<RoundSmallBlackKnob>(mm2px(Vec(x, kStretch)), module, PaulstretchHeads::STRETCH_PARAM + h));
            addParam(createParamCentered<RoundSmallBlackKnob>(mm2px(Vec(x, kPitch)), module, PaulstretchHeads::PITCH_PARAM + h));
            addParam(createParamCentered<Trimpot>(mm2px(Vec(x, kStart)), module, PaulstretchHeads::START_PARAM + h));
            addParam(createLightParamCentered<VCVLightLatch<MediumSimpleLight<BlueLight>>>(
                mm2px(Vec(x, kFreeze)), module, PaulstretchHeads::FREEZE_PARAM + h, PaulstretchHeads::FREEZE_LIGHT + h));
            addParam(createLightParamCentered<VCVLightLatch<MediumSimpleLight<YellowLight>>>(
                mm2px(Vec(x, kReverse)), module, PaulstretchHeads::REVERSE_PARAM + h, PaulstretchHeads::REVERSE_LIGHT + h));
            addInput(createInputCentered<PJ301MPort>(mm2px(Vec(x, jStretch)), module, PaulstretchHeads::STRETCH_INPUT + h));
            addInput(createInputCentered<PJ301MPort>(mm2px(Vec(x, jPitch)), module, PaulstretchHeads::PITCH_INPUT + h));
            addInput(createInputCentered<PJ301MPort>(mm2px(Vec(x, jScan)), module, PaulstretchHeads::SCAN_INPUT + h));
            addInput(createInputCentered<PJ301MPort>(mm2px(Vec(x, jFreeze)), module, PaulstretchHeads::FREEZE_INPUT + h));
            addInput(createInputCentered<PJ301MPort>(mm2px(Vec(x, jReverse)), module, PaulstretchHeads::REVERSE_INPUT + h));
            addOutput(createOutputCentered<PJ301MPort>(mm2px(Vec(x, jOutL)), module, PaulstretchHeads::OUT_L_OUTPUT + h));
            addOutput(createOutputCentered<PJ301MPort>(mm2px(Vec(x, jOutR)), module, PaulstretchHeads::OUT_R_OUTPUT + h));
        }

        addChild(createLightCentered<SmallLight<GreenLight>>(mm2px(Vec(shared, 17.f)), module, PaulstretchHeads::LINK_LIGHT));
        addText(shared, 21.5f, "LINK", 7.f);
        auto* display = createWidget<HeadsDisplay>(mm2px(Vec(69.6f, 25.f)));
        display->box.size = mm2px(Vec(9.8f, 32.f));
        display->module = module;
        addChild(display);
        addText(shared, jStretch - 6.4f, "RESET", 7.f);
        addInput(createInputCentered<PJ301MPort>(mm2px(Vec(shared, jStretch)), module, PaulstretchHeads::RESET_INPUT));
    }

    PanelText* numbers[PaulstretchHeads::PER] = {};
    int shownIndex = 0;

    // Numbers the heads by the expander's place in the row: 1-4, 5-8, 9-12.
    void step() override {
        ModuleWidget::step();
        auto* m = getModule<PaulstretchHeads>();
        const int index = m ? std::max(0, m->index.load()) : 0;
        if (index == shownIndex) return;
        shownIndex = index;
        for (int h = 0; h < PaulstretchHeads::PER; h++) {
            const int head = index * PaulstretchHeads::PER + h;
            numbers[h]->text = std::to_string(head + 1);
            numbers[h]->color = paulstretch::headColor(head);
        }
    }

    // text centred on (x, y) in mm
    PanelText* addText(float x, float y, const std::string& text, float fontSize = 8.f,
                       NVGcolor color = nvgRGB(0xe8, 0xe8, 0xe8)) {
        auto* t = createWidget<PanelText>(mm2px(Vec(x, y)));
        t->text = text;
        t->fontSize = fontSize;
        t->color = color;
        addChild(t);
        return t;
    }
};

Model* modelPaulstretchHeads = createModel<PaulstretchHeads, PaulstretchHeadsWidget>("PaulstretchHeads");
