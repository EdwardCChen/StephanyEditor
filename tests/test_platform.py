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
def test_br_mac_4_win_5_extra_shortcuts_only_ever_add(monkeypatch):
    """跨平台的鍵表只有一份；各平台只能「多綁一個」，不得另建一套。

    Linux 什麼都不必補（F1/F2 按得到、Alt+C 沒有被選單搶走）；
    macOS 與 Windows 各自補的鍵，都必須是既有動作的額外綁定。
    """
    if platforms.IS_LINUX:
        assert platforms.EXTRA_SHORTCUTS == {}
    for table in (platforms._MAC_EXTRA_SHORTCUTS, platforms._WINDOWS_EXTRA_SHORTCUTS):
        for action_id, sequences in table.items():
            assert sequences, action_id


#: 每個平台的補鍵表。規則對每一張都成立，不是只檢查目前這台機器的那張
#: ——否則在 Linux 上跑 CI 時，兩張表都不會被驗到。
ALL_EXTRA_TABLES = {
    "macOS": platforms._MAC_EXTRA_SHORTCUTS,
    "Windows": platforms._WINDOWS_EXTRA_SHORTCUTS,
}


def test_every_extra_shortcut_belongs_to_a_real_action():
    """漏改 mainwindow 的 action_id 時，這個測試會抓到。"""
    for platform, table in ALL_EXTRA_TABLES.items():
        for action_id in table:
            assert f'action_id="{action_id}"' in MAINWINDOW_SRC, (
                f"{platform} 的 {action_id}"
            )


def test_extra_shortcuts_do_not_use_alt_plus_letter():
    """補鍵不得再用 Alt+字母／數字——那正是要繞過的東西：
    macOS 會直接打出字元（⌥C → ç，BR-MAC-3），Windows 會被選單助憶鍵
    吃掉（F-WIN-08）。用它當替代鍵等於沒換。
    """
    for platform, table in ALL_EXTRA_TABLES.items():
        for sequences in table.values():
            for seq in sequences:
                assert not re.search(r"Alt\+[A-Za-z0-9]$", seq), f"{platform}：{seq}"


def test_extra_shortcuts_are_control_based():
    """一律以 Ctrl 為主修飾鍵：Qt 在 macOS 會把它對映成 ⌘，Windows 就是
    Ctrl 本身，兩邊寫法一致（BR-MAC-4、BR-WIN-5）。"""
    for platform, table in ALL_EXTRA_TABLES.items():
        for sequences in table.values():
            for seq in sequences:
                assert seq.startswith("Ctrl+"), f"{platform}：{seq}"


def test_extra_shortcuts_are_unique_within_each_platform():
    for platform, table in ALL_EXTRA_TABLES.items():
        used = [s for seqs in table.values() for s in seqs]
        assert len(used) == len(set(used)), platform


def test_every_extra_shortcut_has_a_label_for_the_help_dialog():
    """說明視窗是照這張表自動產生的；少一個標籤就會印出代號給使用者看。

    用讀原始碼而不是 import 的方式檢查，這個檔案才能留在「無 Qt」的測試裡。
    """
    start = MAINWINDOW_SRC.index("EXTRA_SHORTCUT_LABELS = {")
    labels = MAINWINDOW_SRC[start : MAINWINDOW_SRC.index("}", start)]
    for platform, table in ALL_EXTRA_TABLES.items():
        for action_id in table:
            assert f'"{action_id}":' in labels, f"{platform} 的 {action_id}"


def test_every_platform_with_extra_keys_explains_why():
    """說明視窗要講「為什麼這個鍵換了」。補了鍵卻沒有理由可講，
    使用者只會看到一串沒頭沒尾的按鍵（SRS-006 F-WIN-08 的收尾）。"""
    if platforms.EXTRA_SHORTCUTS:
        assert platforms.EXTRA_SHORTCUTS_TITLE
        assert platforms.EXTRA_SHORTCUTS_REASON
    else:
        assert not platforms.EXTRA_SHORTCUTS_TITLE
        assert not platforms.EXTRA_SHORTCUTS_REASON


def test_the_gnome_hint_is_linux_only():
    """GNOME 會攔截 Alt+拖曳——那是 Linux 才有的事。"""
    assert bool(platforms.STICKY_MODE_HINT) is platforms.IS_LINUX


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


