"""Regression: raw exception text must not reach an UNAUTHENTICATED caller.

Two JSON-RPC handlers returned ``str(e)`` straight into the error envelope:

* ``_handle_completion_complete`` — ``{"message": f"Completion failed: {str(e)}"}``
* ``run_stdio``'s ``tools/call`` branch — ``{"message": str(e)}``

``completion/complete`` is reachable with NO credentials (``_dispatch_ws_method``
routes it with only ``(params, request_id)``), and the stdio loop authenticates
nothing at the transport. So an anonymous caller received whatever the raised
exception happened to carry: absolute filesystem paths, module and class names,
database/driver text, and any credential embedded in a connection string quoted
back by a driver.

THE FIX — the caller gets a generic message plus a CORRELATION ID; the full
detail is logged server-side, credential-scrubbed via ``mask_error_text``. The
one exception is the server's OWN tool-availability refusals, which it raises as
``ToolNotAvailableError``: those messages are authored here, embed no foreign
text, and are the useful answer for a legitimate client.

FALSIFYING RESULT — if the leak were NOT closed, the assertions below would
observe ``/private/var/secret-root``, ``PGConnectionBroken``, and the
``s3cr3t-p4ssw0rd`` substring inside the message returned to the caller. Each
was the observed pre-fix behaviour.
"""

import asyncio
import io
import json
import re
import sys

import pytest
from kailash_mcp.server import MCPServer

pytestmark = pytest.mark.regression


# Distinctive tokens standing in for the three disclosure classes the raw
# ``str(e)`` shipped: an internal path, an internal type name, and a credential.
SECRET_PATH = "/private/var/secret-root/kailash_internal/dispatch.py"
SECRET_TYPE = "PGConnectionBroken"
SECRET_CRED = "s3cr3t-p4ssw0rd"
LEAKY_TEXT = (
    f"{SECRET_TYPE} at {SECRET_PATH}: "
    f"postgresql://svc:{SECRET_CRED}@10.1.2.3:5432/prod could not be reached"
)

CORRELATION_RE = re.compile(r"correlation id: ([0-9a-f]{8,})", re.IGNORECASE)


def _server_side_record(caplog, event: str):
    """The structured record for ``event``.

    Detail is carried in ``extra=`` FIELDS, not interpolated into the message
    (observability.md MUST-3), so ``caplog.text`` — which renders the message
    only — cannot see it. Read the record.
    """
    for record in caplog.records:
        if record.getMessage() == event:
            return record
    raise AssertionError(
        f"no server-side record for {event!r}; got "
        f"{[r.getMessage() for r in caplog.records]}"
    )


def _rendered(record) -> str:
    """Every field of the record an operator or shipper would see."""
    return (
        " ".join(
            str(getattr(record, field, ""))
            for field in ("correlation_id", "error", "error_type", "traceback")
        )
        + f" {record.getMessage()}"
    )


def _assert_no_detail_leaked(message: str) -> None:
    for token in (SECRET_PATH, SECRET_TYPE, SECRET_CRED, "postgresql://"):
        assert token not in message, (
            f"internal detail {token!r} was returned to an unauthenticated "
            f"caller: {message!r}"
        )


async def _drive_stdio(server: MCPServer, request: dict) -> dict:
    payload = json.dumps(request) + "\n"
    stdin, stdout = io.StringIO(payload), io.StringIO()
    real_stdin, real_stdout = sys.stdin, sys.stdout
    sys.stdin, sys.stdout = stdin, stdout
    try:
        await asyncio.wait_for(server.run_stdio(), timeout=10)
    finally:
        sys.stdin, sys.stdout = real_stdin, real_stdout
    return json.loads(stdout.getvalue().strip().splitlines()[0])


