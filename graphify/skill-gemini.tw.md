---
name: graphify
description: 任何輸入 (程式碼、文件、論文、圖片) → 知識圖譜 → 社群分群 → HTML + JSON + 稽核報告
trigger: /graphify
---

# /graphify

將任何資料夾內的檔案，轉化為具備社群分群偵測、透明誠實稽核追蹤功能，且支援導覽的知識圖譜。產出物包含三項：互動式 HTML、可供 GraphRAG 讀取的 JSON、以及白話文版本的 GRAPH_REPORT.md。

## 用法

```
/graphify                                             # 在當前目錄執行完整管線 → 產出 Obsidian 筆記庫
/graphify <path>                                      # 在指定路徑執行完整管線
/graphify <path> --mode deep                          # 深度提取，產生更豐富的推演 (INFERRED) 關聯邊
/graphify <path> --update                             # 漸進式更新 - 僅對新增/變更的檔案重新提取
/graphify <path> --cluster-only                       # 針對現有圖譜重新執行分群演算
/graphify <path> --no-viz                             # 跳過視覺化 HTML，僅產出報告 + JSON
/graphify <path> --html                               # (HTML 預設本來就會產生，這標籤只是防呆)
/graphify <path> --svg                                # 匯出 graph.svg 靜態圖 (可嵌入 Notion, GitHub)
/graphify <path> --graphml                            # 匯出 graph.graphml (可供 Gephi, yEd 使用)
/graphify <path> --neo4j                              # 產生 graphify-out/cypher.txt 供 Neo4j 匯入
/graphify <path> --neo4j-push bolt://localhost:7687   # 直接將結構推送到 Neo4j 資料庫
/graphify <path> --mcp                                # 啟動 MCP stdio 授權介面供 AI 代理人讀取
/graphify <path> --watch                              # 監控資料夾，程式碼變更時自動重建 (不需耗費 LLM 成本)
/graphify <path> --wiki                               # 建立讓 Agent 容易爬行的維基百科 (包含 index.md 與每個社群的文章)
/graphify <path> --obsidian --obsidian-dir ~/vaults/my-project  # 將筆記庫輸出到自訂路徑
/graphify add <url>                                   # 抓取網址，存入 ./raw 後更新圖譜
/graphify add <url> --author "名字"                   # 標記文章原作者
/graphify add <url> --contributor "名字"              # 標記檔案提供者
/graphify query "<問題>"                               # BFS 廣度優先查詢 - 取得廣泛的上下文情境
/graphify query "<問題>" --dfs                         # DFS 深度優先查詢 - 追蹤特定依賴路徑
/graphify query "<問題>" --budget 1500                 # 限制 Token 回覆上限
/graphify path "AuthModule" "Database"                # 尋找兩個概念之間的最短路徑
/graphify explain "SwinTransformer"                   # 以白話文解釋某個特定節點脈絡
```

## graphify 的用途

graphify 的核心理念源於 Andrej Karpathy 的 `/raw` 資料夾工作流：將任何論文、推文、截圖、程式碼、筆記全部丟到一個資料夾裡——然後得到一張結構化的知識圖譜，為你找出你沒料想過的各種事物關聯。

單靠 Claude 做不到，但這工具能幫你做到的三件事：
1. **持久化的圖譜資料 (Persistent graph)** - 所有關聯資料都存入 `graphify-out/graph.json` 並且可跨會話存續。就算過了幾週再提問，也不必花時間花錢重新閱讀所有文件。
2. **誠實的稽核軌跡 (Honest audit trail)** - 每一條連線（Edge）都會標註是 EXTRACTED (原文直接擷取)、INFERRED (邏輯推演) 或 AMBIGUOUS (模糊不清)。你可以清楚區分什麼是明確找出的，什麼是模型猜測出來的。
3. **跨文件的驚喜發現 (Cross-document surprise)** - 社群演算法會從不同檔案的概念中找出隱藏連結，這些往往是你從來沒想過要直接問的事情。

適用情境：
- 面對一個全新接觸的專案原始碼 (動手改 Code 之前先理解整個架構)
- 處理長篇的閱讀清單 (把論文 + 推文 + 筆記 變成一張可導覽的圖譜)
- 研究文獻庫 (結合參考文獻網絡與概念圖譜)
- 你的個人 `/raw` 資料夾 (丟進去、讓它生長、對它提問)

## 被呼叫時你必須執行的動作

如果沒有指定路徑參數，請使用 `.` (當前目錄)。不要回過頭來詢問使用者路徑。

請嚴格遵循下列執行順序。嚴禁略過任何一個步驟。

### Step 1 - 確認 graphify 已經安裝完成

**首先偵測系統環境，然後執行對應的指令區塊。**

**Bash (Linux / macOS / WSL):**
```bash
# Detect the correct Python interpreter (handles pipx, venv, system installs)
GRAPHIFY_BIN=$(which graphify 2>/dev/null)
if [ -n "$GRAPHIFY_BIN" ]; then
    PYTHON=$(head -1 "$GRAPHIFY_BIN" | tr -d '#!')
    case "$PYTHON" in
        *[!a-zA-Z0-9/_.-]*) PYTHON="python3" ;;
    esac
else
    PYTHON="python3"
fi

# Verify graphify is importable — never auto-install
if ! "$PYTHON" -c "import graphify" 2>/dev/null; then
    echo "ERROR: graphify not found in the active Python environment." >&2
    echo "Please activate your project venv and install manually:" >&2
    echo "  uv pip install -e ." >&2
    echo "  # or: uv add graphifyy" >&2
    exit 1
fi

mkdir -p graphify-out
"$PYTHON" -c "import sys; open('graphify-out/.graphify_python', 'w').write(sys.executable)"
```

**PowerShell (Windows):**
```powershell
$importCheck = python -c "import graphify" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Error "ERROR: graphify not found in the active Python environment."
    Write-Error "Please activate your project venv and install manually:"
    Write-Error "  uv pip install -e ."
    exit 1
}
New-Item -ItemType Directory -Force -Path graphify-out | Out-Null
python -c "import sys; open('graphify-out/.graphify_python', 'w').write(sys.executable)"
```

如果 import 成功，不需印出任何資訊，直接進入 Step 2。

**在後續所有的 shell 指令區塊中：**
- **Bash:** 請將 `python3` 替換為 `$(cat graphify-out/.graphify_python)`
- **PowerShell:** 請將 `python` 替換為 `(Get-Content graphify-out/.graphify_python -Raw).Trim()`

### Step 2 - 檔案偵測 (Detect files)

```bash
$(cat graphify-out/.graphify_python) -c "
import json
from graphify.detect import detect
from pathlib import Path
result = detect(Path('INPUT_PATH'))
print(json.dumps(result))
" > graphify-out/.graphify_detect.json
```

將 INPUT_PATH 替換為使用者實際提供的路徑。**千萬不要**使用 cat 直接印出整個 JSON 內容 - 請在默默讀取資料後，改用乾淨的結果摘要呈現：

```
語料庫: X 個檔案 · 約 Y 個單字
  程式碼:   N 個檔案 (.py .ts .go ...)
  文件:     N 個檔案 (.md .txt ...)
  論文:     N 個檔案 (.pdf ...)
  圖片:     N 個檔案
```

接著依照結果採取處置：
- 如果 `total_files` 是 0: 停止分析並回覆 "No supported files found in [路徑]."
- 如果 `skipped_sensitive` 不是空的: 指出被略過的檔案「數量與範圍」，絕對不要把略過檔名印出來。
- 如果 `total_words` > 2,000,000 或是 `total_files` > 200: 列出檔案數目最多的前 5 大子目錄，並詢問要挑選哪一個子目錄進行。必須等待使用者回答後再繼續。
- 以外的情形: 直奔 Step 3，不要用廢話詢問了。

### Step 3 - 提取實體與關聯 (Extract entities and relationships)

**開始之前：** 確認原指令是否有指定 `--mode deep`。如果有，接下來在 Step B2 時，你必須強制把 `DEEP_MODE=true` 帶給每一個子代理人 (subagent)。記住這項初始呼叫的意圖，不要漏掉。

這個大步驟分為兩條線：**結構化提取** (結果具有確定性且免耗費成本) 和 **語意提取** (LLM 分析，需要 Token 成本)。

**請平行執行 Part A (AST) 與 Part B (語意)。在同一個回應中，同時派遣所有語意代理人並啟動 AST 程式結構提取。因為兩者處理的檔案類型完全不同，你可以同步跑。等完了再於 Part C 合併。**

注意：AST + 語意能為大專案節省 5-15 秒時間。AST 相當快；請在代理人研讀文件與論文的時候一起分工啟動。

#### Part A - 程式碼檔案的結構提取 (AST)

對於偵測到的程式碼檔案，馬上在背景平行打給系統進行 AST 解析：

