import hashlib
import logging
import time
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.ai.gateway.errors import (
    CircuitOpen,
    RateLimited,
    Timeout,
    TransientProviderError,
)
from app.ai.gateway.manager import LLMGateway
from app.ai.gateway.types import LLMMessage, LLMRequest
from app.ai.rag.answer_models import (
    Citation,
    KnowledgeAnswerResponse,
    KnowledgeQuestionRequest,
    LLMAnswerOutput,
)
from app.ai.rag.policy_guard import PolicyGuard
from app.ai.rag.retrieval import HybridRetriever, RetrievedChunk, RetrievedEvidence
from app.ai.rag.rewriter import QueryRewriter
from app.ai.rag.validator import AnswerValidator
from app.ai.security.masking import mask_pii as mask_financial_text
from app.core.errors import ForbiddenException, NotFoundException
from app.models.conversations import Conversation, Message
from app.models.enums import AuditActor, ConsentType, MessageRole
from app.models.protect import AuditTrail
from app.models.user import Consent, User
from app.services.verified_contacts import get_all_verified_contacts

logger = logging.getLogger("app.ai.rag.answer")

PROMPT_FILE = Path(__file__).parent / "prompts" / "rag_answer_v1.md"
PROMPT_VERSION = "rag_answer_v1"
PROMPT_CONTENT = PROMPT_FILE.read_text(encoding="utf-8") if PROMPT_FILE.exists() else "Answer from evidence."
PROMPT_HASH = hashlib.sha256(PROMPT_CONTENT.encode("utf-8")).hexdigest()[:12]


class ConsentRequiredError(Exception):
    """Raised when user lacks active AI data processing consent."""

    pass


