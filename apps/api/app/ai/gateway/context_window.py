from app.ai.gateway.types import LLMMessage


def estimate_tokens(text: str) -> int:
    """Conservative multilingual token estimator.

    Accounts for Malayalam and Indic script token explosion:
    - Standard Latin / English text: ~4 chars per token.
    - Malayalam (U+0D00 - U+0D7F) & Devanagari (U+0900 - U+097F): ~1 char per token.
    """
    if not text:
        return 0

    indic_chars = 0
    other_chars = 0

    for ch in text:
        code = ord(ch)
        # Check Malayalam (0x0D00-0x0D7F) or Devanagari (0x0900-0x097F)
        if (0x0D00 <= code <= 0x0D7F) or (0x0900 <= code <= 0x097F):
            indic_chars += 1
        else:
            other_chars += 1

    # Conservative estimation
    return indic_chars + (other_chars // 4) + 1


def prune_conversation_window(
    messages: list[LLMMessage],
    max_history_turns: int = 6,
    max_tokens: int = 2000,
) -> list[LLMMessage]:
    """Prune conversation history window.

    Rules:
    - Retains all system instructions (role == 'system').
    - Keeps at most the latest `max_history_turns` non-system messages.
    - Ensures conversation tokens stay within `max_tokens`.
    - Never mutates financial numbers or mixes messages across turns.
    """
    system_messages = [m for m in messages if m.role == "system"]
    conversation_messages = [m for m in messages if m.role != "system"]

    # Step 1: Keep at most last N turns
    recent_messages = conversation_messages[-max_history_turns:]

    # Step 2: Ensure budget under max_tokens by pruning from the oldest of recent
    result_conversation: list[LLMMessage] = []
    accumulated_tokens = sum(estimate_tokens(m.content) for m in system_messages)

    for msg in reversed(recent_messages):
        msg_tokens = estimate_tokens(msg.content)
        if accumulated_tokens + msg_tokens <= max_tokens:
            result_conversation.insert(0, msg)
            accumulated_tokens += msg_tokens
        else:
            break

    return system_messages + result_conversation
