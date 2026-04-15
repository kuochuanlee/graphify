# Book Branch 實作計畫書

> 目標：在 graphify 新增 book mode，處理書本等自然語言文本，產出
> Claim/Evidence 論證圖譜、Obsidian vault 與互動 HTML。
> 執行者：Gemini CLI（逐階段完成，每階段附驗收測試）

---

## 設計決策紀錄（2026-04-15 討論結果）

### 決定 1：只做 Gemini CLI skill 全包模式

使用者在 Gemini CLI 內執行 `/graphify <書名> --book --wiki --obsidian`，
由 skill 一路編排到底，中間的 LLM 語意分析步驟由 Gemini CLI 的 LLM 處理。

### 決定 2：skill 是編排層，pipeline 是工具層

- **Skill 層**（平台相關）：告訴 LLM 怎麼編排流程、何時呼叫語意分析
- **Pipeline 層**（平台無關）：純 Python CLI 子命令，處理切割/合併/建圖等固定邏輯

Skill 直接依序呼叫個別 pipeline 子命令（與現有 code mode 相同模式）。

### 決定 3：LLM 介入點

- **語意分析**：對每個 chunk 呼叫一次 LLM（主要工作量）
- **Community labeling**：由 skill 交給 LLM 處理（沿用現有做法）

### 決定 4：`--out-dir` 參數與書本目錄結構

書本的資料夾結構：
```
raw/奇點已近/
    奇點已近_clean.md       <-- 書本原始檔
    images/                 <-- 插圖
    graphify-out/           <-- 輸出目錄（由 --out-dir 指定）
        book_chunks/
```

Pipeline 新增 `--out-dir` 參數，讓 `graphify-out/` 建在書本資料夾下，
而非專案根目錄。這樣 chunk 裡的圖片引用可以用相對路徑解析。

### 決定 5：Image 處理（方案 B）

不複製圖片。`split.py` 切割文字時：
1. 保留 `![alt](images/fig.png)` 語法在 chunk 文字裡
2. 在 METADATA header 加入 `Images: images/fig1.png, images/fig2.png`

Skill 做語意分析時，看到 METADATA 裡有 images，把文字 + 圖片一起送給
LLM multimodal API。

### 決定 6：Skill 主次地位

- `skill-gemini.md`（英文）：供 AI 執行的主檔案，用詞須審慎斟酌語意
- `skill-gemini.tw.md`（繁體中文）：逐行翻譯，供人類快速理解

### 決定 7：未來方向

- 本 branch 最終只處理書本/自然語言，code 相關 function 會清理砍掉
- 未來 Claude Desktop 支援：MCP tools wrapper + skill-claude.md

---

## 總覽

```
Phase 0 | 環境準備：複製 split.py，確認 tests 能跑               [已完成]
Phase 1 | split.py 改造：注入 METADATA header                    [已完成]
Phase 2 | detect.py 改造：偵測書本模式                            [已完成]
Phase 3 | pipeline.py 改造：--out-dir + book-prepare 子命令
Phase 4 | 端對端冒煙測試：用真實書本跑通全流程
Phase 5 | skill 文件更新：skill-gemini.md 加入 book mode 編排邏輯
```

---

## Phase 0：環境準備 [已完成]

### 任務

1. 將 `reference/split.py` 複製到 `graphify/split.py`
2. 將 `reference/test_split.py` 複製到 `tests/test_split.py`
3. 確認 `graphify/templates/semantic_extraction_book.txt` 已存在

### 驗收

```bash
python -m pytest tests/test_split.py -v
```

---

## Phase 1：split.py 改造（注入 METADATA header） [已完成]

### 目標

`flush()` 寫出 chunk 前，在檔案最開頭插入 METADATA header（書名 + 涵蓋標題），
讓 LLM 在跨章節 chunk 邊界時能正確進行指代消解。

### 驗收

```bash
python -m pytest tests/test_split.py -v
```

---

## Phase 2：detect.py 改造（書本模式偵測） [已完成]

### 目標

`detect()` 回傳結果新增 `book_mode: bool` 和 `book_file: str | None` 欄位。

### 驗收

```bash
python -m pytest tests/test_detect.py -v
```

---

## Phase 3：pipeline.py 改造

### 3A：`OUT_DIR` 支援 `--out-dir` 參數

**目標**：讓輸出目錄可由命令列指定，預設仍為 `graphify-out/`。

**改動位置**：`graphify/pipeline.py`

