
## 專案使用流程 (利用 Graphify 為書籍/文件建立論證圖譜)

利用 graphify 為書籍或長篇文件建立 Claim/Evidence 論證圖譜，快速理解論述結構。

### 步驟零：專案環境與依賴套件安裝

在第一次使用專案，或是你有更新程式碼、切換環境時，需要將本專案 (`graphify`) 與它的依賴套件（如建立圖譜用的 `networkx` 以及 `tree-sitter` 等）安裝到你的虛擬環境中：

1. 確保目前終端機已經啟用了 `.venv` 虛擬環境 (`uv venv`)。
2. 執行以下指令以編輯模式 (`-e`) 將專案安裝：
```powershell
uv pip install -e .
```
*(備註：如果不執行這步，Python 會說找不到 `graphify` 模組或報錯缺少 `networkx` 等依賴)*

### 步驟一：安裝全域 Skill (只需做一次或 skill 有更新時)

在 D:\gemini-cli\graphify 目錄下，且啟動該專案 .venv 的狀態下執行以下指令：

```powershell
python -m graphify install --platform gemini
```

Gemini CLI 是從 user 目錄下的 .gemini\skills\graphify 讀取全域 Skill。這指令會將 `D:\gemini-cli\graphify\graphify\skill-gemini.md` 複製到該目錄下，並改名為 `SKILL.md`。

### 步驟二：將書本放到 book 資料夾

將書籍檔案（.txt、.md、.pdf 等）放入 `D:\gemini-cli\graphify\book\<書名>\` 資料夾。

### 步驟三：建立書本論證圖譜 (Skill 自動法 - 適合小型文件)

在 graphify 專案目錄下啟動 Gemini CLI，輸入：

```
/graphify ./book/<書名>
```

圖譜產物會放在 `./book/<書名>/graphify-out/` 內。

> **[注意] 被擋/取消的原因**
> 如果書籍內容較長，這會產生數十個以上的 Chunks。Gemini CLI 的 sub-agent 在接收到大批量任務時，會因為預估處理時間太長 (例如超過 270 秒) 觸發安全機制而**主動取消 (Request cancelled)**。
> 如果遇到這種情況，請改用以下的「步驟四：手動分解法」。

### 步驟四：建立書本論證圖譜 (手動分解法 - 適合大型書籍)

為了避免處理大量分塊 (Chunks) 時被系統強制中斷，推薦使用 `run_workflow.py` 將任務分為三階段，並搭配與 AI 對話手動推進：

**第一階段：偵測與準備**
```powershell
python run_workflow.py "book\<書名>" --step 1
```
> 執行完畢後，終端機畫面上會印出「提示詞」，請複製該段提示詞並貼給 AI，讓 AI 接手後續的語意批次提取。

**第二階段：合併與分析**（待 AI 處理完第一階段後執行）
```powershell
python run_workflow.py "book\<書名>" --step 2
```
> 畫面上會再次印出提示詞，請一樣複製給 AI，這階段是讓 AI 幫忙將社群分群節點命名。

**第三階段：收尾與產出**（待 AI 完成第二階段後執行）
```powershell
python run_workflow.py "book\<書名>" --step 3
```
圖譜的最終產物，包含網頁版圖譜、Obsidian 筆記和 JSON 檔案，皆會存放於 `./book/<書名>/graphify-out/` 內。

### 步驟五：利用 MCP 伺服器讓 AI 主動利用圖譜來回答問題

#### 啟動 MCP 伺服器
讓 AI 會自己決定去呼叫你掛載的 graphify API 工具，做更精準細化的查詢。 請把最後面的路徑換成你實際的書本圖譜絕對路徑。在專案目錄下執行：

```powershell
gemini mcp add graphify python -m graphify.serve "D:\gemini-cli\book\<書名>\graphify-out\graph.json"
```

這指令其實就是 Gemini CLI 會幫忙到專案目錄下的.gemini\settings.json 寫入 mcp server 設定，你也可以手動編輯。

#### 卸載 MCP 伺服器

```powershell
gemini mcp remove graphify
```

## 未來待做事項

- [ ] 優化語意分析功能，可改多次LLM處理，加強schema的設計方式
- [ ] 增加前置的處理，改善分割方式，和引入詞頻分析來輔助
- [ ] 增加 LLM 外包功能的流程設計
- [ ] 確保能在linux上執行
- [ ] 使用工作流讓一切都自動化


