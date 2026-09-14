# SRS-005：macOS 支援

| 項目 | 內容 |
|---|---|
| 版本 | 1.0 |
| 狀態 | 已拍板，開發中 |
| 前置 | SRS-001 ~ SRS-004 |

## 1. 背景與問題

同一個人在 Ubuntu 與 macOS 兩台機器上開發，卻用不同的編輯器，切換時操作
會互相打架。本專案已經在 Ubuntu 上可用，缺的是讓同一份原始碼在 macOS 上
也是一個「正常的 Mac 應用程式」。

實際盤點後有六個必須處理的差異，前兩個是會讓核心功能直接壞掉的：

1. **欄模式在 macOS 上一定對不齊。** macOS 沒有內建 `Noto Sans Mono CJK`。
   量測系統內建等寬字型（12pt）的結果：

   | 字型 | 半形寬 | 中文寬 | 比例 |
   |---|---|---|---|
   | Menlo | 7.22 | 12.00 | 1.66 |
   | Monaco | 7.19 | 12.00 | 1.67 |
   | Courier New | 7.19 | 12.00 | 1.67 |
   | Andale Mono | 7.19 | 12.00 | 1.67 |
   | PT Mono | 7.19 | 12.00 | 1.67 |

   這些等寬字型都沒有中文字符，中文是由系統的 CJK 字型（PingFang 等）遞補
   算圖的，而 CJK 字型的中文寬度固定等於字級（12pt → 12.0）。所以只要
   半形寬不是「字級的一半」，比例就不會是 2，整個矩形就是歪的。

2. **⌥（Option）+ 字母／數字在 macOS 會打出字元。** `⌥C` 送出的是 `ç`、
   `⌥0` 是 `º`。欄模式的按鍵處理只擋了 `ctrl`、沒擋 `alt`，於是快速鍵沒攔到時
   會把 `ç` 插進矩形的每一行。

3. **選單列會顯示成腳本名稱。** 與 SRS-004 的「Dock 顯示成 python3」是同一類
   問題的 macOS 版本（見 §2 D-01 的實測）。

4. **Finder 開檔不走 argv。** macOS 雙擊檔案或拖到 Dock 圖示時，檔案是以
   `QFileOpenEvent` 送進來的，目前的 `main()` 只讀 `sys.argv`，所以開不起來。

5. **「關於」「結束」該在應用程式選單裡。** Qt 靠英文字樣猜測 `menuRole`，
   本專案選單是中文，猜不到，兩個項目會留在「檔案」選單，不符 macOS 慣例。

6. **`F1` / `F2` 在筆電上預設要壓 `Fn`。** 書籤與說明的快速鍵因此不好按。
7. **應用程式選單是英文的。** 「About / Services / Hide / Quit」這幾項不是本專案
   建的，是 Qt 依 macOS 慣例自己組出來的；沒載入 Qt 的翻譯時它們是英文，夾在
   一整排中文選單（檔案／編輯／搜尋…）裡特別突兀。`QMessageBox` 的 OK／Cancel
   按鈕也是同一批字串。

## 2. 拍板決策

