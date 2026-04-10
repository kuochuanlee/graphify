# Graphify — Gemini CLI Support Implementation Plan

> **執行對象：Gemini (Antigravity)**
> 本文件列出所有需要修改的檔案、位置、和具體內容。請依序完成所有任務，每個任務完成後確認檔案已儲存。

---

## 背景說明

Graphify 目前支援 Claude Code、Codex、OpenCode 等平台。本次任務是新增對 **Gemini CLI** 的支援。

Gemini CLI 的 skill 系統與 Claude Code 使用相同的 `SKILL.md` 開放格式，因此 `graphify/skill.md` 本體**幾乎不需要改動**，主要工作集中在：

1. `graphify/__main__.py` — 新增 gemini 平台設定與指令
2. `graphify/skill.md` — 修改 Step B2 的 subagent 並行語法
3. `tests/test_install.py` — 新增 gemini 的測試案例

---

## Task 1：修改 `graphify/__main__.py`

### 1-A：在 `_PLATFORM_CONFIG` 字典新增 `gemini` 項目

**位置：** 找到以下這段（約第 82-83 行）：
```python
    "trae-cn": {
        "skill_dst": Path(".trae-cn") / "skills" / "graphify" / "SKILL.md",
        "claude_md": False,
    },
```

**在其後面緊接著新增：**
```python
    "gemini": {
        "skill_dst": Path(".gemini") / "skills" / "graphify" / "SKILL.md",
        "claude_md": False,
    },
```

---

### 1-B：新增兩個常數字串

**位置：** 找到現有的 `_CLAUDE_MD_MARKER` 和 `_CLAUDE_MD_SECTION` 常數定義（在 `claude_install` 函式上方）。

**在其後面新增：**
```python
_GEMINI_MD_MARKER = "<!-- graphify -->"
_GEMINI_MD_SECTION = """
<!-- graphify -->
## graphify

Before answering any architecture, codebase structure, or dependency questions,
check if `graphify-out/GRAPH_REPORT.md` exists and read it first.
Navigate via the knowledge graph instead of grepping through raw files.

After making code changes, remind the user to run `/graphify --update`
to keep the graph current.
<!-- /graphify -->
"""
```

---

### 1-C：新增 `gemini_install()` 函式

**位置：** 找到 `claude_install()` 函式，在其**後面**新增以下兩個函式：

```python
def gemini_install(project_dir: Path | None = None) -> None:
    """Write graphify section to GEMINI.md for Gemini CLI always-on integration."""
    import re
    project_dir = project_dir or Path(".")
    gemini_md = project_dir / "GEMINI.md"
    if gemini_md.exists():
        content = gemini_md.read_text(encoding="utf-8")
        if _GEMINI_MD_MARKER in content:
            print(f"  GEMINI.md  ->  already registered (no change)")
            return
        gemini_md.write_text(content.rstrip() + "\n" + _GEMINI_MD_SECTION, encoding="utf-8")
        print(f"  GEMINI.md  ->  graphify section added at {gemini_md}")
    else:
        gemini_md.write_text(_GEMINI_MD_SECTION.lstrip(), encoding="utf-8")
        print(f"  GEMINI.md  ->  created at {gemini_md}")


def gemini_uninstall(project_dir: Path | None = None) -> None:
    """Remove graphify section from GEMINI.md."""
    import re
    project_dir = project_dir or Path(".")
    gemini_md = project_dir / "GEMINI.md"
    if not gemini_md.exists():
        print("  GEMINI.md  ->  not found (nothing to do)")
        return
    content = gemini_md.read_text(encoding="utf-8")
    if _GEMINI_MD_MARKER not in content:
        print("  GEMINI.md  ->  graphify section not found (nothing to do)")
        return
    cleaned = re.sub(
        r"\n?<!-- graphify -->.*?<!-- /graphify -->",
        "",
        content,
        flags=re.DOTALL,
    )
    gemini_md.write_text(cleaned.rstrip() + "\n", encoding="utf-8")
    print(f"  GEMINI.md  ->  graphify section removed")
```

