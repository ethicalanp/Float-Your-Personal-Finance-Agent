import hashlib
import time
from pathlib import Path
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.ai.rag.chunker import StructureAwareChunker
from app.ai.rag.cleaner import clean_text
from app.ai.rag.embedder.base import BaseEmbedder
from app.ai.rag.language import detect_section_language
from app.ai.rag.models import (
    IngestRunReport,
    IngestWarning,
    Language,
    Manifest,
    TokenStatistics,
)
from app.ai.rag.parsers import get_parser_for_content
from app.ai.rag.repository import KnowledgeRepository
from app.ai.rag.security import scan_for_prompt_injections


class PipelineError(Exception):
    pass


def validate_raw_source(
    raw_bytes: bytes,
    max_size: int = 10 * 1024 * 1024,
) -> tuple[str, int]:
    """Stage 1: Validate size, encoding, and compute SHA-256 hash."""
    if len(raw_bytes) == 0:
        raise PipelineError("Source content is empty (0 bytes)")
    if len(raw_bytes) > max_size:
        raise PipelineError(f"Source content {len(raw_bytes)} bytes exceeds maximum {max_size} limit")

    content_hash = hashlib.sha256(raw_bytes).hexdigest()
    return content_hash, len(raw_bytes)


async def run_ingestion_pipeline(
    manifest: Manifest,
    embedder: BaseEmbedder,
    db_session: AsyncSession | Session,
    base_dir: Path | str = ".",
    force: bool = False,
    max_docs: int | None = None,
    batch_size: int = 8,
) -> IngestRunReport:
    """Run offline ingestion pipeline over approved manifest sources with batch progress tracking."""
    base_path = Path(base_dir)
    repo = KnowledgeRepository(db_session)
    chunker = StructureAwareChunker()

    report = IngestRunReport(
        timestamp=str(Path(".").stat().st_mtime),
        embedding_model=embedder.model_name,
    )
    from datetime import UTC, datetime

    report.timestamp = datetime.now(UTC).isoformat()

    all_tokens: list[int] = []
    sources = manifest.sources[:max_docs] if max_docs is not None else manifest.sources
    total_sources = len(sources)

    print(f"\n[Pipeline] Ingestion starting for {total_sources} document(s) (batch_size={batch_size})...", flush=True)

    total_embed_time: float = 0.0
    total_chunks_embedded: int = 0

    for doc_idx, source in enumerate(sources, start=1):
        report.documents_seen += 1
        print(f"\n[Doc {doc_idx}/{total_sources}] Processing '{source.title}' ({source.id})", flush=True)
        try:
            # 1. Acquire raw bytes
            raw_bytes: bytes
            filename: str
            if source.file_path:
                file_full = base_path / source.file_path
                if not file_full.exists():
                    file_full = Path(source.file_path)
                if not file_full.exists():
                    raise PipelineError(f"Local file not found for source '{source.id}': {source.file_path}")
                raw_bytes = file_full.read_bytes()
                filename = file_full.name
            else:
                raise PipelineError(
                    f"Source '{source.id}' has source_url only. Download source locally before offline ingestion."
                )

            # 2. Validate
            content_hash, byte_size = validate_raw_source(raw_bytes)

            # Check idempotency
            existing_doc = await repo.get_document_by_content_hash(content_hash)
            if existing_doc and not force:
                report.documents_unchanged += 1
                print(
                    f"  -> Unchanged (hash: {content_hash[:8]}...). Skipped. (Use force=True to re-ingest)",
                    flush=True,
                )
                continue

            supersedes_id = None
            if existing_doc:
                supersedes_id = existing_doc.id

            # 3. Parse
            parser = get_parser_for_content(filename=filename)
            parsed_doc = parser.parse(raw_bytes, filename=filename)

            # 4. Clean sections
            for sec in parsed_doc.sections:
                sec.content = clean_text(sec.content)

            # 5. Security Injection Scan
            injections = scan_for_prompt_injections(parsed_doc.raw_text)
            if injections:
                report.warnings.append(
                    IngestWarning(
                        document_id=source.id,
                        code="INJECTION_PATTERNS_DETECTED",
                        message=f"Found {len(injections)} suspicious prompt injection patterns: {injections[:2]}",
                    )
                )

            # 6. Detect language per section & check agreements
            section_languages = []
            for sec in parsed_doc.sections:
                det_lang, disagreement = detect_section_language(sec.content, manifest_language=source.language)
                section_languages.append(det_lang)
                if disagreement:
                    report.warnings.append(
                        IngestWarning(
                            document_id=source.id,
                            code="LANGUAGE_DISAGREEMENT",
                            message=(
                                f"Section '{sec.heading or 'top'}' detected as '{det_lang}' "
                                f"but manifest specified '{source.language}'"
                            ),
                        )
                    )

            primary_language: Language = source.language
            if source.language == "mixed" and section_languages:
                primary_language = cast(Language, max(set(section_languages), key=section_languages.count))

            # Check license warning
            if not source.licence_note:
                report.warnings.append(
                    IngestWarning(
                        document_id=source.id,
                        code="MISSING_LICENCE_NOTE",
                        message=f"Source '{source.id}' has no licence_note; cannot be published, will hold in review",
                    )
                )

            # 7. Structure-aware chunking
            chunks = chunker.chunk_document(
                document=parsed_doc,
                language=primary_language,
                embedding_model=embedder.model_name,
            )

            for c in chunks:
                all_tokens.append(c.token_count)
                report.languages[c.language] = report.languages.get(c.language, 0) + 1
                if c.token_count > 800:
                    report.warnings.append(
                        IngestWarning(
                            document_id=source.id,
                            code="OVERSIZED_CHUNK",
                            message=f"Chunk {c.chunk_index} has {c.token_count} tokens (exceeds 800 limit)",
                        )
                    )
                elif c.token_count < 20:
                    report.warnings.append(
                        IngestWarning(
                            document_id=source.id,
                            code="UNDERSIZED_CHUNK",
                            message=f"Chunk {c.chunk_index} has only {c.token_count} tokens",
                        )
                    )

            # 8. Embed chunks in batches with progress logging & ETA
            # Prepend title and heading to text for embedding (keeping chunk.content clean for display)
            passages = [
                f"{source.title.strip()}\n{c.heading_path.strip() + '\n' if c.heading_path else ''}{c.content.strip()}"
                for c in chunks
            ]
            doc_chunks_count = len(passages)
            print(f"  -> Generated {doc_chunks_count} chunk(s). Embedding in batches of {batch_size}...", flush=True)

            vectors: list[list[float]] = []
            doc_embed_start = time.monotonic()

            for b_start in range(0, doc_chunks_count, batch_size):
                b_end = min(b_start + batch_size, doc_chunks_count)
                batch_texts = passages[b_start:b_end]
                t_b0 = time.monotonic()

                b_vecs = embedder.embed_passages(batch_texts, batch_size=batch_size)
                vectors.extend(b_vecs)

                b_duration = time.monotonic() - t_b0
                total_embed_time += b_duration
                total_chunks_embedded += len(batch_texts)

                elapsed_doc = time.monotonic() - doc_embed_start
                avg_time_per_chunk = elapsed_doc / b_end if b_end > 0 else 0.0
                remaining_chunks = doc_chunks_count - b_end
                eta_seconds = remaining_chunks * avg_time_per_chunk

                pct = int((b_end / doc_chunks_count) * 100)
                print(
                    f"  -> Chunks [{b_end}/{doc_chunks_count}] ({pct}%) | "
                    f"Batch: {len(batch_texts)} in {b_duration:.2f}s | "
                    f"Rate: {avg_time_per_chunk:.3f}s/chunk | "
                    f"ETA: {eta_seconds:.1f}s",
                    flush=True,
                )

            for c, vec in zip(chunks, vectors, strict=False):
                c.embedding = vec

            # 9. Store in DB (transition to 'review')
            doc_row = await repo.create_document(
                source=source,
                content_hash=content_hash,
                status="review",
                supersedes_id=supersedes_id,
            )
            await repo.save_chunks(doc_row.id, chunks)

            report.documents_new += 1
            report.chunks_created += len(chunks)
            print(f"  -> Saved {len(chunks)} chunks to database.", flush=True)

        except Exception as e:
            report.documents_failed += 1
            print(f"  -> [FAILED] {source.id}: {e}", flush=True)
            report.warnings.append(
                IngestWarning(
                    document_id=source.id,
                    code="PIPELINE_FAILURE",
                    message=str(e),
                )
            )

    # Compute token statistics
    if all_tokens:
        import statistics

        report.token_statistics = TokenStatistics(
            min=min(all_tokens),
            median=float(statistics.median(all_tokens)),
            max=max(all_tokens),
            total=sum(all_tokens),
        )

    # Record total chunks and timing metrics
    report.total_embedding_time_s = round(total_embed_time, 2)
    if total_chunks_embedded > 0:
        report.time_per_chunk_s = round(total_embed_time / total_chunks_embedded, 3)

    print("\n" + "=" * 70, flush=True)
    print(
        f"[Summary] Docs Seen: {report.documents_seen} | New: {report.documents_new} | "
        f"Total Chunks: {report.chunks_created} | Total Time: {report.total_embedding_time_s}s | "
        f"Rate: {report.time_per_chunk_s}s/chunk",
        flush=True,
    )
    print("=" * 70, flush=True)

    return report
