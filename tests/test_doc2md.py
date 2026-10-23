"""
Comprehensive test suite for doc2md-cli.
TDD coverage: Text normalization, GFM pipe tables, DOCX/PPTX parsing,
PDF extraction via pypdf, boilerplate/header-footer deduplication,
token estimation & chunking, and CLI interactive mode.
"""
import io
import json
import os
import zipfile
import pytest
from pypdf import PdfWriter

from doc2md.core import (
    clean_text_for_llm,
    format_as_gfm_table,
    strip_boilerplate_headers,
    chunk_markdown,
    convert_to_markdown,
    DocumentResult,
)
from doc2md.cli import main


# ---------------------------------------------------------------------------
# Text Normalization & Table Formatting Tests
# ---------------------------------------------------------------------------

def test_clean_text_for_llm():
    dirty = "Line 1\r\nLine 2   with   spaces.\n\n\n\nLine 3\r"
    cleaned = clean_text_for_llm(dirty)
    assert "\r" not in cleaned
    assert "\n\n\n" not in cleaned
    assert "Line 2 with spaces." in cleaned


def test_format_as_gfm_table():
    rows = [
        ["Header 1", "Header 2", "Header 3"],
        ["Cell 1", "Cell 2", "Cell 3"],
        ["Val A", "Val B", "Val C"],
    ]
    table_md = format_as_gfm_table(rows)
    lines = table_md.strip().splitlines()
    assert len(lines) == 4
    assert lines[0] == "| Header 1 | Header 2 | Header 3 |"
    assert lines[1] == "| --- | --- | --- |"
    assert lines[2] == "| Cell 1 | Cell 2 | Cell 3 |"


def test_strip_boilerplate_headers():
    pages = [
        "Confidential Document 2026\nActual content of page 1.\nPage 1 of 3",
        "Confidential Document 2026\nActual content of page 2.\nPage 2 of 3",
        "Confidential Document 2026\nActual content of page 3.\nPage 3 of 3",
    ]
    cleaned_pages = strip_boilerplate_headers(pages)
    assert len(cleaned_pages) == 3
    # Repetitive top header should be stripped
    assert "Confidential Document 2026" not in cleaned_pages[0]
    assert "Confidential Document 2026" not in cleaned_pages[1]
    assert "Actual content of page 1." in cleaned_pages[0]


def test_chunk_markdown():
    text = "Paragraph 1 is here.\n\nParagraph 2 has more text.\n\nParagraph 3 is the final part."
    chunks = chunk_markdown(text, chunk_size=35)
    assert len(chunks) >= 2
    for c in chunks:
        assert len(c) <= 60  # Allows boundary padding


# ---------------------------------------------------------------------------
# Document Format Converters (TXT, DOCX, PPTX, PDF)
# ---------------------------------------------------------------------------

def test_convert_txt_file(tmp_path):
    txt_file = tmp_path / "sample.txt"
    txt_file.write_text("# Title\n\nThis is a plain text file for testing.", encoding="utf-8")

    res: DocumentResult = convert_to_markdown(str(txt_file))
    assert res.format == "txt"
    assert "# Title" in res.markdown_text
    assert res.estimated_tokens > 0


