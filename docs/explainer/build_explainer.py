"""Builds "How Paulstretch works" (PDF). Usage: python3 build_explainer.py OUT.pdf FIGDIR"""
import os
import sys

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, Image, KeepTogether, NextPageTemplate, PageBreak,
                                PageTemplate, Paragraph, Spacer, Table, TableStyle)

OUT, FIG = sys.argv[1], sys.argv[2]
F = "/System/Library/Fonts/Supplemental/"
pdfmetrics.registerFont(TTFont("Arial", F + "Arial.ttf"))
pdfmetrics.registerFont(TTFont("Arial-Bold", F + "Arial Bold.ttf"))
pdfmetrics.registerFont(TTFont("Arial-Italic", F + "Arial Italic.ttf"))
pdfmetrics.registerFont(TTFont("Arial-BoldItalic", F + "Arial Bold Italic.ttf"))
registerFontFamily("Arial", normal="Arial", bold="Arial-Bold", italic="Arial-Italic", boldItalic="Arial-BoldItalic")

INK = colors.HexColor("#1d1f24")
SOFT = colors.HexColor("#5a5d66")
AMBER = colors.HexColor("#c8901e")
TINT = colors.HexColor("#f4f4f6")
RULE = colors.HexColor("#d9d9de")
PANEL = colors.HexColor("#2b2d33")

body = ParagraphStyle("body", fontName="Arial", fontSize=10.5, leading=15, textColor=INK, spaceAfter=6)
lead = ParagraphStyle("lead", parent=body, fontSize=11.5, leading=16.5)
small = ParagraphStyle("small", parent=body, fontSize=8.5, leading=11.5, textColor=SOFT)
look = ParagraphStyle("look", parent=body, fontSize=9.5, leading=13.5, spaceAfter=2)
bullet = ParagraphStyle("bullet", parent=body, leftIndent=12, bulletIndent=2, spaceAfter=3)


def P(t, s=body): return Paragraph(t, s)
def B(t): return Paragraph(t, bullet, bulletText="•")


class Heading(Flowable):
    def __init__(self, num, text):
        super().__init__(); self.num, self.text = num, text
    def wrap(self, aw, ah): return aw, 14 * mm
    def draw(self):
        c = self.canv
        if self.num:
            c.setFont("Arial-Bold", 8.5); c.setFillColor(AMBER); c.drawString(0, 10.5 * mm, self.num.upper())
        c.setFont("Arial-Bold", 16); c.setFillColor(INK); c.drawString(0, 4 * mm, self.text)
        c.setStrokeColor(AMBER); c.setLineWidth(1.4); c.line(0, 1.5 * mm, 20 * mm, 1.5 * mm)


def fig(name, width):
    """A figure, reduced to a 256-colour palette on white. That halves the PDF
    (reportlab stores a full-colour PNG as raw RGB plus a transparency mask)
    with no visible change. Near-white colours are snapped to pure white so the
    figure doesn't sit in a faint grey box."""
    src = PILImage.open(os.path.join(FIG, name + ".png")).convert("RGBA")
    w, h = src.size
    flat = PILImage.new("RGB", src.size, (255, 255, 255))
    flat.paste(src, mask=src.split()[3])
    small = flat.quantize(256, method=PILImage.Quantize.FASTOCTREE, dither=PILImage.Dither.NONE)
    pal = small.getpalette()
    for i in range(0, len(pal), 3):
        if min(pal[i:i + 3]) >= 246: pal[i:i + 3] = [255, 255, 255]
    small.putpalette(pal)
    path = os.path.join(FIG, name + "-small.png")
    small.save(path, optimize=True)
    return Image(path, width=width, height=width * h / w)


def lookfor(items):
    rows = [[Paragraph("<b>What to look for</b>", look)]] + [[Paragraph("• " + t, look)] for t in items]
    t = Table(rows, colWidths=[None])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), TINT), ("LINEBEFORE", (0, 0), (0, -1), 2, AMBER),
                           ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                           ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                           ("TOPPADDING", (0, 0), (-1, 0), 6), ("BOTTOMPADDING", (0, -1), (-1, -1), 6)]))
    return t


