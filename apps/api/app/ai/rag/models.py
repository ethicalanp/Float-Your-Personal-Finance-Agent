from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

DocumentStatus = Literal["draft", "processing", "review", "published", "superseded", "archived"]
DocType = Literal["advisory", "sop", "guideline", "circular", "discussion_paper", "report", "fixture", "literacy"]
Language = Literal["en", "ml", "hi", "manglish", "mixed", "und"]


class ManifestSource(BaseModel):
    """Schema for each approved knowledge source in manifest.yaml."""

    id: str = Field(..., min_length=2, max_length=128, pattern=r"^[a-zA-Z0-9_\-\.]+$")
    title: str = Field(..., min_length=3, max_length=255)
    publisher: str = Field(..., min_length=2, max_length=128)
    source_url: str | None = None
    file_path: str | None = None
    language: Language = "en"
    doc_type: DocType = "advisory"
    licence_note: str | None = None
    publication_date: date | None = None
    effective_date: date | None = None
    reviewer: str | None = None
    version: str = "1"

    @model_validator(mode="after")
    def validate_source_location(self) -> "ManifestSource":
        if not self.source_url and not self.file_path:
            raise ValueError(f"Source '{self.id}' must provide either 'source_url' or 'file_path'")
        return self


class Manifest(BaseModel):
    """Container for all manifest sources with validation and domain allowlist."""

    sources: list[ManifestSource] = Field(default_factory=list)

    def get_source(self, source_id: str) -> ManifestSource | None:
        for s in self.sources:
            if s.id == source_id:
                return s
        return None

    def domain_allowlist(self) -> set[str]:
        """Extract allowed domains from all HTTPS source URLs in the manifest."""
        domains: set[str] = set()
        for s in self.sources:
            if s.source_url and s.source_url.startswith("https://"):
                try:
                    from urllib.parse import urlparse

                    parsed = urlparse(s.source_url)
                    if parsed.netloc:
                        # strip optional port
                        domain = parsed.netloc.split(":")[0].lower()
                        domains.add(domain)
                except Exception:
                    pass
        return domains


class ParsedSection(BaseModel):
    heading: str | None = None
    heading_path: str = ""
    content: str
    level: int = 1


class ParsedDocument(BaseModel):
    title: str
    sections: list[ParsedSection]
    raw_text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentChunk(BaseModel):
    chunk_index: int
    content: str
    heading_path: str | None = None
    language: str = "en"
    token_count: int = 0
    embedding_dim: int = 768
    embedding_model: str = "intfloat/multilingual-e5-base"
    embedding: list[float] | None = None


class IngestWarning(BaseModel):
    document_id: str
    code: str
    message: str


class TokenStatistics(BaseModel):
    min: int = 0
    median: float = 0.0
    max: int = 0
    total: int = 0


class IngestRunReport(BaseModel):
    timestamp: str
    documents_seen: int = 0
    documents_new: int = 0
    documents_unchanged: int = 0
    documents_failed: int = 0
    chunks_created: int = 0
    total_embedding_time_s: float = 0.0
    time_per_chunk_s: float = 0.0
    token_statistics: TokenStatistics = Field(default_factory=TokenStatistics)
    languages: dict[str, int] = Field(default_factory=dict)
    embedding_model: str = "intfloat/multilingual-e5-base"
    warnings: list[IngestWarning] = Field(default_factory=list)
