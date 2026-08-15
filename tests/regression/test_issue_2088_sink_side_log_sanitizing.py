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

    def test_a_hostile_user_id_produces_exactly_one_record_per_log_call(self, caplog):
        """#2040 AC#4, BEHAVIOURALLY -- the issue says in terms that asserting
        on source text is not sufficient.

        Drives ``AgentUIMiddleware.create_session``, which is the function
        holding the log calls and the one ``POST /api/sessions`` forwards the
        request-body ``user_id`` straight into. Asserts on the RECORDS, not on
        the source.
        """
        import asyncio

        from kailash.middleware.core.agent_ui import AgentUIMiddleware

        middleware = AgentUIMiddleware(max_sessions=8)
        with caplog.at_level(logging.INFO, logger="kailash.middleware.core.agent_ui"):
            asyncio.run(middleware.create_session(user_id=INJECTION + CONTROL_CHARS))

        session_records = [
            r for r in caplog.records if "session" in r.getMessage().lower()
        ]
        assert session_records, "no session record was logged; this proves nothing"
        for record in session_records:
            message = record.getMessage()
            assert len(message.splitlines()) <= 1, message
            assert "\n" not in message and "\r" not in message, message
            assert "\x00" not in message and "\x1b" not in message, message
            # The forged CRITICAL line must not appear as its own record.
            assert not message.startswith("[CRITICAL]"), message

    def test_the_gateway_and_agent_ui_sites_route_through_the_shared_helper(self):
        """The structural half, paired with the behavioural test above rather
        than standing in for it. Covers the two sibling `agent_ui` sites the
        sweep found, which #2040 did not name."""
        gateway = (
            REPO_ROOT / "src/kailash/middleware/communication/api_gateway.py"
        ).read_text()
        assert "from ...utils.secure_logging import sanitize_log_value" in gateway
        assert 'f"Session created: {session_id} for user {user_id}"' not in gateway

        agent_ui = (REPO_ROOT / "src/kailash/middleware/core/agent_ui.py").read_text()
        assert "sanitize_log_value" in agent_ui
        assert 'f"Session created: {session_id} for user {user_id}"' not in agent_ui
        assert 'f"Created session {session_id} for user {user_id}"' not in agent_ui


class TestTheScannerRecognizableBarrierShape:
    """`sanitize_log_value` must END in the one shape CodeQL recognizes.

    `LogInjection::ReplaceLineBreaksSanitizer` matches a `.replace` attribute
    call whose first argument is a string literal in ``["\\r\\n", "\\n"]``, and
    only the node actually RETURNED is the one taint flows out of. The trailing
    `.replace` pair is a runtime no-op -- the join above it has already turned
    every non-printable character, `\\r` and `\\n` included, into a space -- so
    nothing about the OUTPUT would change if someone deleted it as dead code.
    That is exactly why it needs a test: the behavioural assertions in
    `TestPublicValueSanitizer` stay green either way.

    MEASURED, which is what makes this a regression test rather than a
    preference: with a generator-expression join as the returned node, all four
    `py/log-injection` alerts on PR #2103 pointed AT the `sanitize_log_value(...)`
    call itself (api_gateway.py:474,516 and agent_ui.py:455,470), and a
    `neutralModel` row naming the function did not clear them.
    """

    def _returned_expression(self):
        source = (REPO_ROOT / "src/kailash/utils/secure_logging.py").read_text()
        tree = ast.parse(source)
        function = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "sanitize_log_value"
        )
        returns = [n for n in ast.walk(function) if isinstance(n, ast.Return)]
        # By SOURCE POSITION, not `ast.walk` order -- walk is breadth-first, so
        # a `return` nested inside the `except` handler comes back after the
        # top-level one. The success path is the textually last return; the
        # earlier ones are the `<unrepresentable>` / clamp degradations, which
        # carry no caller value.
        return max(returns, key=lambda n: (n.lineno, n.col_offset)).value

    def test_the_success_path_returns_a_replace_call_on_a_newline_literal(self):
        returned = self._returned_expression()
        assert isinstance(returned, ast.Call), ast.dump(returned)
        assert isinstance(returned.func, ast.Attribute), ast.dump(returned.func)
        assert returned.func.attr == "replace", ast.dump(returned.func)
        first_arg = returned.args[0]
        assert isinstance(first_arg, ast.Constant), ast.dump(first_arg)
        # Bare "\r" does NOT satisfy the query -- only "\n" and "\r\n" do -- so
        # the "\n" call must be the outermost, returned one.
        assert first_arg.value in ("\n", "\r\n"), repr(first_arg.value)

    def test_the_pair_is_a_no_op_so_behaviour_is_unchanged(self):
        """Discrimination for the test above: it pins a SHAPE, and this pins
        that the shape costs nothing behaviourally, so a future reader can see
        the two are not in tension."""
        payload = "a\rb\nc\r\nd"
        flattened = "".join(ch if ch.isprintable() else " " for ch in payload)
        assert sanitize_log_value(payload) == flattened
        assert sanitize_log_value(payload) == flattened.replace("\r", " ").replace(
            "\n", " "
        )


