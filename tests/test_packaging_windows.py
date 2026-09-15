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

"""Windows 安裝的一致性測試（SRS-006 D-W1 ~ D-W3、F-WIN-*、BR-WIN-*）。

與 `test_packaging_macos.py` 同一個理由：應用程式身分是好幾個檔案「剛好
對得上」才成立的，改了一處忘了另一處，就會回到「工作列顯示成 pythonw」。

本檔刻意不 import PySide6，才能在 CI 的「核心邏輯（無 Qt）」job 裡跑。
需要 Qt 或真的 Windows API 的部分標了 skipif。
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

import pytest

from stephany import APP_ID, BUNDLE_ID, __version__, platforms

ROOT = Path(__file__).resolve().parent.parent
BUILD_SCRIPT = ROOT / "packaging" / "build-win.py"
MAKE_ICONS = ROOT / "packaging" / "make-icons.py"

SCRIPT = BUILD_SCRIPT.read_text(encoding="utf-8")

#: 只看實際會執行的部分——註解裡寫「不需要 sitecustomize」不該被當成
#: 用了 sitecustomize（與 test_packaging_macos.py 的 CODE 同一個作法）
CODE = "\n".join(
    line for line in SCRIPT.splitlines() if not line.lstrip().startswith("#")
)

windows_only = pytest.mark.skipif(
    not platforms.IS_WINDOWS, reason="只有 Windows 驗得到"
)

#: 建好的安裝樹。沒建過就 skip——建一次要下載 200 MB，不該綁在每次跑測試上。
DIST = ROOT / "dist" / "StephanyEditor"

needs_build = pytest.mark.skipif(
    not DIST.exists(),
    reason="還沒建置（先跑 python packaging/build-win.py）",
)


# ======================================================================
# D-W3：不需要第三方打包工具
# ======================================================================
def test_d_w3_no_third_party_bundler_is_required():
    for tool in ("PyInstaller", "pyinstaller", "cx_Freeze", "cx_freeze",
                 "nuitka", "Nuitka", "py2exe", "pywin32", "win32com"):
        assert tool not in CODE, tool


def test_d_w3_only_the_standard_library_and_venv_are_used():
    """ctypes 是標準函式庫，venv 是 Python 自己就有的——這兩樣構成
    「clone 下來就能建」的底線。"""
    assert "import venv" in CODE
    assert "import ctypes" in CODE


def test_nf_w4_the_build_script_is_python_not_a_batch_file():
    """中文訊息在 cmd 與 PowerShell 的編碼行為都不可靠；Python 本來就是
    本專案的硬相依，用它寫建構腳本沒有額外成本（NF-W4）。"""
    assert BUILD_SCRIPT.exists()
    assert not (ROOT / "packaging" / "build-win.bat").exists()
    assert not (ROOT / "packaging" / "build-win.ps1").exists()
    assert BUILD_SCRIPT.suffix == ".py"


def test_build_script_refuses_to_run_on_the_wrong_platform():
    assert 'os.name != "nt"' in SCRIPT or "platforms.IS_WINDOWS" in SCRIPT


def test_build_script_rejects_a_python_older_than_the_project_requires():
    assert "(3, 10)" in SCRIPT


# ======================================================================
# BR-WIN-1：版本號與識別碼只有一個來源
# ======================================================================
def test_br_win_1_version_comes_from_the_package():
    assert f'"{__version__}"' not in CODE, "建構腳本不得寫死版本號"
    assert "__version__" in SCRIPT


def test_br_win_3_identifiers_come_from_the_package():
    assert f'"{BUNDLE_ID}"' not in CODE, "建構腳本不得寫死 bundle id"
    assert "BUNDLE_ID" in SCRIPT
    assert "APP_ID" in SCRIPT


# ======================================================================
# BR-WIN-6 / F-WIN-10：不需要系統管理員
# ======================================================================
def test_br_win_6_nothing_is_written_outside_the_user_profile():
    """寫到 HKLM 或 Program Files 就需要 UAC 提權；整個安裝方式的
    前提是「不需要」（F-WIN-10）。"""
    for forbidden in ("HKEY_LOCAL_MACHINE", "HKLM", "ProgramFiles",
                      "PROGRAMFILES", "System32", "runas"):
        assert forbidden not in CODE, forbidden


def test_br_win_6_the_install_target_is_under_localappdata():
    assert "LOCALAPPDATA" in SCRIPT


def test_f_win_09_config_stays_out_of_the_install_directory():
    """解除安裝會整個刪掉安裝目錄；設定與巨集在 %APPDATA%，不會被連坐。

    注意不能只寫 `"APPDATA" in SCRIPT`——它是 `LOCALAPPDATA` 的子字串，
    光靠安裝目錄那一行就會通過，等於什麼都沒檢查。
    """
    import re

    assert re.search(r'(?<!LOCAL)APPDATA', CODE), "沒有用到 %APPDATA%"
    assert "config_dir" in CODE, "解除安裝時要能告訴使用者設定留在哪"


# ======================================================================
# D-W1：身分
# ======================================================================
def test_d_w1_the_executable_is_a_renamed_interpreter():
    """給自己一個專屬執行檔，工作管理員才不會顯示成 pythonw。"""
    assert "pythonw.exe" in SCRIPT
    assert f"{APP_ID}.exe" in SCRIPT or "EXE_NAME" in SCRIPT


def _pe_subsystem(path: Path) -> int:
    """讀 PE 標頭的 Subsystem 欄位：2 = GUI，3 = 主控台。"""
    data = path.read_bytes()
    pe = int.from_bytes(data[0x3C:0x40], "little")
    assert data[pe : pe + 4] == b"PE\x00\x00", "不是 PE 檔"
    # Subsystem 在選用標頭的 offset 68，PE32 與 PE32+ 都一樣
    optional = pe + 24
    return int.from_bytes(data[optional + 68 : optional + 70], "little")


@windows_only
@needs_build
def test_f_win_05_the_gui_entry_point_really_is_a_windowed_executable():
    """用 python.exe 當 GUI 進入點的話，每次啟動都會彈一個主控台視窗出來
    （F-WIN-05「不得彈出多餘的主控台視窗」）。

    這件事光看腳本寫了 `pythonw.exe` 是驗不出來的——複製錯了檔案，字串
    仍然在。直接讀產出執行檔的 PE 子系統欄位。
    """
    IMAGE_SUBSYSTEM_WINDOWS_GUI, IMAGE_SUBSYSTEM_WINDOWS_CUI = 2, 3
    gui = DIST / "Scripts" / f"{APP_ID}.exe"
    cli = DIST / "Scripts" / f"{APP_ID}-cli.exe"
    assert _pe_subsystem(gui) == IMAGE_SUBSYSTEM_WINDOWS_GUI, (
        "GUI 進入點不是視窗子系統——啟動時會多一個主控台視窗"
    )
    assert _pe_subsystem(cli) == IMAGE_SUBSYSTEM_WINDOWS_CUI, (
        "終端機進入點不是主控台子系統——--version 的輸出會看不到"
    )


def test_d_w2_no_sitecustomize_hack_is_needed():
    """macOS 要那個 hack 是因為 LaunchServices 不給參數；Windows 的
    ShellExecute 會給，所以進入點就是正常的 `-m stephany`（D-W2）。"""
    assert "sitecustomize" not in CODE
    assert "sitecustomize" in SCRIPT, "註解裡要說明為什麼 Windows 不需要它"
    assert "-m stephany" in CODE


# ======================================================================
# BR-WIN-2：不得帶進建構期殘留
# ======================================================================
@windows_only
def test_br_win_2_the_stripper_actually_removes_things(build_win, tmp_path,
                                                       monkeypatch):
    """原本只檢查腳本裡有沒有出現「pip」這幾個字，所以把
    `strip_build_artifacts()` 整個改成 `return` 也照樣會過。

    改成拿一棵假的安裝樹餵給它，看它到底刪不刪。
    """
    dist = tmp_path / "StephanyEditor"
    site = dist / "Lib" / "site-packages"
    scripts = dist / "Scripts"
    for path in (site, scripts, dist / "Include"):
        path.mkdir(parents=True)
    for name in ("pip", "setuptools", "pkg_resources", "_distutils_hack"):
        (site / name).mkdir()
    (site / "distutils-precedence.pth").write_text("", encoding="utf-8")
    (site / "stephany").mkdir()
    (site / "stephany" / "__pycache__").mkdir()
    (site / "stephany" / "x.pyc").write_bytes(b"")
    (scripts / "pip.exe").write_bytes(b"")
    (scripts / "pyside6-designer.exe").write_bytes(b"")
    (scripts / "activate.bat").write_bytes(b"")
    (scripts / "deactivate.bat").write_bytes(b"")
    (scripts / "python.exe").write_bytes(b"")  # 這個不能被刪掉
    (dist / ".gitignore").write_text("", encoding="utf-8")

    monkeypatch.setattr(build_win, "DIST", dist)
    build_win.strip_build_artifacts(site)

    for gone in (site / "pip", site / "setuptools", site / "pkg_resources",
                 site / "_distutils_hack", site / "distutils-precedence.pth",
                 site / "stephany" / "__pycache__", site / "stephany" / "x.pyc",
                 scripts / "pip.exe", scripts / "pyside6-designer.exe",
                 scripts / "activate.bat", scripts / "deactivate.bat",
                 dist / "Include", dist / ".gitignore"):
        assert not gone.exists(), f"沒有被清掉：{gone}"
    assert (scripts / "python.exe").exists(), "把不該刪的也刪了"
    assert (site / "stephany").exists(), "把程式本體刪掉了"


# ======================================================================
# F-WIN-03 / F-WIN-04：檔案關聯
# ======================================================================
def test_f_win_03_registers_under_the_per_user_classes_root():
    assert "Software\\\\Classes" in SCRIPT or r"Software\Classes" in SCRIPT


def test_f_win_04_the_open_command_quotes_the_file_argument():
    """沒有引號的話，路徑含空白的檔案會被拆成好幾個參數。"""
    assert '"%1"' in SCRIPT


def test_f_win_03_covers_plain_text_and_source_files():
    for extension in (".txt", ".py", ".md", ".json"):
        assert extension in SCRIPT, extension


def test_f_win_03_does_not_steal_the_default_handler():
    """只登記到「開啟方式」清單，不改使用者原本的預設程式
    （對應 macOS 的 LSHandlerRank = Alternate）。"""
    for forbidden in ("UserChoice", "FileExts", "OpenWithProgids"):
        assert forbidden not in CODE, forbidden


# ======================================================================
# F-WIN-06：解除安裝
# ======================================================================
def test_f_win_06_uninstall_exists_and_removes_all_three_things():
    assert "--uninstall" in SCRIPT
    for what in ("Classes", "Programs", "lnk"):
        assert what in SCRIPT, what


@windows_only
def test_f_win_06_uninstall_really_removes_everything_it_should(
    build_win, tmp_path, monkeypatch
):
    """原本只是拿正規表示式掃 `uninstall()` 的原始碼——`uninstall()` 本身
    從來沒被執行過，而且把 `rmtree` 寫在 `config_dir()` **前面**就繞過去了。

    改成真的跑一次：假的安裝目錄、假的捷徑、測試專用的登錄機碼。
    """
    import winreg

    install_dir = tmp_path / "Programs" / "StephanyEditor"
    (install_dir / "Scripts").mkdir(parents=True)
    (install_dir / "build-info.json").write_text("{}", encoding="utf-8")
    shortcut = tmp_path / "Start Menu" / "Stephany Editor.lnk"
    shortcut.parent.mkdir(parents=True)
    shortcut.write_bytes(b"")
    test_key = r"Software\Classes\Applications\stephany-editor-UNINST.exe"
    winreg.CreateKey(
        winreg.HKEY_CURRENT_USER, test_key + r"\shell\open\command"
    ).Close()

    config_dir = tmp_path / "設定"
    config_dir.mkdir()
    (config_dir / "macros.json").write_text("[]", encoding="utf-8")

    monkeypatch.setattr(build_win, "INSTALL_DIR", install_dir)
    monkeypatch.setattr(build_win, "SHORTCUT", shortcut)
    monkeypatch.setattr(build_win, "APP_KEY", test_key)
    monkeypatch.setenv(platforms.CONFIG_DIR_ENV, str(config_dir))

    try:
        build_win.uninstall()

        assert not install_dir.exists(), "安裝目錄沒有被移除"
        assert not shortcut.exists(), "捷徑沒有被移除"
        with pytest.raises(FileNotFoundError):
            winreg.OpenKey(winreg.HKEY_CURRENT_USER, test_key).Close()

        # F-WIN-06 的括號：設定與巨集是使用者的資料，不該被連坐
        assert config_dir.exists(), "把使用者的設定目錄刪掉了"
        assert (config_dir / "macros.json").exists(), "把使用者的巨集刪掉了"
    finally:
        build_win.delete_key_tree(winreg.HKEY_CURRENT_USER, test_key)


@windows_only
def test_f_win_06_uninstalling_something_that_is_not_installed_is_quiet(
    build_win, tmp_path, monkeypatch
):
    """沒裝過就解除安裝，不該丟例外。"""
    monkeypatch.setattr(build_win, "INSTALL_DIR", tmp_path / "沒有這個")
    monkeypatch.setattr(build_win, "SHORTCUT", tmp_path / "沒有這個.lnk")
    monkeypatch.setattr(
        build_win, "APP_KEY",
        r"Software\Classes\Applications\stephany-editor-NOPE2.exe",
    )
    build_win.uninstall()


# ======================================================================
# 圖示：與 Linux／macOS 同一個 SVG（SRS-004 D-06）
# ======================================================================
def test_icons_come_from_the_same_single_svg():
    assert "make-icons.py" in SCRIPT or "make_icons" in SCRIPT
    assert "stephany-editor.svg" in SCRIPT


def test_make_icons_gained_an_ico_mode():
    text = MAKE_ICONS.read_text(encoding="utf-8")
    assert "--ico" in text


# -- .ico 產生器本身（需要 Qt）----------------------------------------
@pytest.fixture(scope="module")
def ico_bytes(tmp_path_factory):
    pytest.importorskip("PySide6")
    import subprocess

    out = tmp_path_factory.mktemp("icons") / "stephany-editor.ico"
    import os

    result = subprocess.run(
        [sys.executable, str(MAKE_ICONS),
         str(ROOT / "stephany" / "resources" / "stephany-editor.svg"),
         str(out), "--ico"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen",
             "PYTHONIOENCODING": "utf-8"},
    )
    assert result.returncode == 0, result.stderr
    return out.read_bytes()


def test_the_ico_has_a_valid_header(ico_bytes):
    reserved, kind, count = struct.unpack("<HHH", ico_bytes[:6])
    assert reserved == 0
    assert kind == 1, "type 必須是 1（圖示），2 是滑鼠游標"
    assert count >= 5, f"只有 {count} 種尺寸"


def test_the_ico_carries_every_size_windows_asks_for(ico_bytes):
    """16 是檔案總管的小圖示、32 是捷徑、256 是「超大圖示」檢視。"""
    count = struct.unpack("<H", ico_bytes[4:6])[0]
    sizes = set()
    for i in range(count):
        entry = ico_bytes[6 + i * 16 : 6 + (i + 1) * 16]
        width = entry[0] or 256  # ICO 用 0 表示 256
        sizes.add(width)
    for expected in (16, 32, 48, 256):
        assert expected in sizes, f"缺少 {expected}x{expected}：{sorted(sizes)}"


def test_every_ico_entry_points_inside_the_file(ico_bytes):
    """目錄寫錯的話 Windows 只會顯示成空白圖示，不會報錯——直接驗。"""
    count = struct.unpack("<H", ico_bytes[4:6])[0]
    for i in range(count):
        entry = ico_bytes[6 + i * 16 : 6 + (i + 1) * 16]
        size, offset = struct.unpack("<II", entry[8:16])
        assert offset + size <= len(ico_bytes)
        payload = ico_bytes[offset : offset + size]
        assert payload[:8] == b"\x89PNG\r\n\x1a\n", "應為 PNG 壓縮的圖示項目"


# ======================================================================
# 對「真的建出來的那棵樹」的驗證
# ======================================================================
# 上面那些測試看的是腳本寫了什麼，這一段看的是跑完之後長什麼樣。
# 沒建過就 skip——建一次要下載 200 MB，不該綁在每次跑測試上。


@windows_only
@needs_build
def test_d_w1_the_built_tree_has_its_own_executable():
    exe = DIST / "Scripts" / f"{APP_ID}.exe"
    assert exe.exists(), "沒有專屬執行檔，工作管理員會顯示成 pythonw"
    assert (DIST / "Scripts" / f"{APP_ID}-cli.exe").exists()


@windows_only
@needs_build
def test_d_w2_the_renamed_interpreter_still_finds_its_venv():
    """改名會不會讓 Python 找不到 pyvenv.cfg／site-packages——直接問它。"""
    import subprocess

    result = subprocess.run(
        [str(DIST / "Scripts" / f"{APP_ID}-cli.exe"), "-c",
         "import sys, stephany; print(sys.prefix); print(stephany.__version__)"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert result.returncode == 0, result.stderr
    prefix, version = result.stdout.split()
    assert Path(prefix) == DIST
    assert version == __version__


@windows_only
@needs_build
def test_f_win_05_the_cli_entry_point_takes_arguments():
    """macOS 的進入點吃不到參數（所以才要 sitecustomize）；Windows 吃得到，
    這是 D-W2 的實證——`--version` 必須印出本程式的版本，不是 Python 的。"""
    import subprocess

    result = subprocess.run(
        [str(DIST / "Scripts" / f"{APP_ID}-cli.exe"), "-m", "stephany", "--version"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"Stephany Editor {__version__}"


@windows_only
@needs_build
def test_the_build_records_what_it_produced():
    """建構戳記：記下版本、Python 版本與建構時間。

    除了「這是哪一版」這個實用價值之外，下一個測試要靠它的時間戳分辨
    「建構留下的」與「跑過之後才產生的」位元碼。
    """
    import json

    info = json.loads((DIST / "build-info.json").read_text(encoding="utf-8"))
    assert info["version"] == __version__
    assert info["app_id"] == APP_ID
    assert info["built_at"]
    assert info["python"]


@windows_only
@needs_build
def test_br_win_2_the_built_tree_has_no_build_time_leftovers():
    """BR-WIN-2 管的是**建構**期的殘留。

    `__pycache__` 要分兩種：建構過程留下來的（該清掉），與使用者跑過之後
    Python 自己寫的（很正常，清不掉也不該清）。用建構戳記的時間分辨——
    戳記是建構的最後一步寫的，比它新的位元碼就是跑出來的。

    這個區別不是為了漂亮：CI 的「終端機進入點可以執行」那一步就在本測試
    之前，跑過之後必然留下位元碼。少了這個判斷，CI 一定紅燈。
    """
    import json

    stamp = (DIST / "build-info.json").stat().st_mtime

    leftovers = [
        str(path)
        for path in list(DIST.rglob("__pycache__")) + list(DIST.rglob("*.pyc"))
        if path.stat().st_mtime <= stamp
    ]
    for name in ("pip", "setuptools", "pkg_resources", "_distutils_hack"):
        leftovers += [str(p) for p in DIST.glob(f"Lib/site-packages/{name}")]
    assert not leftovers, leftovers
    # 戳記本身要讀得動，順便確認上面用的是同一個檔案
    json.loads((DIST / "build-info.json").read_text(encoding="utf-8"))


@windows_only
@needs_build
def test_br_win_2_the_developer_tools_are_not_shipped():
    """PySide6 帶了二十幾個 pyside6-*.exe（designer、uic、rcc…），
    那些是開發工具，使用者的安裝裡不需要。"""
    tools = sorted(p.name for p in (DIST / "Scripts").glob("pyside6-*.exe"))
    assert not tools, tools


@windows_only
@needs_build
def test_br_win_2_the_venv_scaffolding_is_not_shipped():
    """`Include/` 與 activate 腳本是 venv 給開發者用的，安裝裡用不到。"""
    assert not (DIST / "Include").exists()
    assert not list((DIST / "Scripts").glob("activate*"))
    assert not (DIST / ".gitignore").exists()


@windows_only
@needs_build
def test_the_icon_is_next_to_the_executable():
    assert (DIST / f"{APP_ID}.ico").exists()


@windows_only
@needs_build
def test_f_win_05_the_cmd_shim_is_written_with_crlf():
    """cmd.exe 對 LF-only 的批次檔行為不一致，一律用 CRLF。"""
    raw = (DIST / f"{APP_ID}.cmd").read_bytes()
    assert b"\r\n" in raw
    assert raw.count(b"\n") == raw.count(b"\r\n"), "有沒配對的 LF"


# ======================================================================
# 捷徑與登錄機碼的機制驗證（F-WIN-01、F-WIN-03、F-WIN-04）
# ======================================================================
# 這一段不安裝任何東西：捷徑寫到暫存目錄，登錄檔寫到一個測試專用的機碼，
# 測完就刪。驗的是「這套 COM／winreg 程式碼真的做得到它宣稱的事」。


@pytest.fixture(scope="module")
def build_win():
    """把 build-win.py 當模組載進來（檔名有連字號，不能直接 import）。"""
    if not platforms.IS_WINDOWS:
        pytest.skip("只有 Windows 驗得到")
    import importlib.util

    spec = importlib.util.spec_from_file_location("build_win", BUILD_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@windows_only
def test_f_win_01_the_shortcut_carries_the_app_user_model_id(build_win, tmp_path):
    """釘選到工作列的捷徑與執行中的視窗要被認成同一個應用程式，靠的就是
    兩邊的 AppUserModelID 相同（程式那邊由 platforms.set_app_user_model_id
    設定）。`WScript.Shell` 建得出捷徑但設不了這個欄位，所以才自己走 COM。
    """
    lnk = tmp_path / "Stephany Editor.lnk"
    exe = tmp_path / "stephany-editor.exe"
    exe.write_bytes(b"")
    icon = tmp_path / "stephany-editor.ico"
    icon.write_bytes(b"")

    build_win.write_shortcut(lnk, exe, "-m stephany", icon, BUNDLE_ID)

    assert lnk.exists()
    assert build_win.read_shortcut_app_user_model_id(lnk) == BUNDLE_ID


@windows_only
def test_the_shortcut_points_at_the_executable_with_the_right_arguments(
    build_win, tmp_path
):
    """走 -m stephany，參數才會完整交給 argparse（D-W2）。"""
    import ctypes
    from ctypes import byref, c_void_p, c_wchar_p

    lnk = tmp_path / "捷徑.lnk"
    exe = tmp_path / "stephany-editor.exe"
    exe.write_bytes(b"")
    icon = tmp_path / "icon.ico"
    icon.write_bytes(b"")
    build_win.write_shortcut(lnk, exe, "-m stephany", icon, BUNDLE_ID)

    # 讀回 target 與 arguments
    link = c_void_p()
    build_win._ole32.CoCreateInstance(
        byref(build_win.GUID(build_win.CLSID_SHELL_LINK)), None, 1,
        byref(build_win.GUID(build_win.IID_SHELL_LINK_W)), byref(link),
    )
    persist = build_win._query_interface(link, build_win.IID_PERSIST_FILE)
    build_win._vcall(persist, 5, c_wchar_p, ctypes.wintypes.DWORD)(
        persist, str(lnk), 0
    )
    buf = ctypes.create_unicode_buffer(1024)
    build_win._vcall(link, 3, c_wchar_p, ctypes.c_int, c_void_p, ctypes.c_int)(
        link, buf, 1024, None, 0
    )  # GetPath
    assert buf.value.lower() == str(exe).lower()

    args = ctypes.create_unicode_buffer(1024)
    build_win._vcall(link, 10, c_wchar_p, ctypes.c_int)(link, args, 1024)
    assert args.value == "-m stephany"


@windows_only
def test_f_win_04_the_registered_open_command_survives_a_path_with_spaces(
    build_win, tmp_path, monkeypatch
):
    """「開啟方式」送進來的路徑常常含空白（例如「我的 文件」）。
    命令字串裡的 "%1" 沒有引號的話會被拆成好幾個參數。
    """
    import winreg

    test_key = r"Software\Classes\Applications\stephany-editor-TEST.exe"
    monkeypatch.setattr(build_win, "APP_KEY", test_key)
    exe = tmp_path / "有 空白的目錄" / "stephany-editor.exe"
    exe.parent.mkdir()
    exe.write_bytes(b"")
    icon = tmp_path / "icon.ico"
    icon.write_bytes(b"")

    try:
        build_win.register_file_types(exe, icon)

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, test_key + r"\shell\open\command"
        ) as key:
            command = winreg.QueryValueEx(key, None)[0]
        assert command == f'"{exe}" -m stephany "%1"'
        assert command.endswith('"%1"')

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, test_key + r"\SupportedTypes"
        ) as key:
            count = winreg.QueryInfoKey(key)[1]
            names = {winreg.EnumValue(key, i)[0] for i in range(count)}
        assert ".txt" in names and ".py" in names

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, test_key) as key:
            assert winreg.QueryValueEx(key, "FriendlyAppName")[0] == "Stephany Editor"
    finally:
        build_win.delete_key_tree(winreg.HKEY_CURRENT_USER, test_key)


@windows_only
def test_f_win_06_delete_key_tree_removes_nested_keys(build_win):
    """winreg 只刪得掉空的機碼；解除安裝要能整棵砍掉。"""
    import winreg

    root = r"Software\Classes\Applications\stephany-editor-TEST2.exe"
    winreg.CreateKey(winreg.HKEY_CURRENT_USER, root + r"\shell\open\command").Close()
    try:
        assert build_win.delete_key_tree(winreg.HKEY_CURRENT_USER, root) is True
        with pytest.raises(FileNotFoundError):
            winreg.OpenKey(winreg.HKEY_CURRENT_USER, root).Close()
    finally:
        build_win.delete_key_tree(winreg.HKEY_CURRENT_USER, root)


@windows_only
def test_delete_key_tree_is_quiet_about_a_key_that_is_not_there(build_win):
    """解除安裝一個沒裝過的東西不該炸開。"""
    import winreg

    assert build_win.delete_key_tree(
        winreg.HKEY_CURRENT_USER,
        r"Software\Classes\Applications\stephany-editor-NOPE.exe",
    ) is False


# ======================================================================
# NF-W3：CI 要真的在 Windows 上跑
# ======================================================================
CI = ROOT / ".github" / "workflows" / "ci.yml"


def test_nf_w3_ci_runs_the_tests_on_a_windows_runner():
    """字型度量、選單助憶鍵搶快速鍵、AppUserModelID——這些差異在 Linux 上
    跑一百次也不會發現，跟 SRS-005 NF-03 要求 macOS runner 是同一個理由。
    """
    text = CI.read_text(encoding="utf-8")
    assert "windows-latest" in text


def test_nf_w3_the_windows_job_does_not_use_the_offscreen_plugin():
    """Windows 的 offscreen 字型資料庫是空的（D-W9）：設了它，字型測試會
    安靜地全部 skip，CI 綠燈但什麼都沒驗到。

    做法是逐一檢查每個 job 區塊：Linux 的兩個 job 需要 offscreen，
    Windows 的不行。
    """
    import re

    text = CI.read_text(encoding="utf-8")
    # 以兩個空白縮排的 job 名稱切開
    blocks = re.split(r"\n  (?=[a-z0-9-]+:\n)", text)
    windows_blocks = [b for b in blocks if "windows-latest" in b]
    assert windows_blocks, "找不到 Windows job"
    for block in windows_blocks:
        assert "QT_QPA_PLATFORM: offscreen" not in block, (
            "Windows job 不得設 offscreen（SRS-006 D-W9）"
        )


def test_the_windows_job_builds_the_installation_too():
    """F-WIN-10：建構腳本要能在乾淨的 Windows 上、沒有額外工具、
    不需提權的情況下跑起來——這件事只有 CI 驗得到。"""
    text = CI.read_text(encoding="utf-8")
    assert "build-win.py" in text


# ======================================================================
# NF-W4：中文訊息在非 UTF-8 的主控台不得炸開
# ======================================================================
@windows_only
def test_nf_w4_make_icons_survives_a_non_utf8_console(tmp_path):
    """make-icons.py 成功時會印一行中文到 stdout，而 build-win.py 是用
    子行程呼叫它、stdout 直接繼承下去——所以它炸開就等於建構失敗。

    這裡刻意走真的產生 .ico 的路徑：用 `--help` 測不到，因為用法說明是
    印到 stderr 的，而 stderr 預設就是 backslashreplace，本來就不會炸。
    """
    import os
    import subprocess

    result = subprocess.run(
        [sys.executable, str(MAKE_ICONS),
         str(ROOT / "stephany" / "resources" / "stephany-editor.svg"),
         str(tmp_path / "out.ico"), "--ico"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "cp1252",
             "QT_QPA_PLATFORM": "offscreen"},
    )
    assert "UnicodeEncodeError" not in result.stderr, result.stderr
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "out.ico").exists()


@windows_only
@pytest.mark.parametrize("script", ["build-win.py"])
def test_nf_w4_the_scripts_survive_a_non_utf8_console(script):
    """GitHub 的 windows runner 是 en-US 映像，主控台字碼頁是 cp1252，
    而本專案的訊息全是中文——`print()` 會直接 UnicodeEncodeError 中止。

    NF-W4 當初寫「中文訊息在 cmd 與 PowerShell 的編碼行為都不可靠」是
    選用 Python 的理由，但光是用 Python 並不會自動解決，腳本得自己把
    輸出串流轉成 UTF-8。

    這裡用 PYTHONIOENCODING=cp1252 重現 runner 的環境（本機是 cp950，
    編得出中文，測不出來）。
    """
    import os
    import subprocess

    result = subprocess.run(
        [sys.executable, str(ROOT / "packaging" / script), "--help"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "cp1252"},
    )
    assert "UnicodeEncodeError" not in result.stderr, result.stderr
    assert result.returncode in (0, 2), result.stderr


# ======================================================================
# 安全性／穩健性（code review 指出的實質問題）
# ======================================================================
def test_the_path_advice_does_not_corrupt_the_user_path():
    """`setx PATH "%PATH%;..."` 是有名的 PATH 殺手：

    * 在 cmd 裡 `%PATH%` 展開的是「系統 + 使用者」合併後的值，執行下去等於
      把整份系統 PATH 複製一份到使用者 PATH；日後系統 PATH 更新就再也吃不到。
    * `setx` 超過 1024 個字元會**靜默截斷**。

    安裝腳本不該印一行會弄壞使用者環境的指令。
    """
    assert "setx" not in CODE, "不要建議使用者用 setx 改 PATH"
    assert "%PATH%" not in CODE
    assert "setx" in SCRIPT, "註解裡要說明為什麼不用它"


def test_the_path_advice_reads_only_the_user_scope():
    """正確做法是只讀寫 User 範圍的 Path，不要碰到系統的那一份。"""
    assert 'GetEnvironmentVariable("Path", "User")' in SCRIPT
    assert '"User"' in SCRIPT


@windows_only
def test_the_com_helper_releases_what_it_creates(build_win, tmp_path):
    """`write_shortcut()` 在測試裡會被重複呼叫；介面指標與 PROPVARIANT
    的記憶體若不釋放，就是一路漏到行程結束。"""
    assert "_release(" in CODE, "沒有釋放 COM 介面指標"
    assert "CoTaskMemFree" in CODE, "PROPVARIANT 的字串沒有釋放"
    assert "CoUninitialize" in CODE, "CoInitialize 沒有配對"

    # 連續呼叫多次不得出錯（漏了 Release 不會當場壞，但至少確認沒改壞）
    exe = tmp_path / "stephany-editor.exe"
    exe.write_bytes(b"")
    icon = tmp_path / "i.ico"
    icon.write_bytes(b"")
    for i in range(20):
        lnk = tmp_path / f"s{i}.lnk"
        build_win.write_shortcut(lnk, exe, "-m stephany", icon, BUNDLE_ID)
        assert build_win.read_shortcut_app_user_model_id(lnk) == BUNDLE_ID


@windows_only
def test_reinstalling_while_the_editor_is_running_says_so(build_win, tmp_path,
                                                          monkeypatch):
    """重裝時若舊的執行檔正被使用中，`shutil.rmtree` 會丟
    PermissionError 的 traceback，使用者看不懂。要給一句人話。"""
    install_dir = tmp_path / "Programs" / "StephanyEditor"
    install_dir.mkdir(parents=True)
    locked = install_dir / "locked.exe"
    locked.write_bytes(b"x")

    monkeypatch.setattr(build_win, "INSTALL_DIR", install_dir)
    monkeypatch.setattr(build_win, "DIST", tmp_path / "dist")
    (tmp_path / "dist").mkdir()

    def boom(*args, **kwargs):
        raise PermissionError(13, "程序無法存取檔案，因為它正由另一個程序使用")

    monkeypatch.setattr(build_win.shutil, "rmtree", boom)

    with pytest.raises(SystemExit):
        build_win.install()
