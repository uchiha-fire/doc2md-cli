"""
Core extraction and LLM-optimized Markdown generator for doc2md.
Handles PDF, DOCX, PPTX, and TXT with pure Python standards.
Zephyrus Labs (https://zephyrus-labs.tech/)
Lead Developer: Shubham Sharma
"""
import os
import re
import xml.etree.ElementTree as ET
import zipfile
from typing import Any, Dict, List, Optional
from pypdf import PdfReader

PAGE_NUMBER_REGEX = re.compile(r"^\s*(?:Page\s+\d+(?:\s+of\s+\d+)?|\d+\s*/\s*\d+|\b\d+\b)\s*$", re.IGNORECASE)


class DocumentResult:
    """Encapsulates the converted document output with token statistics."""
    def __init__(
        self,
        format: str,
        total_pages: int,
        markdown_text: str,
        word_count: int,
        estimated_tokens: int,
        chunks: Optional[List[str]] = None,
    ):
        self.format = format
        self.total_pages = total_pages
        self.markdown_text = markdown_text
        self.word_count = word_count
        self.estimated_tokens = estimated_tokens
        self.chunks = chunks

    def to_dict(self) -> Dict[str, Any]:
        return {
            "format": self.format,
            "total_pages": self.total_pages,
            "word_count": self.word_count,
            "estimated_tokens": self.estimated_tokens,
            "chunks_count": len(self.chunks) if self.chunks else 1,
            "markdown": self.markdown_text,
        }


def clean_text_for_llm(text: str) -> str:
    """Normalizes whitespace and removes redundant empty lines for token efficiency."""
    text = re.sub(r"\r\n|\r", "\n", text)
    # Remove excessive horizontal spaces while preserving newlines
    text = re.sub(r"[ \t]+", " ", text)
    # Normalize 3+ newlines to standard double newline (paragraphs)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return "\n".join(line.strip() for line in text.splitlines()).strip()


def format_as_gfm_table(rows: List[List[str]]) -> str:
    """Formats a 2D matrix of string cells into a GitHub Flavored Markdown pipe table."""
    if not rows or not any(rows):
        return ""

    # Normalize column count
    max_cols = max(len(r) for r in rows)
    normalized = [r + [""] * (max_cols - len(r)) for r in rows]

    # Clean cell values
    cleaned_rows = [
        [cell.replace("\n", " ").replace("|", "\\|").strip() for cell in r]
        for r in normalized
    ]

    header = cleaned_rows[0]
    separator = ["---"] * max_cols
    body = cleaned_rows[1:]

    lines = []
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join(separator) + " |")
    for row in body:
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)


def strip_boilerplate_headers(pages: List[str]) -> List[str]:
    """
    Detects and prunes repetitive top header and bottom footer noise across multi-page docs.
    """
    if len(pages) <= 1:
        return pages

    header_candidates: Dict[str, int] = {}
    footer_candidates: Dict[str, int] = {}

    page_lines_list = [p.splitlines() for p in pages]

    for lines in page_lines_list:
        clean_lines = [l.strip() for l in lines if l.strip()]
        if not clean_lines:
            continue
        first_line = clean_lines[0]
        last_line = clean_lines[-1]
        header_candidates[first_line] = header_candidates.get(first_line, 0) + 1
        footer_candidates[last_line] = footer_candidates.get(last_line, 0) + 1

    threshold = max(2, int(len(pages) * 0.6))
    repeated_headers = {k for k, v in header_candidates.items() if v >= threshold}
    repeated_footers = {k for k, v in footer_candidates.items() if v >= threshold}

    cleaned_pages = []
    for lines in page_lines_list:
        clean_lines = [l.strip() for l in lines if l.strip()]
        if not clean_lines:
            cleaned_pages.append("")
            continue

        start_idx = 0
        end_idx = len(clean_lines)

        # Check top line
        if clean_lines[start_idx] in repeated_headers or PAGE_NUMBER_REGEX.match(clean_lines[start_idx]):
            start_idx += 1

        # Check bottom line
        if end_idx > start_idx:
            if clean_lines[end_idx - 1] in repeated_footers or PAGE_NUMBER_REGEX.match(clean_lines[end_idx - 1]):
                end_idx -= 1

        cleaned_pages.append("\n".join(clean_lines[start_idx:end_idx]))

    return cleaned_pages


