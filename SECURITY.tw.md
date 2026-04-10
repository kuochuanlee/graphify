# 資訊安全政策 (Security Policy)

## 支援的版本 (Supported Versions)

| 版本 (Version) | 是否支援 (Supported) |
|---------|-----------|
| 0.3.x   | 是       |
| < 0.3   | 否        |

## 回報安全性漏洞 (Reporting a Vulnerability)

**請勿在公開的 GitHub Issue 上回報任何安全性漏洞。**

請透過 GitHub 私密漏洞回報功能 (private vulnerability reporting)，或是直接發送電子郵件通知專案維護者。在回報時請附上以下資訊：

- 漏洞的詳細描述
- 重現漏洞的步驟
- 潛在的影響範圍
- 建議的修復方案 (如果有)

我們將會在 48 小時內確認已收到回報，如屬重大嚴重問題，我們將力求在 7 天內釋出修正檔。

## 資訊安全模型 (Security Model)

graphify 是一個**本地端的開發輔助工具**。它以 Claude Code 擴充技能的形式執行，也可作為本地端的 MCP stdio 伺服器啟動。在進行圖譜分析時，它絕對不會執行任何網路呼叫連線 - 唯有在進行 `ingest`（使用者明確下達指令要求抓取 URL）時才會產生連網行為。

### 威脅攻擊面剖析 (Threat Surface)

| 攻擊媒介 (Vector) | 防禦措施 (Mitigation) |
|--------|-----------|
| 透過 URL 抓取造成的 SSRF 攻擊 | `security.validate_url()` 只允許 `http` 和 `https` 通訊協定，並且從底層直接封鎖所有 private/loopback/link-local IP 網段，也全面封鎖各大雲端商的 metadata 端點。任何網址轉址 (Redirect) 的目標皆會被重新防堵驗證。包含推文 oEmbed 抓取在內的每一條對外呼叫路徑，都必定會通過 `safe_fetch()` 機制處理。 |
| 過大容量下載癱瘓 | `safe_fetch()` 會採用串流式下載 (streams) 處理回應，並在檔案超過 50 MB 時強制中斷並捨棄。而若是針對純文本的 `safe_fetch_text()` 則會在 10 MB 時就被截斷。 |
| 處理非 2xx 的 HTTP 異常狀態碼回應 | `safe_fetch()` 在遇到非 2xx 的異常狀態碼時會主動拋出 `HTTPError` 例外 - 絕不僅僅把錯誤頁面當成正常內容來默默消化處理。 |
| MCP 伺服器內的目錄穿越漏洞 (Path traversal) | `security.validate_graph_path()` 會解析所有實體路徑，且嚴格限制讀寫必須要在 `graphify-out/` 這個專屬沙盒資料夾內部。另外也會嚴格驗證確保 `graphify-out/` 目錄確實存在。 |
| 輸出至圖表 HTML 的 XSS 攻擊 | `security.sanitize_label()` 會自動剔除所有 ASCII 控制字元，將長度強制限縮封頂在 256 個字元內，並且在 pyvis 要嵌入呈現之前，會先將所有的節點標籤 (node labels) 與邊緣標籤 (edge titles) 進行全方位的 HTML-escapes 跳脫。 |
| 透過節點標籤造成的提示詞注入攻擊 (Prompt injection) | `sanitize_label()` 的過濾機制同樣會應用在拋出給 MCP 的文字敘述內容上 - 原生惡意來源檔案中任何蓄意設計過的節點標籤字眼，絕對無法破壞或干擾最後拋給 AI 代理人 (agents) 吸收的文字排版格式。 |
| YAML frontmatter 注入惡意程式碼 | `_yaml_str()` 會在將任何潛在使用可控字串 (例如：從網頁拔回來的標題、使用者拋出的詢問問題) 嵌入至最終 YAML frontmatter 解析格式以前，先把所有的反斜線、雙引號以及換行符號執行安全跳脫處理 (escapes)。 |
| 由問題原始碼檔案編碼導致的崩潰當機 | 全盤採用帶有 `errors="replace"` 的模式來解碼所有的 tree-sitter 位元組字節 - 這確保若遇上任何非主流非 UTF-8 格式的無腦亂裝死原始碼時，系統會優雅降級讀取，而不是搞到整個提取程序全面崩盤。 |
| 符號連結造成的穿越 (Symlink traversal) | 整個 `detect.py` 分析層都明確寫死帶有 `os.walk(..., followlinks=False)` 來斬草除根杜絕任何這類無端外溢漫遊。 |
| graph.json 壞檔損毀 | 負責提供對外介接服務的 `serve.py` 裡面的 `_load_graph()` 已完整捕獲 `json.JSONDecodeError` 錯誤，當壞圖發生時只會給出清晰易懂的系統重啟復原建議提示，而不是拋出醜陋的系統中斷錯誤碼。 |

### graphify **絕對不碰** 的事情 (What graphify does NOT do)

- 不會執行啟動任何常駐的對外網路監聽埠 (MCP server 永遠只透過安全的 stdio 標準輸出入機制溝通)
- 不會去暗自執行或直譯原始碼檔案當中的內容 (tree-sitter 僅負責解析抽象語法樹 ASTs - 完全沒有 eval/exec 的操作空間)
- 絕對不會在任何呼叫外部子程序的操作當中使用 `shell=True` 這個具風險的作法
- 絕對不會暗自備份保存或上傳任何憑證或 API 金鑰

### 非強制的選擇性對外網路呼叫 (Optional network calls)

- `ingest` 開發工具子指令: 只會明確透過網路去抓取由開發者長官親手主動提供的明文 URL 網址
- 解析 PDF 的擷取器: 僅會在本地對單機實體檔案作動 (pypdf 底層本身不具備也無法發出出網呼叫能力)
- watch 監控模式: 單純靠作業系統本地檔案異動事件機制驅動監聽 (watchdog 本身一樣具備純本地絕不對外網路呼叫的特質)
