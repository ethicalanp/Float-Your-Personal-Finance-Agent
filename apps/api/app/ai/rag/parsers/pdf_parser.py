import io
import re

from app.ai.rag.models import ParsedDocument, ParsedSection
from app.ai.rag.parsers.base import BaseParser


class PDFDocumentParser(BaseParser):
    """Parser for PDF documents extracting text pages and detecting structural headings."""

    def parse(self, content_bytes: bytes, filename: str | None = None) -> ParsedDocument:
        extracted_pages: list[str] = []

        # Attempt using pypdf if installed
        try:
            import pypdf

            reader = pypdf.PdfReader(io.BytesIO(content_bytes))
            for page in reader.pages:
                text = page.extract_text() or ""
                if text.strip():
                    extracted_pages.append(text.strip())
        except Exception:
            # Fallback to standard PDF stream extraction for basic text streams
            extracted_pages = self._extract_raw_pdf_text(content_bytes)

        full_text = "\n\n".join(extracted_pages).strip()
        title = filename or "Untitled PDF Document"

        # Break text into sections by detecting likely headings (e.g. numbered sections like "1. Title" or all caps)
        sections = self._detect_sections(full_text)
        if sections and sections[0].heading:
            title = sections[0].heading

        return ParsedDocument(
            title=title,
            sections=sections,
            raw_text=full_text,
        )

    def _extract_raw_pdf_text(self, data: bytes) -> list[str]:
        """Simple fallback text extractor scanning for PDF text strings."""
        text_pieces: list[str] = []
        # Find BT (Begin Text) ... ET (End Text) blocks
        bt_et_pattern = re.compile(rb"BT\s*(.*?)\s*ET", re.DOTALL)
        str_pattern = re.compile(rb"\((.*?)\)T[jJ]", re.DOTALL)

        for match in bt_et_pattern.finditer(data):
            block = match.group(1)
            for str_match in str_pattern.finditer(block):
                raw_str = str_match.group(1)
                try:
                    decoded = raw_str.decode("utf-8", errors="replace")
                    if decoded.strip():
                        text_pieces.append(decoded.strip())
                except Exception:
                    pass

        if not text_pieces:
            # Ultimate plain text fallback if PDF was plain ASCII
            try:
                decoded = data.decode("latin-1", errors="ignore")
                printable = "".join(c for c in decoded if c.isprintable() or c in "\n\t")
                if printable.strip():
                    return [printable.strip()]
            except Exception:
                pass

        return [" ".join(text_pieces)] if text_pieces else []

    def _detect_sections(self, text: str) -> list[ParsedSection]:
        lines = text.splitlines()
        sections: list[ParsedSection] = []

        current_heading: str | None = None
        current_lines: list[str] = []
        heading_path = ""

        # Pattern for "1. ", "Section 2", "CHAPTER 3" or short bold-like lines
        heading_re = re.compile(r"^(\d+[\.\)]\s+[A-Z0-9\u0D00-\u0D7F][^\n]{3,80}|Section\s+\d+.*)$", re.IGNORECASE)

        for line in lines:
            line_clean = line.strip()
            if not line_clean:
                continue

            if heading_re.match(line_clean) and len(line_clean) < 100:
                if current_lines:
                    content_str = "\n".join(current_lines).strip()
                    if content_str:
                        sections.append(
                            ParsedSection(
                                heading=current_heading,
                                heading_path=heading_path,
                                content=content_str,
                                level=1,
                            )
                        )
                    current_lines = []
                current_heading = line_clean
                heading_path = line_clean
            else:
                current_lines.append(line_clean)

        if current_lines:
            content_str = "\n".join(current_lines).strip()
            if content_str:
                sections.append(
                    ParsedSection(
                        heading=current_heading,
                        heading_path=heading_path,
                        content=content_str,
                        level=1,
                    )
                )

        if not sections and text.strip():
            sections.append(
                ParsedSection(
                    heading=None,
                    heading_path="",
                    content=text.strip(),
                    level=1,
                )
            )

        return sections
