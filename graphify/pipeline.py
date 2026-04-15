"""graphify pipeline - CLI wrapper 層，供 skill 調度使用。

本模組提供 CLI subcommand，封裝 skill-gemini.md 中描述的管線各階段。
每個 subcommand 都是對原始 graphify library function 的薄包裝，額外處理：
  - 程式化決策邏輯（取代 skill 中的自然語言判斷）
  - 結構化 JSON 輸出供 LLM 消費
  - OS 無關的執行方式（不需要 Bash/PowerShell 分支）

本檔案獨立於上游 graphify 專案維護。
原始 library function 透過 import 呼叫，不做修改。
"""
from __future__ import annotations

import glob
import json
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from string import Template

# === 常數 ===

# graphify-out 輸出目錄（預設值，可由 --out-dir 參數覆蓋）
OUT_DIR = Path("graphify-out")

# 圖片副檔名（分 chunk 時每張圖片獨立一組）
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

# 程式碼副檔名（用於 --update 時判斷是否為 code-only 變更）
_CODE_EXTS = {
    ".py", ".ts", ".js", ".jsx", ".tsx", ".go", ".rs", ".java",
    ".cpp", ".c", ".rb", ".swift", ".kt", ".cs", ".scala", ".php",
    ".cc", ".cxx", ".hpp", ".h", ".kts", ".lua", ".zig", ".ps1",
    ".ex", ".exs", ".m", ".mm", ".jl",
}


# === 工具函式 ===

def _load_json(name: str) -> dict:
    """從 graphify-out/ 讀取 JSON 檔案。"""
    return json.loads((OUT_DIR / name).read_text(encoding="utf-8"))


def _save_json(name: str, data: dict) -> None:
    """將 JSON 檔案寫入 graphify-out/。"""
    (OUT_DIR / name).write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _load_graph():
    """從 graphify-out/graph.json 載入 NetworkX 圖譜。"""
    from networkx.readwrite import json_graph

    data = json.loads(
        (OUT_DIR / "graph.json").read_text(encoding="utf-8")
    )
    try:
        return json_graph.node_link_graph(data, edges="links")
    except TypeError:
        return json_graph.node_link_graph(data)


def _print_json(data: dict) -> None:
    """將結構化 JSON 印到 stdout 供 LLM 消費。"""
    print(json.dumps(data, indent=2, ensure_ascii=False))


# === Pipeline subcommand 實作 ===

def cmd_check_install() -> None:
    """Step 1: 驗證 graphify 可匯入，建立輸出目錄。"""
    try:
        import graphify  # noqa: F401
    except ImportError:
        print(
            "ERROR: graphify not found in the active Python environment.",
            file=sys.stderr,
        )
        print(
            "Please activate your project venv and install manually:",
            file=sys.stderr,
        )
        print("  uv pip install -e .", file=sys.stderr)
        sys.exit(1)

    # 建立輸出目錄並記錄 Python 直譯器路徑
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / ".graphify_python").write_text(
        sys.executable,
        encoding="utf-8",
    )


def cmd_detect(args: list[str]) -> None:
    """Step 2: 偵測檔案，輸出帶有 action 決策欄位的 JSON。"""
    # 解析 --book flag 與路徑參數
    force_book = "--book" in args
    positional = [a for a in args if not a.startswith("--")]

    if not positional:
        print("error: missing path argument", file=sys.stderr)
        sys.exit(1)

    from graphify.detect import detect

    path = positional[0]
    result = detect(Path(path))

    # --book 強制模式：跳過 BOOK_CHAR_THRESHOLD 自動偵測，
    # 直接找最大的 .md/.txt 檔案作為 book_file
    if force_book and not result.get("book_mode"):
        doc_files = [
            Path(f) for f in result.get("files", {}).get("document", [])
        ]
        if doc_files:
            # 選擇最大的文件檔案作為書本
            largest = max(doc_files, key=lambda p: p.stat().st_size)
            result["book_mode"] = True
            result["book_file"] = str(largest)
        else:
            print(
                "ERROR: --book specified but no .md/.txt files found.",
                file=sys.stderr,
            )
            sys.exit(1)

    # 程式化決策邏輯（原本散落在 skill 中用自然語言描述）
    action = "proceed"
    confirmation_prompt = None
    total_files = result.get("total_files", 0)
    total_words = result.get("total_words", 0)
    files = result.get("files", {})

    # 沒有檔案 → 停止（book mode 下只要有 book_file 就繼續）
    if total_files == 0 and not result.get("book_mode"):
        action = "stop"

    # 語料庫過大 → 詢問使用者選擇子目錄（book mode 不適用此檢查）
    elif not result.get("book_mode") and (total_words > 2_000_000 or total_files > 200):
        action = "ask_user"
        dir_counts: dict[str, int] = defaultdict(int)
        for cat_files in files.values():
            for f in cat_files:
                dir_counts[str(Path(f).parent)] += 1
        top_dirs = sorted(
            dir_counts.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:5]
        lines = [
            f"Corpus is large ({total_files} files, ~{total_words:,} words).",
            "Top subdirectories:",
        ]
        for d, count in top_dirs:
            lines.append(f"  {d}: {count} files")
        lines.append("Which subfolder should I run on?")
        confirmation_prompt = "\n".join(lines)

    # 判斷是否為純程式碼語料庫
    non_code = (
        files.get("document", [])
        + files.get("paper", [])
        + files.get("image", [])
    )
    code_only = bool(not non_code and files.get("code"))

    # 格式化摘要
    summary_lines = [f"Corpus: {total_files} files ~ ~{total_words:,} words"]
    if result.get("book_mode"):
        summary_lines.append(f"  Book mode: {result.get('book_file', 'unknown')}")
    for cat, flist in files.items():
        if flist:
            exts = sorted(set(Path(f).suffix for f in flist[:10]))[:5]
            summary_lines.append(
                f"  {cat}: {len(flist)} files ({' '.join(exts)})"
            )

    skipped = result.get("skipped_sensitive", [])

    # 儲存偵測結果供後續步驟使用
    _save_json(".graphify_detect.json", result)

    _print_json({
        "action": action,
        "summary": "\n".join(summary_lines),
        "confirmation_prompt": confirmation_prompt,
        "total_files": total_files,
        "total_words": total_words,
        "skipped_count": len(skipped),
        "code_only": code_only,
        "book_mode": result.get("book_mode", False),
    })


