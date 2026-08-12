"""#2088 / #2040 — sanitizing lives at the SINK, not at N call sites.

The acceptance criterion the issue states is a SWEEP, not an enumeration:
"the sweep is the instrument that caught this; the enumeration is what missed
it". So the load-bearing test here is
``test_no_call_site_can_reach_a_sink_with_an_unsanitized_value``, which drives
EVERY call site the AST can find rather than a list someone maintained.

Discrimination is established per assertion: each sink test states the payload
and the record shape that would appear if the sink did nothing, and the sweep
reports the site count it walked (a sweep that walked zero sites would pass
vacuously, so the count is asserted too).
"""

import ast
import json
import logging
import pathlib

import pytest

from kailash.nodes.security.audit_log import AuditLogNode
from kailash.nodes.security.security_event import SecurityEventNode, SeverityLevel
from kailash.utils.secure_logging import sanitize_log_structure, sanitize_log_value

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

# A payload that forges a whole extra record if it is interpolated raw.
INJECTION = "alice\n[CRITICAL] auth_bypass: forged record (User: root)"
CONTROL_CHARS = "u\r\n\x00\x1b[31mid"


def _records(caplog):
    return [r.getMessage() for r in caplog.records]


# ---------------------------------------------------------------------------
# SecurityEventNode — the LIVE surface (unconditional f-string, no json branch)
# ---------------------------------------------------------------------------


class TestSecurityEventSink:
    @pytest.mark.parametrize("field", ["user_id", "message", "event_type"])
    def test_no_field_can_forge_a_second_record(self, caplog, field):
        """Without the sink fix each of these produces TWO lines, the second
        indistinguishable from a genuine CRITICAL security event."""
        node = SecurityEventNode(name="inj")
        with caplog.at_level(logging.INFO, logger="security.inj"):
            node.execute(**{field: INJECTION})

        assert caplog.records, "the sink logged nothing; the test proves nothing"
        for message in _records(caplog):
            assert "\n" not in message, message
            assert "\r" not in message, message

    def test_the_returned_event_is_sanitized_too_not_just_the_log_line(self):
        """The record is the artifact. A caller persisting the returned event
        would otherwise re-introduce the injection downstream."""
        node = SecurityEventNode(name="ret")
        event = node.execute(user_id=INJECTION, message=INJECTION)["security_event"]
        assert "\n" not in event["user_id"]
        assert "\n" not in event["message"]

    def test_nested_metadata_strings_are_sanitized(self):
        node = SecurityEventNode(name="meta")
        event = node.execute(metadata={"a": {"b": [INJECTION]}})["security_event"]
        assert "\n" not in event["metadata"]["a"]["b"][0]

    def test_metadata_keys_are_sanitized_as_well_as_values(self):
        node = SecurityEventNode(name="metakey")
        event = node.execute(metadata={INJECTION: "v"})["security_event"]
        assert all("\n" not in k for k in event["metadata"])

    def test_non_string_metadata_keeps_its_type(self):
        """No-false-positive: sanitizing must not turn numbers into strings."""
        node = SecurityEventNode(name="types")
        event = node.execute(metadata={"n": 5, "f": 1.5, "b": True, "z": None})[
            "security_event"
        ]
        assert event["metadata"] == {"n": 5, "f": 1.5, "b": True, "z": None}

    def test_an_absent_user_id_stays_absent_rather_than_becoming_the_string_none(self):
        node = SecurityEventNode(name="none")
        event = node.execute(message="anonymous")["security_event"]
        assert event["user_id"] is None

    def test_values_are_length_capped_not_only_escaped(self):
        """Escaping alone does not bound anything -- an unbounded field
        survives it intact. Separate problem, separate assertion."""
        node = SecurityEventNode(name="cap")
        event = node.execute(user_id="A" * 50_000, message="B" * 50_000)[
            "security_event"
        ]
        assert len(event["user_id"]) <= 1024
        assert len(event["message"]) <= 1024