---

### 1-D：在主指令分派區塊新增 `gemini` 子指令

**位置：** 找到處理 `elif cmd == "claude":` 的區塊（約第 520-527 行）：
```python
    elif cmd == "claude":
        sub = args[1] if len(args) > 1 else ""
        if sub == "install":
            claude_install()
        elif sub == "uninstall":
            claude_uninstall()
        else:
            print("Usage: graphify claude [install|uninstall]", file=sys.stderr)
```

**在其後面新增：**
```python
    elif cmd == "gemini":
        sub = args[1] if len(args) > 1 else ""
        if sub == "install":
            gemini_install()
        elif sub == "uninstall":
            gemini_uninstall()
        else:
            print("Usage: graphify gemini [install|uninstall]", file=sys.stderr)
```

---

### 1-E：更新 help 文字

**位置：** 找到以下這行（約第 471 行）：
```python
        print("  install [--platform P]  copy skill to platform config dir (claude|windows|codex|opencode|claw|droid|trae|trae-cn)")
```

**改成：**
```python
        print("  install [--platform P]  copy skill to platform config dir (claude|windows|codex|opencode|claw|droid|trae|trae-cn|gemini)")
```

---

**位置：** 找到以下這兩行（約第 486-487 行）：
```python
        print("  claude install          write graphify section to CLAUDE.md + PreToolUse hook (Claude Code)")
        print("  claude uninstall        remove graphify section from CLAUDE.md + PreToolUse hook")
```

**在其後面新增：**
```python
        print("  gemini install          write graphify section to GEMINI.md (Gemini CLI)")
        print("  gemini uninstall        remove graphify section from GEMINI.md")
```

---

## Task 2：修改 `graphify/skill.md`

### 2-A：修改 Step B2 的 subagent 並行指令說明

**位置：** 找到以下這段文字：
```
**MANDATORY: You MUST use the Agent tool here. Reading files yourself one-by-one is forbidden - it is 5-10x slower. If you do not use the Agent tool you are doing this wrong.**
```

**改成：**
```
**MANDATORY: You MUST dispatch all chunks in parallel. Reading files yourself one-by-one is forbidden - it is 5-10x slower.**

**For Gemini CLI:** Use subagents via the `@` syntax or dispatch parallel shell processes:
Write each chunk's prompt to a temp file, then dispatch all in parallel using background shell jobs:
```bash
for i in $(seq 1 $TOTAL_CHUNKS); do
  gemini --yolo -p "$(cat graphify-out/.graphify_prompt_$i.txt)" \
    > graphify-out/.graphify_chunk_$i.json 2>&1 &
done
wait
```
**For Claude Code:** Call the Agent tool multiple times IN THE SAME RESPONSE — one call per chunk.
```

---

### 2-B：修改底部的 `graphify claude install` 說明段落

**位置：** 找到以下段落（接近檔案尾端）：
```markdown
## For native CLAUDE.md integration

Run once per project to make graphify always-on in Claude Code sessions:

```bash
graphify claude install
```

This writes a `## graphify` section to the local `CLAUDE.md` ...

```bash
graphify claude uninstall  # remove the section
```
```

**在其後面新增一個新段落：**
```markdown
## For native GEMINI.md integration

Run once per project to make graphify always-on in Gemini CLI sessions:

```bash
graphify gemini install
```

This writes a `## graphify` section to the local `GEMINI.md` that instructs Gemini
to read `graphify-out/GRAPH_REPORT.md` before answering architecture questions
and to remind the user to run `--update` after code changes.

```bash
graphify gemini uninstall  # remove the section
```
```

---

## Task 3：修改 `tests/test_install.py`

### 3-A：在平台對應表新增 gemini

**位置：** 找到 `_EXPECTED` 或類似的平台路徑對應字典（約第 8-15 行）：
```python
    "claude": (".claude/skills/graphify/SKILL.md",),
    ...
    "windows": (".claude/skills/graphify/SKILL.md",),
