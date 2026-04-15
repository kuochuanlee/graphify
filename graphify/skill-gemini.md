---
name: graphify
description: any input (code, docs, papers, images) -> knowledge graph -> clustered communities -> HTML + JSON + audit report
trigger: /graphify
---

# /graphify

Turn any folder of files into a navigable knowledge graph with community detection, an honest audit trail, and three outputs: interactive HTML, GraphRAG-ready JSON, and a plain-language GRAPH_REPORT.md.

## Usage

```
/graphify                                             # full pipeline on current directory
/graphify <path>                                      # full pipeline on specific path
/graphify <path> --mode deep                          # thorough extraction, richer INFERRED edges
/graphify <path> --update                             # incremental - re-extract only new/changed files
/graphify <path> --book                               # book mode - extract Claim/Evidence argumentation graph
/graphify <path> --book --with-images                  # book mode with multimodal image analysis (costs more tokens)
/graphify <path> --cluster-only                       # rerun clustering on existing graph
/graphify <path> --no-viz                             # skip visualization, just report + JSON
/graphify <path> --svg                                # also export graph.svg
/graphify <path> --graphml                            # export graph.graphml (Gephi, yEd)
/graphify <path> --neo4j                              # generate graphify-out/cypher.txt for Neo4j
/graphify <path> --neo4j-push bolt://localhost:7687   # push directly to Neo4j
/graphify <path> --mcp                                # start MCP stdio server
/graphify <path> --watch                              # auto-sync graph as files change
/graphify <path> --wiki                               # build agent-crawlable wiki
/graphify <path> --obsidian                           # also generate Obsidian vault (opt-in)
/graphify <path> --obsidian --obsidian-dir ~/vaults/x # write vault to custom path
/graphify add <url>                                   # fetch URL, save to ./raw, update graph
/graphify add <url> --author "Name"                   # tag who wrote it
/graphify add <url> --contributor "Name"              # tag who added it
/graphify query "<question>"                          # BFS traversal - broad context
/graphify query "<question>" --dfs                    # DFS - trace a specific path
/graphify query "<question>" --budget 1500            # cap at N tokens
/graphify path "AuthModule" "Database"                # shortest path between two concepts
/graphify explain "SwinTransformer"                   # plain-language explanation of a node
```

## What graphify is for

graphify is built around Andrej Karpathy's /raw folder workflow: drop anything into a folder - papers, tweets, screenshots, code, notes - and get a structured knowledge graph that shows you what you didn't know was connected.

Three things it does that an LLM alone cannot:
1. **Persistent graph** - relationships stored in `graphify-out/graph.json`, survive across sessions.
2. **Honest audit trail** - every edge tagged EXTRACTED, INFERRED, or AMBIGUOUS.
3. **Cross-document surprise** - community detection finds hidden connections between concepts in different files.

## What You Must Do When Invoked

If no path was given, use `.` (current directory). Do not ask the user for a path.

**Before running any steps**, check for these shortcut conditions:

- If `--book` flag is present OR the path contains a single large document: **Skip the steps below entirely.** Go to the "For --book (Book Mode)" section and follow those steps instead.

- If the only flag is `--mcp` AND `graphify-out/graph.json` exists: Run `python -m graphify.serve graphify-out/graph.json` and stop. Do not run the pipeline.

- If the only new flags are export-related (`--wiki`, `--obsidian`, `--svg`, `--graphml`) AND `graphify-out/graph.json` exists: Run `python -m graphify pipeline export [flags]` and stop. Do not run the pipeline.

Follow these steps in order. Do not skip steps. **Important:** Run each command separately. Do NOT use `&&` to combine commands (PowerShell 5 does not support it).

### Step 1 - Ensure graphify is installed

```
python -m graphify pipeline check-install
```

If it prints an error, tell the user and stop. Otherwise proceed silently.

### Step 2 - Detect files

```
python -m graphify pipeline detect INPUT_PATH
```

Replace INPUT_PATH with the actual path. Read the JSON output:

- If `action` is `"stop"`: tell the user "No supported files found in [path]" and stop.
- If `action` is `"ask_user"`: print the `confirmation_prompt` field and wait for the user's answer.
- If `action` is `"proceed"`: print the `summary` field and continue.
- If `skipped_count` > 0: mention how many files were skipped (do not show filenames).

### Step 3 - Extract entities and relationships

This step has two parallel tracks: **AST extraction** (deterministic, free) and **semantic extraction** (LLM, costs tokens). Run both in parallel where possible.

#### Part A - AST extraction for code files

```
python -m graphify pipeline ast-extract
```

#### Part B - Semantic extraction

**Fast path:** If the detect output showed `code_only: true`, skip Part B entirely and go to Part C.

**B0 - Check cache:**

```
python -m graphify pipeline cache-check
```

If `skip_semantic` is true in the output, go to Part C.

**B1 - Prepare chunks and prompts:**

```
python -m graphify pipeline prepare-semantic [--deep]
```

Add `--deep` if the original invocation used `--mode deep`. Read `total_chunks` from the JSON output.

**B2 - Dispatch:**

