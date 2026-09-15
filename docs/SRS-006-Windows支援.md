# SRS-006：Windows 支援

| 項目 | 內容 |
|---|---|
| 版本 | 1.0 |
| 狀態 | 已拍板，開發中 |
| 前置 | SRS-001 ~ SRS-005 |

## 1. 背景與問題

同一個人在 Ubuntu、macOS、Windows 三台機器上工作。前兩個平台已經可用，
Windows 在 SRS-005 §6 被明確列為範圍外——`platforms.py` 留了分支，但那些
分支是**猜的，沒有任何一行在 Windows 上被驗證過**。本規格把它補完。

在 Windows 11（zh-TW，PySide6 6.11.2）上實測後，有六件事要處理。
前兩件會讓現有功能直接壞掉：

1. **`Alt+C`（欄位編輯器）在 Windows 上完全按不到。** 選單列有
   `編碼(&C)`，Windows 的選單助憶鍵優先權高於 `QAction` 的快速鍵，於是
   `Alt+C` 被選單吃掉。實測同一種送鍵方式的對照：

   | 快速鍵 | 動作 | 觸發 |
   |---|---|---|
   | `Ctrl+N` | 開新檔案 | ✅ |
   | `Ctrl+Shift+B` | 黏著式欄選取 | ✅ |
   | `Alt+0` | 全部摺疊 | ✅ |
   | `Alt+1` | 摺疊到第 1 層 | ✅ |
   | **`Alt+C`** | **欄位編輯器** | **❌ 沒有反應** |

   這與 macOS 的 `⌥C` → `ç`（BR-MAC-3）是同一個功能、不同成因的故障：
   三個平台裡有兩個按不到 `Alt+C`。

2. **`platforms.py` 的 Windows 字型清單從來沒被量測過。** 實測後結論是
   「清單內容剛好對，但順序錯、而且漏掉了會踩雷的變體」（見 §2 D-W4）。

3. **工作列與工作管理員會顯示成 `pythonw`。** 這是 SRS-004 D-01
   （Dock 顯示成 `python3`）與 SRS-005 D-01（選單列顯示成 `main.py`）
   在 Windows 上的第三個版本：應用程式身分由作業系統從**執行檔路徑**推導，
   而所有 Python 程式的執行檔路徑都是同一個 `pythonw.exe`。

4. **沒有安裝方式。** Ubuntu 有 `.deb`、macOS 有 `.app`，Windows 目前只能
   從原始碼跑，而 `run.sh` 是 bash 腳本，Windows 沒有。

5. **檔案關聯與「開啟檔案」入口不存在。** 在 Explorer 按右鍵「開啟方式」
   看不到本程式。

6. **`offscreen` 平台外掛在 Windows 上的字型資料庫是空的。** 實測
   `QFontDatabase.families()` 在 `QT_QPA_PLATFORM=offscreen` 下回傳 **0 筆**
   （Linux／macOS 都不是這樣）。所有字型量測的測試會因此「安靜地 skip」——
   CI 全綠，但字型不變量一次都沒被驗過。這是測試基礎設施的問題，不是
   程式的問題，但不處理的話 F-WIN-07 等於沒有把關。

## 2. 拍板決策

