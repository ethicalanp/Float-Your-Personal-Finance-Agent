"""Manual verification script for Grounded RAG answers.

Runs 10 sample questions (4 English, 3 Malayalam, 3 Manglish) covering:
OTP shared, reporting fraud, helpline number, UPI safety, an out-of-scope investment question,
and one unanswerable query against the configured LLM provider.
Prints status, citations, degraded flag, validation_failures, and latency.
Zero keys or raw prompts are printed.
"""

import asyncio
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv

from app.ai.gateway.dependencies import get_llm_gateway
from app.ai.rag.answer import KnowledgeAnswerService
from app.ai.rag.answer_models import KnowledgeQuestionRequest
from app.ai.rag.embedder.base import BaseEmbedder
from app.ai.rag.embedder.local import LocalEmbedder
from app.ai.rag.retrieval import HybridRetriever, RetrievalConfig
from app.db.session import get_async_session_factory
from app.models.enums import ConsentType
from app.models.user import Consent, User

# Ensure local .env is loaded
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

SMOKE_QUESTIONS = [
    # 4 English
    {
        "lang": "English",
        "topic": "helpline number",
        "q": "What is the national helpline number for reporting online financial cyber fraud in India?",
    },
    {
        "lang": "English",
        "topic": "reporting fraud",
        "q": "How do I report an unauthorized financial fraud transaction within the golden first hour?",
    },
    {
        "lang": "English",
        "topic": "OTP shared",
        "q": "I accidentally shared my OTP with someone claiming to be bank support. What should I do immediately?",
    },
    {
        "lang": "English",
        "topic": "UPI safety",
        "q": "Can I receive money on UPI without entering my UPI PIN?",
    },
    # 3 Malayalam
    {
        "lang": "Malayalam",
        "topic": "helpline number",
        "q": "ഓൺലൈൻ സാമ്പത്തിക തട്ടിപ്പ് നടന്നാൽ വിളിക്കേണ്ട ദേശീയ ഹെൽപ്പ്‌ലൈൻ നമ്പർ ഏതാണ്?",
    },
    {
        "lang": "Malayalam",
        "topic": "OTP shared",
        "q": "ബാങ്കിൽ നിന്നാണെന്ന് പറഞ്ഞ് വിളിച്ചയാൾക്ക് അറിയാതെ ഒടിപി കൊടുത്തുപോയി. അടിയന്തരമായി ഞാൻ എന്താണ് ചെയ്യേണ്ടത്?",
    },
    {
        "lang": "Malayalam",
        "topic": "UPI safety",
        "q": "യുപിഐ വഴി അക്കൗണ്ടിലേക്ക് പണം ലഭിക്കാൻ യുപിഐ പിൻ അടിക്കേണ്ടതുണ്ടോ?",
    },
    # 3 Manglish
    {
        "lang": "Manglish",
        "topic": "reporting fraud",
        "q": "Ente accountil ninnu unauthorized aayi paisa poyi, complaint engane kodukkum?",
    },
    {
        "lang": "Manglish",
        "topic": "out-of-scope investment",
        "q": "Nale double aakan vendi njan eth stockil aanu invest cheyyendathu?",
    },
    {
        "lang": "Manglish",
        "topic": "unanswerable",
        "q": "Can aliens invest in RBI sovereign green bonds via UPI?",
    },
]


async def run_smoke() -> None:
    print("=" * 75)
    print("Float Grounded RAG Answer Smoke Test (Manual 10-Question Verification)")
    print("=" * 75)

    gateway = get_llm_gateway()
    print(f"Provider:               {gateway.config.provider}")
    print(f"Model:                  {gateway.config.model}")
    print(f"Approved for Real Data: {gateway.config.approved_for_real_data}")
    print(f"Max Concurrency:        {gateway.config.max_concurrency}")

    try:
        embedder: BaseEmbedder = LocalEmbedder()
        print("Embedder:               LocalEmbedder (intfloat/multilingual-e5-base)")
    except Exception as e:
        from app.ai.rag.embedder.fake import FakeEmbedder

        embedder = FakeEmbedder()
        print(f"Embedder:               FakeEmbedder (fallback: {type(e).__name__})")

    session_factory = get_async_session_factory()
    async with session_factory() as session:
        smoke_user_id = uuid.uuid4()
        user = User(
            id=smoke_user_id,
            email=f"smoke_{smoke_user_id.hex[:6]}@example.com",
            normalized_email=f"smoke_{smoke_user_id.hex[:6]}@example.com",
            hashed_password="mock",
            full_name="Smoke Test User",
            is_active=True,
        )
        consent = Consent(
            id=uuid.uuid4(),
            user_id=smoke_user_id,
            consent_type=ConsentType.AI_DATA_PROCESSING,
        )
        session.add_all([user, consent])
        await session.commit()

        retriever = HybridRetriever(session=session, embedder=embedder, config=RetrievalConfig())
        service = KnowledgeAnswerService(session=session, retriever=retriever, gateway=gateway)

        for idx, item in enumerate(SMOKE_QUESTIONS, 1):
            lang = item["lang"]
            topic = item["topic"]
            q = item["q"]
            print(f"\n[{idx}/10] [{lang.upper()}] Topic: {topic}")
            print(f"Question: {q}")
            t0 = time.monotonic()
            try:
                lang_hint = "en" if lang == "English" else ("ml" if lang == "Malayalam" else "manglish")
                req = KnowledgeQuestionRequest(question=q, language_hint=lang_hint)
                resp = await service.answer(req, user=user)
                elapsed_ms = (time.monotonic() - t0) * 1000.0

                print(f"  Status:              {resp.status.upper()}")
                print(f"  Confidence:          {resp.confidence.upper()}")
                print(f"  Degraded:            {resp.degraded} (Reason: {resp.degraded_reason or 'None'})")
                print(f"  Validation Failures: {resp.validation_failures if resp.validation_failures else 'None'}")
                print(f"  Citations ({len(resp.citations)}):")
                for c in resp.citations:
                    print(f"    - [{c.alias}] {c.document_title} ({c.publisher})")
                print(f"  Latency:             {elapsed_ms:.1f} ms")
                print(f"  Answer Snippet:      {resp.answer[:200]}...")
            except Exception as err:
                elapsed_ms = (time.monotonic() - t0) * 1000.0
                print(f"  FAILED:              {type(err).__name__}: {err} ({elapsed_ms:.1f} ms)")


def main() -> None:
    asyncio.run(run_smoke())


if __name__ == "__main__":
    main()