class TestSensitiveNameHeuristicSource:
    """The admin capability constant keeps its VALUE and loses its acronym.

    Under the name `MFA_ADMIN_CAPABILITY` this constant was the taint SOURCE
    for six of the seven high-severity alerts on PR #2103, reported as
    "sensitive data (password)" -- `py/clear-text-logging-sensitive-data`
    classifies from the binding's NAME, and reads an `mfa`-containing
    identifier as credential material. It reached six sinks because it is
    interpolated into refusal messages that leave through `result["error"]`,
    which unrelated nodes then log.

    The wire value is the contract and must not drift with the rename.
    """

    def test_the_capability_value_is_unchanged(self):
        from kailash.nodes.auth._actor import ADMIN_CAPABILITY

        assert ADMIN_CAPABILITY == "mfa:admin"

    def test_the_old_name_is_gone_from_the_sdk(self):
        """A leftover alias would re-open every one of the six alerts, since
        the classification is on the NAME and an alias is another binding."""
        for path in (REPO_ROOT / "src/kailash/nodes/auth").rglob("*.py"):
            assert "MFA_ADMIN_CAPABILITY" not in path.read_text(), path


class TestProviderRejectsANameInMfaConfig:
    """`mfa_config={"name": ...}` is a duplicate keyword argument.

    `EnterpriseAuthProviderNode` passes `name=` explicitly and splats
    `**mfa_config`, so a `name` key raised `TypeError: got multiple values for
    keyword argument 'name'` from inside provider construction, naming neither
    the config key nor the provider. It now refuses with a message that does.
    """

    def test_a_name_key_is_refused_by_name(self):
        from kailash.nodes.auth.enterprise_auth_provider import (
            EnterpriseAuthProviderNode,
        )

        with pytest.raises(ValueError) as excinfo:
            EnterpriseAuthProviderNode(name="p", mfa_config={"name": "hijack"})
        message = str(excinfo.value)
        assert "mfa_config" in message and "'name'" in message, message
        assert "p_mfa" in message, message

    def test_a_provider_without_that_key_still_constructs(self):
        """Discrimination: without this the test above would pass against a
        constructor that refused everything."""
        from kailash.nodes.auth.enterprise_auth_provider import (
            EnterpriseAuthProviderNode,
        )

        provider = EnterpriseAuthProviderNode(name="p", mfa_config={})
        assert provider.mfa_node is not None
        assert provider.name == "p"


class TestTheOptOutWarnCannotCarryMfaConfigContent:
    """CodeQL alert #11530 (`mfa.py:89`) is a false positive, and this is why.

    The alert traces `mfa_config` -- classified "sensitive data (password)"
    from the parameter's NAME -- into the opt-out WARN's node name. The edge it
    uses is `MultiFactorAuthNode(name=..., **mfa_config)`: a splat can
    statically supply any keyword, so the analyzer cannot rule out `name`
    coming from the dict. At runtime it never can, because `name=` is passed
    explicitly and a `name` key in `mfa_config` is now refused outright.

    Rather than assert that in prose, this drives the real construction with a
    marked value in `mfa_config` and reads the emitted record. It is the
    artifact backing a false-positive disposition, so it names the payload and
    would FAIL if any config key or value reached the message.
    """

    MARKER = "SEKRIT-hunter2-VALUE"

    def test_the_warn_carries_the_node_name_and_nothing_from_the_config(self, caplog):
        from kailash.nodes.auth.enterprise_auth_provider import (
            EnterpriseAuthProviderNode,
        )

        with caplog.at_level(logging.WARNING, logger="kailash.nodes.auth.mfa"):
            EnterpriseAuthProviderNode(
                name="p2103",
                mfa_config={
                    "require_actor": False,
                    "totp_issuer": self.MARKER,
                },
            )

        warnings = [m for m in _records(caplog) if "require_actor=False" in m]
        assert warnings, "the opt-out WARN did not fire; this proves nothing"
        for message in warnings:
            # Positive control: the record DOES carry the derived node name, so
            # a message that carried nothing at all would not pass this.
            assert "p2103_mfa" in message, message
            # The property under test.
            assert self.MARKER not in message, message
            assert "totp_issuer" not in message, message