| 編號 | 決策 | 理由 |
|---|---|---|
| **D-W1** | 應用程式身分靠「**給自己一個專屬的執行檔**」建立：把 venv 的 `pythonw.exe` 複製成 `stephany-editor.exe`，並額外設定 `AppUserModelID` | 與 SRS-004 D-01、SRS-005 D-01 同一條結論的第三次印證：身分要由作業系統認得的地方宣告。Windows 認的是執行檔路徑——所有 Python 程式共用 `pythonw.exe`，所以必須先有自己的執行檔，工作管理員與工作列才不會顯示成 `pythonw`。`AppUserModelID` 則是讓釘選、跳躍清單與視窗分組對得起來的那把鑰匙 |
| **D-W2** | 進入點就是 `stephany-editor.exe -m stephany <檔案>`，**不需要 macOS 那套 `sitecustomize` hack** | 實測：改名後的 venv 直譯器仍然正確認得 `pyvenv.cfg`、`sys.prefix` 與 site-packages，而且**命令列參數完整保留**。macOS 之所以要 hack，是因為 LaunchServices 啟動時不給任何參數（D-02）；Windows 的 ShellExecute 會給，所以同一個問題在這裡不存在。少一層 hack 就少一處會壞的地方 |
| **D-W3** | 不使用 PyInstaller／cx_Freeze／Nuitka／Inno Setup／WiX；只用 `python -m venv` + 標準函式庫的 `ctypes` | 與 SRS-004 D-03（不用 debhelper）、SRS-005 D-03（不用 py2app）同一個取捨：建構主機不必安裝額外工具、不需要系統管理員。代價與 macOS 完全相同——產出的安裝相依「機器上有 Python 3.10+」，適合自用安裝而非對外散布（§6 有誠實說明） |
| **D-W4** | Windows 的對齊字型清單為 `MingLiU`／`細明體` → `NSimSun`／`SimSun` → `MS Gothic`，退路是 `Consolas` | 實測 9~24pt、跨 19 個字元（含繁中專用字、假名、全形標點、罕用字）全部剛好 2.000。順序改成**繁中優先**：原本猜的清單把日文的 `MS Gothic` 排第一，對一個以繁體中文為主的編輯器是錯的優先序。`Consolas`（1.82）、`Cascadia Mono`（1.71）、`Courier New`（1.67）、`Lucida Console`（1.66）全部不合格，只能當退路 |
| **D-W5** | 清單只收**非 `P` 開頭**的變體：要 `MingLiU` 不要 `PMingLiU`，要 `MS Gothic` 不要 `MS PGothic` | 這是 Windows 版的 BR-MAC-6（Osaka 要指名 `Regular-Mono`）。實測 `PMingLiU` 的比例是 **2.13**，因為 `P` = proportional，半形字不是固定寬。名字只差一個字母，量出來就是歪的 |
| **D-W6** | 同時列出英文名與本地化名（`MingLiU` 與 `細明體`）；`platforms.py` 不做 locale 判斷 | 實測 Qt 在 zh-TW 的 Windows 上**兩個名稱都會列出**，但在其他語系的 Windows 上不保證。兩個都寫進清單是 O(1) 成本，比在 `platforms.py` 裡塞 locale 判斷乾淨得多（後者會違反 D-08 的精神） |
| **D-W7** | `Alt+C` 保留，另外補一個 `Ctrl+Shift+C`；補鍵機制沿用 SRS-005 D-05 的 `EXTRA_SHORTCUTS`，不新增機制 | BR-MAC-4 說「各平台共用同一組快速鍵定義，只能增加不得另建」。macOS 為了 `⌥C` → `ç` 已經補了 `Ctrl+Shift+C`，Windows 為了選單助憶鍵衝突需要的是**同一個補鍵**——直接沿用，三個平台的肌肉記憶反而更一致 |
| **D-W8** | 安裝到 `%LOCALAPPDATA%\Programs\StephanyEditor`，捷徑放使用者的「開始」功能表，檔案關聯寫 `HKCU\Software\Classes` | 全部都是每位使用者自己的範圍，**不需要系統管理員權限**，也就不需要 UAC 提權。對應 F-MAC-10／F-MAC-11「不需 root、移除不留系統層級殘檔」 |
| **D-W9** | Windows 的 GUI 測試**不得**使用 `QT_QPA_PLATFORM=offscreen`，改用原生平台外掛 | 實測 offscreen 在 Windows 上的 `QFontDatabase.families()` 是 **0 筆**，所有字型測試會安靜地 skip 而不是紅燈——CI 會顯示全綠，但什麼都沒驗到。GitHub 的 `windows-latest` runner 跑得起原生平台外掛 |

### D-W4 的實測數據

`QFontMetricsF.horizontalAdvance("漢") / horizontalAdvance("0")`，
PySide6 6.11.2、Windows 11 zh-TW、原生平台外掛：

| 字型 | 9pt | 12pt | 18pt | 24pt | 判定 |
|---|---|---|---|---|---|
| MingLiU／細明體 | 2.000 | 2.000 | 2.000 | 2.000 | ✅ |
| NSimSun／SimSun | 2.000 | 2.000 | 2.000 | 2.000 | ✅ |
| MS Gothic | 2.000 | 2.000 | 2.000 | 2.000 | ✅ |
| DFKai-SB（標楷體） | 2.000 | 2.000 | 2.000 | 2.000 | ✅ 但非等寬用途 |
| **PMingLiU** | 2.133 | 2.129 | 2.130 | 2.129 | ❌ proportional |
| Consolas | 1.820 | 1.819 | 1.820 | 1.819 | ❌ 退路 |
| Cascadia Mono | 1.707 | 1.707 | 1.707 | 1.707 | ❌ |
| Courier New | 1.670 | 1.668 | 1.668 | 1.666 | ❌ |
| Lucida Console | 1.662 | 1.660 | 1.661 | 1.660 | ❌ |
| Microsoft JhengHei | 1.726 | 1.727 | 1.726 | 1.725 | ❌ |

與 macOS 的 Osaka 一樣，**字型本身缺字也不影響**：量測
`漢臺灣繁體国語あア（）：「」；、々鷗顥` 19 個字元，合格字型全部維持 2.000
——系統遞補上來的 CJK 字型，中文寬度同樣等於字級。

⚠️ 這些字型屬於 Windows 的**語言補充字型**（optional features）：
zh-TW／zh-CN／ja 語系的 Windows 預設就有，但一台乾淨的 en-US Windows 11
可能一個都沒有。那種機器會退回 `Consolas` 並在狀態列警告——與 F-MAC-07
的處理方式一致，不會默默歪掉。

### D-W1 的實測數據

`SetCurrentProcessExplicitAppUserModelID` 回傳 `S_OK`，
`GetCurrentProcessExplicitAppUserModelID` 讀得回同一個字串；未設定時
後者回傳 `E_FAIL`（`0x80004005`），代表系統會退回用執行檔路徑推導。

