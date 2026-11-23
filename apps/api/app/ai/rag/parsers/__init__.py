from app.ai.rag.parsers.base import BaseParser
from app.ai.rag.parsers.html_parser import HTMLDocumentParser
from app.ai.rag.parsers.markdown_parser import MarkdownParser
from app.ai.rag.parsers.pdf_parser import PDFDocumentParser
from app.ai.rag.parsers.text_parser import PlainTextParser


def get_parser_for_content(content_type: str | None = None, filename: str | None = None) -> BaseParser:
    """Select the appropriate parser based on content-type or filename extension."""
    ct = (content_type or "").lower()
    fn = (filename or "").lower()

    if "markdown" in ct or fn.endswith(".md") or fn.endswith(".markdown"):
        return MarkdownParser()
    if "html" in ct or fn.endswith(".html") or fn.endswith(".htm"):
        return HTMLDocumentParser()
    if "pdf" in ct or fn.endswith(".pdf"):
        return PDFDocumentParser()
    return PlainTextParser()


__all__ = [
    "BaseParser",
    "MarkdownParser",
    "HTMLDocumentParser",
    "PDFDocumentParser",
    "PlainTextParser",
    "get_parser_for_content",
]