def on_page(c, doc):
    if doc.page == 1: return
    c.saveState()
    c.setFont("Arial", 8); c.setFillColor(SOFT)
    c.drawString(20 * mm, 12 * mm, "How Paulstretch works")
    c.drawRightString(A4[0] - 20 * mm, 12 * mm, str(doc.page))
    c.setStrokeColor(RULE); c.setLineWidth(0.5); c.line(20 * mm, 16 * mm, A4[0] - 20 * mm, 16 * mm)
    c.restoreState()


def on_cover(c, doc):
    c.saveState()
    c.setFillColor(PANEL); c.rect(0, A4[1] - 100 * mm, A4[0], 100 * mm, stroke=0, fill=1)
    c.setFillColor(colors.HexColor("#f0b040")); c.rect(0, A4[1] - 4 * mm, A4[0], 4 * mm, stroke=0, fill=1)
    c.setFont("Arial-Bold", 10); c.drawString(20 * mm, A4[1] - 28 * mm, "PAULSTRETCH · EXPLAINED WITH PICTURES")
    c.setFillColor(colors.white); c.setFont("Arial-Bold", 30); c.drawString(20 * mm, A4[1] - 48 * mm, "How Paulstretch works")
    c.setFont("Arial", 12.5); c.setFillColor(colors.HexColor("#c8cad0"))
    c.drawString(20 * mm, A4[1] - 62 * mm, "Making a sound last much longer, without changing its pitch:")
    c.drawString(20 * mm, A4[1] - 69 * mm, "what the module does, one step at a time.")
    c.setFont("Arial", 9); c.setFillColor(colors.HexColor("#8a8c93"))
    c.drawString(20 * mm, A4[1] - 82 * mm, "Paulstretch (“Paul's Extreme Sound Stretch”) was invented by Nasca Octavian Paul.")
    c.drawString(20 * mm, A4[1] - 88 * mm,"For the Paulstretch and Paulstretch Heads modules, plugin version 2.1.0 · 7 November 2026")
    c.restoreState()


doc = BaseDocTemplate(OUT, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=22 * mm,
                      title="How Paulstretch works", author="VCV Rack Modules",
                      subject="An illustrated, non-technical explanation of the Paulstretch module")
W = doc.width
doc.addPageTemplates([
    PageTemplate("cover", [Frame(doc.leftMargin, doc.bottomMargin, W, A4[1] - 112 * mm - doc.bottomMargin)], onPage=on_cover),
    PageTemplate("normal", [Frame(doc.leftMargin, doc.bottomMargin, W, doc.height)], onPage=on_page)])

s = [NextPageTemplate("normal")]

# ---------- cover page text ----------
s.append(P("Paulstretch can turn a two-second chord into a minute-long, slowly breathing cloud of sound. It does this "
           "without the sound dropping in pitch, which is what normally happens when you slow something down.", lead))
s.append(P("This guide shows how, using pictures of real sounds going through the same steps as the module. You "
           "don't need any background: each picture comes with a short explanation and a few things to look for."))
s.append(Spacer(1, 4))
s.append(P("<b>In this guide</b>"))
for t in ("Why slowing down usually changes the pitch", "Two ways to look at a sound",
          "The five steps: slice, list the pitches, give each a random phase shift, overlap, move on slowly",
          "What comes out", "Why sharp sounds become soft", "Small and large windows", "Pitch, freeze and reverse",
          "Several voices on one sound, and how they share the work"):
    s.append(B(t))
s.append(PageBreak())

# ---------- 1 ----------
s.append(Heading("1", "Why slowing down usually changes the pitch"))
s.append(P("Sound is air moving quickly back and forth. How fast it moves sets the <b>pitch</b>: the note A, for "
           "example, moves back and forth 440 times a second, written 440 Hz. A drawing of that movement over time "
           "is called a <b>waveform</b>."))
