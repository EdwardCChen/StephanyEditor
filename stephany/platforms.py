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

"""平台差異的唯一集中處（SRS-005 D-08）。

專案只在三個地方真的需要知道自己跑在哪個作業系統上——字型、設定目錄、
少數快速鍵——與其讓 `sys.platform` 散落在 UI 各處，全部收在這裡，
「這個專案在各平台上到底有幾件事不一樣」才看得出來。

本模組刻意**不 import Qt**，`core/` 才能繼續維持零 UI 相依（NF-01）。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

IS_MAC = sys.platform == "darwin"
IS_WINDOWS = os.name == "nt"
IS_LINUX = not IS_MAC and not IS_WINDOWS


# ======================================================================
# 字型（SRS-005 D-04、BR-MAC-6）
# ======================================================================
# 欄模式的前提是「一個中文字剛好等於兩個半形字」。清單元素是
# (字型家族, 樣式名稱)，樣式為 None 代表用該家族的預設樣式——
# `Osaka` 就是必須指名樣式的例子：預設樣式的比例是 1.5，
# 只有 `Regular-Mono` 是 2.0（BR-MAC-6）。
#
# 清單刻意分成兩段：
#
#   ALIGNED_FONTS   中文確實是半形兩倍寬，欄模式完全正確。測試會逐一量測。
#   FALLBACK_FONTS  一個 CJK 等寬字型都沒有時的退路。至少是等寬、看得下去，
#                   但欄位會歪——狀態列會出現警告，不是默默錯掉。

#: 各平台通用、需要使用者自行安裝的 CJK 等寬字型（最優先）
_PORTABLE_FONTS: tuple[tuple[str, str | None], ...] = (
    ("Noto Sans Mono CJK TC", None),
    ("Noto Sans Mono CJK SC", None),
    ("Sarasa Mono TC", None),
    ("Sarasa Mono SC", None),
)

# macOS 沒有內建 Noto Sans Mono CJK；量測過所有內建等寬字型後，半形寬剛好
# 等於字級一半（也就是中文正好兩倍寬）的只有 Osaka 的 Regular-Mono 樣式。
# Menlo / Monaco / Courier New / Andale Mono / PT Mono 的比例都是 1.66~1.67。
_MAC_ALIGNED = _PORTABLE_FONTS + (("Osaka", "Regular-Mono"),)
_MAC_FALLBACK = (("Menlo", None),)

_LINUX_ALIGNED = _PORTABLE_FONTS + (("WenQuanYi Zen Hei Mono", None),)
_LINUX_FALLBACK = (
    ("Noto Sans Mono", None),
    ("DejaVu Sans Mono", None),
    ("Monospace", None),
)

# Windows 的清單是量出來的（SRS-006 D-W4）：9~24pt、19 個字元（含繁中專用字、
# 假名、全形標點、罕用字）全部剛好 2.000。順序是繁中 → 簡中 → 日文，因為本專案
# 以繁體中文為主。
#
# 兩個陷阱：
#
#   * **不要 P 開頭的變體**（BR-WIN-4）。`PMingLiU` 只比 `MingLiU` 多一個字母，
#     P = proportional，半形字不是固定寬，實測比例 2.13。`MS PGothic` 同理。
#   * **英文名與本地化名都要列**（D-W6）。Qt 在 zh-TW 的 Windows 上兩個都會列出
#     （`MingLiU` 與 `細明體`），其他語系不保證；兩個都寫進來，比在這裡判斷
#     locale 乾淨。
#
# 這些是 Windows 的「語言補充字型」：zh-TW／zh-CN／ja 語系預設就有，乾淨的
# en-US Windows 11 可能一個都沒有——那種機器走下面的退路 + 狀態列警告。
_WINDOWS_ALIGNED = _PORTABLE_FONTS + (
    ("MingLiU", None),
    ("細明體", None),
    ("NSimSun", None),
    ("SimSun", None),
    ("MS Gothic", None),
)
# 一定裝得到，但一個都不合格（實測：Consolas 1.82、Cascadia Mono 1.71、
# Courier New 1.67）。至少是等寬，欄位會歪，狀態列會講。
_WINDOWS_FALLBACK = (
    ("Consolas", None),
    ("Cascadia Mono", None),
    ("Courier New", None),
)

ALIGNED_FONTS: tuple[tuple[str, str | None], ...] = (
    _MAC_ALIGNED if IS_MAC else _WINDOWS_ALIGNED if IS_WINDOWS else _LINUX_ALIGNED
)
FALLBACK_FONTS: tuple[tuple[str, str | None], ...] = (
    _MAC_FALLBACK if IS_MAC else _WINDOWS_FALLBACK if IS_WINDOWS else _LINUX_FALLBACK
)

#: `_pick_font()` 由前往後找第一個裝得到的
PREFERRED_FONTS: tuple[tuple[str, str | None], ...] = ALIGNED_FONTS + FALLBACK_FONTS

#: 字型不合格時，狀態列要建議使用者改用什麼（各平台拿得到的東西不一樣）
FONT_HINT: str = (
    "Osaka Regular-Mono（系統內建）或 Sarasa Mono TC"
    if IS_MAC
    else "細明體（MingLiU，Windows 的中文補充字型）或 Noto Sans Mono CJK"
    if IS_WINDOWS
    else "Noto Sans Mono CJK"
)


# ======================================================================
# 快速鍵（SRS-005 D-05、BR-MAC-4）
# ======================================================================
# Qt 會把可攜寫法的 `Ctrl+X` 在 macOS 解析成 `⌘X`，所以主要的快速鍵表
# 一份就夠，不必也不該再寫一份 macOS 版（BR-MAC-4）。
# 這裡只列「在 macOS 上壓不到或會誤觸」而需要**額外**補一個鍵的動作：
#
#   * F1 / F2 系列：MacBook 預設要一起壓 Fn 才送得出功能鍵
#   * ⌥ + 字母／數字：macOS 鍵盤配置會直接產生字元（⌥C → ç）
#
# 原本的鍵仍然有效，跨平台的肌肉記憶不會斷。
_MAC_EXTRA_SHORTCUTS: dict[str, tuple[str, ...]] = {
    "help": ("Ctrl+?",),  # ⌘? ——macOS 的「說明」慣例鍵
    "bookmark_toggle": ("Ctrl+Shift+M",),  # ⇧⌘M：原 Ctrl+F2
    "bookmark_next": ("Ctrl+Alt+Down",),  # ⌥⌘↓：原 F2
    "bookmark_prev": ("Ctrl+Alt+Up",),  # ⌥⌘↑：原 Shift+F2
    "column_editor": ("Ctrl+Shift+C",),  # ⇧⌘C：原 Alt+C（⌥C 會打出 ç）
}

# Windows 只有一個動作按不到，但成因跟 macOS 不一樣：選單列有 `編碼(&C)`，
# Windows 的選單助憶鍵優先權高於 QAction 的快速鍵，於是 `Alt+C` 被選單吃掉
# （實測：同樣送鍵方式下 Ctrl+N／Ctrl+Shift+B／Alt+0／Alt+1 都會觸發，
# 只有 Alt+C 沒有反應）。補的鍵與 macOS 是同一個，肌肉記憶才不會分岔
# （SRS-006 D-W7、BR-WIN-5）。
#
# F1／F2 在 Windows 上直接按得到，不必跟著 macOS 一起補。
_WINDOWS_EXTRA_SHORTCUTS: dict[str, tuple[str, ...]] = {
    "column_editor": ("Ctrl+Shift+C",),  # 原 Alt+C 被 編碼(&C) 選單搶走
}

EXTRA_SHORTCUTS: dict[str, tuple[str, ...]] = (
    _MAC_EXTRA_SHORTCUTS if IS_MAC else _WINDOWS_EXTRA_SHORTCUTS if IS_WINDOWS else {}
)


def extra_shortcuts(action: str) -> tuple[str, ...]:
    """某個動作在本平台要額外綁定的快速鍵；沒有就回傳空 tuple。"""
    return EXTRA_SHORTCUTS.get(action, ())


#: 說明視窗裡那一段替代鍵的標題與理由。各平台補鍵的**原因不一樣**，
#: 文字寫死在 UI 裡的話，Windows 使用者會讀到「不必壓 Fn」這種跟他無關的話。
EXTRA_SHORTCUTS_TITLE: str = (
    "功能鍵按不到時（不必壓 Fn）"
    if IS_MAC
    else "被系統或選單搶走的鍵，另有替代鍵"
    if IS_WINDOWS
    else ""
)

EXTRA_SHORTCUTS_REASON: str = (
    "原本的鍵仍然有效；⌥+C 會直接打出 ç，所以也多給了一個。"
    if IS_MAC
    else "原本的鍵仍然有效；Alt+C 會被選單列的「編碼(&C)」助憶鍵吃掉，所以多給了一個。"
    if IS_WINDOWS
    else ""
)

#: 只有 Linux 需要這句：GNOME 預設會把 Alt+拖曳拿去搬視窗。
STICKY_MODE_HINT: str = "（GNOME 會攔截 Alt+拖曳時就用這個）" if IS_LINUX else ""


#: 說明文字裡的修飾鍵寫法。macOS 使用者看的是符號，不是英文字。
MODIFIER_NAMES: dict[str, str] = (
    {"Ctrl": "⌘", "Alt": "⌥", "Shift": "⇧", "Meta": "⌃"}
    if IS_MAC
    else {"Ctrl": "Ctrl", "Alt": "Alt", "Shift": "Shift", "Meta": "Meta"}
)


def mod(name: str) -> str:
    """單獨提到某個修飾鍵時的顯示字樣，例如「按住 Alt 拖曳」。"""
    return MODIFIER_NAMES.get(name, name)


# ======================================================================
# 應用程式身分（SRS-006 D-W1、F-WIN-01、BR-WIN-3）
# ======================================================================
from . import BUNDLE_ID  # noqa: E402  放在這裡才看得出它屬於「身分」這一段

#: Windows 用來辨識應用程式的識別碼。與 macOS 的 `CFBundleIdentifier`
#: 同一個字串（BR-WIN-3）。
APP_USER_MODEL_ID = BUNDLE_ID


def set_app_user_model_id(app_id: str = APP_USER_MODEL_ID) -> bool:
    """向 Windows 宣告這個程序的身分；非 Windows 平台什麼都不做。

    沒有宣告時，Windows 會從**執行檔路徑**推導身分——而從原始碼執行時，
    所有 Python 程式的執行檔路徑都是同一個 `pythonw.exe`，於是工作列會把
    本程式跟其他 Python 程式分到同一組，工作管理員也顯示成 `pythonw`。

    這是 SRS-004 D-01（Dock 顯示成 `python3`）與 SRS-005 D-01（選單列顯示成
    `main.py`）在 Windows 上的第三個版本：**應用程式身分要由作業系統認得的
    地方宣告，不是由程式自己喊。** 安裝版另外還有自己的
    `stephany-editor.exe`（D-W1），兩者一起才完整。

    回傳有沒有真的設定成功。設不起來只是工作列分組不理想，不該讓程式起不來，
    所以失敗就安靜回傳 False。
    """
    if not IS_WINDOWS:
        return False
    try:
        import ctypes

        hr = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except (AttributeError, OSError):  # 非 CPython、或 shell32 不在
        return False
    return hr == 0


# ======================================================================
# 設定目錄（SRS-005 D-06）
# ======================================================================
#: 想在多台機器間共用巨集的人，把這個環境變數指到雲端同步目錄即可
CONFIG_DIR_ENV = "STEPHANY_CONFIG_DIR"

APP_DIR_NAME = "StephanyEditor"


def config_dir() -> Path:
    """使用者設定與巨集的存放目錄，遵循各平台自己的慣例。"""
    override = os.environ.get(CONFIG_DIR_ENV)
    if override:
        return Path(override)
    if IS_MAC:
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    if IS_WINDOWS:
        base = os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_DIR_NAME
    base = os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
    return Path(base) / APP_DIR_NAME
