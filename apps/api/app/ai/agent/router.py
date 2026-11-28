import re

from pydantic import BaseModel, ConfigDict, Field

from app.ai.agent.models import RouteClass, RouteResult
from app.ai.gateway.manager import LLMGateway
from app.ai.gateway.types import LLMMessage, LLMRequest

# ============================================================================
# Localized Clarifying Questions & Refusals
# ============================================================================

CLARIFYING_QUESTIONS = {
    "en": (
        "How can I help you today? You can ask about your spending summary, "
        "recurring bills, indicative loan readiness, or scam recovery advice."
    ),
    "ml": (
        "ഞാൻ എങ്ങനെയാണ് സഹായിക്കേണ്ടത്? നിങ്ങളുടെ ചെലവുകൾ, റിക്കറിംഗ് ബില്ലുകൾ, "
        "വായ്പാ യോഗ്യത, അല്ലെങ്കിൽ തട്ടിപ്പ് സഹായം എന്നിവയെക്കുറിച്ച് ചോദിക്കാം."
    ),
    "manglish": (
        "Njan enganeya sahayikkendath? Ningalude spending summary, recurring bills, "
        "loan readiness, athallenkil scam help kurichu chodikkam."
    ),
}

OUT_OF_SCOPE_REFUSALS = {
    "en": (
        "I am a read-only personal finance assistant. I cannot execute money transfers, "
        "initiate payments, or alter account records. Nor can I provide investment advice, "
        "stock/crypto recommendations, or tax filing services. I can only assist with personal "
        "spending analysis, recurring payments, indicative borrow readiness, and consumer fraud protection."
    ),
    "ml": (
        "ഞാൻ വിവരങ്ങൾ കാണാൻ മാത്രമുള്ള (read-only) പേഴ്സണൽ ഫിനാൻസ് അസിസ്റ്റന്റാണ്. "
        "പണമിടപാടുകൾ നടത്താനോ അക്കൗണ്ട് മാറ്റങ്ങൾ വരുത്താനോ എനിക്ക് കഴിയില്ല. "
        "ഓഹരി/ക്രിപ്റ്റോ നിക്ഷേപ ഉപദേശങ്ങളോ നികുതി ഫയലിംഗോ നൽകാനും സാധ്യമല്ല."
    ),
    "manglish": (
        "Njan read-only personal finance assistant aanu. Money transfer cheyyaano, payment initiate cheyyaano, "
        "records delete cheyyaano patilla. Enikku investment advice, stock recommendations, "
        "athallenkil tax filing sahayikkaan patilla."
    ),
}

# ============================================================================
# Keyword and Pattern Dictionaries
# ============================================================================

# Hard safety override keywords: ANY match routes to protect immediately.
SAFETY_OVERRIDE_PATTERNS = [
    r"\b(?:fraud|scam|scammer|phishing|blackmail|hacked|fake call|fake message|fake bank)\b",
    r"\b(?:otp|one time password|cvv|atm pin|upi pin)\b",
    (
        r"\b(?:unauthorized transaction|unauthorized|money debited without permission|"
        r"money deducted|unauthorized withdrawal)\b"
    ),
    r"\b(?:stolen|card.*stolen|stolen.*card|lost card|lost phone|blocked account|freeze account|theft)\b",
    r"\b(?:digital arrest|police call scam|fedex scam|part time job scam|telegram task scam|task scam)\b",
    r"\b(?:1930|cybercrime|cyber crime|ncrp|national cyber crime portal)\b",
    # Malayalam
    (
        r"(?:തട്ടിപ്പ|തട്ടിപ്പ്|തട്ടിപ്പുകാരൻ|ഡിജിറ്റൽ അറസ്റ്റ്|വ്യാജ|പണം പോയി|പണം നഷ്ടപ്പെട്ടു|"
        r"ഒടിപി|ഹാക്ക്|സൈബർ ക്രൈം|സൈബർക്രൈം|അക്കൗണ്ട് മരവിപ്പിച്ചു|മോഷണം|അപഹരിച്ചു|എടിഎം)"
    ),
    # Manglish
    r"\b(?:thattippu|panam poyi|scam aano|fraud aano|otp chodichu|link click cheythu|account block aayi)\b",
    r"\b(?:paisa poyi|digital arrest|police call cheythu|fraud call|scam message|card stolen|stolen|unauthorized)\b",
]