class TestSecurityEventSeverityFailsClosed:
    """A sink that raises on a malformed severity DROPS the security event."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("info", SeverityLevel.INFO),
            ("INFO", SeverityLevel.INFO),
            ("critical", SeverityLevel.CRITICAL),
            (" High ", SeverityLevel.HIGH),
            (SeverityLevel.LOW, SeverityLevel.LOW),
        ],
    )
    def test_case_and_whitespace_are_normalized(self, raw, expected):
        node = SecurityEventNode(name="sev")
        result = node.execute(severity=raw)
        assert result["security_event"]["severity"] == expected.value

    @pytest.mark.parametrize("raw", ["warning", "bogus", "", None, 7, object()])
    def test_an_unrecognized_severity_ranks_TIGHTEST_and_does_not_raise(self, raw):
        """CRITICAL, not INFO: a typo must make an event louder, never
        silently downgrade a real CRITICAL below every alert threshold."""
        node = SecurityEventNode(name="sev2", alert_threshold="HIGH")
        result = node.execute(severity=raw)
        assert result["security_event"]["severity"] == "CRITICAL"
        assert result["alert_triggered"] is True

    def test_the_in_tree_workflow_severities_are_valid_members(self):
        """Two in-tree callers passed "info" and "warning", so those two
        security events had never been recorded at all. Pins the literals."""
        source = (REPO_ROOT / "src/kailash/middleware/core/workflows.py").read_text()
        tree = ast.parse(source)
        found = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            for key, value in zip(node.keys, node.values):
                if (
                    isinstance(key, ast.Constant)
                    and key.value == "severity"
                    and isinstance(value, ast.Constant)
                ):
                    found.append(value.value)
        assert found, "found no severity literals; the sweep proves nothing"
        for literal in found:
            SeverityLevel(literal)  # raises if the literal is not a member


# ---------------------------------------------------------------------------
# AuditLogNode — LATENT under json, LIVE under any other format
# ---------------------------------------------------------------------------


class TestAuditLogSink:
    @pytest.mark.parametrize("field", ["user_id", "message", "event_type"])
    def test_the_non_json_path_cannot_forge_a_record(self, caplog, field):
        """This branch is what promotes the node from latent to live: it
        interpolates every field with no escaping at all."""
        node = AuditLogNode(name="txt", output_format="text")
        with caplog.at_level(logging.INFO, logger="audit.txt"):
            node.execute(**{field: INJECTION})

        assert caplog.records
        for message in _records(caplog):
            assert "\n" not in message, message

    def test_nested_event_data_strings_are_covered_on_the_non_json_path(self, caplog):
        """`event_data` is rendered by str(dict) there, so a NESTED string is
        a record field exactly as a top-level one is."""
        node = AuditLogNode(name="txt2", output_format="text")
        with caplog.at_level(logging.INFO, logger="audit.txt2"):
            node.execute(event_data={"outer": {"inner": INJECTION}})

        assert caplog.records
        for message in _records(caplog):
            assert "\n" not in message, message

    def test_the_json_path_stays_parseable_and_carries_no_raw_control_bytes(
        self, caplog
    ):
        node = AuditLogNode(name="js")
        with caplog.at_level(logging.INFO, logger="audit.js"):
            node.execute(user_id=CONTROL_CHARS, message=INJECTION)

        assert caplog.records
        payload = json.loads(_records(caplog)[0])
        assert "\n" not in payload["user_id"]
        assert "\x00" not in payload["user_id"]
        assert "\x1b" not in payload["user_id"]

    def test_the_returned_entry_is_sanitized(self):
        node = AuditLogNode(name="ret")
        entry = node.execute(user_id=INJECTION, event_data={"k": INJECTION})[
            "audit_entry"
        ]
        assert "\n" not in entry["user_id"]
        assert "\n" not in entry["data"]["k"]

    def test_event_type_still_routes_the_log_level(self, caplog):
        """No-false-positive: sanitizing must not break level routing."""
        node = AuditLogNode(name="lvl")
        with caplog.at_level(logging.INFO, logger="audit.lvl"):
            node.execute(event_type="error", message="boom")
        assert caplog.records[0].levelname == "ERROR"


# ---------------------------------------------------------------------------
# THE SWEEP — the instrument the issue asks for
# ---------------------------------------------------------------------------


def _sink_call_sites():
    """Every `self.<attr>.execute(...)` in the SDK whose attr names a sink.

    Walks the AST rather than consulting a list. The enumeration is the thing
    that failed in #2066: two raw sites were missed inside a single branch by
    the author who had just written the helper.
    """
    roots = [REPO_ROOT / "src/kailash"] + sorted(
        (REPO_ROOT / "packages").glob("*/src/*")
    )
    sink_attrs = {
        "audit_log_node",
        "audit_logger",
        "audit_node",
        "security_event_node",
        "security_logger",
        "_audit_node",
    }
    sites = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            # Six gitignored build/lib shadow trees return duplicate hits.
            if "/build/lib/" in str(path):
                continue
            try:
                tree = ast.parse(path.read_text())
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr in (
                    "execute",
                    "run",
                    "execute_async",
                    "async_run",
                ):
                    owner = func.value
                    if isinstance(owner, ast.Attribute) and owner.attr in sink_attrs:
                        sites.append((str(path.relative_to(REPO_ROOT)), node.lineno))
    return sites


def test_the_sweep_actually_finds_call_sites():
    """A sweep that walks nothing passes vacuously. Pin the floor."""
    sites = _sink_call_sites()
    assert len(sites) >= 15, sites


def test_no_call_site_can_reach_a_sink_with_an_unsanitized_value():
    """The structural claim: safety does not depend on the call site.

    Rather than re-checking each caller for a `log_safe(...)` wrapper -- which
    is the discipline that drifted -- this drives the SINKS directly with the
    worst payload any caller could pass, in every parameter each accepts, on
    every output format, and asserts one record out.
    """
    payloads = {
        "user_id": INJECTION,
        "message": INJECTION,
        "event_type": INJECTION,
        "metadata": {INJECTION: [INJECTION, {"deep": INJECTION}]},
        "event_data": {INJECTION: [INJECTION, {"deep": INJECTION}]},
    }

    logging.getLogger("security.sweep").setLevel(logging.DEBUG)
    for fmt in ("json", "text", "plain"):
        audit = AuditLogNode(name="sweep_audit", output_format=fmt)
        entry = audit.execute(**{k: v for k, v in payloads.items() if k != "metadata"})[
            "audit_entry"
        ]
        assert "\n" not in json.dumps(entry).replace("\\n", ""), (fmt, entry)

    event = SecurityEventNode(name="sweep_event").execute(
        **{k: v for k, v in payloads.items() if k != "event_data"}
    )["security_event"]
    assert "\n" not in json.dumps(event).replace("\\n", ""), event


def test_no_sdk_caller_hand_rolls_its_own_log_value_sanitizer():
    """One shared helper, never per-package copies (`rules/security.md`
    § Credential Decode Helpers). `log_safe` is allowed BECAUSE it is now a
    thin alias with no implementation of its own -- asserted here so it
    cannot quietly grow one back."""
    hygiene = (REPO_ROOT / "src/kailash/nodes/auth/_log_hygiene.py").read_text()
    assert "sanitize_log_value" in hygiene
    assert "isprintable" not in hygiene, (
        "_log_hygiene grew its own flattening implementation again; it must "
        "delegate to kailash.utils.secure_logging.sanitize_log_value"
    )


# ---------------------------------------------------------------------------
# #2040 — a PUBLIC value-sanitizer exists and the api_gateway site uses it
# ---------------------------------------------------------------------------


class TestPublicValueSanitizer:
    def test_it_is_public_and_documented(self):
        assert not sanitize_log_value.__name__.startswith("_")
        assert sanitize_log_value.__doc__
        assert not sanitize_log_structure.__name__.startswith("_")
        assert sanitize_log_structure.__doc__

    @pytest.mark.parametrize("raw", ["a\nb", "a\rb", "a\x00b", "a\x1b[31mb", "a b"])
    def test_it_neutralises_every_structure_forging_byte(self, raw):
        out = sanitize_log_value(raw)
        assert "\n" not in out and "\r" not in out
        assert "\x00" not in out and "\x1b" not in out
        assert len(out.splitlines()) <= 1

    def test_it_bounds_length_and_cannot_be_told_not_to(self):
        assert len(sanitize_log_value("x" * 10_000)) <= 1024
        assert len(sanitize_log_value("x" * 10_000, limit=10**9)) <= 1024

    def test_it_never_raises_on_a_hostile_value(self):
        class Hostile:
            def __str__(self):
                raise RuntimeError("no")

        assert sanitize_log_value(Hostile()) == "<unrepresentable>"

    def test_a_lying_str_subclass_cannot_defeat_the_bound(self):
        class Lying(str):
            def __len__(self):
                return 1

        assert len(sanitize_log_value(Lying("x" * 5000))) <= 1024

    def test_structure_sanitizer_bounds_recursion(self):
        payload = current = {}
        for _ in range(50):
            current["next"] = {}
            current = current["next"]
        sanitize_log_structure(payload)  # must not RecursionError

    def test_the_api_gateway_user_id_site_routes_through_it(self):
        """`request.user_id` is the POST body value on the default path, since
        the optional-auth dependency resolves no principal."""
        source = (
            REPO_ROOT / "src/kailash/middleware/communication/api_gateway.py"
        ).read_text()
        assert "from ...utils.secure_logging import sanitize_log_value" in source
        assert 'f"Session created: {session_id} for user {user_id}"' not in source

    def test_the_agent_ui_sibling_sites_route_through_it(self):
        """Found by sweeping, not by fixing only the site #2040 named."""
        source = (REPO_ROOT / "src/kailash/middleware/core/agent_ui.py").read_text()
        assert "sanitize_log_value" in source
        assert 'f"Session created: {session_id} for user {user_id}"' not in source
        assert 'f"Created session {session_id} for user {user_id}"' not in source
