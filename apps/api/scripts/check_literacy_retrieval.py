import asyncio
import sys

if sys.platform == "win32":
    if not isinstance(asyncio.get_event_loop_policy(), asyncio.WindowsSelectorEventLoopPolicy):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from sqlalchemy import func, select

from app.ai.rag.embedder.local import LocalEmbedder
from app.ai.rag.retrieval import HybridRetriever, RetrievalConfig
from app.db.session import get_async_engine, get_async_session_factory
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument

SAMPLE_QUERIES = [
    # English definition queries
    ("what is money?", "en"),
    ("what is compound interest and how does it work?", "en"),
    ("what is an emergency fund?", "en"),
    ("explain difference between assets and liabilities", "en"),
    # Malayalam queries
    ("എന്താണ് പണം?", "ml"),
    ("എമർജൻസി ഫണ്ട് എന്നാൽ എന്ത്?", "ml"),
    ("ആസ്തികളും ബാധ്യതകളും തമ്മിലുള്ള വ്യത്യാസം എന്താണ്?", "ml"),
    # Manglish queries
    ("enthannu emergency fund?", "manglish"),
    ("what is panam and currency?", "manglish"),
    ("compound interest engane aanu calculate cheyyunnathu?", "manglish"),
]

async def check():
    session_factory = get_async_session_factory()
    embedder = LocalEmbedder()
    config = RetrievalConfig()
    
    async with session_factory() as session:
        # Check chunks count
        doc = (
            await session.execute(select(KnowledgeDocument).where(KnowledgeDocument.doc_type == "literacy"))
        ).scalar_one()
        idx_cnt = (
            await session.execute(
                select(func.count(KnowledgeChunk.id)).where(
                    KnowledgeChunk.document_id == doc.id, KnowledgeChunk.is_indexable
                )
            )
        ).scalar()
        non_idx_cnt = (
            await session.execute(
                select(func.count(KnowledgeChunk.id)).where(
                    KnowledgeChunk.document_id == doc.id, not KnowledgeChunk.is_indexable
                )
            )
        ).scalar()
        print("=== Literacy Chunks ===")
        print(f"Total chunks: {idx_cnt + non_idx_cnt} (Indexable: {idx_cnt}, Header/Non-indexable: {non_idx_cnt})")
        print()

        retriever = HybridRetriever(session=session, embedder=embedder, config=config)
        print("=== 10 Sample Retrievals ===")
        for q, lang in SAMPLE_QUERIES:
            res = await retriever.retrieve(q)
            top = res.chunks[0] if res.chunks else None
            if top:
                score = round(top.vector_score or top.fused_score or 0.0, 4)
                # fetch doc_type from db for this doc
                doc_obj = (
                    await session.execute(
                        select(KnowledgeDocument).where(KnowledgeDocument.id == top.document_id)
                    )
                ).scalar_one_or_none()
                doc_type = doc_obj.doc_type if doc_obj else "unknown"
                print(f"Query [{lang}]: \"{q}\"")
                print(f"  Top Score: {score} | Doc Type: {doc_type} | Cited Heading: {top.heading_path}")
            else:
                print(f"Query [{lang}]: \"{q}\" -> No match")
            print()

    await get_async_engine().dispose()

if __name__ == "__main__":
    asyncio.run(check())
