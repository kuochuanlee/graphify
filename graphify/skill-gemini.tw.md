---
name: graphify
description: 自然語言文本（書籍、論文、文件）-> Claim/Evidence 論證圖譜 -> 社群分群 -> HTML + JSON + 稽核報告
trigger: /graphify
---

# /graphify

將任何自然語言文本集合（書籍、論文、長篇文件）轉化為可導覽的 Claim/Evidence 論證圖譜，具備社群偵測、誠實的稽核追蹤，並產出結構化輸出：互動式 HTML、可供 GraphRAG 讀取的 JSON、Obsidian 筆記庫、以及白話文版的 GRAPH_REPORT.md。

## 用法

```
/graphify <book_folder>                              # 在書本資料夾執行完整管線
/graphify <book_folder> --with-images                # 多模態圖片分析（消耗更多 token）
/graphify <book_folder> --no-viz                     # 跳過視覺化，僅產出報告 + JSON
/graphify <book_folder> --svg                        # 額外匯出 graph.svg
/graphify <book_folder> --graphml                    # 匯出 graph.graphml (Gephi, yEd)
/graphify <book_folder> --obsidian                   # 產生 Obsidian 筆記庫（書本模式預設開啟）
/graphify <book_folder> --obsidian --obsidian-dir ~/vaults/x  # 將筆記庫輸出到自訂路徑
/graphify <book_folder> --wiki                       # 建立可供 Agent 爬行的 wiki（書本模式預設開啟）
/graphify query "<問題>"                              # BFS 廣度優先查詢 - 取得廣泛的上下文
/graphify query "<問題>" --dfs                        # DFS 深度優先查詢 - 追蹤特定路徑
/graphify query "<問題>" --budget 1500                # 限制 Token 回覆上限
/graphify path "NodeA" "NodeB"                       # 尋找兩個概念之間的最短路徑
/graphify explain "SwinTransformer"                  # 以白話文解釋某個節點
```

## graphify 的用途

graphify 處理自然語言文本，產出結構化的 Claim/Evidence 論證圖譜，揭示跨文件的論證邏輯結構。

單靠 LLM 做不到，但這工具能幫你做到的三件事：
1. **持久化圖譜** - 所有關聯存入 `graphify-out/graph.json`，可跨會話存續。
2. **誠實稽核軌跡** - 每條邊都標註 EXTRACTED、INFERRED 或 AMBIGUOUS。
3. **跨文件驚喜發現** - 社群偵測會從不同檔案的概念中找出隱藏連結。

## 被呼叫時你必須執行的動作

**在執行任何步驟之前**，請檢查以下快捷方式條件：

- 如果唯一新增的 flags 與匯出相關（`--wiki`、`--obsidian`、`--svg`、`--graphml`）且 `<book_folder>/graphify-out/graph.json` 檔案存在：執行 `python -m graphify pipeline --out-dir <book_folder>/graphify-out export [flags]` 並停止。不要執行 pipeline。

**重要提示：** 請分開執行每個指令，絕對不要使用 `&&` 來串接指令（PowerShell 5 不支援）。

**重要提示：** 以下所有 pipeline 指令都使用 `--out-dir <book_folder>/graphify-out`，將輸出放在書本資料夾內。

請依照以下步驟順序執行：

### Step 1 - 確認 graphify 已安裝

```
python -m graphify pipeline check-install
```

如果印出錯誤，告知使用者並停止。否則靜默繼續。

### Step 2 - 偵測

```
python -m graphify pipeline --out-dir <book_folder>/graphify-out detect --book <book_folder>/
```

讀取 JSON 輸出確認偵測成功。

### Step 3 - 準備 chunk 及 prompt 檔案

```
python -m graphify pipeline --out-dir <book_folder>/graphify-out book-prepare
```

