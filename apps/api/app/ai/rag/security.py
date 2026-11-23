import re
from typing import Any

INJECTION_PATTERNS = [
    (re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions", re.IGNORECASE), "instruction_override"),
    (re.compile(r"disregard\s+(all\s+)?(previous|prior|above)\s+instructions", re.IGNORECASE), "instruction_override"),
    (re.compile(r"<\s*\|\s*im_start\s*\|>", re.IGNORECASE), "chat_template_delimiter"),
    (re.compile(r"<\s*\|\s*im_end\s*\|>", re.IGNORECASE), "chat_template_delimiter"),
    (re.compile(r"<\s*\|\s*system\s*\|>", re.IGNORECASE), "chat_template_delimiter"),
    (re.compile(r"\[\s*INST\s*\]", re.IGNORECASE), "llama_inst_delimiter"),
    (re.compile(r"^\s*(system|developer|assistant|human)\s*:\s*", re.MULTILINE | re.IGNORECASE), "role_impersonation"),
    (
        re.compile(r"you\s+are\s+now\s+(in\s+)?(DAN|developer|maintenance|unrestricted)\s+mode", re.IGNORECASE),
        "jailbreak_persona",
    ),
    (
        re.compile(r"reveal\s+(your\s+)?(system\s+prompt|instructions|initial\s+prompt)", re.IGNORECASE),
        "prompt_exfiltration",
    ),
    (re.compile(r"tool_call\s*[:=]\s*\{", re.IGNORECASE), "tool_syntax_injection"),
    (re.compile(r"exec\s*\(\s*['\"]", re.IGNORECASE), "code_execution_injection"),
]


def scan_for_prompt_injections(text: str) -> list[dict[str, Any]]:
    """Scan untrusted document content for prompt injection patterns.

    Returns a list of detected threats with category and context snippets.
    """
    matches: list[dict[str, Any]] = []

    for pattern, category in INJECTION_PATTERNS:
        for match in pattern.finditer(text):
            start = max(0, match.start() - 20)
            end = min(len(text), match.end() + 20)
            snippet = text[start:end].replace("\n", " ")

            matches.append(
                {
                    "category": category,
                    "matched_text": match.group(0),
                    "snippet": f"...{snippet}...",
                }
            )

    return matches
