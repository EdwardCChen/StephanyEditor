# 實作計畫：SRS-008 Markdown 預覽

> 第一版計畫採 Qt 內建 `setMarkdown()`；使用者拍板改用 WebEngine 仿 GitHub（A1），
> 預覽放右側停駐面板（A2）。以下為改版後的計畫。

## 變更檔案清單

| 檔案 | 新建／既有 | 內容 |
|---|---|---|
| `stephany/core/markdown.py` | 新建 | `is_markdown()`、`base_dir()`、`is_external_link()`、`render()`（Markdown → HTML 片段）、`page()`（完整頁面＋內嵌樣式表），不 import Qt |
| `tests/test_markdown.py` | 新建 | 核心規則與轉換的單元測試 |
| `stephany/ui/preview.py` | 新建 | `MarkdownPreview`：WebEngine／QTextBrowser 兩種後端、debounce、比例捲動、連結攔截 |
| `tests/test_preview_gui.py` | 新建 | 預覽 widget 與主視窗接線的 GUI 測試 |
| `stephany/ui/mainwindow.py` | 既有 | `QDockWidget`、`act_preview`、檢視選單、`TOOLBAR_LAYOUT`、切換分頁、設定保存 |
| `stephany/__main__.py`、`tests/conftest.py` | 既有 | 建 `QApplication` 前先 import WebEngine（Qt 的硬性要求） |
| `stephany/resources/icons/preview.svg` | 新建 | 眼睛圖示 |
| `requirements.txt` | 既有 | 加 `PySide6-Addons`、`markdown-it-py`、`mdit-py-plugins`、`Pygments` |
| `packaging/build-deb.sh`、`tests/test_packaging.py` | 既有 | Depends／Recommends（D-12） |
| `.github/workflows/ci.yml` | 既有 | 核心 job 裝 markdown-it 等並跑 `test_markdown.py`；GUI job 裝 WebEngine 的系統相依 |
| `README.md`、`samples/demo.md` | 既有／新建 | 功能說明、已知限制、相依與打包大小變化、範例檔 |

## 工作順序

1. **core**：`core/markdown.py` + `tests/test_markdown.py`（BR-MD-1/2/4/6、F-MD-02/03、NF-01/02/03）→ commit
2. **預覽 widget**：`ui/preview.py`（D-06/07/08/09/10/11、BR-MD-3、F-MD-06/07/10）→ commit
3. **主視窗接線**：dock、動作、選單、快速鍵、切換分頁、設定保存（F-MD-01/04/05/09）→ commit
4. **工具列圖示**（BR-MD-5）→ commit
5. **相依與打包**：requirements、deb、CI（D-12）→ commit，看 CI 綠燈
6. **文件**：README、範例檔；macOS 實際建 `.app` 確認 WebEngine 子程序跑得起來 → commit

## 風險

- **打包變大**：`PySide6-Addons` 讓本機 venv 的 PySide6 從約 0.5 GB 變成 1.2 GB；
  `.app` 與 Windows 安裝會同比例變大。使用者已知悉並拍板。
- **Linux 上 Chromium 沙箱**：Ubuntu 24.04 起 AppArmor 限制非特權 user namespace，
  CI runner 上 WebEngine 可能因沙箱起不來 → CI 設 `QTWEBENGINE_DISABLE_SANDBOX=1`。
  **實際使用者的 Ubuntu 上是否需要同樣處理，本機（macOS）驗不到**，列為未實機驗證路徑。
- **WebEngine 非同步**：`setHtml`／`runJavaScript` 都是非同步，GUI 測試要等 `loadFinished`
  與回呼，給逾時上限，避免測試掛住。
- **CI 環境沒有 WebEngine 能用時**：相關測試 `skip` 並寫明原因（`-rs` 會列出），降級路徑另有測試。
- **大型檔案**：每次更新都整份重新轉換；NF-03 以測試量測上限。

## 驗收證明

