#pragma once
#include <rack.hpp>

// Text centred on its position, drawn in the panel's colour scheme.
struct PanelText : rack::TransparentWidget {
    std::string text;
    float fontSize = 8.f;
    NVGcolor color = nvgRGB(0xe8, 0xe8, 0xe8);

    void draw(const DrawArgs& args) override {
        std::shared_ptr<rack::window::Font> font = APP->window->uiFont;
        if (!font) return;
        nvgFontFaceId(args.vg, font->handle);
        nvgFontSize(args.vg, fontSize);
        nvgTextAlign(args.vg, NVG_ALIGN_CENTER | NVG_ALIGN_MIDDLE);
        nvgFillColor(args.vg, color);
        nvgText(args.vg, 0, 0, text.c_str(), nullptr);
    }
};
