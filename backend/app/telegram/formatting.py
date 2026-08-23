"""Small, safe Telegram HTML presentation primitives."""

from __future__ import annotations

from html import escape, unescape
import re
from typing import Any

from telegram.constants import ParseMode
from telegram.error import BadRequest


TELEGRAM_PARSE_MODE = ParseMode.HTML

_HEADINGS = frozenset(
    {
        "Academic alert",
        "Academic concern",
        "Academic progress",
        "Academic recommendations",
        "Academic results",
        "Academic risk",
        "Availability",
        "Availability note",
        "Course result",
        "Data availability",
        "Key facts",
        "Overview",
        "Recommended actions (advisory)",
        "Required information",
        "Student overview",
        "Students needing attention",
        "Upcoming academic items",
        "Verified academic concern",
        "Verified evidence",
        "Verified facts",
        "Weekly tutor briefing",
        "Why this student needs attention",
    }
)
_STATUS_LABELS = frozenset({"Assessment", "Result", "Risk level", "Status"})
_PROMINENT_VALUE_LABELS = frozenset({"Student", "Tutor"})
_IDENTITY_HEADINGS = frozenset(
    {
        "Academic progress",
        "Academic recommendations",
        "Academic risk",
        "Course result",
        "Student overview",
        "Students needing attention",
    }
)
_SAFE_TAG_PATTERN = re.compile(r"</?(?:b|i|code)>", re.IGNORECASE)
_FORMATTING_ERROR_MARKERS = (
    "can't parse entities",
    "can't find end tag",
    "unsupported start tag",
    "unsupported end tag",
    "wrong entity",
)


def escape_telegram_html(value: Any) -> str:
    """Escape an untrusted value before placing it in Telegram HTML."""

    return escape(str(value), quote=True)


def bold_telegram_html(value: Any) -> str:
    """Bold an escaped, untrusted value."""

    return f"<b>{escape_telegram_html(value)}</b>"


def format_telegram_html(plain_text: str) -> str:
    """Escape a plain academic response and add restrained trusted markup."""

    formatted: list[str] = []
    previous_line = ""
    for line in plain_text.split("\n"):
        escaped = escape_telegram_html(line)
        if line in _HEADINGS:
            formatted.append(f"<b>{escaped}</b>")
            previous_line = line
            continue
        label, separator, value = line.partition(": ")
        if separator and label in _STATUS_LABELS | _PROMINENT_VALUE_LABELS:
            formatted.append(f"{escape_telegram_html(label)}: <b>{escape_telegram_html(value)}</b>")
            previous_line = line
            continue
        formatted.append(
            f"<b>{escaped}</b>" if previous_line in _IDENTITY_HEADINGS and line else escaped
        )
        previous_line = line
    return "\n".join(formatted)


def telegram_html_to_plain(html_text: str) -> str:
    """Remove only application-supported tags and decode escaped literals."""

    return unescape(_SAFE_TAG_PATTERN.sub("", html_text))


def is_telegram_formatting_error(exc: BaseException) -> bool:
    """Return true only for Telegram's explicit entity/markup rejections."""

    if not isinstance(exc, BadRequest):
        return False
    message = str(exc).lower()
    return any(marker in message for marker in _FORMATTING_ERROR_MARKERS)
