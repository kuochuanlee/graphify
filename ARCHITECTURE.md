# Architecture

graphify is a three-layer architecture: **Skill** (LLM instructions) -> **Pipeline** (CLI wrapper) -> **Library** (core functions).

- **Skill** (`skill-gemini.md` / `skill-gemini.tw.md`): Operation manual for LLMs, defines the invocation sequence
- **Pipeline** (`pipeline.py`): CLI subcommand layer, encapsulates decision logic and temp file management
- **Library** (`detect.py`, `split.py`, `build.py`, ...): Pure functions, can be used standalone

## Pipeline Layer (`pipeline.py`)

`pipeline.py` is the glue layer between the skill and the library. Invoked via `python -m graphify pipeline <subcommand>`.

Responsibilities:
- Programmatic decision logic (replaces natural language judgments in the skill)
- Structured JSON output for LLM consumption
- Temp file read/write and lifecycle management under `graphify-out/`
- OS-agnostic execution (no Bash/PowerShell branching needed)

### Subcommands

| Subcommand | Function | Purpose |
|------------|----------|---------|
| `check-install` | `cmd_check_install` | Verify graphify is importable, create output directory |
| `detect <path>` | `cmd_detect` | Detect files, output JSON with action decision fields |
| `book-prepare` | `cmd_book_prepare` | Split book into chunks, generate prompts, detect completed chunks |
| `merge-semantic` | `cmd_merge_semantic` | Collect chunk results, validate, cache, merge |
| `merge-all` | `cmd_merge_all` | Merge AST stub + semantic extraction results |
| `build <path>` | `cmd_build` | Build graph, cluster, analyze |
| `label <json>` | `cmd_label` | Apply community labels and regenerate report |
| `export [flags]` | `cmd_export` | Export HTML/SVG/Obsidian/Wiki |
| `finalize [path]` | `cmd_finalize` | Save manifest, update cost tracker, cleanup temp files |
| `path <A> <B>` | `cmd_path` | Shortest path between two nodes |
| `explain <node>` | `cmd_explain` | Plain-language explanation of a node |

## Book Pipeline Data Flow

```
detect --book
    |
book-prepare  (split book -> chunks, generate prompts, detect completed chunks)
    |
[LLM dispatch]  (read prompts, send to LLM, save chunk JSON results)
    |
merge-semantic  (collect chunk results, validate, merge)
    |
merge-all  (merge AST stub + semantic)
    |
build -> label -> export -> finalize
```

## Temp Files (`graphify-out/.graphify_*`)

Pipeline steps communicate through temp files under `graphify-out/`:

| File | Written by | Read by | Content |
|------|-----------|---------|---------| 
| `.graphify_detect.json` | `detect` | `build`, `finalize` | Detected file list and statistics |
| `.graphify_ast.json` | `book-prepare` | `merge-all` | Empty AST stub (book mode has no code) |
| `.graphify_prompt_N.txt` | `book-prepare` | LLM dispatch | Prompt for chunk N |
| `.graphify_chunk_N.json` | LLM dispatch | `merge-semantic` | Extraction result for chunk N |
| `.graphify_semantic.json` | `merge-semantic` | `merge-all` | Merged semantic extraction results |
| `.graphify_extract.json` | `merge-all` | `build`, `finalize` | Final merged extraction results |
| `.graphify_analysis.json` | `build` | `label`, `export` | Clustering, God nodes, Surprises |
| `.graphify_labels.json` | `label` | `export` | Community label mappings |

All `.graphify_*` temp files are cleaned up during the `finalize` step.

## Module Responsibilities

| Module | Function | Input -> Output |
|--------|----------|-----------------|
| `pipeline.py` | CLI subcommands | skill invocations -> structured JSON output + temp file management |
| `detect.py` | `detect(root)` | directory -> files dict + statistics |
| `split.py` | `split_book(path)` | book folder -> chunk files + metadata |
| `build.py` | `build_from_json(extraction)` | extraction dict -> `nx.Graph` |
| `cluster.py` | `cluster(G)` | graph -> `{community_id: [node_ids]}` |
| `analyze.py` | `god_nodes` / `surprising_connections` / `suggest_questions` | graph -> analysis dicts |
| `report.py` | `generate(G, ...)` | graph + analysis -> GRAPH_REPORT.md string |
| `export.py` | `to_json` / `to_html` / `to_obsidian` / `to_svg` / ... | graph -> multiple output formats |
| `cache.py` | `check_semantic_cache` / `save_semantic_cache` | files -> (cached, uncached) split |
| `security.py` | validation helpers | URL / path / label -> validated or raises |
| `validate.py` | `validate_extraction(data)` | extraction dict -> error list |
| `benchmark.py` | `run_benchmark(graph_path)` | graph file -> corpus vs subgraph token comparison |
| `wiki.py` | `to_wiki(G, ...)` | graph -> Agent-crawlable wiki pages |

## Extraction Output Schema

Every extractor returns:

```json
{
  "nodes": [
    {"id": "unique_string", "label": "human name", "type": "Claim|Evidence", "content": "summary text"}
  ],
  "edges": [
    {"source": "id_a", "target": "id_b", "relation": "supports|refines|conflicts", "confidence": "EXTRACTED|INFERRED|AMBIGUOUS"}
  ]
}
```

`validate.py` enforces this schema before `build_from_json()` consumes it.

## Confidence Labels

| Label | Meaning |
|-------|---------|
| `EXTRACTED` | Relationship is explicitly stated in the source text |
| `INFERRED` | Relationship is a reasonable deduction (e.g., co-occurrence in context) |
| `AMBIGUOUS` | Relationship is uncertain; flagged for human review in GRAPH_REPORT.md |

## Security

All external input passes through `graphify/security.py` before use:

- Graph file paths -> `validate_graph_path()` (must resolve inside `graphify-out/`)
- Node labels -> `sanitize_label()` (strips control chars, caps 256 chars, HTML-escapes)

See `SECURITY.md` for the full threat model.

## Testing

One test file per module under `tests/`. Run with:

```bash
pytest tests/ -q
```

All tests are pure unit tests - no network calls, no file system side effects outside `tmp_path`.
