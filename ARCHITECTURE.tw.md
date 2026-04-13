# 架構

graphify 是一個三層架構：**Skill** (LLM 指令) → **Pipeline** (CLI 封裝層) → **Library** (核心函式)。

- **Skill** (`skill-gemini.md` / `skill-gemini.tw.md`)：給 LLM 讀的操作手冊，定義呼叫順序
- **Pipeline** (`pipeline.py`)：CLI subcommand 層，封裝決策邏輯和暫存檔案管理
- **Library** (`detect.py`, `extract.py`, `build.py`, ...)：純函式，可獨立使用

## Pipeline 層 (`pipeline.py`)

`pipeline.py` 是 skill 與 library 之間的膠合層。透過 `python -m graphify pipeline <subcommand>` 呼叫。

職責：
- 程式化決策邏輯（取代 skill 中的自然語言判斷）
- 結構化 JSON 輸出供 LLM 消費
- 暫存檔案在 `graphify-out/` 的讀寫與生命週期管理
- OS 無關的執行方式（不需要 Bash/PowerShell 分支）

### Subcommands

| Subcommand | 對應函式 | 用途 |
|------------|---------|------|
| `check-install` | `cmd_check_install` | 驗證 graphify 可匯入，建立輸出目錄 |
| `detect <path>` | `cmd_detect` | 偵測檔案，輸出帶決策欄位的 JSON |
| `ast-extract` | `cmd_ast_extract` | 對程式碼檔案執行 AST 結構化提取 |
| `cache-check` | `cmd_cache_check` | 檢查語意提取快取 |
| `prepare-semantic` | `cmd_prepare_semantic` | 將未快取檔案切分 chunk 並產生 prompt 檔案 |
| `merge-semantic` | `cmd_merge_semantic` | 收集 chunk 結果、驗證、快取、合併 |
| `merge-all` | `cmd_merge_all` | 合併 AST + 語意提取結果 |
| `build <path>` | `cmd_build` | 建立圖譜、分群、分析 |
| `label <json>` | `cmd_label` | 套用社群標籤並重新產生報告 |
| `export [flags]` | `cmd_export` | 匯出 HTML/SVG/Obsidian/Neo4j/Wiki |
| `benchmark` | `cmd_benchmark` | Token 壓縮率基準測試 |
| `finalize [path]` | `cmd_finalize` | 儲存 manifest、更新成本追蹤器、清理暫存檔 |
| `update-detect <path>` | `cmd_update_detect` | 偵測自上次執行以來的變更檔案 |
| `update-merge` | `cmd_update_merge` | 將新提取結果合併到既有圖譜 |
| `cluster-only` | `cmd_cluster_only` | 對既有圖譜重新執行分群 |
| `path <A> <B>` | `cmd_path` | 兩個節點之間的最短路徑 |
| `explain <node>` | `cmd_explain` | 以白話文解釋節點 |
| `add <url>` | `cmd_add` | 抓取 URL，存入語料庫 |

## 完整管線資料流

```
detect → ast-extract ─────────────────────────────┐
     └→ cache-check → prepare-semantic → [LLM dispatch] → merge-semantic ─┤
                                                                          ↓
                                                                     merge-all
                                                                          ↓
                                                          build → label → export → benchmark → finalize
```

## 增量更新 (--update) 資料流

```
update-detect
    ↓  寫入 .graphify_detect.json（僅新檔案）+ .graphify_incremental.json（完整結果）
ast-extract / cache-check / prepare-semantic / merge-semantic / merge-all
    ↓  提取步驟只處理變更的檔案
update-merge
    ↓  合併新提取 + 既有圖譜，還原 .graphify_extract.json 和 .graphify_detect.json 為完整資料
build → label → export → benchmark → finalize
```

設計模式：**縮小範圍 → 提取 → 還原範圍**。`update-detect` 將 `.graphify_detect.json` 限縮為新檔案，讓中段提取步驟自然只處理變更的部分；`update-merge` 在合併完成後還原完整資料，確保後段步驟拿到正確的全量。

## 暫存檔案 (`graphify-out/.graphify_*`)

管線各步驟透過 `graphify-out/` 下的暫存檔案傳遞資料：

| 檔案 | 寫入者 | 讀取者 | 內容 |
|------|--------|--------|------|
| `.graphify_detect.json` | `detect` / `update-detect` / `update-merge` | `ast-extract`, `cache-check`, `build`, `finalize` | 偵測到的檔案清單與統計 |
| `.graphify_incremental.json` | `update-detect` | `update-merge` | 增量偵測完整結果（含 new_files, deleted_files） |
| `.graphify_ast.json` | `ast-extract` | `merge-all` | AST 提取的 nodes/edges |
| `.graphify_uncached.txt` | `cache-check` | `prepare-semantic` | 未快取的檔案清單 |
| `.graphify_cached.json` | `cache-check` | `merge-semantic` | 從快取載入的 nodes/edges |
| `.graphify_prompt_N.txt` | `prepare-semantic` | LLM dispatch | 第 N 個 chunk 的 prompt |
| `.graphify_chunk_N.json` | LLM dispatch | `merge-semantic` | 第 N 個 chunk 的提取結果 |
| `.graphify_semantic.json` | `merge-semantic` | `merge-all` | 合併後的語意提取結果 |
| `.graphify_extract.json` | `merge-all` / `update-merge` | `build`, `finalize` | 最終合併的所有提取結果 |
| `.graphify_analysis.json` | `build` | `label`, `export` | 分群、God nodes、Surprises |
| `.graphify_labels.json` | `label` | `export` | 社群標籤對應表 |

