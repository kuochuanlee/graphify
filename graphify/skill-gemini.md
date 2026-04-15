---
name: graphify
description: natural language texts (books, papers, docs) -> Claim/Evidence argumentation graph -> clustered communities -> HTML + JSON + audit report
trigger: /graphify
---

# /graphify

Turn any collection of natural language texts (books, papers, long documents) into a navigable Claim/Evidence argumentation graph with community detection, an honest audit trail, and structured outputs: interactive HTML, GraphRAG-ready JSON, Obsidian vault, and a plain-language GRAPH_REPORT.md.

## Usage

```
/graphify <book_folder>                              # full pipeline on book folder
/graphify <book_folder> --with-images                # multimodal image analysis (costs more tokens)
/graphify <book_folder> --no-viz                     # skip visualization, just report + JSON
/graphify <book_folder> --svg                        # also export graph.svg
/graphify <book_folder> --graphml                    # export graph.graphml (Gephi, yEd)
/graphify <book_folder> --obsidian                   # generate Obsidian vault (on by default for book mode)
/graphify <book_folder> --obsidian --obsidian-dir ~/vaults/x  # write vault to custom path
/graphify <book_folder> --wiki                       # build agent-crawlable wiki (on by default for book mode)
/graphify query "<question>"                         # BFS traversal - broad context
/graphify query "<question>" --dfs                   # DFS - trace a specific path
/graphify query "<question>" --budget 1500           # cap at N tokens
/graphify path "NodeA" "NodeB"                       # shortest path between two concepts
/graphify explain "SwinTransformer"                  # plain-language explanation of a node
```

## What graphify is for

graphify processes natural language texts and produces a structured Claim/Evidence argumentation graph that reveals the logical structure of arguments across documents.

Three things it does that an LLM alone cannot:
1. **Persistent graph** - relationships stored in `graphify-out/graph.json`, survive across sessions.
2. **Honest audit trail** - every edge tagged EXTRACTED, INFERRED, or AMBIGUOUS.
3. **Cross-document surprise** - community detection finds hidden connections between concepts in different files.

## What You Must Do When Invoked

**Before running any steps**, check for these shortcut conditions:

- If the only new flags are export-related (`--wiki`, `--obsidian`, `--svg`, `--graphml`) AND `<book_folder>/graphify-out/graph.json` exists: Run `python -m graphify pipeline --out-dir <book_folder>/graphify-out export [flags]` and stop. Do not run the pipeline.

**Important:** Run each command separately. Do NOT use `&&` to combine commands (PowerShell 5 does not support it).

**Important:** All pipeline commands below use `--out-dir <book_folder>/graphify-out` to place outputs inside the book folder.

Follow these steps in order:

### Step 1 - Detect

```
python -m graphify pipeline --out-dir <book_folder>/graphify-out detect --book <book_folder>/
```

Read the JSON output to confirm detection succeeded.

### Step 2 - Prepare chunks and prompts

```
python -m graphify pipeline --out-dir <book_folder>/graphify-out book-prepare
```

Produces: chunk files in `book_chunks/`, prompt files, and an empty AST stub. Read the JSON output:
- `total_chunks`: total number of chunks
- `completed_chunks`: chunks with valid results from a previous run (already done)
- `remaining_chunks`: chunks that still need LLM processing

If `remaining_chunks` is empty, all chunks are already done - skip Step 3 and go directly to Step 4.

### Step 3 - Semantic extraction (LLM step - you handle this)

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

### Step 4 - Merge semantic results

```
python -m graphify pipeline --out-dir <book_folder>/graphify-out merge-semantic
```

If the output status says it failed, re-run only the failed chunks, then run merge-semantic again.

### Step 5 - Merge all

```
python -m graphify pipeline --out-dir <book_folder>/graphify-out merge-all
```

### Step 6 - Build graph, cluster, analyze

```
python -m graphify pipeline --out-dir <book_folder>/graphify-out build <book_folder>/
```

If it exits with error (empty graph), stop and tell the user.

### Step 7 - Label communities (LLM step - you handle this)

Read `<book_folder>/graphify-out/.graphify_analysis.json`. For each community key, look at its node labels and assign a 2-5 word human-readable name (e.g. "Moore's Law Evidence", "Computational Limits", "Neural Architecture Claims").

Write the labels to `<book_folder>/graphify-out/labels_draft.json`, then apply:

```
python -m graphify pipeline --out-dir <book_folder>/graphify-out label --from-file <book_folder>/graphify-out/labels_draft.json --path <book_folder>/
```

### Step 8 - Export

```
python -m graphify pipeline --out-dir <book_folder>/graphify-out export --obsidian --wiki
```

Book mode always generates Obsidian vault and wiki by default. Add other flags (`--svg`, `--graphml`) if the user requested them.

### Step 9 - Finalize

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

Do NOT paste the full report - just those three sections.

Then pick the most interesting suggested question and ask:

> "The most interesting question this graph can answer: **[question]**. Want me to trace it?"

If the user says yes, use `/graphify query "[question]"` and walk them through the answer using the graph structure. End each reply with a natural follow-up so the session feels like navigation, not a one-shot report.

---

## For /graphify query

If the question contains non-English terms, translate the key concepts to English before running the query. For example, "Moore's Law" stays as is, but CJK terms need translation. The graph nodes are in English so the query keywords must be English to get matches.

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

## Honesty Rules

- Never invent an edge. If unsure, use AMBIGUOUS.
- Never skip the corpus check warning.
- Always show token cost in the report.
- Never hide cohesion scores behind symbols - show the raw number.
- Never run HTML viz on graphs with more than 5,000 nodes without warning the user.
