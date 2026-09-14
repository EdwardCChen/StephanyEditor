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

"""平台差異模組的測試（SRS-005 D-04 ~ D-08、NF-01）。

本檔刻意不 import PySide6，才能在 CI 的「核心邏輯（無 Qt）」job 裡跑——
這同時也是 NF-01「平台判斷不得把 Qt 相依帶進 core」的持續驗證。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from stephany import platforms

ROOT = Path(__file__).resolve().parent.parent
PLATFORMS_SRC = (ROOT / "stephany" / "platforms.py").read_text(encoding="utf-8")
MAINWINDOW_SRC = (ROOT / "stephany" / "ui" / "mainwindow.py").read_text(encoding="utf-8")


# -- NF-01：平台模組不得把 Qt 拖進來 ----------------------------------
def test_nf_01_the_platform_module_does_not_import_qt():
    """core/ 透過這個模組取得設定目錄；它一旦相依 Qt，core 就跟著髒了。"""
    assert "PySide6" not in PLATFORMS_SRC
    assert "PyQt" not in PLATFORMS_SRC


def test_d_08_platform_checks_live_in_one_place():
    """`sys.platform` 只能出現在 platforms.py，不得散落各處。"""
    offenders = []
    for path in sorted((ROOT / "stephany").rglob("*.py")):
        if path.name == "platforms.py":
            continue
        text = path.read_text(encoding="utf-8")
        if "sys.platform" in text or "platform.system()" in text:
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, f"平台判斷應集中在 platforms.py：{offenders}"


def test_exactly_one_platform_flag_is_true():
    flags = [platforms.IS_MAC, platforms.IS_WINDOWS, platforms.IS_LINUX]
    assert sum(1 for f in flags if f) == 1


# -- D-04 / BR-MAC-6：字型清單 ---------------------------------------
def test_preferred_fonts_are_family_and_style_pairs():
    """只記家族名稱是不夠的——Osaka 的預設樣式比例是 1.5，不是 2。"""
    for entry in platforms.PREFERRED_FONTS:
        family, style = entry
        assert isinstance(family, str) and family
        assert style is None or isinstance(style, str)


def test_br_mac_6_the_macos_list_names_the_osaka_mono_style():
    assert ("Osaka", "Regular-Mono") in platforms._MAC_ALIGNED
    # 只寫家族名稱會挑到比例 1.5 的那個樣式，欄模式就歪了
    assert ("Osaka", None) not in platforms._MAC_ALIGNED


def test_d_04_macos_has_an_aligned_font_that_needs_no_installation():
    """macOS 沒有 Noto Sans Mono CJK，所以對齊清單裡必須有系統內建的選項。"""
    assert ("Osaka", "Regular-Mono") in platforms._MAC_ALIGNED


def test_aligned_fonts_are_tried_before_the_fallbacks():
    """退路只是「至少是等寬」，會歪；有對得齊的就不該用到它。"""
    n = len(platforms.ALIGNED_FONTS)
    assert platforms.PREFERRED_FONTS[:n] == platforms.ALIGNED_FONTS
    assert platforms.PREFERRED_FONTS[n:] == platforms.FALLBACK_FONTS


def test_portable_fonts_come_before_the_platform_specific_ones():
    """使用者自己裝的 CJK 等寬字型比系統內建的優先。"""
    for fonts in (
        platforms._MAC_ALIGNED,
        platforms._LINUX_ALIGNED,
        platforms._WINDOWS_ALIGNED,
    ):
        assert fonts[: len(platforms._PORTABLE_FONTS)] == platforms._PORTABLE_FONTS


def test_no_font_appears_in_both_tiers():
    assert not set(platforms.ALIGNED_FONTS) & set(platforms.FALLBACK_FONTS)


def test_the_font_warning_names_something_available_on_this_platform():
    assert platforms.FONT_HINT
    if platforms.IS_MAC:
        assert "Osaka" in platforms.FONT_HINT


# -- D-05 / BR-MAC-4：快速鍵 -----------------------------------------
def test_br_mac_4_only_macos_adds_extra_shortcuts():
    """跨平台的鍵表只有一份；macOS 只能「多綁一個」，不得另建一套。"""
    if not platforms.IS_MAC:
        assert platforms.EXTRA_SHORTCUTS == {}


def test_every_extra_shortcut_belongs_to_a_real_action():
    """漏改 mainwindow 的 action_id 時，這個測試會抓到。"""
    for action_id in platforms._MAC_EXTRA_SHORTCUTS:
        assert f'action_id="{action_id}"' in MAINWINDOW_SRC, action_id


def test_extra_shortcuts_do_not_use_option_plus_letter():
    """⌥+字母／數字在 macOS 會直接打出字元，當快速鍵不可靠（BR-MAC-3）。"""
    for sequences in platforms._MAC_EXTRA_SHORTCUTS.values():
        for seq in sequences:
            assert not re.search(r"Alt\+[A-Za-z0-9]$", seq), seq


def test_extra_shortcuts_are_command_based():
    """Qt 會把可攜寫法的 Ctrl 對映成 ⌘，替代鍵一律以它為主修飾鍵。"""
    for sequences in platforms._MAC_EXTRA_SHORTCUTS.values():
        for seq in sequences:
            assert seq.startswith("Ctrl+"), seq


def test_extra_shortcuts_are_unique():
    used = [s for seqs in platforms._MAC_EXTRA_SHORTCUTS.values() for s in seqs]
    assert len(used) == len(set(used))


def test_every_extra_shortcut_has_a_label_for_the_help_dialog():
    """說明視窗是照這張表自動產生的；少一個標籤就會印出代號給使用者看。

    用讀原始碼而不是 import 的方式檢查，這個檔案才能留在「無 Qt」的測試裡。
    """
    start = MAINWINDOW_SRC.index("EXTRA_SHORTCUT_LABELS = {")
    labels = MAINWINDOW_SRC[start : MAINWINDOW_SRC.index("}", start)]
    for action_id in platforms._MAC_EXTRA_SHORTCUTS:
        assert f'"{action_id}":' in labels, action_id


def test_extra_shortcuts_of_an_unknown_action_is_empty():
    assert platforms.extra_shortcuts("沒有這個動作") == ()


def test_modifier_names_follow_the_platform():
    assert platforms.mod("Ctrl") == ("⌘" if platforms.IS_MAC else "Ctrl")
    assert platforms.mod("Alt") == ("⌥" if platforms.IS_MAC else "Alt")


# -- D-06：設定目錄 ---------------------------------------------------
def test_d_06_config_dir_follows_the_platform_convention():
    path = platforms.config_dir()
    assert path.name == "StephanyEditor"
    if platforms.IS_MAC:
        assert path.parent.name == "Application Support"
        assert path.parent.parent.name == "Library"


def test_d_06_config_dir_can_be_overridden(monkeypatch, tmp_path):
    """想把巨集放在雲端同步目錄的人用這個環境變數。"""
    monkeypatch.setenv(platforms.CONFIG_DIR_ENV, str(tmp_path / "共用"))
    assert platforms.config_dir() == tmp_path / "共用"


def test_macro_store_lives_under_the_config_dir(monkeypatch, tmp_path):
    from stephany.core.macro import default_store_path

    monkeypatch.setenv(platforms.CONFIG_DIR_ENV, str(tmp_path))
    path = default_store_path()
    assert path == tmp_path / "macros.json"


@pytest.mark.skipif(not platforms.IS_LINUX, reason="XDG 只在 Linux 分支")
def test_linux_still_honours_xdg_config_home(monkeypatch, tmp_path):
    monkeypatch.delenv(platforms.CONFIG_DIR_ENV, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert platforms.config_dir() == tmp_path / "StephanyEditor"
