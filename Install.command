#!/bin/bash
# Double-click installer for the GitHub Release zip.
cd "$(dirname "$0")"
bash scripts/install_from_source.sh
echo ""
read -r -p "Press Enter to close…"
