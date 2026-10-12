# CLAUDE.md

給 agent 的專案慣例。人看的說明在 README.md，規格在 docs/SRS-*.md。

## 指令

```bash
./run.sh                                  # 第一次會建 .venv 並安裝相依
.venv/bin/python -m pytest tests -q       # 全套
```

健康輸出（macOS 本機）：`492 passed, 27 skipped`，**且結束碼為 0**——
WebEngine 的當機常發生在印完結果之後，只看最後一行會漏掉。

## 慣例

- 規格驅動：程式碼註解、測試名稱、commit message 都引用規格編號（`F-MD-01`、`BR-TB-3`、`D-07`）
- 測試先行：先看到測試以預期原因失敗，再寫實作；新測試第一次就綠，要故意改壞實作確認它會紅
- `stephany/core/` 不得 import Qt（CI 的核心 job 不裝 PySide6 來驗證）
- 顏色不寫死，一律從 `QPalette` 經 `ui/theme.py` 推導
- 建 `MainWindow` 的測試一定要用 `window` 或 `isolated_settings` fixture，否則在 macOS／Windows 上會讀寫使用者真正的設定

## 架構

- `core/`：純邏輯；`ui/`：Qt；`platforms.py`：平台差異唯一集中處
- `__main__.create_app()`：與真實啟動相同的組裝，測試要走真實路徑時用它（只能在全新程序裡呼叫）
- `packaging/`：三平台打包腳本；`dist/` 是產物，不進版控

## 已知地雷區

- **offscreen 測不到 macOS 原生視窗的當機。** QtWebEngine 在 cocoa 上會建原生子視窗，
  offscreen 下不會。已發生兩次「CI 全綠、安裝版當機」（SRS-008）：
  1. 整個 app 掛 Python 事件過濾器 → WebEngine 物件解構時 segfault
  2. 在 `show()` 途中（例如 `visibilityChanged`）建 WebEngine → `showChildren` segfault

  因此：碰到 WebEngine 或視窗生命週期的改動，除了 pytest，還要用
  `QT_QPA_PLATFORM=cocoa` 照 `create_app()` 實際啟動，**用使用者真正的設定值**
  （最大化、面板開著）重複跑多次看結束碼；回歸測試則驗「性質」（例如 show() 回來
  當下還沒建預覽），而不是只驗「沒當機」。當機報告在 `~/Library/Logs/DiagnosticReports/`。
- **不要在 widget 樹正在顯示／重排的回呼裡新增子元件**，延到下一輪事件迴圈（`QTimer.singleShot(0, ...)`）。
- PySide6 6.11 的 `QUrl.adjusted(RemoveFragment)` 綁定不接受該列舉；processEvents() 不處理 `deleteLater`，
  需要 `QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)`。
