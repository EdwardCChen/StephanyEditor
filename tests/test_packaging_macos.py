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

"""macOS .app 中繼資料的一致性測試（SRS-005 D-01 ~ D-03、F-MAC-*、NF-02）。

與 `test_packaging.py` 同一個理由：應用程式身分是由好幾個檔案「剛好對得上」
才成立的，改了其中一處忘了改另一處就會回到「選單列顯示成腳本名稱」。
這種事用肉眼檢查不可靠，直接寫成斷言。

本檔刻意不 import PySide6，才能在 CI 的「核心邏輯（無 Qt）」job 裡跑。
"""

from __future__ import annotations

import plistlib
import re
from pathlib import Path

import pytest

from stephany import __version__
from stephany.__main__ import APP_ID

ROOT = Path(__file__).resolve().parent.parent
PLIST = ROOT / "packaging" / "Info.plist"
BUILD_SCRIPT = ROOT / "packaging" / "build-app.sh"
BOOTSTRAP = ROOT / "packaging" / "stephany-editor.bootstrap"
CLI = ROOT / "packaging" / "stephany-editor.cli"
MAKE_ICONS = ROOT / "packaging" / "make-icons.py"

SCRIPT = BUILD_SCRIPT.read_text(encoding="utf-8")

#: 只看實際會執行的部分——註解裡提到「不用 py2app」不該被當成用了 py2app
CODE = "\n".join(
    line for line in SCRIPT.splitlines() if not line.lstrip().startswith("#")
)


@pytest.fixture(scope="module")
def plist() -> dict:
    return plistlib.loads(PLIST.read_bytes())


def _shell_var(name: str) -> str:
    match = re.search(rf'^{name}="([^"]*)"', SCRIPT, re.MULTILINE)
    assert match, f"build-app.sh 找不到 {name}"
    return match.group(1)


# -- D-01：Contents/MacOS 底下必須是直譯器本體 ------------------------
def test_d_01_the_bundle_executable_is_the_app_id(plist):
    assert plist["CFBundleExecutable"] == APP_ID


def test_d_01_build_script_copies_the_interpreter_into_macos():
    """換成 shell 啟動器的話，NSBundle 會認不得這個 .app，
    選單列就會顯示成腳本檔名（規格 §2 有實測數據）。"""
    assert 'cp "$CONTENTS/bin/python3" "$CONTENTS/MacOS/$APP_ID"' in SCRIPT


def test_d_01_the_bundle_executable_is_never_a_shell_script():
    assert '"$CONTENTS/MacOS/$APP_ID" <<' not in CODE
    assert "#!/bin/sh" not in CODE


# -- D-02：venv 建在 Contents/，進入點掛在 sitecustomize --------------
def test_d_02_venv_is_rooted_at_contents():
    """直譯器在 Contents/MacOS/，Python 找的 venv 標記就是 Contents/pyvenv.cfg。"""
    assert '-m venv --copies "$CONTENTS"' in SCRIPT


def test_d_02_entry_point_is_installed_as_sitecustomize():
    assert 'stephany-editor.bootstrap "$SITE/sitecustomize.py"' in SCRIPT


def test_d_02_bootstrap_only_takes_over_a_bare_launch():
    """帶參數時要讓路給 -m stephany，否則終端機用法會被吃掉。"""
    text = BOOTSTRAP.read_text(encoding="utf-8")
    assert "sys.orig_argv" in text
    assert "_launched_by_the_dock()" in text


def test_d_02_bootstrap_ignores_the_process_serial_number_argument():
    assert "-psn_" in BOOTSTRAP.read_text(encoding="utf-8")


def test_d_02_bootstrap_exits_instead_of_falling_through_to_the_repl():
    assert "os._exit" in BOOTSTRAP.read_text(encoding="utf-8")


# -- D-03：不用 py2app / PyInstaller ---------------------------------
def test_d_03_no_third_party_bundler_is_required():
    for tool in ("py2app", "pyinstaller", "PyInstaller", "briefcase"):
        assert tool not in CODE, tool


def test_d_03_uses_only_the_tools_macos_already_ships():
    for tool in ("iconutil", "hdiutil", "ditto"):
        assert tool in CODE, tool


