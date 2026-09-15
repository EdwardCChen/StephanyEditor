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

"""建置 Stephany Editor 的 Windows 安裝（SRS-006 D-W1 ~ D-W3、F-WIN-*）。

刻意只用 `python -m venv` 與標準函式庫的 `ctypes`／`winreg`，不經任何
第三方打包工具或 COM 套件——與 SRS-004（不用 debhelper）、SRS-005（不用
py2app）是同一個取捨：建構主機不必先裝東西，也不需要系統管理員。
代價與 macOS 的 `.app` 完全相同：產出的安裝相依「這台機器上有 Python」。

為什麼是 Python 而不是 .bat／.ps1（NF-W4）：本專案的訊息全是中文，而
cmd 與 PowerShell 的編碼行為都不可靠；Python 本來就是硬相依，用它寫沒有
額外成本。

用法：
    python packaging/build-win.py                建到 dist/StephanyEditor
    python packaging/build-win.py --install      建完後安裝到使用者目錄
    python packaging/build-win.py --uninstall    解除安裝
    python packaging/build-win.py --install --shortcut-only   只重建捷徑與關聯
"""

from __future__ import annotations

import argparse
import ctypes
import os
import shutil
import struct  # noqa: F401  與 make-icons 的 .ico 格式共用知識，見 make_icon()
import subprocess
import sys
import venv
import winreg
from ctypes import POINTER, byref, c_void_p, c_wchar_p
from ctypes.wintypes import BYTE, DWORD, WORD
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from stephany import APP_ID, BUNDLE_ID, __version__  # noqa: E402

APP_NAME = "Stephany Editor"

#: 給自己一個專屬的執行檔——沒有它，工作管理員與工作列會顯示成 pythonw
#: （SRS-006 D-W1）
EXE_NAME = f"{APP_ID}.exe"
CLI_EXE_NAME = f"{APP_ID}-cli.exe"
CMD_NAME = f"{APP_ID}.cmd"
ICO_NAME = f"{APP_ID}.ico"

DIST = ROOT / "dist" / "StephanyEditor"

#: 安裝位置。使用者自己的目錄，所以不需要提權（BR-WIN-6、F-WIN-10）。
INSTALL_ROOT = Path(
    os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
)
INSTALL_DIR = INSTALL_ROOT / "Programs" / "StephanyEditor"

START_MENU = (
    Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
    / "Microsoft" / "Windows" / "Start Menu" / "Programs"
)
SHORTCUT = START_MENU / f"{APP_NAME}.lnk"

#: 要出現在「開啟方式」清單裡的副檔名（F-WIN-03）。
#: 只登記到這個程式自己的 Applications 機碼底下，不碰使用者的預設程式設定
#: ——對應 macOS 的 LSHandlerRank = Alternate。
SUPPORTED_TYPES = (
    ".txt", ".text", ".log", ".md", ".csv", ".ini", ".conf", ".cfg",
    ".py", ".pyw", ".js", ".ts", ".json", ".xml", ".yaml", ".yml",
    ".c", ".h", ".cpp", ".hpp", ".cs", ".java", ".go", ".rs",
    ".sh", ".bat", ".ps1", ".sql", ".html", ".css", ".toml",
)

#: 每個使用者自己的類別根，寫這裡不需要提權（BR-WIN-6）
CLASSES = r"Software\Classes"
APP_KEY = rf"{CLASSES}\Applications\{EXE_NAME}"


def fail(message: str) -> None:
    print(f"錯誤：{message}", file=sys.stderr)
    raise SystemExit(1)


def check_platform() -> None:
    if os.name != "nt":
        fail("這個腳本只能在 Windows 上執行（Linux 用 build-deb.sh，macOS 用 build-app.sh）。")
    if sys.version_info < (3, 10):
        fail(
            f"需要 Python 3.10 以上，目前是 {sys.version.split()[0]}。"
        )


