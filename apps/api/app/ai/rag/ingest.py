import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

if sys.platform == "win32":
    if not isinstance(asyncio.get_event_loop_policy(), asyncio.WindowsSelectorEventLoopPolicy):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.ai.rag.dependencies import get_embedder
from app.ai.rag.embedder.base import BaseEmbedder
from app.ai.rag.embedder.fake import FakeEmbedder
from app.ai.rag.manifest import load_manifest
from app.ai.rag.pipeline import run_ingestion_pipeline
from app.ai.rag.repository import KnowledgeRepository
from app.db.session import get_async_engine, get_async_session_factory


def _resolve_embedder(choice: str = "auto") -> BaseEmbedder:
    """Resolve embedder implementation from choice ('auto', 'local', 'fake')."""
    if choice == "fake":
        return FakeEmbedder()
    if choice == "local":
        from app.ai.rag.embedder.local import LocalEmbedder

        return LocalEmbedder()
    # auto
    return get_embedder()


async def cmd_run(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        # Check relative to repo root
        manifest_path = Path("..") / ".." / args.manifest
    if not manifest_path.exists():
        manifest_path = Path("d:/PersonalFinanceAgent") / args.manifest
    if not manifest_path.exists():
        print(f"Error: manifest file '{args.manifest}' does not exist.")
        return 1

    manifest = load_manifest(manifest_path)
    embedder = _resolve_embedder(getattr(args, "embedder", "auto"))
    print(
        f"Ingesting with embedder: {type(embedder).__name__} "
        f"(model='{embedder.model_name}', dim={embedder.dimension})",
        flush=True,
    )

    session_factory = get_async_session_factory()
    try:
        async with session_factory() as session:
            report = await run_ingestion_pipeline(
                manifest=manifest,
                embedder=embedder,
                db_session=session,
                base_dir=manifest_path.parent,
                force=args.force,
                max_docs=getattr(args, "max_docs", None),
                batch_size=getattr(args, "batch_size", 8),
            )
            await session.commit()

            # Optionally publish all reviewed documents
            if getattr(args, "publish", False):
                print("\nPublishing and smoke-testing ingested documents...", flush=True)
                repo = KnowledgeRepository(session)
                review_docs = await repo.list_documents(status="review")
                for doc in review_docs:
                    try:
                        await repo.approve_document(doc.id, reviewer="auto-ingest-reviewer", embedder=embedder)
                        print(f"  [PUBLISHED] {doc.id} - {doc.title}", flush=True)
                    except Exception as e:
                        print(f"  [APPROVAL FAILED] {doc.id} - {e}", flush=True)
                await session.commit()
    finally:
        await get_async_engine().dispose()

    report_dict = report.model_dump()
    print("\n--- Ingestion Run Report ---", flush=True)
    print(f"Documents Seen:       {report.documents_seen}", flush=True)
    print(f"Documents New:        {report.documents_new}", flush=True)
    print(f"Documents Unchanged:  {report.documents_unchanged}", flush=True)
    print(f"Documents Failed:     {report.documents_failed}", flush=True)
    print(f"Total Chunks Created: {report.chunks_created}", flush=True)
    print(f"Total Embedding Time: {report.total_embedding_time_s}s", flush=True)
    print(f"Time Per Chunk:       {report.time_per_chunk_s}s/chunk", flush=True)
    print("----------------------------\n", flush=True)

    if args.report_file:
        out_path = Path(args.report_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report_dict, indent=2), encoding="utf-8")
        print(f"\nReport written to {out_path}")

    return 0 if report.documents_failed == 0 else 1


async def cmd_list(args: argparse.Namespace) -> int:
    session_factory = get_async_session_factory()
    try:
        async with session_factory() as session:
            repo = KnowledgeRepository(session)
            docs = await repo.list_documents(status=args.status)

            if not docs:
                print("No documents found.", flush=True)
                return 0

            print(f"{'ID':<38} {'STATUS':<12} {'VERSION':<8} {'TITLE':<45} {'PUBLISHER':<20}", flush=True)
            print("-" * 130, flush=True)
            for d in docs:
                print(
                    f"{str(d.id):<38} {d.status:<12} {d.version:<8} {d.title[:43]:<45} {d.publisher[:18]:<20}",
                    flush=True,
                )
    finally:
        await get_async_engine().dispose()
    return 0


