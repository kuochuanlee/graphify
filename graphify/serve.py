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
    for nid in sorted(nodes, key=lambda n: G.degree(n), reverse=True):
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
                        "staged": {"type": "boolean", "default": false, "description": "If true, shows staged changes (git diff --staged)."}
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
            f"  Degree: {G.degree(nid)}",
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
        repo_path = arguments.get("repo_path", ".")
        
        # 執行 git status，加入 --no-pager 避免卡死
        try:
            result = subprocess.run(
                ["git", "--no-pager", "status", "-s"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            
            # 檢查是否有輸出
            if not result.stdout.strip():
                return "No changes in the repository."
                
            return result.stdout
            
        except subprocess.CalledProcessError as e:
            return f"Git command failed: {e.stderr}"
            
        except FileNotFoundError:
            return "Git executable not found."


    def _tool_git_diff(arguments: dict) -> str:
        repo_path = arguments.get("repo_path", ".")
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
            
        # 執行 git diff
        try:
            result = subprocess.run(
                cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True
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
            
        except subprocess.CalledProcessError as e:
            return f"Git command failed: {e.stderr}"
            
        except FileNotFoundError:
            return "Git executable not found."


    def _tool_read_file(arguments: dict) -> str:
        file_path = arguments.get("file_path", "")
        start_line = arguments.get("start_line")   # 可為 None 或整數
        end_line = arguments.get("end_line")       # 可為 None 或整數
        
        # 檢查檔名參數
        if not file_path:
            return "Error: file_path is required."
            
        # 讀取並處理檔案
        try:
            path = Path(file_path).resolve()
            
            # 安全邊界：只允許讀取當前工作目錄（CWD）底下的檔案，防止路徑穿越（Path Traversal）
            cwd = Path.cwd().resolve()
            try:
                path.relative_to(cwd)
            except ValueError:
                return f"Error: Access denied. '{file_path}' is outside the working directory."
            
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
    }

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
        handler = _handlers.get(name)
        if not handler:
            return [types.TextContent(type="text", text=f"Unknown tool: {name}")]
        return [types.TextContent(type="text", text=handler(arguments))]

    import asyncio

    async def main() -> None:
        async with stdio_server() as streams:
            await server.run(streams[0], streams[1], server.create_initialization_options())

    asyncio.run(main())


if __name__ == "__main__":
    graph_path = sys.argv[1] if len(sys.argv) > 1 else "graphify-out/graph.json"
    serve(graph_path)