def test_convert_docx_mock(tmp_path):
    docx_file = tmp_path / "sample.docx"

    # Create mock DOCX (ZIP containing word/document.xml)
    doc_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
        <w:body>
            <w:p>
                <w:pPr><w:pStyle w:val="Heading1"/></w:pPr>
                <w:r><w:t>Project Architecture</w:t></w:r>
            </w:p>
            <w:p>
                <w:r><w:t>Overview of system design.</w:t></w:r>
            </w:p>
            <w:tbl>
                <w:tr>
                    <w:tc><w:p><w:r><w:t>Service</w:t></w:r></w:p></w:tc>
                    <w:tc><w:p><w:r><w:t>Port</w:t></w:r></w:p></w:tc>
                </w:tr>
                <w:tr>
                    <w:tc><w:p><w:r><w:t>API</w:t></w:r></w:p></w:tc>
                    <w:tc><w:p><w:r><w:t>8080</w:t></w:r></w:p></w:tc>
                </w:tr>
            </w:tbl>
        </w:body>
    </w:document>"""

    with zipfile.ZipFile(str(docx_file), "w") as z:
        z.writestr("word/document.xml", doc_xml)

    res = convert_to_markdown(str(docx_file), extract_tables=True)
    assert res.format == "docx"
    assert "# Project Architecture" in res.markdown_text
    assert "Overview of system design." in res.markdown_text
    assert "| Service | Port |" in res.markdown_text
    assert "| API | 8080 |" in res.markdown_text


def test_convert_pptx_mock(tmp_path):
    pptx_file = tmp_path / "presentation.pptx"

    # Create mock PPTX (ZIP containing ppt/slides/slide1.xml)
    slide_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
           xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
        <p:cSld>
            <p:spTree>
                <p:sp>
                    <p:txBody>
                        <a:p><a:r><a:t>Q3 Strategic Review</a:t></a:r></a:p>
                    </p:txBody>
                </p:sp>
                <p:sp>
                    <p:txBody>
                        <a:p><a:r><a:t>Key Objective 1: Cloud Migration</a:t></a:r></a:p>
                        <a:p><a:r><a:t>Key Objective 2: Cost Reduction</a:t></a:r></a:p>
                    </p:txBody>
                </p:sp>
            </p:spTree>
        </p:cSld>
    </p:sld>"""

    with zipfile.ZipFile(str(pptx_file), "w") as z:
        z.writestr("ppt/slides/slide1.xml", slide_xml)

    res = convert_to_markdown(str(pptx_file))
    assert res.format == "pptx"
    assert "<!-- Slide 1 -->" in res.markdown_text
    assert "Q3 Strategic Review" in res.markdown_text
    assert "Key Objective 1: Cloud Migration" in res.markdown_text


def test_convert_pdf_real(tmp_path):
    pdf_file = tmp_path / "document.pdf"

    # Generate genuine PDF using pypdf.PdfWriter
    writer = PdfWriter()
    page1 = writer.add_blank_page(width=300, height=300)
    writer.write(str(pdf_file))

    res = convert_to_markdown(str(pdf_file))
    assert res.format == "pdf"
    assert res.total_pages == 1


# ---------------------------------------------------------------------------
# CLI Commands and Interactive Mode Tests
# ---------------------------------------------------------------------------

def test_cli_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "doc2md-cli" in captured.out or "0.1.0" in captured.out


def test_cli_convert_to_file(tmp_path):
    txt_file = tmp_path / "notes.txt"
    out_file = tmp_path / "notes.md"
    txt_file.write_text("Meeting notes for team.", encoding="utf-8")

    exit_code = main([str(txt_file), "-o", str(out_file), "-q"])
    assert exit_code == 0
    assert out_file.exists()
    assert "Meeting notes for team." in out_file.read_text(encoding="utf-8")


def test_cli_json_mode(tmp_path, capsys):
    txt_file = tmp_path / "info.txt"
    txt_file.write_text("JSON payload test line.", encoding="utf-8")

    exit_code = main([str(txt_file), "--json"])
    assert exit_code == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["format"] == "txt"
    assert "JSON payload test line." in data["markdown"]


def test_cli_interactive_wizard(tmp_path, monkeypatch, capsys):
    doc_file = tmp_path / "doc.txt"
    doc_file.write_text("Interactive wizard test.", encoding="utf-8")
    out_file = tmp_path / "doc.md"

    # Inputs:
    # 1. file path
    # 2. output mode: 2 (Save to file)
    # 3. destination path
    # 4. extract tables: y
    # 5. strip headers: y
    # 6. chunk size: (empty, no chunking)
    inputs = iter([
        str(doc_file),
        "2",
        str(out_file),
        "y",
        "y",
        "",
    ])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    exit_code = main(["--interactive"])
    assert exit_code == 0
    assert out_file.exists()
