# MCP stdio server - exposes graph query tools to Claude and other agents
from __future__ import annotations
import json
import sys
import subprocess
from pathlib import Path
import networkx as nx
from networkx.readwrite import json_graph
from graphify.security import validate_graph_path, sanitize_label


def _load_graph(graph_path: str) -> nx.Graph:
    try:
        safe = validate_graph_path(graph_path)
        data = json.loads(safe.read_text())
        try:
            return json_graph.node_link_graph(data, edges="links")
        except TypeError:
            return json_graph.node_link_graph(data)
    except (ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(f"error: graph.json is corrupted ({exc}). Re-run /graphify to rebuild.", file=sys.stderr)
        sys.exit(1)


def _communities_from_graph(G: nx.Graph) -> dict[int, list[str]]:
    """Reconstruct community dict from community property stored on nodes."""
    communities: dict[int, list[str]] = {}
    for node_id, data in G.nodes(data=True):
        cid = data.get("community")
        if cid is not None:
            communities.setdefault(int(cid), []).append(node_id)
    return communities


def _score_nodes(G: nx.Graph, terms: list[str]) -> list[tuple[float, str]]:
    scored = []
    for nid, data in G.nodes(data=True):
        label = data.get("label", "").lower()
        source = data.get("source_file", "").lower()
        score = sum(1 for t in terms if t in label) + sum(0.5 for t in terms if t in source)
        if score > 0:
            scored.append((score, nid))
    return sorted(scored, reverse=True)


def _bfs(G: nx.Graph, start_nodes: list[str], depth: int) -> tuple[set[str], list[tuple]]:
    visited: set[str] = set(start_nodes)
    frontier = set(start_nodes)
    edges_seen: list[tuple] = []
    for _ in range(depth):
        next_frontier: set[str] = set()
        for n in frontier:
            for neighbor in G.neighbors(n):
                if neighbor not in visited:
                    next_frontier.add(neighbor)
                    edges_seen.append((n, neighbor))
        visited.update(next_frontier)
        frontier = next_frontier
    return visited, edges_seen


def _dfs(G: nx.Graph, start_nodes: list[str], depth: int) -> tuple[set[str], list[tuple]]:
    visited: set[str] = set()
    edges_seen: list[tuple] = []
    stack = [(n, 0) for n in reversed(start_nodes)]
    while stack:
        node, d = stack.pop()
        if node in visited or d > depth:
            continue
        visited.add(node)
        for neighbor in G.neighbors(node):
            if neighbor not in visited:
                stack.append((neighbor, d + 1))
                edges_seen.append((node, neighbor))
    return visited, edges_seen


def _subgraph_to_text(G: nx.Graph, nodes: set[str], edges: list[tuple], token_budget: int = 2000) -> str:
    """Render subgraph as text, cutting at token_budget (approx 3 chars/token)."""
    char_budget = token_budget * 3
    lines = []
    for nid in sorted(nodes, key=lambda n: G.degree[n], reverse=True):
        d = G.nodes[nid]
        line = f"NODE {sanitize_label(d.get('label', nid))} [src={d.get('source_file', '')} loc={d.get('source_location', '')} community={d.get('community', '')}]"
        lines.append(line)
    for u, v in edges:
        if u in nodes and v in nodes:
            d = G.edges[u, v]
            line = f"EDGE {sanitize_label(G.nodes[u].get('label', u))} --{d.get('relation', '')} [{d.get('confidence', '')}]--> {sanitize_label(G.nodes[v].get('label', v))}"
            lines.append(line)
    output = "\n".join(lines)
    if len(output) > char_budget:
        output = output[:char_budget] + f"\n... (truncated to ~{token_budget} token budget)"
    return output


def _find_node(G: nx.Graph, label: str) -> list[str]:
    """Return node IDs whose label or ID matches the search term (case-insensitive)."""
    term = label.lower()
    return [nid for nid, d in G.nodes(data=True)
            if term in d.get("label", "").lower() or term == nid.lower()]


def serve(graph_path: str = "graphify-out/graph.json") -> None:
    """Start the MCP server. Requires pip install mcp."""
    # Allow overriding graph_path via command line argument
    if len(sys.argv) > 1:
        graph_path = sys.argv[1]
    try:
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
        from mcp import types
    except ImportError as e:
        raise ImportError("mcp not installed. Run: pip install mcp") from e

    # 從 graph_path 推導出專案根目錄（graphify-out/ 的上層）
    # 這樣 git 工具就知道要對哪個 repo 執行，read_file 也有安全邊界
    _graph_file = Path(graph_path).resolve()
    _project_root = _graph_file.parent.parent
    print(f"[graphify] Serving graph: {_graph_file}", file=sys.stderr)
    print(f"[graphify] Project root: {_project_root}", file=sys.stderr)

    G = _load_graph(graph_path)
    communities = _communities_from_graph(G)

    server = Server("graphify")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="query_graph",
                description="Search the knowledge graph using BFS or DFS. Returns relevant nodes and edges as text context.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "question": {"type": "string", "description": "Natural language question or keyword search"},
                        "mode": {"type": "string", "enum": ["bfs", "dfs"], "default": "bfs",
                                 "description": "bfs=broad context, dfs=trace a specific path"},
                        "depth": {"type": "integer", "default": 3, "description": "Traversal depth (1-6)"},
                        "token_budget": {"type": "integer", "default": 2000, "description": "Max output tokens"},
                    },
                    "required": ["question"],
                },
            ),
            types.Tool(
                name="get_node",
                description="Get full details for a specific node by label or ID.",
                inputSchema={
                    "type": "object",
                    "properties": {"label": {"type": "string", "description": "Node label or ID to look up"}},
                    "required": ["label"],
                },
            ),
            types.Tool(
                name="get_neighbors",
                description="Get all direct neighbors of a node with edge details.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "relation_filter": {"type": "string", "description": "Optional: filter by relation type"},
                    },
                    "required": ["label"],
                },
            ),
            types.Tool(
                name="get_community",
                description="Get all nodes in a community by community ID.",
                inputSchema={
                    "type": "object",
                    "properties": {"community_id": {"type": "integer", "description": "Community ID (0-indexed by size)"}},
                    "required": ["community_id"],
                },
            ),
            types.Tool(
                name="god_nodes",
                description="Return the most connected nodes - the core abstractions of the knowledge graph.",
                inputSchema={"type": "object", "properties": {"top_n": {"type": "integer", "default": 10}}},
            ),
            types.Tool(
                name="graph_stats",
                description="Return summary statistics: node count, edge count, communities, confidence breakdown.",
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name="shortest_path",
                description="Find the shortest path between two concepts in the knowledge graph.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "source": {"type": "string", "description": "Source concept label or keyword"},
                        "target": {"type": "string", "description": "Target concept label or keyword"},
                        "max_hops": {"type": "integer", "default": 8, "description": "Maximum hops to consider"},
                    },
                    "required": ["source", "target"],
                },
            ),
            types.Tool(
                name="git_status",
                description="Get the status of the current git repository (short format). Shows modified, added, and deleted files.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "repo_path": {"type": "string", "default": ".", "description": "Optional repository path (default is current directory)."}
                    }
                },
            ),
            types.Tool(
                name="git_diff",
                description="Get the git diff for specific files or the entire repository. Use to review exact code changes.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "repo_path": {"type": "string", "default": ".", "description": "Optional repository path."},
                        "target": {"type": "string", "description": "Optional specific file or directory path to diff. If omitted, shows all changes."},
                        "staged": {"type": "boolean", "default": False, "description": "If true, shows staged changes (git diff --staged)."}
                    }
                },
            ),
            types.Tool(
                name="read_file",
                description="Read the contents of a specific file in the repository.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Absolute or relative path to the file to read."},
                        "start_line": {"type": "integer", "description": "Optional starting line number (1-indexed)."},
                        "end_line": {"type": "integer", "description": "Optional ending line number (inclusive)."}
                    },
                    "required": ["file_path"],
                },
            ),
            types.Tool(
                name="list_directory",
                description=(
                    "Generate a file tree of the project directory. "
                    "By default lists all tracked files (respects .gitignore via git ls-files). "
                    "Falls back to plain filesystem walk if git is unavailable. "
                    "Use this to understand the project structure before reading files."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "subdir": {
                            "type": "string",
                            "description": "Optional sub-directory path relative to project root (e.g. 'src'). Defaults to project root."
                        },
                        "max_depth": {
                            "type": "integer",
                            "default": 5,
                            "description": "Maximum directory depth to display (1-10). Default is 5."
                        },
                        "show_hidden": {
                            "type": "boolean",
                            "default": False,
                            "description": "If true, includes hidden files/dirs (starting with '.'). Default is false."
                        }
                    }
                },
            ),
            types.Tool(
                name="write_file",
                description=(
                    "Write full content to a file in the project. "
                    "Creates the file (and any missing parent directories) if it does not exist, "
                    "or overwrites it completely if it does. "
                    "Best for creating new files or fully replacing small files. "
                    "For partial edits to existing files, prefer edit_file instead. "
                    "Relative paths are resolved from the project root. "
                    "Writes are restricted to the project directory; .git/ is always blocked.\n"
                    "IMPORTANT: There is NO delete or rename tool available. "
                    "If you need to delete or rename a file, DO NOT overwrite it with empty content. "
                    "Instead, advise the user in your text response to do it manually."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to the file to write. Relative paths resolve from project root."
                        },
                        "content": {
                            "type": "string",
                            "description": "Full UTF-8 text content to write to the file."
                        }
                    },
                    "required": ["file_path", "content"],
                },
            ),
            types.Tool(
                name="edit_file",
                description=(
                    "Edit an existing file. Supports three modes:\n"
                    "1. SEARCH-REPLACE (default): Provide old_content and new_content. "
                    "Exact match is tried first, then normalized whitespace fallback. "
                    "Use start_line/end_line to narrow scope if needed.\n"
                    "2. INSERT: Set old_content to empty string and provide start_line. "
                    "new_content is inserted BEFORE that line.\n"
                    "3. RANGE-REPLACE: Set replace_range=true with start_line and end_line. "
                    "The entire line range is replaced with new_content. "
                    "old_content is used as a short verification anchor (must exist in the range) "
                    "to prevent accidental overwrites -- just provide a distinctive line, not the full block.\n"
                    "Always call read_file first to confirm line numbers. "
                    "Relative paths are resolved from the project root. "
                    "Edits are restricted to the project directory; .git/ is always blocked.\n"
                    "IMPORTANT: There is NO delete or rename tool available. "
                    "If you need to delete or rename a file, advise the user in your text response to do it manually."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to the file to edit. Relative paths resolve from project root."
                        },
                        "old_content": {
                            "type": "string",
                            "description": "Text to find and replace. Empty string triggers INSERT mode (requires start_line). In RANGE-REPLACE mode, acts as a short verification anchor."
                        },
                        "new_content": {
                            "type": "string",
                            "description": "Replacement text, or text to insert."
                        },
                        "start_line": {
                            "type": "integer",
                            "description": "1-indexed start line. Narrows search scope, or defines insert/range-replace position."
                        },
                        "end_line": {
                            "type": "integer",
                            "description": "1-indexed end line (inclusive). Narrows search scope, or defines range-replace boundary."
                        },
                        "replace_range": {
                            "type": "boolean",
                            "default": False,
                            "description": "If true, replaces the entire start_line-end_line range with new_content. old_content becomes a verification anchor only, saving tokens."
                        }
                    },
                    "required": ["file_path", "old_content", "new_content"],
                },
            ),
        ]

    def _tool_query_graph(arguments: dict) -> str:
        question = arguments["question"]
        mode = arguments.get("mode", "bfs")
        depth = min(int(arguments.get("depth", 3)), 6)
        budget = int(arguments.get("token_budget", 2000))
        terms = [t.lower() for t in question.split() if len(t) > 2]
        scored = _score_nodes(G, terms)
        start_nodes = [nid for _, nid in scored[:3]]
        if not start_nodes:
            return "No matching nodes found."
        nodes, edges = _dfs(G, start_nodes, depth) if mode == "dfs" else _bfs(G, start_nodes, depth)
        header = f"Traversal: {mode.upper()} depth={depth} | Start: {[G.nodes[n].get('label', n) for n in start_nodes]} | {len(nodes)} nodes found\n\n"
        return header + _subgraph_to_text(G, nodes, edges, budget)

    def _tool_get_node(arguments: dict) -> str:
        label = arguments["label"].lower()
        matches = [(nid, d) for nid, d in G.nodes(data=True)
                   if label in d.get("label", "").lower() or label == nid.lower()]
        if not matches:
            return f"No node matching '{label}' found."
        nid, d = matches[0]
        return "\n".join([
            f"Node: {d.get('label', nid)}",
            f"  ID: {nid}",
            f"  Source: {d.get('source_file', '')} {d.get('source_location', '')}",
            f"  Type: {d.get('file_type', '')}",
            f"  Community: {d.get('community', '')}",
            f"  Degree: {G.degree[nid]}",
        ])

    def _tool_get_neighbors(arguments: dict) -> str:
        label = arguments["label"].lower()
        rel_filter = arguments.get("relation_filter", "").lower()
        matches = _find_node(G, label)
        if not matches:
            return f"No node matching '{label}' found."
        nid = matches[0]
        lines = [f"Neighbors of {G.nodes[nid].get('label', nid)}:"]
        for neighbor in G.neighbors(nid):
            d = G.edges[nid, neighbor]
            rel = d.get("relation", "")
            if rel_filter and rel_filter not in rel.lower():
                continue
            lines.append(f"  --> {G.nodes[neighbor].get('label', neighbor)} [{rel}] [{d.get('confidence', '')}]")
        return "\n".join(lines)

    def _tool_get_community(arguments: dict) -> str:
        cid = int(arguments["community_id"])
        nodes = communities.get(cid, [])
        if not nodes:
            return f"Community {cid} not found."
        lines = [f"Community {cid} ({len(nodes)} nodes):"]
        for n in nodes:
            d = G.nodes[n]
            lines.append(f"  {d.get('label', n)} [{d.get('source_file', '')}]")
        return "\n".join(lines)

    def _tool_god_nodes(arguments: dict) -> str:
        from .analyze import god_nodes as _god_nodes
        nodes = _god_nodes(G, top_n=int(arguments.get("top_n", 10)))
        lines = ["God nodes (most connected):"]
        lines += [f"  {i}. {n['label']} - {n['edges']} edges" for i, n in enumerate(nodes, 1)]
        return "\n".join(lines)

    def _tool_graph_stats(_: dict) -> str:
        confs = [d.get("confidence", "EXTRACTED") for _, _, d in G.edges(data=True)]
        total = len(confs) or 1
        return (
            f"Nodes: {G.number_of_nodes()}\n"
            f"Edges: {G.number_of_edges()}\n"
            f"Communities: {len(communities)}\n"
            f"EXTRACTED: {round(confs.count('EXTRACTED')/total*100)}%\n"
            f"INFERRED: {round(confs.count('INFERRED')/total*100)}%\n"
            f"AMBIGUOUS: {round(confs.count('AMBIGUOUS')/total*100)}%\n"
        )

    def _tool_shortest_path(arguments: dict) -> str:
        src_scored = _score_nodes(G, [t.lower() for t in arguments["source"].split()])
        tgt_scored = _score_nodes(G, [t.lower() for t in arguments["target"].split()])
        if not src_scored:
            return f"No node matching source '{arguments['source']}' found."
        if not tgt_scored:
            return f"No node matching target '{arguments['target']}' found."
        src_nid, tgt_nid = src_scored[0][1], tgt_scored[0][1]
        max_hops = int(arguments.get("max_hops", 8))
        try:
            path_nodes = nx.shortest_path(G, src_nid, tgt_nid)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return f"No path found between '{G.nodes[src_nid].get('label', src_nid)}' and '{G.nodes[tgt_nid].get('label', tgt_nid)}'."
        hops = len(path_nodes) - 1
        if hops > max_hops:
            return f"Path exceeds max_hops={max_hops} ({hops} hops found)."
        segments = []
        for i in range(len(path_nodes) - 1):
            u, v = path_nodes[i], path_nodes[i + 1]
            edata = G.edges[u, v]
            rel = edata.get("relation", "")
            conf = edata.get("confidence", "")
            conf_str = f" [{conf}]" if conf else ""
            if i == 0:
                segments.append(G.nodes[u].get("label", u))
            segments.append(f"--{rel}{conf_str}--> {G.nodes[v].get('label', v)}")
        return f"Shortest path ({hops} hops):\n  " + " ".join(segments)

    def _tool_git_status(arguments: dict) -> str:
        # 優先使用呼叫方傳入的 repo_path，否則使用從 graph_path 推導出的專案根目錄
        repo_path = arguments.get("repo_path") or str(_project_root)
        
        # 執行 git status，加入 --no-pager 避免卡死；timeout 防止永久阻塞
        # 重要：必須加上 stdin=DEVNULL，防止 git 繼承 MCP Server 的 stdio 管道
        # （若 git 嘗試從 stdin 讀取（如認證提示），會吃掉 MCP 協議資料，導致 Claude Desktop 常轉圈圈）
        try:
            result = subprocess.run(
                ["git", "--no-pager", "status", "-s"],
                cwd=repo_path,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                check=True,
                timeout=30
            )
            
            # 檢查是否有輸出
            if not result.stdout.strip():
                return "No changes in the repository."
                
            return result.stdout
            
        except subprocess.TimeoutExpired:
            return "Git command timed out after 30 seconds."
            
        except subprocess.CalledProcessError as e:
            stderr = e.stderr or ""
            return f"Git command failed (exit {e.returncode}): {stderr.strip()}"
            
        except FileNotFoundError:
            return "Git executable not found. Ensure git is installed and in PATH."


    def _tool_git_diff(arguments: dict) -> str:
        # 優先使用呼叫方傳入的 repo_path，否則使用從 graph_path 推導出的專案根目錄
        repo_path = arguments.get("repo_path") or str(_project_root)
        target = arguments.get("target", "")
        staged = arguments.get("staged", False)
        
        # 組裝指令，強制關閉 pager
        cmd = ["git", "--no-pager", "diff"]
        
        # 判斷是否只比較 staged 變更
        if staged:
            cmd.append("--staged")
            
        # 判斷是否有指定特定檔案
        if target:
            cmd.extend(["--", target])
            
        # 執行 git diff；timeout 防止永久阻塞
        # 重要：必須加上 stdin=DEVNULL，防止 git 繼承 MCP Server 的 stdio 管道
        try:
            result = subprocess.run(
                cmd,
                cwd=repo_path,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                check=True,
                timeout=30
            )
            
            # 檢查是否有變更
            if not result.stdout.strip():
                return f"No diff output. Ensure the target has {'staged' if staged else 'unstaged'} modifications, or it might be untracked."
                
            # 限制輸出大小，避免 Payload 超載；按行截斷避免切斷 hunk 中間
            lines_out = result.stdout.splitlines(keepends=True)
            if len(result.stdout) > 50000:
                accumulated = []
                total_chars = 0
                for line in lines_out:
                    if total_chars + len(line) > 50000:
                        break
                    accumulated.append(line)
                    total_chars += len(line)
                output = "".join(accumulated)
                output += "\n\n... (Diff output truncated. Use 'target' argument to diff a specific file.)"
                return output
                
            return result.stdout
            
        except subprocess.TimeoutExpired:
            return "Git command timed out after 30 seconds."
            
        except subprocess.CalledProcessError as e:
            stderr = e.stderr or ""
            return f"Git command failed (exit {e.returncode}): {stderr.strip()}"
            
        except FileNotFoundError:
            return "Git executable not found. Ensure git is installed and in PATH."


    def _tool_read_file(arguments: dict) -> str:
        file_path = arguments.get("file_path", "")
        start_line = arguments.get("start_line")   # 可為 None 或整數
        end_line = arguments.get("end_line")       # 可為 None 或整數
        
        # 檢查檔名參數
        if not file_path:
            return "Error: file_path is required."
            
        # 讀取並處理檔案
        try:
            # 相對路徑以 _project_root 為基礎解析，避免依賴 MCP Server 不確定的 CWD
            # 絕對路徑直接解析（仍受後續安全邊界保護）
            if Path(file_path).is_absolute():
                path = Path(file_path).resolve()
            else:
                path = (_project_root / file_path).resolve()
            
            # 安全邊界：只允許讀取專案根目錄底下的檔案，防止路徑穿越（Path Traversal）
            try:
                path.relative_to(_project_root)
            except ValueError:
                return f"Error: Access denied. '{file_path}' is outside the project root ({_project_root})."
            
            # 確認檔案合法性
            if not path.is_file():
                return f"Error: '{file_path}' is not a file or does not exist."
                
            # 防止過大檔案導致記憶體問題
            if path.stat().st_size > 10 * 1024 * 1024:
                return "Error: File is too large (>10MB). Cannot read."
            
            # 讀取所有行數
            lines = path.read_text(encoding="utf-8").splitlines()
            total_lines = len(lines)
            
            # 計算起始行：明確用 None 判斷，避免 start_line=0 被誤判為未傳入
            s = max(1, int(start_line)) if start_line is not None else 1
            
            # 計算結束行：明確用 None 判斷，避免 end_line=0 被誤判為未傳入
            e = min(total_lines, int(end_line)) if end_line is not None else total_lines
            
            # 驗證範圍是否合理
            if s > total_lines:
                return f"Error: start_line={s} exceeds file length ({total_lines} lines)."
                
            if s > e:
                return f"Error: Invalid line range {s}-{e}. start_line must be <= end_line."
                
            # 取出目標範圍的文字，回傳時附上行號資訊供 LLM 定位
            selected_lines = lines[s-1:e]
            header = f"[File: {path} | Lines: {s}-{e} of {total_lines}]\n"
            content = "\n".join(selected_lines)
            
            # 針對太長的內容進行截斷（按行截斷避免截斷在程式碼中間）
            if len(content) > 100000:
                accumulated = []
                total_chars = 0
                for line in selected_lines:
                    if total_chars + len(line) + 1 > 100000:
                        break
                    accumulated.append(line)
                    total_chars += len(line) + 1
                content = "\n".join(accumulated)
                content += f"\n\n... (Content truncated. Read to line {s + len(accumulated) - 1}. Specify end_line to read further. Total lines: {total_lines})"
            elif start_line is None and end_line is None and total_lines > 500:
                content += f"\n\n--- (File has {total_lines} lines total. Use start_line and end_line for targeted reading.) ---"
                
            return header + content
            
        except UnicodeDecodeError:
            return f"Error: File '{file_path}' is not valid UTF-8 text."
            
        except Exception as e:
            return f"Error reading file: {e}"

    def _tool_list_directory(arguments: dict) -> str:
        subdir = arguments.get("subdir", "").strip()
        max_depth = min(max(int(arguments.get("max_depth", 5)), 1), 10)
        show_hidden = bool(arguments.get("show_hidden", False))

        # 計算目標目錄（相對路徑以 _project_root 為基底走訪）
        if subdir:
            target_dir = (_project_root / subdir).resolve()
        else:
            target_dir = _project_root

        # 安全邊界：只允許列出專案根目錄底下的目錄
        try:
            target_dir.relative_to(_project_root)
        except ValueError:
            return f"Error: Access denied. '{subdir}' is outside the project root ({_project_root})."

        if not target_dir.is_dir():
            return f"Error: '{subdir}' is not a directory or does not exist."

        # 嘗試用 git ls-files 取得已追蹤的相對路徑清單（自動尊重 .gitignore）
        # 若失敗則 fallback 到純 os.walk
        tracked_paths: set[str] | None = None
        try:
            result = subprocess.run(
                ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                cwd=str(_project_root),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=15
            )
            if result.returncode == 0 and result.stdout.strip():
                # 取得相對於 _project_root 的路徑集合（含目錄前綴）
                tracked_paths = set(result.stdout.splitlines())
        except Exception:
            # git 不可用時靜默降級
            tracked_paths = None

        # 依呼叫位置決定以哪個目錄為根節點
        # 同時產生相對於 _project_root 的路徑前綴，用於 tracked_paths 過濾
        try:
            display_root = target_dir.relative_to(_project_root)
        except ValueError:
            display_root = target_dir

        # 遞迴走訪目錄，產生縮排樹狀文字
        lines: list[str] = [str(display_root) + "/"]

        # 預設排除的噪音目錄（不論 show_hidden 設定）
        _ALWAYS_EXCLUDE = {".git", "__pycache__", ".venv", "node_modules", ".mypy_cache", ".pytest_cache"}

        def _walk(current: Path, prefix: str, depth: int) -> None:
            if depth > max_depth:
                return

            # 收集並排序子項目（目錄優先，再按名稱字母排序）
            try:
                entries = sorted(current.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
            except PermissionError:
                lines.append(prefix + "[Permission denied]")
                return

            for i, entry in enumerate(entries):
                name = entry.name
                is_last = (i == len(entries) - 1)

                # 過濾隱藏項目
                if not show_hidden and name.startswith("."):
                    continue

                # 永遠排除噪音目錄
                if name in _ALWAYS_EXCLUDE:
                    continue

                # 若有 git 追蹤清單，過濾未被追蹤的路徑
                if tracked_paths is not None:
                    # 計算此 entry 相對於 _project_root 的路徑字串（統一用正斜線）
                    try:
                        rel = entry.relative_to(_project_root).as_posix()
                    except ValueError:
                        rel = entry.name

                    # 目錄：只要 tracked_paths 中有任何以此路徑為前綴的項目，就顯示
                    if entry.is_dir():
                        rel_prefix = rel + "/"
                        has_tracked = any(p.startswith(rel_prefix) or p == rel for p in tracked_paths)
                        if not has_tracked:
                            continue
                    else:
                        # 檔案：必須在追蹤清單中
                        if rel not in tracked_paths:
                            continue

                # 產生樹狀分支符號
                connector = "+-- " if is_last else "+-- "
                lines.append(prefix + connector + name + ("/" if entry.is_dir() else ""))

                # 遞迴進入目錄
                if entry.is_dir():
                    extension = "    " if is_last else "|   "
                    _walk(entry, prefix + extension, depth + 1)

        _walk(target_dir, "", 1)

        # 輸出大小保護：超過 300 行時截斷並提示
        if len(lines) > 300:
            lines = lines[:300]
            lines.append("... (output truncated at 300 lines. Use 'subdir' to narrow down.)")

        return "\n".join(lines)

    def _normalize(s: str) -> str:
        """將每行的前後空白去除，用於模糊比對時忽略縮排差異"""
        return "\n".join(line.strip() for line in s.splitlines())

    def _tool_write_file(arguments: dict) -> str:
        file_path = arguments.get("file_path", "")
        content = arguments.get("content")

        # 檢查必要參數
        if not file_path:
            return "Error: file_path is required."

        if content is None:
            return "Error: content is required."

        # 解析目標路徑（相對路徑以 _project_root 為基礎）
        if Path(file_path).is_absolute():
            path = Path(file_path).resolve()
        else:
            path = (_project_root / file_path).resolve()

        # 安全邊界 1：必須在專案根目錄內
        try:
            path.relative_to(_project_root)
        except ValueError:
            return f"Error: Access denied. '{file_path}' is outside the project root ({_project_root})."

        # 安全邊界 2：封鎖 .git/ 目錄，防止破壞 git 內部結構
        try:
            git_dir = (_project_root / ".git").resolve()
            path.relative_to(git_dir)
            return "Error: Access denied. Writing to .git/ is not allowed."
        except ValueError:
            pass

        # 內容大小限制（防止意外寫入過大資料）
        content_bytes = content.encode("utf-8")
        if len(content_bytes) > 5 * 1024 * 1024:
            return "Error: Content exceeds 5MB limit."

        # 自動建立不存在的父目錄（方便新增檔案到新子目錄）
        try:
            path.parent.mkdir(parents=True, exist_ok=True)

            is_new = not path.exists()

            path.write_text(content, encoding="utf-8")

            # 回傳確認資訊，讓 LLM 能驗證操作結果
            line_count = content.count("\n") + (1 if content else 0)
            rel_path = path.relative_to(_project_root)
            action = "Created" if is_new else "Overwrote"
            return (
                f"{action}: {rel_path}\n"
                f"Lines: {line_count}\n"
                f"Bytes: {len(content_bytes)}\n"
                f"Absolute path: {path}"
            )

        except PermissionError:
            return f"Error: Permission denied writing to '{file_path}'."

        except Exception as e:
            return f"Error writing file: {e}"

    def _tool_edit_file(arguments: dict) -> str:
        file_path = arguments.get("file_path", "")
        old_content = arguments.get("old_content")
        new_content = arguments.get("new_content")
        start_line = arguments.get("start_line")
        end_line = arguments.get("end_line")
        replace_range = bool(arguments.get("replace_range", False))

        # 檢查必要參數
        if not file_path:
            return "Error: file_path is required."

        if old_content is None:
            return "Error: old_content is required."

        if new_content is None:
            return "Error: new_content is required."

        # 解析目標路徑（相對路徑以 _project_root 為基礎）
        if Path(file_path).is_absolute():
            path = Path(file_path).resolve()
        else:
            path = (_project_root / file_path).resolve()

        # 安全邊界 1：必須在專案根目錄內
        try:
            path.relative_to(_project_root)
        except ValueError:
            return f"Error: Access denied. '{file_path}' is outside the project root ({_project_root})."

        # 安全邊界 2：封鎖 .git/ 目錄
        try:
            git_dir = (_project_root / ".git").resolve()
            path.relative_to(git_dir)
            return "Error: Access denied. Writing to .git/ is not allowed."
        except ValueError:
            pass

        # 檔案必須存在（edit 不同於 write，不能建立新檔）
        if not path.is_file():
            return f"Error: '{file_path}' does not exist. Use write_file to create new files."

        try:
            full_text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return f"Error: File '{file_path}' is not valid UTF-8 text."

        all_lines = full_text.splitlines(keepends=True)
        total_lines = len(all_lines)
        rel_path = path.relative_to(_project_root)

        # =============================================
        # 模式判定
        # =============================================

        # --- INSERT 模式：old_content 為空 + start_line 指定插入位置 ---
        if old_content == "" and not replace_range:
            if start_line is None:
                return "Error: INSERT mode requires start_line. Set start_line to the line BEFORE which to insert."

            insert_at = int(start_line)

            if insert_at < 1 or insert_at > total_lines + 1:
                return f"Error: start_line={insert_at} out of range. File has {total_lines} lines (use {total_lines + 1} to append)."

            # 在指定行之前插入；確保 new_content 結尾有換行
            insert_text = new_content if new_content.endswith("\n") else new_content + "\n"

            before = "".join(all_lines[:insert_at - 1])
            after = "".join(all_lines[insert_at - 1:])
            new_text = before + insert_text + after

            new_bytes = new_text.encode("utf-8")
            if len(new_bytes) > 5 * 1024 * 1024:
                return "Error: Edited file would exceed 5MB limit."

            path.write_text(new_text, encoding="utf-8")

            inserted_count = insert_text.count("\n")
            new_total = new_text.count("\n") + 1
            return (
                f"Inserted at: {rel_path} (before line {insert_at})\n"
                f"Lines inserted: {inserted_count}\n"
                f"Total lines after edit: {new_total}\n"
                f"Bytes: {len(new_bytes)}"
            )

        # --- RANGE-REPLACE 模式：行號範圍覆寫，old_content 僅作驗證錨點 ---
        if replace_range:
            if start_line is None or end_line is None:
                return "Error: RANGE-REPLACE mode requires both start_line and end_line."

            rs = max(1, int(start_line))
            re_ = min(total_lines, int(end_line))

            if rs > total_lines or rs > re_:
                return f"Error: Invalid line range {rs}-{re_}. File has {total_lines} lines."

            # 切出目標範圍的內容
            range_text = "".join(all_lines[rs - 1:re_])

            # old_content 作為驗證錨點：必須存在於該範圍內（精確或模糊）
            anchor_found = old_content in range_text

            if not anchor_found:
                anchor_found = _normalize(old_content) in _normalize(range_text)

            if not anchor_found:
                preview = range_text[:500].rstrip()
                return (
                    f"Error: Verification anchor not found in lines {rs}-{re_}.\n"
                    f"The old_content you provided does not exist in this range.\n"
                    f"--- Actual content (first 500 chars) ---\n"
                    f"{preview}\n"
                    f"--- End preview ---\n"
                    f"Hint: Use read_file to verify the content at these lines."
                )

            # 驗證通過，用 new_content 覆寫整個行號範圍
            before = "".join(all_lines[:rs - 1])
            after = "".join(all_lines[re_:])

            # 確保接合處有換行（防止前後區塊黏在一起）
            if new_content and not new_content.endswith("\n") and after:
                new_text = before + new_content + "\n" + after
            else:
                new_text = before + new_content + after

            new_bytes = new_text.encode("utf-8")
            if len(new_bytes) > 5 * 1024 * 1024:
                return "Error: Edited file would exceed 5MB limit."

            path.write_text(new_text, encoding="utf-8")

            old_line_count = re_ - rs + 1
            new_line_count = new_text.count("\n") + 1
            return (
                f"Range-replaced: {rel_path} (lines {rs}-{re_})\n"
                f"Old lines removed: {old_line_count}\n"
                f"Total lines after edit: {new_line_count}\n"
                f"Bytes: {len(new_bytes)}"
            )

        # --- SEARCH-REPLACE 模式（預設）：精確匹配 + 模糊 fallback ---

        # 如果有提供 start_line / end_line，將搜尋範圍縮窄到該區段
        if start_line is not None or end_line is not None:
            s = max(1, int(start_line)) if start_line is not None else 1
            e = min(total_lines, int(end_line)) if end_line is not None else total_lines

            if s > total_lines or s > e:
                return f"Error: Invalid line range {s}-{e}. File has {total_lines} lines."

            scope_lines = all_lines[s - 1:e]
            scope_text = "".join(scope_lines)
            scope_offset = sum(len(l) for l in all_lines[:s - 1])
        else:
            scope_lines = all_lines
            scope_text = full_text
            scope_offset = 0
            s = 1
            e = total_lines

        # 第一階段：精確匹配
        match_pos = scope_text.find(old_content)
        match_method = "exact"

        # 第二階段：精確匹配失敗，嘗試去空白模糊匹配 (Fuzzy Fallback)
        if match_pos == -1:
            normalized_old = _normalize(old_content)
            old_line_count = len(old_content.splitlines())
            for i in range(len(scope_lines) - old_line_count + 1):
                candidate = "".join(scope_lines[i:i + old_line_count])
                if _normalize(candidate) == normalized_old:
                    match_pos = sum(len(l) for l in scope_lines[:i])
                    old_content = candidate
                    match_method = "normalized"
                    break

        # 兩階段都失敗，回傳診斷資訊
        if match_pos == -1:
            preview_lines = scope_lines[:20]
            preview = "".join(preview_lines).rstrip()
            return (
                f"Error: old_content not found in '{file_path}' "
                f"(searched lines {s}-{e}).\n"
                f"--- Actual content in range (first 20 lines) ---\n"
                f"{preview}\n"
                f"--- End preview ---\n"
                f"Hint: Ensure old_content matches the file. "
                f"Use read_file with start_line/end_line to verify."
            )

        # 檢查是否有多個匹配（在範圍內）
        second_match = scope_text.find(old_content, match_pos + len(old_content))
        if second_match != -1:
            line_of_first = scope_text[:match_pos].count("\n") + s
            line_of_second = scope_text[:second_match].count("\n") + s
            total_in_scope = scope_text.count(old_content)
            return (
                f"Error: old_content appears {total_in_scope} times "
                f"in lines {s}-{e}.\n"
                f"First at line {line_of_first}, second at line {line_of_second}.\n"
                f"Use start_line/end_line to narrow scope to a unique match."
            )

        # 執行替換（在全文中的絕對位置）
        abs_pos = scope_offset + match_pos
        new_text = (
            full_text[:abs_pos]
            + new_content
            + full_text[abs_pos + len(old_content):]
        )

        # 內容大小限制
        new_bytes = new_text.encode("utf-8")
        if len(new_bytes) > 5 * 1024 * 1024:
            return "Error: Edited file would exceed 5MB limit."

        # 寫回檔案
        path.write_text(new_text, encoding="utf-8")

        # 回傳確認資訊
        new_line_count = new_text.count("\n") + 1
        match_line = full_text[:abs_pos].count("\n") + 1
        return (
            f"Edited: {rel_path}\n"
            f"Match method: {match_method}\n"
            f"Replaced at line: {match_line}\n"
            f"Total lines after edit: {new_line_count}\n"
            f"Bytes: {len(new_bytes)}"
        )

    _handlers = {
        "query_graph": _tool_query_graph,
        "get_node": _tool_get_node,
        "get_neighbors": _tool_get_neighbors,
        "get_community": _tool_get_community,
        "god_nodes": _tool_god_nodes,
        "graph_stats": _tool_graph_stats,
        "shortest_path": _tool_shortest_path,
        "git_status": _tool_git_status,
        "git_diff": _tool_git_diff,
        "read_file": _tool_read_file,
        "write_file": _tool_write_file,
        "edit_file": _tool_edit_file,
        "list_directory": _tool_list_directory,
    }

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
        handler = _handlers.get(name)
        if not handler:
            return [types.TextContent(type="text", text=f"Unknown tool: {name}")]
        
        # 包裹 top-level try-except：任何未捕捉的例外都必須以文字回傳
        # 否則 async task 崩潰會讓 Claude Desktop 永遠看到轉圈圈而沒有回應
        try:
            result = handler(arguments)
            return [types.TextContent(type="text", text=result)]
        except Exception as exc:
            error_msg = f"[graphify internal error] {type(exc).__name__}: {exc}"
            print(error_msg, file=sys.stderr)
            return [types.TextContent(type="text", text=error_msg)]

    import asyncio

    async def main() -> None:
        async with stdio_server() as streams:
            await server.run(streams[0], streams[1], server.create_initialization_options())

    asyncio.run(main())


if __name__ == "__main__":
    graph_path = sys.argv[1] if len(sys.argv) > 1 else "graphify-out/graph.json"
    serve(graph_path)