def test_the_build_does_not_try_to_codesign():
    """codesign 會因為 D-02 必需的 Contents/pyvenv.cfg 而整個失敗；
    與其每次印一行「簽章略過」，不如明講不簽，並在註解裡寫清楚原因。"""
    assert "codesign" not in CODE
    assert "codesign" in SCRIPT  # 註解裡有解釋
    assert "com.apple.quarantine" in SCRIPT  # 也給了拿到別台 Mac 的解法


def test_d_03_build_needs_no_root():
    """唯一出現 sudo 的地方是「印出來給人自己跑」的 symlink 指令。"""
    for line in CODE.splitlines():
        assert "sudo " not in line or line.lstrip().startswith("echo "), line


def test_build_script_refuses_to_run_on_the_wrong_platform():
    assert '"$(uname -s)" != "Darwin"' in SCRIPT


def test_build_script_rejects_a_python_older_than_the_project_requires():
    """macOS 內建的 /usr/bin/python3 是 3.9，直接用會在別處炸開。"""
    assert "sys.version_info < (3, 10)" in SCRIPT


# -- BR-MAC-1：版本號只有一個來源 -------------------------------------
def test_br_mac_1_version_comes_from_the_package(plist):
    assert plist["CFBundleShortVersionString"] == "@VERSION@"
    assert plist["CFBundleVersion"] == "@VERSION@"
    assert "stephany/__init__.py" in SCRIPT
    assert "s|@VERSION@|$VERSION|g" in SCRIPT


def test_br_mac_1_version_is_a_valid_bundle_version():
    """CFBundleVersion 只接受以點分隔的數字。"""
    assert re.fullmatch(r"\d+(\.\d+)*", __version__), __version__


# -- BR-MAC-5：bundle id 與 app_id 同源 -------------------------------
def test_br_mac_5_bundle_id_is_derived_from_the_app_id():
    bundle_id = _shell_var("BUNDLE_ID")
    assert bundle_id.endswith(f".{APP_ID}"), bundle_id
    assert bundle_id.count(".") >= 2, "CFBundleIdentifier 慣例是反向網域名稱"


def test_br_mac_5_plist_takes_the_bundle_id_from_the_build_script(plist):
    assert plist["CFBundleIdentifier"] == "@BUNDLE_ID@"
    assert "s|@BUNDLE_ID@|$BUNDLE_ID|g" in SCRIPT


def test_app_name_is_human_readable_not_the_app_id(plist):
    assert plist["CFBundleName"] == "Stephany Editor"
    assert plist["CFBundleName"] != APP_ID


# -- F-MAC-03：註冊為文字檔的開啟方式 ---------------------------------
def test_f_mac_03_registers_as_a_text_file_handler(plist):
    types = plist["CFBundleDocumentTypes"]
    assert types, "沒有宣告 CFBundleDocumentTypes，Finder 的「打開方式」不會列出來"
    content_types = types[0]["LSItemContentTypes"]
    assert "public.plain-text" in content_types
    assert "public.source-code" in content_types


def test_f_mac_03_does_not_steal_the_default_handler(plist):
    """Alternate = 出現在「打開方式」清單裡，但不搶走使用者原本的預設程式。"""
    assert plist["CFBundleDocumentTypes"][0]["LSHandlerRank"] == "Alternate"


def test_f_mac_03_declares_itself_an_editor_not_a_viewer(plist):
    assert plist["CFBundleDocumentTypes"][0]["CFBundleTypeRole"] == "Editor"


# -- F-MAC-05：終端機指令 ---------------------------------------------
def test_f_mac_05_cli_wrapper_runs_the_module_not_the_bare_interpreter():
    """直接執行 Contents/MacOS/ 的檔案時，參數會被 Python 自己解析掉
    （`--version` 會印出 Python 的版本），所以要走 -m。"""
    text = CLI.read_text(encoding="utf-8")
    assert "-m stephany" in text
    assert '"$CONTENTS/MacOS/stephany-editor"' in text


def test_f_mac_05_cli_wrapper_resolves_symlinks():
    """它會被 symlink 到 /usr/local/bin，$0 不能直接當成實際位置用。"""
    assert "readlink" in CLI.read_text(encoding="utf-8")


def test_f_mac_05_cli_wrapper_is_installed_into_the_bundle():
    assert 'stephany-editor.cli "$CONTENTS/Resources/bin/$APP_ID"' in SCRIPT


