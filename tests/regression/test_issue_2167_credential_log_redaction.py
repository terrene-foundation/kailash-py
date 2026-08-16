"""Regression tests for issue #2167 — credentials reaching clear-text log sinks.

Two defects, five CodeQL HIGH alerts:

* **A** — ``AuditLogNode.execute`` passed the caller's ``event_data`` bag through
  ``sanitize_log_structure``, which is explicitly NOT a redaction step, so a
  credential up to 256 characters reached the log byte-intact
  (alerts 11503/11504/11505 — one bug, three sinks sharing one value).
* **B** — ``HTTPRequestNode`` / ``AsyncHTTPRequestNode`` logged the request URL
  unmasked, plus the assembled ``Authorization`` header and the request body
  (alerts 11506/11507, and the byte-identical sync sibling CodeQL never flagged).

**These assert on the EMITTED STREAM, not on ``LogRecord`` objects.** A leaked
credential is produced at *format* time: ``logger.info(f"...{secret}...")``
renders before the record exists, so a test that inspects ``record.args`` or
counts records cannot tell a redacted call from an unredacted one. Attaching a
real ``StreamHandler`` with a real ``Formatter`` and searching the resulting text
is the only instrument here that discriminates.

No ``Mock`` for the nodes or the redaction helpers: a mock accepts every call
and passes identically whether the fix is present or absent.
"""

import base64
import logging
from io import StringIO

import pytest

# The literal secrets these tests hunt for in the emitted log text. Distinctive
# enough that a substring search cannot match incidentally.
_SECRET = "s3cr3t-issue-2167-must-not-appear"
_PASSWORD = "pw-issue-2167-must-not-appear"
_TOKEN = "tok-issue-2167-must-not-appear"


class _Capture:
    """Attach a real handler+formatter to a logger and collect emitted TEXT."""

    def __init__(self, logger_name: str):
        self._logger = logging.getLogger(logger_name)
        self._stream = StringIO()
        self._handler = logging.StreamHandler(self._stream)
        self._handler.setFormatter(
            logging.Formatter("%(levelname)s:%(name)s:%(message)s")
        )
        self._prev_level = self._logger.level
        self._prev_propagate = self._logger.propagate

    def __enter__(self) -> "_Capture":
        self._logger.addHandler(self._handler)
        self._logger.setLevel(logging.DEBUG)
        # Keep the records off the root handlers so a pytest capture plugin is
        # not what this test is actually measuring.
        self._logger.propagate = False
        return self

    def __exit__(self, *exc) -> None:
        self._handler.flush()
        self._logger.removeHandler(self._handler)
        self._logger.setLevel(self._prev_level)
        self._logger.propagate = self._prev_propagate

    @property
    def text(self) -> str:
        self._handler.flush()
        return self._stream.getvalue()


# ---------------------------------------------------------------------------
# Defect A — AuditLogNode / SecurityEventNode
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("output_format", ["json", "text"])
def test_audit_log_node_withholds_credential_valued_keys(output_format):
    """LOAD-BEARING for defect A: a credential-named key must not reach the log.

    Both formats are exercised because they are separate sinks: ``json.dumps``
    escapes control characters but does NOT withhold values, and the ``else``
    branch interpolates ``event_data`` into an f-string with no escaping at all.
    A fix applied to only one leaves the other live.
    """
    from kailash.nodes.security.audit_log import AuditLogNode

    node = AuditLogNode(name="issue2167_audit", output_format=output_format)

    with _Capture("audit.issue2167_audit") as cap:
        node.execute(
            event_type="info",
            message="provisioning complete",
            user_id="alice",
            event_data={
                "api_key": _SECRET,
                "nested": {"refresh_token": _TOKEN},
                "password": _PASSWORD,
            },
        )

    for leaked in (_SECRET, _TOKEN, _PASSWORD):
        assert (
            leaked not in cap.text
        ), f"credential reached the audit log ({output_format} format): {cap.text!r}"
    assert (
        "[REDACTED]" in cap.text
    ), f"expected a redaction marker recording that a field was withheld: {cap.text!r}"


def test_audit_log_node_keeps_non_credential_fields_readable():
    """CONTROL: redaction must withhold values, not gut the record.

    Without this, a fix that dropped ``event_data`` wholesale — or replaced the
    whole bag with one marker — would pass the test above for the wrong reason.
    """
    from kailash.nodes.security.audit_log import AuditLogNode

    node = AuditLogNode(name="issue2167_audit_ctl", output_format="text")

    with _Capture("audit.issue2167_audit_ctl") as cap:
        node.execute(
            event_type="info",
            message="provisioning complete",
            event_data={"tenant": "acme-corp", "record_count": 42, "api_key": _SECRET},
        )

    assert "acme-corp" in cap.text, f"diagnostic field was lost: {cap.text!r}"
    assert "42" in cap.text, f"diagnostic field was lost: {cap.text!r}"
    assert (
        "api_key" in cap.text
    ), f"the KEY must survive so an auditor sees which field was withheld: {cap.text!r}"
    assert _SECRET not in cap.text


def test_audit_log_node_returned_entry_is_also_redacted():
    """The returned entry must agree with what was logged.

    Returning the unredacted bag while logging a redacted one would put the
    credential straight back into workflow results, which are themselves
    routinely logged and persisted.
    """
    from kailash.nodes.security.audit_log import AuditLogNode

    node = AuditLogNode(name="issue2167_audit_ret")
    result = node.execute(event_type="info", event_data={"api_key": _SECRET})

    assert _SECRET not in str(
        result
    ), f"credential survived in the return value: {result!r}"


