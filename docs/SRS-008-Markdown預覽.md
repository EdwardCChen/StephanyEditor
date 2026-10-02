# SRS-008：Markdown 預覽

| 項目 | 內容 |
|---|---|
| 版本 | 1.0 |
| 狀態 | 已拍板，開發中 |
| 前置 | SRS-001 ~ SRS-007 |

## 1. 背景與問題

編輯 `.md` 檔時只看得到原始碼，標題層級、表格欄位是否對齊、清單縮排是否
被正確解讀為巢狀、圖片路徑是否寫對——這些都要另外開瀏覽器或推上 GitHub
才知道。編輯器需要一個邊打邊看的預覽，用來確認排版版面是否正確。

目標是「看起來接近 GitHub」，因為多數 Markdown 最後是在 GitHub 上被閱讀。

## 2. 拍板決策

| 編號 | 決策 | 理由 |
|---|---|---|
| **D-01** | 以 **QtWebEngine**（`QWebEngineView`）顯示，搭配仿 GitHub 的樣式表 | 使用者拍板：要確認的是「在 GitHub 上長怎樣」。Qt 內建的 `setMarkdown()` 結構正確，但它不是瀏覽器，CSS 支援很有限，長相與 GitHub 差很多。代價是相依 `PySide6-Addons`，三種打包都會明顯變大 |
| **D-02** | Markdown → HTML 的轉換在 **Python 端**做（`markdown-it-py` + `mdit-py-plugins`，程式碼上色用 `Pygments`），放在 `core/`，不在網頁裡跑 JS 函式庫 | 轉換規則才是要測的東西。放在 Python、不依賴 Qt，就能在 CI 的「核心邏輯（無 Qt）」job 裡完整單元測試；放在網頁裡則只能透過非同步的 WebEngine 間接測。三者都是純 Python、GPL 相容（MIT／BSD），Ubuntu 有系統套件 |
| **D-03** | 預覽放在主視窗右側的停駐面板（`QDockWidget`），跟著目前分頁走；不把每個分頁改成分割畫面 | 使用者拍板。現有程式處處假設「分頁的 widget 就是編輯器」，改成分割畫面變更量與風險都大得多 |
| **D-04** | 預覽是手動開關（檢視選單、工具列、`Ctrl`+`Shift`+`V`），開關狀態跨 session 保留 | `Ctrl`+`Shift`+`V` 是 VS Code 的同一功能；三個平台都沒有被佔用 |
| **D-05** | 只渲染「副檔名是 Markdown」或「未命名」的分頁；其他分頁顯示提示文字 | 把 `.py` 當 Markdown 渲染沒有意義，反而讓人以為壞了。未命名分頁常是貼上來的草稿，所以放行 |
| **D-06** | 文字變動後延遲 300 ms 才更新（debounce）。更新時只替換內容區塊（`innerHTML`），不重新載入整頁 | 每按一個鍵就整頁重載，長文件會卡，而且捲動位置會跳回頂端 |
| **D-07** | 預覽的捲動依比例跟隨編輯器 | 精確的行對行同步需要原始碼位置對照，成本高。比例跟隨是 best-effort，圖片或大表格多的文件會有落差 |
| **D-08** | 頁面內的 **JavaScript 一律關閉**；本程式自己的更新指令在隔離的 `ApplicationWorld` 執行 | Markdown 允許內嵌 HTML（GitHub 也允許），打開別人寫的 `.md` 不該因此執行其中的 `<script>`。Qt 的 `JavascriptEnabled` 只管頁面自己的 MainWorld，不影響 `runJavaScript(..., ApplicationWorld)` |
| **D-09** | 允許載入**遠端圖片**（例如 README 上的 badge） | 與 GitHub 一致；擋掉的話大部分 README 頂端會是一排破圖，無法確認版面。代價是開啟檔案時會對圖片所在的伺服器發出請求，記錄於 README |
| **D-10** | 預覽中點連結：`http(s)`／`mailto` 交給系統預設程式；其他（相對路徑、錨點以外的導覽）一律攔下不動作 | 預覽面板不是瀏覽器，點了把預覽換成別的頁面只會讓人迷路 |
| **D-11** | 執行環境沒有 QtWebEngine 時**優雅降級**成 `QTextBrowser` 顯示同一份 HTML，並在面板上方註明「簡易模式」 | WebEngine 是大型相依（deb 的 `Recommends`，見 D-12），沒裝不能讓整個編輯器起不來，也不該讓預覽功能消失 |
| **D-12** | deb：`markdown-it`／`mdit-py-plugins`／`pygments` 列 `Depends`，WebEngine 列 `Recommends` | 前三者是小型純 Python 套件；WebEngine 會拉進整套 Chromium。`apt install` 預設就會裝 Recommends，所以一般使用者拿到的就是完整版，只有刻意 `--no-install-recommends` 的人走 D-11 的降級路徑 |

