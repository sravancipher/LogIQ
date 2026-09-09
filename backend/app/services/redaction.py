from __future__ import annotations

import re
from typing import Any

# Applied to any log content (message text) before it is embedded in a prompt sent to
# an LLM by the chat assistant. Order matters: more specific patterns (JWT, AWS key)
# run before the generic key=value ones so they aren't half-masked by a broader match.
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bBearer\s+[A-Za-z0-9\-_.=]+", re.IGNORECASE), "Bearer [REDACTED]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"), "[REDACTED_JWT]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED_AWS_KEY]"),
    (re.compile(r"\bsk-[A-Za-z0-9]{16,}\b"), "[REDACTED_KEY]"),
    (
        re.compile(r"(?i)\b(api[_-]?key|apikey|authorization|password|passwd|pwd|secret|token)\b\s*[:=]\s*[\"']?\S{3,}[\"']?"),
        r"\1=[REDACTED]",
    ),
]


def redact_text(text: str) -> str:
    if not text:
        return text
    redacted = text
    for pattern, replacement in _PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def redact_value(value: Any) -> Any:
    """Recursively redact strings inside a plain str/dict/list structure. Other types
    (numbers, bools, None) pass through unchanged."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {k: redact_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_value(v) for v in value]
    return value
