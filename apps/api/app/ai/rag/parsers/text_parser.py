from app.ai.rag.models import ParsedDocument, ParsedSection
from app.ai.rag.parsers.base import BaseParser


class PlainTextParser(BaseParser):
    """Parser for plain text documents."""

    def parse(self, content_bytes: bytes, filename: str | None = None) -> ParsedDocument:
        text = content_bytes.decode("utf-8", errors="replace").strip()
        title = filename or "Untitled Document"

        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        sections: list[ParsedSection] = []

        for p in paragraphs:
            sections.append(
                ParsedSection(
                    heading=None,
                    heading_path="",
                    content=p,
                    level=1,
                )
            )

        return ParsedDocument(
            title=title,
            sections=sections,
            raw_text=text,
        )
