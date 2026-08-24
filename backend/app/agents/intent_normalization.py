"""Conservative lexical normalization for academic intent words only."""

from __future__ import annotations

import re


INTENT_KEYWORDS = frozenset({
    "academic", "failed", "passed", "progress", "progressing",
    "recommend", "recommendation", "recommendations", "overview",
})


def normalize_intent_text(text: str) -> str:
    """Correct clear intent-keyword typos without exposing corrected entities."""
    return re.sub(
        r"[^\W\d_]+",
        lambda match: canonical_intent_keyword(match.group(0)) or match.group(0),
        text.casefold(),
    )


def canonical_intent_keyword(
    token: str, allowed: frozenset[str] = INTENT_KEYWORDS
) -> str | None:
    value = token.casefold()
    if value in allowed:
        return value
    if len(value) < 5 or not value.isalpha():
        return None
    limit = 2 if len(value) >= 9 else 1
    ranked = sorted((_edit_distance(value, candidate), candidate) for candidate in allowed)
    if not ranked or ranked[0][0] > limit:
        return None
    if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
        return None
    return ranked[0][1]


def _edit_distance(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, 1):
        current = [left_index]
        for right_index, right_char in enumerate(right, 1):
            current.append(min(
                current[-1] + 1,
                previous[right_index] + 1,
                previous[right_index - 1] + (left_char != right_char),
            ))
        previous = current
    return previous[-1]
