#!/bin/bash
# Reruns every comparison. Usage: bash run_all.sh UPSTREAM_DIR [OUR_SRC_DIR] [RACK_SDK_DIR] CONTROL_FILE
# Output goes to stdout; tee it to a file if you want to keep it.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
if [ $# -lt 4 ]; then echo "usage: bash run_all.sh UPSTREAM_DIR OUR_SRC_DIR RACK_SDK_DIR CONTROL_FILE (see README.md)" >&2; exit 2; fi
UP="$1"
OURS_DIR="$2"
SDK="$3"
CONTROL="$4"
CHK=(python3 -I "$HERE/simcheck.py")

OURS=()
for f in PaulstretchCore.hpp Paulstretch.cpp PaulstretchHeads.cpp PaulstretchExpander.hpp AudioFile.hpp PanelText.hpp; do
  OURS+=("$OURS_DIR/$f")
done
PAUL=()
while IFS= read -r f; do PAUL+=("$f"); done < <(find "$UP/paulstretch_cpp" \( -name '*.cpp' -o -name '*.h' \) -not -path '*/contrib/*' | sort)
KISS=()
while IFS= read -r f; do KISS+=("$f"); done < <(find "$UP/paulstretch_cpp/contrib" \( -name '*.c' -o -name '*.h' \) | sort)
RACKDSP=()
while IFS= read -r f; do RACKDSP+=("$f"); done < <(find "$SDK/include/dsp" -name '*.hpp' | sort)
RACKDSP+=("$SDK/include/dsp/../../dep/include/pffft.h")
while IFS= read -r f; do RACKDSP+=("$f"); done < <(find "$SDK/dep/include/speex" -name '*.h' | sort)
PAULCORE=("$UP/paulstretch_cpp/Stretch.cpp" "$UP/paulstretch_cpp/Stretch.h" "$UP/paulstretch_cpp/ProcessedStretch.cpp" "$UP/paulstretch_cpp/ProcessedStretch.h" "$UP/paulstretch_cpp/Player.cpp" "$UP/paulstretch_cpp/Control.cpp")

echo "### 1. Positive control (disguised copy) vs paulstretch_cpp"
"${CHK[@]}" --label "control vs paulstretch_cpp" --ours "$CONTROL" --theirs "${PAUL[@]}" --show-runs 6 --raw

echo; echo "### 2. Ours vs paulstretch_cpp (GPL)"
"${CHK[@]}" --label "ours vs paulstretch_cpp" --ours "${OURS[@]}" --theirs "${PAUL[@]}" --show-runs 5 --raw --stop-ids-from "${RACKDSP[@]}" --json "$HERE/ours_vs_paul.json"

echo; echo "### 3. Negative baseline: ours vs Rack SDK dsp + pffft/speex headers"
"${CHK[@]}" --label "ours vs Rack SDK dsp" --ours "${OURS[@]}" --theirs "${RACKDSP[@]}" --show-runs 3 --json "$HERE/ours_vs_rack.json"

echo; echo "### 4. Negative baseline: ours vs kiss_fft (third-party C FFT bundled in paulstretch_cpp/contrib, BSD)"
"${CHK[@]}" --label "ours vs kiss_fft" --ours "${OURS[@]}" --theirs "${KISS[@]}" --show-runs 2

echo; echo "### 5. Negative baseline, reversed: Paul's core files vs Rack SDK dsp (two unrelated codebases)"
"${CHK[@]}" --label "paul core vs Rack SDK dsp" --ours "${PAULCORE[@]}" --theirs "${RACKDSP[@]}" --show-runs 2
