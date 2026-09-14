#!/usr/bin/env bash
# 把 Stephany Editor 加進 Ubuntu 的應用程式選單。
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/.local/share/applications/stephany-editor.desktop"
mkdir -p "$(dirname "$DEST")"
cat > "$DEST" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Stephany Editor
Comment=支援中文欄（直行）模式的文字編輯器
Exec=$DIR/run.sh %F
Icon=accessories-text-editor
Terminal=false
Categories=Utility;TextEditor;Development;
MimeType=text/plain;text/x-python;text/x-csrc;application/json;
StartupNotify=true
DESKTOP
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
echo "已安裝：$DEST"