OUT_OF_SCOPE_PATTERNS = [
    (
        r"\b(?:transfer|wire|send money|pay to|pay my|delete|cancel payment|"
        r"remove transaction|change password|reset password)\b"
    ),
    r"\b(?:stock|stocks|invest|investing|investment|crypto|bitcoin|ethereum|trading|intraday|forex|nifty|shares?)\b",
    r"\b(?:tax|taxes|itr|income tax|gst|audit|tax evasion|tax return)\b",
    r"\b(?:weather|forecast|rain|cricket|match|football|recipe|movie)\b",
    r"(?:ഓഹരി|ക്രിപ്റ്റോ|ടാക്സ്|നികുതി|കാലാവസ്ഥ|മത്സരം|നിക്ഷേപിക്ക)",
    r"\b(?:stock|stocks|trading|crypto|itr|tax|filing|weather)\b",
]

CREDIT_READINESS_PATTERNS = [
    r"\b(?:loan|borrow|borrowing|credit score|cibil|eligibility|readiness|ready)\b",
    r"(?:വായ്പ|ലോൺ|ക്രെഡിറ്റ് സ്കോർ|യോഗ്യത|തയ്യാറെടുപ്പ്)",
    r"\b(?:loan|borrow|cibil|credit score|eligibility|kittumo|ready)\b",
]

PERSONAL_FINANCE_PATTERNS = [
    r"\b(?:spend|spending|spent|expense|expenses|income|salary|cash flow|statement|transaction|transactions)\b",
    r"\b(?:recurring|subscription|subscriptions|bill|bills|netflix|gym|rent|groceries|dining|utilities|budget)\b",
    r"\b(?:goal|goals|emergency fund|emergency buffer|rainy day|savings target)\b",
    r"\b(?:net worth|assets|liabilities|subscription leak|leaks)\b",
    r"\b(?:compare|monthly|category|breakdown|highest|lowest|inflow|outflow)\b",
    r"(?:ചെലവ്|ചെലവാക്കി|വരുമാനം|പണം|രൂപ|സബ്സ്ക്രിപ്ഷൻ|മാസം|സ്റ്റേറ്റ്മെന്റ്|ബില്ലുകൾ|ഭക്ഷണം)",
    r"\b(?:chelavu|varumanam|spend|spent|expense|expenses|recurring|bill|bills|paisa|kaasu|summary)\b",
]

KNOWLEDGE_PATTERNS = [
    r"\b(?:rbi|reserve bank|guideline|guidelines|rule|rules|ombudsman|dicgc|insurance|deposit)\b",
    r"\b(?:zero liability|chargeback|regulation|regulations|grievance|redressal|rights|tokenization)\b",
    r"(?:ആർബിഐ|റിസർവ് ബാങ്ക്|നിയമം|ചട്ടം|പരാതി|പരിഹാരം|ഇൻഷുറൻസ്|അവകാശങ്ങൾ)",
    r"\b(?:rbi|rules|rule|ombudsman|zero liability|deposit insurance|tokenization|guidelines)\b",
]


class LLMRouterOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    route: RouteClass = Field(description="The assigned route class")
    reason: str = Field(description="One sentence justification for this route")


def detect_query_language(text: str) -> str:
    """Detect language of user text: 'ml', 'manglish', or 'en'."""
    if any("\u0d00" <= char <= "\u0d7f" for char in text):
        return "ml"
    lower = text.lower()
    manglish_indicators = [
        "chelavu", "varumanam", "thattippu", "panam", "poyi", "enthannu", "kittumo",
        "aano", "njan", "ningalude", "engane", "nokku", "chodichu", "paisa", "ethra",
        "tharumo", "kaanikku", "vangnam"
    ]
    if any(re.search(rf"\b{word}\b", lower) for word in manglish_indicators):
        return "manglish"
    return "en"


def _matches_any(patterns: list[str], text: str) -> bool:
    for pattern in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


