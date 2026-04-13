# Architecture

graphify is a three-layer architecture: **Skill** (LLM instructions) → **Pipeline** (CLI wrapper) → **Library** (core functions).

- **Skill** (`skill-gemini.md` / `skill-gemini.tw.md`): Operation manual for LLMs, defines the invocation sequence
- **Pipeline** (`pipeline.py`): CLI subcommand layer, encapsulates decision logic and temp file management
- **Library** (`detect.py`, `extract.py`, `build.py`, ...): Pure functions, can be used standalone

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
| `ast-extract` | `cmd_ast_extract` | AST structured extraction for code files |
| `cache-check` | `cmd_cache_check` | Check semantic extraction cache |
| `prepare-semantic` | `cmd_prepare_semantic` | Split uncached files into chunks and generate prompt files |
| `merge-semantic` | `cmd_merge_semantic` | Collect chunk results, validate, cache, merge |
| `merge-all` | `cmd_merge_all` | Merge AST + semantic extraction results |
| `build <path>` | `cmd_build` | Build graph, cluster, analyze |
| `label <json>` | `cmd_label` | Apply community labels and regenerate report |
| `export [flags]` | `cmd_export` | Export HTML/SVG/Obsidian/Neo4j/Wiki |
| `benchmark` | `cmd_benchmark` | Token compression ratio benchmark |
| `finalize [path]` | `cmd_finalize` | Save manifest, update cost tracker, cleanup temp files |
| `update-detect <path>` | `cmd_update_detect` | Detect files changed since last run |
| `update-merge` | `cmd_update_merge` | Merge new extraction results into existing graph |
| `cluster-only` | `cmd_cluster_only` | Re-cluster existing graph without re-extracting |
| `path <A> <B>` | `cmd_path` | Shortest path between two nodes |
| `explain <node>` | `cmd_explain` | Plain-language explanation of a node |
| `add <url>` | `cmd_add` | Fetch URL, save to corpus |

## Full Pipeline Data Flow

```
detect → ast-extract ─────────────────────────────┐
     └→ cache-check → prepare-semantic → [LLM dispatch] → merge-semantic ─┤
                                                                          ↓
                                                                     merge-all
                                                                          ↓
                                                          build → label → export → benchmark → finalize
```

## Incremental Update (--update) Data Flow

```
update-detect
    ↓  writes .graphify_detect.json (new files only) + .graphify_incremental.json (full result)
ast-extract / cache-check / prepare-semantic / merge-semantic / merge-all
    ↓  extraction steps process only changed files
update-merge
    ↓  merges new extraction + existing graph, restores .graphify_extract.json and .graphify_detect.json to full data
build → label → export → benchmark → finalize
```

Design pattern: **narrow scope → extract → restore scope**. `update-detect` narrows `.graphify_detect.json` to new files only, so mid-stage extraction steps naturally process only the changed subset; `update-merge` restores full data after merging, ensuring downstream steps (build/finalize) receive the correct complete dataset.

## Temp Files (`graphify-out/.graphify_*`)

Pipeline steps communicate through temp files under `graphify-out/`:

| File | Written by | Read by | Content |
|------|-----------|---------|---------|
| `.graphify_detect.json` | `detect` / `update-detect` / `update-merge` | `ast-extract`, `cache-check`, `build`, `finalize` | Detected file list and statistics |
| `.graphify_incremental.json` | `update-detect` | `update-merge` | Full incremental detection result (includes new_files, deleted_files) |
| `.graphify_ast.json` | `ast-extract` | `merge-all` | AST-extracted nodes/edges |
| `.graphify_uncached.txt` | `cache-check` | `prepare-semantic` | List of uncached files |
| `.graphify_cached.json` | `cache-check` | `merge-semantic` | Nodes/edges loaded from cache |
| `.graphify_prompt_N.txt` | `prepare-semantic` | LLM dispatch | Prompt for chunk N |
| `.graphify_chunk_N.json` | LLM dispatch | `merge-semantic` | Extraction result for chunk N |
| `.graphify_semantic.json` | `merge-semantic` | `merge-all` | Merged semantic extraction results |
| `.graphify_extract.json` | `merge-all` / `update-merge` | `build`, `finalize` | Final merged extraction results |
| `.graphify_analysis.json` | `build` | `label`, `export` | Clustering, God nodes, Surprises |
| `.graphify_labels.json` | `label` | `export` | Community label mappings |