```

**新增：**
```python
    "gemini": (".gemini/skills/graphify/SKILL.md",),
```

---

### 3-B：新增 gemini install 測試函式

**位置：** 在檔案末尾新增：

```python
def test_install_gemini(tmp_path):
    _install(tmp_path, "gemini")
    assert (tmp_path / ".gemini" / "skills" / "graphify" / "SKILL.md").exists()


def test_gemini_install_creates_gemini_md(tmp_path):
    from graphify.__main__ import gemini_install
    gemini_install(tmp_path)
    assert (tmp_path / "GEMINI.md").exists()
    content = (tmp_path / "GEMINI.md").read_text(encoding="utf-8")
    assert "<!-- graphify -->" in content


def test_gemini_install_idempotent(tmp_path):
    from graphify.__main__ import gemini_install
    gemini_install(tmp_path)
    gemini_install(tmp_path)
    content = (tmp_path / "GEMINI.md").read_text(encoding="utf-8")
    assert content.count("<!-- graphify -->") == 1


def test_gemini_uninstall_removes_section(tmp_path):
    from graphify.__main__ import gemini_install, gemini_uninstall
    gemini_install(tmp_path)
    gemini_uninstall(tmp_path)
    content = (tmp_path / "GEMINI.md").read_text(encoding="utf-8")
    assert "<!-- graphify -->" not in content


def test_gemini_install_appends_to_existing_gemini_md(tmp_path):
    from graphify.__main__ import gemini_install
    existing = tmp_path / "GEMINI.md"
    existing.write_text("# My Project\n\nSome existing content.\n", encoding="utf-8")
    gemini_install(tmp_path)
    content = existing.read_text(encoding="utf-8")
    assert "# My Project" in content
    assert "<!-- graphify -->" in content
```

---

## Task 4：更新 `README.md`

### 4-A：在 Platform support 表格新增 gemini 列

**位置：** 找到 Platform support 的 markdown 表格：
```markdown
| Claude Code (Linux/Mac) | `graphify install` |
...
| Trae CN | `graphify install --platform trae-cn` |
```

**新增一列：**
```markdown
| Gemini CLI | `graphify install --platform gemini` |
```

---

### 4-B：在 always-on 指令表格新增 gemini 列

**位置：** 找到以下表格：
```markdown
| Claude Code | `graphify claude install` |
| Codex       | `graphify codex install`  |
...
```

**新增一列：**
```markdown
| Gemini CLI  | `graphify gemini install` |
```

---

### 4-C：在 Usage 區塊的指令列表新增 gemini

**位置：** 找到：
```
graphify claude install            # CLAUDE.md + PreToolUse hook (Claude Code)
graphify claude uninstall
```

**在其後新增：**
```
graphify gemini install            # GEMINI.md (Gemini CLI)
graphify gemini uninstall
```

---

## 完成後驗證

請執行以下指令確認改動正確：

```bash
# 安裝測試
python -m pytest tests/test_install.py -v -k "gemini"

# 手動驗證 install 指令
python -m graphify install --platform gemini
# 預期輸出：skill installed -> ~/.gemini/skills/graphify/SKILL.md

# 手動驗證 gemini install/uninstall
python -m graphify gemini install
# 預期：在當前目錄建立 GEMINI.md 並寫入 <!-- graphify --> 區塊

python -m graphify gemini uninstall
# 預期：GEMINI.md 中的 <!-- graphify --> 區塊被移除

# 確認 help 文字有更新
python -m graphify --help | grep gemini
```

---

## 摘要：改動的檔案清單

| 檔案 | 改動數量 | 說明 |
|------|---------|------|
| `graphify/__main__.py` | 5 處 | 新增 gemini platform config、常數、兩個函式、指令分派、help 文字 |
| `graphify/skill.md` | 2 處 | 修改 subagent 並行說明、新增 GEMINI.md 整合段落 |
| `tests/test_install.py` | 2 處 | 新增 gemini 到平台表、新增 5 個測試函式 |
| `README.md` | 3 處 | 更新三個表格/指令列表 |
