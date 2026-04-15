# graphify (Book Mode)

[English](README.md) | [繁體中文](README.tw.md)

**An AI-assisted book analysis tool.** Type `/graphify <book_folder>` in Gemini CLI - it reads your book/document files, builds a Claim/Evidence argumentation graph, and reveals the logical structure you didn't know was there. Understand complex arguments faster. Find hidden connections between ideas across chapters.

> Drop any collection of natural language texts - books, papers, long documents - into a folder, and get a structured argumentation graph that shows claims, evidence, and how they connect.

```
/graphify ./my-book                # analyze a book folder
```

```
graphify-out/
+-- graph.html       interactive argumentation graph - click nodes, search, filter by community
+-- GRAPH_REPORT.md  god nodes, surprising connections, suggested questions
+-- graph.json       persistent graph - query later without re-reading
+-- obsidian/        Obsidian vault for navigating the knowledge structure
+-- wiki/            agent-crawlable wiki articles per community
```

## How it works

graphify splits book content into manageable chunks, then uses LLM semantic extraction to identify Claims and Evidence from the text. Each chunk is analyzed for argumentation structure - what claims are being made, what evidence supports them, and how arguments refine or conflict with each other. The results are merged into a NetworkX graph, clustered with Leiden community detection, and exported as interactive HTML, queryable JSON, Obsidian vault, and a plain-language audit report.

**Clustering is graph-topology-based - no embeddings.** Leiden finds communities by edge density. The graph structure is the similarity signal - no separate embedding step or vector database needed.

Every relationship is tagged `EXTRACTED` (found directly in source), `INFERRED` (reasonable inference), or `AMBIGUOUS` (flagged for review). You always know what was found vs guessed.

## Install

**Requires:** Python 3.10+ and [Gemini CLI](https://github.com/google-gemini/gemini-cli)

```bash
pip install graphifyy
```

> The PyPI package is temporarily named `graphifyy` while the `graphify` name is being reclaimed. The CLI command is still `graphify`.

Then install the skill for Gemini CLI:

```bash
graphify install --platform gemini
```

## Usage

```
/graphify <book_folder>                              # full pipeline on book folder
/graphify <book_folder> --with-images                # with multimodal image analysis (costs more tokens)
/graphify <book_folder> --no-viz                     # skip visualization, just report + JSON
/graphify <book_folder> --svg                        # also export graph.svg
/graphify <book_folder> --graphml                    # export graph.graphml (Gephi, yEd)
/graphify <book_folder> --obsidian                   # Obsidian vault (on by default)
/graphify <book_folder> --wiki                       # agent-crawlable wiki (on by default)

/graphify query "<question>"                         # BFS traversal - broad context
/graphify query "<question>" --dfs                   # DFS - trace a specific path
/graphify query "<question>" --budget 1500           # cap at N tokens
/graphify path "NodeA" "NodeB"                       # shortest path between two concepts
/graphify explain "ConceptName"                      # plain-language explanation of a node
```

## What you get

**God nodes** - highest-degree concepts (what everything connects through)

**Surprising connections** - ranked by composite score. Cross-chapter edges rank higher. Each result includes a plain-language why.

**Suggested questions** - 4-5 questions the graph is uniquely positioned to answer

**Claim/Evidence structure** - nodes are typed as `Claim` or `Evidence`, edges as `supports`, `refines`, or `conflicts`. The graph reveals the argumentation skeleton of the entire book.

**Confidence scores** - every INFERRED edge has a `confidence_score` (0.0-1.0). You know not just what was guessed but how confident the model was.

**Resumable pipeline** - if extraction is interrupted, re-running picks up where it left off. Already-processed chunks are detected and skipped automatically.

## Privacy

graphify sends text content to your LLM provider (via Gemini CLI) for semantic extraction. No telemetry, usage tracking, or analytics of any kind. The only network calls are to your configured model API during extraction.

## Tech stack

NetworkX + Leiden (graspologic) + vis.js. Semantic extraction via Gemini. No server, runs entirely locally.

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for module responsibilities and pipeline data flow.
