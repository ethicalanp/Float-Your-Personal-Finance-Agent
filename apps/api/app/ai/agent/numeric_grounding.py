import re
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, Field

from app.ai.tools.base import Fact

MALAYALAM_DIGIT_MAP = {
    "൦": "0",
    "൧": "1",
    "൨": "2",
    "൩": "3",
    "൪": "4",
    "൫": "5",
    "൬": "6",
    "൭": "7",
    "൮": "8",
    "൯": "9",
}

# Known non-factual operational numbers (e.g., official helpline, current year)
WHITELISTED_OPERATIONAL_NUMBERS = {
    Decimal("1930"),  # National Cybercrime Helpline
    Decimal("2024"),  # Years
    Decimal("2025"),
    Decimal("2026"),
    Decimal("2027"),
}


class GroundingValidationResult(BaseModel):
    is_valid: bool
    ungrounded_numbers: list[str] = Field(default_factory=list)
    grounded_facts: list[str] = Field(default_factory=list)
    total_numbers_found: int = 0


def translate_malayalam_digits(text: str) -> str:
    """Translate Malayalam numerals to ASCII digits."""
    result = []
    for ch in text:
        result.append(MALAYALAM_DIGIT_MAP.get(ch, ch))
    return "".join(result)


def parse_indian_number(token: str) -> Decimal | None:
    """Parse string containing Indian numbers, currency, commas, lakh, crore, or percentages into Decimal."""
    cleaned = token.strip().replace(",", "")
    cleaned = re.sub(r"^[₹\$\€\£]|^(?:rs\.?|inr)\s*", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = cleaned.rstrip("%").strip()

    # Check for lakh / crore
    lakh_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:lakh|lakhs|l)\b", cleaned, re.IGNORECASE)
    if lakh_match:
        try:
            return Decimal(lakh_match.group(1)) * Decimal("100000")
        except InvalidOperation:
            return None

    crore_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:crore|crores|cr)\b", cleaned, re.IGNORECASE)
    if crore_match:
        try:
            return Decimal(crore_match.group(1)) * Decimal("10000000")
        except InvalidOperation:
            return None

    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


class NumericGroundingValidator:
    """Validates that every number in an assistant answer is grounded in tool facts or retrieved evidence."""

    def validate(
        self,
        answer_text: str,
        facts: list[Fact],
        evidence_chunks: list[dict[str, Any]] | None = None,
    ) -> GroundingValidationResult:
        # 1. Translate Malayalam numerals
        normalized_text = translate_malayalam_digits(answer_text)

        # 2. Extract grounded fact numbers
        fact_values: dict[Decimal, str] = {}
        for f in facts:
            val_dec = parse_indian_number(f.value)
            if val_dec is not None:
                fact_values[val_dec] = f.id
                # Add common roundings
                fact_values[round(val_dec, 2)] = f.id
                fact_values[round(val_dec, 0)] = f.id

        # 3. Extract numbers present in quoted evidence chunks
        evidence_numbers: set[Decimal] = set()
        if evidence_chunks:
            for chunk in evidence_chunks:
                chunk_text = translate_malayalam_digits(chunk.get("content", ""))
                # Extract numbers from evidence chunk
                for num_match in re.findall(r"\b\d+(?:,\d+)*(?:\.\d+)?\b", chunk_text):
                    dec = parse_indian_number(num_match)
                    if dec is not None:
                        evidence_numbers.add(dec)

        # 4. Extract all candidate numbers from answer_text
        # Remove citation aliases [E1], [E2] before scanning
        scrubbed = re.sub(r"\[E\d+\]", "", normalized_text)
        # Matches numbers with optional commas and decimals, optional prefix/suffix
        number_tokens = re.findall(
            r"(?:₹|Rs\.?|INR\s*)?\b\d+(?:,\d+)*(?:\.\d+)?(?:\s*(?:lakh|crore|cr|l|%))?\b%?",
            scrubbed,
            flags=re.IGNORECASE,
        )

        ungrounded: list[str] = []
        grounded_fact_ids: set[str] = set()
        total_found = 0

        for raw_token in number_tokens:
            token = raw_token.strip()
            val = parse_indian_number(token)
            if val is None:
                continue

            total_found += 1

            # Check whitelisted operational constants (like 1930, current year)
            if val in WHITELISTED_OPERATIONAL_NUMBERS:
                continue

            # Check exact or rounded match with facts
            matched_fact = False
            for fact_val, fact_id in fact_values.items():
                if abs(val - fact_val) <= Decimal("0.05"):
                    grounded_fact_ids.add(fact_id)
                    matched_fact = True
                    break

            if matched_fact:
                continue

            # Check match with evidence chunks
            matched_evidence = False
            for ev_val in evidence_numbers:
                if abs(val - ev_val) <= Decimal("0.05"):
                    matched_evidence = True
                    break

            if matched_evidence:
                continue

            ungrounded.append(raw_token)

        is_valid = len(ungrounded) == 0
        return GroundingValidationResult(
            is_valid=is_valid,
            ungrounded_numbers=ungrounded,
            grounded_facts=list(grounded_fact_ids),
            total_numbers_found=total_found,
        )