產出：`book_chunks/` 內的 chunk 檔案、prompt 檔案、以及空的 AST stub。讀取 JSON 輸出：
- `total_chunks`：總 chunk 數
- `completed_chunks`：先前執行已有有效結果的 chunk（已完成）
- `remaining_chunks`：仍需 LLM 處理的 chunk

如果 `remaining_chunks` 為空，表示所有 chunk 已完成，跳過 Step 4 直接前往 Step 5。

### Step 4 - 語意提取（LLM 步驟 - 由你處理）

僅處理 `remaining_chunks` 中列出的 chunk（不是全部 chunk）。

針對 `remaining_chunks` 中的每個 chunk 索引 `i`：

1. 讀取 prompt 檔案：`<book_folder>/graphify-out/.graphify_prompt_<i>.txt`
2. 將 prompt 文字送給 LLM
3. 將原始 JSON 回應儲存至 `<book_folder>/graphify-out/.graphify_chunk_<i>.json`

**僅當指定 `--with-images` 時：** 發送每個 prompt 前，檢查 METADATA header 是否有 "Images in this chunk:" 行。如果有列出圖片，將那些圖片檔案（路徑相對於書本資料夾）與 prompt 一起送出進行多模態分析。未指定 `--with-images` 時，忽略圖片引用，僅送文字。

平行處理：同時處理最多 5 個 chunk。如果 chunk 因 429 錯誤失敗，等待 30 秒後重試一次。

每個 chunk JSON 回應的 Schema 約束：
- `nodes[].type`：僅限 `"Claim"` 或 `"Evidence"`
- `edges[].type`：僅限 `"supports"`、`"refines"` 或 `"conflicts"`
- 必須包含：`{"nodes": [...], "edges": [...], "hyperedges": []}`

### Step 5 - 合併語意結果

```
python -m graphify pipeline --out-dir <book_folder>/graphify-out merge-semantic
```

如果輸出狀態顯示失敗，只重新執行失敗的 chunk，然後再次執行 merge-semantic。

### Step 6 - 合併全部

```
python -m graphify pipeline --out-dir <book_folder>/graphify-out merge-all
```

### Step 7 - 建立圖譜、分群、分析

```
python -m graphify pipeline --out-dir <book_folder>/graphify-out build <book_folder>/
```

如果以錯誤結束（空圖譜），停止並告知使用者。

### Step 8 - 為社群命名標記（LLM 步驟 - 由你處理）

讀取 `<book_folder>/graphify-out/.graphify_analysis.json`。針對每個社群鍵值，查看其節點名稱並指定 2-5 個字的人類可讀名稱（例如 "Moore's Law Evidence"、"Computational Limits"、"Neural Architecture Claims"）。

將標籤寫出至 `<book_folder>/graphify-out/labels_draft.json`，然後套用：

```
python -m graphify pipeline --out-dir <book_folder>/graphify-out label --from-file <book_folder>/graphify-out/labels_draft.json --path <book_folder>/
```

### Step 9 - 匯出

```
python -m graphify pipeline --out-dir <book_folder>/graphify-out export --obsidian --wiki
```

書本模式預設產生 Obsidian 筆記庫和 wiki。如果使用者有指定其他 flags（`--svg`、`--graphml`）也一併加入。

### Step 10 - 收尾

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
  obsidian/             - Obsidian 筆記庫
  wiki/                 - 可供 Agent 爬行的 wiki
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

## 用於 /graphify query

如果問題中包含非英語術語，請在執行查詢前將關鍵概念翻譯成英文。例如，"Moore's Law" 保持原文，但中日韓文需要翻譯。由於圖譜節點使用英文，因此查詢關鍵字也必須是英文才能獲得匹配結果。

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

## 誠實守則

- 絕不虛構邊。不確定就用 AMBIGUOUS。
- 絕不跳過語料庫檢查警告。
- 報告中一律顯示 Token 成本。
- 不以符號隱藏 cohesion 分數，一律顯示原始數值。
- 圖譜超過 5,000 個節點時，不警告使用者就絕不執行 HTML 視覺化。
