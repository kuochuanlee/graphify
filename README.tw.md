# graphify

[English](README.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja-JP.md) | [한국어](README.ko-KR.md) | [繁體中文](README.tw.md)

[![CI](https://github.com/safishamsi/graphify/actions/workflows/ci.yml/badge.svg?branch=v3)](https://github.com/safishamsi/graphify/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/graphifyy)](https://pypi.org/project/graphifyy/)
[![Downloads](https://img.shields.io/pypi/dm/graphifyy)](https://pypi.org/project/graphifyy/)
[![Sponsor](https://img.shields.io/badge/sponsor-safishamsi-ea4aaa?logo=github-sponsors)](https://github.com/sponsors/safishamsi)

**一個 AI 程式設計助理技能。** 在 Claude Code、Codex、OpenCode、OpenClaw、Factory Droid 或 Trae 中輸入 `/graphify` - 它會讀取你的檔案，建立知識圖譜，並為你呈現出其中隱藏的架構。幫助你更快地理解專案原始碼。找出架構決策背後的「原因」。

完全支援多模態。丟入程式碼、PDF、Markdown 檔案、截圖、圖表、白板照片，甚至是其他語言的圖片 - graphify 會使用 Claude 的視覺解析能力，從中提取概念和關聯性，並將它們連結成一個知識圖譜。透過 tree-sitter AST 支援 20 種程式語言（Python、JS、TS、Go、Rust、Java、C、C++、Ruby、C#、Kotlin、Scala、PHP、Swift、Lua、Zig、PowerShell、Elixir、Objective-C、Julia）。

> Andrej Karpathy 習慣保留一個 `/raw` 資料夾，用來放置各種論文、推文、截圖和筆記。graphify 就是為了解決這個問題而生 - 相較於直接閱讀原始檔案，每次查詢節省了高達 71.5 倍的 Token，圖譜資料跨會話持久保存，並且會誠實標示哪些內容是「擷取自原文」還是「推理猜測」。

```
/graphify .                        # 適用於任何資料夾 - 你的程式庫、筆記、論文或任何檔案
```

```
graphify-out/
├── graph.html       互動式圖譜 - 點擊節點、搜尋、依社群過濾
├── GRAPH_REPORT.md  神級節點、意外關聯、建議的提問清單
├── graph.json       持久化圖譜資料 - 可供數週後直接查詢，不需重新閱讀檔案
└── cache/           SHA256 快取 - 重新執行時只處理異動過的檔案
```

你可以加上一個 `.graphifyignore` 檔案，用來排除不想加入圖譜的資料夾：

```
# .graphifyignore
vendor/
node_modules/
dist/
*.generated.py
```

這與 `.gitignore` 的語法完全相同。規則比對基準是你執行 graphify 所在的相對目錄路徑。

## 運作原理

graphify 分兩階段執行。第一階段，透過確定性的 AST (抽象語法樹) 解析程式碼結構（包含類別、函式、匯入、呼叫圖譜、文件字串、原由註解），這部分完全不需要使用 LLM。第二階段，Claude 子代理（Subagent）以平行處理的方式讀取文件、論文與圖片，從中提取概念、關聯以及設計原由。結果會合併至 NetworkX 圖譜物件，再透過 Leiden 社群演算法（Community Detection）進行分群，最後匯出為互動式 HTML、可供查詢的 JSON 檔案，以及一份白話文的稽核報告。

**分群是基於圖譜的拓撲結構 — 不使用向量嵌入（Embeddings）。** Leiden 演算法是透過邊界密度（Edge density）來尋找社群。Claude 所提取的語意相似性關聯（例如 `semantically_similar_to`，標記為 INFERRED）已經存在於圖譜中，因此它們會直接影響社群偵測。圖譜結構本身就是相似性的訊號 — 完全不需要額外的嵌入運算步驟或向量資料庫。

每一段關聯性都會被加上標籤：`EXTRACTED`（在來源中直接發現）、`INFERRED`（合理的推論，附帶信心分數），或是 `AMBIGUOUS`（標記為待審閱）。你永遠能清楚分辨哪些是真實擷取到的內容，哪些是猜測出來的。

## 安裝方式

**需求環境：** Python 3.10+ 以及下列其中之一: [Claude Code](https://claude.ai/code)、[Codex](https://openai.com/codex)、[OpenCode](https://opencode.ai)、[OpenClaw](https://openclaw.ai)、[Factory Droid](https://factory.ai) 或 [Trae](https://trae.ai)

```bash
pip install graphifyy && graphify install
```

> 由於 `graphify` 這個名稱正在要求取回權限中，所以上架於 PyPI 的套件名稱暫時命名為 `graphifyy`。但 CLI 和技能指令皆依然維持 `graphify`。

### 平台支援度

| 平台 | 安裝指令 |
|----------|----------------|
| Claude Code (Linux/Mac) | `graphify install` |
| Claude Code (Windows) | `graphify install` (自動偵測) 或 `graphify install --platform windows` |
| Codex | `graphify install --platform codex` |
| OpenCode | `graphify install --platform opencode` |
| OpenClaw | `graphify install --platform claw` |
| Factory Droid | `graphify install --platform droid` |
| Trae | `graphify install --platform trae` |
| Trae CN | `graphify install --platform trae-cn` |
| Gemini CLI | `graphify install --platform gemini` |

Codex 使用者也需要在 `~/.codex/config.toml` 下的 `[features]` 補上 `multi_agent = true` 才能啟用平行提取。Factory Droid 透過 `Task` 工具來進行平行代理指派。OpenClaw 由於平台本身對於平行工具支援度尚在初期，只使用循序提取。Trae 使用 Agent 工具指派但不支援 PreToolUse hooks — 而是透過 AGENTS.md 常駐機制。

接著打開你的 AI 程式開發助理，並輸入：

```
/graphify .
```

注意：Codex 執行技能使用的前綴為 `$`，因此請輸入 `$graphify .` 代替。

### 讓你的 AI 助理預設讀取圖譜 (強烈建議)

圖譜建立完成後，在專案內執行一次以下指令：

| 平台 | 指令 |
|----------|---------|
| Claude Code | `graphify claude install` |
| Codex | `graphify codex install` |
| OpenCode | `graphify opencode install` |
| OpenClaw | `graphify claw install` |
| Factory Droid | `graphify droid install` |
| Trae | `graphify trae install` |
| Trae CN | `graphify trae-cn install` |
| Gemini CLI | `graphify gemini install` |

以 **Claude Code** 為例，上述指令會完成兩件事：首先，將指示放入 `CLAUDE.md`，告訴 Claude 在回答架構問題前先詳讀 `graphify-out/GRAPH_REPORT.md`；其次，在 `.claude/settings.json` 安裝 **PreToolUse hook** 機制，每次執行 Glob 及 Grep 工具之前觸發提示。如此一來，如果圖譜存在，Claude 會看到：「_graphify: 知識圖譜存在。在全文搜尋之前，請先閱讀 GRAPH_REPORT.md 解神級節點和社群分群資訊。_」 — 讓 Claude 改用圖譜脈絡導航，而不再對全部專案亂槍打鳥。

**Codex** 會依樣畫葫蘆，寫入 `AGENTS.md` 並在 `.codex/hooks.json` 安裝 PreToolUse hook。

**OpenCode** 則同樣寫入 `AGENTS.md`，並註冊 **`tool.execute.before` 擴充功能**。

**OpenClaw、Factory Droid、Trae** 無工具攔截支援，所以只提供 `AGENTS.md` 的寫入常駐機制。

如果有需要解除安裝，請對照輸入移除指令即可（例如 `graphify claude uninstall`）。

**「常駐」與「主動指令」，兩者差異為何？**

每次常駐介入機制，會提示出 `GRAPH_REPORT.md`，一份列出重要節點、分群和特殊發現的簡要報告檔。當處理日常問題時，助理就能透過這張輪廓「地圖」回答你的問題。
而 `/graphify query`、`/graphify path`、`/graphify explain` 正確的深入原始圖譜細節。當你確實要進行深度解剖，想要看最底層到底有哪一種明確關聯以及置信度多少時，主動下令才會有最好的效果。總而言之：常駐功能提供環境地圖，手動指令給予更細緻的分析能力。

## 勿將 `graph.json` 直接餵給語言模型

切勿把整個 `graph.json` 全部丟進聊天內容中，這樣做並無益處。
推薦流程如下：

1. 先請助理閱讀 `graphify-out/GRAPH_REPORT.md`。
2. 遇到特定問題，再以 `graphify query` 擷取一部分需要探討的圖譜結構。
3. 將這小段局部的內容餵給模型。

例如：

```bash
graphify query "show the auth flow" --graph graphify-out/graph.json
graphify query "what connects DigestAuth to Response?" --graph graphify-out/graph.json
```

助理看到這樣的局部的節點名稱、關聯方向，就能更聚焦地討論原始檔。
如果你正在使用的 AI 助理對 MCP（Model Context Protocol）支援度很高，你可以啟動圖譜的伺服器。

```bash
python -m graphify.serve graphify-out/graph.json
```

如此一來，助理將可以無限量呼叫專屬抓取指令（`query_graph`, `get_node`, `get_neighbors`）深入查詢資料。

<details>
<summary>手動安裝指令 (curl)</summary>

```bash
mkdir -p ~/.claude/skills/graphify
curl -fsSL https://raw.githubusercontent.com/safishamsi/graphify/v3/graphify/skill.md \
  > ~/.claude/skills/graphify/SKILL.md
```

開啟 `~/.claude/CLAUDE.md`：

```
- **graphify** (`~/.claude/skills/graphify/SKILL.md`) - any input to knowledge graph. Trigger: `/graphify`
When the user types `/graphify`, invoke the Skill tool with `skill: "graphify"` before doing anything else.
```

</details>

## 完整用法

```
/graphify                          # 分析當前目錄
/graphify ./raw                    # 指定特定資料夾分析
/graphify ./raw --mode deep        # 對推論型 INFERRED 關聯採用更激進的擷取方式
/graphify ./raw --update           # 僅針對有變更的檔案重新執行提取，並合併回圖譜中
/graphify ./raw --cluster-only     # 不要重新提取檔案，只針對已有資料重新執行社群與分群演算法
/graphify ./raw --no-viz           # 省去 HTML 的繪製時間，僅生成報表與 JSON
/graphify ./raw --obsidian                          # 生成額外的 Obsidian 筆記庫 (預設不啟動)
/graphify ./raw --obsidian --obsidian-dir ~/vaults/myproject  # 將 Obsidian 筆記庫輸出到指定的路徑

/graphify add https://arxiv.org/abs/1706.03762        # 抓取一篇論文、儲存，然後更新到圖譜中
/graphify add https://x.com/karpathy/status/...       # 抓取推文
/graphify add https://... --author "Name"             # 為增加的文件特別加上作者標籤
/graphify add https://... --contributor "Name"        # 標註貢獻這份文件的人

/graphify query "what connects attention to the optimizer?"
/graphify query "what connects attention to the optimizer?" --dfs   # 指定使用 DFS 深度跟蹤依賴關聯順序
/graphify query "what connects attention to the optimizer?" --budget 1500  # 限制在 N 個 Token 以內
/graphify path "DigestAuth" "Response"
/graphify explain "SwinTransformer"

/graphify ./raw --watch            # (背景執行) 自動監控檔案更動。程式碼：即時同步圖譜 / 文件：顯示通知
/graphify ./raw --wiki             # （實驗性）建立類似維基百科的文件目錄庫 (包含 index.md 與社群文章)
/graphify ./raw --svg              # 產生靜態圖形 graph.svg
/graphify ./raw --graphml          # 匯出至 Gephi, yEd 生態系的 graph.graphml
/graphify ./raw --neo4j            # 給預計匯入 Neo4j 的使用者產生 cypher.txt
/graphify ./raw --neo4j-push bolt://localhost:7687    # 推送整套關聯至運作中的 Neo4j 資料庫
/graphify ./raw --mcp              # 直接以此專案開啟 MCP stdio 介面服務

# Git hooks - 跨平台通用。切換分支、或是每一次 commit，系統將自動從背景更新圖譜
graphify hook install
graphify hook uninstall
graphify hook status

# 常駐各系統 AI 輔助功能的設定指令 (為對應平台加掛專屬提示詞)
graphify claude install            # CLAUDE.md + PreToolUse hook (Claude Code)
graphify claude uninstall
graphify codex install             # AGENTS.md (Codex)
graphify opencode install          # AGENTS.md + tool.execute.before plugin (OpenCode)
graphify claw install              # AGENTS.md (OpenClaw)
graphify droid install             # AGENTS.md (Factory Droid)
graphify trae install              # AGENTS.md (Trae)
graphify trae uninstall
graphify trae-cn install           # AGENTS.md (Trae CN)
graphify trae-cn uninstall
graphify gemini install            # GEMINI.md (Gemini CLI)
graphify gemini uninstall

# 若不想依靠任何 AI 小幫手，你也可以直接在終端機對分析結果作簡單互動：
graphify query "what connects attention to the optimizer?"
graphify query "show the auth flow" --dfs
graphify query "what is CfgNode?" --budget 500
graphify query "..." --graph path/to/graph.json
```

支援各種檔案格式，就算混用也能完美讀取：

| 類型 | 附檔名支援 | 提取方式 |
|------|-----------|------------|
| 程式碼 | `.py .ts .js .jsx .tsx .go .rs .java .c .cpp .rb .cs .kt .scala .php .swift .lua .zig .ps1 .ex .exs .m .mm .jl` | AST (基於 tree-sitter) + 函數追蹤 + 文件字串/註解重點擷取 |
| 文件 | `.md .txt .rst` | 基於 Claude 的實體發現 + 原由設計剖析 |
| 辦公室軟體 | `.docx .xlsx` | 轉為 Markdown 語法再給 Claude（這包含需要執行安裝：`pip install graphifyy[office]`） |
| 論文 | `.pdf` | 語意名詞搜刮 + 參考文獻比對 |
| 圖像 | `.png .jpg .webp .gif` | Claude Vision - 針對架構截圖、螢幕繪圖、以及多語言畫面進行語意提取 |

## 此套件能帶來的產出物

**神級節點 (God nodes)** - 在整個系統裡交織度最大、最容易牽一髮動全身的節點。

**意外關聯 (Surprising connections)** - 最容易讓人沒想到的關聯。模型會給予程式碼與外在文件的橋樑最高的關注度。

**建議的提問清單 (Suggested questions)** - 根據現在你的系統狀態，你現在問這些問題將最能發揮這張圖譜最大的效益。

**不僅只是「怎麼做」，還有「為什麼」 (The "why")** - 設計層次的考量重點、特殊註解(`# NOTE:`, `# IMPORTANT:`, `# HACK:`, `# WHY:`) 等等，將轉換為 `rationale_for` 系列節點，讓初次接手的人不再看著程式碼瞎猜。

**信心程度 (Confidence scores)** - 第一線提取保證正確（`EXTRACTED` : 1.0）；其他衍生的脈絡推導會加上信心數值 `confidence_score` (0.0-1.0)，讓你可以區分猜測與現實。

**語意層級相似 (Semantic similarity edges)** - 模型能在沒有語法直接引用的情況下，找出「因為做類似事情而產生關聯」的對象。

**無關代碼的超邊連結 (Hyperedges)** - 單純依賴 A<->B 短距離邊線是無法還原出「這些零散功能全都是某身份驗證流程」這種概念的。這種特殊高階關係將有特殊的封裝與表達。

**消耗縮減成果 (Token benchmark)** - 圖譜的好處是減少你在日常溝通對 AI 一直餵食相同檔案的頻率。執行過一次將可以享受巨量 Token 的折抵，系統內建評估指令讓你自行看數據，在 50 個混合檔案專案裡可做到直接縮小至 **71.5x** 以下。（搭配 SHA256 快取則速度更快了）

**監控背景同步 (Auto-sync `--watch`)** - 對程式碼存檔，立刻更新 AST；對文件圖檔存檔，再對話列印通知。這是一套跟編輯器綁在一塊的開發輔助體驗。

## 實際測試成果分享

| 資料集庫 | 檔案數 | 降低耗損(Reduction) | 成果輸出參考 |
|--------|-------|-----------|--------|
| Karpathy 範例儲存庫 + 5 篇相關論文 + 4 張截圖 | 52 | **71.5x** | [`worked/karpathy-repos/`](worked/karpathy-repos/) |
| 本專案本身 (graphify) + Transformer架構論文 | 4 | **5.4x** | [`worked/mixed-corpus/`](worked/mixed-corpus/) |
| httpx (模擬 Python 開發庫日常) | 6 | ~1x | [`worked/httpx/`](worked/httpx/) |

當你的專案小而美的時候（檔案不多），單純把它丟給 Claude 或許最快也能輕鬆搞定（壓縮比為 1x）；但隨著圖譜檔案數目擴大，建立結構可以高達百倍的收益。

## 隱私權保護

graphify 是開源且本地發送的系統，並「不會遙測送出」你的電腦習慣或開發流程。
針對文字圖檔以及文件，將會發送給基層模型（如同平時使用的服務，如 OpenAI / Claude，取決於你本身的防禦/政策協議），若你的平台本身不拿資料做訓練，那 Graphify 也是。而至於你重要的「程式碼」結構，則完全是依賴本地本機環境下的 AST Tree-Sitter 解譯器去剖析提取，因此程式碼片段並不會因此流出傳送。

## 技術生態池

NetworkX + Leiden (依賴 graspologic 函式庫) + tree-sitter + vis.js。無伺服器，無向量庫（向量庫由實體圖譜技術取代），100% 於個人電腦在地建構與執行。

## 關於作者的下一步

Graphify 是一個圖譜基礎層面。我們現正以它為核心開發更新型的服務 [Penpax](https://safishamsi.github.io/penpax.ai)—它是一種全裝置的邊緣數位分身，致力於將你的筆記、會議、瀏覽及程式庫整合成一張不間斷的巨型圖譜，目前在預約階段。

## 回報與協作

如果發現有些部分解析異常，你可以利用 `graphify-out/cache/` 或是提供樣本給我們。如果你有意圖願貢獻一些分析測試，也可以參閱 `ARCHITECTURE.md` 了解我們的解構架構。

