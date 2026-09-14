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

# 從原始碼目錄註冊桌面項目（不安裝套件、不需 root）。
#
# 只是想試用的話用這個；要正式安裝請改用：
#     ./packaging/build-deb.sh && sudo apt install ./dist/stephany-editor_*.deb
#
# 桌面檔名、Icon、StartupWMClass 必須與程式宣告的 app_id 一致，
# 工作列才不會把視窗顯示成 python3（SRS-004 D-01）。
set -euo pipefail

if [ "$(uname -s)" = "Darwin" ]; then
    echo "這是 Linux 的桌面項目註冊腳本。macOS 請用：" >&2
    echo "    ./packaging/build-app.sh --install" >&2
    exit 1
fi

DIR="$(cd "$(dirname "$0")" && pwd)"
APP_ID="stephany-editor"
DEST="$HOME/.local/share/applications/$APP_ID.desktop"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"

mkdir -p "$(dirname "$DEST")" "$ICON_DIR"
cp "$DIR/stephany/resources/$APP_ID.svg" "$ICON_DIR/$APP_ID.svg"

sed "s|^Exec=.*|Exec=$DIR/run.sh %F|" "$DIR/packaging/$APP_ID.desktop" > "$DEST"
chmod 0644 "$DEST"

command -v update-desktop-database >/dev/null 2>&1 &&
    update-desktop-database -q "$HOME/.local/share/applications" || true
# 使用者層級的 hicolor 目錄沒有 index.theme，gtk-update-icon-cache 會報錯。
# 圖示查找本來就會跨 XDG_DATA_DIRS 合併，快取有沒有建都找得到，所以略過即可。
if [ -f "$HOME/.local/share/icons/hicolor/index.theme" ] &&
   command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -f "$HOME/.local/share/icons/hicolor" || true
fi

echo "已安裝：$DEST"
echo "圖示：  $ICON_DIR/$APP_ID.svg"
