#!/bin/bash
# Contact sheet of a rendered video at the given output times, plus its length and loudness.
#   qa/sheet.sh renders/demo.mp4 0.8,3.3,6,12 [sheet.png]
set -euo pipefail
V=$1; OUT=${3:-${V%.*}-sheet.png}
TMP=$(mktemp -d); i=0
for t in ${2//,/ }; do
  ffmpeg -hide_banner -loglevel error -y -ss "$t" -i "$V" -frames:v 1 -vf scale=360:-2 "$TMP/$(printf %03d $i).png"
  i=$((i + 1))
done
cols=$(( i < 6 ? i : 6 )); rows=$(( (i + cols - 1) / cols ))
ffmpeg -hide_banner -loglevel error -y -framerate 1 -i "$TMP/%03d.png" -vf "tile=${cols}x${rows}:padding=6:color=white" -frames:v 1 "$OUT"
rm -rf "$TMP"
echo "sheet    $OUT"
printf "length   %ss\n" "$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$V")"
ffmpeg -hide_banner -i "$V" -af ebur128 -f null - 2>&1 | awk '/Integrated loudness/{f=1} f && /I:/{print "loudness", $2, $3; exit}'
