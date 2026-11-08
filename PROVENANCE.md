# Provenance of the Paulstretch modules

The Paulstretch and Paulstretch Heads modules are written for this plugin.
They implement Nasca Octavian Paul's Paulstretch algorithm.

## Sources and licences

| Source | Licence | How it is used |
|---|---|---|
| [paulstretch_python](https://github.com/paulnasca/paulstretch_python), commit 0d4e7a0 | Public domain ("this file is released under Public Domain") | The algorithm the DSP core follows. |
| [paulstretch_cpp](https://github.com/paulnasca/paulstretch_cpp), commit 7f5c399 | GPL version 2 only | No code used. Ideas only: pitch shift, and the planned effects listed below. |

Because paulstretch_cpp is GPL-2 only, its code cannot be included in this
plugin, which is GPL-3.0-or-later. Copyright covers code, not algorithms or
ideas (17 U.S.C. §102(b); EU Directive 2009/24/EC art. 1(2)). Features whose
idea comes from paulstretch_cpp are therefore written from a description of
the effect, never from its source.

## Where each part of `src/PaulstretchCore.hpp` comes from

From paulstretch_python:
- window (1-x²)^1.25: `paulstretch_stereo.py` line 83;
- hop of half a window, read position advanced by hop/stretch: stereo lines 79 and 125;
- magnitudes kept, uniform random phases, inverse real FFT: stereo lines 98-105;
- window applied again after the inverse FFT: stereo line 108;
- overlap-add of the new frame's first half with the old frame's second half: stereo line 111;
- the `hinv` amplitude correction h-(1-h)·cos(2πi/half), h = (1+√0.5)/2: `paulstretch_mono.py` lines 62-63 and 93.

Original to this plugin:
- the power-matching output gain;
- the clamped double-precision window (needed under Rack's fast-math flags) and the NaN guard;
- reverse playback;
- multiple heads and the expander;
- recording, wrap-around and file loading (`src/AudioFile.hpp`).

Idea from paulstretch_cpp, written independently:
- pitch shift by moving bin magnitudes. The implementation differs: one
  path for both directions, each bin's power split between the two bins
  either side of its target (T022), and power summing.

Planned features whose ideas come from paulstretch_cpp: spread, harmonics,
octave mixer (T011, T013, T014). Onset detection (T012) is in the
public-domain `paulstretch_newmethod.py`.

## Similarity check (7 November 2026)

The plugin's sources were compared with paulstretch_cpp using a token-based
checker in the style of MOSS and JPlag (`tools/provenance/`). It renames every
identifier to one placeholder, ignores layout and comments, and looks for
shared runs of code. The check was calibrated against two reference points:
a deliberately disguised copy of four of Paul's functions, and unrelated DSP
code from the Rack SDK.

| Comparison | fingerprints shared (k=20) | coverage (k=20) | longest shared run |
|---|---|---|---|
| Disguised copy vs paulstretch_cpp (should be caught) | 18.5% | 38.1% | 61 tokens |
| PaulstretchCore.hpp vs paulstretch_cpp | 3.1% | 16.1% | 31 tokens |
| PaulstretchCore.hpp vs Rack SDK DSP code (unrelated) | 1.5% | 7.2% | 28 tokens |
| Paul's Stretch.cpp vs Rack SDK (two unrelated codebases) | 2.2% | 7.7% | 35 tokens |

Rechecked on 8 November 2026, after the expander chain, voice staggering,
per-head SCAN and the expander displays were added:

| Comparison | fingerprints shared (k=20) | coverage (k=20) | longest shared run |
|---|---|---|---|
| PaulstretchCore.hpp vs paulstretch_cpp | 2.8% | 14.8% | 31 tokens |
| PaulstretchCore.hpp vs Rack SDK DSP code (unrelated) | 1.5% | 8.3% | 28 tokens |
| Every other plugin source vs paulstretch_cpp | 0.6% or less | 4.0% or less | 28 tokens |

Rechecked again on 8 November 2026, after the pitch shift was changed to split
each bin's power between neighbouring bins (T022): PaulstretchCore.hpp vs
paulstretch_cpp 2.7% / 14.5% / 31 tokens; vs Rack SDK 1.5% / 8.1% / 28 tokens;
every other source unchanged. No shared run touches the pitch-shift loop.

Every shared fragment is a generic loop such as
`for (int i = 0; i < n; i++) x[i] = …`, and the same shapes also match
unrelated Rack code. The plugin shares no comments, distinctive identifiers or
unusual constants with paulstretch_cpp. In design, the core differs from
paulstretch_cpp in each place where paulstretch_cpp differs from the Python
version:
- window shape;
- random-number generator;
- DC and Nyquist handling;
- overlap-add, where paulstretch_cpp crossfades;
- buffering;
- pitch-shift details.

**Conclusion:** no evidence of copied or closely paraphrased GPL code.
A token check cannot detect ideas carried over, and the design comparison
above is a judgement, not a measurement. This record is not legal advice.