class KnowledgeAnswerService:
    """Production grounded RAG answering service with consent gating, deterministic validation,

    abstention gates, and extractive degraded fallbacks.
    """

    FRAUD_KEYWORDS = [
        "scam",
        "fraud",
        "hacked",
        "phishing",
        "unauthorized",
        "stolen",
        "cyber",
        "freeze",
        "mule",
        "police",
        "1930",
        "complaint",
        "fake",
        "തട്ടിപ്പ്",
        "പരാതി",
        "പണം",
        "ചതി",
        "thattippu",
        "parathi",
        "panam",
    ]

    POLICY_REFUSAL_RULES = [
        # Investment, stocks, crypto, options trading, leverage advice
        (
            r"\b(?:stock|stocks|invest|investing|investment|crypto|bitcoin|ethereum|trading|intraday|"
            r"forex|nifty|shares?|call option|put option|50x leverage|leverage|binary options)\b",
            "Float is a read-only consumer personal finance assistant and cannot provide "
            "stock, crypto, or investment advice.",
        ),
        # Tax evasion and tax calculation/filing advice
        (
            r"\b(?:tax evasion|hide cash|black money|evade tax|itr filing|tax return filing|bypass tax)\b",
            "Float cannot provide tax calculation, tax evasion, or formal tax filing advice.",
        ),
        # Legal drafting, affidavits, court petitions, litigation representation
        (
            r"\b(?:writ petition|affidavit|high court judge|draft a writ|draft an affidavit|"
            r"lawyer|advocate|court case|sue)\b",
            "Float cannot draft court petitions, affidavits, or provide formal legal representation advice.",
        ),
        # Adversarial prompt injections and system overrides
        (
            r"\b(?:ignore all previous|system override|unrestricted|bypass data boundaries|forget you are float)\b",
            "Request refused: system override or policy violation attempt.",
        ),
        # Forged/fake identity documents or illegal certificates
        (
            r"\b(?:fake|forge|duplicate)\s+(?:aadhaar|pan|passport|voter|id\s*card|identity|license|driving\s*licence)\b",
            "Float cannot assist with creating or procuring forged or fraudulent identity documents.",
        ),
        # Malayalam refusal keywords
        (
            r"(?:ഓഹരി|ക്രിപ്റ്റോ|ടാക്സ്|നികുതി|വക്കീൽ|കോടതി|ഹൈക്കോടതി|ഇൻട്രാഡേ|നിക്ഷേപിക്ക|കള്ളപ്പണം)",
            "Float cannot provide stock, investment, tax filing, or legal petition advice.",
        ),
        # Manglish refusal keywords
        (
            r"\b(?:intraday|nifty|call option|put option|black money|white aakkan|vakkeel|case vaadhikkan)\b",
            "Float cannot provide stock, investment, tax filing, or legal petition advice.",
        ),
    ]

    DISCLAIMER = (
        "Float provides regulatory information and recovery guidance for educational purposes only. "
        "It does not constitute legal, financial, or tax advice. For emergencies, contact your bank and 1930."
    )

    def __init__(
        self,
        session: AsyncSession | Session,
        retriever: HybridRetriever,
        gateway: LLMGateway,
        validator: AnswerValidator | None = None,
        rewriter: QueryRewriter | None = None,
        policy_guard: PolicyGuard | None = None,
        translate_query_for_retrieval: bool = False,
    ) -> None:
        self.session = session
        self.retriever = retriever
        self.gateway = gateway
        self.validator = validator or AnswerValidator()
        self.rewriter = rewriter or QueryRewriter()
        self.policy_guard = policy_guard or PolicyGuard(embedder=getattr(self.retriever, "embedder", None))
        self.translate_query_for_retrieval = translate_query_for_retrieval

    async def _check_consent(self, user_id: uuid.UUID) -> None:
        """Verify user has an active ai_data_processing consent."""
        stmt = (
            select(Consent)
            .where(
                Consent.user_id == user_id,
                Consent.consent_type == ConsentType.AI_DATA_PROCESSING,
                Consent.revoked_at.is_(None),
            )
            .limit(1)
        )
        if isinstance(self.session, AsyncSession):
            result = await self.session.execute(stmt)
            consent = result.scalar_one_or_none()
        else:
            consent = self.session.execute(stmt).scalar_one_or_none()

        if not consent:
            raise ConsentRequiredError(
                "AI data processing consent (ai_data_processing) is required to use the assistant."
            )

    def _is_fraud_topic(self, query: str) -> bool:
        q_lower = query.lower()
        return any(kw in q_lower for kw in self.FRAUD_KEYWORDS)

    def _format_helpline_text(self) -> str:
        contacts = get_all_verified_contacts()
        portal = next((c for c in contacts if c.get("toll_free_number") == "1930"), None)
        text = "\n\n**Official Helplines for Immediate Assistance:**\n"
        if portal:
            p_notice = portal.get("priority_notice", "Call immediately within the golden hour to freeze funds.")
            text += (
                f"- National Cyber Crime Helpline: **{portal['toll_free_number']}** (or call 112)\n"
                f"- Official Portal: {portal.get('website', 'https://cybercrime.gov.in')}\n"
                f"- Priority Action: {p_notice}\n"
            )
        text += "- Contact your bank's official 24x7 customer support immediately to block cards and netbanking."
        return text

    def _build_citations(self, cited_aliases: list[str], alias_map: dict[str, RetrievedChunk]) -> list[Citation]:
        citations: list[Citation] = []
        for alias in cited_aliases:
            chunk = alias_map.get(alias)
            if chunk:
                citations.append(
                    Citation(
                        alias=alias,
                        chunk_id=chunk.chunk_id,
                        document_title=chunk.title,
                        publisher=chunk.publisher,
                        heading=chunk.heading_path,
                        source_url=chunk.source_url,
                        effective_date=chunk.effective_date,
                    )
                )
        return citations

    def _compute_confidence(
        self,
        status: str,
        evidence: RetrievedEvidence,
        validation_failures: list[str],
        repaired: bool,
    ) -> str:
        if status != "answered":
            return "low"
        if evidence.degraded or repaired or validation_failures:
            return "medium"
        if evidence.top_fused_score >= 0.02 and len(evidence.chunks) >= 2:
            return "high"
        return "medium"

    def _create_extractive_fallback(
        self,
        query: str,
        evidence: RetrievedEvidence,
        alias_map: dict[str, RetrievedChunk],
        reason: str,
    ) -> LLMAnswerOutput:
        """Create a safe extractive fallback from top retrieved evidence snippets."""
        if not evidence.chunks:
            return LLMAnswerOutput(
                status="insufficient_evidence",
                answer="No official regulatory documentation was found to answer your inquiry."
                + (self._format_helpline_text() if self._is_fraud_topic(query) else ""),
                cited_aliases=[],
                refusal_reason=None,
            )

        top_chunks = evidence.chunks[:2]
        aliases = [k for k, v in alias_map.items() if v in top_chunks]

        snippets = []
        for a in aliases:
            c = alias_map[a]
            snippet = c.text[:250].strip()
            snippets.append(f"[{a}] {snippet}...")

        answer = "Here is the relevant excerpt from official regulatory guidance:\n\n" + "\n\n".join(snippets)
        if self._is_fraud_topic(query):
            answer += self._format_helpline_text()

        return LLMAnswerOutput(
            status="answered",
            answer=answer,
            cited_aliases=aliases,
            refusal_reason=None,
        )

    async def _translate_query_to_english(
        self,
        query: str,
        lang: str,
        user_id: uuid.UUID,
        trace_id: str,
    ) -> str:
        """Translate Malayalam/Manglish query to English for retrieval while preserving original for answering."""
        if not self.gateway or self.gateway.config.provider == "fake":
            return query
        try:
            req = LLMRequest(
                messages=[
                    LLMMessage(
                        role="system",
                        content=(
                            "Translate the user's Malayalam or Manglish personal-finance/cyber-fraud question "
                            "into concise English search keywords/question. Output ONLY the English text."
                        ),
                    ),
                    LLMMessage(role="user", content=f"[{lang}] {query}"),
                ],
                temperature=0.0,
                max_output_tokens=1500,
                prompt_version="query_translate_v1",
                trace_id=trace_id,
                user_id=str(user_id),
                data_class="masked_real",
            )
            resp = await self.gateway.complete(req)
            translated = (resp.text or "").strip()
            return translated if translated else query
        except Exception as exc:
            logger.warning("Query translation fallback (%s); using original query.", type(exc).__name__)
            return query

    def _build_soft_abstain_response(
        self,
        masked_question: str,
        evidence: RetrievedEvidence,
        effective_lang: str,
        trace_id: str,
    ) -> KnowledgeAnswerResponse:
        """Return borderline soft abstain: state what is known with citations and offer 2 related questions."""
        top_chunks = evidence.chunks[:2]
        alias_map = {f"E{i + 1}": c for i, c in enumerate(top_chunks)}
        citations = self._build_citations(list(alias_map.keys()), alias_map)

        known_lines = []
        related_questions: list[str] = []
        for alias, chunk in alias_map.items():
            snippet = chunk.text.strip().replace("\n", " ")[:220]
            known_lines.append(f"- [{alias}] {chunk.title}: {snippet}...")
            topic = (chunk.heading_path or chunk.title).split(">")[-1].strip()
            related_questions.append(f"What does {chunk.title} say about {topic}?")

        while len(related_questions) < 2:
            related_questions.append("How do I report an unauthorized digital payment or UPI fraud on 1930?")
        related_questions = related_questions[:2]

        answer_text = (
            "Official documents do not directly answer your exact question with high certainty, "
            "but here is what is known from related verified sources:\n\n"
            + "\n".join(known_lines)
            + "\n\nRelated questions you can ask:\n"
            + f"1. {related_questions[0]}\n"
            + f"2. {related_questions[1]}"
        )
        if self._is_fraud_topic(masked_question):
            answer_text += self._format_helpline_text()

        return KnowledgeAnswerResponse(
            status="insufficient_evidence",
            answer=answer_text,
            citations=citations,
            confidence="low",
            refusal_reason=None,
            language=effective_lang,
            degraded=evidence.degraded,
            degraded_reason=evidence.degraded_reason,
            disclaimer=self.DISCLAIMER,
            trace_id=trace_id,
            prompt_version=f"{PROMPT_VERSION}:{PROMPT_HASH}",
            model=self.gateway.config.model,
            provider=self.gateway.config.provider,
            validation_failures=[],
            soft_abstain=True,
            related_questions=related_questions,
        )

    def _check_policy_guard(
        self,
        question: str,
        language_hint: str | None,
        trace_id: str,
        kb_sim: float | None = None,
    ) -> KnowledgeAnswerResponse | None:
        """Evaluate multi-layer policy rules (Regex Layer 1 + Intent/Semantic Layer 2)."""
        res = self.policy_guard.check(question, language_hint=language_hint, kb_sim=kb_sim)
        if res.refused:
            lang = language_hint or "en"
            reason_text = res.reason or "This request is outside Float's verified regulatory scope."
            return KnowledgeAnswerResponse(
                status="refused",
                answer=f"I cannot fulfill this request. {reason_text}",
                citations=[],
                confidence="high",
                refusal_reason=reason_text,
                language=lang,
                degraded=False,
                degraded_reason=None,
                disclaimer=self.DISCLAIMER,
                trace_id=trace_id,
                prompt_version=f"policy_guard_v2_{res.layer}",
                model=self.gateway.config.model if self.gateway else "guard",
                provider=self.gateway.config.provider if self.gateway else "local",
                validation_failures=[],
            )
        return None

    async def answer(self, request: KnowledgeQuestionRequest, user: User) -> KnowledgeAnswerResponse:
        t0 = time.monotonic()
        trace_id = uuid.uuid4().hex

        # 1. Consent Gate (403 if missing)
        await self._check_consent(user.id)

        # 2. Policy Guard before retrieval (reject out-of-scope advice requests immediately)
        guard_response = self._check_policy_guard(request.question, request.language_hint, trace_id)
        if guard_response:
            return guard_response

        # 3. Mask the Question
        masked_question = mask_financial_text(request.question)

        # 3. Follow-up Rewriting using Conversation Window
        history_messages: list[Message] = []
        conversation: Conversation | None = None
        if request.conversation_id:
            conv_stmt = select(Conversation).where(
                Conversation.id == request.conversation_id,
            )
            if isinstance(self.session, AsyncSession):
                res = await self.session.execute(conv_stmt)
                conversation = res.scalar_one_or_none()
            else:
                conversation = self.session.execute(conv_stmt).scalar_one_or_none()

            if not conversation:
                raise NotFoundException(f"Conversation {request.conversation_id} not found")
            if conversation.user_id != user.id:
                raise ForbiddenException("Access to this conversation is forbidden")

            if conversation:
                msg_stmt = (
                    select(Message)
                    .where(Message.conversation_id == conversation.id)
                    .order_by(Message.created_at.desc())
                    .limit(6)
                )
                if isinstance(self.session, AsyncSession):
                    m_res = await self.session.execute(msg_stmt)
                    history_messages = list(reversed(m_res.scalars().all()))
                else:
                    history_messages = list(reversed(self.session.execute(msg_stmt).scalars().all()))

        search_query = self.rewriter.rewrite(masked_question, history_messages)
        effective_lang = request.language_hint or "en"
        if self.translate_query_for_retrieval and effective_lang in ("ml", "manglish"):
            search_query = await self._translate_query_to_english(
                search_query, effective_lang, user.id, trace_id
            )

        # 4. Phase 3 Hybrid Retrieval
        try:
            evidence = await self.retriever.retrieve(
                search_query,
                query_language_hint=effective_lang,
            )
        except TypeError:
            evidence = await self.retriever.retrieve(search_query)

        # 4b. Calibrated Semantic Policy Guard evaluation (Layer 2B with retrieval evidence score)
        semantic_guard = self._check_policy_guard(
            request.question, request.language_hint, trace_id, kb_sim=evidence.top_vector_score
        )
        if semantic_guard:
            return semantic_guard

        # 5. Abstention Gate BEFORE LLM (with Soft Abstain for borderline confidence)
        if not evidence.chunks or not evidence.passed_min_evidence:
            cfg = getattr(self.retriever, "config", None)
            min_thr = cfg.threshold_for_language(effective_lang) if cfg else 0.83
            soft_min = getattr(cfg, "soft_abstain_min_score", 0.76) if cfg else 0.76
            embedder_name = getattr(getattr(self.retriever, "embedder", None), "model_name", "")
            is_fake_embedder = embedder_name == "fake-deterministic-embedder"
            top_score = evidence.top_fused_score if (is_fake_embedder or min_thr < 0.1) else evidence.top_vector_score
            borderline = bool(evidence.chunks) and (
                (0.005 <= top_score < 0.01) if is_fake_embedder else (soft_min <= top_score < min_thr)
            )

            if borderline:
                resp = self._build_soft_abstain_response(
                    masked_question=masked_question,
                    evidence=evidence,
                    effective_lang=effective_lang,
                    trace_id=trace_id,
                )
            else:
                answer_text = (
                    "Official regulatory documents do not contain sufficient evidence "
                    "to answer this inquiry with certainty."
                )
                if self._is_fraud_topic(masked_question):
                    answer_text += self._format_helpline_text()

                resp = KnowledgeAnswerResponse(
                    status="insufficient_evidence",
                    answer=answer_text,
                    citations=[],
                    confidence="low",
                    refusal_reason=None,
                    language=effective_lang,
                    degraded=evidence.degraded,
                    degraded_reason=evidence.degraded_reason,
                    disclaimer=self.DISCLAIMER,
                    trace_id=trace_id,
                    prompt_version=f"{PROMPT_VERSION}:{PROMPT_HASH}",
                    model=self.gateway.config.model,
                    provider=self.gateway.config.provider,
                    validation_failures=[],
                    soft_abstain=False,
                    related_questions=[],
                )
            await self._persist_and_audit(user.id, request, masked_question, resp, trace_id, time.monotonic() - t0)
            return resp

        # 6. Build Evidence Prompt with Short Aliases (E1, E2, ...)
        alias_map: dict[str, RetrievedChunk] = {}
        evidence_blocks: list[str] = []
        for idx, chunk in enumerate(evidence.chunks):
            alias = f"E{idx + 1}"
            alias_map[alias] = chunk
            block = (
                f'<data_boundary source="{chunk.source_url}" citation="{alias}">\n'
                f"Title: {chunk.title}\n"
                f"Section: {chunk.heading_path or 'General'}\n"
                f"{chunk.text}\n"
                f"</data_boundary>"
            )
            evidence_blocks.append(block)

        formatted_evidence = "\n\n".join(evidence_blocks)
        user_prompt = (
            f"Question: {masked_question}\n"
            f"Language Requested: {request.language_hint or 'Match question language'}\n\n"
            f"Evidence Documents:\n{formatted_evidence}\n\n"
            f"Answer the question following all standing instructions and provide the structured response."
        )

        llm_messages = [
            LLMMessage(role="system", content=PROMPT_CONTENT),
            LLMMessage(role="user", content=user_prompt),
        ]

        llm_req = LLMRequest(
            messages=llm_messages,
            response_schema=LLMAnswerOutput,
            temperature=0.0,
            max_output_tokens=800,
            prompt_version=PROMPT_VERSION,
            trace_id=trace_id,
            user_id=str(user.id),
            data_class="masked_real",
        )

        # 7. LLM Gateway Execution with Degraded Handling
        degraded = evidence.degraded
        degraded_reasons: list[str] = [evidence.degraded_reason] if evidence.degraded_reason else []
        repaired = False
        output: LLMAnswerOutput | None = None

        try:
            llm_resp = await self.gateway.complete(llm_req)
            if isinstance(llm_resp.parsed, LLMAnswerOutput):
                output = llm_resp.parsed
            elif isinstance(llm_resp.parsed, dict):
                output = LLMAnswerOutput(**llm_resp.parsed)
            else:
                # Fallback to direct extractive
                degraded = True
                degraded_reasons.append("UnparseableStructuredOutput")
                output = self._create_extractive_fallback(
                    masked_question, evidence, alias_map, "UnparseableStructuredOutput"
                )
        except (Timeout, CircuitOpen, RateLimited, TransientProviderError, Exception) as exc:
            logger.warning("LLM Gateway failed (%s), switching to extractive fallback", type(exc).__name__)
            degraded = True
            degraded_reasons.append(f"GatewayError({type(exc).__name__})")
            output = self._create_extractive_fallback(
                masked_question, evidence, alias_map, f"GatewayError({type(exc).__name__})"
            )

        # 8. Deterministic Validation & Bounded Repair
        failures: list[str] = []
        if output and not degraded:
            failures = self.validator.validate(output, alias_map, user_language=request.language_hint or "en")

            # If validation failed, attempt 1 bounded repair
            if failures:
                repair_msg = (
                    "Your previous response failed validation with the following errors:\n"
                    "- " + "\n- ".join(failures) + "\n\n"
                    "Please correct the output. Ensure every cited alias (E1, E2) exists in the evidence, "
                    "all numbers and helplines appear in the evidence, and no prohibited advice is given."
                )
                repair_req = LLMRequest(
                    messages=llm_messages
                    + [
                        LLMMessage(role="assistant", content=output.answer),
                        LLMMessage(role="user", content=repair_msg),
                    ],
                    response_schema=LLMAnswerOutput,
                    temperature=0.0,
                    max_output_tokens=800,
                    prompt_version=f"{PROMPT_VERSION}_repair",
                    trace_id=trace_id,
                    user_id=str(user.id),
                    data_class="masked_real",
                )
                try:
                    rep_resp = await self.gateway.complete(repair_req)
                    rep_out = rep_resp.parsed if isinstance(rep_resp.parsed, LLMAnswerOutput) else None
                    if rep_out:
                        rep_failures = self.validator.validate(
                            rep_out, alias_map, user_language=request.language_hint or "en"
                        )
                        if not rep_failures:
                            output = rep_out
                            failures = []
                            repaired = True
                        else:
                            failures = rep_failures
                except Exception as r_err:
                    failures.append(f"RepairFailed({type(r_err).__name__})")

                # If still failed after 1 repair -> extractive fallback!
                if failures:
                    degraded = True
                    degraded_reasons.append("ValidationRepairFailed: " + "; ".join(failures[:2]))
                    output = self._create_extractive_fallback(masked_question, evidence, alias_map, "ValidationFailed")

        assert output is not None
        citations = self._build_citations(output.cited_aliases, alias_map)
        confidence = self._compute_confidence(output.status, evidence, failures, repaired)

        final_response = KnowledgeAnswerResponse(
            status=output.status,
            answer=output.answer,
            citations=citations,
            confidence=confidence,  # type: ignore[arg-type]
            refusal_reason=output.refusal_reason,
            language=request.language_hint or "en",
            degraded=degraded,
            degraded_reason="; ".join(degraded_reasons) if degraded_reasons else None,
            disclaimer=self.DISCLAIMER,
            trace_id=trace_id,
            prompt_version=f"{PROMPT_VERSION}:{PROMPT_HASH}",
            model=self.gateway.config.model,
            provider=self.gateway.config.provider,
            validation_failures=failures,
        )

        # 9. Persist conversation & Audit log
        await self._persist_and_audit(
            user.id, request, masked_question, final_response, trace_id, time.monotonic() - t0
        )

        # Safe logging: zero raw query/answer text
        logger.info(
            "RAG Answer completed trace_id=%s status=%s citations=%d latency_ms=%.1f degraded=%s",
            trace_id,
            final_response.status,
            len(final_response.citations),
            (time.monotonic() - t0) * 1000.0,
            final_response.degraded,
        )

        return final_response

    async def _persist_and_audit(
        self,
        user_id: uuid.UUID,
        request: KnowledgeQuestionRequest,
        masked_question: str,
        response: KnowledgeAnswerResponse,
        trace_id: str,
        duration_s: float,
    ) -> None:
        """Persist masked conversation turns and metadata-only audit entry."""
        conv_id = request.conversation_id
        if not conv_id:
            conv = Conversation(
                id=uuid.uuid4(),
                user_id=user_id,
                title=masked_question[:40],
            )
            self.session.add(conv)
            conv_id = conv.id

        user_msg = Message(
            id=uuid.uuid4(),
            user_id=user_id,
            conversation_id=conv_id,
            role=MessageRole.USER,
            content_masked=masked_question,
            trace_id=trace_id,
        )
        assistant_msg = Message(
            id=uuid.uuid4(),
            user_id=user_id,
            conversation_id=conv_id,
            role=MessageRole.ASSISTANT,
            content_masked=response.answer,
            trace_id=trace_id,
        )
        self.session.add_all([user_msg, assistant_msg])

        audit = AuditTrail(
            id=uuid.uuid4(),
            user_id=user_id,
            actor=AuditActor.USER,
            action="assistant_knowledge_query",
            resource_type="knowledge",
            resource_id=trace_id,
            metadata_json={
                "status": response.status,
                "confidence": response.confidence,
                "citation_count": len(response.citations),
                "citation_ids": [c.chunk_id for c in response.citations],
                "degraded": response.degraded,
                "latency_ms": round(duration_s * 1000.0, 2),
                "validation_failures": response.validation_failures,
            },
        )
        self.session.add(audit)

        if isinstance(self.session, AsyncSession):
            await self.session.commit()
        else:
            self.session.commit()