s.append(P("Play a tape at half speed and every movement takes twice as long. The sound lasts twice as long, but it "
           "also moves back and forth half as often, so it drops an octave. Paulstretch makes the sound last longer "
           "while keeping how fast it moves, so the pitch stays where it was."))
s.append(fig("01_tape", W))
s.append(P("Below, a 10-second note is stretched to 20 seconds both ways. The wide strips show the whole sound; the "
           "small ones on the right zoom in on 20 milliseconds of each, at the same moment of the note."))
s.append(lookfor(["Top: the note lasts 10 seconds.",
                  "Both stretched versions last 20 seconds. Count the waves in the zooms: about nine, then four and a "
                  "half (the tape, an octave lower), then nine again (Paulstretch, the same note).",
                  "Paulstretch fades in over its first moment, and its loudness wobbles: the random phase shifts (step 3) "
                  "does that to a single held note. It still dies away slowly, like the original.",
                  "At the very end the note's start comes round again: the module plays the sound in a loop."]))

# ---------- 2 ----------
s.append(PageBreak())
s.append(Heading("2", "Two ways to look at a sound"))
s.append(P("A waveform shows how a sound moves over time. A <b>spectrum</b> shows the same sound another way: as a "
           "list of the pitches it contains and how much of each. Think of it as the sound's list of ingredients."))
s.append(P("Below is a C major chord, three notes played together. Its waveform is a dense tangle. Its spectrum is "
           "easy to read: one peak for each note, plus smaller peaks higher up. Those smaller peaks, called "
           "harmonics, are what make a plucked string sound different from a flute playing the same note."))
s.append(fig("02_two_views", W))
s.append(lookfor(["The three tall peaks on the right are the notes C, E and G.",
                  "Peaks further right are higher pitches. The height of a peak is how much of that pitch there is."]))
s.append(Spacer(1, 6))
s.append(P("Later pictures use a <b>spectrogram</b>: a spectrum for every moment, laid side by side. Time runs "
           "left to right, pitch runs bottom to top, and darker means louder. A held note is a horizontal line."))

# ---------- 3 ----------
s.append(PageBreak())
s.append(Heading("3", "Step 1: take a short slice"))
s.append(P("Paulstretch works on short slices of the sound, one after another. The length of a slice is the "
           "<b>window</b>, the WINDOW knob on the module. Here it is about a fifth of a second."))
s.append(P("Each slice is faded in and out, following the orange curve, so its edges are silent. Without the fade, "
           "every slice would start and stop abruptly, and you would hear a click each time."))
s.append(fig("03_slice", W))
s.append(lookfor(["The shaded part is the slice. The orange curve is the fade.",
                  "In the lower picture, the slice starts and ends at zero: no sudden edges."]))

# ---------- 4 ----------
s.append(PageBreak())
s.append(Heading("4", "Steps 2 and 3: list the pitches, then shift their phases at random"))
s.append(P("Next, the module works out the slice's spectrum: which pitches are in it and how much of each. Every "
           "pitch in that list has two parts: an <b>amount</b> (how loud) and a <b>phase</b>: where its wave is in its "
           "up-and-down cycle at the start of the slice, which sets exactly when its waves rise and fall."))
s.append(P("Paulstretch keeps every amount exactly as it was, and gives every pitch a random phase shift: its wave is "
           "slid along by a random part of one cycle. Then it "
           "rebuilds the slice from that list. The waveform comes out looking completely different, but the "
           "ingredients are the same, so it sounds like the same moment: the same notes, at the same loudness."))
s.append(P("This is the heart of Paulstretch. The random phases remove everything that happens <i>within</i> the "
           "slice, such as the exact moment a note starts. What's left is pure colour, which is why the result sounds "
           "so smooth.", body))
s.append(P("Below, the slice is taken apart into its notes, one colour each, with their higher harmonics in grey. "
           "The rebuilt slice uses the same coloured waves, each with its own random phase shift."))
s.append(fig("04_scramble", 0.74 * W))
s.append(lookfor(["Each coloured wave keeps its pitch and size; only where its waves rise and fall has moved.",
                  "Added together, the two sides look nothing alike: the waves no longer line up the same way.",
                  "Bottom: the two spectra lie on top of each other. The shading shows where each coloured wave "
                  "comes from."]))