```bash
$(cat graphify-out/.graphify_python) -c "
import sys, json
from graphify.extract import collect_files, extract
from pathlib import Path
import json

code_files = []
detect = json.loads(Path('graphify-out/.graphify_detect.json').read_text())
for f in detect.get('files', {}).get('code', []):
    code_files.extend(collect_files(Path(f)) if Path(f).is_dir() else [Path(f)])

if code_files:
    result = extract(code_files)
    Path('graphify-out/.graphify_ast.json').write_text(json.dumps(result, indent=2))
    print(f'AST: {len(result[\"nodes\"])} nodes, {len(result[\"edges\"])} edges')
else:
    Path('graphify-out/.graphify_ast.json').write_text(json.dumps({'nodes':[],'edges':[],'input_tokens':0,'output_tokens':0}))
    print('No code files - skipping AST extraction')
"
```

#### Part B - 語意提取 (平行代理人 subagents)

**快速通關 (Fast path):** 如果偵測階段發現 0 個文件、論文或圖片（純 Code 專案），請立刻跳過整個 Part B，直奔 Part C 進行合併。AST 就已經包辦了程式碼的所有處理，此時不需要指派任何語意代理人。

**強制規定：你務必要平行分派所有區塊 (chunks)。嚴禁你親自逐一讀取檔案 - 太無效率，會慢上 5-10 倍。**

**如果你在 Gemini CLI：** 請先把每一個 chunk 的提示詞都寫進暫存檔，然後再一口氣利用背景行程全部丟出去。
請偵測你的系統環境，並選擇對應的指令執行：

**Bash (Linux / macOS / WSL):**
```bash
for i in $(seq 1 $TOTAL_CHUNKS); do
  gemini --yolo -p "$(cat graphify-out/.graphify_prompt_$i.txt)" \
    > graphify-out/.graphify_chunk_$i.json 2>&1 &
done
wait
```

**PowerShell (Windows):**
```powershell
$jobs = 1..$env:TOTAL_CHUNKS | ForEach-Object {
    $i = $_
    Start-Job -ScriptBlock {
        $prompt = Get-Content "graphify-out/.graphify_prompt_$using:i.txt" -Raw
        gemini --yolo -p $prompt | Out-File "graphify-out/.graphify_chunk_$using:i.json" -Encoding utf8
    }
}
$jobs | Wait-Job | Receive-Job
Remove-Job -Job $jobs
```

**如果你在 Claude Code：** 在你的同一則回應 (RESPONSE) 當中，連續呼叫多次 Agent 工具 — 一個區塊呼叫一次。

在派出子代裡人之前，請先印出一則耗時評估預測（timing estimate）：
- 從 `graphify-out/.graphify_detect.json` 讀取 `total_words` 與各類檔案總數。
- 預估代理人數目：`ceil(uncached_non_code_files / 22)` (平均每個 chunk 為 20-25 個檔案)
- 預估耗費時間：每一批次約需 45 秒 (因為是平行跑，所以總共就是 ≈ 45s × ceil(代理人數/平行上限))
- 在畫面上印出：「Semantic extraction: ~N files → X agents, estimated ~Ys (語意提取：~N 個檔案 → X 位代理人，預估約 ~Y 秒)」

**Step B0 - 優先檢查快取 (Check extraction cache first)**

在派發任何代理人前，先檢查有哪些檔案早就已經存有快取：

```bash
$(cat graphify-out/.graphify_python) -c "
import json
from graphify.cache import check_semantic_cache
from pathlib import Path

detect = json.loads(Path('graphify-out/.graphify_detect.json').read_text())
all_files = [f for files in detect['files'].values() for f in files]

cached_nodes, cached_edges, cached_hyperedges, uncached = check_semantic_cache(all_files)

if cached_nodes or cached_edges or cached_hyperedges:
    Path('graphify-out/.graphify_cached.json').write_text(json.dumps({'nodes': cached_nodes, 'edges': cached_edges, 'hyperedges': cached_hyperedges}))
Path('graphify-out/.graphify_uncached.txt').write_text('\n'.join(uncached))
print(f'Cache: {len(all_files)-len(uncached)} files hit, {len(uncached)} files need extraction')
"
```

只有表列於 `graphify-out/.graphify_uncached.txt` 中的檔案，才需要指派代理人去讀。如果萬一所有圖檔跟文件全都在快取裡了，那麼請立刻跳過直接去 Part C。

**Step B1 - 切分處理區塊 (Split into chunks)**

讀取 `graphify-out/.graphify_uncached.txt` 的名單。將檔案依據 20 到 25 個為一組的方式切分 (chunks)。請讓每一張「圖片」自成一個獨自的區塊（因為視覺解析需要獨立脈絡）。在分組切分時，請盡量把來自「同一個資料夾」的文字檔案群組在同一個 chunk 裡提交，這非常重要，這能大幅提高他們理解相關元件和抓出跨檔關聯性的機率。

**Step B2 - 在同一則訊息中「一次」派出所有的代理人**

這點要呼叫工具時才會發生。請在「同一則」回話中，直接多次發出 Agent tool 呼叫 ─ 一個區塊用一個呼叫。這是唯一能讓系統平行驅動的方法。如果你採取了「呼叫一個 Agent、等他跑完、再呼叫下一個」的邏輯，你就是在序列化執行，完全失去了這個機制的意義。

3 個區塊時的實際運作範例：
```
[Agent 工具呼叫 1: 檔案清單 1-15]
[Agent 工具呼叫 2: 檔案清單 16-30]  
[Agent 工具呼叫 3: 檔案清單 31-45]
```
必須在「唯一的一則訊息」裡發送，而不是發三次工具交替對話。

每一位子代理人都會拿到以下這份完全一模一樣的提示詞（請為每一個 chunk 替換掉其中的 FILE_LIST、CHUNK_NUM、TOTAL_CHUNKS 以及 DEEP_MODE 變數）：

```
你是一個 graphify 的擷取代理人。請閱讀條列的檔案清單，並從中擷取知識圖譜的片段。
「只准」輸出符合下列 Schema 的合法 JSON 格式文字 - 禁止任何多餘解釋、不准有 markdown 格式碼、不准有任何開場白。

檔案 (第 CHUNK_NUM 個切塊，共 TOTAL_CHUNKS 個):
FILE_LIST

規則:
- EXTRACTED (直接擷取): 在原文內有直接明示的關連 (例如 import, 具名呼叫, 引文, "參見 §3.2")
- INFERRED (邏輯推演): 合理的推斷 (共用的資料結構、隱含有相依性)
- AMBIGUOUS (模糊不清): 充滿不確定性 - 標記下來供人類人工審閱，絕對不准默默忽略

針對程式碼檔案: 將焦點放在 AST 找不到的語意層連結 (像是呼叫關係、共享基礎資料、架構設計模式)。
  不准重複擷取 import - AST 早就幫你做好了。
針對文件與論文檔案: 擷取具名概念、個體、參考論文。並且要去抓取「設計原由」(rationale) — 特別是那些在解釋「為什麼要做這個決定」、「為什麼選這個折衷方案」或「設計意圖」的段落。請把它們存成特定節點，並用 `rationale_for` 連向它所解釋的母體概念。
針對圖片檔案: 使用視覺能力來理解該圖片的本質「是什麼」 - 絕對不是叫你想辦法做 OCR 光學字元辨識。
  UI 應用程式截圖: 版面切割模式、設計決策、關鍵元件、目的。
  圖表 (Chart): 關鍵評估指標 (metric)、趨勢/洞察、資料來源。
  推文/社群貼文: 把主張 (claim) 當成一個節點，也擷取作者和提到的概念。
  架構圖 (Diagram): 系統元件與連線。
  研究論文圖解: 它示範了什麼、方法、結果。
  手寫/白板照片: 點子與箭頭，如果不確定它到底寫什麼請標記為 AMBIGUOUS。

DEEP_MODE (如果呼叫命令有帶 --mode deep 參數): 在做 INFERRED 關連判斷時「越激進越好」 - 主動尋找間接依賴、共享基礎假設、潛在的耦合。遇到不確定的東西請標記為 AMBIGUOUS，而不是當作沒看見略過。

語意近似度 (Semantic similarity): 如果在這個 chunk 的檔案中有兩個概念是在解決相同的問題、或代表相同的觀念，就算它們沒有實質的實體連線 (沒有 import, 沒有呼叫, 沒引文)，也請為他們加入 `semantically_similar_to` 的關連邊，並註記為 INFERRED，然後附上能反映近似度大小的 confidence_score (0.6-0.95 之間)。範例：
- 兩支同樣都在做輸入檢驗、但彼此從未呼叫過對方的函數
- 程式碼裡實作的某個類別，以及在論文裡對同一個演算法的描述概念
- 兩個都在處理相似的系統失效問題，但採取作法不同的自訂錯誤分類
請小心：只有當這兩者的相似性非常獨特、無可取代且具備跨檔交集時才准加入。千萬不准為泛用事物那種微不足道的表面文字相似度加入。

超連線 (Hyperedges): 如果有三個或以上的節點，非常明確是一起組成同一個概念、工作流、或設計模式時（光靠兩兩相連的單一純邊線無法清楚表達的巨觀場景），就把這群清單加到最上層的 `hyperedges` 陣列裡。範例：
- 實作同一個共通協定或介面的所有分類
- 整個身份驗證 (auth flow) 流程裡面牽扯到的所有函數群 (即便他們無法互相呼叫)
- 論文同一段落裡所形成的一個共通連貫思維群聚
請謹慎使用：只有當群體關係能帶給圖譜「多出兩兩連線以外的意義」才用。每個 chunk 最高上限只准產生 3 組 hyperedges。

如果有檔案包含了 YAML frontmatter（--- ... --- 區塊），請把 source_url, captured_at, author, contributor 的資訊「直接複製填寫到從該檔案擷取出來的每一個節點」。

confidence_score (信心分數配重值) 在「每一條邏輯邊 (Edge)」都強制必填 - 嚴禁省略，也不准通通塞 0.5 應付了事：
- EXTRACTED: 信心分數統一就是 1.0，沒別的。
- INFERRED: 請對每一條線進行分別的主觀推敲。
  如果是直接的結構證據（共用資料規格或明確依賴）: 給 0.8-0.9。
  合理但帶有一定不確定性的推論: 給 0.6-0.7。
  稍顯薄弱或充滿猜測性: 給 0.4-0.5。大部分都會落在 0.6-0.9，絕不能使用 0.5 當作不想思考的隨機預設值。
- AMBIGUOUS: 給 0.1-0.3。

「只准」輸出像下面這樣的確切 JSON 格式 (嚴禁夾帶其他任何說明文字)：
{"nodes":[{"id":"filestem_entityname","label":"Human Readable Name","file_type":"code|document|paper|image","source_file":"relative/path","source_location":null,"source_url":null,"captured_at":null,"author":null,"contributor":null}],"edges":[{"source":"node_id","target":"node_id","relation":"calls|implements|references|cites|conceptually_related_to|shares_data_with|semantically_similar_to|rationale_for","confidence":"EXTRACTED|INFERRED|AMBIGUOUS","confidence_score":1.0,"source_file":"relative/path","source_location":null,"weight":1.0}],"hyperedges":[{"id":"snake_case_id","label":"Human Readable Label","nodes":["node_id1","node_id2","node_id3"],"relation":"participate_in|implement|form","confidence":"EXTRACTED|INFERRED","confidence_score":0.75,"source_file":"relative/path"}],"input_tokens":0,"output_tokens":0}
```