# ======================================================================
# 建置
# ======================================================================
def build() -> Path:
    """在 dist/StephanyEditor 底下做出一份可以直接跑的安裝。"""
    print(f"==> 建置 {APP_NAME} {__version__}")
    print(f"    直譯器：{sys.executable}（{sys.version.split()[0]}）")

    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.parent.mkdir(parents=True, exist_ok=True)

    # --copies：不要用 symlink，整包目錄之後要被搬到別的位置
    venv.EnvBuilder(with_pip=True, symlinks=False).create(DIST)
    scripts = DIST / "Scripts"

    print("==> 安裝相依套件")
    subprocess.run(
        [str(scripts / "python.exe"), "-m", "pip", "install", "--quiet",
         "--upgrade", "pip"],
        check=True,
    )
    subprocess.run(
        [str(scripts / "python.exe"), "-m", "pip", "install", "--quiet",
         "-r", str(ROOT / "requirements.txt")],
        check=True,
    )

    # --- 程式碼本體直接放進 site-packages，不必再靠 PYTHONPATH ---
    site = next(DIST.glob("Lib/site-packages"))
    shutil.copytree(
        ROOT / "stephany",
        site / "stephany",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )

    # --- D-W1：專屬執行檔 ---
    # 改名後的直譯器仍然認得 ..\pyvenv.cfg，site-packages 也照樣找得到，
    # 而且**命令列參數完整保留**——所以 Windows 不需要 macOS 那套
    # sitecustomize 進入點（D-W2）。
    shutil.copy2(scripts / "pythonw.exe", scripts / EXE_NAME)  # GUI：不開主控台
    shutil.copy2(scripts / "python.exe", scripts / CLI_EXE_NAME)  # 終端機用

    # --- F-WIN-05：終端機指令 ---
    (DIST / CMD_NAME).write_text(
        "@echo off\r\n"
        "rem Stephany Editor 的終端機進入點（SRS-006 F-WIN-05）。\r\n"
        "rem 走 -m stephany，命令列參數才會完整交給 argparse。\r\n"
        f'"%~dp0Scripts\\{CLI_EXE_NAME}" -m stephany %*\r\n',
        encoding="utf-8",
        newline="",
    )

    make_icon(DIST / ICO_NAME, python=scripts / "python.exe")

    # --- 文件與授權 ---
    for name in ("README.md", "LICENSE"):
        shutil.copy2(ROOT / name, DIST / name)

    strip_build_artifacts(site)

    size = sum(f.stat().st_size for f in DIST.rglob("*") if f.is_file())
    print(f"==> 完成：{DIST}（{size / 1024 / 1024:.0f} MB）")
    return DIST


def make_icon(target: Path, python: Path) -> None:
    """用同一個 SVG 產生 .ico（SRS-004 D-06 的延伸）。"""
    subprocess.run(
        [str(python), str(ROOT / "packaging" / "make-icons.py"),
         str(ROOT / "stephany" / "resources" / "stephany-editor.svg"),
         str(target), "--ico"],
        check=True,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
    )


