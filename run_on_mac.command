#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is required. Install it from https://www.python.org/downloads/"
  read -r -p "Press Enter to close..."
  exit 1
fi

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python download_physics_0625.py --workers 3

echo
echo "Completed. The downloaded folder and ZIP are beside this script."
read -r -p "Press Enter to close..."