| 單位 | 怎樣算完成 |
|---|---|
| 1 | `tests/test_markdown.py` 全綠；CI 核心 job（無 Qt）綠燈 |
| 2 | `tests/test_preview_gui.py`：WebEngine 後端顯示表格、debounce 前不更新之後更新、更新後捲動位置不歸零、內嵌 `<script>` 不執行、點外部連結呼叫系統開啟、相對路徑導覽被攔下；降級後端可顯示；編輯器 `isModified()` 不受影響 |
| 3 | GUI 測試：`Ctrl+Shift+V` 綁在 `act_preview`、切換分頁內容跟著換、非 md 顯示提示、重開視窗開關狀態保留 |
| 4 | 既有 `test_icons.py`、`test_toolbar_gui.py` 全綠（含新圖示） |
| 5 | `test_packaging.py` 綠；GitHub Actions 四個 job 綠 |
| 6 | macOS `.app` 實機開 `samples/demo.md` 預覽有畫面（截圖） |

## 未決事項（假設清單）

| 編號 | 假設 | 類型 |
|---|---|---|
| A1 | 渲染引擎用 WebEngine 仿 GitHub | 已銷帳（使用者拍板） |
| A2 | 右側停駐面板 | 已銷帳（使用者拍板） |
| A3 | 未命名分頁也渲染（D-05） | non-blocking |
| A4 | 快速鍵 `Ctrl`+`Shift`+`V`（D-04） | non-blocking |
| A5 | 比例捲動同步可接受（D-07） | non-blocking |
| A6 | 允許遠端圖片、關閉頁面 JS（D-08、D-09） | non-blocking |
| A7 | 數學式、Mermaid、GitHub 提示框不在本版（SRS §6） | non-blocking |
| A8 | deb 的 WebEngine 列 Recommends 而非 Depends（D-12） | non-blocking |

## 質詢

1. **哪一步最可能失敗？** CI 的 Linux GUI job 上跑 WebEngine（沙箱、GL、缺系統函式庫）。
   對策：先在 CI 加相依並設 `QTWEBENGINE_DISABLE_SANDBOX`；若仍起不來，WebEngine
   測試 skip 並寫明原因，降級路徑與核心轉換照樣在 CI 上驗證。
2. **有沒有變更更少的做法？** 把轉換放在網頁裡（內嵌 marked.js + highlight.js），
   Python 端就不必新增三個套件。但那樣核心規則只能透過 WebEngine 間接測，而且要
   把第三方 JS 原始碼放進本專案的版控與授權清單。選 Python 端轉換。
3. **若 WebEngine 在某平台根本不能用？** D-11 的降級路徑讓預覽仍可用（長相退回
   簡易版），不會讓編輯器起不來。

## 實作偏離與發現

| 項目 | 偏離／發現 | 處理 |
|---|---|---|
| 相依 | 計畫沒列 `linkify-it-py`：markdown-it 的 `gfm-like` 預設要它才能把裸網址變連結（GitHub 的行為） | 加入 requirements 與 deb Depends（`python3-linkify-it`） |
| NF-03 | 1 秒門檻在 GitHub Actions runner 上隨機紅燈（Python 3.10 runner 1.23 秒、Windows 1.03 秒；開發機 0.27 秒） | 規格改為「開發機 < 1 秒，測試門檻 3 秒防數量級退化」 |
| 測試隔離 | conftest 只把 INI 格式的設定導到暫存目錄；主視窗的 `QSettings(org, app)` 在 macOS 是 plist、Windows 是登錄檔，**既有測試一直在讀寫使用者真正的設定** | 抽出 `isolated_settings` fixture 強制改用 INI，既有自建主視窗的測試也改用它 |
| WebEngine 回呼 | 面板被刪除後，還在途中的 `runJavaScript` 回呼才回來，對已刪除的物件發信號 | 回呼開頭以 `shiboken6.isValid()` 檢查 |
| PySide6 6.11 | `QUrl.adjusted(RemoveFragment)` 綁定不接受該列舉 | 改用字串比對 |
| 打包大小 | macOS `.app` 實測 343 MB → 1.2 GB | 已知悉（A1 拍板時即說明），寫進 README |