If `total_chunks` is 0, skip to Part C.

For each chunk from 1 to `total_chunks`, construct the following PowerShell command (replace `i` with the chunk number). Run ALL chunks concurrently in the background.

```powershell
Get-Content graphify-out\prompts\i.txt -Raw | gemini --yolo | Out-File -FilePath graphify-out\chunks\i.json -Encoding utf8
```

Wait for all background executions to complete before proceeding.
If a chunk fails with 429 (Too Many Requests), wait 30 seconds and retry once before reporting failure.

**B3 - Merge results:**

```
python -m graphify pipeline merge-semantic
```

If the output status says it failed, re-run only the failed chunks, then run merge-semantic again.

#### Part C - Merge AST + semantic

```
python -m graphify pipeline merge-all
```

### Step 4 - Build graph, cluster, analyze

```
python -m graphify pipeline build INPUT_PATH
```

If it exits with error (empty graph), stop and tell the user.

### Step 5 - Label communities

Read `graphify-out/.graphify_analysis.json`. For each community key, look at its node labels and assign a 2-5 word human-readable name (e.g. "Attention Mechanism", "Training Pipeline", "Data Loading").

Write the labels out to a file `graphify-out/labels_draft.json`

Then apply the labels:

```
python -m graphify pipeline label --from-file graphify-out/labels_draft.json --path INPUT_PATH
```

### Step 6-7 - Generate outputs

```
python -m graphify pipeline export [--obsidian] [--obsidian-dir DIR] [--svg] [--graphml] [--neo4j] [--neo4j-push URI] [--wiki] [--no-viz]
```

Pass through the same flags the user specified in the original invocation. HTML is generated by default unless `--no-viz`.

**If `--neo4j-push`:** ask the user for credentials (user, password) before running.

### Step 7d - MCP server (only if --mcp flag)

```
python -m graphify.serve graphify-out/graph.json
```

### Step 8 - Benchmark

```
python -m graphify pipeline benchmark
```

Print the output if it ran. Small corpora are skipped automatically.

### Step 9 - Finalize and report

```
python -m graphify pipeline finalize INPUT_PATH
```

**After finalize completes, stop. Do not retry any failed steps.**

Then tell the user (omit obsidian line unless --obsidian was given):

```
Graph complete. Outputs in graphify-out/

  graph.html            - interactive graph, open in browser
  GRAPH_REPORT.md       - audit report
  graph.json            - raw graph data
  obsidian/             - Obsidian vault (only if --obsidian)
```

Paste these sections from GRAPH_REPORT.md into the chat:
- God Nodes
- Surprising Connections
- Suggested Questions

Do NOT paste the full report - just those three sections.

Then pick the most interesting suggested question and ask:

> "The most interesting question this graph can answer: **[question]**. Want me to trace it?"

If the user says yes, use `/graphify query "[question]"` and walk them through the answer using the graph structure. End each reply with a natural follow-up so the session feels like navigation, not a one-shot report.

---

## For --update (incremental re-extraction)

```
python -m graphify pipeline update-detect INPUT_PATH
```

Read the JSON output:
- If `action` is `"stop"`: print the message and stop.
- If `code_only` is true: print "[graphify update] Code-only changes - skipping semantic extraction", run only ast-extract, skip Part B, then merge-all and continue to Steps 4-9.
- Otherwise: run the full Steps 3A-3C pipeline as normal.

After merge-all, merge into existing graph:

```
python -m graphify pipeline update-merge
```

Then proceed with Steps 4-9.

---

## For --cluster-only

```
python -m graphify pipeline cluster-only
```

Then run Steps 5-9 (label, export, benchmark, finalize).

---

## For --book (Book Mode)

Trigger: user runs `/graphify <book_folder> --book`, or detect result has `book_mode: true`.

Book mode processes natural language texts (books, long documents) and produces a Claim/Evidence argumentation graph instead of a code knowledge graph.

**Important:** All pipeline commands below use `--out-dir <book_folder>/graphify-out` to place outputs inside the book folder.

Follow these steps in order:

### Book Step 1 - Detect

```
python -m graphify pipeline --out-dir <book_folder>/graphify-out detect --book <book_folder>/
```

Read the JSON output and confirm `book_mode` is true. If not, fall back to the normal pipeline.

### Book Step 2 - Prepare chunks and prompts

```
python -m graphify pipeline --out-dir <book_folder>/graphify-out book-prepare
```

Produces: chunk files in `book_chunks/`, prompt files, and an empty AST stub. Read the JSON output:
- `total_chunks`: total number of chunks
- `completed_chunks`: chunks with valid results from a previous run (already done)
- `remaining_chunks`: chunks that still need LLM processing

If `remaining_chunks` is empty, all chunks are already done - skip Book Step 3 and go directly to Book Step 4.

### Book Step 3 - Semantic extraction (LLM step - you handle this)

Only process chunks listed in `remaining_chunks` (not all chunks).

For each chunk index `i` in `remaining_chunks`:

