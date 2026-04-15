# graphify (Book Mode)

[English](README.md) | [繁體中文](README.tw.md)

**一個 AI 輔助的書籍分析工具。** 在 Gemini CLI 中輸入 `/graphify <book_folder>` - 它會讀取你的書籍/文件檔案，建立 Claim/Evidence 論證圖譜，並揭示你原本沒發現的邏輯結構。更快地理解複雜論述。找出跨章節之間隱藏的概念連結。

> 將任何自然語言文本集合 - 書籍、論文、長篇文件 - 丟進一個資料夾，就能得到一張結構化的論證圖譜，展示主張、證據、以及它們之間的關聯。

```
/graphify ./my-book                # 分析書本資料夾
```

```
graphify-out/
+-- graph.html       互動式論證圖譜 - 點擊節點、搜尋、依社群過濾
+-- GRAPH_REPORT.md  神級節點、意外關聯、建議的提問清單
+-- graph.json       持久化圖譜 - 日後可直接查詢，不需重新閱讀
+-- obsidian/        Obsidian 筆記庫，用於導覽知識結構
+-- wiki/            可供 Agent 爬行的社群 wiki 文章
```

## 運作原理

graphify 將書本內容切分為可處理的 chunk，然後使用 LLM 語意提取從文本中辨識 Claim（主張）和 Evidence（證據）。每個 chunk 都會被分析其論證結構 - 提出了什麼主張、有什麼證據支持、論點之間如何精煉或衝突。結果會合併至 NetworkX 圖譜物件，再透過 Leiden 社群演算法進行分群，最後匯出為互動式 HTML、可供查詢的 JSON、Obsidian 筆記庫、以及白話文稽核報告。

**分群是基於圖譜的拓撲結構 - 不使用向量嵌入（Embeddings）。** Leiden 演算法透過邊界密度來尋找社群。圖譜結構本身就是相似性的訊號 - 不需要額外的嵌入運算或向量資料庫。

每一段關聯性都會被加上標籤：`EXTRACTED`（在來源中直接發現）、`INFERRED`（合理的推論）、或 `AMBIGUOUS`（標記為待審閱）。你永遠能清楚分辨哪些是真實擷取到的內容，哪些是猜測出來的。

## 安裝方式

**需求環境：** Python 3.10+ 以及 [Gemini CLI](https://github.com/google-gemini/gemini-cli)

```bash
pip install graphifyy
```

> 由於 `graphify` 名稱正在取回中，PyPI 套件暫時命名為 `graphifyy`。CLI 指令仍為 `graphify`。

接著為 Gemini CLI 安裝 skill：

```bash
graphify install --platform gemini
```

## 完整用法

```
/graphify <book_folder>                              # 在書本資料夾執行完整管線
/graphify <book_folder> --with-images                # 多模態圖片分析（消耗更多 token）
/graphify <book_folder> --no-viz                     # 跳過視覺化，僅產出報告 + JSON
/graphify <book_folder> --svg                        # 額外匯出 graph.svg
/graphify <book_folder> --graphml                    # 匯出 graph.graphml (Gephi, yEd)
/graphify <book_folder> --obsidian                   # Obsidian 筆記庫（預設開啟）
/graphify <book_folder> --wiki                       # Agent wiki（預設開啟）

/graphify query "<問題>"                              # BFS 廣度優先查詢 - 取得廣泛上下文
/graphify query "<問題>" --dfs                        # DFS 深度優先 - 追蹤特定路徑
/graphify query "<問題>" --budget 1500                # 限制 Token 回覆上限
/graphify path "NodeA" "NodeB"                       # 尋找兩個概念之間的最短路徑
/graphify explain "ConceptName"                      # 以白話文解釋某個節點
```

## 此工具能帶來的產出物

**神級節點 (God nodes)** - 在整個系統裡交織度最大、最容易牽一髮動全身的概念。

**意外關聯 (Surprising connections)** - 跨章節的關聯會獲得更高的排序。每個結果都附帶白話文的理由說明。

**建議的提問清單 (Suggested questions)** - 4-5 個這張圖譜最擅長回答的問題。

**Claim/Evidence 結構** - 節點分為 `Claim`（主張）和 `Evidence`（證據），邊分為 `supports`（支持）、`refines`（精煉）和 `conflicts`（衝突）。圖譜揭示整本書的論證骨架。

**信心分數 (Confidence scores)** - 每條 INFERRED 邊都有 `confidence_score` (0.0-1.0)，清楚分辨模型的猜測信心。

**可恢復的管線** - 如果提取被中斷，重新執行會自動從上次中斷處繼續。已完成的 chunk 會被偵測並自動跳過。

## 隱私權保護

graphify 透過 Gemini CLI 將文本內容傳送給你的 LLM 供應商進行語意提取。不做任何遙測、使用追蹤或分析。唯一的網路呼叫是提取過程中對你設定的模型 API 的請求。

## 技術生態

NetworkX + Leiden (graspologic) + vis.js。語意提取透過 Gemini。無伺服器，100% 在地執行。

## 架構

詳見 [ARCHITECTURE.tw.md](ARCHITECTURE.tw.md) 了解模組職責與管線資料流。
