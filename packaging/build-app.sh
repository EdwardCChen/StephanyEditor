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

# 建置 Stephany Editor 的 macOS .app（SRS-005 D-01 ~ D-03、F-MAC-10）。
#
# 刻意只用系統內建的 python3 -m venv / iconutil / hdiutil，不經 py2app 或
# PyInstaller —— 與 SRS-004 不用 debhelper 是同一個取捨：建構主機不必安裝
# 額外的打包工具，也不需要 root。
#
# 用法：
#   ./packaging/build-app.sh                 建到 dist/
#   ./packaging/build-app.sh --install       建完後安裝到 /Applications
#   ./packaging/build-app.sh --dmg           另外產生 .dmg
#   PYTHON=/opt/homebrew/bin/python3.13 ./packaging/build-app.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

APP_ID="stephany-editor"
APP_NAME="Stephany Editor"
BUNDLE_ID="io.github.edwardcchen.stephany-editor"
COPYRIGHT_HOLDER="Edward Chen"
COPYRIGHT_YEAR="2026"
INSTALL_DIR="${INSTALL_DIR:-/Applications}"

DO_INSTALL=0
DO_DMG=0
for arg in "$@"; do
    case "$arg" in
        --install) DO_INSTALL=1 ;;
        --dmg) DO_DMG=1 ;;
        -h|--help) sed -n '18,27p' "$0"; exit 0 ;;
        *) echo "未知參數：$arg" >&2; exit 2 ;;
    esac
done

if [ "$(uname -s)" != "Darwin" ]; then
    echo "錯誤：這個腳本只能在 macOS 上執行（Linux 請用 build-deb.sh）。" >&2
    exit 1
fi

# BR-MAC-1 / BR-PK-1：版本號只有一個來源
VERSION="$(/usr/bin/python3 -c "
import re, pathlib
text = pathlib.Path('stephany/__init__.py').read_text(encoding='utf-8')
print(re.search(r'__version__ = \"([^\"]+)\"', text).group(1))
")"

# 建構用的直譯器。這一版 Python 的標準函式庫就是 .app 之後執行時會用的那一份
# （D-03 的取捨），所以刻意印出來讓人看見。
PY="${PYTHON:-python3}"
if ! command -v "$PY" >/dev/null 2>&1; then
    echo "錯誤：找不到 ${PY}。請安裝 Python 3.10+ 或設定 PYTHON=..." >&2
    exit 1
fi
"$PY" - <<'PYCHECK' || exit 1
import sys
if sys.version_info < (3, 10):
    sys.exit(
        f"錯誤：需要 Python 3.10 以上，目前是 {sys.version.split()[0]}。\n"
        "      macOS 內建的 /usr/bin/python3 是 3.9，請用 Homebrew 或 "
        "python.org 的版本，再以 PYTHON=... 指定。"
    )
PYCHECK

APP="$ROOT/dist/$APP_NAME.app"
CONTENTS="$APP/Contents"

echo "==> 建置 $APP_NAME $VERSION"
echo "    直譯器：$("$PY" -c 'import sys; print(sys.executable, sys.version.split()[0])')"

rm -rf "$APP"
mkdir -p "$ROOT/dist"

# --- venv 直接建在 Contents/ 之下（D-02）---
# 直譯器最後會放在 Contents/MacOS/，而 Python 找 venv 標記時看的是
# 「執行檔目錄的上一層有沒有 pyvenv.cfg」——剛好就是 Contents/pyvenv.cfg。
"$PY" -m venv --copies "$CONTENTS"
"$CONTENTS/bin/python3" -m pip install --quiet --upgrade pip
"$CONTENTS/bin/python3" -m pip install --quiet -r requirements.txt

# --- D-01：Contents/MacOS/ 底下放的是直譯器本體，不是 shell 啟動器 ---
mkdir -p "$CONTENTS/MacOS" "$CONTENTS/Resources"
cp "$CONTENTS/bin/python3" "$CONTENTS/MacOS/$APP_ID"
chmod 0755 "$CONTENTS/MacOS/$APP_ID"

# --- 程式碼本體（BR-MAC-2：不含 __pycache__、測試、開發腳本）---
mkdir -p "$CONTENTS/Resources/app"
tar -c -C "$ROOT" \
    --exclude='__pycache__' --exclude='*.pyc' --exclude='*.pyo' \
    stephany | tar -x -C "$CONTENTS/Resources/app"

