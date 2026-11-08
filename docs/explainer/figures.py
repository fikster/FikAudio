"""Figures for "How Paulstretch works". Every picture is computed: the stretch
below follows the same steps as src/PaulstretchCore.hpp (window, magnitudes,
random phases, overlap-add, hop/stretch), on simple synthetic test sounds.

Usage: python3 figures.py OUTDIR
"""
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import FancyArrowPatch, Rectangle

OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)
SR = 22050

# palette: reference categorical slots 1-3, plus greys
IN = "#2a78d6"     # input / original
OUTC = "#eb6834"   # output / result
THIRD = "#1baf7a"
INK = "#1d1f24"
SOFT = "#6b6e76"
GRID = "#e4e4e8"
SURF = "#ffffff"
SPEC = LinearSegmentedColormap.from_list("spec", ["#ffffff", "#bcd3f2", "#2a78d6", "#0b2e5c"])

plt.rcParams.update({
    "font.family": "Arial", "font.size": 9, "axes.titlesize": 10, "axes.titleweight": "bold",
    "axes.titlelocation": "left", "axes.edgecolor": "#b9bbc2", "axes.labelcolor": SOFT,
    "xtick.color": SOFT, "ytick.color": SOFT, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": False, "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.dpi": 220,
    "lines.linewidth": 1.2, "legend.frameon": False, "legend.fontsize": 8.5,
})


def save(fig, name):
    fig.savefig(os.path.join(OUT, name + ".png"), bbox_inches="tight", pad_inches=0.06)
    plt.close(fig)


# ---------- the method, as in PaulstretchCore ----------
def window(n):
    x = np.linspace(-1, 1, n)
    return np.clip(1 - x * x, 0, None) ** 1.25


def hinv_curve(n):
    half = n // 2
    w = window(n)
    h = (1 + np.sqrt(0.5)) / 2
    hv = h - (1 - h) * np.cos(np.arange(half) * 2 * np.pi / half)
    mw2 = np.mean(w * w)
    power = np.sum(mw2 * (w[:half] ** 2 + w[half:] ** 2) * hv * hv)
    return hv / np.sqrt(power / half)


def shift_mags(mag, pitch):
    if pitch == 1:
        return mag
    out = np.zeros_like(mag)
    j = np.round(np.arange(len(mag)) * pitch).astype(int)
    ok = j < len(mag)
    np.add.at(out, j[ok], mag[ok] ** 2)
    return np.sqrt(out)


def paulstretch(x, factor, n, seconds, pitch=1.0, seed=3, reverse=False, start=0.0, freeze_at=None):
    """Returns the output and the read position used for each frame."""
    rng = np.random.default_rng(seed)
    half = n // 2
    w, hv = window(n), hinv_curve(n)
    length = len(x)
    frames = int(seconds * SR / half) + 1
    out = np.zeros(frames * half)
    prev = np.zeros(n)
    pos = start * length
    positions = []
    for k in range(frames):
        idx = (int(pos) + np.arange(n)) % length
        mag = shift_mags(np.abs(np.fft.rfft(x[idx] * w)), pitch)
        frame = np.fft.irfft(mag * np.exp(1j * rng.uniform(0, 2 * np.pi, len(mag))), n) * w
        out[k * half:(k + 1) * half] = (frame[:half] + prev[half:]) * hv
        prev = frame
        positions.append(pos)
        t = k * half / SR
        if freeze_at is None or not (freeze_at[0] <= t < freeze_at[1]):
            pos = (pos + (-half if reverse else half) / factor) % length
    return out[: int(seconds * SR)], np.array(positions)


# ---------- test sounds ----------
def t_axis(sec):
    return np.arange(int(sec * SR)) / SR


def note(freq, sec, decay=3.0, harmonics=(1.0, 0.45, 0.25, 0.12)):
    t = t_axis(sec)
    env = np.exp(-decay * t) * np.minimum(1, t / 0.005)
    return env * sum(a * np.sin(2 * np.pi * freq * (i + 1) * t) for i, a in enumerate(harmonics)) / 1.8


C, E, G = 261.6, 329.6, 392.0


def silence(sec):
    return np.zeros(int(sec * SR))


