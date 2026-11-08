"""Builds the Paulstretch user manual (PDF). Usage: python3 build_manual.py OUT.pdf SCREENSHOT.png"""
import sys
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table, TableStyle,
                                Flowable, PageBreak, Image, KeepTogether, NextPageTemplate, CondPageBreak)

OUT, SHOT = sys.argv[1], sys.argv[2]
F = "/System/Library/Fonts/Supplemental/"
pdfmetrics.registerFont(TTFont("Arial", F + "Arial.ttf"))
pdfmetrics.registerFont(TTFont("Arial-Bold", F + "Arial Bold.ttf"))
pdfmetrics.registerFont(TTFont("Arial-Italic", F + "Arial Italic.ttf"))
pdfmetrics.registerFont(TTFont("Arial-BoldItalic", F + "Arial Bold Italic.ttf"))
from reportlab.pdfbase.pdfmetrics import registerFontFamily
registerFontFamily("Arial", normal="Arial", bold="Arial-Bold", italic="Arial-Italic", boldItalic="Arial-BoldItalic")

INK = colors.HexColor("#1d1f24")
SOFT = colors.HexColor("#5a5d66")
AMBER = colors.HexColor("#c8901e")
RULE = colors.HexColor("#d9d9de")
TINT = colors.HexColor("#f4f4f6")
PANEL = colors.HexColor("#2b2d33")
PANEL_LINE = colors.HexColor("#5a5d66")
PANEL_TEXT = colors.HexColor("#e8e8e8")
BOX = colors.HexColor("#d8d8dc")
HEAD = [colors.HexColor(c) for c in ("#40c8e0", "#b080f0", "#70d070", "#f070a8")]

body = ParagraphStyle("body", fontName="Arial", fontSize=10, leading=14.2, textColor=INK, spaceAfter=6)
small = ParagraphStyle("small", parent=body, fontSize=8.5, leading=11.5, textColor=SOFT, spaceAfter=0)
cell = ParagraphStyle("cell", parent=body, fontSize=9, leading=12, spaceAfter=0)
cellb = ParagraphStyle("cellb", parent=cell, fontName="Arial-Bold")
h1 = ParagraphStyle("h1", fontName="Arial-Bold", fontSize=20, leading=24, textColor=INK, spaceBefore=0, spaceAfter=10)
h2 = ParagraphStyle("h2", fontName="Arial-Bold", fontSize=13, leading=17, textColor=INK, spaceBefore=12, spaceAfter=5)
h3 = ParagraphStyle("h3", fontName="Arial-Bold", fontSize=10.5, leading=14, textColor=INK, spaceBefore=8, spaceAfter=3)
bullet = ParagraphStyle("bullet", parent=body, leftIndent=12, bulletIndent=2, spaceAfter=3)
step = ParagraphStyle("step", parent=body, leftIndent=16, bulletIndent=2, spaceAfter=3)
caption = ParagraphStyle("caption", parent=small, alignment=TA_CENTER, spaceBefore=4)


def P(t, s=body): return Paragraph(t, s)
def B(t): return Paragraph(t, bullet, bulletText="•")
def S(n, t): return Paragraph(t, step, bulletText=f"{n}.")


class H1(Flowable):
    """Chapter heading with an amber rule."""
    def __init__(self, text, kicker=""):
        super().__init__(); self.text, self.kicker = text, kicker
    def wrap(self, aw, ah): self.w = aw; return aw, 15 * mm
    def draw(self):
        c = self.canv
        if self.kicker:
            c.setFont("Arial-Bold", 8.5); c.setFillColor(AMBER); c.drawString(0, 11.5 * mm, self.kicker.upper())
        c.setFont("Arial-Bold", 19); c.setFillColor(INK); c.drawString(0, 4.5 * mm, self.text)
        c.setStrokeColor(AMBER); c.setLineWidth(1.4); c.line(0, 1.5 * mm, 22 * mm, 1.5 * mm)


def table(rows, widths, header=True):
    data = [[Paragraph(str(x), cellb if (header and i == 0) or j == 0 else cell) for j, x in enumerate(r)]
            for i, r in enumerate(rows)]
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    st = [("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
          ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
          ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 6)]
    if header:
        st += [("BACKGROUND", (0, 0), (-1, 0), TINT), ("LINEBELOW", (0, 0), (-1, 0), 0.8, INK)]
    t.setStyle(TableStyle(st))
    return t


def note(text):
    t = Table([[Paragraph(text, cell)]], colWidths=[None])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), TINT), ("LINEBEFORE", (0, 0), (0, -1), 2, AMBER),
                           ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                           ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    return t


# ---------- panel drawings, to scale from the module's own widget positions (mm) ----------
class Panel(Flowable):
    def __init__(self, width_mm, scale, draw_fn):
        super().__init__(); self.wmm, self.k, self.fn = width_mm, scale, draw_fn
    def wrap(self, aw, ah): return self.wmm * mm * self.k, 128.5 * mm * self.k
    def draw(self):
        c, k = self.canv, self.k
        X = lambda x: x * mm * k
        Y = lambda y: (128.5 - y) * mm * k
        g = dict(c=c, X=X, Y=Y, k=k)
        c.setFillColor(PANEL); c.rect(0, 0, X(self.wmm), Y(0), stroke=0, fill=1)
        c.setFillColor(colors.HexColor("#f0b040")); c.rect(0, Y(1.2), X(self.wmm), X(1.2), stroke=0, fill=1)
        self.fn(g)