def cmd_ast_extract() -> None:
    """Step 3A: 對程式碼檔案執行 AST 結構化提取。"""
    from graphify.extract import collect_files, extract

    detect = _load_json(".graphify_detect.json")
    code_files = []
    for f in detect.get("files", {}).get("code", []):
        p = Path(f)
        if p.is_dir():
            code_files.extend(collect_files(p))
        else:
            code_files.append(p)

    if code_files:
        result = extract(code_files)
        _save_json(".graphify_ast.json", result)
        print(
            f'AST: {len(result["nodes"])} nodes, '
            f'{len(result["edges"])} edges'
        )
    else:
        _save_json(
            ".graphify_ast.json",
            {
                "nodes": [],
                "edges": [],
                "input_tokens": 0,
                "output_tokens": 0,
            },
        )
        print("No code files - skipping AST extraction")


def cmd_cache_check() -> None:
    """Step B0: 檢查語意提取快取。"""
    from graphify.cache import check_semantic_cache

    detect = _load_json(".graphify_detect.json")
    all_files = [f for files in detect["files"].values() for f in files]

    cached_nodes, cached_edges, cached_hyperedges, uncached = (
        check_semantic_cache(all_files)
    )

    # 有快取結果就寫入暫存檔
    if cached_nodes or cached_edges or cached_hyperedges:
        _save_json(".graphify_cached.json", {
            "nodes": cached_nodes,
            "edges": cached_edges,
            "hyperedges": cached_hyperedges,
        })

    # 寫入未快取檔案清單
    (OUT_DIR / ".graphify_uncached.txt").write_text(
        "\n".join(uncached),
        encoding="utf-8",
    )

    _print_json({
        "cached_count": len(all_files) - len(uncached),
        "uncached_count": len(uncached),
        "skip_semantic": len(uncached) == 0,
    })


