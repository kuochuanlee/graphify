"""
graphify/split.py

Book auto-split pre-processor.

Detects a single large .md/.txt file in the corpus and splits it into
chapter-aligned chunks before extraction begins. Chunks are written to
graphify-out/book_chunks/ so the SHA256 cache stays stable across runs.

每個 chunk 開頭注入 METADATA header（書名 + 涵蓋標題），
讓 LLM 在跨章節 chunk 邊界時能正確進行指代消解。
"""

from __future__ import annotations

import re
from pathlib import Path

# -- 可調整常數 -------------------------------------------------------
BOOK_CHAR_THRESHOLD = 50_000   # 字元數超過此值才視為「書本」
TARGET_CHUNK_SIZE   = 2_000    # 目標累積字數（在此大小附近的 ## 邊界切斷）
MAX_CHUNK_SIZE      = 3_500    # 超過此值強制在下一個 ## 邊界切斷
CHUNK_DIR_NAME      = "book_chunks"  # 輸出子目錄名稱（在 graphify-out/ 底下）
# ---------------------------------------------------------------------


def is_large_single_doc(paths: list[Path]) -> Path | None:
    """
    檢查檔案清單是否符合「單一大型文件」條件。

    條件：
      - .md 或 .txt 檔案恰好只有 1 個
      - 該檔案字元數 >= BOOK_CHAR_THRESHOLD

    符合時回傳該 Path，否則回傳 None。
    """
    doc_files = [p for p in paths if p.suffix in (".md", ".txt")]
    if len(doc_files) != 1:
        return None
    candidate = doc_files[0]
    try:
        text = candidate.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if len(text) >= BOOK_CHAR_THRESHOLD:
        return candidate
    return None


def _make_slug(title_line: str, max_len: int = 40) -> str:
    """
    把 Markdown 標題行轉成適合用於檔名的 slug。

    修正：
    - 全形空格、半形空格、常見標點先統一換成單一底線
    - 再去掉其他非中文、非英數、非底線的雜訊字元
    - 中文字之間不插入額外底線

    例："## 第三章：智能爆炸的來臨" -> "第三章_智能爆炸的來臨"
    例："# 奇點已近"               -> "奇點已近"
    """
    # 去掉前綴的 # 符號與緊跟的空白
    title = re.sub(r"^#+\s*", "", title_line).strip()
    # 步驟一：把空白類、常見標點換成單一底線
    slug = re.sub(r"[\s\.\u3000：:　·・•《》【】「」『』（）()]+", "_", title)
    # 步驟二：去掉其他非中文、非英數、非底線的字元
    slug = re.sub(r"[^\w\u4e00-\u9fff]", "", slug)
    # 步驟三：清理頭尾多餘底線，壓縮連續底線
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug[:max_len] if slug else "untitled"


def split_book(source: Path, out_dir: Path) -> list[Path]:
    """
    將單一大型 Markdown 檔案依章節結構拆分為多個小檔案。

    拆分規則：
      - H1 （# ）：強制切斷，章標題附加到下一個 chunk 開頭
      - H2 （## ）邊界：若累積字數 >= TARGET_CHUNK_SIZE 則切斷
      - 累積字數 >= MAX_CHUNK_SIZE 時，下一個 ## 強制切斷
      - 單一 ## 超過 MAX_CHUNK_SIZE 時單獨成一份

    每個 chunk 開頭注入 METADATA header，包含書名與該 chunk 涵蓋的標題。
    輸出檔名格式：001_slug.md, 002_slug.md, ...
    回傳產生的 Path 清單，依序排列。
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    lines = source.read_text(encoding="utf-8").splitlines(keepends=True)

    # -- 狀態變數 -----------------------------------------------------
    chunks: list[Path] = []
    current_lines: list[str] = []
    current_size: int = 0
    current_chapter_title: str = ""   # 最近一個 H1 標題，用於命名
    current_section_title: str = ""   # 最近一個 H2 標題，用於命名
    chunk_index: int = 1
    pending_h1: str | None = None     # 尚未附加到 chunk 的 H1 標題行

    # METADATA header 相關狀態
    current_chunk_headings: list[str] = []   # 收集本 chunk 的標題，供 METADATA header 使用
    book_title: str = source.stem            # 書名：取來源檔名（不含副檔名）
    # -----------------------------------------------------------------

    def flush() -> None:
        """將 current_lines 寫出為一個 chunk 檔案，並注入 METADATA header。"""
        nonlocal chunk_index, current_lines, current_size, current_chunk_headings

        if not current_lines:
            return

        # 組合 METADATA header
        headings_str = " | ".join(current_chunk_headings) if current_chunk_headings else ""
        metadata_header = (
            f"[[METADATA_START]]\n"
            f"Book: {book_title}\n"
            f"Headings in this chunk: {headings_str}\n"
            f"[[METADATA_END]]\n\n"
        )

        # 優先用 H1 章標題當前綴 + H2 節標題，讓檔名更有意義
        if current_chapter_title and current_section_title:
            title_for_slug = current_chapter_title + "_" + current_section_title
        elif current_chapter_title:
            title_for_slug = current_chapter_title
        elif current_section_title:
            title_for_slug = current_section_title
        else:
            title_for_slug = "untitled"

        slug = _make_slug(title_for_slug)
        fname = out_dir / f"{chunk_index:03d}_{slug}.md"
        fname.write_text(metadata_header + "".join(current_lines), encoding="utf-8")
        chunks.append(fname)

        chunk_index += 1
        current_lines = []
        current_size = 0
        current_chunk_headings = []   # flush 後清空標題收集

    for line in lines:
        is_h1 = bool(re.match(r"^# (?!#)", line))   # 恰好一個 #
        is_h2 = bool(re.match(r"^## (?!#)", line))  # 恰好兩個 #

        if is_h1:
            # H1：強制切斷現有 chunk，H1 標題行暫存，附到下個 chunk 開頭
            flush()
            current_chapter_title = line
            current_section_title = ""
            pending_h1 = line          # 不立刻加入，等下一行進來時一起附加

            # flush 後重置標題收集，並加入本 H1 標題
            current_chunk_headings = []
            current_chunk_headings.append(line.strip())
            continue

        if is_h2:
            # H2：檢查是否需要切斷
            should_cut = current_size >= TARGET_CHUNK_SIZE
            if should_cut and current_lines:
                flush()
                # 切斷後，把懸掛的 H1 標題帶到新 chunk
                if pending_h1:
                    current_chunk_headings.append(pending_h1.strip())
                    current_lines.append(pending_h1)
                    current_size += len(pending_h1)
                    pending_h1 = None
            else:
                # 不切斷時才消費 pending_h1（避免重複）
                if pending_h1:
                    current_lines.append(pending_h1)
                    current_size += len(pending_h1)
                    pending_h1 = None

            # 收集 H2 標題（在 flush 之後，確保標題歸屬正確的 chunk）
            current_chunk_headings.append(line.strip())

            current_section_title = line
            current_lines.append(line)
            current_size += len(line)
            continue

        # 一般行：先消費 pending_h1（若有）
        if pending_h1:
            current_lines.append(pending_h1)
            current_size += len(pending_h1)
            pending_h1 = None

        current_lines.append(line)
        current_size += len(line)

    # 收尾：最後剩餘的內容
    if pending_h1 and not current_lines:
        current_lines.append(pending_h1)
    flush()

    return chunks
