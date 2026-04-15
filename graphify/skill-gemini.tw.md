---
name: graphify
description: 任何輸入 (程式碼、文件、論文、圖片) -> 知識圖譜 -> 社群分群 -> HTML + JSON + 稽核報告
trigger: /graphify
---

# /graphify

將任何資料夾內的檔案轉化為可導覽的知識圖譜，具備社群偵測、誠實的稽核追蹤，並產出三項輸出：互動式 HTML、可供 GraphRAG 讀取的 JSON、以及白話文版的 GRAPH_REPORT.md。

## 用法

```
/graphify                                             # 在當前目錄執行完整管線
/graphify <path>                                      # 在指定路徑執行完整管線
/graphify <path> --mode deep                          # 深度提取，產生更豐富的 INFERRED 關聯邊
/graphify <path> --update                             # 漸進式更新 - 僅重新提取新增/變更的檔案
/graphify <path> --book                               # 書本模式 - 提取 Claim/Evidence 論證圖譜
/graphify <path> --cluster-only                       # 針對既有圖譜重新執行分群
/graphify <path> --no-viz                             # 跳過視覺化，僅產出報告 + JSON
/graphify <path> --svg                                # 額外匯出 graph.svg
/graphify <path> --graphml                            # 匯出 graph.graphml (Gephi, yEd)
/graphify <path> --neo4j                              # 產生 graphify-out/cypher.txt 供 Neo4j 匯入
/graphify <path> --neo4j-push bolt://localhost:7687   # 直接推送到 Neo4j
/graphify <path> --mcp                                # 啟動 MCP stdio 伺服器
/graphify <path> --watch                              # 監控檔案變更並自動同步圖譜
/graphify <path> --wiki                               # 建立可供 Agent 爬行的 wiki
/graphify <path> --obsidian                           # 額外產生 Obsidian 筆記庫 (需明確指定)
/graphify <path> --obsidian --obsidian-dir ~/vaults/x # 將筆記庫輸出到自訂路徑
/graphify add <url>                                   # 抓取 URL，存入 ./raw，更新圖譜
/graphify add <url> --author "名字"                   # 標記原作者
/graphify add <url> --contributor "名字"              # 標記提供者
/graphify query "<問題>"                               # BFS 廣度優先查詢 - 取得廣泛的上下文
/graphify query "<問題>" --dfs                         # DFS 深度優先查詢 - 追蹤特定路徑
/graphify query "<問題>" --budget 1500                 # 限制 Token 回覆上限
/graphify path "AuthModule" "Database"                # 尋找兩個概念之間的最短路徑
/graphify explain "SwinTransformer"                   # 以白話文解釋某個節點
```

## graphify 的用途

graphify 的核心理念源於 Andrej Karpathy 的 /raw 資料夾工作流：將任何論文、推文、截圖、程式碼、筆記全部丟到一個資料夾裡，然後得到一張結構化的知識圖譜，為你找出你沒料想過的關聯。

單靠 LLM 做不到，但這工具能幫你做到的三件事：
1. **持久化圖譜** - 所有關聯存入 `graphify-out/graph.json`，可跨會話存續。
2. **誠實稽核軌跡** - 每條邊都標註 EXTRACTED、INFERRED 或 AMBIGUOUS。
3. **跨文件驚喜發現** - 社群偵測會從不同檔案的概念中找出隱藏連結。

## 被呼叫時你必須執行的動作

如果沒有指定路徑，使用 `.` (當前目錄)。不要詢問使用者路徑。

**在執行任何步驟之前**，請檢查以下快捷方式條件：

- 如果唯一 flag 是 `--mcp` 且 `graphify-out/graph.json` 檔案存在：執行 `python -m graphify.serve graphify-out/graph.json` 並停止。不要執行pipeline。

- 如果唯一新增的 flags 與匯出相關（`--wiki`、`--obsidian`、`--svg`、`--graphml`）且 `graphify-out/graph.json` 檔案存在：執行 `python -m graphify pipeline export [flags]` 並停止。不要執行pipeline。

請依照以下步驟順序執行，不可跳過任何步驟。**重要提示：**請分開執行每個指令，絕對不要使用 `&&` 來串接指令 (PowerShell 5 不支援)。

### Step 1 - 確認 graphify 已安裝

```
python -m graphify pipeline check-install
```