def txt(g, x, y, s, size=8, color=PANEL_TEXT, font="Arial"):
    c = g["c"]; c.setFont(font, size * g["k"] * 0.36 * 2.2); c.setFillColor(color)
    c.drawCentredString(g["X"](x), g["Y"](y) - size * g["k"] * 0.36 * 0.75, s)


def knob(g, x, y, r, angle=-150):
    import math
    c, X, Y = g["c"], g["X"], g["Y"]
    c.setFillColor(colors.HexColor("#111215")); c.setStrokeColor(colors.HexColor("#3a3c42")); c.setLineWidth(0.6)
    c.circle(X(x), Y(y), X(r), stroke=1, fill=1)
    c.setStrokeColor(colors.white); c.setLineWidth(max(0.8, X(0.45)))
    a = math.radians(90 - angle)
    c.line(X(x), Y(y), X(x) + X(r * 0.85) * math.cos(a), Y(y) + X(r * 0.85) * math.sin(a))


def trim(g, x, y): knob(g, x, y, 2.9)


def button(g, x, y, light=None):
    c, X, Y = g["c"], g["X"], g["Y"]
    c.setFillColor(colors.HexColor("#1a1b1f")); c.setStrokeColor(colors.HexColor("#4a4c52")); c.setLineWidth(0.6)
    c.circle(X(x), Y(y), X(3.0), stroke=1, fill=1)
    c.setFillColor(light or colors.HexColor("#2c2d32")); c.circle(X(x), Y(y), X(1.7), stroke=0, fill=1)


def jack(g, x, y):
    c, X, Y = g["c"], g["X"], g["Y"]
    c.setFillColor(colors.HexColor("#c9cacf")); c.setStrokeColor(colors.HexColor("#8d8f96")); c.setLineWidth(0.5)
    c.circle(X(x), Y(y), X(3.9), stroke=1, fill=1)
    c.setFillColor(colors.HexColor("#efeff2")); c.circle(X(x), Y(y), X(2.9), stroke=0, fill=1)
    c.setFillColor(colors.black); c.circle(X(x), Y(y), X(1.8), stroke=0, fill=1)


def screws(g, wmm):
    c, X, Y = g["c"], g["X"], g["Y"]
    for sx in (7.5, wmm - 7.5):
        for sy in (2.5, 126):
            c.setFillColor(colors.HexColor("#b8b9be")); c.circle(X(sx), Y(sy), X(1.9), stroke=0, fill=1)


def main_panel(g):
    import math
    c, X, Y = g["c"], g["X"], g["Y"]
    screws(g, 50.8)
    txt(g, 25.4, 9, "PAULSTRETCH", 12)
    knob(g, 13, 26, 8.6, angle=-40); txt(g, 13, 39.5, "STRETCH")
    knob(g, 37, 26, 6.6, angle=0); txt(g, 37, 39.5, "WINDOW")
    labels = ["1k", "2k", "4k", "8k", "16k", "32k", "64k"]
    for i, s in enumerate(labels):
        a = math.radians(-135 + i * 45)
        lx, ly = 37 + 10.6 * math.sin(a), 26 - 10.6 * math.cos(a)
        txt(g, lx, ly, s, 6.5, colors.HexColor("#f0b040") if i == 4 else colors.HexColor("#9a9ca3"))
    knob(g, 7.6, 48, 4.0, -120); txt(g, 7.6, 54.2, "START")
    knob(g, 19.2, 48, 4.0, 0); txt(g, 19.2, 54.2, "PITCH")
    button(g, 31.2, 48); txt(g, 31.2, 54.2, "REC")
    button(g, 43.2, 48); txt(g, 43.2, 54.2, "FREEZE")
    # display
    c.setFillColor(colors.HexColor("#101014")); c.roundRect(X(4), Y(58.5 + 8.5), X(42.8), X(8.5), X(0.7), stroke=0, fill=1)
    top, bh, span = 58.5 + 0.3, 7.9, 3.5
    c.setFillColor(colors.Color(0.94, 0.69, 0.25, 0.3)); c.rect(X(4 + 22), Y(top + bh), X(span), X(bh), stroke=0, fill=1)
    cx = 4 + 22 + span / 2
    c.setFillColor(colors.HexColor("#f0b040")); c.rect(X(cx - 0.17), Y(top + bh), X(0.35), X(bh), stroke=0, fill=1)
    p = c.beginPath(); p.moveTo(X(cx + 0.35), Y(top + 0.4)); p.lineTo(X(cx + 1.4), Y(top + 1.1)); p.lineTo(X(cx + 0.35), Y(top + 1.8)); p.close()
    c.drawPath(p, stroke=0, fill=1)
    c.setFont("Courier", X(3.0)); c.setFillColor(PANEL_TEXT)
    c.drawString(X(5), Y(63.8), "my_sample"); c.drawRightString(X(45.6), Y(63.8), "12.4 s")
    c.setFillColor(PANEL_LINE); c.rect(X(3), Y(70.8), X(44.8), X(0.3), stroke=0, fill=1)
    xs = [7.6, 19.2, 31.2, 43.2]
    for x, n in zip(xs, ["STRETCH", "SCAN", "RESET", "FREEZE"]): jack(g, x, 81); txt(g, x, 74.6, n, 7)
    for x, n in zip(xs, ["REC", "V/OCT", "IN L", "IN R"]): jack(g, x, 97); txt(g, x, 90.6, n, 7)
    c.setFillColor(BOX); c.roundRect(X(25.4), Y(103.4 + 16.2), X(23.6), X(16.2), X(1.5), stroke=0, fill=1)
    jack(g, 7.6, 113); txt(g, 7.6, 106.6, "REV", 7)
    button(g, 19.2, 113); txt(g, 19.2, 106.6, "REVERSE", 7)
    for x, n in zip(xs[2:], ["OUT L", "OUT R"]): jack(g, x, 113); txt(g, x, 106.6, n, 7, colors.HexColor("#202024"))
    txt(g, 25.4, 124.8, "v2.1.0 (build date)", 6, colors.HexColor("#8a8c93"))


