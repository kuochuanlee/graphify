# Graphify — Gemini CLI 支援補充計畫（跨平台修正）

> **執行對象：Gemini (Antigravity)**
> 本文件是 `GEMINI_IMPL_PLAN.md` 的追加補丁，專門修正 `skill-gemini.md` 在 Windows (PowerShell) 環境下的相容性問題。
> **前提：** 原始計畫的所有任務已完成。本計畫僅修改 `graphify/skill-gemini.md` 一個檔案。

---

## 背景

`skill-gemini.md` 目前繼承自 `skill.md`（Bash 語法）。
在 Windows 上，Gemini CLI 使用 PowerShell 執行 shell 指令，Bash 語法會直接報錯。
`skill-windows.md` 已有完整的 PowerShell 對應版本可以參考。

修正策略：**方案三（雙版本並列）** ——
在每個含有 shell 控制流的位置，同時提供 Bash（Linux/macOS/WSL）和 PowerShell（Windows）兩套語法，
由 Gemini 在執行時依作業系統自行選用。

純 Python 的 `-c "..."` 指令本身跨平台可用，**不需要修改**。
需要修改的只有 shell 控制流、背景執行、和 `rm` 等純 shell 指令。

---

## 需要修改的位置清單（共 5 處）

| # | 位置 | 問題語法 | 原因 |
|---|------|---------|------|
| 1 | Step 1（安裝偵測） | `which`, `head`, `case`, `if/fi`, `2>/dev/null`, `2>&1 \| tail` | 全是 Bash-only |
| 2 | Step B2（平行分派） | `for/do/done`, `seq`, `$(cat ...)`, `2>&1 &`, `wait` | 核心問題，已在原計畫提及但只給 Bash |
| 3 | Step B3（清理暫存） | `rm -f ...` | Windows 無 `rm`，要用 `Remove-Item` |
| 4 | `--watch` 指令 | `python3 -m graphify.watch` | Windows 慣用 `python`，且需說明背景執行方式 |
| 5 | Step 1 說明文字 | `$(cat graphify-out/.graphify_python)` | 此語法貫穿全文，需在開頭說明 Windows 的對應讀法 |

---

## Task 1：修改 Step 1 — 安裝偵測

### 位置

找到以下整段（第 60-81 行附近）：

```markdown
### Step 1 - Ensure graphify is installed

```bash
# Detect the correct Python interpreter (handles pipx, venv, system installs)
GRAPHIFY_BIN=$(which graphify 2>/dev/null)
if [ -n "$GRAPHIFY_BIN" ]; then
    PYTHON=$(head -1 "$GRAPHIFY_BIN" | tr -d '#!')
    case "$PYTHON" in
        *[!a-zA-Z0-9/_.-]*) PYTHON="python3" ;;
    esac
else
    PYTHON="python3"
fi
"$PYTHON" -c "import graphify" 2>/dev/null || "$PYTHON" -m pip install graphifyy -q 2>/dev/null || "$PYTHON" -m pip install graphifyy -q --break-system-packages 2>&1 | tail -3
# Write interpreter path for all subsequent steps (persists across invocations)
mkdir -p graphify-out
"$PYTHON" -c "import sys; open('graphify-out/.graphify_python', 'w').write(sys.executable)"
```

If the import succeeds, print nothing and move straight to Step 2.

**In every subsequent bash block, replace `python3` with `$(cat graphify-out/.graphify_python)` to use the correct interpreter.**
```

### 改成

````markdown
### Step 1 - Ensure graphify is installed

**Detect your OS first, then use the matching block.**

**Bash (Linux / macOS / WSL):**
```bash
# Detect the correct Python interpreter (handles pipx, venv, system installs)
GRAPHIFY_BIN=$(which graphify 2>/dev/null)
if [ -n "$GRAPHIFY_BIN" ]; then
    PYTHON=$(head -1 "$GRAPHIFY_BIN" | tr -d '#!')
    case "$PYTHON" in
        *[!a-zA-Z0-9/_.-]*) PYTHON="python3" ;;
    esac
else
    PYTHON="python3"
fi
"$PYTHON" -c "import graphify" 2>/dev/null || "$PYTHON" -m pip install graphifyy -q 2>/dev/null || "$PYTHON" -m pip install graphifyy -q --break-system-packages 2>&1 | tail -3
mkdir -p graphify-out
"$PYTHON" -c "import sys; open('graphify-out/.graphify_python', 'w').write(sys.executable)"
```

**PowerShell (Windows):**
```powershell
python -c "import graphify" 2>$null
if ($LASTEXITCODE -ne 0) { pip install graphifyy -q 2>&1 | Select-Object -Last 3 }
New-Item -ItemType Directory -Force -Path graphify-out | Out-Null
python -c "import sys; open('graphify-out/.graphify_python', 'w').write(sys.executable)"
```

If the import succeeds, print nothing and move straight to Step 2.