如果印出錯誤，告知使用者並停止。否則靜默繼續。

### Step 2 - 偵測檔案

```
python -m graphify pipeline detect INPUT_PATH
```

將 INPUT_PATH 替換為實際路徑。讀取 JSON 輸出：

- 如果 `action` 是 `"stop"`：告知使用者 "No supported files found in [路徑]" 並停止。
- 如果 `action` 是 `"ask_user"`：印出 `confirmation_prompt` 欄位並等待使用者回答。
- 如果 `action` 是 `"proceed"`：印出 `summary` 欄位並繼續。
- 如果 `skipped_count` > 0：提及被跳過的檔案數量（不要顯示檔名）。

### Step 3 - 提取實體與關聯

此步驟有兩條平行路線：**AST 結構化提取**（確定性、免費）和**語意提取**（LLM、需要 Token 成本）。盡可能平行執行。

#### Part A - 程式碼檔案的 AST 提取

```
python -m graphify pipeline ast-extract
```

#### Part B - 語意提取

**快速通關：** 如果偵測結果顯示 `code_only: true`，跳過整個 Part B 直接進入 Part C。

**B0 - 檢查快取：**

```
python -m graphify pipeline cache-check
```

如果輸出中 `skip_semantic` 為 true，直接進入 Part C。

**B1 - 準備 chunk 及 prompt 檔案：**

```
python -m graphify pipeline prepare-semantic [--deep]
```

如果原始呼叫使用了 `--mode deep` 就加上 `--deep`。讀取 JSON 輸出中的 `total_chunks`。

**B2 - 派發：**

如果 `total_chunks` 為 0，跳到 Part C。

針對 1 到 `total_chunks` 的每個 chunk，建構下方的 PowerShell 指令（將 `i` 替換為實際數字）。將所有 chunk 的指令丟到背景平行執行。

```powershell
Get-Content graphify-out\.graphify_prompt_i.txt -Raw | gemini --yolo | Out-File -FilePath graphify-out\.graphify_chunk_i.json -Encoding utf8
```

等待所有的背景執行完畢後，再進入下個步驟。
If a chunk fails with 429 (Too Many Requests), wait 30 seconds and retry once before reporting failure.

**B3 - 合併結果：**

```
python -m graphify pipeline merge-semantic
```

如果輸出狀態顯示失敗，只重新執行失敗的 chunk，然後再次執行 merge-semantic。

#### Part C - 合併 AST + 語意結果

```
python -m graphify pipeline merge-all
```

### Step 4 - 建立圖譜、分群、分析

```
python -m graphify pipeline build INPUT_PATH
```

如果以錯誤結束（空圖譜），停止並告知使用者。

### Step 5 - 為社群命名標記

讀取 `graphify-out/.graphify_analysis.json`。針對每個社群鍵值，查看其節點名稱並指定 2-5 個字的人類可讀名稱（例如 "Attention Mechanism"、"Training Pipeline"、"Data Loading"）。

將標籤寫出至檔案 `graphify-out/labels_draft.json`

然後套用標籤：

```
python -m graphify pipeline label --from-file graphify-out/labels_draft.json --path INPUT_PATH
```

### Step 6-7 - 產生輸出

```
python -m graphify pipeline export [--obsidian] [--obsidian-dir DIR] [--svg] [--graphml] [--neo4j] [--neo4j-push URI] [--wiki] [--no-viz]
```

將使用者在原始呼叫中指定的 flags 原封不動傳入。HTML 預設產生，除非指定 `--no-viz`。

**如果是 `--neo4j-push`：** 執行前先向使用者詢問帳號密碼。

### Step 7d - MCP 伺服器（僅限指定 --mcp 時）

```
python -m graphify.serve graphify-out/graph.json
```

### Step 8 - 基準測試

```
python -m graphify pipeline benchmark
```

如果有執行就印出結果。小型語料庫會自動跳過。

### Step 9 - 收尾與報告

```
python -m graphify pipeline finalize INPUT_PATH
```

**在 finalize 執行完畢後停止。不要重試任何失敗的步驟。**

然後告知使用者（除非指定了 --obsidian，否則省略 obsidian 那行）：