def melody():
    # silence after it, so the stretch doesn't loop back into the first note
    return np.concatenate([note(C, 0.5, 4), note(E, 0.5, 4), note(G, 0.5, 4), silence(0.25)])


def chord(sec=1.0):
    return (note(C, sec, 1.2) + note(E, sec, 1.2) + note(G, sec, 1.2)) / 2


def spectrogram(ax, y, fmax=1400, title=None, vmin=-55):
    n, hop = 1024, 128
    w = np.hanning(n)
    frames = [np.abs(np.fft.rfft(y[i:i + n] * w)) for i in range(0, len(y) - n, hop)]
    S = 20 * np.log10(np.array(frames).T + 1e-9)
    S -= S.max()
    freqs = np.fft.rfftfreq(n, 1 / SR)
    keep = freqs <= fmax
    ax.imshow(S[keep], origin="lower", aspect="auto", cmap=SPEC, vmin=vmin, vmax=0,
              extent=[0, len(y) / SR, 0, freqs[keep][-1]], interpolation="bilinear")
    ax.set_ylabel("pitch (Hz)")
    ax.set_xlabel("time (s)")
    if title:
        ax.set_title(title)


def envelope(y, ms=20):
    k = int(SR * ms / 1000)
    p = np.convolve(y * y, np.ones(k) / k, mode="same")
    return np.sqrt(p)


def label_peaks(ax, freqs, mags, names, color):
    for f0, nm in zip((C, E, G), names):
        i = np.argmin(np.abs(freqs - f0))
        ax.annotate(nm, (freqs[i], mags[i]), xytext=(0, 4), textcoords="offset points", ha="center",
                    fontsize=8.5, color=INK, fontweight="bold")


# ---------- 1. tape versus Paulstretch ----------
def fig_tape():
    # a 10 s note A that swells in and slowly dies away, with a few harmonics
    sec = 10.0
    t = t_axis(sec)
    env = np.minimum(1, t / 0.4) * np.exp(-0.3 * t)
    def tone(freq, tt):
        return sum(a * np.sin(2 * np.pi * freq * (i + 1) * tt) for i, a in enumerate((1.0, 0.35, 0.15))) / 1.5
    orig = env * tone(440, t)
    # tape at half speed: every sample takes twice as long, so 20 s and an octave down
    t2 = t_axis(2 * sec)
    tape = np.interp(t2 / 2, t, env) * tone(220, t2)
    # Paulstretch at 2x with the module's largest window (65536 samples at 44.1 kHz = 1.5 s)
    ps, _ = paulstretch(orig, 2, 32768, 2 * sec)
    ps *= np.max(np.abs(orig)) / np.max(np.abs(ps))

    zoom_ms = 20
    zooms = (2.0, 4.0, 4.0)  # where each zoom is taken: the same moment of the note
    rows = ((orig, IN, "Original: 10 seconds of the note A (440 Hz)"),
            (tape, SOFT, "Tape at half speed: 20 seconds, an octave lower (220 Hz)"),
            (ps, OUTC, "Paulstretch, 2× longer: 20 seconds, still 440 Hz"))
    fig = plt.figure(figsize=(6.8, 4.6))
    gs = fig.add_gridspec(3, 2, width_ratios=[3.3, 1], hspace=0.75, wspace=0.08)
    for r, ((y, c, title), z) in enumerate(zip(rows, zooms)):
        ax = fig.add_subplot(gs[r, 0])
        tt = np.arange(len(y)) / SR
        ax.plot(tt, y, color=c, lw=0.35, rasterized=True)
        ax.set_xlim(0, 20.5)
        ax.set_ylim(-1.15, 1.15)
        ax.set_yticks([])
        ax.spines["left"].set_visible(False)
        ax.set_xticks(range(0, 21, 5))
        ax.set_title(title, fontsize=9.5)
        ax.axvspan(z, z + 0.25, color=INK, alpha=0.18, lw=0)
        if r == 2:
            ax.annotate("fades in", (0.4, -0.3), xytext=(0.9, -1.05), fontsize=8, color=INK, va="center",
                        arrowprops=dict(arrowstyle="-", color=SOFT, lw=0.8))
            ax.annotate("the start comes\nround again", (19.6, -0.5), xytext=(15.2, -0.95), fontsize=8,
                        color=INK, va="center", arrowprops=dict(arrowstyle="-", color=SOFT, lw=0.8))
            ax.set_xlabel("time (seconds)")
        zx = fig.add_subplot(gs[r, 1])
        i0 = int(z * SR)
        seg = y[i0:i0 + int(zoom_ms / 1000 * SR)]
        zx.plot(np.arange(len(seg)) / SR * 1000, seg / np.max(np.abs(seg)), color=c, lw=1.0)
        zx.set_ylim(-1.25, 1.25)
        zx.set_yticks([])
        zx.spines["left"].set_visible(False)
        zx.set_xticks([0, 10, 20])
        zx.set_title(f"zoom: 20 ms at {z:g} s", fontsize=8.5, fontweight="normal", color=SOFT)
        if r == 2:
            zx.set_xlabel("milliseconds")
    save(fig, "01_tape")