def cmd_prepare_semantic(args: list[str]) -> None:
    """Step B1: 將未快取檔案切分 chunk 並產生 prompt 檔案。"""
    deep = "--deep" in args

    # 清除前次殘留的 chunk 和 prompt 暫存檔案，避免污染後續 merge
    _clean_stale_dispatch_files()

    # 讀取未快取檔案清單
    uncached_path = OUT_DIR / ".graphify_uncached.txt"
    if not uncached_path.exists():
        _print_json({"total_chunks": 0, "prompt_files": []})
        return

    uncached = [
        f
        for f in uncached_path.read_text(encoding="utf-8").strip().split("\n")
        if f
    ]
    if not uncached:
        _print_json({"total_chunks": 0, "prompt_files": []})
        return

    # 載入 prompt template
    template_path = (
        Path(__file__).parent / "templates" / "semantic_extraction.txt"
    )
    template_text = template_path.read_text(encoding="utf-8")
    tmpl = Template(template_text)

    # 分組邏輯：圖片獨立一組，其餘以目錄為單位分組，每組 20-25 個檔案
    images = [
        f for f in uncached
        if Path(f).suffix.lower() in _IMAGE_EXTS
    ]
    non_images = [
        f for f in uncached
        if Path(f).suffix.lower() not in _IMAGE_EXTS
    ]

    # 依照目錄分組（同目錄的檔案放在一起可提高跨檔關聯擷取率）
    by_dir: dict[str, list[str]] = defaultdict(list)
    for f in non_images:
        by_dir[str(Path(f).parent)].append(f)

    # 建構 chunks，每組上限 25 個檔案
    chunks: list[list[str]] = []
    current: list[str] = []
    for dir_path in sorted(by_dir.keys()):
        dir_files = by_dir[dir_path]
        if len(current) + len(dir_files) > 25:
            if current:
                chunks.append(current)
            # 單一目錄超過 25 個檔案就拆分
            while len(dir_files) > 25:
                chunks.append(dir_files[:25])
                dir_files = dir_files[25:]
            current = list(dir_files)
        else:
            current.extend(dir_files)
    if current:
        chunks.append(current)

    # 每張圖片獨立一組（視覺解析需要獨立脈絡）
    for img in images:
        chunks.append([img])

    total = len(chunks)

    # Deep mode 額外指令區段
    deep_section = ""
    if deep:
        deep_section = (
            "DEEP_MODE is ON: be aggressive with INFERRED edges - "
            "indirect deps, shared assumptions, latent couplings. "
            "Mark uncertain ones AMBIGUOUS instead of omitting."
        )

    # 產生每個 chunk 的 prompt 檔案
    prompt_files = []
    for i, chunk in enumerate(chunks, 1):
        prompt = tmpl.safe_substitute(
            FILE_LIST="\n".join(chunk),
            CHUNK_NUM=str(i),
            TOTAL_CHUNKS=str(total),
            DEEP_MODE_SECTION=deep_section,
        )
        p = OUT_DIR / f".graphify_prompt_{i}.txt"
        p.write_text(prompt, encoding="utf-8")
        prompt_files.append(str(p))

    # 預估耗時（平行執行，每批約 45 秒）
    est_time = 45 * ((total + 4) // 5)

    _print_json({
        "total_chunks": total,
        "prompt_files": prompt_files,
        "estimated_seconds": est_time,
        "estimate_message": (
            f"Semantic extraction: ~{len(uncached)} files -> "
            f"{total} agents, estimated ~{est_time}s"
        ),
    })


def cmd_merge_semantic() -> None:
    """Step B3: 收集 chunk 結果、驗證、快取、合併、清理暫存檔。"""
    from graphify.cache import save_semantic_cache

    # 收集所有 chunk 結果
    chunk_files = sorted(glob.glob(str(OUT_DIR / ".graphify_chunk_*.json")))
    all_nodes: list[dict] = []
    all_edges: list[dict] = []
    all_hyperedges: list[dict] = []
    success_count = 0
    fail_count = 0

    for cf in chunk_files:
        try:
            data = json.loads(Path(cf).read_text(encoding="utf-8-sig"))
            if "nodes" in data and "edges" in data:
                all_nodes.extend(data["nodes"])
                all_edges.extend(data["edges"])
                all_hyperedges.extend(data.get("hyperedges", []))
                success_count += 1
            else:
                print(f"Warning: {cf} missing nodes/edges, skipping")
                fail_count += 1
        except (json.JSONDecodeError, OSError) as e:
            print(f"Warning: {cf} invalid ({e}), skipping")
            fail_count += 1

    # 先寫入快取再判定成敗（確保斷點續建可用）
    # 即使整體失敗，已成功的 chunk 仍會被快取，下次 cache-check 可識別
    if all_nodes or all_edges:
        saved = save_semantic_cache(all_nodes, all_edges, all_hyperedges)
        print(f"Cached {saved} files")

    # 超過半數 chunk 失敗則中止（快取已寫入，下次重跑可續建）
    total = success_count + fail_count
    if total > 0 and fail_count > total / 2:
        print(
            f"FATAL: {fail_count}/{total} chunks failed (>50%). Aborting.",
            file=sys.stderr,
        )
        print(
            f"FATAL: {fail_count}/{total} chunks failed (>50%). Aborting."
        )
        sys.exit(1)

    # 儲存新的語意提取結果
    new_data = {
        "nodes": all_nodes,
        "edges": all_edges,
        "hyperedges": all_hyperedges,
    }
    _save_json(".graphify_semantic_new.json", new_data)

    # 合併快取 + 新結果
    cached = (
        _load_json(".graphify_cached.json")
        if (OUT_DIR / ".graphify_cached.json").exists()
        else {"nodes": [], "edges": [], "hyperedges": []}
    )

    merged_nodes = cached["nodes"] + all_nodes
    merged_edges = cached["edges"] + all_edges
    merged_hyperedges = (
        cached.get("hyperedges", []) + all_hyperedges
    )

    # 依 id 去除重複節點
    seen: set[str] = set()
    deduped = []
    for n in merged_nodes:
        if n["id"] not in seen:
            seen.add(n["id"])
            deduped.append(n)

    _save_json(".graphify_semantic.json", {
        "nodes": deduped,
        "edges": merged_edges,
        "hyperedges": merged_hyperedges,
        "input_tokens": 0,
        "output_tokens": 0,
    })

    print(
        f"Extraction complete - {len(deduped)} nodes, "
        f"{len(merged_edges)} edges "
        f"({len(cached['nodes'])} from semantic cache, "
        f"{len(all_nodes)} newly extracted)"
    )

    # 清理所有暫存檔案
    for name in [
        ".graphify_cached.json",
        ".graphify_uncached.txt",
        ".graphify_semantic_new.json",
    ]:
        p = OUT_DIR / name
        if p.exists():
            p.unlink()

    _clean_stale_dispatch_files()


def _clean_stale_dispatch_files() -> None:
    """清除前次執行殘留的 chunk 和 prompt 暫存檔案。

    避免殘留檔案污染後續執行的 merge 結果。
    由 prepare-semantic 和 merge-semantic 呼叫。
    """
    for pattern in [".graphify_chunk_*.json", ".graphify_prompt_*.txt"]:
        for f in OUT_DIR.glob(pattern):
            f.unlink(missing_ok=True)


def cmd_book_prepare() -> None:
    """Book mode: 切割書本為 chunks，產生 prompt 檔案，建立空 AST stub。"""
    from graphify.split import split_book

    detect = _load_json(".graphify_detect.json")

    # 確認偵測結果為 book mode
    if not detect.get("book_mode"):
        print("ERROR: book_mode not detected.", file=sys.stderr)
        sys.exit(1)

    book_file = Path(detect["book_file"])
    chunk_dir = OUT_DIR / "book_chunks"

    # 清除前次殘留的 dispatch 暫存檔
    _clean_stale_dispatch_files()

    # 清除前次殘留的 chunk 目錄
    if chunk_dir.exists():
        shutil.rmtree(chunk_dir)

    # 切割書本為 chunks
    chunks = split_book(book_file, chunk_dir)
    total = len(chunks)

    # 載入 book prompt template
    template_path = (
        Path(__file__).parent / "templates" / "semantic_extraction_book.txt"
    )
    template_text = template_path.read_text(encoding="utf-8")
    tmpl = Template(template_text)

    # 產生每個 chunk 的 prompt 檔案
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
        "nodes": [],
        "edges": [],
        "input_tokens": 0,
        "output_tokens": 0,
    })

    # 預估耗時（平行執行，每批約 45 秒）
    est_time = 45 * ((total + 4) // 5)

    _print_json({
        "total_chunks": total,
        "prompt_files": prompt_files,
        "estimated_seconds": est_time,
        "estimate_message": f"Book extraction: {total} chunks, estimated ~{est_time}s",
    })


def cmd_merge_all() -> None:
    """Step 3C: 合併 AST + 語意提取結果。"""
    ast = _load_json(".graphify_ast.json")

    # 語意結果可能不存在（code-only 的情況下跳過了 Part B）
    sem = (
        _load_json(".graphify_semantic.json")
        if (OUT_DIR / ".graphify_semantic.json").exists()
        else {
            "nodes": [],
            "edges": [],
            "hyperedges": [],
            "input_tokens": 0,
            "output_tokens": 0,
        }
    )

    # AST 節點優先，語意節點依 id 去重後合併
    seen = {n["id"] for n in ast["nodes"]}
    merged_nodes = list(ast["nodes"])
    for n in sem["nodes"]:
        if n["id"] not in seen:
            merged_nodes.append(n)
            seen.add(n["id"])

    merged = {
        "nodes": merged_nodes,
        "edges": ast["edges"] + sem["edges"],
        "hyperedges": sem.get("hyperedges", []),
        "input_tokens": sem.get("input_tokens", 0),
        "output_tokens": sem.get("output_tokens", 0),
    }
    _save_json(".graphify_extract.json", merged)

    print(
        f'Merged: {len(merged_nodes)} nodes, {len(merged["edges"])} edges '
        f'({len(ast["nodes"])} AST + {len(sem["nodes"])} semantic)'
    )


def cmd_build(args: list[str]) -> None:
    """Step 4: 建立圖譜、分群、分析。"""
    if not args:
        print("error: missing path argument", file=sys.stderr)
        sys.exit(1)

    input_path = args[0]

    from graphify.build import build_from_json
    from graphify.cluster import cluster, score_all
    from graphify.analyze import (
        god_nodes,
        surprising_connections,
        suggest_questions,
    )
    from graphify.report import generate
    from graphify.export import to_json

    extraction = _load_json(".graphify_extract.json")
    detection = _load_json(".graphify_detect.json")

    G = build_from_json(extraction)

    # 空圖譜檢查
    if G.number_of_nodes() == 0:
        print(
            "ERROR: Graph is empty - extraction produced no nodes.",
            file=sys.stderr,
        )
        print(
            "Possible causes: all files were skipped, "
            "binary-only corpus, or extraction failed.",
            file=sys.stderr,
        )
        sys.exit(1)

    communities = cluster(G)
    cohesion = score_all(G, communities)
    tokens = {
        "input": extraction.get("input_tokens", 0),
        "output": extraction.get("output_tokens", 0),
    }
    gods = god_nodes(G)
    surprises = surprising_connections(G, communities)

    # 暫用數字標籤，Step 5 會替換為人類可讀名稱
    labels = {cid: f"Community {cid}" for cid in communities}
    questions = suggest_questions(G, communities, labels)

    report = generate(
        G,
        communities,
        cohesion,
        labels,
        gods,
        surprises,
        detection,
        tokens,
        input_path,
        suggested_questions=questions,
    )
    Path(OUT_DIR / "GRAPH_REPORT.md").write_text(report, encoding="utf-8")
    to_json(G, communities, str(OUT_DIR / "graph.json"))

    analysis = {
        "communities": {str(k): v for k, v in communities.items()},
        "cohesion": {str(k): v for k, v in cohesion.items()},
        "gods": gods,
        "surprises": surprises,
        "questions": questions,
    }
    _save_json(".graphify_analysis.json", analysis)

    print(
        f"Graph: {G.number_of_nodes()} nodes, "
        f"{G.number_of_edges()} edges, "
        f"{len(communities)} communities"
    )


def cmd_label(args: list[str]) -> None:
    """Step 5: 套用社群標籤並重新產生報告。

    支援兩種輸入方式：
    - 直接傳 JSON 字串：pipeline label '{"0": "Name"}'
    - 從檔案讀取：pipeline label --from-file labels.json
    """
    labels_json = None
    labels_file = None
    input_path = "."

    # 解析參數
    i = 0
    while i < len(args):
        if args[i] == "--from-file" and i + 1 < len(args):
            labels_file = args[i + 1]
            i += 2
        elif args[i] == "--path" and i + 1 < len(args):
            input_path = args[i + 1]
            i += 2
        elif labels_json is None and not args[i].startswith("--"):
            labels_json = args[i]
            i += 1
        else:
            i += 1

    # 從檔案讀取 JSON（優先於命令列引數，避免 shell 引號問題）
    if labels_file:
        try:
            labels_json = Path(labels_file).read_text(encoding="utf-8")
        except OSError as e:
            print(f"error: cannot read labels file: {e}", file=sys.stderr)
            sys.exit(1)

    if not labels_json:
        print(
            "error: missing labels. Use JSON string or --from-file",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        labels = {int(k): v for k, v in json.loads(labels_json).items()}
    except (json.JSONDecodeError, ValueError) as e:
        print(f"error: invalid labels JSON: {e}", file=sys.stderr)
        sys.exit(1)

    from graphify.build import build_from_json
    from graphify.analyze import suggest_questions
    from graphify.report import generate

    extraction = _load_json(".graphify_extract.json")
    detection = _load_json(".graphify_detect.json")
    analysis = _load_json(".graphify_analysis.json")

    G = build_from_json(extraction)
    communities = {int(k): v for k, v in analysis["communities"].items()}
    cohesion = {int(k): v for k, v in analysis["cohesion"].items()}
    tokens = {
        "input": extraction.get("input_tokens", 0),
        "output": extraction.get("output_tokens", 0),
    }

    # 用真實標籤重新產生推薦問題
    questions = suggest_questions(G, communities, labels)

    report = generate(
        G,
        communities,
        cohesion,
        labels,
        analysis["gods"],
        analysis["surprises"],
        detection,
        tokens,
        input_path,
        suggested_questions=questions,
    )
    Path(OUT_DIR / "GRAPH_REPORT.md").write_text(report, encoding="utf-8")
    # 暫存檔（供同次管線內的後續步驟使用）
    _save_json(
        ".graphify_labels.json",
        {str(k): v for k, v in labels.items()},
    )

    # 持久化版本（不帶 .graphify_ 前綴，finalize 不會清理）
    # 供事後獨立呼叫 export --wiki 等指令使用
    _save_json(
        "community_labels.json",
        {str(k): v for k, v in labels.items()},
    )

    print("Report updated with community labels")


def cmd_export(args: list[str]) -> None:
    """Step 6-7: 將圖譜匯出為各種格式。"""
    # 解析 flags
    do_html = "--no-viz" not in args
    do_obsidian = "--obsidian" in args
    do_svg = "--svg" in args
    do_graphml = "--graphml" in args
    do_neo4j = "--neo4j" in args
    do_wiki = "--wiki" in args
    neo4j_push_uri = None
    obsidian_dir = str(OUT_DIR / "obsidian")

    for i, a in enumerate(args):
        if a == "--neo4j-push" and i + 1 < len(args):
            neo4j_push_uri = args[i + 1]
        if a == "--obsidian-dir" and i + 1 < len(args):
            obsidian_dir = args[i + 1]

    # 載入圖譜：優先使用管線暫存檔（pipeline 內呼叫），
    # 若已被 finalize 清理則 fallback 到已完成的 graph.json（獨立呼叫）
    extract_path = OUT_DIR / ".graphify_extract.json"
    analysis_path = OUT_DIR / ".graphify_analysis.json"

    if extract_path.exists() and analysis_path.exists():
        # 正常管線流程：從暫存的 extract + analysis 重建
        from graphify.build import build_from_json

        extraction = _load_json(".graphify_extract.json")
        analysis = _load_json(".graphify_analysis.json")

        G = build_from_json(extraction)
        communities = {int(k): v for k, v in analysis["communities"].items()}
        cohesion = {int(k): v for k, v in analysis["cohesion"].items()}
    elif (OUT_DIR / "graph.json").exists():
        # Fallback：finalize 已清理暫存檔，從完成品 graph.json 載入
        G = _load_graph()

        # 從圖譜節點的 community 屬性重建 communities dict
        communities: dict[int, list[str]] = {}
        for node_id, data in G.nodes(data=True):
            cid = data.get("community")
            if cid is not None:
                communities.setdefault(int(cid), []).append(node_id)

        # 從圖譜重新計算 cohesion
        from graphify.cluster import score_all
        cohesion = score_all(G, communities)
    else:
        print(
            "ERROR: No graph data found. Run /graphify first.",
            file=sys.stderr,
        )
        sys.exit(1)

    # 社群標籤：暫存檔 > 持久檔 > 空（fallback 到數字編號）
    if (OUT_DIR / ".graphify_labels.json").exists():
        labels_raw = _load_json(".graphify_labels.json")
    elif (OUT_DIR / "community_labels.json").exists():
        labels_raw = _load_json("community_labels.json")
    else:
        labels_raw = {}
    labels = {int(k): v for k, v in labels_raw.items()}

    # HTML（預設產生，除非 --no-viz）
    if do_html:
        if G.number_of_nodes() > 5000:
            print(
                f"Graph has {G.number_of_nodes()} nodes - "
                f"too large for HTML. Use Obsidian vault instead."
            )
        else:
            from graphify.export import to_html

            to_html(
                G,
                communities,
                str(OUT_DIR / "graph.html"),
                community_labels=labels or None,
            )
            print("graph.html written - open in any browser")

    # Obsidian 筆記庫
    if do_obsidian:
        from graphify.export import to_obsidian, to_canvas

        n = to_obsidian(
            G,
            communities,
            obsidian_dir,
            community_labels=labels or None,
            cohesion=cohesion,
        )
        print(f"Obsidian vault: {n} notes in {obsidian_dir}/")
        to_canvas(
            G,
            communities,
            f"{obsidian_dir}/graph.canvas",
            community_labels=labels or None,
        )
        print(f"Canvas: {obsidian_dir}/graph.canvas")

    # SVG 靜態圖
    if do_svg:
        from graphify.export import to_svg

        to_svg(
            G,
            communities,
            str(OUT_DIR / "graph.svg"),
            community_labels=labels or None,
        )
        print("graph.svg written")

    # GraphML（Gephi, yEd）
    if do_graphml:
        from graphify.export import to_graphml

        to_graphml(G, communities, str(OUT_DIR / "graph.graphml"))
        print("graph.graphml written")

    # Neo4j Cypher 匯出檔
    if do_neo4j:
        from graphify.export import to_cypher

        to_cypher(G, str(OUT_DIR / "cypher.txt"))
        print(
            "cypher.txt written - import with: "
            "cypher-shell < graphify-out/cypher.txt"
        )

    # Neo4j 直接推送
    if neo4j_push_uri:
        from graphify.export import push_to_neo4j

        result = push_to_neo4j(
            G,
            uri=neo4j_push_uri,
            user="neo4j",
            password="",
            communities=communities,
        )
        print(
            f'Pushed to Neo4j: {result["nodes"]} nodes, '
            f'{result["edges"]} edges'
        )

    # Wiki
    if do_wiki:
        from graphify.wiki import to_wiki

        to_wiki(
            G,
            communities,
            str(OUT_DIR / "wiki"),
            community_labels=labels or None,
        )
        print("Wiki written to graphify-out/wiki/")


def cmd_benchmark() -> None:
    """Step 8: 執行 Token 壓縮率基準測試。"""
    detect_path = OUT_DIR / ".graphify_detect.json"
    if not detect_path.exists():
        print("Benchmark skipped - no detection data found")
        return

    detection = _load_json(".graphify_detect.json")
    total_words = detection.get("total_words", 0)

    # 小型語料庫跳過：圖譜的價值在結構清晰度而非壓縮率
    if total_words <= 5000:
        print(
            "Corpus is small (<=5000 words) - benchmark skipped "
            "(graph value is structural clarity, not compression)"
        )
        return

    from graphify.benchmark import run_benchmark, print_benchmark

    result = run_benchmark(
        str(OUT_DIR / "graph.json"),
        corpus_words=total_words,
    )
    print_benchmark(result)


def cmd_finalize(args: list[str]) -> None:
    """Step 9: 儲存 manifest、更新成本追蹤器、清理暫存檔。"""
    from graphify.detect import save_manifest

    detect = _load_json(".graphify_detect.json")
    save_manifest(detect["files"])

    # 更新累計成本追蹤器
    extract = _load_json(".graphify_extract.json")
    input_tok = extract.get("input_tokens", 0)
    output_tok = extract.get("output_tokens", 0)

    cost_path = OUT_DIR / "cost.json"
    if cost_path.exists():
        cost = json.loads(cost_path.read_text(encoding="utf-8"))
    else:
        cost = {
            "runs": [],
            "total_input_tokens": 0,
            "total_output_tokens": 0,
        }

    cost["runs"].append({
        "date": datetime.now(timezone.utc).isoformat(),
        "input_tokens": input_tok,
        "output_tokens": output_tok,
        "files": detect.get("total_files", 0),
    })
    cost["total_input_tokens"] += input_tok
    cost["total_output_tokens"] += output_tok
    cost_path.write_text(
        json.dumps(cost, indent=2),
        encoding="utf-8",
    )

    if input_tok == 0 and output_tok == 0:
        print("This run: N/A (tokens not recorded by Gemini CLI)")
    else:
        print(f"This run: {input_tok:,} input tokens, {output_tok:,} output tokens")
    print(
        f"All time: {cost['total_input_tokens']:,} input, "
        f"{cost['total_output_tokens']:,} output "
        f"({len(cost['runs'])} runs)"
    )

    # 清理暫存檔案
    for name in [
        ".graphify_detect.json",
        ".graphify_extract.json",
        ".graphify_ast.json",
        ".graphify_semantic.json",
        ".graphify_analysis.json",
        ".graphify_labels.json",
        ".needs_update",
    ]:
        p = OUT_DIR / name
        if p.exists():
            p.unlink()


def cmd_update_detect(args: list[str]) -> None:
    """--update: 偵測自上次執行以來的變更檔案。"""
    if not args:
        print("error: missing path argument", file=sys.stderr)
        sys.exit(1)

    from graphify.detect import detect_incremental

    result = detect_incremental(Path(args[0]))
    new_total = result.get("new_total", 0)
    _save_json(".graphify_incremental.json", result)

    # 為了讓後續 extract 步驟只處理新檔案，我們同步寫入 .graphify_detect.json
    detect_copy = result.copy()
    detect_copy["files"] = result.get("new_files", {})
    _save_json(".graphify_detect.json", detect_copy)

    # 沒有變更 → 停止
    if new_total == 0:
        _print_json({
            "action": "stop",
            "message": "No files changed since last run.",
        })
        return

    # 判斷是否全部都是程式碼檔案的變更
    new_files = result.get("new_files", {})
    all_changed = [f for files in new_files.values() for f in files]
    code_only = all(
        Path(f).suffix.lower() in _CODE_EXTS
        for f in all_changed
    )

    _print_json({
        "action": "proceed",
        "new_total": new_total,
        "code_only": code_only,
        "message": f"{new_total} new/changed file(s) to re-extract.",
    })


def cmd_update_merge() -> None:
    """--update: 將新提取結果合併到既有圖譜。"""
    from graphify.build import build_from_json
    from graphify.export import to_json
    from networkx.readwrite import json_graph

    old_graph_path = OUT_DIR / "graph.json"
    backup_path = OUT_DIR / ".graphify_old.json"

    # 備份舊圖譜
    if old_graph_path.exists():
        shutil.copy(str(old_graph_path), str(backup_path))

    # 載入既有圖譜
    existing_data = json.loads(
        old_graph_path.read_text(encoding="utf-8")
    )
    try:
        G_existing = json_graph.node_link_graph(
            existing_data, edges="links"
        )
    except TypeError:
        G_existing = json_graph.node_link_graph(existing_data)

    # 載入新的提取結果
    new_extraction = _load_json(".graphify_extract.json")
    G_new = build_from_json(new_extraction)

    # 修剪已刪除檔案的節點
    incremental = _load_json(".graphify_incremental.json")
    deleted = set(incremental.get("deleted_files", []))
    if deleted:
        to_remove = [
            n for n, d in G_existing.nodes(data=True)
            if d.get("source_file") in deleted
        ]
        G_existing.remove_nodes_from(to_remove)
        print(
            f"Pruned {len(to_remove)} ghost nodes "
            f"from {len(deleted)} deleted file(s)"
        )

    # 合併新圖譜到既有圖譜
    G_existing.update(G_new)
    print(
        f"Merged: {G_existing.number_of_nodes()} nodes, "
        f"{G_existing.number_of_edges()} edges"
    )

    # 顯示圖譜差異
    if backup_path.exists():
        from graphify.analyze import graph_diff

        old_data = json.loads(
            backup_path.read_text(encoding="utf-8")
        )
        try:
            G_old = json_graph.node_link_graph(old_data, edges="links")
        except TypeError:
            G_old = json_graph.node_link_graph(old_data)

        diff = graph_diff(G_old, G_new)
        summary = diff.get("summary", "")
        if summary:
            print(summary)
        if diff.get("new_nodes"):
            labels = [
                n.get("label", "?") for n in diff["new_nodes"][:5]
            ]
            print(f"New nodes: {', '.join(labels)}")
        if diff.get("new_edges"):
            print(f"New edges: {len(diff['new_edges'])}")

    # 儲存合併後的完整圖譜至 .graphify_extract.json 供後續 cmd_build 讀取
    nodes = []
    for n, d in G_existing.nodes(data=True):
        node = {"id": n}
        node.update(d)
        nodes.append(node)

    edges = []
    for u, v, d in G_existing.edges(data=True):
        edge = {"source": d.get("_src", u), "target": d.get("_tgt", v)}
        for k, val in d.items():
            if k not in ('_src', '_tgt'):
                edge[k] = val
        edges.append(edge)

    merged_extract = {
        "nodes": nodes,
        "edges": edges,
        "hyperedges": G_existing.graph.get("hyperedges", []),
        "input_tokens": new_extraction.get("input_tokens", 0),
        "output_tokens": new_extraction.get("output_tokens", 0),
    }
    _save_json(".graphify_extract.json", merged_extract)

    # 恢復完整的 .graphify_detect.json，確保報告的檔案總數正確，且不會覆蓋掉未變更檔案的 manifest
    _save_json(".graphify_detect.json", incremental)

    # 清理備份和漸進式偵測資料
    for p in [backup_path, OUT_DIR / ".graphify_incremental.json"]:
        if p.exists():
            p.unlink()


def cmd_cluster_only() -> None:
    """--cluster-only: 對既有圖譜重新執行分群，不重新提取。"""
    graph_path = OUT_DIR / "graph.json"
    if not graph_path.exists():
        print(
            "ERROR: No graph found. Run /graphify <path> first.",
            file=sys.stderr,
        )
        sys.exit(1)

    from graphify.cluster import cluster, score_all
    from graphify.analyze import god_nodes, surprising_connections
    from graphify.report import generate
    from graphify.export import to_json

    G = _load_graph()
    detection = {
        "total_files": 0,
        "total_words": 99999,
        "needs_graph": True,
        "warning": None,
        "files": {"code": [], "document": [], "paper": []},
    }
    tokens = {"input": 0, "output": 0}

    communities = cluster(G)
    cohesion = score_all(G, communities)
    gods = god_nodes(G)
    surprises = surprising_connections(G, communities)
    labels = {cid: f"Community {cid}" for cid in communities}

    report = generate(
        G,
        communities,
        cohesion,
        labels,
        gods,
        surprises,
        detection,
        tokens,
        ".",
    )
    Path(OUT_DIR / "GRAPH_REPORT.md").write_text(report, encoding="utf-8")
    to_json(G, communities, str(OUT_DIR / "graph.json"))

    analysis = {
        "communities": {str(k): v for k, v in communities.items()},
        "cohesion": {str(k): v for k, v in cohesion.items()},
        "gods": gods,
        "surprises": surprises,
    }
    _save_json(".graphify_analysis.json", analysis)

    print(f"Re-clustered: {len(communities)} communities")


def cmd_path(args: list[str]) -> None:
    """/graphify path: 尋找兩個概念之間的最短路徑。"""
    if len(args) < 2:
        print(
            'error: usage: graphify pipeline path "NodeA" "NodeB"',
            file=sys.stderr,
        )
        sys.exit(1)

    graph_path = OUT_DIR / "graph.json"
    if not graph_path.exists():
        print(
            "ERROR: No graph found. Run /graphify <path> first.",
            file=sys.stderr,
        )
        sys.exit(1)

    import networkx as nx

    G = _load_graph()
    a_term = args[0]
    b_term = args[1]

    def find_node(term: str):
        """依關鍵字比對找出最佳匹配節點。"""
        term_lower = term.lower()
        scored = sorted(
            [
                (
                    sum(
                        1 for w in term_lower.split()
                        if w in G.nodes[n].get("label", "").lower()
                    ),
                    n,
                )
                for n in G.nodes()
            ],
            reverse=True,
        )
        if scored and scored[0][0] > 0:
            return scored[0][1]
        return None

    src = find_node(a_term)
    tgt = find_node(b_term)

    if not src or not tgt:
        print(f"Could not find nodes matching: {a_term!r} or {b_term!r}")
        return

    try:
        path = nx.shortest_path(G, src, tgt)
        print(f"Shortest path ({len(path) - 1} hops):")
        for i, nid in enumerate(path):
            label = G.nodes[nid].get("label", nid)
            if i < len(path) - 1:
                edge = G.edges[nid, path[i + 1]]
                rel = edge.get("relation", "")
                conf = edge.get("confidence", "")
                print(f"  {label} --{rel}--> [{conf}]")
            else:
                print(f"  {label}")
    except nx.NetworkXNoPath:
        print(f"No path found between {a_term!r} and {b_term!r}")
    except nx.NodeNotFound as e:
        print(f"Node not found: {e}")


def cmd_explain(args: list[str]) -> None:
    """/graphify explain: 解釋單一節點及其所有連線。"""
    if not args:
        print(
            'error: usage: graphify pipeline explain "NodeName"',
            file=sys.stderr,
        )
        sys.exit(1)

    graph_path = OUT_DIR / "graph.json"
    if not graph_path.exists():
        print(
            "ERROR: No graph found. Run /graphify <path> first.",
            file=sys.stderr,
        )
        sys.exit(1)

    G = _load_graph()
    term = args[0]
    term_lower = term.lower()

    # 依關鍵字比對找出最佳匹配節點
    scored = sorted(
        [
            (
                sum(
                    1 for w in term_lower.split()
                    if w in G.nodes[n].get("label", "").lower()
                ),
                n,
            )
            for n in G.nodes()
        ],
        reverse=True,
    )

    if not scored or scored[0][0] == 0:
        print(f"No node matching {term!r}")
        return

    nid = scored[0][1]
    data_n = G.nodes[nid]

    print(f'NODE: {data_n.get("label", nid)}')
    print(f'  source: {data_n.get("source_file", "unknown")}')
    print(f'  type: {data_n.get("file_type", "unknown")}')
    print(f"  degree: {G.degree(nid)}")
    print()
    print("CONNECTIONS:")
    for neighbor in G.neighbors(nid):
        edge = G.edges[nid, neighbor]
        nlabel = G.nodes[neighbor].get("label", neighbor)
        rel = edge.get("relation", "")
        conf = edge.get("confidence", "")
        src_file = G.nodes[neighbor].get("source_file", "")
        print(f"  --{rel}--> {nlabel} [{conf}] ({src_file})")


def cmd_add(args: list[str]) -> None:
    """/graphify add: 抓取 URL 並存入語料庫。"""
    if not args:
        print("error: missing URL argument", file=sys.stderr)
        sys.exit(1)

    url = args[0]
    author = None
    contributor = None

    # 解析 --author 和 --contributor 參數
    i = 1
    while i < len(args):
        if args[i] == "--author" and i + 1 < len(args):
            author = args[i + 1]
            i += 2
        elif args[i] == "--contributor" and i + 1 < len(args):
            contributor = args[i + 1]
            i += 2
        else:
            i += 1

    from graphify.ingest import ingest

    try:
        out = ingest(
            url,
            Path("./raw"),
            author=author,
            contributor=contributor,
        )
        print(f"Saved to {out}")
        print(
            "Run /graphify --update to merge into the existing graph."
        )
    except (ValueError, RuntimeError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)


# === 主要分派器 ===

def main(args: list[str]) -> None:
    """路由 pipeline subcommand。

    支援 --out-dir <path> 全域參數，可在 subcommand 之前指定輸出目錄。
    """
    global OUT_DIR

    # 解析全域參數 --out-dir（在 subcommand 之前）
    filtered_args: list[str] = []
    i = 0
    while i < len(args):
        if args[i] == "--out-dir" and i + 1 < len(args):
            OUT_DIR = Path(args[i + 1])
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            i += 2
        else:
            filtered_args.append(args[i])
            i += 1

    args = filtered_args

    if not args:
        print("Usage: graphify pipeline [--out-dir <path>] <subcommand>", file=sys.stderr)
        print(file=sys.stderr)
        print("Subcommands:", file=sys.stderr)
        print("  check-install      Verify graphify is installed", file=sys.stderr)
        print("  detect <path>      Detect files and decide action", file=sys.stderr)
        print("  ast-extract        AST extraction for code files", file=sys.stderr)
        print("  cache-check        Check semantic extraction cache", file=sys.stderr)
        print("  prepare-semantic   Split files, write prompt files", file=sys.stderr)
        print("  merge-semantic     Merge chunk results + cache", file=sys.stderr)
        print("  merge-all          Merge AST + semantic extraction", file=sys.stderr)
        print("  book-prepare       Book mode: split book into chunks, generate prompts", file=sys.stderr)
        print("  build <path>       Build graph, cluster, analyze", file=sys.stderr)
        print("  label <json>       Apply community labels", file=sys.stderr)
        print("  export [flags]     Export HTML/SVG/Obsidian/Neo4j", file=sys.stderr)
        print("  benchmark          Token reduction benchmark", file=sys.stderr)
        print("  finalize [path]    Save manifest, cleanup", file=sys.stderr)
        print("  update-detect <p>  Detect changed files", file=sys.stderr)
        print("  update-merge       Merge into existing graph", file=sys.stderr)
        print("  cluster-only       Re-cluster existing graph", file=sys.stderr)
        print("  path <A> <B>       Shortest path between nodes", file=sys.stderr)
        print("  explain <node>     Explain a node", file=sys.stderr)
        print("  add <url>          Fetch URL, save to corpus", file=sys.stderr)
        sys.exit(1)

    subcmd = args[0]
    sub_args = args[1:]

    # subcommand 對應表
    dispatch = {
        "check-install": lambda: cmd_check_install(),
        "detect": lambda: cmd_detect(sub_args),
        "ast-extract": lambda: cmd_ast_extract(),
        "cache-check": lambda: cmd_cache_check(),
        "prepare-semantic": lambda: cmd_prepare_semantic(sub_args),
        "merge-semantic": lambda: cmd_merge_semantic(),
        "merge-all": lambda: cmd_merge_all(),
        "book-prepare": lambda: cmd_book_prepare(),
        "build": lambda: cmd_build(sub_args),
        "label": lambda: cmd_label(sub_args),
        "export": lambda: cmd_export(sub_args),
        "benchmark": lambda: cmd_benchmark(),
        "finalize": lambda: cmd_finalize(sub_args),
        "update-detect": lambda: cmd_update_detect(sub_args),
        "update-merge": lambda: cmd_update_merge(),
        "cluster-only": lambda: cmd_cluster_only(),
        "path": lambda: cmd_path(sub_args),
        "explain": lambda: cmd_explain(sub_args),
        "add": lambda: cmd_add(sub_args),
    }

    if subcmd not in dispatch:
        print(
            f"error: unknown pipeline subcommand '{subcmd}'",
            file=sys.stderr,
        )
        sys.exit(1)

    dispatch[subcmd]()
