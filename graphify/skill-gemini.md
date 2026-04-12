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

For each chunk from 1 to `total_chunks`, construct the command below (replace `i` with the actual number). Run ALL chunks in a parallel bash block.

```bash
gemini --yolo -p "$(cat graphify-out/.graphify_prompt_i.txt)" > graphify-out/.graphify_chunk_i.json &
# ... repeat for i=2, i=3 ...
wait
```

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

## For /graphify query

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
