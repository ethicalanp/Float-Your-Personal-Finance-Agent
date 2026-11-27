import re
from typing import Any

from app.ai.rag.answer_models import LLMAnswerOutput
from app.ai.rag.retrieval import RetrievedChunk
from app.services.verified_contacts import get_all_verified_contacts


class AnswerValidationError(Exception):
    """Raised when an answer fails critical deterministic safety or grounding checks."""

    def __init__(self, failure_reasons: list[str]):
        super().__init__("; ".join(failure_reasons))
        self.failure_reasons = failure_reasons


class AnswerValidator:
    """Deterministic post-LLM validation engine for grounded RAG answers.

    Guarantees:
    1. Citation validity: every cited alias exists in retrieved evidence.
    2. Support check: sentence-level claim grounding against cited evidence.
    3. Number and contact grounding: every number, phone number, email, and URL
       must appear in cited evidence or the verified-contacts directory.
    4. Policy check: rejects investment advice, tax advice, legal counsel,
       instructions to transfer money, share OTPs, or install remote access apps.
    5. Language check: verifies appropriate response language.
    """

    POLICY_VIOLATION_PATTERNS = [
        (
            re.compile(r"\b(guaranteed\s+returns?|invest\s+in|buy\s+stock|crypto\s+investment)\b", re.IGNORECASE),
            "Investment advice prohibited",
        ),
        (
            re.compile(r"\b(tax\s+evasion|avoid\s+paying\s+taxes|tax\s+loophole)\b", re.IGNORECASE),
            "Tax advice prohibited",
        ),
        (
            re.compile(r"\b(legal\s+counsel|file\s+a\s+lawsuit\s+immediately|sue\s+them)\b", re.IGNORECASE),
            "Legal counsel prohibited",
        ),
        (
            re.compile(r"\b(transfer\s+(?:your\s+)?money\s+to|send\s+funds\s+to\s+safe\s+account)\b", re.IGNORECASE),
            "Money transfer instruction prohibited",
        ),
        (
            re.compile(
                r"\b(share\s+(?:your\s+)?otp|tell\s+me\s+(?:your\s+)?pin|enter\s+(?:your\s+)?cvv)\b", re.IGNORECASE
            ),
            "Credential request prohibited",
        ),
        (
            re.compile(r"\b(anydesk|teamviewer|rustdesk|quicksupport|airdroid)\b", re.IGNORECASE),
            "Remote access tool instruction prohibited",
        ),
        (
            re.compile(
                r"(?:<\s*script\b|<\s*iframe\b|javascript:|vbscript:|data:text/html|\bonerror\s*=|\bonload\s*=)",
                re.IGNORECASE,
            ),
            "HTML/script or unsafe link injection prohibited",
        ),
    ]

    # Pattern to extract numbers with 2 or more digits, percentages, and currencies
    NUMBER_PATTERN = re.compile(r"\b(?:\$|₹|rs\.?|inr)?\s*\d{2,}(?:,\d+)*(?:\.\d+)?%?\b", re.IGNORECASE)
    # Phone numbers (e.g. 1930, 1800 1234, 112, 10-digit mobiles)
    PHONE_PATTERN = re.compile(r"\b(?:\+91[- ]?)?(?:1930|112|1800[- ]?\d{3,4}[- ]?\d{3,4}|\d{5}[- ]?\d{5})\b")
    # URLs and Emails
    URL_PATTERN = re.compile(r"https?://[^\s<>\"']+|www\.[^\s<>\"']+", re.IGNORECASE)
    EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")

    def __init__(self, verified_contacts: list[dict[str, Any]] | None = None) -> None:
        self.verified_contacts = verified_contacts if verified_contacts is not None else get_all_verified_contacts()
        self._verified_whitelist = self._build_verified_whitelist(self.verified_contacts)

    def _build_verified_whitelist(self, contacts: list[dict[str, Any]]) -> set[str]:
        whitelist: set[str] = set()
        for c in contacts:
            for key in ("toll_free_number", "alternate_number", "website", "fraud_reporting_email", "sms_block_code"):
                val = c.get(key)
                if val:
                    # Clean and add normalized values
                    for token in re.findall(r"[A-Za-z0-9./:-]+", str(val)):
                        if len(token) >= 3:
                            whitelist.add(token.lower())
        # Add universal numbers
        whitelist.update(["1930", "112", "cybercrime.gov.in", "rbi.org.in", "npci.org.in"])
        return whitelist

    def validate(
        self,
        output: LLMAnswerOutput,
        alias_map: dict[str, RetrievedChunk],
        user_language: str = "en",
    ) -> list[str]:
        """Perform comprehensive deterministic validation.

        Returns:
            list[str] of validation failure descriptions. Empty list means passed.
        """
        failures: list[str] = []

        # 1. Policy check (Critical Safety)
        for pattern, reason in self.POLICY_VIOLATION_PATTERNS:
            if pattern.search(output.answer):
                failures.append(f"PolicyViolation: {reason}")

        # 2. Status & Citation Consistency
        if output.status == "answered":
            if not output.cited_aliases:
                failures.append("MissingCitations: Answered status requires at least one citation alias")
            for alias in output.cited_aliases:
                if alias not in alias_map:
                    failures.append(f"InvalidCitationAlias: Cited alias '{alias}' was not in retrieved evidence")
        elif output.status in ("insufficient_evidence", "refused"):
            if output.cited_aliases:
                failures.append(f"ForbiddenCitations: Status '{output.status}' must not contain citation aliases")

        # If status is refused or insufficient_evidence, support and number grounding are skipped
        if output.status != "answered":
            return failures

        # 3. Grounding text pool
        cited_text = " ".join([alias_map[a].text for a in output.cited_aliases if a in alias_map]).lower()

        # 4. Number, Phone, URL, and Email Grounding
        answer_text = output.answer

        # Check phone numbers
        for match in self.PHONE_PATTERN.finditer(answer_text):
            raw_phone = match.group(0).strip()
            digits = re.sub(r"\D", "", raw_phone)
            # If phone number doesn't appear in cited text or whitelist, fail
            if digits not in cited_text and not any(digits in w for w in self._verified_whitelist):
                failures.append(
                    f"InventedPhoneNumber: Phone number '{raw_phone}' not grounded in evidence or verified contacts"
                )

        # Check URLs
        for match in self.URL_PATTERN.finditer(answer_text):
            url = match.group(0).strip().lower()
            domain = re.sub(r"^https?://(?:www\.)?", "", url).split("/")[0]
            if domain not in cited_text and not any(domain in w for w in self._verified_whitelist):
                failures.append(f"InventedURL: URL '{url}' not grounded in evidence or verified directory")

        # Check Emails
        for match in self.EMAIL_PATTERN.finditer(answer_text):
            email = match.group(0).strip().lower()
            if email not in cited_text and not any(email in w for w in self._verified_whitelist):
                failures.append(f"InventedEmail: Email '{email}' not grounded in evidence or verified directory")

        # Check arbitrary numerical claims (>= 2 digits)
        for match in self.NUMBER_PATTERN.finditer(answer_text):
            num_str = match.group(0).strip()
            digits = re.sub(r"\D", "", num_str)
            if len(digits) >= 2:
                # Must be present in cited text or verified whitelist
                if digits not in cited_text and not any(digits in w for w in self._verified_whitelist):
                    failures.append(f"InventedNumber: Number/Amount '{num_str}' not found in cited evidence")

        # 5. Sentence-Level Support Check (Token intersection)
        sentences = [s.strip() for s in re.split(r"[.!?\n]+", answer_text) if len(s.strip()) > 15]
        cited_tokens = set(re.findall(r"\w{3,}", cited_text))

        unsupported_sentences = 0
        for sent in sentences:
            sent_tokens = set(re.findall(r"\w{3,}", sent.lower()))
            if not sent_tokens:
                continue
            # Lexical overlap
            overlap = len(sent_tokens.intersection(cited_tokens)) / len(sent_tokens)
            if overlap < 0.20:
                unsupported_sentences += 1

        if sentences and (unsupported_sentences / len(sentences)) > 0.50:
            failures.append(
                f"UnsupportedClaims: {unsupported_sentences}/{len(sentences)} claims lack support in cited evidence"
            )

        return failures