**In every subsequent shell block:**
- **Bash:** replace `python3` with `$(cat graphify-out/.graphify_python)`
- **PowerShell:** replace `python` with `(Get-Content graphify-out/.graphify_python -Raw).Trim()`
````

---

## Task 2：修改 Step B2 — 平行分派（核心修正）

### 位置

找到以下這段（第 151-162 行附近）：

```markdown
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

### 改成

````markdown
**MANDATORY: You MUST dispatch all chunks in parallel. Reading files yourself one-by-one is forbidden - it is 5-10x slower.**

**For Gemini CLI:** Write each chunk's prompt to a temp file first, then dispatch all in parallel.
Detect your OS and use the matching block:

**Bash (Linux / macOS / WSL):**
```bash
for i in $(seq 1 $TOTAL_CHUNKS); do
  gemini --yolo -p "$(cat graphify-out/.graphify_prompt_$i.txt)" \
    > graphify-out/.graphify_chunk_$i.json 2>&1 &
done
wait
```

**PowerShell (Windows):**
```powershell
$jobs = 1..$env:TOTAL_CHUNKS | ForEach-Object {
    $i = $_
    Start-Job -ScriptBlock {
        $prompt = Get-Content "graphify-out/.graphify_prompt_$using:i.txt" -Raw
        gemini --yolo -p $prompt | Out-File "graphify-out/.graphify_chunk_$using:i.json" -Encoding utf8
    }
}
$jobs | Wait-Job | Receive-Job
Remove-Job -Job $jobs
```

**For Claude Code:** Call the Agent tool multiple times IN THE SAME RESPONSE — one call per chunk.
````

---

## Task 3：修改 Step B3 — 清理暫存檔

### 位置

找到以下這行（第 316 行附近）：

```markdown
Clean up temp files: `rm -f graphify-out/.graphify_cached.json graphify-out/.graphify_uncached.txt graphify-out/.graphify_semantic_new.json`
```

### 改成

```markdown
Clean up temp files:

**Bash:** `rm -f graphify-out/.graphify_cached.json graphify-out/.graphify_uncached.txt graphify-out/.graphify_semantic_new.json`

**PowerShell:** `Remove-Item -Force -ErrorAction SilentlyContinue graphify-out/.graphify_cached.json, graphify-out/.graphify_uncached.txt, graphify-out/.graphify_semantic_new.json`
```

---

## Task 4：修改 `--watch` 指令區塊

### 位置

找到以下這段（第 1169-1186 行附近）：

```markdown
## For --watch

Start a background watcher that monitors a folder and auto-updates the graph when files change.

```bash
python3 -m graphify.watch INPUT_PATH --debounce 3
```

Replace INPUT_PATH with the folder to watch. Behavior depends on what changed:
...
Press Ctrl+C to stop.
```

### 改成

````markdown
## For --watch

Start a background watcher that monitors a folder and auto-updates the graph when files change.

**Bash (Linux / macOS / WSL):**
```bash
$(cat graphify-out/.graphify_python) -m graphify.watch INPUT_PATH --debounce 3
```

**PowerShell (Windows):**
```powershell
# Run in a new background job, or open a separate terminal and run:
python -m graphify.watch INPUT_PATH --debounce 3
```

Replace INPUT_PATH with the folder to watch. Behavior depends on what changed:
...
Press Ctrl+C (or `Stop-Job` for PowerShell background jobs) to stop.
````

> **注意：** `...` 代表中間段落（Behavior depends on what changed / Debounce / For agentic workflows）保持原文不變，只替換上下的指令區塊和 Ctrl+C 那行。

---

## 驗證

修改完成後，請確認以下幾點：

1. `skill-gemini.md` 中已不存在任何孤立的 Bash 控制流區塊（`for/do/done`、`if/fi`、`wait`、`rm -f`、`which`），每一個都有對應的 PowerShell 版本並排。
2. 純 Python `-c "..."` 的區塊保持原樣，不需要任何修改。
3. `graphify hook install/uninstall/status` 指令區塊不需要修改（這些是呼叫 Python CLI 的指令，跨平台可用）。
4. 用 grep 確認沒有遺漏：
   ```bash
   grep -n "^for i in\|^wait$\|^rm -f\|which graphify\|2>/dev/null\|2>&1 &" skill-gemini.md
   # 預期：無輸出
   ```

---

## 修改摘要

| 位置 | 改動 |
|------|------|
| Step 1 安裝區塊 | 新增 PowerShell 對應版本；更新 `$(cat ...)` 說明文字加入 PowerShell 讀法 |
| Step B2 平行分派 | 新增 PowerShell 版本（`Start-Job` + `Wait-Job`） |
| Step B3 清理暫存 | 新增 PowerShell 版本（`Remove-Item`） |
| `--watch` 區塊 | 修正 `python3` → 使用動態路徑；新增 PowerShell 說明 |
