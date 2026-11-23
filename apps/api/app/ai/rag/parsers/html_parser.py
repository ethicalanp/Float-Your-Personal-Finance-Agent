from html.parser import HTMLParser

from app.ai.rag.models import ParsedDocument, ParsedSection
from app.ai.rag.parsers.base import BaseParser


class StructuredHTMLParser(HTMLParser):
    """HTML parser that ignores scripts/styles/nav and extracts structured headings and text."""

    def __init__(self) -> None:
        super().__init__()
        self.title: str = "Untitled Document"
        self._in_title = False
        self._ignore_tags = {"script", "style", "nav", "header", "footer", "aside", "noscript", "iframe"}
        self._ignore_depth = 0

        self.sections: list[ParsedSection] = []
        self._heading_stack: list[tuple[int, str]] = []
        self._current_content: list[str] = []
        self._current_heading: str | None = None
        self._current_level: int = 1

        self._active_heading_tag: str | None = None
        self._heading_buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_lower = tag.lower()
        if tag_lower in self._ignore_tags:
            self._ignore_depth += 1
            return

        if self._ignore_depth > 0:
            return

        if tag_lower == "title":
            self._in_title = True
        elif tag_lower in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._flush_content()
            self._active_heading_tag = tag_lower
            self._heading_buffer = []
        elif tag_lower == "li":
            self._current_content.append("\n- ")
        elif tag_lower in {"p", "div", "br", "tr"}:
            self._current_content.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()
        if tag_lower in self._ignore_tags:
            self._ignore_depth = max(0, self._ignore_depth - 1)
            return

        if self._ignore_depth > 0:
            return

        if tag_lower == "title":
            self._in_title = False
        elif tag_lower in {"h1", "h2", "h3", "h4", "h5", "h6"} and self._active_heading_tag == tag_lower:
            h_text = " ".join("".join(self._heading_buffer).split()).strip()
            level = int(tag_lower[1])

            if h_text:
                if level == 1 and self.title == "Untitled Document":
                    self.title = h_text

                while self._heading_stack and self._heading_stack[-1][0] >= level:
                    self._heading_stack.pop()
                self._heading_stack.append((level, h_text))

                self._current_heading = h_text
                self._current_level = level

            self._active_heading_tag = None
            self._heading_buffer = []

    def handle_data(self, data: str) -> None:
        if self._ignore_depth > 0:
            return

        if self._in_title:
            cleaned = data.strip()
            if cleaned:
                self.title = cleaned
        elif self._active_heading_tag:
            self._heading_buffer.append(data)
        else:
            self._current_content.append(data)

    def _flush_content(self) -> None:
        raw_text = "".join(self._current_content).strip()
        if raw_text:
            lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
            cleaned_content = "\n".join(lines)
            if cleaned_content:
                path_str = " > ".join(h[1] for h in self._heading_stack)
                self.sections.append(
                    ParsedSection(
                        heading=self._current_heading,
                        heading_path=path_str,
                        content=cleaned_content,
                        level=self._current_level,
                    )
                )
        self._current_content = []

    def close(self) -> None:
        super().close()
        self._flush_content()


class HTMLDocumentParser(BaseParser):
    """Parser for HTML documents."""

    def parse(self, content_bytes: bytes, filename: str | None = None) -> ParsedDocument:
        html_str = content_bytes.decode("utf-8", errors="replace")
        parser = StructuredHTMLParser()
        parser.feed(html_str)
        parser.close()

        title = parser.title if parser.title != "Untitled Document" else (filename or "Untitled Document")

        # If no sections, fall back to entire text
        if not parser.sections:
            clean_raw = " ".join(html_str.split())
            if clean_raw:
                parser.sections.append(
                    ParsedSection(
                        heading=None,
                        heading_path="",
                        content=clean_raw,
                        level=1,
                    )
                )

        raw_text = "\n\n".join(s.content for s in parser.sections)

        return ParsedDocument(
            title=title,
            sections=parser.sections,
            raw_text=raw_text,
        )