def heads_panel(g):
    c, X, Y = g["c"], g["X"], g["Y"]
    screws(g, 81.28)
    txt(g, 40.64, 9, "PAULSTRETCH HEADS", 11)
    c.setFillColor(PANEL_LINE)
    c.rect(X(3), Y(61.9), X(75.28), X(0.3), stroke=0, fill=1)
    c.rect(X(68.3), Y(73), X(0.3), X(62), stroke=0, fill=1)
    c.setFillColor(BOX); c.roundRect(X(14.5), Y(107.2 + 18.4), X(53.5), X(18.4), X(1.5), stroke=0, fill=1)
    col = [21, 34.5, 48, 61.5]; shared = 74.5; names = 7
    rows = [(25, "STRETCH"), (34, "PITCH"), (42, "START"), (49.5, "FREEZE"), (56.5, "REVERSE"),
            (67, "STR CV"), (76, "V/OCT"), (85, "SCAN"), (94, "FRZ GATE"), (103, "REV GATE"), (112, "OUT L"), (121, "OUT R")]
    for y, n in rows: txt(g, names, y, n, 7)
    for h, x in enumerate(col):
        txt(g, x, 17, str(h + 1), 10, HEAD[h], "Arial-Bold")
        knob(g, x, 25, 3.85, -60 + h * 25); knob(g, x, 34, 3.85, 0)
        trim(g, x, 42)
        button(g, x, 49.5); button(g, x, 56.5)
        for y in (67, 76, 85, 94, 103, 112, 121): jack(g, x, y)
    c.setFillColor(colors.HexColor("#3ad06a")); c.circle(X(shared), Y(17), X(1.1), stroke=0, fill=1)
    txt(g, shared, 21.5, "LINK", 7)
    c.setFillColor(colors.HexColor("#101014")); c.roundRect(X(69.6), Y(25 + 32), X(9.8), X(32), X(0.7), stroke=0, fill=1)
    lw = 9.6 / 4
    for i, (fy, still, rev) in enumerate(((0.12, False, False), (0.40, False, True), (0.40, True, False), (0.72, False, False))):
        hc = HEAD[i]; x0 = 69.7 + i * lw + 0.15; cw = lw - 0.3
        c.setFillColor(colors.Color(hc.red, hc.green, hc.blue, 0.3)); c.rect(X(x0), Y(25.1 + fy * 31.8 + 5.9), X(cw), X(5.9), stroke=0, fill=1)
        cy = 25.1 + fy * 31.8 + 2.95
        c.setFillColor(hc); c.rect(X(x0), Y(cy + 0.17), X(cw), X(0.35), stroke=0, fill=1)
        if not still:
            d = -1 if rev else 1; mx = x0 + cw / 2
            p = c.beginPath(); p.moveTo(X(mx - cw * 0.35), Y(cy + d * 0.35)); p.lineTo(X(mx + cw * 0.35), Y(cy + d * 0.35)); p.lineTo(X(mx), Y(cy + d * (0.35 + cw * 0.5))); p.close()
            c.drawPath(p, stroke=0, fill=1)
    txt(g, shared, 60.6, "RESET", 7); jack(g, shared, 67)


# ---------- page furniture ----------
def on_page(c, doc):
    if doc.page == 1: return
    c.saveState()
    c.setFont("Arial", 8); c.setFillColor(SOFT)
    c.drawString(20 * mm, 12 * mm, "Paulstretch and Paulstretch Heads · User manual")
    c.drawRightString(A4[0] - 20 * mm, 12 * mm, str(doc.page))
    c.setStrokeColor(RULE); c.setLineWidth(0.5); c.line(20 * mm, 16 * mm, A4[0] - 20 * mm, 16 * mm)
    c.restoreState()


