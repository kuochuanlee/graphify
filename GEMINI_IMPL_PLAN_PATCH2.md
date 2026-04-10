# Graphify — Gemini CLI 補丁二（漏網之魚修正）

> **執行對象：Gemini (Antigravity)**
> 本文件修正 `GEMINI_IMPL_PLAN_PATCH.md` 執行後，驗證步驟所發現的三個殘留問題。
> 僅修改 `graphify/skill-gemini.md`。

---

## Task A：修改 Step 9 — 清理暫存檔的 `rm -f`

### 位置

找到以下這段（Step 9 Python 區塊的**結尾**，緊接在 `"` 之後）：

```
"
rm -f graphify-out/.graphify_detect.json graphify-out/.graphify_extract.json graphify-out/.graphify_ast.json graphify-out/.graphify_semantic.json graphify-out/.graphify_analysis.json graphify-out/.graphify_labels.json
rm -f graphify-out/.needs_update 2>/dev/null || true
```

### 改成

```
"

# Bash (Linux / macOS / WSL):
# rm -f graphify-out/.graphify_detect.json graphify-out/.graphify_extract.json graphify-out/.graphify_ast.json graphify-out/.graphify_semantic.json graphify-out/.graphify_analysis.json graphify-out/.graphify_labels.json
# rm -f graphify-out/.needs_update 2>/dev/null || true

# PowerShell (Windows):
# $files = @('graphify-out/.graphify_detect.json','graphify-out/.graphify_extract.json','graphify-out/.graphify_ast.json','graphify-out/.graphify_semantic.json','graphify-out/.graphify_analysis.json','graphify-out/.graphify_labels.json','graphify-out/.needs_update')
# Remove-Item -Force -ErrorAction SilentlyContinue $files
```

> **為什麼用註解形式？** 這兩行 `rm -f` 是嵌在同一個 bash code block 裡（緊跟 Python heredoc 的 `"`），
> 無法單獨拆成兩個標記為 bash/powershell 的 fenced block。
> 改成雙平台的行內註解，Gemini 能看懂並選對版本執行，是最乾淨的做法。
> 如果你的工具支援把這段拆出來成為獨立段落，也可以改成和 Task 1–4 一樣的雙 fenced block 格式。

---

## Task B：修改 Interpreter guard — 子指令前的解譯器確認

### 位置

找到以下整段（`## Interpreter guard for subcommands` 標題之後）：

```bash
if [ ! -f graphify-out/.graphify_python ]; then
    GRAPHIFY_BIN=$(which graphify 2>/dev/null)
    if [ -n "$GRAPHIFY_BIN" ]; then
        PYTHON=$(head -1 "$GRAPHIFY_BIN" | tr -d '#!')
        case "$PYTHON" in *[!a-zA-Z0-9/_.-]*) PYTHON="python3" ;; esac
    else
        PYTHON="python3"
    fi
    mkdir -p graphify-out
    "$PYTHON" -c "import sys; open('graphify-out/.graphify_python', 'w').write(sys.executable)"
fi
```

### 改成

````markdown
**Bash (Linux / macOS / WSL):**
```bash
if [ ! -f graphify-out/.graphify_python ]; then
    GRAPHIFY_BIN=$(which graphify 2>/dev/null)
    if [ -n "$GRAPHIFY_BIN" ]; then
        PYTHON=$(head -1 "$GRAPHIFY_BIN" | tr -d '#!')
        case "$PYTHON" in *[!a-zA-Z0-9/_.-]*) PYTHON="python3" ;; esac
    else
        PYTHON="python3"
    fi
    mkdir -p graphify-out
    "$PYTHON" -c "import sys; open('graphify-out/.graphify_python', 'w').write(sys.executable)"
fi
```

**PowerShell (Windows):**
```powershell
if (-not (Test-Path "graphify-out/.graphify_python")) {
    New-Item -ItemType Directory -Force -Path graphify-out | Out-Null
    python -c "import sys; open('graphify-out/.graphify_python', 'w').write(sys.executable)"
}
```
````

---

## Task C：修改 `--update` — 備份與清理的行內指令

### 位置

找到以下這兩行（`--update` 區塊的結尾，第 818-819 行附近）：

```
Before the merge step, save the old graph: `cp graphify-out/graph.json graphify-out/.graphify_old.json`
Clean up after: `rm -f graphify-out/.graphify_old.json`
```

### 改成

```markdown
Before the merge step, save the old graph:
- **Bash:** `cp graphify-out/graph.json graphify-out/.graphify_old.json`
- **PowerShell:** `Copy-Item graphify-out/graph.json graphify-out/.graphify_old.json`

Clean up after:
- **Bash:** `rm -f graphify-out/.graphify_old.json`
- **PowerShell:** `Remove-Item -Force -ErrorAction SilentlyContinue graphify-out/.graphify_old.json`
```

---

## 順帶確認：Step 7d MCP server 的 `python3`

### 位置（第 590 行附近）

```bash
python3 -m graphify.serve graphify-out/graph.json
```

以及 Claude Desktop 的 config 範例中：

```json
"command": "python3",
```

### 處理方式

這兩處**不需要修改**。理由：

1. `python3 -m graphify.serve` 這行的用途是「啟動 MCP server」，是使用者手動在終端機執行的長駐指令，不是 Gemini 在 shell 工具裡自動執行的。Gemini 不會把這行塞進 `run_command`——它只是展示給使用者看的說明文字。
2. Claude Desktop config 中的 `python3` 是 JSON 設定值，跟 Gemini 的執行環境無關。Windows 使用者看到這段自然知道要改成自己系統的 Python 路徑。

如果你仍想保守處理，可以在那個 code block 前加一行說明：
> `Replace python3 with your actual Python executable path if needed (e.g. python on Windows).`

但這不是必要的修改。

---

## 執行完後再次驗證

```bash
grep -n "^rm -f\|^cp \|which graphify\|2>/dev/null\|2>&1 &\|^for i in\|^wait$\|^if \[ " graphify/skill-gemini.md
# 預期：無輸出（或只剩 Step 7d 的 python3，已確認不需改）
```

---

## 修改摘要

| Task | 位置 | 改動 |
|------|------|------|
| A | Step 9 清理 | `rm -f` 兩行改為雙平台行內註解 |
| B | Interpreter guard | `if [ ! -f ... ]` / `which` 整段改為雙 fenced block |
| C | `--update` 備份/清理 | `cp` 和 `rm -f` 改為雙平台 bullet list |