# ---------- 2. two views of a sound ----------
def fig_two_views():
    y = chord(1.0)
    fig, (a, b) = plt.subplots(1, 2, figsize=(6.6, 2.5), gridspec_kw={"width_ratios": [1.25, 1]})
    a.plot(t_axis(1.0), y, color=IN, lw=0.5)
    a.set_title("Waveform: how it moves over time")
    a.set_xlabel("time (s)")
    a.set_yticks([])
    a.spines["left"].set_visible(False)
    n = 8192
    seg = y[2000:2000 + n] * np.hanning(n)
    mag = np.abs(np.fft.rfft(seg))
    mag /= mag.max()
    f = np.fft.rfftfreq(n, 1 / SR)
    keep = f < 1300
    b.fill_between(f[keep], mag[keep], color=IN, alpha=0.25, lw=0)
    b.plot(f[keep], mag[keep], color=IN, lw=1)
    label_peaks(b, f, mag, ("C", "E", "G"), IN)
    b.set_title("Spectrum: which pitches it contains")
    b.set_xlabel("pitch (Hz)")
    b.set_ylabel("amount")
    b.set_yticks([])
    b.set_ylim(0, 1.2)
    fig.tight_layout(w_pad=2.0)
    save(fig, "02_two_views")


# ---------- 3. the steps on one slice ----------
def fig_slice():
    y = chord(1.0)
    n = 4096
    start = 6000
    w = window(n)
    t = t_axis(1.0)
    fig, (a, b) = plt.subplots(2, 1, figsize=(6.6, 3.2))
    a.plot(t, y, color="#b5b8c0", lw=0.5)
    seg_t = t[start:start + n]
    a.plot(seg_t, y[start:start + n], color=IN, lw=0.6)
    peak = np.max(np.abs(y))
    a.plot(seg_t, w * peak * 1.05, color=OUTC, lw=1.4, label="the window's shape")
    a.add_patch(Rectangle((seg_t[0], -peak * 1.1), seg_t[-1] - seg_t[0], peak * 2.2, color=OUTC, alpha=0.07, lw=0))
    a.set_title("1 · Take a short slice of the sound (the window)")
    a.set_yticks([])
    a.spines["left"].set_visible(False)
    a.set_xlabel("time (s)")
    a.legend(loc="upper right")
    sl = y[start:start + n] * w
    b.plot(np.arange(n) / SR * 1000, sl, color=IN, lw=0.7)
    b.set_title("The slice, faded in and out by the window")
    b.set_xlabel("time within the slice (ms)")
    b.set_yticks([])
    b.spines["left"].set_visible(False)
    fig.tight_layout(h_pad=1.0)
    save(fig, "03_slice")


