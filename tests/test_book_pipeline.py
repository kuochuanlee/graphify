"""tests/test_book_pipeline.py

端對端自動測試：book mode pipeline。

使用 tests/fixtures/sample_book/ 的小型合成書本，
mock BOOK_CHAR_THRESHOLD 降低門檻，
並用假的 LLM chunk 結果模擬語意提取，
驗證 detect -> book-prepare -> merge-semantic -> merge-all -> build -> export 全流程。
"""

import json
import shutil
from pathlib import Path
from unittest import mock

import pytest

# 測試用的常數
FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_BOOK_DIR = FIXTURES / "sample_book"
SAMPLE_BOOK_FILE = SAMPLE_BOOK_DIR / "the_future_of_ai.md"


def _make_fake_chunk_result(chunk_index: int) -> dict:
    """產生假的 LLM 語意提取結果，模擬 .graphify_chunk_N.json 的格式。"""
    return {
        "nodes": [
            {
                "id": f"claim_{chunk_index}_1",
                "type": "Claim",
                "content": f"Test claim from chunk {chunk_index}",
                "aliases": [],
                "confidence_score": 0.9,
                "source_chunk": f"chunk_{chunk_index:03d}.md",
            },
            {
                "id": f"evidence_{chunk_index}_1",
                "type": "Evidence",
                "content": f"Test evidence from chunk {chunk_index}",
                "aliases": [],
                "confidence_score": 0.85,
                "source_chunk": f"chunk_{chunk_index:03d}.md",
            },
        ],
        "edges": [
            {
                "source": f"evidence_{chunk_index}_1",
                "target": f"claim_{chunk_index}_1",
                "type": "supports",
                "confidence_score": 0.88,
            },
        ],
        "hyperedges": [],
    }