def on_cover(c, doc):
    c.saveState()
    c.setFillColor(PANEL); c.rect(0, A4[1] - 118 * mm, A4[0], 118 * mm, stroke=0, fill=1)
    c.setFillColor(colors.HexColor("#f0b040")); c.rect(0, A4[1] - 4 * mm, A4[0], 4 * mm, stroke=0, fill=1)
    c.setFillColor(colors.HexColor("#f0b040")); c.setFont("Arial-Bold", 10)
    c.drawString(20 * mm, A4[1] - 30 * mm, "VCV RACK MODULES · USER MANUAL")
    c.setFillColor(colors.white); c.setFont("Arial-Bold", 34)
    c.drawString(20 * mm, A4[1] - 50 * mm, "Paulstretch")
    c.setFont("Arial", 20); c.setFillColor(colors.HexColor("#d0d1d6"))
    c.drawString(20 * mm, A4[1] - 62 * mm, "and Paulstretch Heads")
    c.setFont("Arial", 11); c.setFillColor(colors.HexColor("#b0b2b8"))
    c.drawString(20 * mm, A4[1] - 78 * mm, "Extreme time-stretching of recordings and audio files,")
    c.drawString(20 * mm, A4[1] - 84 * mm, "with up to twelve more stretch voices on expanders.")
    c.setFont("Arial", 9); c.setFillColor(colors.HexColor("#8a8c93"))
    c.drawString(20 * mm, A4[1] - 104 * mm, "Plugin version 2.1.0 · Manual dated 7 November 2026")
    c.restoreState()


doc = BaseDocTemplate(OUT, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=20 * mm, bottomMargin=22 * mm,
                      title="Paulstretch and Paulstretch Heads: User manual", author="VCV Rack Modules",
                      subject="User manual for the Paulstretch VCV Rack module and its expander")
full = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="full")
cover_frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, A4[1] - 128 * mm - doc.bottomMargin, id="cover")
doc.addPageTemplates([PageTemplate("cover", [cover_frame], onPage=on_cover),
                      PageTemplate("normal", [full], onPage=on_page)])

W = doc.width
s = []

# ---------- cover ----------
s.append(NextPageTemplate("normal"))
shot = Image(SHOT, width=48 * mm, height=48 * mm * 1652 / 676)
cover_text = [
    P("<b>What these modules do</b>", h3),
    P("Paulstretch turns any sound into a slowly evolving texture. It plays a recording back many times "
      "slower, from 1 to 8192 times its length, without lowering its pitch and without the stutter of "
      "ordinary time-stretching. A two-second chord becomes a minute-long swell; a voice becomes a choir-like pad."),
    P("Record straight from your patch or load a WAV or AIFF file. Play it forwards or backwards, freeze it, "
      "shift its pitch, and scan through it by hand or from CV. Add the <b>Paulstretch Heads</b> expander for "
      "four more independent voices reading the same audio, and chain up to three of them for twelve."),
    P("<b>In this manual</b>", h3),
    P("1 · Quick start<br/>2 · The Paulstretch module<br/>3 · Getting audio in<br/>4 · Playing it back<br/>"
      "5 · The display<br/>6 · Paulstretch Heads expander<br/>7 · Patch ideas<br/>8 · Specifications<br/>"
      "9 · Credits and licence", body),
]
ct = Table([[shot, cover_text]], colWidths=[56 * mm, W - 56 * mm])
ct.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (0, 0), 8 * mm)]))
s.append(ct)
s.append(P("The Paulstretch module in a patch, with a file loaded.", ParagraphStyle("lc", parent=small, spaceBefore=3)))
s.append(PageBreak())

# ---------- 1 quick start ----------
s.append(H1("Quick start", "Chapter 1"))
s.append(P("Five minutes from an empty patch to a stretched sound."))
s.append(S(1, "Add <b>Paulstretch</b> to your patch. Patch <b>OUT L</b> and <b>OUT R</b> to an audio interface, "
              "mixer or reverb. For mono, patch only OUT L: it then carries both channels."))
s.append(S(2, "Get some audio into the module, either way:"))
s.append(Paragraph("<b>Load a file:</b> right-click the module and choose <b>Load audio file…</b>, or drag a WAV or "
                   "AIFF file onto it from your desktop.", ParagraphStyle("s2", parent=bullet, leftIndent=28, bulletIndent=18), bulletText="–"))
s.append(Paragraph("<b>Record:</b> patch a source into <b>IN L</b> (and <b>IN R</b> for stereo), press <b>REC</b>, "
                   "let it run for a few seconds, then press REC again.", ParagraphStyle("s3", parent=bullet, leftIndent=28, bulletIndent=18), bulletText="–"))
s.append(S(3, "You hear the audio slowed down eight times, the default. Turn <b>STRETCH</b> up for slower, "
              "smoother textures."))
s.append(S(4, "Try <b>WINDOW</b>: smaller windows keep more of the original's detail and grain; larger windows "
              "sound smoother and more blurred."))
s.append(S(5, "Press <b>FREEZE</b> to hold the sound where it is, and <b>REVERSE</b> to play backwards."))
s.append(Spacer(1, 4))
s.append(note("<b>Saving.</b> Recordings are saved with the patch. A loaded file is saved as a link to "
              "where it is on disk, unless you right-click and turn on <b>Store a copy of the file in the patch</b>. "
              "See chapter 3."))