**Step B3 - 收集、快取並合併 (Collect, cache, and merge)**

等待所有的子代理人跑完。對於收到的每一個回饋：
- 若代理人回傳了帶有 `nodes` 與 `edges` 的合法 JSON，就接納它並將其成果存入快取系統
- 若代理人出錯或是回以無效 JSON，請列印警告並跳過該 chunk - 但切勿全面中斷

不過如果發現有超過半數以上的 chunks 都發生了錯誤，則停止並知會使用者。

將新結果存入快取：
```bash
$(cat graphify-out/.graphify_python) -c "
import json
from graphify.cache import save_semantic_cache
from pathlib import Path

new = json.loads(Path('graphify-out/.graphify_semantic_new.json').read_text()) if Path('graphify-out/.graphify_semantic_new.json').exists() else {'nodes':[],'edges':[],'hyperedges':[]}
saved = save_semantic_cache(new.get('nodes', []), new.get('edges', []), new.get('hyperedges', []))
print(f'Cached {saved} files')
"
```

合併快取與全新擷取的成果，並存入 `graphify-out/.graphify_semantic.json`：
```bash
$(cat graphify-out/.graphify_python) -c "
import json
from pathlib import Path

cached = json.loads(Path('graphify-out/.graphify_cached.json').read_text()) if Path('graphify-out/.graphify_cached.json').exists() else {'nodes':[],'edges':[],'hyperedges':[]}
new = json.loads(Path('graphify-out/.graphify_semantic_new.json').read_text()) if Path('graphify-out/.graphify_semantic_new.json').exists() else {'nodes':[],'edges':[],'hyperedges':[]}

all_nodes = cached['nodes'] + new.get('nodes', [])
all_edges = cached['edges'] + new.get('edges', [])
all_hyperedges = cached.get('hyperedges', []) + new.get('hyperedges', [])
seen = set()
deduped = []
for n in all_nodes:
    if n['id'] not in seen:
        seen.add(n['id'])
        deduped.append(n)

merged = {
    'nodes': deduped,
    'edges': all_edges,
    'hyperedges': all_hyperedges,
    'input_tokens': new.get('input_tokens', 0),
    'output_tokens': new.get('output_tokens', 0),
}
Path('graphify-out/.graphify_semantic.json').write_text(json.dumps(merged, indent=2))
print(f'Extraction complete - {len(deduped)} nodes, {len(all_edges)} edges ({len(cached[\"nodes\"])} from cache, {len(new.get(\"nodes\",[]))} new)')
"
```
清理暫存資料夾檔案：

**Bash:** `rm -f graphify-out/.graphify_cached.json graphify-out/.graphify_uncached.txt graphify-out/.graphify_semantic_new.json`

**PowerShell:** `Remove-Item -Force -ErrorAction SilentlyContinue graphify-out/.graphify_cached.json, graphify-out/.graphify_uncached.txt, graphify-out/.graphify_semantic_new.json`

#### Part C - 將 AST 與語意提取結果整併為最後版本

```bash
$(cat graphify-out/.graphify_python) -c "
import sys, json
from pathlib import Path

ast = json.loads(Path('graphify-out/.graphify_ast.json').read_text())
sem = json.loads(Path('graphify-out/.graphify_semantic.json').read_text())

# Merge: AST nodes first, semantic nodes deduplicated by id
seen = {n['id'] for n in ast['nodes']}
merged_nodes = list(ast['nodes'])
for n in sem['nodes']:
    if n['id'] not in seen:
        merged_nodes.append(n)
        seen.add(n['id'])

merged_edges = ast['edges'] + sem['edges']
merged_hyperedges = sem.get('hyperedges', [])
merged = {
    'nodes': merged_nodes,
    'edges': merged_edges,
    'hyperedges': merged_hyperedges,
    'input_tokens': sem.get('input_tokens', 0),
    'output_tokens': sem.get('output_tokens', 0),
}
Path('graphify-out/.graphify_extract.json').write_text(json.dumps(merged, indent=2))
total = len(merged_nodes)
edges = len(merged_edges)
print(f'Merged: {total} nodes, {edges} edges ({len(ast[\"nodes\"])} AST + {len(sem[\"nodes\"])} semantic)')
"
```

### Step 4 - 建立圖譜、分群、分析與產生輸出檔案 (Build graph, cluster, analyze, generate outputs)

```bash
mkdir -p graphify-out
$(cat graphify-out/.graphify_python) -c "
import sys, json
from graphify.build import build_from_json
from graphify.cluster import cluster, score_all
from graphify.analyze import god_nodes, surprising_connections, suggest_questions
from graphify.report import generate
from graphify.export import to_json
from pathlib import Path

extraction = json.loads(Path('graphify-out/.graphify_extract.json').read_text())
detection  = json.loads(Path('graphify-out/.graphify_detect.json').read_text())

G = build_from_json(extraction)
communities = cluster(G)
cohesion = score_all(G, communities)
tokens = {'input': extraction.get('input_tokens', 0), 'output': extraction.get('output_tokens', 0)}
gods = god_nodes(G)
surprises = surprising_connections(G, communities)
labels = {cid: 'Community ' + str(cid) for cid in communities}
# Placeholder questions - regenerated with real labels in Step 5
questions = suggest_questions(G, communities, labels)

report = generate(G, communities, cohesion, labels, gods, surprises, detection, tokens, 'INPUT_PATH', suggested_questions=questions)
Path('graphify-out/GRAPH_REPORT.md').write_text(report)
to_json(G, communities, 'graphify-out/graph.json')

analysis = {
    'communities': {str(k): v for k, v in communities.items()},
    'cohesion': {str(k): v for k, v in cohesion.items()},
    'gods': gods,
    'surprises': surprises,
    'questions': questions,
}
Path('graphify-out/.graphify_analysis.json').write_text(json.dumps(analysis, indent=2))
if G.number_of_nodes() == 0:
    print('ERROR: Graph is empty - extraction produced no nodes.')
    print('Possible causes: all files were skipped, binary-only corpus, or extraction failed.')
    raise SystemExit(1)
print(f'Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges, {len(communities)} communities')
"
```

如果此步驟的執行結果印出了 `ERROR: Graph is empty`，請立刻中止並直接告訴使用者發生了什麼事 - 千萬不要繼續硬跑接下來的命名與視覺化步驟。

將 INPUT_PATH 替換為實際的絕對路徑。

### Step 5 - 為社群標記命名 (Label communities)

讀取 `graphify-out/.graphify_analysis.json`。針對當中的每一個社群鍵值 (community key)，請查閱其底下的所有節點名稱 (node labels)，並幫它用 2-5 個字的簡易白話文想一個適合的名字 (例如："Attention Mechanism", "Training Pipeline", "Data Loading")。

