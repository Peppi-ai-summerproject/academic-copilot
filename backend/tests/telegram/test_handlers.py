from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram.error import BadRequest, Forbidden

from app.telegram import handlers


def _update(reply_text: AsyncMock):
    message = SimpleNamespace(
        text="Show student",
        reply_chat_action=AsyncMock(),
        reply_text=reply_text,
    )
    return SimpleNamespace(
        effective_message=message,
        effective_user=SimpleNamespace(id=101, username="tutor"),
        effective_chat=SimpleNamespace(id=202),
    )


def test_interactive_reply_escapes_dynamic_html_and_sets_html_mode(monkeypatch):
    backend = SimpleNamespace(
        send_message=AsyncMock(
            return_value=(
                "Student overview\nAlice <b>Admin</b>\n"
                "Course: Databases & APIs\nStatus: FAILED\nGrade: 0"
            )
        )
    )
    reply_text = AsyncMock()
    monkeypatch.setattr(handlers, "backend_client", backend)

    asyncio.run(handlers.handle_message(_update(reply_text), None))

    sent, = reply_text.await_args_list
    assert sent.kwargs["parse_mode"] == "HTML"
    assert sent.args[0].startswith("<b>Student overview</b>")
    assert "Alice &lt;b&gt;Admin&lt;/b&gt;" in sent.args[0]
    assert "Databases &amp; APIs" in sent.args[0]
    assert "Status: <b>FAILED</b>" in sent.args[0]
    assert "Grade: <b>0</b>" in sent.args[0]


def test_interactive_formatting_rejection_retries_once_as_plain_text(monkeypatch):
    plain = "Academic risk\nAlice <b>Admin</b> & O'Neil"
    backend = SimpleNamespace(send_message=AsyncMock(return_value=plain))
    reply_text = AsyncMock(side_effect=[BadRequest("Can't parse entities"), None])
    monkeypatch.setattr(handlers, "backend_client", backend)

    asyncio.run(handlers.handle_message(_update(reply_text), None))

    assert reply_text.await_count == 2
    assert reply_text.await_args_list[1].args == (plain,)
    assert reply_text.await_args_list[1].kwargs == {}


def test_interactive_non_formatting_failure_is_not_retried(monkeypatch):
    backend = SimpleNamespace(send_message=AsyncMock(return_value="Academic risk"))
    reply_text = AsyncMock(side_effect=Forbidden("blocked"))
    monkeypatch.setattr(handlers, "backend_client", backend)

    with pytest.raises(Forbidden):
        asyncio.run(handlers.handle_message(_update(reply_text), None))

    assert reply_text.await_count == 1
