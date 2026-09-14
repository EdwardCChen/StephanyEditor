#!/usr/bin/env bash
# 建置 Stephany Editor 的 .deb 安裝檔（SRS-004 D-03、F-PK-07）。
#
# 刻意只用 dpkg-deb 直接組出二進位套件，不經 debhelper：
# 建構主機不必安裝 debhelper / dh-python / devscripts（那些要 root 權限），
# 任何 Ubuntu 機器 clone 下來就能建，也不需要 sudo。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PKG="stephany-editor"
MAINTAINER="Edward Chen <edwardcchen@gmail.com>"
HOMEPAGE="https://github.com/EdwardCChen/StephanyEditor"

# BR-PK-1：版本號只有一個來源
VERSION="$(python3 -c "
import re, pathlib
text = pathlib.Path('stephany/__init__.py').read_text(encoding='utf-8')
print(re.search(r'__version__ = \"([^\"]+)\"', text).group(1))
")"

# 產生圖示需要 PySide6；優先用專案的 venv，其次系統的
if [ -x "$ROOT/.venv/bin/python" ]; then
    PY="$ROOT/.venv/bin/python"
else
    PY="python3"
fi
if ! "$PY" -c "import PySide6.QtSvg" 2>/dev/null; then
    echo "錯誤：找不到 PySide6（產生圖示需要）。請先執行 ./run.sh 建立 .venv，" >&2
    echo "      或安裝 python3-pyside6.qtsvg。" >&2
    exit 1
fi

BUILD="$(mktemp -d)"
trap 'rm -rf "$BUILD"' EXIT
STAGE="$BUILD/$PKG"

echo "==> 建置 $PKG $VERSION"

# --- 程式碼本體（BR-PK-2：不含 .venv、__pycache__、測試、開發腳本）---
install -d "$STAGE/usr/share/$PKG/stephany"
tar -c -C "$ROOT" \
    --exclude='__pycache__' --exclude='*.pyc' --exclude='*.pyo' \
    stephany | tar -x -C "$STAGE/usr/share/$PKG"

# --- 啟動器 ---
install -D -m 0755 packaging/stephany-editor.launcher "$STAGE/usr/bin/$PKG"

# --- 桌面項目（F-PK-03、F-PK-04）---
install -D -m 0644 packaging/stephany-editor.desktop \
    "$STAGE/usr/share/applications/$PKG.desktop"

# --- 圖示（D-06）---
"$PY" packaging/make-icons.py stephany/resources/stephany-editor.svg \
    "$STAGE/usr/share/icons/hicolor"
find "$STAGE/usr/share/icons" -type f -exec chmod 0644 {} +

# --- 文件 ---
install -D -m 0644 README.md "$STAGE/usr/share/doc/$PKG/README.md"
install -d "$STAGE/usr/share/doc/$PKG"
cat > "$STAGE/usr/share/doc/$PKG/copyright" <<EOF
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: Stephany Editor
Source: $HOMEPAGE

Files: *
Copyright: $(date +%Y) Edward Chen
License: 尚未宣告
 本專案尚未選定授權條款。若要對外散布，請先於原始碼庫加入 LICENSE 檔
 並同步更新這個檔案。
EOF
printf '%s (%s) unstable; urgency=low\n\n  * 由 packaging/build-deb.sh 產生。變更請見 git 歷史：\n    %s\n\n -- %s  %s\n' \
    "$PKG" "$VERSION" "$HOMEPAGE" "$MAINTAINER" "$(date -R)" \
    | gzip -9n > "$STAGE/usr/share/doc/$PKG/changelog.Debian.gz"
chmod 0644 "$STAGE/usr/share/doc/$PKG/changelog.Debian.gz"

# --- 套件中繼資料 ---
INSTALLED_KB="$(du -sk "$STAGE" | cut -f1)"
install -d "$STAGE/DEBIAN"
cat > "$STAGE/DEBIAN/control" <<EOF
Package: $PKG
Version: $VERSION
Section: editors
Priority: optional
Architecture: all
Depends: python3 (>= 3.10), python3-pyside6.qtcore, python3-pyside6.qtgui, python3-pyside6.qtwidgets
Recommends: fonts-noto-cjk
Maintainer: $MAINTAINER
Homepage: $HOMEPAGE
Installed-Size: $INSTALLED_KB
Description: 支援中文欄（直行）模式的文字編輯器
 Notepad++ 風格的編輯器，重點是讓欄（直行）模式在中英文混排時真的可用。
 .
 所有矩形運算以「顯示欄位」而非字元索引為單位（一個中文字算兩欄），
 矩形邊界切到半個全形字時該字降級為兩個空白，刪除或插入後版面仍然對齊。
 .
 另含書籤、巨集錄製（錄語意命令而非鍵盤按鍵，中文輸入法打的字也錄得到）、
 程式碼摺疊、正規表示式尋找取代，以及 Big5 / UTF-8 / GB18030 編碼偵測。
EOF

# BR-PK-3：安裝與移除後更新桌面資料庫與圖示快取
cat > "$STAGE/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database -q /usr/share/applications || true
    fi
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -q -f /usr/share/icons/hicolor || true
    fi
fi
exit 0
EOF
cat > "$STAGE/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database -q /usr/share/applications || true
    fi
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -q -f /usr/share/icons/hicolor || true
    fi
fi
exit 0
EOF
chmod 0755 "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/postrm"

# md5sums（dpkg --verify 與完整性檢查用）
( cd "$STAGE" && find . -path ./DEBIAN -prune -o -type f -print0 \
    | xargs -0 md5sum | sed 's|\./||' > DEBIAN/md5sums )
chmod 0644 "$STAGE/DEBIAN/md5sums"

# 正規化權限：建構者的 umask（常見的 002）會讓目錄變成 775、檔案 664，
# 不符 Debian 政策。統一成 755/644 後再把該執行的補回來。
find "$STAGE" -type d -exec chmod 0755 {} +
find "$STAGE" -type f -exec chmod 0644 {} +
chmod 0755 "$STAGE/usr/bin/$PKG" "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/postrm"

# --- 打包（BR-PK-4：檔案擁有者一律 root:root）---
mkdir -p "$ROOT/dist"
DEB="$ROOT/dist/${PKG}_${VERSION}_all.deb"
dpkg-deb --build --root-owner-group "$STAGE" "$DEB" >/dev/null

echo "==> 完成：$DEB"
dpkg-deb --info "$DEB" | sed -n '2,12p'
echo "安裝：sudo apt install $DEB"
