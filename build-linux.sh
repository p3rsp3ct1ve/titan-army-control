#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 -m venv --copies --system-site-packages .venv-linux
.venv-linux/bin/python -m pip install --upgrade pip pyinstaller
.venv-linux/bin/python -m PyInstaller --noconfirm --clean TitanArmyControl-linux.spec
echo "Built dist/TitanArmyControl-linux"