# ---------- 2 the module ----------
s.append(PageBreak())
s.append(H1("The Paulstretch module", "Chapter 2"))
s.append(P("A 10 HP module. Controls sit in the top half, jacks in the bottom half; the light box holds the outputs."))
pan = Panel(50.8, 1.0, main_panel)
side = [
    P("<b>Top row</b>", h3),
    P("<b>STRETCH</b> sets how much slower the sound plays. <b>WINDOW</b> sets the size of each analysed slice "
      "of audio, from 1k to 64k samples; the selected size is lit amber on the scale.", cell),
    P("<b>Second row</b>", h3),
    P("<b>START</b> sets where playback (re)starts. <b>PITCH</b> shifts the pitch in semitones. "
      "<b>REC</b> and <b>FREEZE</b> are latching buttons with lights.", cell),
    P("<b>Display</b>", h3),
    P("Shows the buffer: where the voice is reading, the window, the expander's heads, the file name and the "
      "buffer length. See chapter 5.", cell),
    P("<b>Jacks</b>", h3),
    P("Control inputs in the first row, record, pitch and audio inputs in the second, and reverse and the audio "
      "outputs in the third. The <b>REVERSE</b> button sits beside its gate jack.", cell),
]
pt = Table([[pan, side]], colWidths=[50.8 * mm + 8 * mm, W - 58.8 * mm])
pt.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
s.append(pt)
s.append(P("Panel drawn to scale. The display shows an example: the amber block is the window, the line its centre, "
           "the arrow the direction.", ParagraphStyle("pc", parent=small, spaceBefore=4)))

s.append(PageBreak())
s.append(P("Controls", h2))
s.append(table([
    ["Control", "Range and default", "What it does"],
    ["STRETCH", "1× to 8192×; default 8×", "How many times slower than the original the sound plays. The knob is logarithmic: 8×, 64× and 512× are evenly spaced along it. Added to the STRETCH input."],
    ["WINDOW", "1k, 2k, 4k, 8k, 16k, 32k, 64k samples; default 16k", "The length of each slice the module analyses. Clicks between the seven sizes. See “Choosing a window” in chapter 4."],
    ["START", "0 to 100% of the buffer; default 0%", "Where playback starts after RESET, a new recording, a file load or clearing the buffer. Also the starting point for SCAN."],
    ["PITCH", "−24 to +24 semitones; default 0", "Shifts the pitch without changing the speed. Clicks in semitones. Added to the V/OCT input."],
    ["REC", "On / off", "Records into the buffer while on. Turns itself off when the buffer is full (60 seconds)."],
    ["FREEZE", "On / off", "Holds the playback position. The sound keeps going, as a sustained texture of that moment."],
    ["REVERSE", "On / off", "Plays the buffer backwards."],
], [24 * mm, 46 * mm, W - 70 * mm]))
s.append(P("Inputs and outputs", h2))
s.append(table([
    ["Jack", "Signal", "What it does"],
    ["STRETCH", "CV, ±V", "Added to the STRETCH knob: +1 V doubles the stretch, −1 V halves it. The total stays within 1× to 8192×."],
    ["SCAN", "CV, 0 to 10 V", "Sets the playback position directly: 0 V is the START position, 10 V a full trip round the buffer. While patched, the position follows SCAN only."],
    ["RESET", "Trigger", "Jumps the main voice back to START. To reset the expanders' heads with it, right-click and turn on <b>RESET also resets all heads</b>."],
    ["FREEZE", "Gate", "Freezes while high, as well as the button."],
    ["REC", "Gate", "Records while high, as well as the button."],
    ["V/OCT", "Pitch CV, 1 V/octave", "Added to the PITCH knob: +1 V is an octave up. The total is limited to ±4 octaves."],
    ["IN L", "Audio, ±5 V", "Left or mono input for recording."],
    ["IN R", "Audio, ±5 V", "Right input for recording. Unpatched, the recording is mono, taken from IN L."],
    ["REV", "Gate", "Flips the direction while high: forwards becomes backwards, and backwards (REVERSE on) becomes forwards."],
    ["OUT L", "Audio, ±5 V", "Left output. When OUT R is unpatched, carries a mono mix of both channels."],
    ["OUT R", "Audio, ±5 V", "Right output. With a mono buffer, the same as OUT L."],
], [22 * mm, 34 * mm, W - 56 * mm]))
s.append(Spacer(1, 4))
s.append(P("Gates and triggers switch at about 1 V. When the module is bypassed in Rack, IN L and IN R pass "
           "straight to OUT L and OUT R.", small))
s.append(P("Levels", h3))
s.append(P("Inputs and outputs use Rack's audio level: ±5 V is full scale. Outputs are limited to ±10 V. "
           "A stretched sound has about the same overall level as the original."))

# ---------- 3 getting audio in ----------
s.append(PageBreak())
s.append(H1("Getting audio in", "Chapter 3"))
s.append(P("The module plays from one buffer of audio. Fill it by recording or by loading a file; each replaces "
           "whatever the buffer held before."))
s.append(P("Recording", h2))
s.append(B("Press <b>REC</b>, or send a gate to the REC input, to start. A new recording replaces the buffer."))
s.append(B("The recording is stereo if <b>IN R</b> is patched when it starts, mono otherwise."))
s.append(B("Press REC again, or let the gate go low, to stop. Recording also stops by itself after 60 seconds: "
           "the button turns off, and a held gate must go low before the next recording."))
s.append(B("While recording, the module already plays what it has so far. The display fills red as the 60 "
           "seconds are used."))
s.append(B("Recordings are saved inside the patch, so they come back when you reopen it."))
s.append(P("Loading a file", h2))
s.append(B("Right-click the module and choose <b>Load audio file…</b>, or drag a file onto the module."))
s.append(B("The file loads in the background while the module keeps playing; the display shows LOADING. "
           "If it fails, the display shows LOAD FAILED for four seconds and the right-click menu says why."))