def strip_build_artifacts(site: Path) -> None:
    """BR-WIN-2：建構期才需要的東西不該留在安裝裡。"""
    for pattern in ("pip", "pip-*.dist-info", "setuptools", "setuptools-*.dist-info",
                    "pkg_resources", "_distutils_hack"):
        for path in site.glob(pattern):
            shutil.rmtree(path, ignore_errors=True) if path.is_dir() else path.unlink()
    for path in site.glob("distutils-precedence.pth"):
        path.unlink()
    for cache in DIST.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)
    for pyc in DIST.rglob("*.pyc"):
        pyc.unlink(missing_ok=True)
    # pip 自己的執行檔沒了 pip 套件也沒用
    for stale in (DIST / "Scripts").glob("pip*.exe"):
        stale.unlink(missing_ok=True)

    # PySide6 帶了二十幾個開發工具（designer、uic、rcc、qmllint…）。
    # 使用者的安裝裡一個都用不到，留著只是讓安裝變大也變雜。
    for tool in (DIST / "Scripts").glob("pyside6-*.exe"):
        tool.unlink(missing_ok=True)

    # venv 給開發者用的鷹架：Include/ 是給編譯擴充模組的標頭檔，
    # activate 系列是給互動式 shell 的，這裡的進入點是 Scripts/ 裡的
    # 專屬執行檔，兩者都用不到。
    shutil.rmtree(DIST / "Include", ignore_errors=True)
    for script in (DIST / "Scripts").glob("activate*"):
        script.unlink(missing_ok=True)
    (DIST / "Scripts" / "deactivate.bat").unlink(missing_ok=True)
    # venv 會在自己的根目錄放一個 .gitignore（與 macOS 的 .app 同樣的處理）
    (DIST / ".gitignore").unlink(missing_ok=True)


# ======================================================================
# 捷徑（含 AppUserModelID）
# ======================================================================
# 只用 ctypes 走 COM，不拉任何第三方套件進來（D-W3）。
# `WScript.Shell` 建得出捷徑，但設不了 System.AppUserModel.ID——而那正是
# 讓「釘選的捷徑」與「執行中的視窗」被 Windows 認成同一個應用程式的欄位。
_ole32 = ctypes.OleDLL("ole32")
_mem = ctypes.WinDLL("ole32")
_mem.CoTaskMemAlloc.restype = c_void_p
_mem.CoTaskMemAlloc.argtypes = [ctypes.c_size_t]

VT_LPWSTR = 31


class GUID(ctypes.Structure):
    _fields_ = [("d1", DWORD), ("d2", WORD), ("d3", WORD), ("d4", BYTE * 8)]

    def __init__(self, text: str):
        super().__init__()
        _ole32.CLSIDFromString(text, byref(self))


class PROPERTYKEY(ctypes.Structure):
    _fields_ = [("fmtid", GUID), ("pid", DWORD)]


class PROPVARIANT(ctypes.Structure):
    _fields_ = [("vt", WORD), ("r1", WORD), ("r2", WORD), ("r3", WORD),
                ("p", c_void_p), ("p2", c_void_p)]


CLSID_SHELL_LINK = "{00021401-0000-0000-C000-000000000046}"
IID_SHELL_LINK_W = "{000214F9-0000-0000-C000-000000000046}"
IID_PERSIST_FILE = "{0000010b-0000-0000-C000-000000000046}"
IID_PROPERTY_STORE = "{886d8eeb-8cf2-4446-8d02-cdba1dbdcf99}"
FMTID_APP_USER_MODEL = "{9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}"

# IShellLinkW 的 vtable 位置（0~2 是 IUnknown）
_SET_WORKING_DIRECTORY = 9
_SET_ARGUMENTS = 11
_SET_ICON_LOCATION = 17
_SET_PATH = 20
# IPersistFile
_PERSIST_SAVE = 6
# IPropertyStore
_STORE_SET_VALUE = 6
_STORE_COMMIT = 7


def _vcall(obj, index, *argtypes):
    table = ctypes.cast(obj, POINTER(POINTER(c_void_p)))[0]
    proto = ctypes.WINFUNCTYPE(ctypes.HRESULT, c_void_p, *argtypes)
    return proto(table[index])


def _query_interface(obj, iid: str) -> c_void_p:
    out = c_void_p()
    _vcall(obj, 0, c_void_p, c_void_p)(obj, byref(GUID(iid)), byref(out))
    return out


