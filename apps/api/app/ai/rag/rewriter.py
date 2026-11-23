import re
from typing import Sequence

from app.models.conversations import Message


class QueryRewriter:
    """Safe conversation query rewriter for grounded RAG.

    Hard Rules:
    1. Rewrites ambiguous follow-up pronouns/phrases into standalone search queries.
    2. The rewrite CANNOT add external facts or hallucinated rules.
    3. Financial numbers (amounts, balances, account digits) from earlier turns are NEVER reused
       or injected into the search query.
    """

    PRONOUN_OR_FOLLOWUP_PATTERNS = [
        r"^(it|this|that|these|those)\b",
        r"^(what about|how about|and|then|so)\b",
        r"^(is it|can i|does it|should i|is this)\b",
        r"^(how long|what is the time|where to|who to)\b",
        r"^(ഇത്|അത്|എങ്ങനെ|എവിടെ|എത്ര)\b",  # Malayalam demonstratives/interrogatives
        r"^(ithu|athu|athinte|ithinte|enganeyanu)\b",  # Manglish demonstratives
    ]

    NUMBER_PATTERN = re.compile(r"\b(?:\$|₹|rs\.?|inr)?\s*\d+(?:,\d+)*(?:\.\d+)?%?\b", re.IGNORECASE)

    def rewrite(self, current_question: str, history: Sequence[Message]) -> str:
        clean_q = current_question.strip()
        if not history:
            return clean_q

        # Check if question appears to be an ambiguous follow-up
        is_followup = False
        lower_q = clean_q.lower()
        for pat in self.PRONOUN_OR_FOLLOWUP_PATTERNS:
            if re.search(pat, lower_q):
                is_followup = True
                break

        if not is_followup and len(clean_q.split()) > 5:
            # Standalone question with sufficient length
            return clean_q

        # Extract topical anchor from recent history (last 1-2 user queries)
        # Strip ALL numbers from history to ensure financial numbers are never reused
        recent_user_turns = [m.content_masked for m in history if m.role.value == "user"]
        if not recent_user_turns:
            return clean_q

        last_user_query = recent_user_turns[-1]
        # Remove any financial amounts or numbers from prior query
        topic_anchor = self.NUMBER_PATTERN.sub("", last_user_query).strip()
        # Clean multiple spaces and punctuation
        topic_anchor = re.sub(r"[?!.,;]+", " ", topic_anchor).strip()

        # If current question is very short or pronoun-only (e.g., "how long do I have to report it?")
        # combine the question with the sanitized topic anchor without inventing facts
        if topic_anchor and topic_anchor.lower() not in lower_q:
            # Remove redundant pronouns from current question
            sanitized_current = re.sub(r"\b(it|this|that)\b", "", clean_q, flags=re.IGNORECASE).strip()
            rewritten = f"{sanitized_current} ({topic_anchor})"
            return rewritten

        return clean_q