```
Graph complete. Outputs in graphify-out/

  graph.html            - 互動式圖譜，用瀏覽器開啟
  GRAPH_REPORT.md       - 稽核報告
  graph.json            - 原始圖譜資料
  obsidian/             - Obsidian 筆記庫（僅當指定 --obsidian）
```

將 GRAPH_REPORT.md 中的以下三個段落貼入對話：
- God Nodes（上帝節點）
- Surprising Connections（驚喜連結）
- Suggested Questions（推薦問題）

不要貼出完整報告，只貼這三個段落。

然後挑出最有趣的推薦問題並詢問：

> "這張圖譜能解答的最有趣的問題是：**[問題]**。需要我幫你追蹤嗎？"

如果使用者同意，用 `/graphify query "[問題]"` 並順著圖譜結構引導使用者理解答案。每次回覆結尾留一個自然的後續跟進，讓對話像導覽而非一次性報告。

---

## 用於 --update（漸進式重新提取）

```
python -m graphify pipeline update-detect INPUT_PATH
```

讀取 JSON 輸出：
- 如果 `action` 是 `"stop"`：印出訊息並停止。
- 如果 `code_only` 為 true：印出 "[graphify update] Code-only changes - skipping semantic extraction"，僅執行 ast-extract，跳過 Part B，然後 merge-all 並繼續 Steps 4-9。
- 否則：按照正常流程執行完整的 Steps 3A-3C 管線。

merge-all 之後，合併到既有圖譜：

```
python -m graphify pipeline update-merge
```

然後繼續 Steps 4-9。

---

## 用於 --cluster-only

```
python -m graphify pipeline cluster-only
```

然後執行 Steps 5-9（命名、匯出、基準測試、收尾）。

---

## 用於 --book（書本模式）

觸發條件：使用者執行 `/graphify <book_folder> --book`，或偵測結果中 `book_mode` 為 true。

書本模式處理自然語言文本（書籍、長篇文件），產出 Claim/Evidence 論證圖譜，而非程式碼知識圖譜。

**重要：** 以下所有 pipeline 指令都使用 `--out-dir <book_folder>/graphify-out`，將輸出放在書本資料夾內。

請依序執行以下步驟：

### Book Step 1 - 偵測

```
python -m graphify pipeline --out-dir <book_folder>/graphify-out detect --book <book_folder>/
```

讀取 JSON 輸出確認 `book_mode` 為 true。如果不是，回退到一般管線。

### Book Step 2 - 準備 chunk 及 prompt 檔案

```
python -m graphify pipeline --out-dir <book_folder>/graphify-out book-prepare
```

產出：`book_chunks/` 內的 chunk 檔案、prompt 檔案、以及空的 AST stub。讀取 JSON 輸出中的 `total_chunks`。

### Book Step 3 - 語意提取（LLM 步驟 - 由你處理）

針對 1 到 `total_chunks` 的每個 chunk：

1. 讀取 prompt 檔案：`<book_folder>/graphify-out/.graphify_prompt_<i>.txt`
2. 檢查 prompt 中 METADATA header 是否有 "Images in this chunk:" 行
3. 如果有列出圖片：將那些圖片檔案（路徑相對於書本資料夾）與 prompt 一起送出進行多模態分析
4. 將 prompt（加上圖片，如果有的話）送給 LLM
5. 將原始 JSON 回應儲存至 `<book_folder>/graphify-out/.graphify_chunk_<i>.json`

平行處理：同時處理最多 5 個 chunk。如果 chunk 因 429 錯誤失敗，等待 30 秒後重試一次。

每個 chunk JSON 回應的 Schema 約束：
- `nodes[].type`：僅限 `"Claim"` 或 `"Evidence"`
- `edges[].type`：僅限 `"supports"`、`"refines"` 或 `"conflicts"`
- 必須包含：`{"nodes": [...], "edges": [...], "hyperedges": []}`

### Book Step 4 - 合併語意結果

```
python -m graphify pipeline --out-dir <book_folder>/graphify-out merge-semantic
```

如果輸出狀態顯示失敗，只重新執行失敗的 chunk，然後再次執行 merge-semantic。

### Book Step 5 - 合併全部

```
python -m graphify pipeline --out-dir <book_folder>/graphify-out merge-all
```

### Book Step 6 - 建立圖譜、分群、分析

```
python -m graphify pipeline --out-dir <book_folder>/graphify-out build <book_folder>/
```

