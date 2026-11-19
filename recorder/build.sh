#!/bin/bash
# Builds the recorder (macOS 15+, Xcode command line tools).
set -euo pipefail
cd "$(dirname "$0")"
swiftc -O record.swift -o record
echo "built $(pwd)/record"
# the desktop driver (native apps instead of a browser page)
swiftc -O ../drive/desktop.swift -o ../drive/desktop
echo "built $(cd ../drive && pwd)/desktop"
