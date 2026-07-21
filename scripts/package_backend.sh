#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

npm --prefix frontend install
npm --prefix frontend run build

python3 -m pip install -r requirements.txt -r requirements-packaging.txt
python3 -m PyInstaller \
  --name AutoPaperReaderServer \
  --clean \
  --noconfirm \
  --add-data "frontend/dist:frontend/dist" \
  --add-data "scripts:scripts" \
  --collect-submodules backend \
  backend/app/desktop_server.py