s.append(B("Files up to 10 minutes long load whole. Longer files load their first 10 minutes, and the right-click "
           "menu says so."))
s.append(B("Files at any sample rate play at the right pitch: they are converted to Rack's rate on loading."))
s.append(B("The right-click menu shows which file is loaded."))
s.append(P("Saving a loaded file with the patch", h3))
s.append(P("By default the patch saves only the file's location, so the file must still be there when you reopen "
           "the patch. To make a patch that works on its own, right-click and turn on "
           "<b>Store a copy of the file in the patch</b>."))
s.append(B("The next time the patch is saved, a copy of the audio goes into the patch. The menu then says "
           "<b>Stored in the patch</b>; before that, <b>Stored when the patch is next saved</b>."))
s.append(B("The copy holds exactly what the module uses, as a WAV file at the original's sample rate and sample "
           "size: no more than the first 10 minutes, and no more than two channels. The samples are identical to "
           "the original's."))
s.append(B("Reopening the patch plays the stored copy, even if the original has since been moved, changed or deleted."))
s.append(B("The patch file grows by the size of that audio. A minute of 16-bit stereo audio at 48 kHz adds "
           "about 11 MB; the most it can add is 10 minutes' worth."))
s.append(B("Loading a different file replaces the copy at the next save. Recording, clearing the buffer or "
           "turning the option off removes it."))
s.append(B("If the original file has gone missing, the menu warns you to keep the option on: turning it off would "
           "leave the patch with no audio."))
s.append(KeepTogether([P("Supported files", h3), table([
    ["Format", "Supported"],
    ["WAV", "16-, 24- and 32-bit and 8-bit integer; 32- and 64-bit float; the WAVE_FORMAT_EXTENSIBLE variant."],
    ["AIFF and AIFF-C", "8- to 32-bit integer, big- or little-endian (sowt); 32- and 64-bit float."],
    ["Channels", "Mono or stereo. Files with more channels load their first two."],
    ["Not supported", "Compressed audio (MP3, AAC, FLAC, compressed AIFF-C, ADPCM WAV) and RF64 WAV files (used for recordings over 4 GB)."],
], [32 * mm, W - 32 * mm])]))
s.append(P("Clearing the buffer", h2))
s.append(P("Right-click and choose <b>Clear buffer</b>. The display shows EMPTY and the module goes silent."))
s.append(P("Changing Rack's sample rate", h2))
s.append(P("The buffer is converted to the new rate, so it keeps its pitch and length."))

# ---------- 4 playing it back ----------
s.append(PageBreak())
s.append(H1("Playing it back", "Chapter 4"))
s.append(P("How the stretch works", h2))
s.append(P("The module reads a short slice of the buffer, the <b>window</b>, and breaks it into its frequencies. "
           "It keeps how loud each frequency is but scrambles their timing, then turns the result back into "
           "sound. Overlapping these slices gives a smooth, continuous texture. Moving through the buffer slowly "
           "between slices is what stretches the sound; the pitch stays the same because each slice keeps its frequencies."))
s.append(P("Because the timing within each slice is scrambled, sharp attacks soften and rhythm dissolves. "
           "That is the character of Paulstretch, and it grows with the window size and the stretch."))
s.append(P("Choosing a window", h2))
s.append(table([
    ["WINDOW", "Length at 48 kHz", "Character"],
    ["1k, 2k", "21 ms, 43 ms", "Most detail, rough and grainy; some of the original's movement survives."],
    ["4k, 8k", "85 ms, 171 ms", "A balance: recognisable, but already smooth."],
    ["16k (default)", "341 ms", "The classic Paulstretch sound for most material."],
    ["32k, 64k", "683 ms, 1.4 s", "Smoothest and most blurred; best for extreme stretches and drones."],
], [28 * mm, 34 * mm, W - 62 * mm]))
s.append(Spacer(1, 4))
s.append(P("The module updates once per half window. Changes to STRETCH, PITCH and the position take effect at the "
           "next update, so with large windows they glide in rather than jump.", small))
s.append(P("Position: START, RESET and SCAN", h2))
s.append(B("Playback moves through the buffer and loops round at the end."))
s.append(B("<b>START</b> is where it restarts: on a RESET trigger, a new recording, a file load or clearing the buffer. "
           "Turning START alone does not move the playback."))
s.append(B("<b>SCAN</b> takes over the position completely while patched. 0 V is the START position; each 10 V is "
           "one trip round the buffer. A slow rising ramp plays it forwards; a sample-and-hold jumps around it. "
           "While SCAN is patched, STRETCH, FREEZE and REVERSE do not move the position."))
s.append(P("FREEZE", h2))
s.append(P("FREEZE stops the position. The output does not stop or loop: each new slice is the same moment with fresh "
           "random timing, so a frozen sound is a steady, living drone of that instant. The button and the gate "
           "work together: either one freezes."))
s.append(P("REVERSE", h2))
s.append(P("REVERSE plays through the buffer backwards. Within a slice there is no forwards or backwards, so what "
           "changes is the shape over time: notes swell in instead of dying away. The REV gate flips the direction "
           "while high, whichever way the button is set, so you can switch direction in rhythm."))
s.append(P("PITCH", h2))
s.append(P("PITCH moves every frequency up or down by the same musical interval, without changing the speed. "
           "The knob clicks in semitones over ±2 octaves; V/OCT adds to it at 1 V per octave, up to ±4 octaves "
           "in total. Shifting up drops whatever goes above the top of the audio range, so very bright material "
           "loses its highest frequencies and some level. Otherwise the level stays the same."))