| 編號 | 決策 | 理由 |
|---|---|---|
| **D-01** | `.app` 的 `CFBundleExecutable` 必須是 **Python 直譯器本體**，不得是 shell 啟動器 | 實測（見下）：用 shell 腳本 `exec` 外部 python 時，`NSBundle.mainBundle` 認不得這個 .app，選單列會顯示成腳本檔名；把直譯器本身放進 `Contents/MacOS/` 就正確顯示 `CFBundleName` |
| **D-02** | venv 直接建在 `Contents/` 之下（`pyvenv.cfg` 與 `MacOS/` 同層），啟動點用 `sitecustomize.py` | 這是讓 D-01 成立的唯一低成本作法：直譯器位於 `Contents/MacOS/`，Python 找 venv 標記時看的是 `../pyvenv.cfg`，剛好就是 `Contents/pyvenv.cfg`。直譯器被 LaunchServices 無參數啟動，所以進入點只能掛在 `sitecustomize` 這個官方 hook 上 |
| **D-03** | 不使用 py2app / PyInstaller，只用 `python3 -m venv` + `iconutil` + `hdiutil` | 與 SRS-004 D-03（不用 debhelper）同一個取捨：建構主機不必安裝額外打包工具，不需要 root，clone 下來就能建。代價是產出的 .app 相依建構時那個 Python 的標準函式庫，適合自用安裝而非對外散布 |
| **D-04** | macOS 的預設字型是 **Osaka Regular-Mono**（系統內建） | 它是 macOS 唯一半形寬剛好等於字級一半的內建等寬字型。實測 9~24pt 全部滿足「中文 = 半形 × 2」，連 Osaka 本身沒有的繁體字、全形標點（由系統字型遞補）也是準的。使用者若已裝 `Sarasa Mono TC` 或 `Noto Sans Mono CJK TC`，優先用那些 |
| **D-05** | 快速鍵不另建一套 macOS 表；沿用 `Ctrl+X` 的可攜寫法讓 Qt 自動對映成 `⌘`，只對「壓不到」與「會誤打字」的鍵補**額外**快速鍵 | Qt 的 `QKeySequence("Ctrl+C")` 在 macOS 會解析成 `⌘C`（已實測）。維護兩套對映表必然會漂移；補充鍵是 `setShortcuts()` 多加一個，原本的鍵仍然有效，跨平台的肌肉記憶不會斷 |
| **D-06** | 巨集與設定放 `~/Library/Application Support/StephanyEditor/`，並提供 `STEPHANY_CONFIG_DIR` 覆寫 | 遵循各平台自己的慣例；想在機器之間共用巨集的人用環境變數指到雲端同步目錄即可 |
| **D-07** | Finder 開檔以 `QFileOpenEvent` 承接，與 argv 走同一條 `open_path()` | macOS 的檔案關聯本來就不經 argv；兩條入口收斂到同一個函式，行為才不會分岔 |
| **D-08** | 平台差異一律集中在 `stephany/platforms.py`，不得散落 `sys.platform` 判斷；`core/` 仍然不得相依 Qt | 與 NF-01「領域核心與 UI 框架分離」同一個理由：差異集中在一處才看得出「這個專案在各平台上到底有幾件事不一樣」 |
| **D-09** | 載入 Qt 內附的 `qtbase_zh_TW` 翻譯，而不是自己去改那幾個選單項目的字 | 那些項目是 Qt 在 `QCocoaMenuItem` 裡用 `QCoreApplication::translate("MAC_APPLICATION_MENU", ...)` 組出來的，本來就設計成由翻譯檔提供；Qt 的繁中翻譯已經有這七個字串（實測涵蓋 About／Quit／Services／Hide／Hide Others／Show All／Preferences），順帶也把 `QMessageBox` 的按鈕變成「確定／取消」。翻譯檔隨 Qt 安裝，不增加相依 |

### D-01 的實測數據

同一支 Qt 程式、同一份 `Info.plist`（`CFBundleName = Stephany Editor`），
只差在 `Contents/MacOS/` 底下放什麼：

| 作法 | `NSBundle.mainBundle` | 選單列顯示 |
|---|---|---|
| shell 腳本 `exec` 專案 `.venv` 的 python | 認到的是 `.venv/bin`，`bundleIdentifier` 為 `None` | **`main.py`** ❌ |
| 直譯器本體放在 `Contents/MacOS/stephany-editor` | 認到 `.app`，`bundleIdentifier` 正確 | **`Stephany Editor`** ✅ |

`QGuiApplication.setApplicationName()` 救不了第一種——Qt 在讀不到
`CFBundleName` 時是退回執行檔／腳本名稱，不是退回 `applicationName`。
這與 SRS-004 D-01 的結論一致：**應用程式身分要由作業系統認得的地方宣告，
不是由程式自己喊。**

## 3. 功能需求