# ======================================================================
# SRS-006：Windows
# ======================================================================
# -- D-W4 / D-W5 / BR-WIN-4：字型清單 --------------------------------
def test_d_w4_windows_aligned_list_holds_the_measured_fonts():
    """實測 9~24pt 全部剛好 2.000 的那幾個（SRS-006 §2 D-W4 的表）。"""
    families = [family for family, _ in platforms._WINDOWS_ALIGNED]
    for family in ("MingLiU", "NSimSun", "MS Gothic"):
        assert family in families, family


def test_br_win_4_no_proportional_variant_is_listed():
    """`PMingLiU` 只比 `MingLiU` 多一個 P，比例卻是 2.13（實測）。

    `MS PGothic` 同理。名字太像了，靠肉眼 review 擋不住，寫成規則。
    """
    for family, _ in platforms._WINDOWS_ALIGNED:
        assert not re.match(r"^(MS )?P[A-Z]", family), family
    assert ("PMingLiU", None) not in platforms._WINDOWS_ALIGNED
    assert ("MS PGothic", None) not in platforms._WINDOWS_ALIGNED


def test_d_w4_traditional_chinese_fonts_come_before_japanese_ones():
    """本專案以繁體中文為主，原本猜的清單把日文的 MS Gothic 排第一。"""
    families = [family for family, _ in platforms._WINDOWS_ALIGNED]
    assert families.index("MingLiU") < families.index("NSimSun")
    assert families.index("NSimSun") < families.index("MS Gothic")


def test_d_w6_localised_font_names_are_listed_too():
    """Qt 在 zh-TW 的 Windows 上同時列出 `MingLiU` 與 `細明體`；
    其他語系不保證，兩個都寫進去比在這裡判斷 locale 乾淨。"""
    families = [family for family, _ in platforms._WINDOWS_ALIGNED]
    assert "細明體" in families
    assert "MingLiU" in families


def test_d_w4_the_always_present_fonts_are_only_fallbacks():
    """Consolas 1.82、Cascadia Mono 1.71、Courier New 1.67——都不合格，
    只能當退路，不得混進對齊清單。"""
    aligned = {family for family, _ in platforms._WINDOWS_ALIGNED}
    for family in ("Consolas", "Cascadia Mono", "Courier New", "Lucida Console"):
        assert family not in aligned, family
    assert ("Consolas", None) in platforms._WINDOWS_FALLBACK


def test_the_windows_font_hint_names_something_obtainable():
    if platforms.IS_WINDOWS:
        assert "細明體" in platforms.FONT_HINT or "MingLiU" in platforms.FONT_HINT


# -- D-W7 / F-WIN-08 / BR-WIN-5：Alt+C 的替代鍵 -----------------------
def test_f_win_08_windows_adds_an_alternative_for_alt_c():
    """實測：Alt+C 被選單列的 編碼(&C) 助憶鍵吃掉，完全按不到。"""
    assert "column_editor" in platforms._WINDOWS_EXTRA_SHORTCUTS


def test_br_win_5_windows_and_macos_share_the_same_alternative_key():
    """同一個問題（按不到 Alt+C）在兩個平台上補同一個鍵，
    肌肉記憶才不會分岔。"""
    assert (
        platforms._WINDOWS_EXTRA_SHORTCUTS["column_editor"]
        == platforms._MAC_EXTRA_SHORTCUTS["column_editor"]
    )


def test_windows_does_not_need_function_key_alternatives():
    """F1/F2 在 Windows 上直接按得到，不該跟著 macOS 一起補。"""
    for action_id in ("help", "bookmark_toggle", "bookmark_next", "bookmark_prev"):
        assert action_id not in platforms._WINDOWS_EXTRA_SHORTCUTS, action_id


def test_the_platform_gets_its_own_extra_shortcut_table():
    if platforms.IS_WINDOWS:
        assert platforms.EXTRA_SHORTCUTS == platforms._WINDOWS_EXTRA_SHORTCUTS
    elif platforms.IS_MAC:
        assert platforms.EXTRA_SHORTCUTS == platforms._MAC_EXTRA_SHORTCUTS


