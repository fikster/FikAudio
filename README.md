# Fik Audio

Modules for [VCV Rack 2](https://vcvrack.com).

## Paulstretch

Extreme time-stretching of a recorded or loaded sound: a few seconds can become minutes of slowly evolving texture, at the same pitch. Record live input or load a WAV or AIFF file, then play it back stretched up to 8192 times its length.

- STRETCH, WINDOW, PITCH and START controls, with CV for stretch and pitch (V/OCT).
- FREEZE holds one moment as a drone.
- REVERSE reads backwards.
- SCAN moves the read position by CV.
- The loaded file can optionally be stored inside the patch.

## Paulstretch Heads

An expander for Paulstretch that adds four more playback heads on the same sound. Each head has its own stretch, pitch, start, freeze, reverse, scan and stereo outputs. Up to three expanders can be chained, for twelve heads in total.

## Documentation

- [User manual (PDF)](docs/Paulstretch-Manual.pdf)
- [How Paulstretch works (PDF)](docs/How-Paulstretch-Works.pdf): an illustrated, non-technical explanation.

## Building

With the [Rack SDK](https://vcvrack.com/manual/Building#Building-Rack-plugins):

```bash
make RACK_DIR=<path to Rack-SDK> install
```

## Credits

Paulstretch ("Paul's Extreme Sound Stretch") was invented by Nasca Octavian Paul. These modules follow the method of his public-domain [Python version](https://github.com/paulnasca/paulstretch_python). The code is our own; see [PROVENANCE.md](PROVENANCE.md) for how that was checked.

## Licence

GPL-3.0-or-later; see [LICENSE](LICENSE). The panels use components from VCV's Component Library, licensed CC BY-NC 4.0.
