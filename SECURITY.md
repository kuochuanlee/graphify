# Security Policy

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Report security issues via GitHub's private vulnerability reporting, or email the maintainer directly. Please include:

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

## Security Model

graphify is a **local development tool**. It runs as a Gemini CLI skill. It makes no network calls during graph analysis - text content is sent to the LLM provider only during semantic extraction.

### Threat Surface

| Vector | Mitigation |
|--------|-----------|
| Path traversal in output | `security.validate_graph_path()` resolves paths and requires them to be inside `graphify-out/`. Also requires the `graphify-out/` directory to exist. |
| XSS in graph HTML output | `security.sanitize_label()` strips control characters, caps at 256 chars, and HTML-escapes all node labels and edge titles before pyvis embeds them. |
| Prompt injection via node labels | `sanitize_label()` also applied to text output - node labels from user-controlled source files cannot break the text format returned to agents. |
| Corrupted graph.json | `_load_graph()` wraps `json.JSONDecodeError` and prints a clear recovery message instead of crashing. |
| Symlink traversal | `os.walk(..., followlinks=False)` is explicit throughout `detect.py`. |

### What graphify does NOT do

- Does not run a network listener (no server process)
- Does not execute code from source files
- Does not use `shell=True` in any subprocess call
- Does not store credentials or API keys
