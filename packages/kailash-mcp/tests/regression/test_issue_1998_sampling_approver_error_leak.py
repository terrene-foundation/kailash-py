"""Regression: the sampling HITL gate returned approver exception text to an
UNAUTHENTICATED caller.

``sampling/createMessage`` is dispatched by ``_dispatch_ws_method``, which
authenticates nothing — the same unauthenticated surface every other handler
answers. Every other handler on that dispatch table routes its exception arms
through ``_internal_error_envelope``; ``_evaluate_sampling_approval`` was the
only one that did not. It returned ``f"sampling approval failed: {exc}"``, where
``exc`` is whatever an arbitrary application-supplied approver callback raised.

Both exception arms leaked, for different reasons:

  * the generic arm interpolated the exception directly; and
  * the ``MCPError`` arm returned ``exc.message``, which LOOKS server-authored
    and is not: the enhanced tool wrapper builds
    ``ToolError(f"Tool execution failed: {e}")``, embedding foreign text inside
    an ``MCPError``. "It is an ``MCPError``" is not sufficient to call a message
    caller-safe — which is why the stdio branch matches a dedicated
    ``ToolNotAvailableError`` type instead.

Secondary, same block: the generic arm logged ``extra={"error": str(exc)}`` with
no ``mask_error_text``, so the credential was also unscrubbed in the record —
invisible to a stdlib formatter but rendered by exactly the structured sinks
this project's logging is written for. Scrubbing the caller path alone would
have relocated the leak rather than closed it.

SEVERITY — this requires an approver to be BOUND, which is the DOCUMENTED
PRODUCTION POSTURE (the unbound default fails closed with a fixed string). It is
therefore a defect that appears only in the configuration real deployments run,
which is the inverse of the usual "only when configured" discount.

FALSIFYING RESULTS, each observed against the pre-fix code by driving the real
handler:
  * generic arm -> caller received ``sampling approval failed: connect failed:
    postgresql://svc:hunter2@db.internal:5432/app at /Users/…/approve.py``;
  * MCPError arm -> caller received ``Tool execution failed: connect failed:
    postgresql://svc:hunter2@db.internal:5432/app …``;
  * the log record's ``error`` field carried the credential unscrubbed;
  * and the CONTROLS below (unbound / declined / timeout) leaked nothing, which
    is what makes the three above attributable to the approver path rather than
    to the handler generally.
"""

import asyncio
import re

import pytest
from kailash_mcp.errors import MCPError, MCPErrorCode, ToolError
from kailash_mcp.server import MCPServer

pytestmark = pytest.mark.regression


CREDENTIAL = "hunter2"
INTERNAL_PATH = "/Users/svc-account/kailash_internal/approve.py"
LEAKY_TEXT = (
    f"connect failed: postgresql://svc:{CREDENTIAL}@db.internal:5432/app "
    f"at {INTERNAL_PATH}"
)
LEAK_TOKENS = (CREDENTIAL, INTERNAL_PATH, "postgresql://", "db.internal")

SAMPLING_PARAMS = {
    "messages": [{"role": "user", "content": {"type": "text", "text": "hi"}}],
    "client_id": "c1",
}


def _server() -> MCPServer:
    """A server whose requesting client advertises sampling.

    Without this the handler refuses at the CAPABILITY check and never reaches
    the approval gate — a probe that omits it returns "No connected clients
    support sampling" and reports no leak whether or not one exists.
    """
    server = MCPServer("regression-sampling-approval")
    server.client_info["c1"] = {"capabilities": {"sampling": {}}}
    return server


async def _drive(server: MCPServer) -> dict:
    return await server._handle_sampling_create_message(SAMPLING_PARAMS, 1)


def _assert_no_leak(response: dict, label: str) -> None:
    rendered = str(response)
    for token in LEAK_TOKENS:
        assert token not in rendered, (
            f"{label}: approver-derived detail {token!r} was returned to an "
            f"unauthenticated caller: {rendered!r}"
        )


def _correlation_id(response: dict) -> str:
    message = response["error"]["message"]
    match = re.search(r"correlation id: ([0-9a-f]{8,})", message)
    assert match, (
        "the refusal carries no correlation id, so the detail was DROPPED "
        f"rather than moved server-side: {message!r}"
    )
    assert response["error"]["data"]["correlationId"] == match.group(1)
    return match.group(1)


# ---------------------------------------------------------------------------
# The two exception arms
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generic_approver_exception_is_not_returned_to_the_caller():
    server = _server()
    server.set_sampling_approver(
        lambda context: (_ for _ in ()).throw(RuntimeError(LEAKY_TEXT))
    )

    response = await _drive(server)

    _assert_no_leak(response, "generic arm")
    _correlation_id(response)
    assert response["error"]["code"] == MCPErrorCode.MCP_SAMPLING_REJECTED.value


@pytest.mark.asyncio
async def test_mcperror_approver_message_is_not_returned_to_the_caller():
    """An ``MCPError``'s MESSAGE is not necessarily server-authored.

    ``ToolError`` is the shape that matters: the enhanced tool wrapper builds
    ``ToolError(f"Tool execution failed: {e}")``, so foreign text arrives inside
    a type that looks like the server's own.
    """
    server = _server()

    def approver(context):
        raise ToolError(f"Tool execution failed: {LEAKY_TEXT}")

    server.set_sampling_approver(approver)
    response = await _drive(server)

    _assert_no_leak(response, "MCPError arm")
    _correlation_id(response)


