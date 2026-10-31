#!/bin/bash
# Makes ./ext: a copy of Sawt's extension for recording.
#   prepare.sh /path/to/sawt/extension
# One change, only for the recording: host access to every site. The real extension gets page
# access from a keypress or click (activeTab), and automation cannot press the browser's own
# shortcuts. Everything the viewer sees and hears is the unchanged extension.
set -euo pipefail
SRC=${1:?usage: prepare.sh /path/to/sawt/extension}
cd "$(dirname "$0")"
rm -rf ext && cp -R "$SRC" ext
python3 - <<'PY'
import json
m = json.load(open("ext/manifest.json"))
m["host_permissions"].append("<all_urls>")
json.dump(m, open("ext/manifest.json", "w"), indent=2)
PY
echo "prepared $(pwd)/ext"