1. Read the prompt file: `<book_folder>/graphify-out/.graphify_prompt_<i>.txt`
2. Send the prompt text to the LLM
3. Save the raw JSON response to `<book_folder>/graphify-out/.graphify_chunk_<i>.json`

**Only if `--with-images` was specified:** Before sending each prompt, check the METADATA header for an "Images in this chunk:" line. If images are listed, include those image files (paths relative to the book folder) together with the prompt for multimodal analysis. Without `--with-images`, ignore image references and send text only.

Parallelism: process up to 5 chunks concurrently. If a chunk fails with 429, wait 30 seconds and retry once.

Schema constraints for each chunk JSON response:
- `nodes[].type`: only `"Claim"` or `"Evidence"`
- `edges[].type`: only `"supports"`, `"refines"`, or `"conflicts"`
- Must include: `{"nodes": [...], "edges": [...], "hyperedges": []}`

### Book Step 4 - Merge semantic results

```
python -m graphify pipeline --out-dir <book_folder>/graphify-out merge-semantic
```

If the output status says it failed, re-run only the failed chunks, then run merge-semantic again.

### Book Step 5 - Merge all

```
python -m graphify pipeline --out-dir <book_folder>/graphify-out merge-all
```

### Book Step 6 - Build graph, cluster, analyze

```
python -m graphify pipeline --out-dir <book_folder>/graphify-out build <book_folder>/
```

If it exits with error (empty graph), stop and tell the user.

### Book Step 7 - Label communities (LLM step - you handle this)

Read `<book_folder>/graphify-out/.graphify_analysis.json`. For each community key, look at its node labels and assign a 2-5 word human-readable name (e.g. "Moore's Law Evidence", "Computational Limits", "Neural Architecture Claims").

Write the labels to `<book_folder>/graphify-out/labels_draft.json`, then apply:

```
python -m graphify pipeline --out-dir <book_folder>/graphify-out label --from-file <book_folder>/graphify-out/labels_draft.json --path <book_folder>/
```

### Book Step 8 - Export

```
python -m graphify pipeline --out-dir <book_folder>/graphify-out export --obsidian --wiki
```

Book mode always generates Obsidian vault and wiki by default. Add other flags (`--svg`, `--graphml`) if the user requested them.

### Book Step 9 - Finalize

```
python -m graphify pipeline --out-dir <book_folder>/graphify-out finalize <book_folder>/
```

**After finalize completes, stop. Do not retry any failed steps.**

Then tell the user:

```
Book graph complete. Outputs in <book_folder>/graphify-out/

  graph.html            - interactive argumentation graph, open in browser
  GRAPH_REPORT.md       - audit report
  graph.json            - raw graph data (Claim/Evidence nodes)
  obsidian/             - Obsidian vault
  wiki/                 - agent-crawlable wiki
```

Paste these sections from GRAPH_REPORT.md into the chat:
- God Nodes
- Surprising Connections
- Suggested Questions

---

## For /graphify query

If the question contains non-English terms, translate the key concepts to English before running the query. For example, "執行流程" → "pipeline execution flow", "錯誤處理" → "error handling". The graph nodes are in English so the query keywords must be English to get matches.

```
graphify query "QUESTION" [--dfs] [--budget N]
```

Use `--dfs` for "how does X reach Y?" questions. Use default BFS for "what connects to X?" questions.

Answer using **only** what the graph contains. If the graph lacks information, say so - do not hallucinate.

After writing the answer, save it:

```
graphify save-result --question "QUESTION" --answer "ANSWER" --type query --nodes NODE1 NODE2
```

---

## For /graphify path

```
python -m graphify pipeline path "NODE_A" "NODE_B"
```

Explain the path in plain language - what each hop means, why it's significant. Then save:

```
graphify save-result --question "Path from NODE_A to NODE_B" --answer "ANSWER" --type path_query --nodes NODE_A NODE_B
```

---

## For /graphify explain

```
python -m graphify pipeline explain "NODE_NAME"
```

Write a 3-5 sentence explanation of what this node is, what it connects to, and why those connections are significant. Then save:

```
graphify save-result --question "Explain NODE_NAME" --answer "ANSWER" --type explain --nodes NODE_NAME
```

---

## For /graphify add

```
python -m graphify pipeline add URL [--author "Name"] [--contributor "Name"]
```

If successful, automatically run the `--update` pipeline on `./raw`.

---

## For --watch

```
python -m graphify.watch INPUT_PATH --debounce 3
```

- Code file changes: auto-rebuild (no LLM needed).
- Doc/image changes: writes a flag, notifies you to run `/graphify --update`.

---

## For git hooks

```
graphify hook install     # install post-commit/post-checkout hooks
graphify hook uninstall   # remove hooks
graphify hook status      # check status
```

---

## For GEMINI.md integration

```
graphify gemini install   # write graphify section to GEMINI.md
graphify gemini uninstall # remove section
```

---

## Honesty Rules

- Never invent an edge. If unsure, use AMBIGUOUS.
- Never skip the corpus check warning.
- Always show token cost in the report.
- Never hide cohesion scores behind symbols - show the raw number.
- Never run HTML viz on graphs with more than 5,000 nodes without warning the user.