# ---------- 5 display ----------
s.append(PageBreak())
s.append(H1("The display", "Chapter 5"))
s.append(P("The display is a map of the whole buffer, from its start on the left to its end on the right."))
s.append(table([
    ["What you see", "Meaning"],
    ["Amber block", "The main voice's window: the slice of audio it is reading now. Its width is the WINDOW size "
                    "compared with the buffer's length. Near the end it wraps round to the left edge."],
    ["Amber line", "The centre of the main voice's window: the part of the audio you hear most. It is the playback "
                   "position."],
    ["Small arrow", "At the top of the amber line: the direction the voice is moving, right when playing forwards, "
                    "left in reverse. Hidden while frozen or while SCAN is patched."],
    ["Name, left", "The loaded file's name, shortened with ~ if long. Not shown for recordings."],
    ["Time, right", "The buffer's length."],
    ["Red fill and REC", "Recording: the fill shows how much of the 60 seconds has been used."],
    ["EMPTY", "Nothing in the buffer."],
    ["LOADING", "A file is loading in the background."],
    ["LOAD FAILED", "A file couldn't be loaded. The right-click menu says why."],
], [38 * mm, W - 38 * mm]))
s.append(Spacer(1, 6))
s.append(note("<b>The expander's heads</b> are shown on each expander's own display, not here: see chapter 6."))

# ---------- 6 expander ----------
s.append(PageBreak())
s.append(H1("Paulstretch Heads expander", "Chapter 6"))
s.append(P("A 16 HP expander that adds four more voices, called heads, to a Paulstretch module. Up to three "
           "can sit in a row, for twelve heads in all. Every head reads the same buffer as the main module, each with its own stretch, pitch, start, direction and outputs. Use it "
           "for chords, for layers moving at different speeds, or for one sound playing forwards against itself backwards."))
pan2 = Panel(81.28, 0.82, heads_panel)
side2 = [
    P("<b>Connecting</b>", h3),
    P("Place the expander <b>directly to the right</b> of a Paulstretch module, touching it. The green "
      "<b>LINK</b> light comes on. Moved away, it goes silent until linked again.", cell),
    P("For more heads, place a second and a third expander to the right of the first, all touching. Their heads "
      "are numbered 5 to 8 and 9 to 12, with the same four column colours. A fourth stays unlinked and silent.", cell),
    P("<b>Layout</b>", h3),
    P("One column per head, numbered in the head's colour. Row names run down the left. Knobs and "
      "buttons are in the top half; CV inputs and the outputs in the bottom half.", cell),
    P("The right-hand column holds the LINK light, the expander's display and the RESET input.", cell),
    P("<b>Display</b>", h3),
    P("Shows this expander's heads on the buffer, which runs from top to bottom: one column per head, in its colour. "
      "Each head's window is a dim block and its centre a bright line, with an arrow pointing down when playing "
      "forwards and up in reverse. The arrow is hidden while the head is frozen or SCAN is patched. Only heads "
      "with an output patched are shown.", cell),
    P("<b>Shared with the main module</b>", h3),
    P("The buffer and the WINDOW size. Recording, loading or clearing on the main module restarts every head "
      "at its START position.", cell),
]
pt2 = Table([[pan2, side2]], colWidths=[81.28 * 0.82 * mm + 7 * mm, W - 81.28 * 0.82 * mm - 7 * mm])
pt2.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
s.append(pt2)
s.append(P("Panel drawn to scale (82%).", ParagraphStyle("pc2", parent=small, spaceBefore=4)))

s.append(PageBreak())
s.append(P("Per-head controls", h2))
s.append(table([
    ["Control", "Range and default", "What it does"],
    ["STRETCH", "1× to 8192×; defaults 8×, 16×, 32×, 64× for heads 1 to 4", "The head's stretch, as on the main module. The defaults are an octave of speed apart, so the heads differ from the start."],
    ["PITCH", "−24 to +24 semitones; default 0", "The head's pitch shift, in semitones."],
    ["START", "0 to 100%; default 0%", "Where the head starts: on the expander's RESET input, and when the main module records, loads or clears."],
    ["FREEZE", "On / off", "Holds the head's position, as on the main module."],
    ["REVERSE", "On / off", "Plays the head backwards."],
    ["STR CV", "CV, ±V", "Added to the head's STRETCH: +1 V doubles it."],
    ["V/OCT", "Pitch CV, 1 V/octave", "Added to the head's PITCH. The total is limited to ±4 octaves."],
    ["SCAN", "CV, 0 to 10 V", "Sets the head's position directly, as SCAN does on the main module: 0 V is the head's START position, 10 V a full trip round the buffer. While patched, the head's position follows SCAN only, and its arrow on the display is hidden."],
    ["FRZ GATE", "Gate", "Freezes the head while high, as well as the button."],
    ["REV GATE", "Gate", "Flips the head's direction while high."],
    ["OUT L, OUT R", "Audio, ±5 V", "The head's own outputs. OUT L carries a mono mix when OUT R is unpatched."],
], [24 * mm, 46 * mm, W - 70 * mm]))
s.append(P("Shared controls", h2))
s.append(table([
    ["Control", "Signal", "What it does"],
    ["LINK", "Light", "On when the expander is linked: touching a Paulstretch on its left, or touching a linked expander, up to three in a row."],
    ["RESET", "Trigger", "Sends this expander's heads back to their START positions. Other expanders' heads, and the main module's own RESET input, are separate."],
], [24 * mm, 22 * mm, W - 46 * mm]))
s.append(P("Good to know", h2))
s.append(B("<b>Only heads in use cost CPU.</b> A head runs when its OUT L or OUT R is patched. Others are switched "
           "off and leave no marker on the display."))