接著，帶入這個名字來重新產生報告，並且為了視覺化圖表將這組標籤對應存入：

```bash
$(cat graphify-out/.graphify_python) -c "
import sys, json
from graphify.build import build_from_json
from graphify.cluster import score_all
from graphify.analyze import god_nodes, surprising_connections, suggest_questions
from graphify.report import generate
from pathlib import Path

extraction = json.loads(Path('graphify-out/.graphify_extract.json').read_text())
detection  = json.loads(Path('graphify-out/.graphify_detect.json').read_text())
analysis   = json.loads(Path('graphify-out/.graphify_analysis.json').read_text())

G = build_from_json(extraction)
communities = {int(k): v for k, v in analysis['communities'].items()}
cohesion = {int(k): v for k, v in analysis['cohesion'].items()}
tokens = {'input': extraction.get('input_tokens', 0), 'output': extraction.get('output_tokens', 0)}

# LABELS - replace these with the names you chose above
labels = LABELS_DICT

# Regenerate questions with real community labels (labels affect question phrasing)
questions = suggest_questions(G, communities, labels)

report = generate(G, communities, cohesion, labels, analysis['gods'], analysis['surprises'], detection, tokens, 'INPUT_PATH', suggested_questions=questions)
Path('graphify-out/GRAPH_REPORT.md').write_text(report)
Path('graphify-out/.graphify_labels.json').write_text(json.dumps({str(k): v for k, v in labels.items()}))
print('Report updated with community labels')
"
```

請將上方指令段落的 `LABELS_DICT` 替換為你實際整理出來成對的字典表 (例如 `{0: "Attention Mechanism", 1: "Training Pipeline"}`)。
並將 INPUT_PATH 替換為實際的路徑。

### Step 6 - 產出 Obsidian 筆記庫 (僅限主動要求) + HTML 互動圖

**在任何情況下都要產出 HTML** (除非被指定 `--no-viz`)。**至於 Obsidian 筆記庫只有在明確帶有 `--obsidian` 參數的情況下才能產生** — 否則必須略過，因為這個動作會為每個系統節點都產生一個純文字檔案。

如果命令中確實有 `--obsidian`：

- 如果這之中還有附帶 `--obsidian-dir <路徑>` 參數，就使用該路徑做為你要輸出筆記庫的目錄。否則預設輸出到 `graphify-out/obsidian` 裡。

```bash
$(cat graphify-out/.graphify_python) -c "
import sys, json
from graphify.build import build_from_json
from graphify.export import to_obsidian, to_canvas
from pathlib import Path

extraction = json.loads(Path('graphify-out/.graphify_extract.json').read_text())
analysis   = json.loads(Path('graphify-out/.graphify_analysis.json').read_text())
labels_raw = json.loads(Path('graphify-out/.graphify_labels.json').read_text()) if Path('graphify-out/.graphify_labels.json').exists() else {}

G = build_from_json(extraction)
communities = {int(k): v for k, v in analysis['communities'].items()}
cohesion = {int(k): v for k, v in analysis['cohesion'].items()}
labels = {int(k): v for k, v in labels_raw.items()}

obsidian_dir = 'OBSIDIAN_DIR'  # replace with --obsidian-dir value, or 'graphify-out/obsidian' if not given

n = to_obsidian(G, communities, obsidian_dir, community_labels=labels or None, cohesion=cohesion)
print(f'Obsidian vault: {n} notes in {obsidian_dir}/')

to_canvas(G, communities, f'{obsidian_dir}/graph.canvas', community_labels=labels or None)
print(f'Canvas: {obsidian_dir}/graph.canvas - open in Obsidian for structured community layout')
print()
print(f'Open {obsidian_dir}/ as a vault in Obsidian.')
print('  Graph view   - nodes colored by community (set automatically)')
print('  graph.canvas - structured layout with communities as groups')
print('  _COMMUNITY_* - overview notes with cohesion scores and dataview queries')
"
```

產生 HTML 圖表（一律執行，除非被指定了 `--no-viz`）：

```bash
$(cat graphify-out/.graphify_python) -c "
import sys, json
from graphify.build import build_from_json
from graphify.export import to_html
from pathlib import Path

extraction = json.loads(Path('graphify-out/.graphify_extract.json').read_text())
analysis   = json.loads(Path('graphify-out/.graphify_analysis.json').read_text())
labels_raw = json.loads(Path('graphify-out/.graphify_labels.json').read_text()) if Path('graphify-out/.graphify_labels.json').exists() else {}

G = build_from_json(extraction)
communities = {int(k): v for k, v in analysis['communities'].items()}
labels = {int(k): v for k, v in labels_raw.items()}

if G.number_of_nodes() > 5000:
    print(f'Graph has {G.number_of_nodes()} nodes - too large for HTML viz. Use Obsidian vault instead.')
else:
    to_html(G, communities, 'graphify-out/graph.html', community_labels=labels or None)
    print('graph.html written - open in any browser, no server needed')
"
```

### Step 7 - 匯出 Neo4j (只有當指定 --neo4j 或 --neo4j-push 時才執行)

**如果是 `--neo4j`** - 產生供手動匯入的 Cypher 檔：

```bash
$(cat graphify-out/.graphify_python) -c "
import sys, json
from graphify.build import build_from_json
from graphify.export import to_cypher
from pathlib import Path

G = build_from_json(json.loads(Path('graphify-out/.graphify_extract.json').read_text()))
to_cypher(G, 'graphify-out/cypher.txt')
print('cypher.txt written - import with: cypher-shell < graphify-out/cypher.txt')
"
```

**如果是 `--neo4j-push <uri>`** - 直接把資料推送到執行中的 Neo4j 伺服器。如果指令沒提供帳密，請回頭詢問使用者：

```bash
$(cat graphify-out/.graphify_python) -c "
import sys, json
from graphify.build import build_from_json
from graphify.cluster import cluster
from graphify.export import push_to_neo4j
from pathlib import Path

extraction = json.loads(Path('graphify-out/.graphify_extract.json').read_text())
analysis   = json.loads(Path('graphify-out/.graphify_analysis.json').read_text())
G = build_from_json(extraction)
communities = {int(k): v for k, v in analysis['communities'].items()}

result = push_to_neo4j(G, uri='NEO4J_URI', user='NEO4J_USER', password='NEO4J_PASSWORD', communities=communities)
print(f'Pushed to Neo4j: {result[\"nodes\"]} nodes, {result[\"edges\"]} edges')
"
```

請將 `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` 替換為實際對應的值。預設連結為 `bolt://localhost:7687`，預設帳號為 `neo4j`。因為底層使用 MERGE 語法建構 - 所以可以安全地重複執行推播，不會灌出重複無效資料。

### Step 7b - 匯出 SVG (只有當指令指定 --svg 參數時)

```bash
$(cat graphify-out/.graphify_python) -c "
import sys, json
from graphify.build import build_from_json
from graphify.export import to_svg
from pathlib import Path

extraction = json.loads(Path('graphify-out/.graphify_extract.json').read_text())
analysis   = json.loads(Path('graphify-out/.graphify_analysis.json').read_text())
labels_raw = json.loads(Path('graphify-out/.graphify_labels.json').read_text()) if Path('graphify-out/.graphify_labels.json').exists() else {}

G = build_from_json(extraction)
communities = {int(k): v for k, v in analysis['communities'].items()}
labels = {int(k): v for k, v in labels_raw.items()}

to_svg(G, communities, 'graphify-out/graph.svg', community_labels=labels or None)
print('graph.svg written - embeds in Obsidian, Notion, GitHub READMEs')
"
```

### Step 7c - 匯出 GraphML (只有當指令指定 --graphml 參數時)

```bash
$(cat graphify-out/.graphify_python) -c "
import json
from graphify.build import build_from_json
from graphify.export import to_graphml
from pathlib import Path

extraction = json.loads(Path('graphify-out/.graphify_extract.json').read_text())
analysis   = json.loads(Path('graphify-out/.graphify_analysis.json').read_text())

G = build_from_json(extraction)
communities = {int(k): v for k, v in analysis['communities'].items()}

to_graphml(G, communities, 'graphify-out/graph.graphml')
print('graph.graphml written - open in Gephi, yEd, or any GraphML tool')
"
```

### Step 7d - 啟動 MCP 伺服器介面 (只有當指令指定 --mcp 參數時)

```bash
python3 -m graphify.serve graphify-out/graph.json
```

這將會啟動一個基於 stdio 發動的 MCP 伺服器，並對外曝露涵蓋這些工具：`query_graph`, `get_node`, `get_neighbors`, `get_community`, `god_nodes`, `graph_stats`, `shortest_path`。將此通訊加入到 Claude Desktop 或任何相容 MCP 的代理人編排器 (orchestrator) 裡，就能讓其他代理人夥伴也能即時自由提問查詢這張圖譜。

如果要將其設定連動到 Claude Desktop，請把它加到 `claude_desktop_config.json` 裡面去：
```json
{
  "mcpServers": {
    "graphify": {
      "command": "python3",
      "args": ["-m", "graphify.serve", "/absolute/path/to/graphify-out/graph.json"]
    }
  }
}
```

