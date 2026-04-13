
## 正確的跨專案使用流程 (利用 Graphify 為其他專案建立圖譜，快速理解程式碼)

利用 graphify 為 fork 回來的專案建立圖譜，快速理解專案架構與節省詢問 AI 的 token 數。

### 步驟一：讓 `/graphify` 指令在所有專案都能喚醒 (只需做一次或skill有更新時)

在 D:\gemini-cli\graphify 目錄下，且啟動該專案 .venv 的狀態下執行以下指令：

```powershell
python -m graphify install --platform gemini
```

Gemini CLI 是從 user 目錄下的 .gemini\skills\graphify 讀取全域 Skill。這指令會將 `D:\gemini-cli\graphify\graphify\skill-gemini.md` 複製到該目錄下，並改名為 `SKILL.md`。

### 步驟二：在目標專案安裝 Graphify (每次目標專案做一次)

切換到目標專案目錄，建立虛擬環境後，將 `graphify` 以「Editable Mode (開發模式)」安裝掛載進來。

```powershell
# 將 D 槽的 graphify 掛載進這個環境 (這樣你以後改 graphify 程式碼，這裡也會同步生效)
uv pip install -e "D:\gemini-cli\graphify"
```

### 步驟三：在目標專案利用 GEMINI.md 賦予 AI 圖譜意識

在目標專案下執行：

```powershell
python -m graphify gemini install
```

這會在專案產生 `GEMINI.md`，讓 AI 回答問題時，會先「自動」去讀圖譜報告，而不是傻傻地全域搜尋。裡面那段 `<!-- graphify -->` 包起來的英文文字，就是這個指令寫進去的。同時建立或更新 .gitignore 和 .graphifyignore 和 .geminiignore。

### 步驟四：在目標專案建立知識圖譜

現在，確認您已經啟動了 `.venv`，然後在目標專案的 terminal 環境執行 gemini，打開 Gemini CLI，並輸入：

```
/graphify .
```

透過這種做法，**圖譜產物（`graphify-out`）會乖乖待在 `D:\other-project`**，核心程式碼依然在 `D:\gemini-cli\graphify`，而且兩個專案的環境依然完美隔離！

### 步驟五：在目標專案局部更新知識圖譜

寫程式是動態的，專案每天都在變。當你今天又改了一些程式碼，不需要傻傻重跑一次龐大的全面掃描，你只要在 Gemini CLI說：

```
/graphify --update
```

### 步驟六：利用 MCP 伺服器讓 AI 主動利用圖譜來回答問題

#### 先確認目標專案安裝 mcp 套件

```powershell
uv pip install mcp
```

#### 啟動 MCP 伺服器
讓 AI 會自己決定去呼叫你掛載的 graphify API 工具，做更精準細化的查詢。 請把最後面的路徑換成你實際的圖譜絕對路徑。在專案目錄下執行：

```powershell
gemini mcp add graphify "D:\gemini-cli\目標專案\.venv\Scripts\python.exe" -m graphify.serve "D:\gemini-cli\目標專案\graphify-out\graph.json"
```

這指令其實就是 Gemini CLI 會幫忙到專案目錄下的.gemini\settings.json 寫入 mcp server 設定，你也可以手動編輯。

#### 卸載 MCP 伺服器

```powershell
gemini mcp remove graphify
```

