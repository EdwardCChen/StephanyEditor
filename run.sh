#!/usr/bin/env bash
# Stephany Editor — 支援中文欄（直行）模式的文字編輯器
# Copyright (C) 2026 Edward Chen
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

# Stephany Editor 啟動腳本。第一次執行會自動建立虛擬環境並安裝相依套件。
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"

if [ ! -x .venv/bin/python ]; then
    # macOS 內建的 /usr/bin/python3 是 3.9，建得起 venv 但裝不了 PySide6，
    # 錯誤訊息又看不出真正原因，所以先擋在這裡（SRS-005）。
    "$PY" - <<'PYCHECK' || exit 1
import sys
if sys.version_info < (3, 10):
    sys.exit(
        f"錯誤：需要 Python 3.10 以上，目前的 python3 是 {sys.version.split()[0]}。\n"
        "      裝一個新版再用 PYTHON=/路徑/python3 ./run.sh 指定即可。"
    )
PYCHECK
    echo "第一次執行：建立虛擬環境中..."
    "$PY" -m venv .venv
    .venv/bin/pip install --quiet --upgrade pip
    .venv/bin/pip install --quiet -r requirements.txt
fi

exec .venv/bin/python -m stephany "$@"
