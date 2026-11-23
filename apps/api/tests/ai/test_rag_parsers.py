from app.ai.rag.parsers import (
    HTMLDocumentParser,
    MarkdownParser,
    PDFDocumentParser,
    PlainTextParser,
    get_parser_for_content,
)


def test_markdown_parser_hierarchical_headings_and_malayalam() -> None:
    md_content = """# [FIXTURE] RBI Master Direction 2026

General intro text.

## 1. Digital Payment Controls

Rules for multi-factor authentication.

### 1.1 Malayalam Advisory
നിങ്ങളുടെ ബാങ്ക് ഒടിപി ആരുമായും പങ്കിടരുത്. ഇതാണ് പ്രധാന നിർദ്ദേശം.

| Rule ID | Limit | Type |
|---|---|---|
| R1 | ₹10,000 | UPI |
| R2 | ₹50,000 | IMPS |

- Step A: Verify beneficiary name
- Step B: Check SMS alerts
"""
    parser = MarkdownParser()
    doc = parser.parse(md_content.encode("utf-8"), filename="test_rbi.md")

    assert doc.title == "[FIXTURE] RBI Master Direction 2026"
    assert len(doc.sections) >= 3

    # Check Malayalam section
    ml_sec = [s for s in doc.sections if "നിങ്ങളുടെ ബാങ്ക് ഒടിപി" in s.content][0]
    assert "Digital Payment Controls" in ml_sec.heading_path
    assert "Malayalam Advisory" in ml_sec.heading_path
    assert "നിങ്ങളുടെ ബാങ്ക് ഒടിപി" in ml_sec.content
    assert "| R1 | ₹10,000 |" in ml_sec.content
    assert "- Step A: Verify" in ml_sec.content


def test_html_parser_drops_scripts_and_nav_and_extracts_headings() -> None:
    html_content = """<!DOCTYPE html>
<html>
<head>
    <title>[FIXTURE] Official Portal Advisory</title>
    <script>alert('malicious_script_should_be_dropped');</script>
    <style>body { color: red; }</style>
</head>
<body>
    <nav><a href="/home">Home</a><a href="/login">Login</a></nav>
    <header><h1>[FIXTURE] Main Portal Header</h1></header>
    <main>
        <h2>Section 1: Fraud Warning</h2>
        <p>Do not enter your UPI PIN to receive money.</p>
        <p>തട്ടിപ്പുകാർ അയക്കുന്ന വ്യാജ ലിങ്കുകളിൽ ക്ലിക്ക് ചെയ്യരുത്.</p>
        <ul>
            <li>Rule 1</li>
            <li>Rule 2</li>
        </ul>
    </main>
    <footer>Copyright 2026</footer>
</body>
</html>
"""
    parser = HTMLDocumentParser()
    doc = parser.parse(html_content.encode("utf-8"), filename="portal.html")

    assert doc.title == "[FIXTURE] Official Portal Advisory" or "[FIXTURE] Main Portal Header" in doc.title
    assert "malicious_script" not in doc.raw_text
    assert "body { color: red; }" not in doc.raw_text
    assert "Do not enter your UPI PIN" in doc.raw_text
    assert "തട്ടിപ്പുകാർ അയക്കുന്ന വ്യാജ ലിങ്കുകളിൽ" in doc.raw_text


def test_pdf_parser_fallback_text_extraction() -> None:
    # Emulate basic PDF text stream with BT ... ET markers
    fake_pdf = (
        b"%PDF-1.4\n1 0 obj\n<<>>\nstream\nBT\n/F1 12 Tf\n"
        b"(1. Digital Safety Notice)Tj\nET\nBT\n"
        b"(Always call 1930 for cyber fraud.)Tj\nET\nendstream\nendobj"
    )
    parser = PDFDocumentParser()
    doc = parser.parse(fake_pdf, filename="fixture_report.pdf")

    assert "Digital Safety Notice" in doc.raw_text or "1930" in doc.raw_text
    assert doc.sections is not None


def test_parser_factory_selection() -> None:
    assert isinstance(get_parser_for_content(filename="doc.md"), MarkdownParser)
    assert isinstance(get_parser_for_content(content_type="text/markdown"), MarkdownParser)
    assert isinstance(get_parser_for_content(filename="portal.html"), HTMLDocumentParser)
    assert isinstance(get_parser_for_content(content_type="text/html"), HTMLDocumentParser)
    assert isinstance(get_parser_for_content(filename="circular.pdf"), PDFDocumentParser)
    assert isinstance(get_parser_for_content(filename="notes.txt"), PlainTextParser)