# -- 圖示（SRS-004 D-06 沿用：單一 SVG 產生所有尺寸）------------------
def test_icons_come_from_the_same_single_svg():
    assert "make-icons.py" in SCRIPT
    assert "stephany/resources/stephany-editor.svg" in SCRIPT
    assert "iconutil -c icns" in SCRIPT


def test_iconset_covers_every_size_iconutil_expects():
    text = MAKE_ICONS.read_text(encoding="utf-8")
    for name in (
        "icon_16x16.png",
        "icon_16x16@2x.png",
        "icon_32x32.png",
        "icon_32x32@2x.png",
        "icon_128x128.png",
        "icon_128x128@2x.png",
        "icon_256x256.png",
        "icon_256x256@2x.png",
        "icon_512x512.png",
        "icon_512x512@2x.png",
    ):
        assert name in text, name


def test_plist_points_at_the_generated_icon(plist):
    assert plist["CFBundleIconFile"] == APP_ID
    assert f'"$CONTENTS/Resources/$APP_ID.icns"' in SCRIPT


# -- BR-MAC-2：bundle 內不得有建構期的殘留 ----------------------------
def test_br_mac_2_build_artifacts_are_stripped():
    for pattern in ("__pycache__", "*.pyc", "pip", "setuptools"):
        assert pattern in SCRIPT, pattern
    assert 'rm -rf "$CONTENTS/bin" "$CONTENTS/include"' in SCRIPT


def test_br_mac_2_only_the_package_is_copied_in():
    """只打包 stephany/，tests/ 與開發腳本自然不會進去。"""
    assert "\n    stephany | tar -x" in SCRIPT


# -- 其他 bundle 中繼資料 ---------------------------------------------
def test_bundle_is_marked_high_resolution(plist):
    """沒有這個鍵，Retina 螢幕上會以兩倍放大的點陣呈現。"""
    assert plist["NSHighResolutionCapable"] is True


def test_bundle_allows_dark_mode(plist):
    """主題是由系統配色推導的（SRS-003），被鎖在淺色就沒意義了。"""
    assert plist["NSRequiresAquaSystemAppearance"] is False


def test_minimum_system_version_matches_the_pyside_wheel(plist):
    """PySide6 的 macOS wheel 是 macosx_13_0_universal2。"""
    assert plist["LSMinimumSystemVersion"] == "13.0"


def test_package_type_is_an_application(plist):
    assert plist["CFBundlePackageType"] == "APPL"


def test_copyright_is_declared(plist):
    assert "@COPYRIGHT@" in plist["NSHumanReadableCopyright"]
    assert "GPL-3.0-or-later" in plist["NSHumanReadableCopyright"]
    assert 'COPYRIGHT_HOLDER="Edward Chen"' in SCRIPT


# -- 授權標頭（GPL 慣例）----------------------------------------------
def test_new_packaging_files_carry_the_licence_notice():
    for path in (BUILD_SCRIPT, BOOTSTRAP, CLI, PLIST.parent / "build-deb.sh"):
        assert "GNU General Public License" in path.read_text(encoding="utf-8"), path


def test_no_shell_variable_is_glued_to_a_chinese_character():
    """`$VAR（` 在 macOS 內建的 bash 3.2 會炸開。

    bash 3.2（macOS 就停在這個版本）在 UTF-8 locale 下解析 `$VAR` 時，會把
    後面那個多位元組字元的第一個位元組也吃進變數名稱，於是 `set -u` 報
    「unbound variable」。本專案的訊息全是中文，很容易踩到，所以直接擋下來：
    變數後面緊接著非 ASCII 字元時一律要寫成 `${VAR}`。

    在 Linux（bash 5）上測不出來，但規則對所有腳本都成立。
    """
    pattern = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)([^\x00-\x7f])")
    offenders = []
    for path in sorted(ROOT.rglob("*.sh")):
        if ".venv" in path.parts or "dist" in path.parts:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for match in pattern.finditer(line):
                offenders.append(
                    f"{path.relative_to(ROOT)}:{number} ${match.group(1)} "
                    f"後面緊接著「{match.group(2)}」，請改成 ${{{match.group(1)}}}"
                )
    assert not offenders, "\n".join(offenders)


def test_shebang_stays_on_the_first_line():
    for path in (BUILD_SCRIPT, CLI):
        assert path.read_text(encoding="utf-8").splitlines()[0].startswith("#!"), path
