#!/bin/bash
# Builds the recorder (macOS 15+, Xcode command line tools).
set -euo pipefail
cd "$(dirname "$0")"
swiftc -O record.swift -o record
echo "built $(pwd)/record"