async def cmd_show(args: argparse.Namespace) -> int:
    doc_uuid = uuid.UUID(args.doc_id)
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        repo = KnowledgeRepository(session)
        doc = await repo.get_document_by_id(doc_uuid)
        if not doc:
            print(f"Document {doc_uuid} not found.")
            return 1

        chunks = await repo.get_chunks_for_document(doc_uuid)
        print(f"Document ID:   {doc.id}")
        print(f"Title:         {doc.title}")
        print(f"Publisher:     {doc.publisher}")
        print(f"Status:        {doc.status}")
        print(f"Version:       {doc.version}")
        print(f"Language:      {doc.language}")
        print(f"Source URL:    {doc.source_url}")
        print(f"Licence Note:  {doc.licence_note or 'NONE'}")
        print(f"Content Hash:  {doc.content_hash}")
        print(f"Reviewed By:   {doc.reviewed_by or 'None'}")
        print(f"Chunks Count:  {len(chunks)}")
        print("\n--- Chunks Sample ---")
        for c in chunks[:3]:
            print(f"[{c.chunk_index}] ({c.language}, {c.token_count} toks) {c.heading_path or ''}")
            print(f"    {c.content[:100]}...\n")
    return 0


async def cmd_approve(args: argparse.Namespace) -> int:
    doc_uuid = uuid.UUID(args.doc_id)
    embedder = FakeEmbedder()
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        repo = KnowledgeRepository(session)
        try:
            approved = await repo.approve_document(doc_uuid, reviewer=args.reviewer, embedder=embedder)
            print(f"Document {approved.id} successfully APPROVED and PUBLISHED by '{approved.reviewed_by}'.")
            return 0
        except Exception as e:
            print(f"Approval REFUSED: {e}")
            return 1


async def cmd_archive(args: argparse.Namespace) -> int:
    doc_uuid = uuid.UUID(args.doc_id)
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        repo = KnowledgeRepository(session)
        archived = await repo.archive_document(doc_uuid)
        print(f"Document {archived.id} transitioned to ARCHIVED.")
    return 0


async def cmd_reembed(args: argparse.Namespace) -> int:
    doc_uuid = uuid.UUID(args.doc_id)
    embedder = FakeEmbedder(model_name=args.model)
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        repo = KnowledgeRepository(session)
        count = await repo.reembed_document(doc_uuid, new_model_name=args.model, embedder=embedder)
        print(f"Successfully re-embedded {count} chunks for document {doc_uuid} with '{args.model}'.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Float Knowledge RAG Ingestion Pipeline CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # run
    p_run = subparsers.add_parser("run", help="Run ingestion pipeline on manifest")
    p_run.add_argument("--manifest", default="data/knowledge/manifest.yaml", help="Path to manifest.yaml")
    p_run.add_argument("--force", action="store_true", help="Force re-ingest unchanged documents")
    p_run.add_argument("--publish", action="store_true", help="Automatically approve and publish reviewed documents")
    p_run.add_argument("--embedder", choices=["auto", "local", "fake"], default="auto", help="Embedder backend")
    p_run.add_argument(
        "--max-docs", type=int, default=None, help="Maximum number of documents to ingest (default: all)"
    )
    p_run.add_argument("--batch-size", type=int, default=8, help="Embedding batch size (default: 8)")
    p_run.add_argument("--report-file", help="Path to save JSON run report")

    # list
    p_list = subparsers.add_parser("list", help="List knowledge documents")
    p_list.add_argument("--status", choices=["draft", "processing", "review", "published", "superseded", "archived"])

    # show
    p_show = subparsers.add_parser("show", help="Show document details and chunks")
    p_show.add_argument("doc_id", help="Document UUID")

    # approve
    p_approve = subparsers.add_parser("approve", help="Approve and publish a reviewed document")
    p_approve.add_argument("doc_id", help="Document UUID")
    p_approve.add_argument("--reviewer", default="compliance-officer", help="Reviewer identity")

    # archive
    p_archive = subparsers.add_parser("archive", help="Archive a document")
    p_archive.add_argument("doc_id", help="Document UUID")

    # reembed
    p_reembed = subparsers.add_parser("reembed", help="Re-embed document chunks with new model")
    p_reembed.add_argument("doc_id", help="Document UUID")
    p_reembed.add_argument("--model", default="intfloat/multilingual-e5-base", help="Target model")

    args = parser.parse_args()

    if args.command == "run":
        sys.exit(asyncio.run(cmd_run(args)))
    elif args.command == "list":
        sys.exit(asyncio.run(cmd_list(args)))
    elif args.command == "show":
        sys.exit(asyncio.run(cmd_show(args)))
    elif args.command == "approve":
        sys.exit(asyncio.run(cmd_approve(args)))
    elif args.command == "archive":
        sys.exit(asyncio.run(cmd_archive(args)))
    elif args.command == "reembed":
        sys.exit(asyncio.run(cmd_reembed(args)))


if __name__ == "__main__":
    main()