def fig_scramble():
    y = chord(1.0)
    n = 4096
    start = 6000
    w = window(n)
    sl = y[start:start + n] * w
    S = np.fft.rfft(sl)
    mag = np.abs(S)
    # the random phases: this seed keeps each note about as loud in the zoomed 25 ms as before,
    # so the picture shows the sliding; other seeds also make a note swell or dip there
    rng = np.random.default_rng(28)
    R = mag * np.exp(1j * rng.uniform(0, 2 * np.pi, len(mag)))
    rebuilt = np.fft.irfft(R, n) * w
    f = np.fft.rfftfreq(n, 1 / SR)

    # split the spectrum into bands: the three notes, and everything above them (their harmonics).
    # The bands' waves add up exactly to the slice, before and after.
    bands = (("C", 0, 295, "#1baf7a"), ("E", 295, 360, "#6250d6"), ("G", 360, 450, "#d55181"),
             ("higher harmonics", 450, SR, "#8a8c93"))
    def part(spec, lo, hi):
        return np.fft.irfft(np.where((f >= lo) & (f < hi), spec, 0), n)
    before = [part(S, lo, hi) for _, lo, hi, _ in bands]
    after = [part(R, lo, hi) * w for _, lo, hi, _ in bands]

    # show 25 ms from the middle of the slice, where the fade is fully open
    z0, zl = n // 2 - int(0.0125 * SR), int(0.025 * SR)
    ms = np.arange(zl) / SR * 1000
    zs = slice(z0, z0 + zl)
    scale = max(np.max(np.abs(x[zs])) for x in before + after)
    sscale = max(np.max(np.abs(sl[zs])), np.max(np.abs(rebuilt[zs])))

    fig = plt.figure(figsize=(6.8, 6.0))
    gs = fig.add_gridspec(7, 2, height_ratios=[1, 1, 1, 1, 1.5, 0.6, 2.3], hspace=0.6, wspace=0.12)
    for col, (parts, total, tc, title) in enumerate(((before, sl, IN, "The slice"),
                                                      (after, rebuilt, OUTC, "Rebuilt with random phase shifts"))):
        for r, ((name, _, _, c), x) in enumerate(zip(bands, parts)):
            ax = fig.add_subplot(gs[r, col])
            ax.plot(ms, x[zs] / scale, color=c, lw=1.1)
            ax.set_ylim(-1.1, 1.1)
            ax.set_yticks([]); ax.set_xticks([])
            for g in range(5, 25, 5):
                ax.axvline(g, color=GRID, lw=0.6, zorder=0)
            ax.spines["left"].set_visible(False); ax.spines["bottom"].set_visible(False)
            ax.axhline(0, color=GRID, lw=0.6, zorder=0)
            ax.text(0.0, 0.98, name, transform=ax.transAxes, fontsize=8.5, color=INK, fontweight="bold",
                    va="bottom")
            if r == 0:
                ax.set_title(title, fontsize=9.5, pad=14)
        ax = fig.add_subplot(gs[4, col])
        ax.plot(ms, total[zs] / sscale, color=tc, lw=1.2)
        ax.set_ylim(-1.15, 1.15)
        ax.set_yticks([])
        ax.spines["left"].set_visible(False)
        ax.text(0.0, 0.98, "all added together", transform=ax.transAxes, fontsize=8.5, color=INK,
                fontweight="bold", va="bottom")
        ax.set_xlabel("milliseconds")

    c = fig.add_subplot(gs[6, :])
    keep = f < 1300
    m1 = mag / mag.max()
    m2 = np.abs(np.fft.rfft(rebuilt))
    m2 = m2 / m2.max()
    for name, lo, hi, col in bands:
        c.axvspan(lo, min(hi, 1300), color=col, alpha=0.10, lw=0)
    c.plot(f[keep], m1[keep], color=IN, lw=2.2, label="the slice")
    c.plot(f[keep], m2[keep], color=OUTC, lw=1.0, ls=(0, (3, 2)), label="rebuilt")
    label_peaks(c, f, m1, ("C", "E", "G"), IN)
    c.set_title("Their spectra: the same pitches, in the same amounts", fontsize=9.5)
    c.set_xlabel("pitch (Hz)")
    c.set_yticks([])
    c.set_xlim(0, 1300)
    c.set_ylim(0, 1.25)
    c.legend(loc="upper right")
    save(fig, "04_scramble")


