"""tests/test_split.py

測試 graphify.split 模組：is_large_single_doc、split_book 與 METADATA header。
"""

import re
import textwrap
from pathlib import Path
import pytest
from graphify.split import is_large_single_doc, split_book, BOOK_CHAR_THRESHOLD


# -- 輔助函式 ----------------------------------------------------------

def _strip_metadata(text: str) -> str:
    """移除 chunk 開頭的 METADATA header 區塊，用於內容比對。"""
    return re.sub(
        r"^\[\[METADATA_START\]\].*?\[\[METADATA_END\]\]\n\n",
        "",
        text,
        flags=re.DOTALL,
    )


def make_book(tmp_path: Path, char_count: int = BOOK_CHAR_THRESHOLD + 1000) -> Path:
    """建立一個超過門檻的假書 .md 檔案。"""
    content_parts = ["# 第一章 序言\n"]

    # 產生多個 ## 段落，每段約 1000 字元，總量超過 char_count
    section_len = 1000
    num_sections = (char_count // section_len) + 1

    for i in range(num_sections):
        content_parts.append(f"\n## 1.{i+1} 測試段落\n\n")
        # 確保每段真的填滿 section_len 的字元數
        content_parts.append("這是測試內容。" * (section_len // len("這是測試內容。")))

    content = "".join(content_parts)
    book = tmp_path / "book.md"
    book.write_text(content, encoding="utf-8")
    return book


# -- is_large_single_doc -----------------------------------------------

class TestIsLargeSingleDoc:

    def test_returns_none_when_multiple_md_files(self, tmp_path):
        (tmp_path / "a.md").write_text("x" * BOOK_CHAR_THRESHOLD, encoding="utf-8")
        (tmp_path / "b.md").write_text("y" * BOOK_CHAR_THRESHOLD, encoding="utf-8")
        paths = list(tmp_path.glob("*.md"))
        assert is_large_single_doc(paths) is None

    def test_returns_none_when_file_too_small(self, tmp_path):
        small = tmp_path / "small.md"
        small.write_text("短文件", encoding="utf-8")
        assert is_large_single_doc([small]) is None

    def test_returns_path_when_single_large_md(self, tmp_path):
        book = make_book(tmp_path)
        assert is_large_single_doc([book]) == book

    def test_returns_path_when_single_large_txt(self, tmp_path):
        txt = tmp_path / "book.txt"
        txt.write_text("內容" * BOOK_CHAR_THRESHOLD, encoding="utf-8")
        assert is_large_single_doc([txt]) == txt

    def test_ignores_non_doc_files(self, tmp_path):
        """有圖片等非文件檔案時，只要 .md 只有一個就觸發。"""
        book = make_book(tmp_path)
        img = tmp_path / "cover.png"
        img.write_bytes(b"\x89PNG")
        assert is_large_single_doc([book, img]) == book


# -- split_book ---------------------------------------------------------

class TestSplitBook:

    def test_produces_multiple_chunks(self, tmp_path):
        book = make_book(tmp_path)
        out = tmp_path / "chunks"
        result = split_book(book, out)
        assert len(result) >= 2, "書本應被拆成至少 2 個 chunk"

    def test_chunks_are_valid_markdown_files(self, tmp_path):
        book = make_book(tmp_path)
        out = tmp_path / "chunks"
        for chunk in split_book(book, out):
            assert chunk.exists()
            assert chunk.suffix == ".md"
            assert len(chunk.read_text(encoding="utf-8")) > 0

    def test_no_chunk_exceeds_hard_limit(self, tmp_path):
        """除非單一 ## 本身就超大，否則每個 chunk 不應超過 MAX_CHUNK_SIZE 太多。"""
        from graphify.split import MAX_CHUNK_SIZE
        book = make_book(tmp_path)
        out = tmp_path / "chunks"
        for chunk in split_book(book, out):
            # 去掉 METADATA header 後檢查實際內容大小
            content = _strip_metadata(chunk.read_text(encoding="utf-8"))
            size = len(content)
            # 允許單一 ## 自身超過限制，但不應超過 2 倍
            assert size < MAX_CHUNK_SIZE * 2, f"{chunk.name} 太大：{size} 字元"

    def test_chunks_cover_all_content(self, tmp_path):
        """所有 chunk 合併後的內容字元數應接近原始檔案（允許 +/- 5% 誤差）。"""
        book = make_book(tmp_path)
        original_size = len(book.read_text(encoding="utf-8"))
        out = tmp_path / "chunks"
        chunks = split_book(book, out)
        # 去掉 METADATA header 後計算實際內容大小
        total = sum(
            len(_strip_metadata(c.read_text(encoding="utf-8")))
            for c in chunks
        )
        assert abs(total - original_size) / original_size < 0.05

    def test_h1_never_spans_chunks(self, tmp_path):
        """H1 章標題絕不出現在 chunk 中間（除了開頭）。"""
        book = make_book(tmp_path)
        out = tmp_path / "chunks"
        for chunk in split_book(book, out):
            # 去掉 METADATA header 後檢查 H1 位置
            content = _strip_metadata(chunk.read_text(encoding="utf-8"))
            lines = content.splitlines()
            h1_positions = [
                i for i, l in enumerate(lines) if re.match(r"^# (?!#)", l)
            ]
            # H1 只能出現在內容開頭（第 0 行），不能出現在中間
            for pos in h1_positions:
                assert pos == 0, f"{chunk.name} 的第 {pos} 行出現 H1，應只在開頭"

    def test_filenames_are_sequential(self, tmp_path):
        """輸出檔名應為 001_xxx.md, 002_xxx.md 的格式。"""
        book = make_book(tmp_path)
        out = tmp_path / "chunks"
        for i, chunk in enumerate(split_book(book, out), start=1):
            assert re.match(rf"^{i:03d}_", chunk.name), \
                f"第 {i} 個 chunk 的檔名格式不符：{chunk.name}"

    def test_empty_book_returns_empty(self, tmp_path):
        empty = tmp_path / "empty.md"
        empty.write_text("", encoding="utf-8")
        out = tmp_path / "chunks"
        result = split_book(empty, out)
        assert result == []

    def test_book_without_headers_becomes_single_chunk(self, tmp_path):
        """沒有任何標題的純文字，應輸出為單一 chunk。"""
        flat = tmp_path / "flat.md"
        flat.write_text("純文字內容。\n" * 500, encoding="utf-8")
        out = tmp_path / "chunks"
        result = split_book(flat, out)
        assert len(result) == 1

    def test_reuse_existing_chunks(self, tmp_path):
        """
        若 out_dir 已有 chunk 檔案，split_book 不應被重複呼叫。
        （這個測試是測 detect.py 的 existing_chunks 邏輯）
        """
        book = make_book(tmp_path)
        out = tmp_path / "chunks"
        first_run = split_book(book, out)
        second_run = sorted(out.glob("*.md"))
        # 第二次直接讀目錄，結果應相同
        assert [p.name for p in first_run] == [p.name for p in second_run]


# -- METADATA header 驗證 -----------------------------------------------

class TestMetadataHeader:

    def test_chunks_have_metadata_header(self, tmp_path):
        """每個 chunk 都應以 [[METADATA_START]] 開頭。"""
        book = make_book(tmp_path)
        out = tmp_path / "chunks"
        for chunk in split_book(book, out):
            text = chunk.read_text(encoding="utf-8")
            assert text.startswith("[[METADATA_START]]"), \
                f"{chunk.name} 缺少 METADATA header"
            assert "[[METADATA_END]]" in text, \
                f"{chunk.name} 缺少 METADATA_END"

    def test_metadata_contains_book_title(self, tmp_path):
        """METADATA header 的 Book 行應包含書名（來源檔名不含副檔名）。"""
        book = make_book(tmp_path)
        out = tmp_path / "chunks"
        chunks = split_book(book, out)
        first_text = chunks[0].read_text(encoding="utf-8")
        # source.stem = "book"
        assert "Book: book" in first_text

    def test_metadata_contains_headings(self, tmp_path):
        """METADATA header 的 Headings 行應包含 chunk 內的 H1/H2 標題。"""
        book = make_book(tmp_path)
        out = tmp_path / "chunks"
        chunks = split_book(book, out)

        # 第一個 chunk 的 METADATA 應包含 H1 標題
        first_text = chunks[0].read_text(encoding="utf-8")
        headings_lines = [
            l for l in first_text.splitlines()
            if l.startswith("Headings in this chunk:")
        ]
        assert len(headings_lines) == 1, "應有恰好一行 Headings"
        assert "第一章" in headings_lines[0], "第一個 chunk 應包含 H1 章標題"

    def test_metadata_format_structure(self, tmp_path):
        """METADATA header 的格式應為固定的四行結構 + 空行分隔。"""
        book = make_book(tmp_path)
        out = tmp_path / "chunks"
        chunks = split_book(book, out)
        first_text = chunks[0].read_text(encoding="utf-8")
        lines = first_text.splitlines()

        # 前四行是 METADATA 結構
        assert lines[0] == "[[METADATA_START]]"
        assert lines[1].startswith("Book: ")
        assert lines[2].startswith("Headings in this chunk: ")
        assert lines[3] == "[[METADATA_END]]"
        # 第五行是空行分隔
        assert lines[4] == ""

    def test_no_header_book_has_empty_headings(self, tmp_path):
        """沒有任何標題的書本，METADATA 的 Headings 行應為空。"""
        flat = tmp_path / "flat.md"
        flat.write_text("純文字內容。\n" * 500, encoding="utf-8")
        out = tmp_path / "chunks"
        chunks = split_book(flat, out)
        text = chunks[0].read_text(encoding="utf-8")
        assert "Headings in this chunk: \n" in text or \
               "Headings in this chunk: \r\n" in text
