#!/bin/bash
# List where sound is in a take, so cuts can land in pauses.
#   qa/speech.sh takes/take1.mov [threshold_db=-40] [min_gap=0.15]
set -euo pipefail
ffmpeg -hide_banner -i "$1" -vn -af "silencedetect=n=${2:--40}dB:d=${3:-0.15}" -f null - 2>&1 \
  | grep -oE "silence_(start|end): [0-9.]+" | awk '
      /end/   { s = $2 }
      /start/ { if (s != "") printf "sound %7.2f -> %7.2f  (%.2fs)\n", s, $2, $2 - s; s = "" }
      END     { if (s != "") printf "sound %7.2f -> end\n", s }'