### Step 8 - 減少 Token 的基準測試 (只有當 total_words > 5000 時)

如果 `graphify-out/.graphify_detect.json` 裡的 `total_words` 超過 5,000，請執行跑分：

```bash
$(cat graphify-out/.graphify_python) -c "
import json
from graphify.benchmark import run_benchmark, print_benchmark
from pathlib import Path

detection = json.loads(Path('graphify-out/.graphify_detect.json').read_text())
result = run_benchmark('graphify-out/graph.json', corpus_words=detection['total_words'])
print_benchmark(result)
"
```

直接將結果印在對視窗上。如果 `total_words <= 5000`，則默默跳過不跑 - 因為對於偏向小型的分析語料庫來說，圖譜的價值在於釐清結構關聯而不在於壓縮 Token 上報數量。

---

### Step 9 - 儲存紀錄檔清單、更新成本追蹤器、清理暫存環境，並輸出最後總結報告

```bash
$(cat graphify-out/.graphify_python) -c "
import json
from pathlib import Path
from datetime import datetime, timezone
from graphify.detect import save_manifest

# Save manifest for --update
detect = json.loads(Path('graphify-out/.graphify_detect.json').read_text())
save_manifest(detect['files'])

# Update cumulative cost tracker
extract = json.loads(Path('graphify-out/.graphify_extract.json').read_text())
input_tok = extract.get('input_tokens', 0)
output_tok = extract.get('output_tokens', 0)

cost_path = Path('graphify-out/cost.json')
if cost_path.exists():
    cost = json.loads(cost_path.read_text())
else:
    cost = {'runs': [], 'total_input_tokens': 0, 'total_output_tokens': 0}

cost['runs'].append({
    'date': datetime.now(timezone.utc).isoformat(),
    'input_tokens': input_tok,
    'output_tokens': output_tok,
    'files': detect.get('total_files', 0),
})
cost['total_input_tokens'] += input_tok
cost['total_output_tokens'] += output_tok
cost_path.write_text(json.dumps(cost, indent=2))

print(f'This run: {input_tok:,} input tokens, {output_tok:,} output tokens')
print(f'All time: {cost[\"total_input_tokens\"]:,} input, {cost[\"total_output_tokens\"]:,} output ({len(cost[\"runs\"])} runs)')
"

# Bash (Linux / macOS / WSL):
# rm -f graphify-out/.graphify_detect.json graphify-out/.graphify_extract.json graphify-out/.graphify_ast.json graphify-out/.graphify_semantic.json graphify-out/.graphify_analysis.json graphify-out/.graphify_labels.json
# rm -f graphify-out/.needs_update 2>/dev/null || true

# PowerShell (Windows):
# $files = @('graphify-out/.graphify_detect.json','graphify-out/.graphify_extract.json','graphify-out/.graphify_ast.json','graphify-out/.graphify_semantic.json','graphify-out/.graphify_analysis.json','graphify-out/.graphify_labels.json','graphify-out/.needs_update')
# Remove-Item -Force -ErrorAction SilentlyContinue $files
```

向使用者回報結果 (除非指令有要求 --obsidian 否則這一段請主動省略關於 obsidian 的那一行回報):
```
圖譜建立完畢。所有產出物皆存放於 PATH_TO_DIR/graphify-out/

  graph.html            - 互動式關聯圖譜，請直接用瀏覽器開啟此檔
  GRAPH_REPORT.md       - 稽核報告
  graph.json            - 圖譜所產生的原始結構資料
  obsidian/             - Obsidian 筆記庫 (僅當參數明確包含 --obsidian 時才會有這資料夾)
```

把 PATH_TO_DIR 替換為剛才被處理目錄的實際絕對路徑。

然後「直接把」剛剛 GRAPH_REPORT.md 這份報告當中的以下三個特定段落文字貼進聊天視窗裡給使用者看：
- 上帝節點 (God Nodes)
- 令人驚奇的關連 (Surprising Connections)
- 推薦深入詢問的問題清單 (Suggested Questions)

絕對不要把整份落落長的報告貼出來 - 貼這三個精華段落就好，請保持簡潔明瞭。

接著，請馬上主動提議要不要深入探索。從報告裡的推薦問題清單中，挑出「最有趣的一個」 - 這個問題通常是橫跨了最多不同社群邊界、或是含有某些最出乎意料的橋樑節點 - 然後主動問使用者：

> "這張圖譜能解答的最有趣的問題應該是：**[填寫這個挑中的問題]**。需要我幫忙追蹤這問題的結構關連嗎？"

如果使用者點頭答應了，就在該圖譜上執行 `/graphify query "[該問題]"`，然後順著圖譜的結構逐步引導使用者理解答案 - 告訴使用者哪些節點連在一起、跨越了哪些知識社群聚落邊境、這條追蹤路徑反映出了什麼道理。只要使用者興致勃勃想探索就繼續引導下去。每一次對話回答都應該在結尾留個自然的後續跟進點（例如："這答案同時還連接到了 X - 你會想繼續深入了解嗎？"），如此一來，這場對話過程就會像是一趟導覽探索活動，而不是一次性甩出死板長篇報告讓它長灰塵。

圖譜本體只是張死板的地圖。而整個管線執行完畢後，你的偉大任務，就是完美扮演那位王牌導覽響導。

---

## 提供給各式附屬子指令的執行環境守衛護城河 (Interpreter guard)

在執行下列任何子指令前（`--update`, `--cluster-only`, `query`, `path`, `explain`, `add`），必須先檢查根目錄 `.graphify_python` 這隻檔案是否還健在。如果它已經遺失不見了（例如使用者不小心刪掉了 `graphify-out/` 資料夾），請優先重新解析環境並產出對應的 Python 直譯器路徑，免得後續罷工死當：

**Bash (Linux / macOS / WSL):**
```bash
if [ ! -f graphify-out/.graphify_python ]; then
    GRAPHIFY_BIN=$(which graphify 2>/dev/null)
    if [ -n "$GRAPHIFY_BIN" ]; then
        PYTHON=$(head -1 "$GRAPHIFY_BIN" | tr -d '#!')
        case "$PYTHON" in *[!a-zA-Z0-9/_.-]*) PYTHON="python3" ;; esac
    else
        PYTHON="python3"
    fi
    mkdir -p graphify-out
    "$PYTHON" -c "import sys; open('graphify-out/.graphify_python', 'w').write(sys.executable)"
fi
```

**PowerShell (Windows):**
```powershell
if (-not (Test-Path "graphify-out/.graphify_python")) {
    New-Item -ItemType Directory -Force -Path graphify-out | Out-Null
    python -c "import sys; open('graphify-out/.graphify_python', 'w').write(sys.executable)"
}
```

## 用於支援 --update (漸進式局部重新提取)

當你自上一次跑完之後，只有新增或修改過少部分檔案時可用。它只會針對「有變更過」的實體檔案重新提取 - 將大大節省花費 Token 與分析時間。

```bash
$(cat graphify-out/.graphify_python) -c "
import sys, json
from graphify.detect import detect_incremental, save_manifest
from pathlib import Path

result = detect_incremental(Path('INPUT_PATH'))
new_total = result.get('new_total', 0)
print(json.dumps(result, indent=2))
Path('graphify-out/.graphify_incremental.json').write_text(json.dumps(result))
if new_total == 0:
    print('No files changed since last run. Nothing to update.')
    raise SystemExit(0)
print(f'{new_total} new/changed file(s) to re-extract.')
"
```

如果確實有變動的新檔案存在，請優先檢查是否「有所變更的檔案都只是純粹的程式碼 Code」：

```bash
$(cat graphify-out/.graphify_python) -c "
import json
from pathlib import Path

result = json.loads(open('graphify-out/.graphify_incremental.json').read()) if Path('graphify-out/.graphify_incremental.json').exists() else {}
code_exts = {'.py','.ts','.js','.go','.rs','.java','.cpp','.c','.rb','.swift','.kt','.cs','.scala','.php','.cc','.cxx','.hpp','.h','.kts','.lua','.toc'}
new_files = result.get('new_files', {})
all_changed = [f for files in new_files.values() for f in files]
code_only = all(Path(f).suffix.lower() in code_exts for f in all_changed)
print('code_only:', code_only)
"
```

如果 `code_only` 為 True: 印出 `[graphify update] Code-only changes detected - skipping semantic extraction (no LLM needed)`，然後只針對有變更的檔案執行 Step 3A (AST)，完全跳過整個 Step 3B (不用派任何抓取子代理人)，接著直接前往合併資料並續走 Steps 4–8。

如果 `code_only` 為 False (只要其中有任何一個被改變的檔案是 doc/paper/image): 那就乖乖照常走完完整的 Steps 3A–3C 分析管線。

接著：