如果以錯誤結束（空圖譜），停止並告知使用者。

### Book Step 7 - 為社群命名標記（LLM 步驟 - 由你處理）

讀取 `<book_folder>/graphify-out/.graphify_analysis.json`。針對每個社群鍵值，查看其節點名稱並指定 2-5 個字的人類可讀名稱（例如 "Moore's Law Evidence"、"Computational Limits"、"Neural Architecture Claims"）。

將標籤寫出至 `<book_folder>/graphify-out/labels_draft.json`，然後套用：

```
python -m graphify pipeline --out-dir <book_folder>/graphify-out label --from-file <book_folder>/graphify-out/labels_draft.json --path <book_folder>/
```

### Book Step 8 - 匯出

```
python -m graphify pipeline --out-dir <book_folder>/graphify-out export [--obsidian] [--wiki]
```

將使用者在原始呼叫中指定的 flags 原封不動傳入。

### Book Step 9 - 收尾

```
python -m graphify pipeline --out-dir <book_folder>/graphify-out finalize <book_folder>/
```

**在 finalize 執行完畢後停止。不要重試任何失敗的步驟。**

然後告知使用者：

```
Book graph complete. Outputs in <book_folder>/graphify-out/

  graph.html            - 互動式論證圖譜，用瀏覽器開啟
  GRAPH_REPORT.md       - 稽核報告
  graph.json            - 原始圖譜資料（Claim/Evidence 節點）
  obsidian/             - Obsidian 筆記庫（僅當指定 --obsidian）
```

將 GRAPH_REPORT.md 中的以下三個段落貼入對話：
- God Nodes（上帝節點）
- Surprising Connections（驚喜連結）
- Suggested Questions（推薦問題）

---

## 用於 /graphify query

如果問題中包含非英語術語，請在執行查詢前將關鍵概念翻譯成英文。例如，“執行流程”→“pipeline execution flow”，“錯誤處理”→“error handling”。由於圖譜節點使用英文，因此查詢關鍵字也必須是英文才能獲得匹配結果。

```
graphify query "問題" [--dfs] [--budget N]
```

使用 `--dfs` 處理「X 如何到達 Y？」的問題。使用預設 BFS 處理「什麼與 X 相連？」的問題。

回答時**僅**使用圖譜中包含的資訊。如果圖譜資料不足，如實說明，不要虛構。

回答後儲存結果：

```
graphify save-result --question "問題" --answer "回答" --type query --nodes NODE1 NODE2
```

---

## 用於 /graphify path

```
python -m graphify pipeline path "NODE_A" "NODE_B"
```

用白話文解釋路徑 - 每一跳代表什麼意義、為何重要。然後儲存：

```
graphify save-result --question "Path from NODE_A to NODE_B" --answer "回答" --type path_query --nodes NODE_A NODE_B
```

---

## 用於 /graphify explain

```
python -m graphify pipeline explain "NODE_NAME"
```

用 3-5 句話解釋這個節點是什麼、它連接到什麼、以及這些連結為何重要。然後儲存：

```
graphify save-result --question "Explain NODE_NAME" --answer "回答" --type explain --nodes NODE_NAME
```

---

## 用於 /graphify add

```
python -m graphify pipeline add URL [--author "名字"] [--contributor "名字"]
```

如果成功，自動對 `./raw` 執行 `--update` 管線。

---

## 用於 --watch

```
python -m graphify.watch INPUT_PATH --debounce 3
```

- 程式碼檔案變更：自動重建（不需 LLM）。
- 文件/圖片變更：寫入旗標，通知你執行 `/graphify --update`。

---

## 用於 git hooks

```
graphify hook install     # 安裝 post-commit/post-checkout hooks
graphify hook uninstall   # 移除 hooks
graphify hook status      # 檢查狀態
```

---

## 用於 GEMINI.md 整合

```
graphify gemini install   # 寫入 graphify 段落到 GEMINI.md
graphify gemini uninstall # 移除段落
```

---

## 誠實守則

- 絕不虛構邊。不確定就用 AMBIGUOUS。
- 絕不跳過語料庫檢查警告。
- 報告中一律顯示 Token 成本。
- 不以符號隱藏 cohesion 分數，一律顯示原始數值。
- 圖譜超過 5,000 個節點時，不警告使用者就絕不執行 HTML 視覺化。