def chunk_markdown(text: str, chunk_size: int = 2000) -> List[str]:
    """Splits markdown into token-friendly chunks bounded by paragraph breaks."""
    paragraphs = text.split("\n\n")
    chunks: List[str] = []
    current_chunk: List[str] = []
    current_len = 0

    for p in paragraphs:
        p_len = len(p)
        if current_chunk and (current_len + p_len + 2 > chunk_size):
            chunks.append("\n\n".join(current_chunk).strip())
            current_chunk = [p]
            current_len = p_len
        else:
            current_chunk.append(p)
            current_len += p_len + 2

    if current_chunk:
        chunks.append("\n\n".join(current_chunk).strip())

    return chunks


def extract_txt_to_markdown(file_path: str) -> DocumentResult:
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    cleaned = clean_text_for_llm(content)
    words = len(cleaned.split())
    est_tokens = len(cleaned) // 4

    return DocumentResult(
        format="txt",
        total_pages=1,
        markdown_text=cleaned,
        word_count=words,
        estimated_tokens=est_tokens,
    )


def extract_pdf_to_markdown(
    file_path: str,
    strip_boilerplate: bool = True,
    max_pages: Optional[int] = None,
) -> DocumentResult:
    reader = PdfReader(file_path)
    total_pages = len(reader.pages)
    num_to_read = min(total_pages, max_pages) if max_pages else total_pages

    raw_pages = []
    for idx in range(num_to_read):
        page = reader.pages[idx]
        text = page.extract_text() or ""
        raw_pages.append(text)

    if strip_boilerplate and len(raw_pages) > 1:
        processed_pages = strip_boilerplate_headers(raw_pages)
    else:
        processed_pages = raw_pages

    formatted_pages = []
    for idx, page_text in enumerate(processed_pages, start=1):
        cleaned = clean_text_for_llm(page_text)
        if cleaned:
            formatted_pages.append(f"<!-- Page {idx} -->\n\n{cleaned}")

    full_md = "\n\n---\n\n".join(formatted_pages)
    words = len(full_md.split())
    est_tokens = len(full_md) // 4

    return DocumentResult(
        format="pdf",
        total_pages=total_pages,
        markdown_text=full_md,
        word_count=words,
        estimated_tokens=est_tokens,
    )


def extract_docx_to_markdown(file_path: str, extract_tables: bool = True) -> DocumentResult:
    """Parses Word .docx using Open Packaging XML without external dependencies."""
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    elements_md = []

    with zipfile.ZipFile(file_path, "r") as z:
        if "word/document.xml" not in z.namelist():
            raise ValueError("Invalid DOCX file: missing word/document.xml")
        xml_content = z.read("word/document.xml")

    root = ET.fromstring(xml_content)
    body = root.find("w:body", ns)
    if body is None:
        body = root

    for child in list(body):
        tag = child.tag.split("}")[-1]

        if tag == "p":
            # Check paragraph style (Headings)
            heading_level = 0
            pPr = child.find("w:pPr", ns)
            if pPr is not None:
                pStyle = pPr.find("w:pStyle", ns)
                if pStyle is not None:
                    style_val = pStyle.attrib.get(f"{{{ns['w']}}}val", "")
                    if "Heading1" in style_val:
                        heading_level = 1
                    elif "Heading2" in style_val:
                        heading_level = 2
                    elif "Heading3" in style_val:
                        heading_level = 3

            # Extract text
            texts = [t.text for t in child.findall(".//w:t", ns) if t.text]
            p_text = "".join(texts).strip()
            if p_text:
                if heading_level > 0:
                    elements_md.append(f"{'#' * heading_level} {p_text}")
                else:
                    elements_md.append(p_text)

        elif tag == "tbl" and extract_tables:
            table_rows = []
            for tr in child.findall("w:tr", ns):
                row_cells = []
                for tc in tr.findall("w:tc", ns):
                    cell_texts = [t.text for t in tc.findall(".//w:t", ns) if t.text]
                    row_cells.append(" ".join(cell_texts).strip())
                if any(row_cells):
                    table_rows.append(row_cells)
            if table_rows:
                elements_md.append(format_as_gfm_table(table_rows))

    full_md = "\n\n".join(elements_md)
    words = len(full_md.split())
    est_tokens = len(full_md) // 4

    return DocumentResult(
        format="docx",
        total_pages=1,
        markdown_text=full_md,
        word_count=words,
        estimated_tokens=est_tokens,
    )