| 編號 | 需求 |
|---|---|
| F-MAC-01 | 選單列、Dock 與「強制結束」清單顯示 `Stephany Editor` 與自訂圖示，不得顯示為 `python3` 或腳本檔名 |
| F-MAC-02 | 提供 `.app`，拖進 `/Applications` 即可使用；建構腳本亦可直接安裝 |
| F-MAC-03 | 在 Finder 的「打開方式」中可選本程式開啟純文字與常見原始碼檔 |
| F-MAC-04 | 從 Finder 雙擊檔案、或把檔案拖到 Dock 圖示，能在既有視窗開新分頁 |
| F-MAC-05 | 提供 `stephany-editor` 終端機指令（指向 .app 內的進入點） |
| F-MAC-06 | 「關於」與「結束」出現在應用程式選單（`Stephany Editor` 選單）而非「檔案」選單 |
| F-MAC-07 | macOS 預設字型須滿足「中文 = 半形 × 2」，開箱即用不必先裝字型 |
| F-MAC-08 | 快速鍵以 `⌘` 為主修飾鍵（`⌘C`／`⌘S`／`⌘F` …），與 macOS 慣例一致 |
| F-MAC-09 | 需要 `Fn` 才壓得到的 `F1`／`F2` 系列快速鍵，須另有不必 `Fn` 的替代鍵 |
| F-MAC-10 | 建構腳本不需 root、不需安裝 py2app／PyInstaller／Xcode 專案 |
| F-MAC-11 | 移除即「把 .app 丟垃圾桶」，不留系統層級殘檔（設定檔除外） |
| F-MAC-12 | 應用程式選單（關於／服務／隱藏／結束）與標準對話框按鈕須與程式其餘介面同為繁體中文 |

## 4. 業務規則

| 編號 | 規則 |
|---|---|
| **BR-MAC-1** | 套件版本號取自 `stephany/__init__.py` 的 `__version__`，`Info.plist` 由樣板在建構時填入，不得手動同步兩處（同 BR-PK-1） |
| **BR-MAC-2** | `.app` 內不得含有 `__pycache__`、`*.pyc`、測試、`pip`／`setuptools` 等建構期套件 |
| **BR-MAC-3** | 欄模式中 `⌥` + 字母／數字所產生的字元不得被當成文字插入矩形（`⌥C` → `ç`、`⌥0` → `º`）；一般模式原本就已排除，兩者須一致 |
| **BR-MAC-4** | 各平台共用同一組快速鍵定義，macOS 只能「增加」替代鍵，不得另建一份完整對映表（D-05） |
| **BR-MAC-5** | `CFBundleIdentifier` 與 Linux 的 `app_id`／`.desktop` 檔名須同源於 `stephany-editor`，不得各自取名 |
| **BR-MAC-6** | 字型偏好清單須包含「字型家族 + 樣式名稱」：`Osaka` 的預設樣式比例是 1.5，只有 `Regular-Mono` 樣式才是 2.0，只記家族名稱會挑到錯的那個 |

## 5. 非功能需求

| 編號 | 需求 |
|---|---|
| NF-01 | 平台差異集中在 `stephany/platforms.py`；該模組不得 import Qt，`core/` 也不得因此相依 Qt |
| NF-02 | `Info.plist` 樣板與程式宣告的識別碼、字型不變量、快速鍵的 `⌘` 對映，須可由測試驗證，不靠人工檢查 |
| NF-03 | CI 須在 macOS runner 上跑全套測試，而非只在 Linux 上跑 |

## 6. 範圍外

- **Windows 支援**：`platforms.py` 已預留分支與設定目錄，但本規格不涵蓋
  `.exe` 打包與實機驗證。
- **程式碼簽章與公證（notarization）**：自用安裝不需要；對外散布才需要
  Apple Developer ID。連 ad-hoc 簽章也不做——`codesign` 會把 bundle 內所有
  非程式碼檔案當成「未簽章的子元件」而整個失敗，而 D-02 必需的
  `Contents/pyvenv.cfg` 正是它不接受的東西。本機自建的 .app 不簽也能跑；
  若把 `.dmg` 拿到別台 Mac，收到端解除隔離即可
  （`xattr -dr com.apple.quarantine`）。
- **App Store 上架**：沙箱化與本專案的「直接開檔案」行為衝突，不考慮。
