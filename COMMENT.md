
## 專案使用流程 (利用 Graphify 為書籍/文件建立論證圖譜)

利用 graphify 為書籍或長篇文件建立 Claim/Evidence 論證圖譜，快速理解論述結構。

### 步驟一：安裝全域 Skill (只需做一次或 skill 有更新時)

在 D:\gemini-cli\graphify 目錄下，且啟動該專案 .venv 的狀態下執行以下指令：

```powershell
python -m graphify install --platform gemini
```

Gemini CLI 是從 user 目錄下的 .gemini\skills\graphify 讀取全域 Skill。這指令會將 `D:\gemini-cli\graphify\graphify\skill-gemini.md` 複製到該目錄下，並改名為 `SKILL.md`。

### 步驟二：將書本放到 book 資料夾

將書籍檔案（.txt、.md、.pdf 等）放入 `D:\gemini-cli\graphify\book\<書名>\` 資料夾。

### 步驟三：建立書本論證圖譜

在 graphify 專案目錄下啟動 Gemini CLI，輸入：

```
/graphify ./book/<書名>
```

圖譜產物會放在 `./book/<書名>/graphify-out/` 內。

### 步驟四：利用 MCP 伺服器讓 AI 主動利用圖譜來回答問題

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


