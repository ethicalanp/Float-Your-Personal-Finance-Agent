import re

from app.ai.rag.models import DocumentChunk, ParsedDocument, ParsedSection


def estimate_tokens(text: str) -> int:
    """Estimate token count accounting for Malayalam and Indic subword inflation.

    In multilingual models (like XLM-RoBERTa / multilingual-e5), Latin words average
    ~1.3 tokens, whereas Dravidian/Indic scripts break into multiple byte-level or
    syllabic subwords (~1.0 - 1.2 tokens per character).
    """
    if not text:
        return 0

    ml_chars = 0
    hi_chars = 0
    latin_words = 0

    for ch in text:
        code = ord(ch)
        if 0x0D00 <= code <= 0x0D7F:
            ml_chars += 1
        elif 0x0900 <= code <= 0x097F:
            hi_chars += 1

    # Find latin words
    words = re.findall(r"[a-zA-Z0-9]+", text)
    latin_words = len(words)

    # Weighted estimate
    est = int(latin_words * 1.3 + ml_chars * 0.8 + hi_chars * 0.7)
    return max(1, est)


class StructureAwareChunker:
    """Splits structured sections into citations-ready chunks respecting headings, tables, and lists."""

    def __init__(
        self,
        target_min_tokens: int = 300,
        target_max_tokens: int = 600,
        absolute_max_tokens: int = 800,
        overlap_tokens: int = 60,
    ) -> None:
        self.target_min_tokens = target_min_tokens
        self.target_max_tokens = target_max_tokens
        self.absolute_max_tokens = absolute_max_tokens
        self.overlap_tokens = overlap_tokens

    def chunk_document(
        self,
        document: ParsedDocument,
        language: str = "en",
        embedding_model: str = "intfloat/multilingual-e5-base",
    ) -> list[DocumentChunk]:
        chunks: list[DocumentChunk] = []
        chunk_idx = 0

        for section in document.sections:
            sec_text = section.content.strip()
            if not sec_text:
                continue

            sec_tokens = estimate_tokens(sec_text)

            # If section easily fits under max tokens, keep as single atomic chunk
            if sec_tokens <= self.target_max_tokens:
                chunks.append(
                    DocumentChunk(
                        chunk_index=chunk_idx,
                        content=sec_text,
                        heading_path=section.heading_path or None,
                        language=language,
                        token_count=sec_tokens,
                        embedding_dim=768,
                        embedding_model=embedding_model,
                    )
                )
                chunk_idx += 1
            else:
                # Need sub-chunking
                sub_chunks = self._subchunk_section(section, language, embedding_model, chunk_idx)
                for sc in sub_chunks:
                    chunks.append(sc)
                    chunk_idx += 1

        return chunks

    def _subchunk_section(
        self,
        section: ParsedSection,
        language: str,
        embedding_model: str,
        start_idx: int,
    ) -> list[DocumentChunk]:
        """Split a long section by paragraphs, tables, or list items without breaking rows."""
        lines = section.content.splitlines()
        units: list[str] = []
        current_unit: list[str] = []
        in_table = False

        for line in lines:
            stripped = line.strip()
            # Detect table rows
            if stripped.startswith("|") and stripped.endswith("|"):
                current_unit.append(line)
                in_table = True
            elif in_table and stripped:
                # Still inside a table
                current_unit.append(line)
            else:
                in_table = False
                if not stripped:
                    # Paragraph boundary
                    if current_unit:
                        units.append("\n".join(current_unit))
                        current_unit = []
                else:
                    current_unit.append(line)

        if current_unit:
            units.append("\n".join(current_unit))

        if not units:
            units = [section.content]

        # Now group units into chunks respecting token budgets
        result: list[DocumentChunk] = []
        curr_buffer: list[str] = []
        curr_tokens = 0
        current_idx = start_idx

        for u in units:
            u_tokens = estimate_tokens(u)
            if curr_tokens + u_tokens <= self.target_max_tokens:
                curr_buffer.append(u)
                curr_tokens += u_tokens
            else:
                if curr_buffer:
                    chunk_text = "\n\n".join(curr_buffer).strip()
                    result.append(
                        DocumentChunk(
                            chunk_index=current_idx,
                            content=chunk_text,
                            heading_path=section.heading_path or None,
                            language=language,
                            token_count=curr_tokens,
                            embedding_dim=768,
                            embedding_model=embedding_model,
                        )
                    )
                    current_idx += 1

                    # Compute overlap from end of buffer
                    overlap_buffer: list[str] = []
                    overlap_count = 0
                    for prev_u in reversed(curr_buffer):
                        p_tok = estimate_tokens(prev_u)
                        if overlap_count + p_tok <= self.overlap_tokens:
                            overlap_buffer.insert(0, prev_u)
                            overlap_count += p_tok
                        else:
                            break
                    curr_buffer = overlap_buffer + [u]
                    curr_tokens = overlap_count + u_tokens
                else:
                    # Single unit is larger than target_max_tokens (e.g. very long paragraph or table)
                    # We accept it up to absolute_max_tokens or split lines
                    result.append(
                        DocumentChunk(
                            chunk_index=current_idx,
                            content=u,
                            heading_path=section.heading_path or None,
                            language=language,
                            token_count=u_tokens,
                            embedding_dim=768,
                            embedding_model=embedding_model,
                        )
                    )
                    current_idx += 1
                    curr_buffer = []
                    curr_tokens = 0

        if curr_buffer:
            chunk_text = "\n\n".join(curr_buffer).strip()
            if chunk_text:
                result.append(
                    DocumentChunk(
                        chunk_index=current_idx,
                        content=chunk_text,
                        heading_path=section.heading_path or None,
                        language=language,
                        token_count=curr_tokens,
                        embedding_dim=768,
                        embedding_model=embedding_model,
                    )
                )

        return result