@pytest.mark.asyncio
async def test_mcperror_arm_preserves_the_approvers_chosen_code():
    """The CODE is server-authored (an enum member) and must survive.

    It is how an approver signals WHICH refusal this is. A fix that collapsed
    every raise to one code would pass the leak tests above while destroying
    the documented contract, so this pins the distinction the fix rests on:
    code preserved, message replaced.
    """
    server = _server()

    def approver(context):
        raise MCPError(
            f"denied: {LEAKY_TEXT}",
            error_code=MCPErrorCode.MCP_SAMPLING_DECLINED,
        )

    server.set_sampling_approver(approver)
    response = await _drive(server)

    assert response["error"]["code"] == MCPErrorCode.MCP_SAMPLING_DECLINED.value, (
        "the approver's chosen error code was discarded; the caller can no "
        "longer tell a decline from a crash"
    )
    _assert_no_leak(response, "MCPError code preservation")


@pytest.mark.asyncio
async def test_approver_exception_is_scrubbed_in_the_server_side_record(caplog):
    """Scrubbing the caller path alone would relocate the leak, not close it.

    The pre-fix arm logged ``extra={"error": str(exc)}`` with no
    ``mask_error_text``. A stdlib formatter does not render extras, so this is
    invisible in ``caplog.text`` — it has to be read off the record, which is
    what a structured sink ships.
    """
    server = _server()
    server.set_sampling_approver(
        lambda context: (_ for _ in ()).throw(RuntimeError(LEAKY_TEXT))
    )

    with caplog.at_level("ERROR"):
        response = await _drive(server)
    correlation_id = _correlation_id(response)

    fields = " ".join(
        str(getattr(record, name, ""))
        for record in caplog.records
        for name in ("error", "traceback", "reason", "message")
    )
    assert (
        CREDENTIAL not in fields
    ), f"the credential is unscrubbed in the server-side record: {fields!r}"
    assert INTERNAL_PATH in fields, (
        "the operator loses all diagnostic value if the detail is dropped "
        f"rather than moved server-side: {fields!r}"
    )
    assert correlation_id in caplog.text, (
        "the id the caller was handed must appear in the RENDERED log, or the "
        f"refusal is undiagnosable: {caplog.text!r}"
    )


# ---------------------------------------------------------------------------
# CONTROLS — the server-authored refusals stay verbatim and actionable
#
# Without these, every test above would pass for a fix that replaced EVERY
# refusal with an opaque correlation id, destroying the messages that tell an
# operator what to do.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unbound_approver_still_fails_closed_with_actionable_text():
    response = await _drive(_server())

    assert response["error"]["code"] == MCPErrorCode.MCP_SAMPLING_REJECTED.value
    message = response["error"]["message"]
    assert "no approver is bound" in message and "set_sampling_approver" in message, (
        "the fail-closed refusal must keep naming its remedy; it is "
        f"server-authored and carries nothing exception-derived: {message!r}"
    )
    assert "correlation id" not in message


@pytest.mark.asyncio
async def test_declined_and_timeout_keep_their_distinct_server_authored_text():
    declining = _server()
    declining.set_sampling_approver(lambda context: False)
    declined = await _drive(declining)
    assert declined["error"]["code"] == MCPErrorCode.MCP_SAMPLING_DECLINED.value
    assert "declined by human reviewer" in declined["error"]["message"]

    timing_out = _server()
    timing_out.set_sampling_approver(
        lambda context: (_ for _ in ()).throw(asyncio.TimeoutError())
    )
    timed_out = await _drive(timing_out)
    assert timed_out["error"]["code"] == MCPErrorCode.MCP_SAMPLING_TIMEOUT.value
    assert "timed out" in timed_out["error"]["message"]


@pytest.mark.asyncio
async def test_approval_still_proceeds_past_the_gate():
    """CONTROL: the gate still APPROVES, so the tests above are not passing
    merely because everything is refused."""
    server = _server()
    server.set_sampling_approver(lambda context: True)

    response = await _drive(server)

    assert "approval" not in response.get("error", {}).get("message", ""), (
        "a truthy approver must let the request through to dispatch: " f"{response!r}"
    )


def test_the_capability_precondition_is_required_to_reach_the_gate():
    """Pin the precondition the probe above needs, because omitting it makes
    every leak test silently vacuous.

    A server whose requester does NOT advertise sampling refuses at the
    capability check and never runs the approver at all — so a leak probe
    written without ``client_info`` reports "no leak" whether or not the leak
    exists. That is exactly what a first pass at this test did.
    """
    server = MCPServer("regression-sampling-precondition")  # no client_info
    called = []
    server.set_sampling_approver(lambda context: called.append(1) or True)

    response = asyncio.run(server._handle_sampling_create_message(SAMPLING_PARAMS, 1))

    assert called == [], "the approver ran despite the capability check refusing"
    assert "support sampling" in response["error"]["message"]