1. `OUT_DIR` 從常數改為全域變數
2. `main()` 解析 `--out-dir <path>` 參數，在 dispatch 之前設定 `OUT_DIR`
3. 所有 `_load_json()`、`_save_json()` 等工具函式已使用 `OUT_DIR`，不需改動

```python
# 用法
python -m graphify pipeline --out-dir raw/奇點已近/graphify-out detect raw/奇點已近/
python -m graphify pipeline --out-dir raw/奇點已近/graphify-out book-prepare
```

### 3B：新增 `cmd_book_prepare()` 函式

**目標**：書本版的 prepare-semantic，供 skill 呼叫，負責：
1. 讀取 `.graphify_detect.json`，確認 `book_mode` 為 True
2. 呼叫 `split_book(book_file, OUT_DIR / "book_chunks")`，產出 chunk 檔案
3. 對每個 chunk 產生對應的 prompt 檔案（使用 `semantic_extraction_book.txt` template）
4. 建立空的 AST stub（`.graphify_ast.json`）
5. 輸出 JSON，格式與現有 `cmd_prepare_semantic` 相同

```python
def cmd_book_prepare() -> None:
    """Book mode: 切割書本為 chunks，產生 prompt 檔案，建立空 AST stub。"""
    from graphify.split import split_book

    detect = _load_json(".graphify_detect.json")

    if not detect.get("book_mode"):
        print("ERROR: book_mode not detected.", file=sys.stderr)
        sys.exit(1)

    book_file = Path(detect["book_file"])
    chunk_dir = OUT_DIR / "book_chunks"

    # 清除前次殘留
    _clean_stale_dispatch_files()
    if chunk_dir.exists():
        shutil.rmtree(chunk_dir)

    chunks = split_book(book_file, chunk_dir)
    total = len(chunks)

    # 載入 book prompt template
    template_path = (
        Path(__file__).parent / "templates" / "semantic_extraction_book.txt"
    )
    template_text = template_path.read_text(encoding="utf-8")
    tmpl = Template(template_text)

    prompt_files = []
    for i, chunk_path in enumerate(chunks, 1):
        prompt = tmpl.safe_substitute(
            CHUNK_NUM=str(i),
            TOTAL_CHUNKS=str(total),
            SOURCE_CHUNK=chunk_path.name,
            CHUNK_TEXT=chunk_path.read_text(encoding="utf-8"),
            CURRENT_HEADINGS="",
        )
        p = OUT_DIR / f".graphify_prompt_{i}.txt"
        p.write_text(prompt, encoding="utf-8")
        prompt_files.append(str(p))

    # Book mode 無 AST，建立空 stub
    _save_json(".graphify_ast.json", {
        "nodes": [], "edges": [], "input_tokens": 0, "output_tokens": 0
    })

    est_time = 45 * ((total + 4) // 5)

    _print_json({
        "total_chunks": total,
        "prompt_files": prompt_files,
        "estimated_seconds": est_time,
        "estimate_message": f"Book extraction: {total} chunks, estimated ~{est_time}s",
    })
```

### 3C：split.py 加入 image 路徑收集

**目標**：切割時辨識 `![alt](path)` 語法，在 METADATA header 記錄圖片路徑。

**改動位置**：`graphify/split.py` 的 `flush()` 和主迴圈

1. 主迴圈中用 regex 收集每行的圖片引用：`re.findall(r'!\[.*?\]\((.*?)\)', line)`
2. METADATA header 新增一行：`Images in this chunk: images/fig1.png | images/fig2.png`
3. 圖片路徑保持原樣（相對於書本根目錄），不做複製

### 3D：更新 `main()` dispatch 表與 usage 說明

在 `dispatch` dict 中加入：

```python
"book-prepare": lambda: cmd_book_prepare(),
```

在 usage 說明中加入：

```
  book-prepare           Book mode: split book into chunks, generate prompts
```

### 驗收

```bash
python -m pytest tests/test_pipeline.py -v
python -m pytest tests/test_split.py -v
```

---

## Phase 4：端對端冒煙測試

### 測試資源

- **自動測試**：`tests/fixtures/sample_book/`，內含小型合成內容（3 章假文 + 小圖片），
  搭配 mock `BOOK_CHAR_THRESHOLD` 降低門檻
- **手動冒煙測試**：直接使用 `raw/` 下的真書（如 `raw/奇點已近/`）

### 測試步驟（模擬 skill 編排流程）

