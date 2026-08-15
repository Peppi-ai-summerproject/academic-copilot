from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from unittest.mock import Mock

import pytest

from app.agents.intent_detection import detect_intent
from app.agents.registry import AgentRegistry
from app.agents.state import AgentState
from app.agents.types import WorkflowStatus
from app.schemas.chat import ChatRequest
from app.services.chat_service import ChatService
from app.services.session_service import SessionService
from app.telegram import commands
from app.telegram import bot as bot_module
from app.telegram.backend_client import BackendClientError


HANDLERS = {
    "student": commands.student_command,
    "progress": commands.progress_command,
    "risk": commands.risk_command,
    "events": commands.events_command,
}


def telegram_update(command: str):
    message = SimpleNamespace(
        text=f"/{command}",
        reply_text=AsyncMock(),
        reply_chat_action=AsyncMock(),
    )
    return SimpleNamespace(
        message=message,
        effective_message=message,
        effective_user=SimpleNamespace(id=101, username="tutor"),
        effective_chat=SimpleNamespace(id=202),
    )


def run_command(command: str, args: list[str], monkeypatch, *, error=False):
    update = telegram_update(command)
    client = SimpleNamespace(send_message=AsyncMock(return_value="Authoritative academic reply"))
    if error:
        client.send_message.side_effect = BackendClientError("private details")
    monkeypatch.setattr(commands, "backend_client", client)
    asyncio.run(HANDLERS[command](update, SimpleNamespace(args=args)))
    return update, client


@pytest.mark.parametrize(
    ("command", "expected_intent"),
    [
        ("student", "reporting"),
        ("progress", "progress"),
        ("risk", "risk"),
        ("events", "calendar"),
    ],
)
def test_valid_academic_command_sends_structured_student_request_and_reply(
    command: str,
    expected_intent: str,
    monkeypatch,
) -> None:
    update, client = run_command(command, ["123"], monkeypatch)

    request = client.send_message.call_args.kwargs
    assert request["student_id"] == 123
    assert request["telegram_user_id"] == 101
    assert request["telegram_chat_id"] == 202
    assert request["username"] == "tutor"
    assert detect_intent(request["message"]).intent == expected_intent
    update.effective_message.reply_text.assert_awaited_once_with(
        "Authoritative academic reply"
    )


@pytest.mark.parametrize("command", HANDLERS)
@pytest.mark.parametrize(
    "args",
    [[], ["abc"], ["-5"], ["0"], ["12.5"], ["123", "extra"]],
)
def test_missing_or_invalid_student_id_never_contacts_backend(
    command: str,
    args: list[str],
    monkeypatch,
) -> None:
    update, client = run_command(command, args, monkeypatch)

    client.send_message.assert_not_awaited()
    response = update.effective_message.reply_text.await_args.args[0]
    assert "student ID" in response
    assert f"/{command} 123" in response


@pytest.mark.parametrize("command", HANDLERS)
def test_backend_failure_returns_safe_response(command: str, monkeypatch) -> None:
    update, client = run_command(command, ["123"], monkeypatch, error=True)

    client.send_message.assert_awaited_once()
    response = update.effective_message.reply_text.await_args.args[0]
    assert "could not connect" in response
    assert "private details" not in response


def test_academic_commands_use_existing_logging_paths(monkeypatch) -> None:
    incoming = Mock()
    outgoing = Mock()
    monkeypatch.setattr(commands, "log_incoming_message", incoming)
    monkeypatch.setattr(commands, "log_outgoing_message", outgoing)

    run_command("risk", ["123"], monkeypatch)

    incoming.assert_called_once_with(
        user_id=101,
        chat_id=202,
        username="tutor",
        message_text="/risk",
    )
    outgoing.assert_called_once_with(
        user_id=101,
        chat_id=202,
        reply_text="Authoritative academic reply",
    )


def test_four_academic_commands_are_registered_to_real_handlers(monkeypatch) -> None:
    monkeypatch.setattr(bot_module.settings, "telegram_bot_token", "123456:TEST_TOKEN")

    application = bot_module.create_bot()
    registered = {
        command: handler.callback
        for handlers in application.handlers.values()
        for handler in handlers
        if hasattr(handler, "commands")
        for command in handler.commands
    }

    assert registered["student"] is commands.student_command
    assert registered["progress"] is commands.progress_command
    assert registered["risk"] is commands.risk_command
    assert registered["events"] is commands.events_command
    assert "placeholder_command" not in {
        callback.__name__ for callback in registered.values()
    }


def test_existing_start_help_status_and_unknown_commands_remain_functional() -> None:
    update = telegram_update("help")
    context = SimpleNamespace(args=[])

    for handler in (
        commands.start_command,
        commands.help_command,
        commands.status_command,
        commands.unknown_command,
    ):
        asyncio.run(handler(update, context))

    replies = [call.args[0] for call in update.message.reply_text.await_args_list]
    assert "Welcome" in replies[0]
    assert "/student <student_id>" in replies[1]
    assert "is running" in replies[2]
    assert "Unknown command" in replies[3]


def test_progress_command_uses_same_chat_service_routing_as_normal_request(
    monkeypatch,
) -> None:
    class RecordingWorkflow:
        def __init__(self) -> None:
            self.states: list[AgentState] = []

        async def run(self, state: AgentState) -> AgentState:
            self.states.append(state.model_copy(deep=True))
            state.workflow_status = WorkflowStatus.COMPLETED
            state.final_response = "Real progress workflow response"
            return state

    workflow = RecordingWorkflow()
    registry = AgentRegistry()
    registry.register("progress", object)  # type: ignore[arg-type]
    chat_service = ChatService(
        session_service=SessionService(),
        workflow=workflow,
        registry=registry,
    )

    class InProcessBackendClient:
        async def send_message(self, **kwargs) -> str:
            response = await chat_service.process_message(ChatRequest(**kwargs))
            return response.reply

    monkeypatch.setattr(commands, "backend_client", InProcessBackendClient())
    update = telegram_update("progress")

    asyncio.run(commands.progress_command(update, SimpleNamespace(args=["123"])))

    assert workflow.states[0].intent == "progress"
    assert workflow.states[0].student_id == 123
    assert workflow.states[0].selected_agents == ["progress"]
    update.message.reply_text.assert_awaited_once_with(
        "Real progress workflow response"
    )
