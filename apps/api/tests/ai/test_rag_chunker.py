from app.ai.rag.chunker import StructureAwareChunker, estimate_tokens
from app.ai.rag.models import ParsedDocument, ParsedSection


def test_estimate_tokens_malayalam_inflation() -> None:
    en_sentence = "Please verify your bank details immediately."
    ml_sentence = "ദയവായി നിങ്ങളുടെ ബാങ്ക് വിവരങ്ങൾ ഉടനടി പരിശോധിക്കുക."

    en_tokens = estimate_tokens(en_sentence)
    ml_tokens = estimate_tokens(ml_sentence)

    # In subword tokenization, Malayalam characters generate more tokens
    assert ml_tokens > en_tokens
    assert ml_tokens > 20


def test_chunker_preserves_heading_path_and_tables() -> None:
    table_content = """Here is the regulatory limit summary:

| Channel | Limit | Velocity |
|---|---|---|
| UPI Lite | ₹1,000 | Max 10 daily |
| IMPS | ₹50,000 | 1 hr cooling |
| NEFT | No limit | Batch window |

Please verify before initiating transfers."""

    doc = ParsedDocument(
        title="[FIXTURE] Payment Limits",
        sections=[
            ParsedSection(
                heading="Limits",
                heading_path="Circular > Payment Limits > Section A",
                content=table_content,
                level=2,
            )
        ],
        raw_text=table_content,
    )

    chunker = StructureAwareChunker(target_max_tokens=600)
    chunks = chunker.chunk_document(doc, language="en")

    assert len(chunks) == 1
    assert chunks[0].heading_path == "Circular > Payment Limits > Section A"
    # Ensure all table rows stayed together in the chunk
    assert "| UPI Lite | ₹1,000 |" in chunks[0].content
    assert "| NEFT | No limit |" in chunks[0].content


def test_chunker_subchunks_long_sections_with_overlap() -> None:
    # Build a long section with multiple paragraphs
    paragraphs = [
        f"Paragraph {i}: This is an in-depth regulatory guidance on banking security procedures "
        f"with necessary safeguards for Indian digital payment systems."
        for i in range(15)
    ]
    long_content = "\n\n".join(paragraphs)

    doc = ParsedDocument(
        title="[FIXTURE] Extended Regulations",
        sections=[
            ParsedSection(
                heading="Detailed Clauses",
                heading_path="Regulations > Clauses",
                content=long_content,
                level=1,
            )
        ],
        raw_text=long_content,
    )

    chunker = StructureAwareChunker(target_max_tokens=200, overlap_tokens=40)
    chunks = chunker.chunk_document(doc, language="en")

    assert len(chunks) >= 2
    for c in chunks:
        assert c.heading_path == "Regulations > Clauses"
        assert c.token_count <= 800

    # Verify overlap exists between chunk 0 and chunk 1
    chunk_0_lines = chunks[0].content.splitlines()
    chunk_1_lines = chunks[1].content.splitlines()
    overlap_found = any(line in chunk_1_lines for line in chunk_0_lines if len(line) > 20)
    assert overlap_found


def test_chunker_handles_empty_sections() -> None:
    doc = ParsedDocument(
        title="[FIXTURE] Empty Sections",
        sections=[
            ParsedSection(heading="Empty 1", heading_path="Top > Empty 1", content="   \n   ", level=1),
            ParsedSection(heading="Valid 2", heading_path="Top > Valid 2", content="Valid content here.", level=1),
        ],
        raw_text="Valid content here.",
    )

    chunker = StructureAwareChunker()
    chunks = chunker.chunk_document(doc, language="en")

    assert len(chunks) == 1
    assert chunks[0].content == "Valid content here."
    assert chunks[0].heading_path == "Top > Valid 2"