s.append(B("To combine heads, patch their outputs into a mixer. Earlier versions had LEVEL knobs and MIX outputs; "
           "patches made with them keep all their other settings."))
s.append(B("Each head has its own random timing, so heads on the same material don't reinforce or cancel each other."))
s.append(B("The heads' audio reaches the first expander one sample after the main module computes it, and each "
           "further expander one sample later: inaudible, but worth knowing for sample-accurate patches."))
s.append(B("The voices take turns to do their heaviest work, so even thirteen voices at the 64k window don't "
           "cause a spike in CPU. One result: after a reset, the heads start up to half a window after the main voice, "
           "one after another."))
s.append(B("The heads' positions are saved with the patch, like the main voice's, so they carry on where they "
           "were when you reopen it."))
s.append(B("In all, a Paulstretch plays up to thirteen independent voices: the main one and up to twelve heads. "
           "The main module's own voice and controls are unaffected by the expander."))

# ---------- 7 patch ideas ----------
s.append(PageBreak())
s.append(H1("Patch ideas", "Chapter 7"))
ideas = [
    ("An endless pad from any sound", "Load a short recording: a sung note, a chord, a door creak. Set STRETCH to 64× or "
     "more and WINDOW to 16k or 32k, and send the outputs into a reverb. Turn START to choose which part of the sound you hear."),
    ("A chord from one note", "Add the expander and patch the four heads' outputs into a mixer. Set head PITCH to 0, +7, +12 and −12 and their "
     "STRETCH knobs to similar values. A single sustained note becomes a slowly breathing chord."),
    ("Forwards against backwards", "Give heads 1 and 2 the same STRETCH, turn on REVERSE for head 2, and pan their outputs "
     "left and right. The same material swells in on one side as it fades on the other."),
    ("Playable drone", "FREEZE a head on a spot you like, then sequence its V/OCT. Every note is a frozen moment of the "
     "original, transposed."),
    ("Performance scanning", "Patch a slow LFO or a hand-played CV into SCAN to move through the sound yourself. Use a "
     "sample-and-hold on a clock for stepped jumps between moments."),
    ("Four hands on one sound", "Patch a different slow LFO or random source into each head's SCAN. Each head wanders "
     "through its own part of the sound, while the main voice plays through it normally."),
    ("Live capture", "Patch a clock divider into REC to capture a new few seconds of your patch every few bars, and "
     "play the last capture stretched underneath."),
    ("Rhythmic direction changes", "Patch a clock or gate sequencer into REV. With large windows the direction changes "
     "become slow shifts in the texture's shape, not clicks."),
]
for t, d in ideas:
    s.append(KeepTogether([P(t, h3), P(d)]))

# ---------- 8 specifications ----------
s.append(PageBreak())
s.append(H1("Specifications", "Chapter 8"))
s.append(table([
    ["Item", "Paulstretch", "Paulstretch Heads"],
    ["Width", "10 HP", "16 HP"],
    ["Voices", "1", "4 per expander, up to 3 expanders (computed in the Paulstretch module)"],
    ["Buffer", "Recording: up to 60 s, mono or stereo. File: up to 10 min.", "Shares the Paulstretch buffer"],
    ["Stretch", "1× to 8192×", "1× to 8192× per head"],
    ["Window", "1024 to 65536 samples, 7 sizes", "Uses the Paulstretch WINDOW"],
    ["Pitch", "±24 semitones knob; ±48 with V/OCT", "Same, per head"],
    ["Audio level", "±5 V full scale; outputs limited to ±10 V", "Same"],
    ["Gate threshold", "About 1 V", "About 1 V"],
    ["CPU (Apple silicon)", "About 0.3% per voice at typical window sizes", "About 0.3% per active head"],
    ["Platform", "VCV Rack 2", "VCV Rack 2"],
], [36 * mm, 66 * mm, W - 102 * mm]))
s.append(Spacer(1, 6))
s.append(P("The two modules are part of the Fik Audio plugin. The version and build time printed at the bottom of the Paulstretch panel are there during "
           "development and will be removed.", small))

# ---------- 9 credits ----------
s.append(P("Credits and licence", h2))
s.append(P("Paulstretch, “Paul's Extreme Sound Stretch”, is an algorithm by Nasca Octavian Paul. These modules follow "
           "his public-domain Python version (github.com/paulnasca/paulstretch_python). The idea of pitch shifting "
           "inside the stretch comes from his paulstretch program; the code here was written independently. The "
           "modules' own additions are reverse playback, the extra heads, live recording and the file loader."))
s.append(P("The plugin is free software under the GNU General Public License, version 3 or later. A record of where "
           "each part of the code comes from, and a check against Paul's GPL program, is in PROVENANCE.md in the "
           "plugin's source."))

doc.build(s)
print("ok")