```bash
$(cat graphify-out/.graphify_python) -c "
import sys, json
from graphify.build import build_from_json
from graphify.export import to_json
from networkx.readwrite import json_graph
import networkx as nx
from pathlib import Path

# Load existing graph
existing_data = json.loads(Path('graphify-out/graph.json').read_text())
G_existing = json_graph.node_link_graph(existing_data, edges='links')

# Load new extraction
new_extraction = json.loads(Path('graphify-out/.graphify_extract.json').read_text())
G_new = build_from_json(new_extraction)

# Prune nodes from deleted files
incremental = json.loads(Path('graphify-out/.graphify_incremental.json').read_text())
deleted = set(incremental.get('deleted_files', []))
if deleted:
    to_remove = [n for n, d in G_existing.nodes(data=True) if d.get('source_file') in deleted]
    G_existing.remove_nodes_from(to_remove)
    print(f'Pruned {len(to_remove)} ghost nodes from {len(deleted)} deleted file(s)')

# Merge: new nodes/edges into existing graph
G_existing.update(G_new)
print(f'Merged: {G_existing.number_of_nodes()} nodes, {G_existing.number_of_edges()} edges')
" 
```

然後，針對這份經過合併的新版大圖譜，如常繼續執行後面的 Steps 4–8。

在跑完 Step 4 時，請列印展示出新舊圖譜之間的差異比對成果：

```bash
$(cat graphify-out/.graphify_python) -c "
import json
from graphify.analyze import graph_diff
from graphify.build import build_from_json
from networkx.readwrite import json_graph
import networkx as nx
from pathlib import Path

# Load old graph (before update) from backup written before merge
old_data = json.loads(Path('graphify-out/.graphify_old.json').read_text()) if Path('graphify-out/.graphify_old.json').exists() else None
new_extract = json.loads(Path('graphify-out/.graphify_extract.json').read_text())
G_new = build_from_json(new_extract)

if old_data:
    G_old = json_graph.node_link_graph(old_data, edges='links')
    diff = graph_diff(G_old, G_new)
    print(diff['summary'])
    if diff['new_nodes']:
        print('New nodes:', ', '.join(n['label'] for n in diff['new_nodes'][:5]))
    if diff['new_edges']:
        print('New edges:', len(diff['new_edges']))
"
```

在進入正式合併步驟之前，優先把目前版本的舊圖譜備份起來：
- **Bash:** `cp graphify-out/graph.json graphify-out/.graphify_old.json`
- **PowerShell:** `Copy-Item graphify-out/graph.json graphify-out/.graphify_old.json`

等上面跑完之後，最後順帶自動清理這些備份垃圾：
- **Bash:** `rm -f graphify-out/.graphify_old.json`
- **PowerShell:** `Remove-Item -Force -ErrorAction SilentlyContinue graphify-out/.graphify_old.json`

---

## 用於 --cluster-only 單純重跑分群機制時

直接跳過所有落落長的 Steps 1–3 結構採集。改為直接從磁碟中讀取現有的 `graphify-out/graph.json` 圖譜進入記憶體，然後重新執行一次分群演算法 (clustering)：

```bash
$(cat graphify-out/.graphify_python) -c "
import sys, json
from graphify.cluster import cluster, score_all
from graphify.analyze import god_nodes, surprising_connections
from graphify.report import generate
from graphify.export import to_json
from networkx.readwrite import json_graph
import networkx as nx
from pathlib import Path

data = json.loads(Path('graphify-out/graph.json').read_text())
G = json_graph.node_link_graph(data, edges='links')

detection = {'total_files': 0, 'total_words': 99999, 'needs_graph': True, 'warning': None,
             'files': {'code': [], 'document': [], 'paper': []}}
tokens = {'input': 0, 'output': 0}

communities = cluster(G)
cohesion = score_all(G, communities)
gods = god_nodes(G)
surprises = surprising_connections(G, communities)
labels = {cid: 'Community ' + str(cid) for cid in communities}

report = generate(G, communities, cohesion, labels, gods, surprises, detection, tokens, '.')
Path('graphify-out/GRAPH_REPORT.md').write_text(report)
to_json(G, communities, 'graphify-out/graph.json')

analysis = {
    'communities': {str(k): v for k, v in communities.items()},
    'cohesion': {str(k): v for k, v in cohesion.items()},
    'gods': gods,
    'surprises': surprises,
}
Path('graphify-out/.graphify_analysis.json').write_text(json.dumps(analysis, indent=2))
print(f'Re-clustered: {len(communities)} communities')
"
```

完成後，接著按照日常一般情況，把後面的 Steps 5–9 跑完 (為社群賦予命名標籤、生圖表示、效能基準衡量、暫存檔案清理、以及產出最新報告)。

---

## 用於 /graphify query 查詢與解答功能

支援擁有兩種截然不同的路徑走訪模式 (traversal modes) - 會隨提出問題性質的不同動態決定：

| 模式 | 參數 | 最佳適用情境說明 |
|------|------|----------|
| BFS 廣度優先 (預設值) | _(無)_ | "這裡的 X 連接著什麼東西？" - 著重於探索宏觀的周遭上下文，會優先往第一層外圍鄰近點推進擴散 |
| DFS 深度優先 | `--dfs` | "請問 X 是如何到達 Y 的？" - 用於順藤摸瓜式追蹤一條具體的依賴長龍或邏輯路徑 |

第一步請先檢查圖譜確定是否真實存在於該目錄：
```bash
$(cat graphify-out/.graphify_python) -c "
from pathlib import Path
if not Path('graphify-out/graph.json').exists():
    print('ERROR: No graph found. Run /graphify <path> first to build the graph.')
    raise SystemExit(1)
"
```
要是上面這檢查擋下了，就中止作動並提醒使用者應該先去找個目錄去跑一遍 `/graphify <路徑>` 建置出基礎大圖譜才行。

載入 `graphify-out/graph.json` 之後，依序進行下述邏輯：

1. 找出最能切中問題中關鍵核心字眼的那 1 乃至 3 個節點作為切入開端。
2. 從這些起點開端，執行你選擇的一種適用的走訪掃描。
3. 把撈到的這圈附近鄰接子圖 (subgraph) 當中的一切資訊全都仔仔細細端出來讀過 - 包含裡面的節點標籤、邊線關連性質、信心分數、甚至是底層引用出處。
4. **「絕對只准」** 用這圖表上目前已經載明的固有客觀事實來回覆問題。如果在回話中有實際引用到特定具體細節時，一定要老老實實標註 `source_location` 以示負責。
5. 萬一發現到圖表目前的內容情報，還真的就是不足以兜出完整答案，就明講 - 絕對不准靠自己的強大腦補能力，無中生有幻覺發明連線。

```bash
$(cat graphify-out/.graphify_python) -c "
import sys, json
from networkx.readwrite import json_graph
import networkx as nx
from pathlib import Path

data = json.loads(Path('graphify-out/graph.json').read_text())
G = json_graph.node_link_graph(data, edges='links')

question = 'QUESTION'
mode = 'MODE'  # 'bfs' or 'dfs'
terms = [t.lower() for t in question.split() if len(t) > 3]

# Find best-matching start nodes
scored = []
for nid, ndata in G.nodes(data=True):
    label = ndata.get('label', '').lower()
    score = sum(1 for t in terms if t in label)
    if score > 0:
        scored.append((score, nid))
scored.sort(reverse=True)
start_nodes = [nid for _, nid in scored[:3]]

if not start_nodes:
    print('No matching nodes found for query terms:', terms)
    sys.exit(0)

subgraph_nodes = set()
subgraph_edges = []

if mode == 'dfs':
    # DFS: follow one path as deep as possible before backtracking.
    # Depth-limited to 6 to avoid traversing the whole graph.
    visited = set()
    stack = [(n, 0) for n in reversed(start_nodes)]
    while stack:
        node, depth = stack.pop()
        if node in visited or depth > 6:
            continue
        visited.add(node)
        subgraph_nodes.add(node)
        for neighbor in G.neighbors(node):
            if neighbor not in visited:
                stack.append((neighbor, depth + 1))
                subgraph_edges.append((node, neighbor))
else:
    # BFS: explore all neighbors layer by layer up to depth 3.
    frontier = set(start_nodes)
    subgraph_nodes = set(start_nodes)
    for _ in range(3):
        next_frontier = set()
        for n in frontier:
            for neighbor in G.neighbors(n):
                if neighbor not in subgraph_nodes:
                    next_frontier.add(neighbor)
                    subgraph_edges.append((n, neighbor))
        subgraph_nodes.update(next_frontier)
        frontier = next_frontier

# Token-budget aware output: rank by relevance, cut at budget (~4 chars/token)
token_budget = BUDGET  # default 2000
char_budget = token_budget * 4

# Score each node by term overlap for ranked output
def relevance(nid):
    label = G.nodes[nid].get('label', '').lower()
    return sum(1 for t in terms if t in label)

ranked_nodes = sorted(subgraph_nodes, key=relevance, reverse=True)

lines = [f'Traversal: {mode.upper()} | Start: {[G.nodes[n].get(\"label\",n) for n in start_nodes]} | {len(subgraph_nodes)} nodes']
for nid in ranked_nodes:
    d = G.nodes[nid]
    lines.append(f'  NODE {d.get(\"label\", nid)} [src={d.get(\"source_file\",\"\")} loc={d.get(\"source_location\",\"\")}]')
for u, v in subgraph_edges:
    if u in subgraph_nodes and v in subgraph_nodes:
        d = G.edges[u, v]
        lines.append(f'  EDGE {G.nodes[u].get(\"label\",u)} --{d.get(\"relation\",\"\")} [{d.get(\"confidence\",\"\")}]--> {G.nodes[v].get(\"label\",v)}')

output = '\n'.join(lines)
if len(output) > char_budget:
    output = output[:char_budget] + f'\n... (truncated at ~{token_budget} token budget - use --budget N for more)'
print(output)
"
```

