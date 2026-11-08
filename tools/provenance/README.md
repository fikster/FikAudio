# Paulstretch similarity check

Token-based comparison (MOSS/JPlag style) of the plugin's Paulstretch sources
against Nasca Octavian Paul's GPL-2 `paulstretch_cpp`, with calibration runs.

## Files

- `simcheck.py`: the checker. Pure Python 3, no dependencies. It only reads the
  files you name. `python3 -I simcheck.py --help` for options.
- `run_all.sh`: reruns every comparison (positive control, ours vs Paul,
  three negative baselines) and prints the tables.
- The results of the original run are summarised in `PROVENANCE.md` at the
  top of the repository. A run also writes `ours_vs_paul.json` and
  `ours_vs_rack.json` here, with the per-pair numbers.

## Rerun

    git clone --depth 1 https://github.com/paulnasca/paulstretch_cpp    <EMPTY_DIR>/paulstretch_cpp
    git clone --depth 1 https://github.com/paulnasca/paulstretch_python <EMPTY_DIR>/paulstretch_python
    bash run_all.sh <EMPTY_DIR> ../../src <RACK_SDK_DIR> <CONTROL_FILE> > results.txt

`<CONTROL_FILE>` is the positive control (see below), kept outside the
repository. Upstream commits
compared: paulstretch_cpp 7f5c399 (2013-11-05), paulstretch_python 0d4e7a0
(2014-12-20). Don't build or run the upstream code; it is only read.

## What the numbers mean

Pass 1 removes comments and preprocessor lines, maps every identifier to `ID`
and every literal to `LIT`, keeps keywords and operators, and hashes k-token
windows (k = 12 and 20), winnowed with window 4.

- `fp%`: share of our winnowed fingerprints that also appear among theirs.
- `cov%`: share of our tokens inside some k-gram that occurs anywhere in theirs.
- `LCR`: longest common normalised token run, with line ranges on both sides.
- `*ALL*` rows: our file against all their files together.
- `run` lines: the longest non-overlapping common runs, shown with our raw
  tokens so they can be judged by eye.

Pass 2 (`--raw`) lists shared identifiers not found in a stoplist or in the
baseline corpus, shared comment word 6-grams, and shared numeric constants that
aren't small integers, powers of two or round numbers.

`--show-covered K` prints every region of our file covered by K-grams found in
theirs.

Read the numbers only against the controls in the same run: generic C++ (for
loops over arrays, resize calls) gives about 10% fp / 25% cov at k = 12 between
unrelated code, so only clear excess over that, long runs (40+ tokens) or
shared distinctive constants or comments mean anything.

## Positive control

The disguised copy used as the positive control is not kept in this
repository: it is derived from GPL-2 code. To recreate one, take a few
non-trivial functions from paulstretch_cpp, rename every identifier, reformat
and reorder independent statements, save it outside the repository, and pass
its path as the fourth argument to `run_all.sh`.