All `.graphify_*` temp files are cleaned up during the `finalize` step.

## Module Responsibilities

| Module | Function | Input → Output |
|--------|----------|----------------|
| `pipeline.py` | CLI subcommands | skill invocations → structured JSON output + temp file management |
| `detect.py` | `detect(root)` / `detect_incremental(root)` | directory → files dict + statistics |
| `extract.py` | `extract(paths)` | file paths → `{nodes, edges}` dict |
| `build.py` | `build_from_json(extraction)` | extraction dict → `nx.Graph` |
| `cluster.py` | `cluster(G)` | graph → `{community_id: [node_ids]}` |
| `analyze.py` | `god_nodes` / `surprising_connections` / `suggest_questions` | graph → analysis dicts |
| `report.py` | `generate(G, ...)` | graph + analysis → GRAPH_REPORT.md string |
| `export.py` | `to_json` / `to_html` / `to_obsidian` / `to_svg` / ... | graph → multiple output formats |
| `ingest.py` | `ingest(url, ...)` | URL → file saved to corpus dir |
| `cache.py` | `check_semantic_cache` / `save_semantic_cache` | files → (cached, uncached) split |
| `security.py` | validation helpers | URL / path / label → validated or raises |
| `validate.py` | `validate_extraction(data)` | extraction dict → error list |
| `serve.py` | MCP stdio server | graph file path → MCP tools for external AI clients |
| `watch.py` | `watch(root, ...)` | directory → writes flag file on change |
| `benchmark.py` | `run_benchmark(graph_path)` | graph file → corpus vs subgraph token comparison |
| `wiki.py` | `to_wiki(G, ...)` | graph → Agent-crawlable wiki pages |

## Extraction Output Schema

Every extractor returns:

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

`validate.py` enforces this schema before `build_from_json()` consumes it.

## Confidence Labels

| Label | Meaning |
|-------|---------|
| `EXTRACTED` | Relationship is explicitly stated in the source (e.g., an import statement, a direct call) |
| `INFERRED` | Relationship is a reasonable deduction (e.g., call-graph second pass, co-occurrence in context) |
| `AMBIGUOUS` | Relationship is uncertain; flagged for human review in GRAPH_REPORT.md |

## Adding a New Language Extractor

1. Add a `extract_<lang>(path: Path) -> dict` function in `extract.py` following the existing pattern (tree-sitter parse → walk nodes → collect `nodes` and `edges` → call-graph second pass for INFERRED `calls` edges).
2. Register the file suffix in `extract()` dispatch and `collect_files()`.
3. Add the suffix to `CODE_EXTENSIONS` in `detect.py` and `_WATCHED_EXTENSIONS` in `watch.py`.
4. Add the tree-sitter package to `pyproject.toml` dependencies.
5. Add a fixture file to `tests/fixtures/` and tests to `tests/test_languages.py`.

## Security

All external input passes through `graphify/security.py` before use:

- URLs → `validate_url()` (http/https only) + `_NoFileRedirectHandler` (blocks file:// redirects)
- Fetched content → `safe_fetch()` / `safe_fetch_text()` (size cap, timeout)
- Graph file paths → `validate_graph_path()` (must resolve inside `graphify-out/`)
- Node labels → `sanitize_label()` (strips control chars, caps 256 chars, HTML-escapes)

See `SECURITY.md` for the full threat model.

## Testing

One test file per module under `tests/`. Run with:

```bash
pytest tests/ -q
```

All tests are pure unit tests - no network calls, no file system side effects outside `tmp_path`.
