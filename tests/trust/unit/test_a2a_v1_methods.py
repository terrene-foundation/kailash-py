# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
A2A 1.0 JSON-RPC method-set conformance tests (#2203 Wave 1 Shard B).

These pin the wire contract measured from the A2A specification at tag
``v1.0.1`` (``specification/a2a.proto`` + ``docs/specification.md``), not from
the issue text or the wave plan — both of which named the 0.2.x/0.3.x
slash-notation methods as though they were 1.0's.

The three conventions under test, and the spec clause fixing each:

- **PascalCase JSON-RPC method names** — § "Protocol Requirements": *"Method
  Naming: PascalCase method names matching gRPC conventions (e.g.,
  ``SendMessage``, ``GetTask``)"*. § "Method Mapping Reference" puts
  ``/message:send`` in the REST column, NOT the JSON-RPC column.
- **camelCase JSON field names** — § "JSON Serialization": *"All JSON
  serializations of the A2A protocol data model MUST use camelCase naming for
  field names, not the snake_case convention used in Protocol Buffer
  definitions."*
- **SCREAMING_SNAKE_CASE enum values** — ProtoJSON enum encoding.

``test_slash_notation_methods_are_not_registered`` is the regression that
matters most: it fails if someone "fixes" this shard back toward the plan's
original wording.
"""

from __future__ import annotations

import uuid

import pytest

from kailash.trust.a2a.exceptions import AuthenticationError, TaskNotFoundError
from kailash.trust.a2a.jsonrpc import A2AMethodHandlers, JsonRpcHandler
from kailash.trust.a2a.messaging import Message, Part, Role, Task, TaskState, TaskStatus
from kailash.trust.a2a.task_store import InMemoryTaskStore

AUTH = "test-bearer-token"


class _TrustOpsStub:
    """Stands in for TrustOperations.

    SendMessage/GetTask never touch trust operations — that is the point of
    the stub, and if a future change makes them touch it, these tests fail
    loudly with AttributeError rather than passing against a permissive mock.
    """


def _handlers(**kwargs) -> A2AMethodHandlers:
    return A2AMethodHandlers(
        trust_operations=_TrustOpsStub(),  # type: ignore[arg-type]
        agent_id="agent-under-test",
        capabilities=["analyze"],
        **kwargs,
    )


def _text_message(text: str = "hello", **kwargs) -> Message:
    return Message(
        message_id=str(uuid.uuid4()),
        role=Role.USER,
        parts=[Part(text=text)],
        **kwargs,
    )


# --------------------------------------------------------------------------
# Method-name registration
# --------------------------------------------------------------------------


def test_v1_pascalcase_methods_are_registered():
    handler = JsonRpcHandler()
    _handlers().register_all(handler)

    registered = set(handler.get_registered_methods())
    assert "SendMessage" in registered
    assert "GetTask" in registered


def test_slash_notation_methods_are_not_registered():
    """0.2.x/0.3.x spellings MUST NOT be registered as 1.0 methods.

    Guards the exact defect this shard was filed against: the plan named
    ``message/send`` / ``tasks/get`` as "the 1.0 method set". They are the
    superseded names; registering them would advertise 1.0 conformance the
    TCK would then fail.
    """
    handler = JsonRpcHandler()
    _handlers().register_all(handler)

    registered = set(handler.get_registered_methods())
    for legacy in ("message/send", "tasks/get", "message/stream", "tasks/cancel"):
        assert legacy not in registered, (
            f"{legacy!r} is a 0.2.x/0.3.x JSON-RPC method name, not A2A 1.0's. "
            "A2A 1.0 § Protocol Requirements mandates PascalCase."
        )


def test_trust_extension_methods_survive_alongside_v1_methods():
    """The Kailash trust methods are a separate namespace, not casualties."""
    handler = JsonRpcHandler()
    _handlers().register_all(handler)

    registered = set(handler.get_registered_methods())
    for trust_method in (
        "agent.capabilities",
        "agent.invoke",
        "trust.verify",
        "trust.delegate",
        "audit.query",
    ):
        assert trust_method in registered


# --------------------------------------------------------------------------
# SendMessage
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_message_creates_task_in_submitted_state():
    handlers = _handlers()
    result = await handlers.handle_send_message(
        {"message": _text_message().to_dict()}, AUTH
    )

    assert "task" in result, "SendMessageResponse oneof must carry the task arm"
    task = result["task"]
    assert task["status"]["state"] == "TASK_STATE_SUBMITTED"
    assert task["id"]


@pytest.mark.asyncio
async def test_send_message_response_uses_camelcase_field_names():
    """Spec MUST: camelCase on the wire, never proto snake_case."""
    handlers = _handlers()
    message = _text_message(context_id="ctx-1")
    result = await handlers.handle_send_message({"message": message.to_dict()}, AUTH)

    task = result["task"]
    assert "contextId" in task
    assert "context_id" not in task

    history_entry = task["history"][0]
    assert "messageId" in history_entry
    assert "message_id" not in history_entry


@pytest.mark.asyncio
async def test_send_message_requires_authentication():
    handlers = _handlers()
    with pytest.raises(AuthenticationError):
        await handlers.handle_send_message({"message": _text_message().to_dict()}, None)


@pytest.mark.asyncio
async def test_send_message_runs_the_configured_message_handler():
    async def executor(message: Message, task: Task) -> Task:
        task.status = TaskStatus(state=TaskState.COMPLETED)
        return task

    handlers = _handlers(message_handler=executor)
    result = await handlers.handle_send_message(
        {"message": _text_message().to_dict()}, AUTH
    )

    assert result["task"]["status"]["state"] == "TASK_STATE_COMPLETED"


@pytest.mark.asyncio
async def test_send_message_handler_failure_marks_task_failed_not_500():
    """A failing executor is a task outcome, not a transport-level crash."""

    async def exploding(message: Message, task: Task) -> Task:
        raise RuntimeError("executor blew up")

    handlers = _handlers(message_handler=exploding)
    result = await handlers.handle_send_message(
        {"message": _text_message().to_dict()}, AUTH
    )

    assert result["task"]["status"]["state"] == "TASK_STATE_FAILED"


@pytest.mark.asyncio
async def test_send_message_rejects_malformed_params():
    from kailash.trust.a2a.exceptions import JsonRpcInvalidParamsError

    handlers = _handlers()
    with pytest.raises(JsonRpcInvalidParamsError):
        await handlers.handle_send_message({}, AUTH)


@pytest.mark.asyncio
async def test_send_message_appends_to_an_existing_task():
    store = InMemoryTaskStore()
    handlers = _handlers(task_store=store)

    first = await handlers.handle_send_message(
        {"message": _text_message("one").to_dict()}, AUTH
    )
    task_id = first["task"]["id"]

    second = await handlers.handle_send_message(
        {"message": _text_message("two", task_id=task_id).to_dict()}, AUTH
    )

    assert second["task"]["id"] == task_id
    assert len(second["task"]["history"]) == 2


@pytest.mark.asyncio
async def test_send_message_to_terminal_task_is_rejected():
    from kailash.trust.a2a.exceptions import JsonRpcInvalidParamsError

    store = InMemoryTaskStore()
    store.put(Task(id="done-task", status=TaskStatus(state=TaskState.COMPLETED)))
    handlers = _handlers(task_store=store)

    with pytest.raises(JsonRpcInvalidParamsError):
        await handlers.handle_send_message(
            {"message": _text_message(task_id="done-task").to_dict()}, AUTH
        )


# --------------------------------------------------------------------------
# GetTask
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_task_returns_a_previously_sent_task():
    store = InMemoryTaskStore()
    handlers = _handlers(task_store=store)

    sent = await handlers.handle_send_message(
        {"message": _text_message().to_dict()}, AUTH
    )
    task_id = sent["task"]["id"]

    fetched = await handlers.handle_get_task({"id": task_id}, AUTH)
    assert fetched["id"] == task_id
    assert fetched["status"]["state"] == "TASK_STATE_SUBMITTED"


@pytest.mark.asyncio
async def test_get_task_unknown_id_raises_dash_32001():
    """Spec § Error Code Mappings pins TaskNotFoundError to -32001.

    A generic invalid-params (-32602) would be indistinguishable to a
    conformant client from a malformed request.
    """
    handlers = _handlers()
    with pytest.raises(TaskNotFoundError) as excinfo:
        await handlers.handle_get_task({"id": "no-such-task"}, AUTH)

    assert excinfo.value.code == -32001


@pytest.mark.asyncio
async def test_get_task_requires_authentication():
    handlers = _handlers()
    with pytest.raises(AuthenticationError):
        await handlers.handle_get_task({"id": "any"}, None)


@pytest.mark.asyncio
async def test_get_task_history_length_trims_to_most_recent():
    store = InMemoryTaskStore()
    handlers = _handlers(task_store=store)

    sent = await handlers.handle_send_message(
        {"message": _text_message("one").to_dict()}, AUTH
    )
    task_id = sent["task"]["id"]
    for text in ("two", "three"):
        await handlers.handle_send_message(
            {"message": _text_message(text, task_id=task_id).to_dict()}, AUTH
        )

    trimmed = await handlers.handle_get_task({"id": task_id, "historyLength": 2}, AUTH)
    assert len(trimmed["history"]) == 2
    assert trimmed["history"][-1]["parts"][0]["text"] == "three"

    none_kept = await handlers.handle_get_task(
        {"id": task_id, "historyLength": 0}, AUTH
    )
    assert "history" not in none_kept


@pytest.mark.asyncio
async def test_get_task_negative_history_length_is_rejected():
    from kailash.trust.a2a.exceptions import JsonRpcInvalidParamsError

    store = InMemoryTaskStore()
    handlers = _handlers(task_store=store)
    sent = await handlers.handle_send_message(
        {"message": _text_message().to_dict()}, AUTH
    )

    with pytest.raises(JsonRpcInvalidParamsError):
        await handlers.handle_get_task(
            {"id": sent["task"]["id"], "historyLength": -1}, AUTH
        )


# --------------------------------------------------------------------------
# End-to-end through the JSON-RPC envelope
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_then_get_over_the_jsonrpc_envelope():
    """Drive the real dispatch path, not just the handler methods."""
    rpc = JsonRpcHandler()
    _handlers(task_store=InMemoryTaskStore()).register_all(rpc)

    send = await rpc.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "SendMessage",
            "params": {"message": _text_message().to_dict()},
        },
        AUTH,
    )
    assert send.error is None, f"SendMessage errored: {send.error}"
    assert send.result is not None
    task_id = send.result["task"]["id"]

    get = await rpc.handle(
        {"jsonrpc": "2.0", "id": 2, "method": "GetTask", "params": {"id": task_id}},
        AUTH,
    )
    assert get.error is None, f"GetTask errored: {get.error}"
    assert get.result is not None
    assert get.result["id"] == task_id


@pytest.mark.asyncio
async def test_legacy_slash_method_returns_method_not_found_over_the_envelope():
    rpc = JsonRpcHandler()
    _handlers().register_all(rpc)

    response = await rpc.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "message/send",
            "params": {"message": _text_message().to_dict()},
        },
        AUTH,
    )
    assert response.error is not None
    assert response.error["code"] == -32601


@pytest.mark.asyncio
async def test_get_task_not_found_surfaces_dash_32001_over_the_envelope():
    """The -32001 code must survive the envelope, not be flattened to -32603."""
    rpc = JsonRpcHandler()
    _handlers().register_all(rpc)

    response = await rpc.handle(
        {"jsonrpc": "2.0", "id": 1, "method": "GetTask", "params": {"id": "nope"}},
        AUTH,
    )
    assert response.error is not None
    assert response.error["code"] == -32001