捷徑端的 `System.AppUserModel.ID`（`PKEY_AppUserModel_ID`）可以只用標準
函式庫的 `ctypes` 經 `IShellLink` + `IPropertyStore` 寫入並讀回驗證，
**不需要 pywin32**——這是 D-W3「不裝額外工具」成立的關鍵。

## 3. 功能需求

| 編號 | 需求 |
|---|---|
| F-WIN-01 | 工作列、工作管理員與「開始」功能表顯示 `Stephany Editor` 與自訂圖示，不得顯示為 `python`／`pythonw` |
| F-WIN-02 | 提供建構腳本，產出可直接使用的安裝目錄；亦可一鍵安裝到 `%LOCALAPPDATA%\Programs` |
| F-WIN-03 | 在 Explorer 的「開啟方式」中可選本程式開啟純文字與常見原始碼檔 |
| F-WIN-04 | 從 Explorer 雙擊或「開啟方式」開檔，檔案路徑須正確傳進程式 |
| F-WIN-05 | 提供 `stephany-editor` 終端機指令（PowerShell 與 cmd 都可用），且不得彈出多餘的主控台視窗 |
| F-WIN-06 | 提供解除安裝腳本，移除安裝目錄、捷徑與登錄機碼（設定檔除外） |
| F-WIN-07 | Windows 預設字型須滿足「中文 = 半形 × 2」。系統沒有合格字型時須退回等寬字型並於狀態列警告，不得默默歪掉 |
| F-WIN-08 | `Alt+C`（欄位編輯器）在 Windows 上必須有實際按得到的替代鍵 |
| F-WIN-09 | 設定與巨集存放於 `%APPDATA%\StephanyEditor\`，並支援 `STEPHANY_CONFIG_DIR` 覆寫 |
| F-WIN-10 | 建構與安裝腳本不需系統管理員權限、不需 UAC 提權、不需安裝任何第三方打包工具 |

## 4. 業務規則

| 編號 | 規則 |
|---|---|
| **BR-WIN-1** | 版本號取自 `stephany/__init__.py` 的 `__version__`，不得在建構腳本或捷徑中手動同步（同 BR-PK-1、BR-MAC-1） |
| **BR-WIN-2** | 安裝目錄內不得含有 `__pycache__`、`*.pyc`、測試、`pip`／`setuptools` 等建構期套件（同 BR-MAC-2） |
| **BR-WIN-3** | `AppUserModelID` 與 macOS 的 `CFBundleIdentifier` 必須是同一個字串；三平台的識別碼一律同源於 `stephany-editor`（延伸 BR-MAC-5） |
| **BR-WIN-4** | 字型偏好清單不得收錄 `P` 開頭的 proportional 變體（`PMingLiU`、`MS PGothic`）——名稱只差一個字母，比例卻是 2.13（D-W5） |
| **BR-WIN-5** | Windows 只能「增加」快速鍵，不得另建一份完整對映表；補鍵與 macOS 共用同一個 `action_id`（同 BR-MAC-4） |
| **BR-WIN-6** | 所有安裝行為限於 `HKCU` 與使用者自己的目錄，不得寫入 `HKLM`、`Program Files` 或 `System32` |

## 5. 非功能需求

| 編號 | 需求 |
|---|---|
| NF-W1 | 平台差異仍然集中在 `stephany/platforms.py`；該模組不得 import Qt（同 NF-01）。Windows 專屬的 `ctypes` 呼叫不得寫進 `core/` |
| NF-W2 | 字型不變量、識別碼一致性、快速鍵綁定須可由測試驗證，不靠人工檢查（同 NF-02） |
| NF-W3 | CI 須在 Windows runner 上跑全套測試，且**不得**使用 offscreen 平台外掛（D-W9） |
| NF-W4 | 建構腳本以 Python 撰寫而非 `.bat`／`.ps1`：Python 本來就是本專案的硬相依，且中文訊息在 cmd 與 PowerShell 的編碼行為都不可靠 |

## 6. 範圍外與已知限制

- **不內嵌 Python**：安裝後的目錄是一個 venv，相依「建構時那個 Python 仍然
  存在於這台機器上」——與 SRS-005 D-03 的 `.app` 完全相同的取捨。要做成
  真正可散布的獨立安裝檔，得改用 embeddable package 或 PyInstaller，
  那會違反 D-W3，留待日後真的有散布需求時再評估。
- **不做程式碼簽章**：自用安裝不需要；對外散布才需要憑證。未簽章的執行檔
  在別台機器上會被 SmartScreen 警告。
- **不做 MSI／MSIX 與 Microsoft Store 上架**：需要簽章與額外工具鏈。
- **不搶預設關聯**：只註冊到「開啟方式」清單（對應 F-MAC-03 的
  `LSHandlerRank = Alternate`），不修改使用者既有的預設程式。
- **深色模式**：Windows 的深色模式偵測沿用既有的「由系統配色推導主題」
  機制（SRS-003），本規格不另外處理。