class IntentRouter:
    """Layered Intent Router with deterministic rules, safety overrides, and LLM fallback."""

    def __init__(self, gateway: LLMGateway | None = None) -> None:
        self.gateway = gateway

    async def route(self, query: str) -> RouteResult:
        cleaned = query.strip()
        lang = detect_query_language(cleaned)

        # 1. HARD SAFETY OVERRIDE: Fraud, scam, or cybercrime queries ALWAYS route to protect
        if _matches_any(SAFETY_OVERRIDE_PATTERNS, cleaned):
            return RouteResult(
                route=RouteClass.PROTECT,
                confidence="high",
                reason_code="safety_override",
            )

        # 2. Refusal: Out of scope
        if _matches_any(OUT_OF_SCOPE_PATTERNS, cleaned):
            return RouteResult(
                route=RouteClass.OUT_OF_SCOPE,
                confidence="high",
                reason_code="refusal_out_of_scope",
                clarifying_question=OUT_OF_SCOPE_REFUSALS.get(lang, OUT_OF_SCOPE_REFUSALS["en"]),
            )

        # 3. Check for Short / Ambiguous / Greeting Queries
        words = re.findall(r"\w+", cleaned.lower())
        greetings = {"hi", "hello", "hey", "namaskaram", "hai", "help", "halo"}
        is_greeting_or_short = (
            len(words) <= 1
            or (
                len(words) <= 3
                and any(w in greetings for w in words)
                and not any(w in ("spend", "loan", "rbi", "chelavu", "panam") for w in words)
            )
        )
        if is_greeting_or_short:
            return RouteResult(
                route=RouteClass.UNCLEAR,
                confidence="high",
                reason_code="clarification_needed",
                clarifying_question=CLARIFYING_QUESTIONS.get(lang, CLARIFYING_QUESTIONS["en"]),
            )

        has_finance = _matches_any(PERSONAL_FINANCE_PATTERNS, cleaned)
        has_knowledge = _matches_any(KNOWLEDGE_PATTERNS, cleaned)
        has_borrow = _matches_any(CREDIT_READINESS_PATTERNS, cleaned)

        # 4. Combined Route: query mentions both personal finances/borrow and regulatory guidelines
        if (has_finance or has_borrow) and has_knowledge:
            return RouteResult(
                route=RouteClass.COMBINED,
                confidence="high",
                reason_code="rule_match_combined",
            )

        # 5. Single High-Confidence Domain Routes
        if has_borrow:
            return RouteResult(
                route=RouteClass.CREDIT_READINESS,
                confidence="high",
                reason_code="rule_match_borrow",
            )
        if has_finance:
            return RouteResult(
                route=RouteClass.PERSONAL_FINANCE,
                confidence="high",
                reason_code="rule_match_finance",
            )
        if has_knowledge:
            return RouteResult(
                route=RouteClass.KNOWLEDGE,
                confidence="high",
                reason_code="rule_match_knowledge",
            )

        # 6. LLM Fallback (only when deterministic rules are not confident)
        if self.gateway is not None:
            try:
                llm_result = await self._classify_with_llm(cleaned)
                if llm_result is not None:
                    # Enforce safety override even on LLM output
                    if _matches_any(SAFETY_OVERRIDE_PATTERNS, cleaned):
                        return RouteResult(
                            route=RouteClass.PROTECT,
                            confidence="high",
                            reason_code="safety_override",
                        )
                    return llm_result
            except Exception:
                # LLM is down or timed out -> gracefully fallback
                pass

        # 7. Default to UNCLEAR with single clarifying question
        return RouteResult(
            route=RouteClass.UNCLEAR,
            confidence="low",
            reason_code="unclear_fallback",
            clarifying_question=CLARIFYING_QUESTIONS.get(lang, CLARIFYING_QUESTIONS["en"]),
        )

    async def _classify_with_llm(self, text: str) -> RouteResult | None:
        if self.gateway is None:
            return None

        prompt = (
            "You are an intent router for a personal finance assistant. Classify the user query into "
            "exactly one of the following route classes:\n"
            "- personal_finance: questions about personal spending, expenses, budget, statements, recurring bills.\n"
            "- knowledge: general questions about banking rules, RBI guidelines, ombudsman, deposit insurance.\n"
            "- protect: suspected scam, fraud, unauthorized transactions, phishing, card theft, cybercrime.\n"
            "- credit_readiness: loan readiness, credit score status, borrow eligibility.\n"
            "- combined: requests that explicitly need personal financial data AND banking guidelines.\n"
            "- out_of_scope: requests for stock trading tips, crypto purchase, tax filing, "
            "or non-finance topics.\n"
            "- unclear: ambiguous, gibberish, or vague input.\n\n"
            f"User query:\n{text}\n"
        )

        req = LLMRequest(
            messages=[LLMMessage(role="user", content=prompt)],
            response_schema=LLMRouterOutput.model_json_schema(),
            temperature=0.0,
            max_output_tokens=150,
            prompt_version="router_v1",
            data_class="demo",
        )

        resp = await self.gateway.complete(req)
        if resp.parsed and isinstance(resp.parsed, dict):
            route_val = resp.parsed.get("route")
            reason = resp.parsed.get("reason", "LLM classified")
            try:
                rc = RouteClass(route_val)
                return RouteResult(route=rc, confidence="medium", reason_code=f"llm_{reason[:30]}")
            except ValueError:
                pass
        return None