def extract_pptx_to_markdown(file_path: str, max_slides: Optional[int] = None) -> DocumentResult:
    """Parses PowerPoint .pptx slides using pure XML without external dependencies."""
    ns = {
        "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
        "p": "http://schemas.openxmlformats.org/presentationml/2006/main"
    }

    slides_md = []
    with zipfile.ZipFile(file_path, "r") as z:
        # Find all slide XML files and sort them numerically
        slide_files = [f for f in z.namelist() if f.startswith("ppt/slides/slide") and f.endswith(".xml")]
        slide_files.sort(key=lambda s: int(re.search(r"\d+", s).group(0)) if re.search(r"\d+", s) else 0)

        num_slides = min(len(slide_files), max_slides) if max_slides else len(slide_files)

        for idx, slide_path in enumerate(slide_files[:num_slides], start=1):
            slide_xml = z.read(slide_path)
            root = ET.fromstring(slide_xml)

            slide_texts = []
            for sp in root.findall(".//p:sp", ns):
                sp_texts = []
                for p in sp.findall(".//a:p", ns):
                    p_texts = [t.text for t in p.findall(".//a:t", ns) if t.text]
                    combined = " ".join(p_texts).strip()
                    if combined:
                        sp_texts.append(combined)
                if sp_texts:
                    slide_texts.extend(sp_texts)

            if slide_texts:
                slide_content = []
                slide_content.append(f"<!-- Slide {idx} -->")
                slide_content.append(f"## {slide_texts[0]}")
                for bullet in slide_texts[1:]:
                    slide_content.append(f"- {bullet}")
                slides_md.append("\n\n".join(slide_content))

    full_md = "\n\n---\n\n".join(slides_md)
    words = len(full_md.split())
    est_tokens = len(full_md) // 4

    return DocumentResult(
        format="pptx",
        total_pages=len(slides_md),
        markdown_text=full_md,
        word_count=words,
        estimated_tokens=est_tokens,
    )


def convert_to_markdown(
    file_path: str,
    extract_tables: bool = True,
    strip_boilerplate: bool = True,
    max_pages: Optional[int] = None,
    chunk_size: Optional[int] = None,
) -> DocumentResult:
    """Universal dispatcher for converting documents to LLM-optimized Markdown."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Input file not found: {file_path}")

    _, ext = os.path.splitext(file_path.lower())

    if ext == ".pdf":
        result = extract_pdf_to_markdown(file_path, strip_boilerplate=strip_boilerplate, max_pages=max_pages)
    elif ext == ".docx":
        result = extract_docx_to_markdown(file_path, extract_tables=extract_tables)
    elif ext == ".pptx":
        result = extract_pptx_to_markdown(file_path, max_slides=max_pages)
    else:
        result = extract_txt_to_markdown(file_path)

    if chunk_size and chunk_size > 0:
        result.chunks = chunk_markdown(result.markdown_text, chunk_size=chunk_size)

    return result