```bash
# Step 1: detect
python -m graphify pipeline --out-dir raw/奇點已近/graphify-out detect raw/奇點已近/

# Step 2: book-prepare
python -m graphify pipeline --out-dir raw/奇點已近/graphify-out book-prepare

# Step 3: 確認 chunks 有 METADATA header 且包含 Images 行
head -10 raw/奇點已近/graphify-out/book_chunks/001_*.md

# Step 4: 確認 prompt 檔案變數已替換
head -20 raw/奇點已近/graphify-out/.graphify_prompt_1.txt

# Step 5: 模擬 LLM 語意分析結果
# 對每個 prompt 產出對應的 .graphify_chunk_N.json

# Step 6: merge-semantic
python -m graphify pipeline --out-dir raw/奇點已近/graphify-out merge-semantic

# Step 7: merge-all
python -m graphify pipeline --out-dir raw/奇點已近/graphify-out merge-all

# Step 8: build
python -m graphify pipeline --out-dir raw/奇點已近/graphify-out build raw/奇點已近/

# Step 9: export
python -m graphify pipeline --out-dir raw/奇點已近/graphify-out export --obsidian

# Step 10: finalize
python -m graphify pipeline --out-dir raw/奇點已近/graphify-out finalize raw/奇點已近/
```

### 驗收標準

- `graph.json` 存在，節點 `type` 只有 `Claim` 或 `Evidence`
- `graph.html` 可在瀏覽器開啟，節點可互動
- `obsidian/` 目錄下每個節點有對應 `.md` 文件，含 wikilink

---

## Phase 5：Skill 文件更新

### 目標

在 `skill-gemini.md`（主檔案，英文，供 AI 執行）中新增 book mode 編排邏輯。
同步更新 `skill-gemini.tw.md`（逐行翻譯，供人類閱讀）。

### skill-gemini.md 新增內容大綱

```
### Book Mode

Trigger: user runs /graphify <book_folder> --book, or detect result has book_mode: true

Pipeline orchestration (execute each step in order):

  1. detect
     Run: graphify pipeline --out-dir <book_folder>/graphify-out detect <book_folder>/
     Read .graphify_detect.json, confirm book_mode is true

  2. book-prepare
     Run: graphify pipeline --out-dir <book_folder>/graphify-out book-prepare
     Produces: chunk files, prompt files, empty AST stub

  3. Semantic extraction (LLM step - you handle this)
     Read each graphify-out/.graphify_prompt_*.txt
     For each prompt:
       - Read the prompt text
       - Check METADATA header for "Images in this chunk:" line
       - If images listed: include those image files together with the prompt
         for multimodal analysis
       - Send prompt (+ images if any) to LLM
       - Save raw JSON response to graphify-out/.graphify_chunk_N.json
     Parallelism: process up to 5 chunks at a time

  4. merge-semantic
     Run: graphify pipeline --out-dir <book_folder>/graphify-out merge-semantic

  5. merge-all
     Run: graphify pipeline --out-dir <book_folder>/graphify-out merge-all

  6. build
     Run: graphify pipeline --out-dir <book_folder>/graphify-out build <book_folder>/

  7. label (LLM step - you handle this)
     Read .graphify_analysis.json, generate human-readable community labels
     Run: graphify pipeline --out-dir <book_folder>/graphify-out label <labels_json>

  8. export
     Run: graphify pipeline --out-dir <book_folder>/graphify-out export --obsidian
     (add --wiki if user requested)

  9. finalize
     Run: graphify pipeline --out-dir <book_folder>/graphify-out finalize <book_folder>/

Schema constraints for chunk JSON:
  - nodes[].type: only "Claim" or "Evidence"
  - edges[].type: only "supports", "refines", or "conflicts"
  - Must include: {nodes: [...], edges: [...], hyperedges: []}
```

### 驗收

閱讀 `skill-gemini.md`，確認：
1. Book mode 段落存在，英文用詞精確無歧義
2. 每一步都有明確的 pipeline 子命令
3. Image multimodal 分析步驟說明清楚
4. `skill-gemini.tw.md` 逐行對應翻譯完成

---

## 各 Phase 依賴關係

```
Phase 0 --> Phase 1 --> Phase 2 --> Phase 3A/B/C/D --> Phase 4 --> Phase 5
               |                       |
          (split.py                (pipeline.py
           + image收集)             + --out-dir)
```

每個 Phase 完成後先跑對應驗收測試，確認通過再進入下一個 Phase。

---

## 不在本次範圍內的事項

- 清理 code mode function（跑通後另立計畫）
- PDF / EPUB 輸入支援
- `--update` 增量更新模式的書本版
- Linux 換行符號修正
- Claude Desktop 支援（MCP tools wrapper + skill-claude.md）