class TestBookPipelineEndToEnd:
    """端對端測試：模擬 book mode 的完整 pipeline 流程。"""

    def test_detect_recognizes_book_mode(self, tmp_path):
        """detect 應能偵測出 book_mode=True。"""
        from graphify.detect import detect

        # mock 門檻值，讓小檔案也能觸發 book mode
        # is_large_single_doc 內部讀取 split.BOOK_CHAR_THRESHOLD
        with mock.patch("graphify.split.BOOK_CHAR_THRESHOLD", 100):
            result = detect(SAMPLE_BOOK_DIR)

        assert result.get("book_mode") is True
        assert result.get("book_file") is not None

    def test_full_pipeline_with_mock_llm(self, tmp_path):
        """完整 pipeline 流程（用假 LLM 結果）。"""
        import graphify.pipeline as pipeline

        # 設定輸出目錄到 tmp_path
        out_dir = tmp_path / "graphify-out"
        out_dir.mkdir()
        pipeline.OUT_DIR = out_dir

        # -- Step 1: detect --
        # mock 門檻值加上手動建構 detect 結果
        book_file_str = str(SAMPLE_BOOK_FILE)
        detect_result = {
            "book_mode": True,
            "book_file": book_file_str,
            "total_files": 1,
            "total_words": 500,
            "files": {"document": [book_file_str]},
            "skipped_sensitive": [],
        }
        pipeline._save_json(".graphify_detect.json", detect_result)

        # -- Step 2: book-prepare --
        pipeline.cmd_book_prepare()

        # 驗證 chunks 產生
        chunk_dir = out_dir / "book_chunks"
        assert chunk_dir.exists(), "book_chunks 目錄應存在"
        chunk_files = sorted(chunk_dir.glob("*.md"))
        assert len(chunk_files) >= 1, "應產生至少 1 個 chunk"

        # 驗證 prompt 檔案產生
        prompt_files = sorted((out_dir / "prompts").glob("*.txt"))
        assert len(prompt_files) == len(chunk_files), \
            "prompt 檔案數量應等於 chunk 數量"

        # 驗證每個 chunk 都有 METADATA header
        for cf in chunk_files:
            text = cf.read_text(encoding="utf-8")
            assert text.startswith("[[METADATA_START]]"), \
                f"{cf.name} 缺少 METADATA header"
            assert "Images in this chunk:" in text, \
                f"{cf.name} 缺少 Images 行"

        # 驗證 AST stub 存在且為空
        ast_data = pipeline._load_json(".graphify_ast.json")
        assert ast_data["nodes"] == []
        assert ast_data["edges"] == []

        # -- Step 3: 模擬 LLM 語意提取（寫入假的 chunk 結果）--
        for i in range(1, len(chunk_files) + 1):
            fake_result = _make_fake_chunk_result(i)
            (out_dir / "chunks" / f"{i}.json").write_text(
                json.dumps(fake_result, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        # -- Step 4: merge-semantic --
        pipeline.cmd_merge_semantic()

        # 驗證語意合併結果存在
        semantic_path = out_dir / ".graphify_semantic.json"
        assert semantic_path.exists(), ".graphify_semantic.json 應存在"
        semantic = json.loads(semantic_path.read_text(encoding="utf-8"))
        assert len(semantic["nodes"]) > 0, "應有合併後的節點"
        assert len(semantic["edges"]) > 0, "應有合併後的邊"

        # -- Step 5: merge-all --
        pipeline.cmd_merge_all()

        extract_path = out_dir / ".graphify_extract.json"
        assert extract_path.exists(), ".graphify_extract.json 應存在"

        # -- Step 6: build --
        pipeline.cmd_build([str(SAMPLE_BOOK_DIR)])

        # 驗證圖譜產出
        graph_path = out_dir / "graph.json"
        assert graph_path.exists(), "graph.json 應存在"
        graph_data = json.loads(graph_path.read_text(encoding="utf-8"))
        assert len(graph_data["nodes"]) > 0, "圖譜應有節點"

        # 驗證報告產出
        report_path = out_dir / "GRAPH_REPORT.md"
        assert report_path.exists(), "GRAPH_REPORT.md 應存在"

        # 驗證分析結果
        analysis_path = out_dir / ".graphify_analysis.json"
        assert analysis_path.exists(), ".graphify_analysis.json 應存在"

        # -- Step 7: export --obsidian --
        pipeline.cmd_export(["--obsidian"])

        # 驗證 HTML 輸出
        html_path = out_dir / "graph.html"
        assert html_path.exists(), "graph.html 應存在"

        # 驗證 Obsidian vault
        obsidian_dir = out_dir / "obsidian"
        assert obsidian_dir.exists(), "obsidian/ 目錄應存在"
        md_files = list(obsidian_dir.glob("*.md"))
        assert len(md_files) > 0, "obsidian/ 下應有 .md 檔案"

    def test_chunks_have_image_references(self, tmp_path):
        """包含圖片的書本，至少一個 chunk 的 METADATA 應有圖片路徑。"""
        import graphify.pipeline as pipeline

        out_dir = tmp_path / "graphify-out"
        out_dir.mkdir()
        pipeline.OUT_DIR = out_dir

        # 建構 detect 結果
        detect_result = {
            "book_mode": True,
            "book_file": str(SAMPLE_BOOK_FILE),
            "total_files": 1,
            "total_words": 500,
            "files": {"document": [str(SAMPLE_BOOK_FILE)]},
            "skipped_sensitive": [],
        }
        pipeline._save_json(".graphify_detect.json", detect_result)

        # 執行 book-prepare
        pipeline.cmd_book_prepare()

        # 檢查至少一個 chunk 的 METADATA 包含圖片路徑
        chunk_dir = out_dir / "book_chunks"
        found_images = False
        for cf in sorted(chunk_dir.glob("*.md")):
            text = cf.read_text(encoding="utf-8")
            for line in text.splitlines():
                if line.startswith("Images in this chunk:") and "images/" in line:
                    found_images = True
                    break

        assert found_images, \
            "sample_book 包含圖片引用，至少一個 chunk 應收集到圖片路徑"

    def test_node_types_are_claim_or_evidence(self, tmp_path):
        """book mode 的節點 type 應只有 Claim 或 Evidence。"""
        import graphify.pipeline as pipeline

        out_dir = tmp_path / "graphify-out"
        out_dir.mkdir()
        pipeline.OUT_DIR = out_dir

        # 建構 detect 結果
        detect_result = {
            "book_mode": True,
            "book_file": str(SAMPLE_BOOK_FILE),
            "total_files": 1,
            "total_words": 500,
            "files": {"document": [str(SAMPLE_BOOK_FILE)]},
            "skipped_sensitive": [],
        }
        pipeline._save_json(".graphify_detect.json", detect_result)
        pipeline.cmd_book_prepare()

        # 模擬 LLM 結果
        chunk_count = len(list((out_dir / "book_chunks").glob("*.md")))
        for i in range(1, chunk_count + 1):
            fake = _make_fake_chunk_result(i)
            (out_dir / "chunks" / f"{i}.json").write_text(
                json.dumps(fake, ensure_ascii=False),
                encoding="utf-8",
            )

        # 跑完後半段 pipeline
        pipeline.cmd_merge_semantic()
        pipeline.cmd_merge_all()
        pipeline.cmd_build([str(SAMPLE_BOOK_DIR)])

        # 驗證節點類型
        graph = json.loads(
            (out_dir / "graph.json").read_text(encoding="utf-8")
        )
        valid_types = {"Claim", "Evidence"}
        for node in graph["nodes"]:
            node_type = node.get("type") or node.get("file_type", "")
            if node_type:
                assert node_type in valid_types, \
                    f"節點 {node.get('id')} 的 type '{node_type}' 不在允許範圍內"