s.append(P("A simplification: the spectrum really splits a slice into about two thousand closely spaced pitches, "
           "and each gets its own random phase. The C above is a small cluster of them around 261 Hz.", small))

# ---------- 5 ----------
s.append(PageBreak())
s.append(Heading("5", "Step 4: overlap the slices"))
s.append(P("A single rebuilt slice fades in and out. To make one continuous sound, the slices overlap: each starts "
           "halfway through the one before. Where one slice fades out, the next fades in, and added together they "
           "give an even, unbroken sound."))
s.append(fig("05_overlap", W))
s.append(lookfor(["Top: rebuilt slices, drawn on two rows so you can see each one. Each starts half a slice after "
                  "the previous one.",
                  "Bottom: their sum. The fades fill each other's gaps, so the level stays even."]))

# ---------- 6 ----------
s.append(PageBreak())
s.append(Heading("6", "Step 5: move through the input slowly"))
s.append(P("Here is where the stretching happens. On the output side, a new slice starts every half window, always "
           "the same distance apart. On the input side, each slice is read from only a little further on than the "
           "one before."))
s.append(P("With STRETCH at 4×, the input moves forward a quarter of the distance the output does. So it takes the "
           "output four times as long to get through the input: one second of input becomes four seconds of output. "
           "At 8× it becomes eight seconds; at 1000×, about seventeen minutes."))
s.append(fig("06_reading", W))
s.append(lookfor(["Top row: where each slice is taken from the input. Small steps.",
                  "Bottom row: where each rebuilt slice is placed in the output. Steps four times as big.",
                  "Nothing is repeated or skipped: the input is simply walked through more slowly."]))

# ---------- 7 ----------
s.append(PageBreak())
s.append(Heading("7", "What comes out"))
s.append(P("Put the five steps together and this is the result. The input is three plucked notes, C, E and G, one "
           "after another. Stretched 4×, the output plays the same three notes, in the same order and at the same "
           "pitches, over four times as long."))
s.append(P("Two things change besides the length. Each note no longer has a clear start; it fades in. And where one "
           "note changes to the next, the two blend, because a slice can span both notes at once."))
s.append(fig("07_result", W))
s.append(lookfor(["The horizontal lines sit at the same heights in both pictures: the pitches haven't changed.",
                  "The output lasts four times as long, and the changes between notes are soft and gradual."]))

# ---------- 8 ----------
s.append(PageBreak())
s.append(Heading("8", "Why sharp sounds become soft"))
s.append(P("A drum hit is almost all attack: a sudden start, then a fade. The start is sudden because, at that "
           "instant, all its pitches line up. In step 3, Paulstretch shifts every pitch's phase at random, so they "
           "no longer line up, and the hit loses its edge and becomes a soft swell of the "
           "same sound, rising and fading over the length of a few slices."))
s.append(fig("08_attack", W))
s.append(lookfor(["Top: the hit starts in an instant.",
                  "Bottom: the stretched version has no instant start. It rises and fades smoothly, and it lasts longer."]))

# ---------- 9 ----------
s.append(Heading("9", "Small and large windows"))
s.append(P("The window size sets how much of the sound each slice covers, and so how much detail survives the "
           "random phase shifts. A small window takes many short slices: separate events still come through, and the sound is "
           "grainier. A large window takes long slices that each cover several events: they merge into one smooth sound."))
s.append(fig("09_window", W))
s.append(lookfor(["Top: six separate short notes.",
                  "Middle, small window: six bumps are still there, rougher.",
                  "Bottom, large window: the bumps are gone. One steady, even sound."]))
s.append(P("On the module, WINDOW goes from 1k (1,024 samples, about 21 milliseconds) to 64k (65,536 samples, about "
           "1.4 seconds). The default, 16k, is about a third of a second.", small))

