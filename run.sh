#!/usr/bin/env bash
# Stephany Editor 啟動腳本。第一次執行會自動建立虛擬環境並安裝相依套件。
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
    echo "第一次執行：建立虛擬環境中..."
    python3 -m venv .venv
    .venv/bin/pip install --quiet --upgrade pip
    .venv/bin/pip install --quiet -r requirements.txt
fi

exec .venv/bin/python -m stephany "$@"