所有 `.graphify_*` 暫存檔案在 `finalize` 步驟中清理。

## 模組職責

| 模組 | 函式 | 輸入 → 輸出 |
|------|------|-------------|
| `pipeline.py` | CLI subcommands | skill 呼叫 → 結構化 JSON 輸出 + 暫存檔案管理 |
| `detect.py` | `detect(root)` / `detect_incremental(root)` | 目錄 → 檔案字典 + 統計 |
| `extract.py` | `extract(paths)` | 檔案路徑 → `{nodes, edges}` 字典 |
| `build.py` | `build_from_json(extraction)` | 提取字典 → `nx.Graph` |
| `cluster.py` | `cluster(G)` | 圖譜 → `{community_id: [node_ids]}` |
| `analyze.py` | `god_nodes` / `surprising_connections` / `suggest_questions` | 圖譜 → 分析字典 |
| `report.py` | `generate(G, ...)` | 圖譜 + 分析 → GRAPH_REPORT.md 字串 |
| `export.py` | `to_json` / `to_html` / `to_obsidian` / `to_svg` / ... | 圖譜 → 多種輸出格式 |
| `ingest.py` | `ingest(url, ...)` | URL → 檔案存入語料目錄 |
| `cache.py` | `check_semantic_cache` / `save_semantic_cache` | 檔案 → (已快取, 未快取) 分組 |
| `security.py` | 驗證輔助函式 | URL / 路徑 / 標籤 → 驗證通過或拋出例外 |
| `validate.py` | `validate_extraction(data)` | 提取字典 → 錯誤清單 |
| `serve.py` | MCP stdio 伺服器 | 圖譜檔案路徑 → 供外部 AI 客戶端使用的 MCP 工具 |
| `watch.py` | `watch(root, ...)` | 目錄 → 檔案變更時寫入旗標檔 |
| `benchmark.py` | `run_benchmark(graph_path)` | 圖譜檔案 → 語料對比子圖的 Token 壓縮比較 |
| `wiki.py` | `to_wiki(G, ...)` | 圖譜 → 可供 Agent 爬行的 wiki 頁面 |

## 提取輸出格式

每個提取器回傳：

```json
{
  "nodes": [
    {"id": "unique_string", "label": "human name", "source_file": "path", "source_location": "L42"}
  ],
  "edges": [
    {"source": "id_a", "target": "id_b", "relation": "calls|imports|uses|...", "confidence": "EXTRACTED|INFERRED|AMBIGUOUS"}
  ]
}
```

`validate.py` 在 `build_from_json()` 消費資料前驗證此格式。

## 信心標籤

| 標籤 | 含義 |
|------|------|
| `EXTRACTED` | 關聯明確存在於原始碼中（例如 import 語句、直接呼叫） |
| `INFERRED` | 關聯是合理的推論（例如 call-graph 二次掃描、在上下文中共同出現） |
| `AMBIGUOUS` | 關聯不確定；在 GRAPH_REPORT.md 中標記供人工審查 |

## 新增語言提取器

1. 在 `extract.py` 中新增 `extract_<lang>(path: Path) -> dict` 函式，遵循既有模式（tree-sitter 解析 → 走訪節點 → 收集 `nodes` 和 `edges` → call-graph 二次掃描產生 INFERRED `calls` 邊）。
2. 在 `extract()` 調度和 `collect_files()` 中註冊副檔名。
3. 將副檔名加入 `detect.py` 的 `CODE_EXTENSIONS` 和 `watch.py` 的 `_WATCHED_EXTENSIONS`。
4. 將 tree-sitter 套件加入 `pyproject.toml` 依賴。
5. 在 `tests/fixtures/` 中新增測試檔案，並在 `tests/test_languages.py` 中新增測試。

## 安全性

所有外部輸入在使用前都會經過 `graphify/security.py` 驗證：

- URL → `validate_url()`（僅允許 http/https）+ `_NoFileRedirectHandler`（阻擋 file:// 重新導向）
- 抓取內容 → `safe_fetch()` / `safe_fetch_text()`（大小上限、逾時）
- 圖譜檔案路徑 → `validate_graph_path()`（必須解析在 `graphify-out/` 內）
- 節點標籤 → `sanitize_label()`（過濾控制字元、上限 256 字元、HTML 跳脫）

完整威脅模型請參見 `SECURITY.md`。

## 測試

每個模組在 `tests/` 下有對應的測試檔案。執行方式：

```bash
pytest tests/ -q
```

所有測試都是純單元測試 — 不做網路呼叫，不在 `tmp_path` 以外產生檔案系統副作用。