## 3. 功能需求

| 編號 | 需求 |
|---|---|
| F-MD-01 | 檢視選單有「Markdown 預覽」可勾選項目，工具列有對應按鈕，快速鍵 `Ctrl`+`Shift`+`V` |
| F-MD-02 | 渲染 GitHub Flavored Markdown：標題、粗斜體、刪除線、清單（含巢狀與核取清單）、表格（含欄位對齊）、引言、程式碼區塊、水平線、連結、圖片、註腳、行內 HTML |
| F-MD-03 | 圍欄程式碼區塊依標示的語言上色；未標示或不認得的語言照原樣顯示，不報錯 |
| F-MD-04 | 編輯內容後預覽自動更新（D-06） |
| F-MD-05 | 切換分頁時預覽跟著換成該分頁的內容 |
| F-MD-06 | 相對路徑的圖片以**該檔案所在目錄**為基準載入；未存檔的分頁沒有基準目錄 |
| F-MD-07 | 非 Markdown 檔的分頁顯示提示（D-05） |
| F-MD-08 | 預覽捲動依比例跟隨編輯器（D-07） |
| F-MD-09 | 預覽面板開關狀態跨 session 保留 |
| F-MD-10 | 深色主題下預覽也是深色（GitHub 的深色配色） |

## 4. 業務規則

| 編號 | 規則 |
|---|---|
| **BR-MD-1** | 「什麼算 Markdown 檔」只有一處判斷：`core.markdown.is_markdown(path)`。副檔名不分大小寫：`.md`、`.markdown`、`.mdown`、`.mkd`、`.mkdn`；`path` 為 `None`（未命名）時為真 |
| **BR-MD-2** | 圖片基準目錄只有一處計算：`core.markdown.base_dir(path)`；未命名時為 `None` |
| **BR-MD-3** | 預覽**唯讀**，不得回寫編輯器的文件，也不得影響 undo 堆疊與「已修改」狀態 |
| **BR-MD-4** | 連結是否交給系統開啟只有一處判斷：`core.markdown.is_external_link(url)`，只有 `http`、`https`、`mailto` 為真 |
| **BR-MD-5** | 工具列按鈕依 SRS-007 規則：單色 24×24 SVG，登記在 `TOOLBAR_LAYOUT`；符號採最通用的「眼睛」（SRS-007 D-07） |
| **BR-MD-6** | 程式碼區塊的內容一律經過 HTML 跳脫；上色只能加上 `<span class>`，不得讓原始碼裡的 `<script>` 等字樣變成真的標籤 |

## 5. 非功能需求

| 編號 | 需求 |
|---|---|
| NF-01 | `core/markdown.py` 不得 import Qt（沿用 SRS-001 NF-01，CI 的核心 job 驗證） |
| NF-02 | 不需要網路即可預覽（樣式表、上色樣式全部內嵌，不從 CDN 載入）；遠端圖片例外（D-09） |
| NF-03 | 1 MB 的 Markdown 檔轉換時間在開發機上 < 1 秒（實測 0.27 秒）。測試門檻放寬為 3 秒：GitHub Actions 的共用 runner 實測要 1.0~1.2 秒，牆鐘時間卡太緊只會讓 CI 隨機紅燈；3 秒仍抓得到數量級的退化（例如不小心寫成 O(n²)） |

## 6. 範圍外與已知限制

- **數學式**（`$...$`）、**Mermaid 圖**、GitHub 專屬的 `> [!NOTE]` 提示框：
  需要額外的 JS 函式庫或 GitHub 專屬語法，本版不做，顯示為原始文字。
- 與 GitHub 的長相是「接近」，不是像素一致：GitHub 的 HTML 消毒規則、
  標題錨點、emoji 短碼（`:smile:`）等細節不同。
- 精確的行對行捲動同步（見 D-07）。
- 匯出 HTML／PDF；點相對連結跳到另一個 `.md` 檔。
