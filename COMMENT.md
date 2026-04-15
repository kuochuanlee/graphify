
## 專案使用流程 (利用 Graphify 為書籍/文件建立論證圖譜)

利用 graphify 為書籍或長篇文件建立 Claim/Evidence 論證圖譜，快速理解論述結構。

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

### 步驟三：在目標專案建立書本論證圖譜

確認已啟動 `.venv`，然後在目標專案的 terminal 環境執行 gemini，打開 Gemini CLI，並輸入：

```
/graphify ./book-folder
```

圖譜產物（`graphify-out`）會放在書本資料夾內。