def write_shortcut(path: Path, target: Path, arguments: str, icon: Path,
                   app_user_model_id: str) -> None:
    """建一個帶圖示與 AppUserModelID 的 .lnk。

    圖示要另外指定，是因為我們的執行檔是 pythonw.exe 改名來的，裡面內嵌的
    還是 Python 的圖示；.lnk 自己的 IconLocation 會蓋過它。
    """
    _ole32.CoInitialize(None)
    link = c_void_p()
    _ole32.CoCreateInstance(
        byref(GUID(CLSID_SHELL_LINK)), None, 1,
        byref(GUID(IID_SHELL_LINK_W)), byref(link),
    )
    _vcall(link, _SET_PATH, c_wchar_p)(link, str(target))
    _vcall(link, _SET_ARGUMENTS, c_wchar_p)(link, arguments)
    _vcall(link, _SET_WORKING_DIRECTORY, c_wchar_p)(link, str(target.parent))
    _vcall(link, _SET_ICON_LOCATION, c_wchar_p, ctypes.c_int)(link, str(icon), 0)

    store = _query_interface(link, IID_PROPERTY_STORE)
    key = PROPERTYKEY(GUID(FMTID_APP_USER_MODEL), 5)  # PKEY_AppUserModel_ID
    encoded = app_user_model_id.encode("utf-16-le") + b"\x00\x00"
    buffer = _mem.CoTaskMemAlloc(len(encoded))
    ctypes.memmove(buffer, encoded, len(encoded))
    value = PROPVARIANT()
    value.vt = VT_LPWSTR
    value.p = buffer
    _vcall(store, _STORE_SET_VALUE, POINTER(PROPERTYKEY), POINTER(PROPVARIANT))(
        store, byref(key), byref(value)
    )
    _vcall(store, _STORE_COMMIT)(store)

    persist = _query_interface(link, IID_PERSIST_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    _vcall(persist, _PERSIST_SAVE, c_wchar_p, ctypes.c_int)(persist, str(path), 1)


def read_shortcut_app_user_model_id(path: Path) -> str | None:
    """讀回 .lnk 上的 AppUserModelID——寫進去了沒有，直接問 Windows。"""
    _PERSIST_LOAD, _STORE_GET_VALUE = 5, 5
    _ole32.CoInitialize(None)
    link = c_void_p()
    _ole32.CoCreateInstance(
        byref(GUID(CLSID_SHELL_LINK)), None, 1,
        byref(GUID(IID_SHELL_LINK_W)), byref(link),
    )
    persist = _query_interface(link, IID_PERSIST_FILE)
    _vcall(persist, _PERSIST_LOAD, c_wchar_p, DWORD)(persist, str(path), 0)
    store = _query_interface(link, IID_PROPERTY_STORE)
    key = PROPERTYKEY(GUID(FMTID_APP_USER_MODEL), 5)
    value = PROPVARIANT()
    _vcall(store, _STORE_GET_VALUE, POINTER(PROPERTYKEY), POINTER(PROPVARIANT))(
        store, byref(key), byref(value)
    )
    if value.vt != VT_LPWSTR or not value.p:
        return None
    return ctypes.cast(value.p, c_wchar_p).value


# ======================================================================
# 安裝
# ======================================================================
def install(shortcut_only: bool = False) -> None:
    if not shortcut_only:
        if not DIST.exists():
            fail("還沒建置，先跑一次不帶參數的 build-win.py。")
        print(f"==> 安裝到 {INSTALL_DIR}")
        if INSTALL_DIR.exists():
            shutil.rmtree(INSTALL_DIR)
        INSTALL_DIR.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(DIST, INSTALL_DIR)

    exe = INSTALL_DIR / "Scripts" / EXE_NAME
    icon = INSTALL_DIR / ICO_NAME
    if not exe.exists():
        fail(f"找不到 {exe}，先完整安裝一次。")

    write_shortcut(SHORTCUT, exe, "-m stephany", icon, BUNDLE_ID)
    print(f"==> 已建立捷徑：{SHORTCUT}")

    register_file_types(exe, icon)
    print(f"==> 已登記「開啟方式」：{len(SUPPORTED_TYPES)} 種副檔名")

    print()
    print("終端機指令（F-WIN-05）——把安裝目錄加進 PATH 即可：")
    print(f'    setx PATH "%PATH%;{INSTALL_DIR}"')
    print(f"    之後就能用 {APP_ID} 檔案.txt 開檔")


def register_file_types(exe: Path, icon: Path) -> None:
    """把自己登記到「開啟方式」清單（F-WIN-03、F-WIN-04）。

    全部寫在自己的 Applications 機碼底下，**不碰** 任何副檔名原本的
    預設程式設定——對應 macOS 的 LSHandlerRank = Alternate。
    """
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, APP_KEY) as key:
        winreg.SetValueEx(key, "FriendlyAppName", 0, winreg.REG_SZ, APP_NAME)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{APP_KEY}\DefaultIcon") as key:
        winreg.SetValueEx(key, None, 0, winreg.REG_SZ, f"{icon},0")
    with winreg.CreateKey(
        winreg.HKEY_CURRENT_USER, rf"{APP_KEY}\shell\open\command"
    ) as key:
        # "%1" 一定要有引號，否則路徑含空白的檔案會被拆成好幾個參數
        winreg.SetValueEx(
            key, None, 0, winreg.REG_SZ, f'"{exe}" -m stephany "%1"'
        )
    with winreg.CreateKey(
        winreg.HKEY_CURRENT_USER, rf"{APP_KEY}\SupportedTypes"
    ) as key:
        for extension in SUPPORTED_TYPES:
            winreg.SetValueEx(key, extension, 0, winreg.REG_SZ, "")