# ---------- 10 ----------
s.append(PageBreak())
s.append(Heading("10", "PITCH: moving every ingredient"))
s.append(P("Because Paulstretch already has each slice as a list of pitches, changing the pitch is simple: before "
           "rebuilding, it moves every ingredient up or down by the same musical interval. An octave up doubles "
           "every pitch. The speed of the stretch isn't affected."))
s.append(fig("10_pitch", W))
s.append(lookfor(["Each blue peak moves to twice its pitch, shown in orange. The C, E and G of the chord become the "
                  "C, E and G an octave higher.",
                  "The highest blue peak, near 1,000 Hz, has no orange partner on this chart: it moved to near 2,000 Hz, "
                  "off the right edge."]))

# ---------- 11 ----------
s.append(Heading("11", "FREEZE: holding one moment"))
s.append(P("FREEZE stops step 5: the module keeps reading slices from the same place. The output doesn't loop or "
           "go silent, though. Every new slice gets fresh random phases in step 3, so it is the same moment, "
           "rebuilt again and again. The result is a steady, slowly shimmering drone."))
s.append(fig("11_freeze", W))
s.append(lookfor(["Inside the shaded part, the lines stay flat: the sound holds still.",
                  "The held slice happens to span the end of the C and the start of the E, so you hear a bit of both.",
                  "When FREEZE is released, the melody carries on from where it stopped."]))

# ---------- 12 ----------
s.append(PageBreak())
s.append(Heading("12", "REVERSE: walking backwards"))
s.append(P("REVERSE runs step 5 backwards: each slice is read from a little earlier than the one before. Inside a "
           "slice there is no forwards or backwards, because its phases are random anyway. So what changes is the "
           "shape over time: a note that faded away now swells in."))
s.append(fig("12_reverse", W))
s.append(lookfor(["Top: a plucked note, loud at the start and fading.",
                  "Middle, forwards: it fades away, slowly.",
                  "Bottom, in reverse: the same note grows from silence to its loudest at the end."]))

# ---------- 13 ----------
s.append(Heading("13", "Several voices on one sound"))
s.append(P("The Paulstretch Heads expander adds more voices, called heads, that read the same recording. Each "
           "head goes through the same five steps, but from its own place, at its own stretch, in its own "
           "direction and at its own pitch. Together they can make chords, or layers moving at different speeds."))
s.append(fig("13_heads", W))
s.append(lookfor(["Each coloured block is one voice's slice; the line in it is the part heard most.",
                  "Head 2's arrow points left: it is in reverse."]))

# ---------- 14 ----------
s.append(PageBreak())
s.append(Heading("14", "How the voices share the work"))
s.append(P("Steps 2 and 3, listing the pitches and rebuilding the slice, are the hard work. Each voice does them "
           "once per half window, all in one go. At the largest window that takes over a millisecond per voice."))
s.append(P("If every voice did its work at the same moment, the computer would face one big burst of work. VCV "
           "Rack has only a few milliseconds to deliver each small batch of audio, and a burst bigger than that "
           "causes a click or dropout. So the voices take turns: each one prepares its next slice a little early, at "
           "its own moment, and switches to it on time. The sound is exactly the same."))
s.append(fig("14_turns", W))
s.append(lookfor(["Left: all five voices work at the same moment, in one big burst.",
                  "Right: the same amount of work, spread out so no two voices work at once."]))
s.append(P("Measured on the module with all 13 voices at the largest window: the busiest moment took about 7.2 "
           "milliseconds all at once, and about 0.6 milliseconds taking turns. Rack's limit for that batch is about "
           "5.3 milliseconds.", small))

# keep each section (heading to the next heading) on one page, with space above its heading
grouped, current = [], []
def flush():
    if current:
        grouped.append(KeepTogether(list(current)))
        current.clear()
for f in s:
    if isinstance(f, Heading):
        flush()
        if grouped and not isinstance(grouped[-1], PageBreak):
            grouped.append(Spacer(1, 10))
        current.append(f)
    elif isinstance(f, (PageBreak, NextPageTemplate)):
        flush()
        grouped.append(f)
    elif current:
        current.append(f)
    else:
        grouped.append(f)
flush()
doc.build(grouped)
print("ok")
