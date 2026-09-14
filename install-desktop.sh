#!/usr/bin/env bash
# 從原始碼目錄註冊桌面項目（不安裝套件、不需 root）。
#
# 只是想試用的話用這個；要正式安裝請改用：
#     ./packaging/build-deb.sh && sudo apt install ./dist/stephany-editor_*.deb
#
# 桌面檔名、Icon、StartupWMClass 必須與程式宣告的 app_id 一致，
# 工作列才不會把視窗顯示成 python3（SRS-004 D-01）。
set -euo pipefail
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
