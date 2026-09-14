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

# Windows 尚未實機驗證（SRS-005 §6 範圍外），先留分支。
# MS Gothic／新宋体／細明體都是中日文的全形等寬字型。
_WINDOWS_ALIGNED = _PORTABLE_FONTS + (
    ("MS Gothic", None),
    ("NSimSun", None),
    ("MingLiU", None),
)
_WINDOWS_FALLBACK = (("Consolas", None),)

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
    else "Noto Sans Mono CJK 或細明體"
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

EXTRA_SHORTCUTS: dict[str, tuple[str, ...]] = _MAC_EXTRA_SHORTCUTS if IS_MAC else {}


def extra_shortcuts(action: str) -> tuple[str, ...]:
    """某個動作在本平台要額外綁定的快速鍵；沒有就回傳空 tuple。"""
    return EXTRA_SHORTCUTS.get(action, ())


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