# ======================================================================
# 解除安裝（F-WIN-06）
# ======================================================================
def uninstall() -> None:
    """移除安裝目錄、捷徑與登錄機碼。

    **不動** 設定與巨集：那是使用者的資料，放在 %APPDATA%\\StephanyEditor，
    重裝之後還要用（F-WIN-06 的括號）。
    """
    removed = []
    if INSTALL_DIR.exists():
        shutil.rmtree(INSTALL_DIR)
        removed.append(str(INSTALL_DIR))
    if SHORTCUT.exists():
        SHORTCUT.unlink()
        removed.append(str(SHORTCUT))
    if delete_key_tree(winreg.HKEY_CURRENT_USER, APP_KEY):
        removed.append(rf"HKCU\{APP_KEY}")

    if removed:
        print("==> 已移除：")
        for item in removed:
            print(f"    {item}")
    else:
        print("==> 沒有找到已安裝的項目")
    from stephany import platforms

    print()
    print(f"設定與巨集保留在 {platforms.config_dir()}（不隨解除安裝刪除）。")


def delete_key_tree(root, path: str) -> bool:
    """winreg 只能刪空的機碼，子機碼要自己遞迴。"""
    try:
        with winreg.OpenKey(root, path) as key:
            while True:
                try:
                    child = winreg.EnumKey(key, 0)
                except OSError:
                    break
                delete_key_tree(root, rf"{path}\{child}")
    except FileNotFoundError:
        return False
    winreg.DeleteKey(root, path)
    return True


# ======================================================================
def main() -> int:
    parser = argparse.ArgumentParser(
        prog="build-win.py",
        description=f"建置與安裝 {APP_NAME}（Windows）",
    )
    parser.add_argument("--install", action="store_true",
                        help="建完後安裝到使用者目錄並建立捷徑與檔案關聯")
    parser.add_argument("--uninstall", action="store_true",
                        help="移除安裝目錄、捷徑與登錄機碼（設定檔保留）")
    parser.add_argument("--shortcut-only", action="store_true",
                        help="不重新建置，只重做捷徑與檔案關聯")
    args = parser.parse_args()

    check_platform()

    if args.uninstall:
        uninstall()
        return 0
    if args.shortcut_only:
        install(shortcut_only=True)
        return 0

    build()
    if args.install:
        install()
    else:
        print()
        print("加上 --install 可以安裝到使用者目錄並建立「開始」功能表捷徑。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