請把 `QUESTION` 換成使用者實際上提問的問題，`MODE` 換成 `bfs` 或是 `dfs`，然後將 `BUDGET` 換成 Token 預算限制字數 (預設 `2000`，或看 `--budget N` 參數帶多少)。接著老老實實基於子圖輸出結果來回答。

在你順利寫完回答之後，為了能長足改善未來的查詢能力，請把這次對話成果儲存回寫入圖譜中：

```bash
$(cat graphify-out/.graphify_python) -m graphify save-result --question "QUESTION" --answer "ANSWER" --type query --nodes NODE1 NODE2
```

把 `QUESTION` 換為問題，`ANSWER` 換成你方才吐出的完整長文解答，`SOURCE_NODES` 換成你當中所引用的全體節點名稱名單。這個神聖動作將會閉合反饋迴圈：當下一次跑 `--update` 時便會把這次的 Q&A 重新作為節點提取進入大圖中。

---

## 用於 /graphify path

尋找圖譜中任兩個具名概念節點之間的最短連通距離 (shortest path)。

首先一樣先確認圖譜存不存在：
```bash
$(cat graphify-out/.graphify_python) -c "
from pathlib import Path
if not Path('graphify-out/graph.json').exists():
    print('ERROR: No graph found. Run /graphify <path> first to build the graph.')
    raise SystemExit(1)
"
```
萬一檢查失敗，請停止動作並告知使用者先去跑一次 `/graphify <路徑>` 來建置最初圖譜。

```bash
$(cat graphify-out/.graphify_python) -c "
import json, sys
import networkx as nx
from networkx.readwrite import json_graph
from pathlib import Path

data = json.loads(Path('graphify-out/graph.json').read_text())
G = json_graph.node_link_graph(data, edges='links')

a_term = 'NODE_A'
b_term = 'NODE_B'

def find_node(term):
    term = term.lower()
    scored = sorted(
        [(sum(1 for w in term.split() if w in G.nodes[n].get('label','').lower()), n)
         for n in G.nodes()],
        reverse=True
    )
    return scored[0][1] if scored and scored[0][0] > 0 else None

src = find_node(a_term)
tgt = find_node(b_term)

if not src or not tgt:
    print(f'Could not find nodes matching: {a_term!r} or {b_term!r}')
    sys.exit(0)

try:
    path = nx.shortest_path(G, src, tgt)
    print(f'Shortest path ({len(path)-1} hops):')
    for i, nid in enumerate(path):
        label = G.nodes[nid].get('label', nid)
        if i < len(path) - 1:
            edge = G.edges[nid, path[i+1]]
            rel = edge.get('relation', '')
            conf = edge.get('confidence', '')
            print(f'  {label} --{rel}--> [{conf}]')
        else:
            print(f'  {label}')
except nx.NetworkXNoPath:
    print(f'No path found between {a_term!r} and {b_term!r}')
except nx.NodeNotFound as e:
    print(f'Node not found: {e}')
"
```

將 `NODE_A` 與 `NODE_B` 替換為使用者提問的實際概念名稱。接著請用白話文解釋一路上經過的路徑 - 每一跳 (hop) 代表什麼意思、為何跨越它們具有特定意義。

寫完這份說明之後，一樣儲存回寫：

```bash
$(cat graphify-out/.graphify_python) -m graphify save-result --question "Path from NODE_A to NODE_B" --answer "ANSWER" --type path_query --nodes NODE_A NODE_B
```

---

## 用於 /graphify explain

以白話直述解譯「單一一個特定節點」 - 以及任何所有和它相連的人事物脈絡。

第一步先去檢查確認圖譜存在：
```bash
$(cat graphify-out/.graphify_python) -c "
from pathlib import Path
if not Path('graphify-out/graph.json').exists():
    print('ERROR: No graph found. Run /graphify <path> first to build the graph.')
    raise SystemExit(1)
"
```
萬一檢查失敗，中止並要求使用者先去執行一遍 `/graphify <路徑>`。

```bash
$(cat graphify-out/.graphify_python) -c "
import json, sys
import networkx as nx
from networkx.readwrite import json_graph
from pathlib import Path

data = json.loads(Path('graphify-out/graph.json').read_text())
G = json_graph.node_link_graph(data, edges='links')

term = 'NODE_NAME'
term_lower = term.lower()

# Find best matching node
scored = sorted(
    [(sum(1 for w in term_lower.split() if w in G.nodes[n].get('label','').lower()), n)
     for n in G.nodes()],
    reverse=True
)
if not scored or scored[0][0] == 0:
    print(f'No node matching {term!r}')
    sys.exit(0)

nid = scored[0][1]
data_n = G.nodes[nid]
print(f'NODE: {data_n.get(\"label\", nid)}')
print(f'  source: {data_n.get(\"source_file\",\"unknown\")}')
print(f'  type: {data_n.get(\"file_type\",\"unknown\")}')
print(f'  degree: {G.degree(nid)}')
print()
print('CONNECTIONS:')
for neighbor in G.neighbors(nid):
    edge = G.edges[nid, neighbor]
    nlabel = G.nodes[neighbor].get('label', neighbor)
    rel = edge.get('relation', '')
    conf = edge.get('confidence', '')
    src_file = G.nodes[neighbor].get('source_file', '')
    print(f'  --{rel}--> {nlabel} [{conf}] ({src_file})')
"
```

把 `NODE_NAME` 換成你被問到的那個主要名詞概念。然後寫出一段大約 3 到 5 句的簡練說明重點：這個節點本身是做什麼的、它跟周圍牽連了什麼節點、為何那些連線關連性很重要。請善加利用 `source_location` 的資訊來作為引文出處證實。

寫完這一段說明後，把它存回去：

```bash
$(cat graphify-out/.graphify_python) -m graphify save-result --question "Explain NODE_NAME" --answer "ANSWER" --type explain --nodes NODE_NAME
```

---

## 用於 /graphify add

抓取網址爬梳內容文字，將其加入語料庫，跟著一併更新圖譜陣列。

```bash
$(cat graphify-out/.graphify_python) -c "
import sys
from graphify.ingest import ingest
from pathlib import Path

try:
    out = ingest('URL', Path('./raw'), author='AUTHOR', contributor='CONTRIBUTOR')
    print(f'Saved to {out}')
except ValueError as e:
    print(f'error: {e}', file=sys.stderr)
    sys.exit(1)
except RuntimeError as e:
    print(f'error: {e}', file=sys.stderr)
    sys.exit(1)
"
```

將 `URL` 替換為實際提供的外部網址。如果使用者有特別附帶作者，那麼在 `AUTHOR` 替換他的名字，`CONTRIBUTOR` 檔案提供者也一樣屬名照辦。萬一這項指令拋出錯誤並崩潰陣亡，你「務必」得告知使用者到底發生什麼事 - 嚴禁默默忽視當沒看見。只要網頁備份儲存成功了，也「必須由你主動去幫忙往下執行」 一遍 `--update` 管線去重新分析 `./raw` 分類，藉此自動把這個新下載回來的文檔無縫結合成進你那現有的系統圖譜裡。

支援相容的外網 URL 格式種類 (它懂得自動判定)：
- Twitter/X 推文 → 透過 oEmbed 機制無頭抓取，存為 `.md` 並自動附帶推文本文標頭與原作者名
- arXiv 論文集 → 單純切出包含 abstract (論文摘要) 與相關元數據 (metadata) 存為 `.md`
- PDF 文件 → 直接老實整個當二進位下載存成 `.pdf` 檔案
- 圖檔圖片 (.png/.jpg/.webp) → 直接下載，反正 Claude 強大神經網路視覺模型有能力在下次掃描時做圖解分析
- 其他所有的閒雜網頁 → 全數強迫由 html2text 轉化為只剩下重點的 Markdown 檔

---

## 用於自動監聽功能 --watch

啟動一個在默默在背景常駐執行的監聽系統。它會隨時緊盯某個目標資料夾變更狀態，一旦發現底下檔案發生異動就能自動動工幫忙重建更新圖譜。

**Bash (Linux / macOS / WSL):**
```bash
$(cat graphify-out/.graphify_python) -m graphify.watch INPUT_PATH --debounce 3
```

**PowerShell (Windows):**
```powershell
# Run in a new background job, or open a separate terminal and run:
python -m graphify.watch INPUT_PATH --debounce 3
```