def test_security_event_node_withholds_credential_valued_metadata():
    """Defect A's sibling: ``SecurityEventNode`` metadata is returned and rendered.

    Its ``log_message`` does not interpolate ``metadata``, so the exposure here
    is the returned bag rather than the log line — the same class, and the same
    fix `_log_hygiene.py:23-26` prescribes for both nodes.
    """
    from kailash.nodes.security.security_event import SecurityEventNode

    node = SecurityEventNode(name="issue2167_secevent")
    result = node.execute(
        event_type="login_failed",
        severity="HIGH",
        message="bad credential",
        metadata={"totp_secret": _SECRET, "nested": {"authorization": _TOKEN}},
    )

    assert _SECRET not in str(result), f"credential survived: {result!r}"
    assert _TOKEN not in str(result), f"credential survived: {result!r}"


def test_log_injection_defence_is_preserved_alongside_redaction():
    """CONTROL: the #2088 sanitizer must still run — redaction is ADDITIVE.

    A fix that swapped ``sanitize_log_structure`` for ``redact_mapping`` rather
    than composing them would withhold credentials while re-opening the
    newline-forgery hole. This asserts both properties hold at once.
    """
    from kailash.nodes.security.audit_log import AuditLogNode

    node = AuditLogNode(name="issue2167_audit_inj", output_format="text")

    with _Capture("audit.issue2167_audit_inj") as cap:
        node.execute(
            event_type="info",
            message="ok",
            event_data={
                "note": "line1\nINFO:audit:forged second record",
                "api_key": _SECRET,
            },
        )

    emitted = cap.text.rstrip("\n")
    assert (
        len(emitted.splitlines()) == 1
    ), f"a newline in event_data forged a second log record: {cap.text!r}"
    assert _SECRET not in cap.text


# ---------------------------------------------------------------------------
# Defect B — HTTPRequestNode / AsyncHTTPRequestNode
# ---------------------------------------------------------------------------

_CRED_URL = f"https://svc:{_PASSWORD}@api.example.com/v1/items?api_key={_SECRET}"


def _http_logger_name(node) -> str:
    """The node's own logger, so the capture measures the node and nothing else."""
    return node.logger.name


@pytest.mark.parametrize("log_requests", [False, True])
def test_sync_http_node_masks_credentials_in_the_request_url(log_requests, monkeypatch):
    """LOAD-BEARING for defect B (sync class — CodeQL never flagged this one).

    ``log_requests=False`` is the DEFAULT path and still logs the URL, so both
    branches are measured.
    """
    from kailash.nodes.api.http import HTTPRequestNode

    node = HTTPRequestNode(name="issue2167_http_sync")

    with _Capture(_http_logger_name(node)) as cap:
        try:
            node.execute(
                url=_CRED_URL,
                method="GET",
                log_requests=log_requests,
                auth_type="basic",
                auth_username="svc",
                auth_password=_PASSWORD,
                retry_count=0,
                timeout=1,
            )
        except Exception:
            # The request itself is expected to fail (no network). The logging
            # under test happens BEFORE the call is made.
            pass

    assert _PASSWORD not in cap.text, f"password reached the log: {cap.text!r}"
    assert (
        _SECRET not in cap.text
    ), f"credential query param reached the log: {cap.text!r}"
    b64 = base64.b64encode(f"svc:{_PASSWORD}".encode()).decode()
    assert (
        b64 not in cap.text
    ), f"base64 Basic credential reached the log (encoding is not masking): {cap.text!r}"


@pytest.mark.parametrize("log_requests", [False, True])
async def test_async_http_node_masks_credentials_in_the_request_url(log_requests):
    """LOAD-BEARING for defect B (async class — alerts 11506/11507)."""
    from kailash.nodes.api.http import AsyncHTTPRequestNode

    node = AsyncHTTPRequestNode(name="issue2167_http_async")

    with _Capture(_http_logger_name(node)) as cap:
        try:
            await node.async_run(
                url=_CRED_URL,
                method="POST",
                log_requests=log_requests,
                auth_type="basic",
                auth_username="svc",
                auth_password=_PASSWORD,
                json_data={
                    "client_secret": _SECRET,
                    "grant_type": "client_credentials",
                },
                retry_count=0,
                timeout=1,
            )
        except Exception:
            pass

    assert _PASSWORD not in cap.text, f"password reached the log: {cap.text!r}"
    assert _SECRET not in cap.text, f"client_secret reached the log: {cap.text!r}"
    b64 = base64.b64encode(f"svc:{_PASSWORD}".encode()).decode()
    assert (
        b64 not in cap.text
    ), f"base64 Basic credential reached the log (encoding is not masking): {cap.text!r}"


def test_http_node_still_logs_a_usable_diagnostic():
    """CONTROL: masking must not silence the log line entirely.

    Without this, deleting the logging calls would pass every assertion above
    while destroying the operator's only record that a request was made.
    """
    from kailash.nodes.api.http import HTTPRequestNode

    node = HTTPRequestNode(name="issue2167_http_diag")

    with _Capture(_http_logger_name(node)) as cap:
        try:
            node.execute(url=_CRED_URL, method="GET", retry_count=0, timeout=1)
        except Exception:
            pass

    assert (
        "api.example.com" in cap.text
    ), f"the host must survive masking or the log is useless: {cap.text!r}"