# ---------------------------------------------------------------------------
# completion/complete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_completion_error_does_not_leak_exception_text(monkeypatch):
    server = MCPServer("regression-error-leak")

    @server.tool()
    def probe(query: str) -> str:
        """Probe."""
        return "ok"

    def _boom(name, info):
        raise RuntimeError(LEAKY_TEXT)

    monkeypatch.setattr(server, "_public_tool_view", _boom)

    response = await server._handle_completion_complete(
        {"ref": {"type": "tool"}, "argument": {"value": ""}}, 1
    )

    message = response["error"]["message"]
    _assert_no_detail_leaked(message)
    assert CORRELATION_RE.search(message), (
        "the caller needs a correlation id to quote when reporting the "
        f"failure: {message!r}"
    )


@pytest.mark.asyncio
async def test_completion_error_logs_scrubbed_detail_server_side(monkeypatch, caplog):
    server = MCPServer("regression-error-leak-log")

    @server.tool()
    def probe(query: str) -> str:
        """Probe."""
        return "ok"

    monkeypatch.setattr(
        server,
        "_public_tool_view",
        lambda name, info: (_ for _ in ()).throw(RuntimeError(LEAKY_TEXT)),
    )

    with caplog.at_level("ERROR"):
        response = await server._handle_completion_complete(
            {"ref": {"type": "tool"}, "argument": {"value": ""}}, 1
        )

    correlation_id = CORRELATION_RE.search(response["error"]["message"]).group(1)
    record = _server_side_record(caplog, "completion.error")
    logged = _rendered(record)

    assert record.correlation_id == correlation_id, (
        "the server-side record must carry the SAME correlation id, or the id "
        f"the caller quotes cannot be traced: {logged!r}"
    )
    assert SECRET_PATH in logged, (
        "the operator loses all diagnostic value if the detail is dropped "
        f"rather than moved server-side: {logged!r}"
    )
    assert (
        SECRET_CRED not in logged
    ), f"credentials must be scrubbed even in the server-side record: {logged!r}"
    assert (
        SECRET_CRED not in caplog.text
    ), f"a credential reached the rendered log message: {caplog.text!r}"


# ---------------------------------------------------------------------------
# run_stdio tools/call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stdio_call_error_does_not_leak_exception_text():
    server = MCPServer("regression-error-leak-stdio")

    @server.tool()
    def explode(text: str) -> str:
        """Raise a detail-bearing exception."""
        raise RuntimeError(LEAKY_TEXT)

    response = await _drive_stdio(
        server,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "explode", "arguments": {"text": "hi"}},
        },
    )

    message = response["error"]["message"]
    _assert_no_detail_leaked(message)
    assert CORRELATION_RE.search(message), message


@pytest.mark.asyncio
async def test_stdio_call_error_logs_scrubbed_detail_server_side(caplog):
    server = MCPServer("regression-error-leak-stdio-log")

    @server.tool()
    def explode(text: str) -> str:
        """Raise a detail-bearing exception."""
        raise RuntimeError(LEAKY_TEXT)

    with caplog.at_level("ERROR"):
        response = await _drive_stdio(
            server,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "explode", "arguments": {"text": "hi"}},
            },
        )

    correlation_id = CORRELATION_RE.search(response["error"]["message"]).group(1)
    record = _server_side_record(caplog, "stdio.tools_call.error")
    logged = _rendered(record)

    assert record.correlation_id == correlation_id, logged
    assert SECRET_PATH in logged, logged
    assert (
        SECRET_CRED not in logged
    ), f"credentials must be scrubbed even in the server-side record: {logged!r}"
    # The wrapper ALSO logs "Error in tool <name>: <mcp_error>" through the
    # rendered message; that path is scrubbed too.
    assert (
        SECRET_CRED not in caplog.text
    ), f"a credential reached the rendered log message: {caplog.text!r}"


# ---------------------------------------------------------------------------
# CONTROL: the server's OWN availability refusals stay legible
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stdio_disabled_refusal_message_is_still_returned():
    """Server-authored refusals embed no foreign text and must survive."""
    server = MCPServer("regression-error-leak-control")

    @server.tool()
    def echo(text: str) -> str:
        """Echo."""
        return text

    server.disable_tool("echo")

    response = await _drive_stdio(
        server,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "echo", "arguments": {"text": "hi"}},
        },
    )

    assert "disabled" in response["error"]["message"].lower(), response