def fig_overlap():
    y = chord(2.0)
    n = 4096
    half = n // 2
    w = window(n)
    rng = np.random.default_rng(11)
    frames = []
    pos = 0
    for k in range(7):
        idx = (int(pos) + np.arange(n)) % len(y)
        mag = np.abs(np.fft.rfft(y[idx] * w))
        frames.append(np.fft.irfft(mag * np.exp(1j * rng.uniform(0, 2 * np.pi, len(mag))), n) * w)
        pos += half / 4
    peak = max(np.max(np.abs(f)) for f in frames)
    hv = hinv_curve(n)
    out = np.zeros(8 * half)
    prev = np.zeros(n)
    for k, fr in enumerate(frames):
        out[k * half:(k + 1) * half] = (fr[:half] + prev[half:]) * hv
        prev = fr
    fig, (a, b) = plt.subplots(2, 1, figsize=(6.6, 3.6), sharex=True, gridspec_kw={"height_ratios": [1.6, 1]})
    for k, fr in enumerate(frames[1:6], start=1):
        tt = (np.arange(n) + (k - 1) * half) / SR * 1000
        row = k % 2
        col = IN if row else "#7fa9e3"
        a.plot(tt, fr / peak * 0.45 + row * 1.1, color=col, lw=0.5)
        a.plot(tt, w * 0.45 + row * 1.1, color=col, lw=1.0, alpha=0.6)
        a.text(tt[n // 2], row * 1.1 + 0.52, f"slice {k}", ha="center", fontsize=8, color=INK)
    a.set_title("2 · Each rebuilt slice starts half a slice after the one before")
    a.set_yticks([])
    a.set_ylim(-0.55, 1.75)
    a.spines["left"].set_visible(False)
    ms = np.arange(len(out)) / SR * 1000
    b.plot(ms - half / SR * 1000, out, color=OUTC, lw=0.5)
    b.set_title("Added together: one smooth, continuous sound")
    b.set_xlabel("time (ms)")
    b.set_yticks([])
    b.spines["left"].set_visible(False)
    b.set_xlim(0, 5 * half / SR * 1000)
    fig.tight_layout(h_pad=0.8)
    save(fig, "05_overlap")


def fig_reading():
    fig, ax = plt.subplots(figsize=(6.6, 2.6))
    ax.set_xlim(-0.4, 10.6)
    ax.set_ylim(-1.6, 3.4)
    ax.axis("off")
    stretch, hop_out = 4, 2.0
    yin, yout = 2.2, 0.0
    ax.plot([-0.3, 10.5], [yin, yin], color="#b9bbc2", lw=0.8)
    ax.plot([-0.3, 10.5], [yout, yout], color="#b9bbc2", lw=0.8)
    ax.text(-0.3, 3.2, "Input: the middle of each slice it reads, a small step apart", color=INK, fontsize=9.5, fontweight="bold")
    ax.text(-0.3, -1.5, "Output: the middle of each rebuilt slice, a big step apart", color=INK, fontsize=9.5, fontweight="bold")
    for k in range(5):
        xi = 1 + k * hop_out / stretch
        xo = 1 + k * hop_out
        ax.add_patch(FancyArrowPatch((xi, yin - 0.12), (xo, yout + 0.14), arrowstyle="-|>", mutation_scale=9,
                                     color="#9a9ca3", lw=0.8))
        ax.plot(xi, yin, "o", color=IN, ms=6)
        ax.plot(xo, yout, "o", color=OUTC, ms=6)
        ax.text(xi, yin + 0.22, str(k + 1), ha="center", fontsize=8, color=IN)
        ax.text(xo, yout - 0.42, str(k + 1), ha="center", fontsize=8, color=OUTC)
    ax.annotate("", xy=(3.5, yin + 0.25), xytext=(3.0, yin + 0.25), arrowprops=dict(arrowstyle="<->", color=IN, lw=1))
    ax.text(3.7, yin + 0.17, "step", color=IN, fontsize=8)
    ax.annotate("", xy=(5.0, yout - 0.62), xytext=(3.0, yout - 0.62), arrowprops=dict(arrowstyle="<->", color=OUTC, lw=1))
    ax.text(5.2, yout - 0.72, "step × 4 (STRETCH 4×)", color=OUTC, fontsize=8)
    save(fig, "06_reading")


def fig_result():
    y = melody()
    out, _ = paulstretch(y, 4, 4096, 6.0, seed=5)
    fig, (a, b) = plt.subplots(2, 1, figsize=(6.6, 3.9), sharey=True)
    spectrogram(a, y, title="Input: three plucked notes, C, E, G, in 1.5 s")
    spectrogram(b, out, title="Output at 4× stretch: the same notes, 6 s long, smooth and blended")
    a.set_xlim(0, 6)
    b.set_xlim(0, 6)
    fig.tight_layout(h_pad=1.0)
    save(fig, "07_result")


def fig_attack():
    hit = np.zeros(int(1.6 * SR))
    tt = t_axis(0.4)
    rng = np.random.default_rng(2)
    hit[int(0.2 * SR):int(0.2 * SR) + len(tt)] = (rng.normal(0, 1, len(tt)) * np.exp(-60 * tt) * 0.8 +
                                                  np.sin(2 * np.pi * 120 * tt) * np.exp(-12 * tt))
    out, _ = paulstretch(hit, 4, 4096, 6.0, seed=4)
    fig, (a, b) = plt.subplots(2, 1, figsize=(6.6, 3.0), sharex=True)
    a.plot(t_axis(len(hit) / SR), hit / np.max(np.abs(hit)), color=IN, lw=0.4)
    a.set_title("Input: a drum hit, sudden then fading")
    b.plot(t_axis(len(out) / SR), out / np.max(np.abs(out)), color=OUTC, lw=0.3)
    b.set_title("Output at 4× stretch: no sudden start, a soft swell and fade")
    b.set_xlabel("time (s)")
    for ax in (a, b):
        ax.set_yticks([])
        ax.spines["left"].set_visible(False)
    fig.tight_layout(h_pad=0.8)
    save(fig, "08_attack")


def fig_window_size():
    y = np.concatenate([note(330, 0.25, 18) for _ in range(6)])
    small, _ = paulstretch(y, 4, 512, len(y) * 4 / SR, seed=6)
    large, _ = paulstretch(y, 4, 8192, len(y) * 4 / SR, seed=6)
    fig, axs = plt.subplots(3, 1, figsize=(6.6, 3.6), sharex=True)
    rows = ((y, IN, "Input: six short notes, 1.5 s", 1),
            (small, OUTC, "Small window, stretched 4×: the six notes still come through", 4),
            (large, OUTC, "Large window, stretched 4×: one smooth, even sound", 4))
    for ax, (sig, col, title, k) in zip(axs, rows):
        e = envelope(sig, 15)
        tt = np.arange(len(e)) / SR / k
        ax.fill_between(tt, e / e.max(), color=col, alpha=0.3, lw=0)
        ax.plot(tt, e / e.max(), color=col, lw=0.9)
        ax.set_title(title, fontsize=9.5)
        ax.set_yticks([])
        ax.set_ylim(0, 1.15)
        ax.spines["left"].set_visible(False)
    axs[2].set_xlabel("position in the input (s); the outputs last 4 times as long")
    fig.tight_layout(h_pad=0.6)
    save(fig, "09_window")


def fig_pitch():
    y = chord(1.0)
    n = 8192
    w = window(n)
    seg = y[3000:3000 + n] * w
    mag = np.abs(np.fft.rfft(seg))
    up = shift_mags(mag, 2.0)
    f = np.fft.rfftfreq(n, 1 / SR)
    keep = f < 1000
    fig, ax = plt.subplots(figsize=(6.6, 2.4))
    m = max(mag.max(), up.max())
    ax.plot(f[keep], mag[keep] / m, color=IN, lw=1.2, label="before")
    ax.plot(f[keep], up[keep] / m, color=OUTC, lw=1.2, label="PITCH +12 (an octave up)")
    for f0, nm in ((C, "C"), (E, "E"), (G, "G")):
        ax.annotate("", xy=(2 * f0, 1.02), xytext=(f0, 1.02),
                    arrowprops=dict(arrowstyle="-|>", color=SOFT, lw=0.8, connectionstyle="arc3,rad=-0.25"))
    ax.set_title("Every ingredient moves to twice its pitch")
    ax.set_xlabel("pitch (Hz)")
    ax.set_yticks([])
    ax.set_ylim(0, 1.15)
    ax.legend(loc="center left")
    save(fig, "10_pitch")


def fig_freeze():
    y = melody()
    out, _ = paulstretch(y, 4, 4096, 6.0, seed=8, freeze_at=(1.6, 4.6))
    fig, ax = plt.subplots(figsize=(6.6, 2.2))
    spectrogram(ax, out, title="Stretched melody, with FREEZE on in the shaded part: one moment, held")
    ax.axvspan(1.6, 4.6, color=OUTC, alpha=0.16, lw=0)
    for xv in (1.6, 4.6):
        ax.axvline(xv, color=OUTC, lw=1.0)
    save(fig, "11_freeze")


def fig_reverse():
    y = np.concatenate([silence(0.2), note(C, 1.3, 3.0), silence(0.2)])
    fwd, _ = paulstretch(y, 4, 4096, 6.4, seed=9, start=0.0)
    rev, _ = paulstretch(y, 4, 4096, 6.4, seed=9, reverse=True, start=0.92)
    fig, axs = plt.subplots(3, 1, figsize=(6.6, 3.4), sharex=False)
    rows = ((y, IN, "Input: one plucked note, loud then fading", 1.7),
            (fwd, OUTC, "Stretched 4× forwards: fades away slowly", 6.4),
            (rev, THIRD, "Stretched 4× in REVERSE: swells in slowly", 6.4))
    for ax, (sig, col, title, sec) in zip(axs, rows):
        e = envelope(sig, 30)
        tt = np.arange(len(e)) / SR
        ax.fill_between(tt, e / e.max(), color=col, alpha=0.3, lw=0)
        ax.plot(tt, e / e.max(), color=col, lw=0.9)
        ax.set_title(title, fontsize=9.5)
        ax.set_yticks([])
        ax.set_ylim(0, 1.15)
        ax.set_xlim(0, sec)
        ax.spines["left"].set_visible(False)
    axs[2].set_xlabel("time (s)")
    fig.tight_layout(h_pad=0.6)
    save(fig, "12_reverse")


def fig_heads():
    fig, ax = plt.subplots(figsize=(6.6, 1.9))
    ax.set_xlim(0, 10)
    ax.set_ylim(-0.9, 2.0)
    ax.axis("off")
    ax.add_patch(Rectangle((0, 0), 10, 0.8, color="#f0f1f3", lw=0))
    ax.text(0, 1.05, "The buffer: one recording, shared by every voice", fontsize=9.5, fontweight="bold", color=INK)
    voices = (("main", 1.2, "#eda100", 1), ("head 1", 3.6, "#40c8e0", 1), ("head 2", 5.0, "#b080f0", -1),
              ("head 3", 7.4, "#70d070", 1), ("head 4", 8.6, "#f070a8", 1))
    for name, x, col, d in voices:
        ax.add_patch(Rectangle((x, 0.04), 0.7, 0.72, color=col, alpha=0.35, lw=0))
        ax.plot([x + 0.35, x + 0.35], [0.04, 0.76], color=col, lw=1.6)
        ax.annotate("", xy=(x + 0.35 + d * 0.55, -0.25), xytext=(x + 0.35, -0.25),
                    arrowprops=dict(arrowstyle="-|>", color=col, lw=1.2))
        ax.text(x + 0.35, -0.7, name, ha="center", fontsize=8.5, color=INK)
    save(fig, "13_heads")


def fig_turns():
    fig, (a, b) = plt.subplots(1, 2, figsize=(6.6, 2.2), sharey=True)
    voices = 5
    period = 10
    for ax, staggered, title in ((a, False, "All at once"), (b, True, "Taking turns")):
        for v in range(voices):
            for k in range(3):
                start = k * period + (v * period / voices if staggered else 0)
                ax.add_patch(Rectangle((start, v - 0.32), 0.9, 0.64, color=IN if not staggered else OUTC, lw=0))
        ax.set_xlim(-0.5, 3 * period)
        ax.set_ylim(-0.7, voices - 0.3)
        ax.set_yticks(range(voices))
        ax.set_yticklabels(["main", "head 1", "head 2", "head 3", "head 4"])
        ax.set_xticks([])
        ax.set_xlabel("time →")
        ax.set_title(title, fontsize=9.5)
    fig.tight_layout(w_pad=1.5)
    save(fig, "14_turns")


for fn in (fig_tape, fig_two_views, fig_slice, fig_scramble, fig_overlap, fig_reading, fig_result, fig_attack,
           fig_window_size, fig_pitch, fig_freeze, fig_reverse, fig_heads, fig_turns):
    fn()
print("figures written to", OUT)
