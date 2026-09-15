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

"""桌面整合與打包中繼資料的一致性測試。

對應 SRS-004 D-01、F-PK-*、BR-PK-1、NF-02。

這組測試存在的理由：工作列顯示成 `python3` 的根因，是「應用程式宣告的
app_id」與「.desktop 檔名」沒有對上。這種不一致用肉眼看很容易漏掉，
而且改了其中一處忘了改另一處就會再犯，所以直接把規則寫成斷言。

本檔刻意不 import PySide6，才能在 CI 的「核心邏輯（無 Qt）」job 裡跑。
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from stephany import __version__
from stephany.__main__ import APP_ID

ROOT = Path(__file__).resolve().parent.parent
DESKTOP_FILE = ROOT / "packaging" / "stephany-editor.desktop"
LAUNCHER = ROOT / "packaging" / "stephany-editor.launcher"
BUILD_SCRIPT = ROOT / "packaging" / "build-deb.sh"
ICON_SVG = ROOT / "stephany" / "resources" / "stephany-editor.svg"

#: 程式碼安裝位置（SRS-004 D-04）
INSTALL_PREFIX = "/usr/share/stephany-editor"


@pytest.fixture(scope="module")
def desktop() -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in DESKTOP_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("["):
            continue
        key, _, value = line.partition("=")
        entries[key.strip()] = value.strip()
    return entries


# -- D-01：app_id / .desktop 檔名 / StartupWMClass 三者必須一致 --------
def test_d_01_desktop_file_is_named_after_the_app_id():
    assert DESKTOP_FILE.name == f"{APP_ID}.desktop"


def test_d_01_startup_wm_class_matches_the_app_id(desktop):
    """X11 下的 Dock 靠 StartupWMClass 比對視窗歸屬。"""
    assert desktop["StartupWMClass"] == APP_ID


def test_d_01_icon_name_matches_the_app_id(desktop):
    assert desktop["Icon"] == APP_ID


def test_d_01_exec_invokes_the_installed_command(desktop):
    assert desktop["Exec"].split()[0] == APP_ID


# -- .desktop 檔的完整性（F-PK-03、F-PK-04）---------------------------
def test_desktop_entry_has_the_required_keys(desktop):
    for key in ("Type", "Name", "Exec", "Icon", "Categories", "Terminal"):
        assert key in desktop, f"缺少 {key}"
    assert desktop["Type"] == "Application"
    assert desktop["Terminal"] == "false"


def test_f_pk_03_appears_under_a_sensible_menu_category(desktop):
    categories = [c for c in desktop["Categories"].split(";") if c]
    assert "TextEditor" in categories
    assert "Utility" in categories


def test_f_pk_04_registers_as_a_handler_for_text_files(desktop):
    mimes = [m for m in desktop["MimeType"].split(";") if m]
    assert "text/plain" in mimes


def test_exec_accepts_file_arguments(desktop):
    """%F 才能從檔案管理員「用它開啟」多個檔案。"""
    assert desktop["Exec"].endswith("%F")


def test_display_name_is_human_readable_not_the_app_id(desktop):
    assert desktop["Name"] == "Stephany Editor"
    assert desktop["Name"] != APP_ID


# -- 啟動器與安裝路徑（D-04）------------------------------------------
def test_launcher_adds_the_install_prefix_to_sys_path():
    assert INSTALL_PREFIX in LAUNCHER.read_text(encoding="utf-8")


def test_launcher_uses_the_system_python():
    first = LAUNCHER.read_text(encoding="utf-8").splitlines()[0]
    assert first == "#!/usr/bin/python3"


def test_build_script_installs_code_where_the_launcher_looks():
    script = BUILD_SCRIPT.read_text(encoding="utf-8")
    assert 'usr/share/$PKG' in script
    assert 'PKG="stephany-editor"' in script


# -- BR-PK-1：版本號只有一個來源 --------------------------------------
def test_br_pk_1_build_script_reads_the_version_from_the_package():
    script = BUILD_SCRIPT.read_text(encoding="utf-8")
    assert "stephany/__init__.py" in script
    assert "__version__" in script


def test_version_is_a_valid_debian_version():
    # Debian 版本號不得以非數字開頭，也不能含有 '-' 以外的怪字元
    assert re.fullmatch(r"\d+(\.\d+)*", __version__), __version__


# -- BR-PK-2：套件內不得含有開發用檔案 --------------------------------
def test_br_pk_2_build_script_excludes_bytecode_and_dev_files():
    script = BUILD_SCRIPT.read_text(encoding="utf-8")
    assert "--exclude='__pycache__'" in script
    assert "--exclude='*.pyc'" in script
    # 只打包 stephany/ 套件本身，tests/ 與開發腳本自然不會進去
    assert "\n    stephany | tar -x" in script


# -- BR-PK-3 / BR-PK-4 -------------------------------------------------
def test_br_pk_3_post_install_refreshes_desktop_and_icon_caches():
    script = BUILD_SCRIPT.read_text(encoding="utf-8")
    assert "update-desktop-database" in script
    assert "gtk-update-icon-cache" in script


def test_br_pk_4_package_is_built_with_root_ownership():
    assert "--root-owner-group" in BUILD_SCRIPT.read_text(encoding="utf-8")


def test_build_script_normalises_permissions():
    """建構者的 umask 不得把 775/664 帶進套件。"""
    script = BUILD_SCRIPT.read_text(encoding="utf-8")
    assert "chmod 0755 {}" in script
    assert "chmod 0644 {}" in script


# -- 圖示（D-06）------------------------------------------------------
def test_icon_svg_exists_and_parses():
    assert ICON_SVG.exists()
    root = ET.fromstring(ICON_SVG.read_text(encoding="utf-8"))
    assert root.tag.endswith("svg")
    assert root.get("viewBox") == "0 0 256 256"


def test_icon_ships_inside_the_python_package():
    """圖示放在套件內，從原始碼直接執行時也找得到。"""
    assert ICON_SVG.parent.name == "resources"
    assert (ICON_SVG.parent / "__init__.py").exists()


def test_build_script_generates_icons_from_the_single_svg():
    script = BUILD_SCRIPT.read_text(encoding="utf-8")
    assert "make-icons.py" in script
    assert "hicolor" in script


# -- 套件相依（D-02、D-05）-------------------------------------------
def test_d_02_depends_on_system_pyside6_not_a_bundled_venv():
    script = BUILD_SCRIPT.read_text(encoding="utf-8")
    assert "python3-pyside6.qtwidgets" in script
    assert ".venv" not in script.split("Depends:")[1].split("\n")[0]


def test_d_05_cjk_font_is_recommended_not_required():
    script = BUILD_SCRIPT.read_text(encoding="utf-8")
    assert "Recommends: fonts-noto-cjk" in script


def test_package_is_architecture_independent():
    assert "Architecture: all" in BUILD_SCRIPT.read_text(encoding="utf-8")


# -- 授權（GPL-3.0）---------------------------------------------------
LICENSE_FILE = ROOT / "LICENSE"

#: 每個原始檔開頭都要有的字串
LICENSE_NOTICE = "GNU General Public License"


def test_license_file_is_the_gpl_version_3():
    text = LICENSE_FILE.read_text(encoding="utf-8")
    assert "GNU GENERAL PUBLIC LICENSE" in text
    assert "Version 3, 29 June 2007" in text


def test_every_source_file_carries_the_licence_notice():
    """GPL 慣例是每個檔案都要有授權聲明；新增檔案漏掉時這個測試會抓到。"""
    missing = []
    for path in sorted((ROOT / "stephany").rglob("*.py")):
        head = path.read_text(encoding="utf-8")[:900]
        if LICENSE_NOTICE not in head:
            missing.append(str(path.relative_to(ROOT)))
    assert not missing, f"缺少授權標頭：{missing}"


def test_test_files_also_carry_the_licence_notice():
    missing = []
    for path in sorted((ROOT / "tests").glob("*.py")):
        head = path.read_text(encoding="utf-8")[:900]
        if LICENSE_NOTICE not in head:
            missing.append(str(path.relative_to(ROOT)))
    assert not missing, f"缺少授權標頭：{missing}"


def test_source_headers_name_the_copyright_holder():
    head = (ROOT / "stephany" / "__init__.py").read_text(encoding="utf-8")[:900]
    assert "Copyright (C) 2026 Edward Chen" in head


def test_shebang_stays_on_the_first_line_after_adding_headers():
    """授權標頭必須加在 shebang 之後，否則腳本無法執行。"""
    for path in (LAUNCHER, ROOT / "run.sh", BUILD_SCRIPT):
        first = path.read_text(encoding="utf-8").splitlines()[0]
        assert first.startswith("#!"), path


def test_package_copyright_declares_gpl_3_plus():
    script = BUILD_SCRIPT.read_text(encoding="utf-8")
    assert "License: GPL-3+" in script


def test_package_copyright_references_the_system_licence_text():
    """Debian 政策：常見授權引用 /usr/share/common-licenses，不重複內嵌。"""
    script = BUILD_SCRIPT.read_text(encoding="utf-8")
    assert "/usr/share/common-licenses/GPL-3" in script


def test_copyright_year_and_holder_are_single_sourced_in_the_build_script():
    script = BUILD_SCRIPT.read_text(encoding="utf-8")
    assert 'COPYRIGHT_HOLDER="Edward Chen"' in script
    assert 'COPYRIGHT_YEAR="2026"' in script


# -- 跨平台開發：行尾（SRS-006 NF-W4 周邊）----------------------------
def test_shell_scripts_are_stored_with_lf_line_endings():
    """`build-app.sh` 與 `build-deb.sh` 只在 macOS／Linux 上執行。

    Windows 加入開發平台之後，`core.autocrlf=true` 的機器一旦把 CRLF 提交
    回去，bash 會把行尾的 `
` 當成指令的一部分，症狀是
    「`$'
': command not found`」——在 Windows 上完全看不出來。
    用 .gitattributes 釘住，不靠每個人的 git 設定正確。
    """
    attributes = ROOT / ".gitattributes"
    assert attributes.exists(), "缺少 .gitattributes，shell 腳本的行尾沒有保障"
    text = attributes.read_text(encoding="utf-8")
    for pattern in ("*.sh", "*.desktop", "*.bootstrap", "*.cli", "*.launcher"):
        assert pattern in text, f"{pattern} 沒有被釘住行尾"
    assert "eol=lf" in text


def test_git_actually_stores_those_files_with_lf():
    """.gitattributes 寫對了不代表既有檔案已經是對的，直接問 git。"""
    import shutil
    import subprocess

    if shutil.which("git") is None:
        pytest.skip("這台機器沒有 git")
    result = subprocess.run(
        ["git", "ls-files", "--eol", "--", "*.sh", "packaging/*"],
        cwd=ROOT, capture_output=True, text=True,
    )
    if result.returncode != 0:
        pytest.skip("不是 git 工作目錄")
    offenders = [
        line for line in result.stdout.splitlines() if "i/crlf" in line
    ]
    assert not offenders, f"以下檔案在儲存庫裡是 CRLF：{offenders}"