# --- 進入點：直譯器被無參數啟動，只能掛在 sitecustomize（D-02）---
SITE="$(echo "$CONTENTS"/lib/python*/site-packages)"
install -m 0644 packaging/stephany-editor.bootstrap "$SITE/sitecustomize.py"

# --- 終端機進入點（F-MAC-05）---
# BSD 的 install 沒有 GNU 的 -D，目錄要自己先建
mkdir -p "$CONTENTS/Resources/bin"
install -m 0755 packaging/stephany-editor.cli "$CONTENTS/Resources/bin/$APP_ID"

# --- 圖示（SRS-004 D-06：單一 SVG 產生所有尺寸）---
ICONSET="$(mktemp -d)/$APP_ID.iconset"
mkdir -p "$ICONSET"
"$CONTENTS/bin/python3" packaging/make-icons.py \
    stephany/resources/stephany-editor.svg "$ICONSET" --iconset
iconutil -c icns -o "$CONTENTS/Resources/$APP_ID.icns" "$ICONSET"
rm -rf "$(dirname "$ICONSET")"

# --- Info.plist（BR-MAC-1：版本號由樣板填入，不手動同步）---
sed -e "s|@VERSION@|$VERSION|g" \
    -e "s|@BUNDLE_ID@|$BUNDLE_ID|g" \
    -e "s|@COPYRIGHT@|Copyright © $COPYRIGHT_YEAR $COPYRIGHT_HOLDER|g" \
    packaging/Info.plist > "$CONTENTS/Info.plist"
chmod 0644 "$CONTENTS/Info.plist"
printf 'APPL????' > "$CONTENTS/PkgInfo"

# --- 文件與授權 ---
install -m 0644 README.md "$CONTENTS/Resources/README.md"
install -m 0644 LICENSE "$CONTENTS/Resources/LICENSE"

# --- BR-MAC-2：清掉建構期才需要的東西 ---
# bin/ 與 include/ 是 venv 給人用的入口，bundle 的進入點是 Contents/MacOS/，
# 兩者都用不到；pip / setuptools 留著只會讓 .app 變大也變雜。
rm -rf "$SITE"/pip "$SITE"/pip-*.dist-info \
       "$SITE"/setuptools "$SITE"/setuptools-*.dist-info \
       "$SITE"/pkg_resources "$SITE"/_distutils_hack "$SITE"/distutils-precedence.pth
rm -rf "$CONTENTS/bin" "$CONTENTS/include"
# venv 會在自己的根目錄放一個 .gitignore；留著會讓 codesign 認為 bundle 裡
# 有「沒簽章的子元件」而整個簽章失敗
rm -f "$CONTENTS/.gitignore"
find "$CONTENTS" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$CONTENTS" -name '*.pyc' -delete 2>/dev/null || true

# 這裡刻意不做程式碼簽章（連 ad-hoc 都不做）。
# `codesign` 會把 bundle 內所有非程式碼的檔案當成「未簽章的子元件」而整個
# 失敗，而 D-02 要求 `Contents/pyvenv.cfg` 必須存在——那正是它不接受的東西。
# 本機自建自用的 .app 不需要簽章也能跑（SRS-005 §6）；若要把 .dmg 拿到別台
# Mac，收到端解除隔離即可：
#     xattr -dr com.apple.quarantine "/Applications/Stephany Editor.app"

SIZE="$(du -sh "$APP" | cut -f1)"
# 變數後面緊接著中文標點時一定要加大括號：macOS 內建的是 bash 3.2，在 UTF-8
# locale 下會把多位元組字元的第一個位元組吃進變數名稱，變成 unbound variable。
echo "==> 完成：${APP}（${SIZE}）"

if [ "$DO_INSTALL" = 1 ]; then
    rm -rf "$INSTALL_DIR/$APP_NAME.app"
    ditto "$APP" "$INSTALL_DIR/$APP_NAME.app"
    echo "==> 已安裝：$INSTALL_DIR/$APP_NAME.app"
    echo "    終端機指令（F-MAC-05）："
    echo "      sudo ln -sf '$INSTALL_DIR/$APP_NAME.app/Contents/Resources/bin/$APP_ID' /usr/local/bin/$APP_ID"
fi

if [ "$DO_DMG" = 1 ]; then
    DMG="$ROOT/dist/${APP_ID}-${VERSION}.dmg"
    rm -f "$DMG"
    hdiutil create -quiet -volname "$APP_NAME" -srcfolder "$APP" \
        -ov -format UDZO "$DMG"
    echo "==> 完成：$DMG"
fi