# -- F-WIN-09：設定目錄 ----------------------------------------------
@pytest.mark.skipif(not platforms.IS_WINDOWS, reason="APPDATA 只在 Windows 分支")
def test_f_win_09_config_dir_lives_under_appdata(monkeypatch, tmp_path):
    monkeypatch.delenv(platforms.CONFIG_DIR_ENV, raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert platforms.config_dir() == tmp_path / "StephanyEditor"


@pytest.mark.skipif(not platforms.IS_WINDOWS, reason="APPDATA 只在 Windows 分支")
def test_config_dir_still_works_without_appdata(monkeypatch):
    """APPDATA 在服務或精簡環境下可能不存在，不能就這樣炸開。"""
    monkeypatch.delenv(platforms.CONFIG_DIR_ENV, raising=False)
    monkeypatch.delenv("APPDATA", raising=False)
    assert platforms.config_dir().name == "StephanyEditor"


def test_d_w9_only_conftest_decides_the_qt_platform_plugin():
    """平台外掛的選擇必須只有一個地方講得算（SRS-006 D-W9）。

    測試模組若自己 `setdefault("QT_QPA_PLATFORM", "offscreen")`，在
    Windows 上就會把 conftest 刻意避開的 offscreen 又設回去——而且因為
    模組是照字母序 import 的，`test_macos_gui` 會先於 `test_windows_gui`
    生效，症狀是「單獨跑那個檔會過、跑全套就 skip」，很難追。
    """
    import ast

    def sets_the_plugin(node: ast.AST) -> bool:
        """`os.environ["QT_QPA_PLATFORM"] = ...` 或 `.setdefault("QT_QPA_PLATFORM", ...)`。

        用 ast 而不是抓字串，才不會被註解、docstring（例如本測試自己的）
        或斷言裡提到的同一個名字誤判。
        """
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in ("setdefault", "update"):
                return any(
                    isinstance(a, ast.Constant) and a.value == "QT_QPA_PLATFORM"
                    for a in node.args
                )
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Subscript)
                    and isinstance(target.slice, ast.Constant)
                    and target.slice.value == "QT_QPA_PLATFORM"
                ):
                    return True
        return False

    offenders = []
    for path in sorted(Path(__file__).resolve().parent.glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if sets_the_plugin(node):
                offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders, f"平台外掛只能由 conftest.py 決定：{offenders}"


# -- D-W1 / BR-WIN-3：三個平台的識別碼同源 ----------------------------
def test_br_win_3_the_bundle_id_has_a_single_source():
    """AppUserModelID（Windows）與 CFBundleIdentifier（macOS）必須同一個字串。

    兩邊各寫一次字面值遲早會漂移——與 BR-PK-1／BR-MAC-1 對版本號的要求
    同一個道理，來源只能有一個。
    """
    from stephany import APP_ID, BUNDLE_ID

    assert BUNDLE_ID.endswith(f".{APP_ID}"), BUNDLE_ID
    assert BUNDLE_ID.count(".") >= 2, "慣例是反向網域名稱"


def test_br_win_3_the_macos_build_script_reads_the_same_source():
    """build-app.sh 不得自己再寫一次 bundle id 的字面值。"""
    from stephany import BUNDLE_ID

    script = (ROOT / "packaging" / "build-app.sh").read_text(encoding="utf-8")
    assert f'BUNDLE_ID="{BUNDLE_ID}"' not in script, (
        "build-app.sh 仍然寫死 bundle id，改成從 stephany 套件讀"
    )
    assert "BUNDLE_ID" in script


def test_d_w1_the_app_user_model_id_is_the_bundle_id():
    from stephany import BUNDLE_ID

    assert platforms.APP_USER_MODEL_ID == BUNDLE_ID


def test_d_w1_setting_the_identity_is_a_no_op_off_windows(monkeypatch):
    """這個函式在每個平台都會被呼叫到，非 Windows 必須安靜地什麼都不做。"""
    if not platforms.IS_WINDOWS:
        assert platforms.set_app_user_model_id() is False


# -- 終端機說明文字也要講本平台按得到的鍵（F-WIN-08 的收尾）------------
def test_the_cli_usage_advertises_a_column_editor_key_that_works_here():
    """`stephany-editor --help` 印的是 Alt+C，但那個鍵在 Windows 按不到
    （被選單助憶鍵吃掉）、在 macOS 會打出 ç。印一個按不到的鍵給使用者看，
    比不印還糟。
    """
    from stephany.__main__ import USAGE

    extra = platforms.extra_shortcuts("column_editor")
    assert "欄位編輯器" in USAGE
    if not extra:
        return
    # 有替代鍵的平台，說明裡就必須看得到它
    keys = extra[0].split("+")
    rendered = " + ".join(platforms.mod(part) for part in keys)
    assert rendered in USAGE, f"說明裡找不到 {rendered}"


def test_the_cli_usage_is_not_written_for_another_platform():
    from stephany.__main__ import USAGE

    if not platforms.IS_MAC:
        for symbol in ("⌘", "⌥", "⇧"):
            assert symbol not in USAGE, symbol
