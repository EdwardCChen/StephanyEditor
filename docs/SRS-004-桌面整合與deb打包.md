# SRS-004：桌面整合與 deb 打包

| 項目 | 內容 |
|---|---|
| 版本 | 1.0 |
| 狀態 | 已拍板，開發中 |
| 前置 | SRS-001 ~ SRS-003 |

## 1. 背景與問題

兩個相關的問題，根因都是「應用程式沒有告訴桌面環境自己是誰」：

1. **工作列／Dock 顯示成 `python3`**，不是應用程式名稱，也沒有自己的圖示。
   Qt 6 在 Wayland 下以 `QGuiApplication::desktopFileName()` 作為 xdg-shell 的
   `app_id`；這個值目前是空字串，於是退回使用執行檔名稱 `python3`。
2. **沒有安裝檔**，只能從原始碼目錄用 `run.sh` 啟動。

## 2. 拍板決策

| 編號 | 決策 | 理由 |
|---|---|---|
| **D-01** | `app_id` / `.desktop` 檔名 / `StartupWMClass` 三者一律使用 `stephany-editor` | 桌面環境是靠這三者比對才知道「這個視窗屬於那個已安裝的應用程式」。任一不一致，Dock 就會顯示成通用的執行檔名稱 |
| **D-02** | 相依系統的 `python3-pyside6.*` 套件，不在 deb 內打包 venv | Ubuntu 26.04 已收錄 PySide6 6.10；內嵌 venv 會讓套件從約 300 KB 膨脹到 100 MB 以上，且 Qt 無法跟著系統更新拿到安全性修補 |
| **D-03** | 以 `dpkg-deb` 直接組出二進位套件，不用 debhelper | 建構主機不必安裝 debhelper/dh-python/devscripts（那些需要 root 權限），任何 Ubuntu 機器 clone 下來就能建。代價是不適合投稿到官方套件庫，但本專案的目標是自用安裝 |
| **D-04** | 純 Python 程式碼裝到 `/usr/share/stephany-editor/`，`/usr/bin` 只放啟動器 | 與架構無關的資料依 FHS 應放 `/usr/share`；套件標為 `Architecture: all` |
| **D-05** | `fonts-noto-cjk` 列為 Recommends 而非 Depends | 它是欄模式對齊的前提，但體積大（約 60 MB）；apt 預設會安裝 Recommends，且程式本身已在字型不合格時於狀態列警告 |
| **D-06** | 圖示由單一 SVG 在建構時產生各尺寸 PNG | 只維護一個來源檔；產生用 PySide6 自己的 QtSvg，不額外相依 rsvg/inkscape |

## 3. 功能需求

| 編號 | 需求 |
|---|---|
| F-PK-01 | 工作列／Dock 顯示應用程式名稱與自訂圖示，不得顯示為 `python3` |
| F-PK-02 | 提供 `.deb` 安裝檔，`sudo apt install ./檔名.deb` 可完成安裝 |
| F-PK-03 | 安裝後出現在 GNOME 應用程式選單，可由選單啟動 |
| F-PK-04 | 註冊為文字檔的可選開啟方式（`text/plain` 等 MIME） |
| F-PK-05 | 提供 `stephany-editor` 指令，可從終端機開檔 |
| F-PK-06 | `dpkg -r` / `apt remove` 可完整移除，不留殘檔 |
| F-PK-07 | 建構腳本可在未安裝 debhelper 的機器上執行，且不需 root |

## 4. 業務規則

| 編號 | 規則 |
|---|---|
| **BR-PK-1** | 套件版本號取自 `stephany/__init__.py` 的 `__version__`，不得手動同步兩處 |
| **BR-PK-2** | 套件內不得含有 `.venv/`、`__pycache__/`、測試與開發腳本 |
| **BR-PK-3** | 安裝與移除後須更新桌面資料庫與圖示快取，否則選單不會立即出現或殘留 |
| **BR-PK-4** | 檔案擁有者一律為 `root:root`，不得帶入建構者的 uid |

## 5. 非功能需求

| 編號 | 需求 |
|---|---|
| NF-01 | 應用程式身分（app_id、顯示名稱、圖示）須可由測試驗證 |
| NF-02 | `.desktop` 檔與套件中繼資料的一致性須可由測試驗證，不靠人工檢查 |