將 INPUT_PATH 替換為你想看的實體資料夾位置。其實際反應程度作為取決於是誰異動了：

- **只涉及純粹的程式碼檔案發生變更時 (.py, .ts, .go...等):** 將會在本地即刻光速重算跑一次 AST 單純結構性提取 + 重建架構圖 + 再次社群分群，全程全自動、不需額外浪費半枚 LLM Tokens。`graph.json` 還有 `GRAPH_REPORT.md` 皆會被靜靜地秒速更新。
- **但要是涉及到了非程式碼文件、長篇論文或是新圖檔變更時:** 系統會偷偷寫下一枚 `graphify-out/needs_update` 旗標檔案紀錄，並且會印出訊息提示你「該手動去敲一次 `/graphify --update` 管線了」 (因為這會動用到那昂貴又耗時的 LLM 語意重新提取程序才能搞定)。

防彈跳防暴衝機制 Debounce (預防連擊，預設為 3 秒鐘): 刻意耐心等到連串檔案讀寫變更全部死寂降溫時才真的啟動運作指令，免得你每改存檔一行就觸發十次重算。

隨時壓下 Ctrl+C (或者在 Windows PowerShell 裡無情使用 `Stop-Job`) 便能切斷這隻背後靈程序。

針對時下流行的代理人式開發工作流程 (Agentic workflows) 會變得極具殺傷力：你大可以開另開一個獨立的終端機放在背景然後常駐跑這隻 `--watch` 腳本不要關。這麼做的話，每當那個叫 Agent 的傢伙發神經瘋狂大量寫 Code 製造新程式海波浪的短暫喘息間隙中，監視器系統本身就能精準把這些大量變更的 Code 通通不流鼻血捕捉轉化建檔下來了。當然，要是這個 Agent 大大也在拼命製造新的 Markdown 解說文件或寫了一堆落落長分析紀錄時，不好意思，等他結束亂噴收工後你還是得自己親自手工下一道 `/graphify --update` 去付錢跑結算，畢竟機器人不一定會幫你結帳。

---

## 用於設定 git commit hook 卡榫機制

幫專案原始庫全自動裝好一支 post-commit hook 短腳本，它的功用是能極度強勢綁定並規定只要每次開發者打上了 commit 完成確認鍵結算後，就無條件自動重造一張熱騰騰出爐圖譜一次。好處是這不需要你在背景放著任何駐點背景系統程序耗能 - 它只專職會在每次 Git 下指令落槌過帳結算時被乖乖觸發呼叫幫你叫一次外送，甚至這機制還神到跟你用的是什麼冷門編輯器完全無關，統統適用。

```bash
graphify hook install    # install
graphify hook uninstall  # remove
graphify hook status     # check
```

每一次打上 `git commit` 落槌交件後，躲在背後的這支 hook 便會自己張大眼睛看清楚有哪些程式檔案被改了動過手腳 (其實就是利用偷偷依靠呼叫 `git diff HEAD~1` 來快速判定)，然後把火力極度集中，只挑那些被染指過動刀的倒楣鬼直接抓去通刷局部重跑分析一遍純粹靠 AST 去無腦進行提取重解析作業，並快狠準乖乖為你無腦端出重建完成的最新出爐 `graph.json` 跟 `GRAPH_REPORT.md` 熱炒兩盤。

如果你這隻 Commit 修改的部分中包含了文字解說文件或改到了精美圖片... 那這隻 hook 根本不會鳥你，完全裝瞎 - 開發的大哥大姊，遇到這事請自己當作沒看到自己手動去敲下一道 `/graphify --update` 來啟動付費大腦幫忙重算謝謝。

如果你在打這道指令時，這個專案原本老早就存在有你那寶貝神功護體的長長一串自訂 post-commit hook 現役內容裡面了，別怕別擔心毀掉自己的基底，graphify 沒那麼笨，它足夠聰明且內斂會懂得乖巧選擇低調用 append 添加寫在原來的屁股末端，絕不出手強行幹掉無情強蓋掉你先前的所有紀錄心血。

---

## 綁定提供給原生的 CLAUDE.md 環境深度系統整合

這輩子針對每個你在接手的專案跑過僅此一次就好。打下後將徹底打開天窗說亮話，它能確保發功讓你的 Graphify 管線從此往後在專案本機面臨任何長期的跨日 Claude Code 會話時期，都能達到隨時強制開啟如影隨形、如同無時無刻都有人幫你監視般神乎其技不掉線的奇效：

```bash
graphify claude install
```

下了這東西之後會把大刀闊斧外掛寫入一段專屬且獨步武林的 `## graphify` 原文潛規則強硬塞進去強制存放到隸屬於專案底下的那隻本機 `CLAUDE.md` 神奇檔案內部，這些內容全都是等同於具有極強洗腦跟催眠指導效果的嚴肅守則條款，它會在最根本第一時間指示 Claude 先給我低頭乖乖偷看這包圖庫報告內含的結論然後才可以開口嘴砲回答那些天殺的複雜原始碼專案架構問題、更別提它也順手立下了打雜規則，強制在幫你親手寫完骯髒複雜的架構重整 Code 之後要給我乖乖無痛順手重建它梳理。

只要一旦建立完並打上這道暗黑標記，日後隨之打開而來的任何下半生新建立起的全新 Sessions 都不再需要你勞煩自己的雙手手工敲下半個 `/graphify` 這破指令來啟動喚醒，因為它就已經長大自己無師自通全都懂門路了，你負責享受就好。

```bash
graphify claude uninstall  # remove the section
```

## 提供給屬於大一統生態系的 GEMINI.md 根源性直接系統整合支援

如同上面也是同個道理，整包專案這生跑個一次就好了，狠狠灌下去將一鍵打開任意門強制啟動，讓 graphify 此等神力不再受拘束在命令列，甚至反過頭來在所有 Gemini CLI 掛機聊天的會話過程當中發揮強制開啟全時監控無所事事運行外掛大絕的作弊威能：

```bash
graphify gemini install
```

下了之後系統就會替本機的隱藏角色 `GEMINI.md` 注入整塊大辣辣引人注目的 `## graphify` 規則強制區段來下達封殺條例，它等同於拿刀子架在系統脖子上強制要求 Gemini 在要張開金口瞎扯回答任何有關於「架構」等狗屁倒灶專案原始碼探討問題以前，給我先乖乖去後面房間老實偷偷摸摸翻閱看完過一遍存放於專屬抽屜的 `graphify-out/GRAPH_REPORT.md` 報表神喻結論，照本宣科不要胡說廢話。

另外更實屬窩心之舉也就是還順手設定在它做完了所有幫你寫下大量噁心連串複雜架構 Code 改版的重勞力打雜活後，還懂得好心提醒健忘的你是不是該記得趁當下親爹熱來下道 `--update` 神力魔法指令幫自己跑更新升級大洗牌了呢？

```bash
graphify gemini uninstall  # remove the section
```

---

## 絕對誠實鐵則 (Honesty Rules) 規範矩陣

- 「這荒唐人生最不該許下的無恥作為就是」你自顧自無端憑空創造捏造跟隨意發明那虛構的連線邊界。凡是只要拿不準甚至毫無頭緒把握時，直接硬生生老實掛上那個 AMBIGUOUS (模糊不清) 沒水準牌子也沒關係，沒人會笑你。
- 當你第一眼看到我們設下語料庫上限檢查警報器在那裡盡忠職守滴滴作響攔路發出刺耳警示要求使用者停下來等答時，絕對不准你在背地裡作弊把那道這該死的警告給直接吞掉隱蔽抹煞甚至妄想全數略過。
- 那個偉大到能反映開發者心血勞力價值的花費 Token 清單項目統計結算帳本成本數量資訊數字，一定必須要毫不猶豫的鉅細靡遺呈現清清白白揭諸公開寫入最終報告神喻清單底下讓大家用良心來檢視公判評價。
- 你若打著算盤想偷偷用任何文字藝術小巧思去嘗試刻意遮掩過濾那醜陋見客不忍直視且毫無生氣死水一攤低落的系統聚合總分數表現？勸你別作夢早早死了這條心了，我現在就是在嚴厲規定命令你毫不留情把所有最原始沒經過半滴修飾包裝加工的悲劇血淋淋原真實數字底稿 (cohesion scores) 印得清清楚楚完好無缺出來讓大家用雙眼血淋淋看透到底就對了，誰怕誰。
- 在未曾警告過無辜可憐且隨時可能會誤觸被雷驚嚇到底層使用者大人的前提跟先決情況考量之下，你絕不准給我自作主張暗行瞞騙私自行刑，直接硬生生丟給那可憐的瀏覽器去死板板接一個整體總數直接大肆張狂暴漲飆破高達無情數量 5,000 大關恐怖節點的超級巨無霸怪獸星團大圖陣列，就這樣大辣辣的把這種超級龐然巨魔怪東西給硬推去實施強制暴力執行渲染繪製任何噁心繁複難解沉重吃力拖慢運算的 HTML。敢不先說一聲試試看！
