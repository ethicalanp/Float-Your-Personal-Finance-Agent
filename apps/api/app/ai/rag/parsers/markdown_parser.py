import re

from app.ai.rag.models import ParsedDocument, ParsedSection
from app.ai.rag.parsers.base import BaseParser


class MarkdownParser(BaseParser):
    """Parses Markdown text into structured sections preserving heading hierarchies, tables, and lists."""

    def parse(self, content_bytes: bytes, filename: str | None = None) -> ParsedDocument:
        text = content_bytes.decode("utf-8", errors="replace")
        lines = text.splitlines()

        title = filename or "Untitled Document"
        sections: list[ParsedSection] = []

        heading_stack: list[tuple[int, str]] = []  # (level, heading_text)
        current_content_lines: list[str] = []
        current_heading: str | None = None
        current_level: int = 1

        heading_regex = re.compile(r"^(#{1,6})\s+(.+)$")

        for line in lines:
            match = heading_regex.match(line.strip())
            if match:
                # Flush existing section if there is content
                if current_content_lines:
                    content_str = "\n".join(current_content_lines).strip()
                    if content_str:
                        path_str = " > ".join(h[1] for h in heading_stack)
                        sections.append(
                            ParsedSection(
                                heading=current_heading,
                                heading_path=path_str,
                                content=content_str,
                                level=current_level,
                            )
                        )
                    current_content_lines = []

                hashes, h_text = match.groups()
                level = len(hashes)
                h_text = h_text.strip()

                if level == 1 and title == (filename or "Untitled Document"):
                    title = h_text

                # Pop headings of equal or greater level
                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()
                heading_stack.append((level, h_text))

                current_heading = h_text
                current_level = level
            else:
                current_content_lines.append(line)

        # Flush final section
        if current_content_lines:
            content_str = "\n".join(current_content_lines).strip()
            if content_str:
                path_str = " > ".join(h[1] for h in heading_stack)
                sections.append(
                    ParsedSection(
                        heading=current_heading,
                        heading_path=path_str,
                        content=content_str,
                        level=current_level,
                    )
                )

        # If no sections were produced (e.g. text without headings)
        if not sections and text.strip():
            sections.append(
                ParsedSection(
                    heading=None,
                    heading_path="",
                    content=text.strip(),
                    level=1,
                )
            )

        return ParsedDocument(
            title=title,
            sections=sections,
            raw_text=text,
        )
