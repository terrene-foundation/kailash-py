"""Regression tests for issue #2060 — nodes/auth called methods that did not exist.

``EnterpriseAuthProviderNode`` called ``execute_async`` on collaborators that
never defined it. A correctly signed, unexpired, correct-issuer JWT raised
``AttributeError`` in ``_log_auth_event`` before the session step, so
``authenticate`` / ``authorize`` / ``logout`` / ``validate`` could not complete
for any action that logs an auth event. The node was non-functional end to end,
not merely degraded.

The reason this survived is the thing these tests exist to prevent: the previous
coverage exercised helpers directly and stubbed the missing methods. A test that
calls ``_log_auth_event`` in isolation, or that assigns a fake onto
``session_node.execute_async``, passes identically whether or not the real path
can run — assigning to a missing attribute simply creates it. **Every test in
this module drives the public surface** (``async_run(action=...)``) with real
collaborators.

The identity-binding fixes from PR #2035 (issue #2026) are re-asserted here
through that public surface, because until #2060 was closed they were correct in
source and unreachable in practice.
"""

import ast
import asyncio
import inspect
import json
import pathlib
import time

import pytest

from kailash.nodes.auth.directory_integration import DirectoryIntegrationNode
from kailash.nodes.auth.enterprise_auth_provider import EnterpriseAuthProviderNode
from kailash.nodes.auth.mfa import MultiFactorAuthNode
from kailash.nodes.auth.session_management import SessionManagementNode
from kailash.nodes.auth.sso import SSOAuthenticationNode

SECRET = "signing-secret-for-tests"
ISSUER = "https://idp.test.invalid"


def _provider(**overrides):
    """A provider wired for JWT auth with no risk/adaptive machinery."""
    kwargs = dict(
        name="eap_2060",
        enabled_methods=["jwt"],
        adaptive_auth_enabled=False,
        risk_assessment_enabled=False,
        jwt_config={"secret": SECRET, "issuer": ISSUER},
        user_permissions={"alice": ["read", "write"]},
    )
    kwargs.update(overrides)
    return EnterpriseAuthProviderNode(**kwargs)


def _token(subject="alice", **claims):
    pyjwt = pytest.importorskip("jwt")
    payload = {"sub": subject, "exp": int(time.time()) + 3600, "iss": ISSUER}
    payload.update(claims)
    return pyjwt.encode(payload, SECRET, algorithm="HS256")


async def _authenticate(node, claimed_user_id="alice"):
    return await node.async_run(
        action="authenticate",
        auth_method="jwt",
        credentials={"jwt_token": _token()},
        user_id=claimed_user_id,
        risk_context={"ip_address": "203.0.113.7"},
    )


# ---------------------------------------------------------------------------
# The four public actions complete end to end
# ---------------------------------------------------------------------------


def test_authenticate_completes_through_the_public_surface():
    """A valid JWT authenticates. This raised AttributeError before #2060."""
    node = _provider()
    result = asyncio.run(_authenticate(node))

    assert result["success"] is True, result
    assert result["authenticated"] is True, result
    assert result["session_id"], "authenticate returned no session id"


def test_validate_completes_through_the_public_surface():
    node = _provider()

    async def scenario():
        auth = await _authenticate(node)
        return await node.async_run(action="validate", session_id=auth["session_id"])

    result = asyncio.run(scenario())
    assert result["valid"] is True, result


def test_authorize_completes_through_the_public_surface():
    node = _provider()

    async def scenario():
        auth = await _authenticate(node)
        return await node.async_run(
            action="authorize",
            session_id=auth["session_id"],
            user_id="alice",
            permissions=["read"],
            resource="doc/1",
        )

    result = asyncio.run(scenario())
    assert result["authorized"] is True, result


def test_logout_completes_and_invalidates_the_session():
    node = _provider()

    async def scenario():
        auth = await _authenticate(node)
        out = await node.async_run(
            action="logout", user_id="alice", session_id=auth["session_id"]
        )
        after = await node.async_run(action="validate", session_id=auth["session_id"])
        return out, after

    logout, after = asyncio.run(scenario())
    assert logout["logged_out"] is True, logout
    assert after["valid"] is False, "session survived logout"


# ---------------------------------------------------------------------------
# PR #2035's identity binding, asserted through the surface that runs
# ---------------------------------------------------------------------------


def test_session_binds_to_the_credential_subject_not_the_caller_claim():
    """alice's credential presented as user_id='admin' yields a session for alice.

    This is PR #2035's fix. Before #2060 it could not execute.
    """
    node = _provider()
    result = asyncio.run(_authenticate(node, claimed_user_id="admin"))

    assert result["user_id"] == "alice", (
        "authenticate honoured the caller-supplied identity over the "
        f"credential's subject: {result}"
    )
    assert result["session_details"]["success"] is True, result["session_details"]


def test_authorize_resolves_the_subject_from_the_session_not_the_caller():
    """The caller claims 'admin'; authorization must evaluate alice's grants."""
    node = _provider()

    async def scenario():
        auth = await _authenticate(node, claimed_user_id="admin")
        allowed = await node.async_run(
            action="authorize",
            session_id=auth["session_id"],
            user_id="admin",  # the caller's claim, which must be ignored
            permissions=["read"],
            resource="doc/1",
        )
        denied = await node.async_run(
            action="authorize",
            session_id=auth["session_id"],
            user_id="admin",
            permissions=["delete"],  # alice holds read+write only
            resource="doc/1",
        )
        return allowed, denied

    allowed, denied = asyncio.run(scenario())

    assert allowed["authorized"] is True, allowed
    assert (
        allowed["user_id"] == "alice"
    ), f"authorization bound to the caller's claim, not the session: {allowed}"
    assert denied["authorized"] is False, (
        "caller claiming admin was granted a permission the session's subject "
        f"does not hold: {denied}"
    )
    assert denied["reason"] == "insufficient_permissions", denied


def test_authorize_without_a_session_is_refused():
    node = _provider()
    result = asyncio.run(
        node.async_run(
            action="authorize", user_id="admin", permissions=["read"], resource="doc/1"
        )
    )
    assert result["authorized"] is False, result
    assert result["reason"] == "session_required", result


# ---------------------------------------------------------------------------
# The records the auth path writes actually say what happened
# ---------------------------------------------------------------------------


def test_session_records_the_authenticating_method_not_a_hardcoded_password():
    """login_method was hardcoded to "password" and the caller could not set it."""
    node = _provider()

    async def scenario():
        auth = await _authenticate(node)
        session_id = auth["session_id"]
        return node.session_node.sessions[session_id]

    session = asyncio.run(scenario())
    assert session.login_method == "jwt", (
        "session recorded a password login for a JWT authentication: "
        f"{session.login_method!r}"
    )


def test_auth_events_are_recorded_with_content(caplog):
    """SecurityEventNode was handed parameters it does not read, so every
    event was written with an empty message and no user."""
    node = _provider()
    with caplog.at_level("INFO", logger="security.eap_2060_security"):
        asyncio.run(_authenticate(node))

    records = [r for r in caplog.records if r.name == "security.eap_2060_security"]
    assert records, "no security event was recorded for a successful authentication"
    assert any("auth_success" in r.getMessage() for r in records), [
        r.getMessage() for r in records
    ]


def test_auth_success_event_names_the_resolved_principal(caplog):
    """The event must attribute the login to alice, not to the claimed 'admin'."""
    node = _provider()
    with caplog.at_level("INFO", logger="security.eap_2060_security"):
        asyncio.run(_authenticate(node, claimed_user_id="admin"))

    messages = [
        r.getMessage()
        for r in caplog.records
        if r.name == "security.eap_2060_security" and "auth_success" in r.getMessage()
    ]
    assert messages, "no auth_success event recorded"
    assert any("User: alice" in m for m in messages), (
        f"auth success attributed to the caller's claim rather than the "
        f"authenticated principal: {messages}"
    )


def test_session_audit_record_names_the_operation():
    """AuditLogNode was called with action=/resource_id=, which it drops, so
    every session audit entry was {"message": "", "data": {}}."""
    node = SessionManagementNode(name="sess_2060")
    written = []
    node.audit_log_node.execute = lambda **kw: written.append(kw) or {"logged": True}

    node.execute(action="create", user_id="alice", ip_address="203.0.113.7")

    assert written, "session creation wrote no audit record"
    entry = written[0]
    assert entry["event_type"] == "session_create", entry
    assert entry["message"], "audit record carries an empty message"
    assert entry["event_data"]["resource_id"], "audit record names no session"


def test_session_security_events_are_not_swallowed_by_a_severity_error():
    """severity was forwarded lowercase; SeverityLevel() rejects it, and the
    except-clause swallowed the ValueError, so no event was ever recorded."""
    node = SessionManagementNode(name="sess_sev_2060", max_sessions=1)
    seen = []
    node.security_event_node.execute = lambda **kw: seen.append(kw) or {"ok": True}

    # Two sessions for one user with max_sessions=1 trips session_limit_exceeded.
    node.execute(action="create", user_id="alice", ip_address="203.0.113.7")
    node.execute(action="create", user_id="alice", ip_address="203.0.113.7")

    assert seen, "no session security event was recorded"
    for event in seen:
        assert event[
            "severity"
        ].isupper(), f"severity forwarded in a form SeverityLevel() rejects: {event['severity']!r}"


# ---------------------------------------------------------------------------
# MFA audit sink
# ---------------------------------------------------------------------------


def test_mfa_audit_sink_is_wired():
    """The sink stood at None from this file's first commit behind a deadlock
    claim for which no evidence exists in the repository's history."""
    node = MultiFactorAuthNode(name="mfa_2060")
    assert node.audit_log_node is not None, "MFA audit sink is not wired"
    assert node.security_event_node is not None, "MFA security event sink is not wired"


@pytest.mark.parametrize("action", ["revoke", "disable", "reset"])
def test_admin_gated_destructive_mfa_actions_write_an_audit_record(action):
    """revoke/disable/reset completed with no record: the sink was None AND the
    sync dispatcher's audit call was commented out."""
    node = MultiFactorAuthNode(name=f"mfa_{action}_2060")
    written = []
    node.audit_log_node.execute = lambda **kw: written.append(kw) or {"logged": True}

    node.run(action=action, user_id="alice", admin_override=True)

    assert written, f"{action} completed with no audit record"
    # `reset` re-enrols before resetting, so it legitimately writes an
    # enrolment record too; the operation's own record must be among them.
    matching = [e for e in written if e["event_type"] == f"mfa_{action}"]
    assert matching, (
        f"{action} wrote records but none naming the operation: "
        f"{[e['event_type'] for e in written]}"
    )
    entry = matching[0]
    assert entry["message"], "audit record carries an empty message"
    assert entry["user_id"] == "alice", entry


def test_mfa_audit_records_declare_the_missing_actor():
    """#2047: this node has no caller identity. The record must not imply that
    user_id is the actor — an auditor reading it sees the subject only."""
    node = MultiFactorAuthNode(name="mfa_actor_2060")
    written = []
    node.audit_log_node.execute = lambda **kw: written.append(kw) or {"logged": True}

    node.run(action="revoke", user_id="alice", admin_override=True)

    assert written, "revoke wrote no audit record"
    assert "actor" in written[0]["event_data"], written[0]
    assert written[0]["event_data"]["actor"] is None, (
        "the node grew a caller identity; #2047 may be closed and this "
        "expectation should be revisited"
    )


# ---------------------------------------------------------------------------
# The mechanical sweep the issue asks for
# ---------------------------------------------------------------------------


def test_no_auth_node_calls_a_collaborator_method_that_does_not_exist():
    """Acceptance criterion: a mechanical sweep, not a judgement call.

    Walks the AST of every module in ``nodes/auth`` for ``self.<collab>.<m>()``
    and asserts ``<m>`` resolves on the constructed collaborator.

    Discrimination: run against ``main`` at aba8a0878 this reports 19 broken
    call sites across ``enterprise_auth_provider.py``, ``sso.py`` and
    ``directory_integration.py``. It is not a check that cannot fail.
    """
    import kailash

    instances = {
        "directory_integration.py": DirectoryIntegrationNode(name="d_sweep"),
        "enterprise_auth_provider.py": EnterpriseAuthProviderNode(name="e_sweep"),
        "mfa.py": MultiFactorAuthNode(name="m_sweep"),
        "session_management.py": SessionManagementNode(name="s_sweep"),
        "sso.py": SSOAuthenticationNode(name="o_sweep"),
    }
    auth_dir = pathlib.Path(kailash.__file__).parent / "nodes" / "auth"

    broken = []
    for filename, instance in instances.items():
        tree = ast.parse((auth_dir / filename).read_text())
        for call in ast.walk(tree):
            if not (
                isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
            ):
                continue
            owner = call.func.value
            if not (
                isinstance(owner, ast.Attribute)
                and isinstance(owner.value, ast.Name)
                and owner.value.id == "self"
            ):
                continue
            if not hasattr(instance, owner.attr):
                continue
            collaborator = getattr(instance, owner.attr)
            if isinstance(
                collaborator, (dict, list, set, tuple, str, int, float, bool)
            ):
                continue
            if collaborator is None:
                # Do NOT skip. A None collaborator is the shape that hid
                # mfa.py's two broken sink calls from this sweep on main: the
                # sink was None, so `hasattr(None, "async_run")` was never the
                # question asked. Reported, not passed over.
                broken.append(
                    f"{filename}:{call.lineno} self.{owner.attr}.{call.func.attr}() "
                    f"-> self.{owner.attr} is None; the call cannot resolve"
                )
                continue
            if not hasattr(collaborator, call.func.attr):
                broken.append(
                    f"{filename}:{call.lineno} self.{owner.attr}.{call.func.attr}() "
                    f"-> {type(collaborator).__name__} defines no {call.func.attr!r}"
                )

    assert not broken, "collaborator calls that cannot resolve:\n" + "\n".join(
        sorted(set(broken))
    )


def test_every_auth_collaborator_awaited_by_the_provider_is_awaitable():
    """Every method the provider AWAITS on a collaborator must be a coroutine.

    Derived from the source rather than a hardcoded attribute list: the earlier
    version named four attributes and asserted they expose ``async_run``, which
    was already true on the broken tree -- the collaborators always defined it,
    the call sites named ``execute_async``. It was the one test in this module
    that passed before the fix, so it could not have caught the defect. This
    version reads the ``await self.<collab>.<method>(...)`` sites out of the
    AST, so a fifth collaborator or a renamed method is covered automatically.
    """
    import kailash

    node = _provider(name="eap_awaitable")
    source = (
        pathlib.Path(kailash.__file__).parent
        / "nodes"
        / "auth"
        / "enterprise_auth_provider.py"
    ).read_text()

    awaited = set()
    for await_node in ast.walk(ast.parse(source)):
        if not isinstance(await_node, ast.Await):
            continue
        call = await_node.value
        if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)):
            continue
        owner = call.func.value
        if (
            isinstance(owner, ast.Attribute)
            and isinstance(owner.value, ast.Name)
            and owner.value.id == "self"
        ):
            awaited.add((owner.attr, call.func.attr))

    assert awaited, "found no awaited collaborator calls; the sweep proved nothing"

    problems = []
    for attr, method_name in sorted(awaited):
        collaborator = getattr(node, attr, None)
        if collaborator is None:
            continue  # a self-method, e.g. await self._authenticate(...)
        method = getattr(collaborator, method_name, None)
        if method is None:
            problems.append(f"self.{attr}.{method_name} does not exist")
        elif not inspect.iscoroutinefunction(method):
            problems.append(
                f"self.{attr}.{method_name} is awaited but is not a coroutine "
                f"function ({type(collaborator).__name__})"
            )
    assert not problems, "awaited collaborator methods that cannot be awaited:\n" + (
        "\n".join(problems)
    )


def test_provider_http_client_exposes_an_awaitable_surface():
    """HTTPRequestNode has neither async_run nor execute_async, so the OAuth
    and social-token paths awaited a method that does not exist."""
    node = _provider()
    assert inspect.iscoroutinefunction(
        node.http_client.async_run
    ), f"{type(node.http_client).__name__} has no awaitable request surface"


# ---------------------------------------------------------------------------
# Findings from the adversarial security review of this change
#
# Wiring an audit sink that had never been wired, and resolving calls that had
# never executed, made several latent defects reachable for the first time.
# These are the tests for them.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "action,kwargs",
    [
        ("setup", {"method": "totp", "user_email": "alice@test.invalid"}),
        ("reset", {"method": "totp", "admin_override": True}),
        ("generate_backup_codes", {"admin_override": True}),
    ],
)
def test_audit_records_never_carry_credential_material(action, kwargs, caplog):
    """The MFA audit record must not contain the second factor itself.

    Wiring the sink while copying the whole result dict put the TOTP seed, the
    otpauth:// provisioning URI that embeds it, and the backup codes into the
    audit log -- readable by anyone with log access, and strictly worse than
    the unwired sink it replaced.
    """
    logger_name = f"audit.mfa_secret_{action}_audit_log"
    node = MultiFactorAuthNode(name=f"mfa_secret_{action}")

    # Enrol first. Without this, generate_backup_codes returns
    # {"success": False, "error": "MFA not setup for user"} and every
    # credential assertion below iterates over None -- the test passes without
    # ever examining a secret.
    node.run(action="setup", user_id="alice", method="totp", user_email="a@t.invalid")
    caplog.clear()

    with caplog.at_level("INFO", logger=logger_name):
        result = node.run(action=action, user_id="alice", **kwargs)

    assert result.get("success") is True, (
        f"{action} did not succeed, so this test examined no credential "
        f"material: {result}"
    )

    written = "\n".join(r.getMessage() for r in caplog.records if r.name == logger_name)
    assert written, f"{action} wrote no audit record"

    secret_keys = (
        "secret",
        "provisioning_uri",
        "qr_code",
        "qr_code_data",
        "qr_code_uri",
        "trust_token",
        "session_id",
    )
    for key in secret_keys:
        value = result.get(key)
        if isinstance(value, str) and len(value) > 6:
            assert (
                value not in written
            ), f"{action} wrote {key!r} into the audit log in plaintext"

    for key in ("backup_codes", "recovery_codes"):
        for code in result.get(key) or []:
            assert (
                str(code) not in written
            ), f"{action} wrote a {key[:-1]} into the audit log in plaintext"

    assert "otpauth://" not in written, "provisioning URI leaked to the audit log"


def test_audit_record_declares_what_it_withheld():
    """Redaction must be visible, not silent: a partial result presented as a
    whole one is its own kind of false record."""
    node = MultiFactorAuthNode(name="mfa_omit")
    written = []
    node.audit_log_node.execute = lambda **kw: written.append(kw) or {"logged": True}

    node.run(action="setup", user_id="alice", method="totp", user_email="a@t.invalid")

    entries = [e for e in written if e["event_type"] == "mfa_setup"]
    assert entries, "setup wrote no mfa_setup record"
    omitted = entries[0]["event_data"]["result"]["omitted_keys"]
    assert "secret" in omitted, omitted
    assert "backup_codes" in omitted or "recovery_codes" in omitted, omitted


def test_audit_sink_never_runs_while_the_mfa_data_lock_is_held():
    """AuditLogNode.execute calls the operator's logging handler. Under
    ``_data_lock`` a slow syslog/HTTP handler would stall every MFA operation
    in the process -- a slow log collector becoming an auth outage.

    Discrimination: this probe reports >= 1 when a sink write happens inside
    the lock; it reported exactly that for ``_log_mfa_event`` before the write
    was deferred.
    """
    import logging as _logging

    node = MultiFactorAuthNode(name="mfa_lockprobe")
    under_lock = []

    class _LockProbe(_logging.Handler):
        def emit(self, record):
            acquired = node._data_lock.acquire(blocking=False)
            under_lock.append(not acquired)
            if acquired:
                node._data_lock.release()

    audit_logger = _logging.getLogger("audit.mfa_lockprobe_audit_log")
    original = audit_logger.handlers
    audit_logger.handlers = [_LockProbe()]
    audit_logger.setLevel(_logging.INFO)
    try:
        node.run(
            action="setup", user_id="alice", method="totp", user_email="a@t.invalid"
        )
    finally:
        audit_logger.handlers = original

    assert under_lock, "no sink write was observed; the probe proved nothing"
    assert not any(under_lock), (
        f"{sum(under_lock)} of {len(under_lock)} audit writes ran while "
        "_data_lock was held"
    )


def test_rate_limited_verify_is_audited():
    """A brute-force must not silence the audit trail exactly when it matters.

    The rate-limit early return skipped the audit call at the end of the
    dispatcher, so records stopped at the threshold.
    """
    node = MultiFactorAuthNode(name="mfa_rl", rate_limit_attempts=1)
    written = []
    node.audit_log_node.execute = lambda **kw: written.append(kw) or {"logged": True}

    for _ in range(4):
        node.run(action="verify", user_id="alice", code="000000", method="totp")

    rate_limited = [
        e for e in written if e["event_data"]["result"].get("rate_limited") is True
    ]
    assert rate_limited, (
        "rate-limited verify attempts produced no audit record: "
        f"{[e['event_type'] for e in written]}"
    )


def test_non_authenticating_actions_do_not_forge_an_auth_success_record(caplog):
    """get_methods echoes the caller's own user_id back and defaults to
    success, so emitting "auth_success" for it let an unauthenticated caller
    write a record indistinguishable from a genuine login for any principal."""
    node = _provider(name="eap_forge")
    with caplog.at_level("INFO", logger="security.eap_forge_security"):
        asyncio.run(node.async_run(action="get_methods", user_id="ceo@corp"))

    messages = [
        r.getMessage()
        for r in caplog.records
        if r.name == "security.eap_forge_security"
    ]
    assert messages, "get_methods recorded nothing at all"
    assert not any(
        "auth_success" in m for m in messages
    ), f"a non-authenticating action forged an auth_success record: {messages}"
    assert (
        node.auth_statistics["successful_auths"] == 0
    ), "a non-authenticating action incremented the successful-auth counter"


def test_a_genuine_login_is_distinguishable_from_a_non_authenticating_action(caplog):
    """The positive half of the check above: authenticate MUST still record
    auth_success, or the test above would pass on a node that logs nothing."""
    node = _provider(name="eap_genuine")
    with caplog.at_level("INFO", logger="security.eap_genuine_security"):
        asyncio.run(_authenticate(node))

    messages = [
        r.getMessage()
        for r in caplog.records
        if r.name == "security.eap_genuine_security"
    ]
    assert any(
        "auth_success" in m for m in messages
    ), f"a real authentication did not record auth_success: {messages}"


def test_user_id_cannot_inject_a_second_log_record(caplog):
    """SecurityEventNode renders user_id into an f-string with no escaping and
    this node's user_id is caller-supplied, so a newline wrote a second
    well-formed record: fabricate logins, bury the real ones."""
    node = _provider(name="eap_inject")
    payload = "alice\n[INFO] auth_success: auth_success via enterprise_auth_provider (User: root)"

    with caplog.at_level("INFO", logger="security.eap_inject_security"):
        asyncio.run(node.async_run(action="get_methods", user_id=payload))

    for record in caplog.records:
        if record.name != "security.eap_inject_security":
            continue
        assert "\n" not in record.getMessage(), (
            f"a caller-supplied user_id produced a multi-line record: "
            f"{record.getMessage()!r}"
        )


def test_sso_security_events_are_recorded_with_severity_and_user(caplog):
    """sso.py probed getattr(security_logger, "async_run"/"execute_async") --
    SecurityEventNode defines neither, so the loop was dead code (issue #2057's
    shape) and the fall-through passed source=/timestamp=/details=, none of
    which the node reads. Every SSO event was a blank INFO line with no user,
    including authentication FAILURES."""
    node = SSOAuthenticationNode(name="sso_ev")
    seen = []
    node.security_logger.execute = lambda **kw: seen.append(kw) or {"ok": True}

    asyncio.run(
        node._log_security_event(
            event_type="sso_failure", action="callback", user_id="alice"
        )
    )

    assert seen, "no SSO security event was recorded"
    event = seen[0]
    assert event["user_id"] == "alice", event
    assert event["message"], "SSO security event carries an empty message"
    assert event["severity"] == "HIGH", (
        f"an SSO authentication failure was recorded at {event['severity']}, "
        "below the default HIGH alert threshold"
    )


def test_http_body_unwraps_the_response_envelope():
    """Both HTTP nodes return {"response": <HTTPResponse envelope>}, and the
    body lives at envelope["content"]. Callers read the envelope directly and
    looked for "email" on it, so a valid token was reported invalid."""
    from kailash.nodes.auth._http_response import http_body

    envelope_result = {
        "success": True,
        "response": {
            "status_code": 200,
            "headers": {},
            "content_type": "application/json",
            "content": {"email": "alice@test.invalid"},
        },
    }
    assert http_body(envelope_result) == {"email": "alice@test.invalid"}
    assert http_body({"success": False, "response": None}) == {}
    assert http_body(None) == {}


# ---------------------------------------------------------------------------
# Second review round: parity across every sink, not just the provider's
# ---------------------------------------------------------------------------


def _injection_payload():
    return "alice\n[INFO] auth_success: auth_success via enterprise_auth_provider (User: root)"


def test_no_auth_node_writes_a_multi_line_security_record():
    """Parity sweep. The first fix sanitized user_id at the provider only,
    while this change made four SIBLING sinks reachable for the first time --
    each of which passes user_id straight into SecurityEventNode's unescaped
    f-string. Fixing one site and leaving the siblings is the multi-site
    plumbing failure `rules/security.md` names.
    """
    payload = _injection_payload()
    offenders = []

    def _recorder(store):
        def _execute(**kwargs):
            store.append(kwargs)
            return {"ok": True}

        return _execute

    # SSO
    sso = SSOAuthenticationNode(name="sso_par")
    sso_seen = []
    sso.security_logger.execute = _recorder(sso_seen)
    asyncio.run(
        sso._log_security_event(
            event_type="sso_failure", action="callback", user_id=payload
        )
    )

    # Session management
    sess = SessionManagementNode(name="sess_par")
    sess_seen = []
    sess.security_event_node.execute = _recorder(sess_seen)
    sess._log_security_event(payload, "session_anomaly_detected", "medium", {})

    # Directory
    directory = DirectoryIntegrationNode(name="dir_par")
    dir_seen = []
    directory.security_logger.execute = _recorder(dir_seen)
    asyncio.run(
        directory._log_security_event(
            event_type="authentication_failure", user_id=payload
        )
    )

    # Provider
    provider = _provider(name="eap_par")
    eap_seen = []
    provider.security_logger.execute = _recorder(eap_seen)
    asyncio.run(provider._log_auth_event(event_type="auth_failure", user_id=payload))

    for label, seen in (
        ("sso", sso_seen),
        ("session_management", sess_seen),
        ("directory_integration", dir_seen),
        ("enterprise_auth_provider", eap_seen),
    ):
        assert seen, f"{label} recorded no security event; the sweep proved nothing"
        for event in seen:
            for field in ("user_id", "message"):
                value = event.get(field)
                if isinstance(value, str) and "\n" in value:
                    offenders.append(f"{label}.{field}")

    assert not offenders, (
        "these sinks let a caller-supplied value write a second log record: "
        + ", ".join(sorted(set(offenders)))
    )


def test_mfa_revocation_emits_the_high_severity_security_event():
    """The four MFA security-event calls stood commented out as "disabled for
    sync operation" because the only surface was async and they run under
    _data_lock. So mfa_revoked -- the event that pages someone when a second
    factor is destroyed -- had never fired."""
    node = MultiFactorAuthNode(name="mfa_sec_evt")
    seen = []
    node.security_event_node.execute = lambda **kw: seen.append(kw) or {"ok": True}

    node.run(action="setup", user_id="alice", method="totp", user_email="a@t.invalid")
    seen.clear()
    node.run(action="revoke", user_id="alice", admin_override=True)

    revoked = [e for e in seen if e["event_type"] == "mfa_revoked"]
    assert (
        revoked
    ), f"revoke emitted no mfa_revoked security event: {[e['event_type'] for e in seen]}"
    assert revoked[0]["severity"] == "HIGH", (
        f"MFA revocation recorded at {revoked[0]['severity']}, below the "
        "default HIGH alert threshold"
    )


def test_queued_records_are_flushed_even_when_the_operation_fails():
    """The flush sits in a finally. A record queued under _data_lock and never
    flushed would linger until some later dispatch happened to drain it, or
    fall off the end of the bounded queue."""
    node = MultiFactorAuthNode(name="mfa_flush")
    written = []
    node.audit_log_node.execute = lambda **kw: written.append(kw) or {"logged": True}

    # An action that returns a failure result rather than succeeding.
    node.run(action="verify", user_id="alice", code="000000", method="totp")

    assert (
        not node._pending_audit_records
    ), f"{len(node._pending_audit_records)} records were left unflushed"
    assert written, "a failed operation wrote no audit record at all"


def test_bounded_in_process_event_history():
    """audit_events sat next to a bounded deque as an UNBOUNDED list, retaining
    every event for the node's lifetime and defeating the cap beside it."""
    node = MultiFactorAuthNode(name="mfa_bounded")
    assert hasattr(
        node.audit_events, "maxlen"
    ), "audit_events is unbounded; it grows without limit"
    assert node.audit_events.maxlen is not None


def test_social_token_validation_reads_the_identity_from_the_response_body():
    """End-to-end cover for the envelope fix at the CALL SITE, not just the
    helper. Reading result["response"] found no email on the envelope, so a
    valid token was reported as an invalid one."""
    node = _provider(name="eap_social")

    async def _fake_request(**kwargs):
        return {
            "success": True,
            "status_code": 200,
            "response": {
                "status_code": 200,
                "headers": {},
                "content_type": "application/json",
                "content": {"email": "alice@test.invalid"},
            },
        }

    node.http_client.async_run = _fake_request
    result = asyncio.run(node._validate_social_token("google", "a-bearer-token"))

    assert result["valid"] is True, result
    assert (
        result["user_id"] == "alice@test.invalid"
    ), f"the identity was not read out of the response body: {result}"


def test_directory_security_events_redact_credential_bearing_fields():
    """The directory and SSO nodes attach free-form attribute bags to their
    records -- for a directory sync that is the full mapped LDAP/AD entry, and
    for SSO whatever the IdP returned. Those paths were unreachable before this
    change (they awaited a method the sink does not define) and are now live.
    """
    node = DirectoryIntegrationNode(name="dir_redact")
    seen = []
    node.security_logger.execute = lambda **kw: seen.append(kw) or {"ok": True}

    asyncio.run(
        node._log_security_event(
            event_type="authentication_failure",
            user_id="alice",
            directory_data={
                "mail": "alice@test.invalid",
                "userPassword": "hunter2",
                "api_key": "sk-secret-value",
                "nested": {"refresh_token": "rt-secret"},
            },
        )
    )

    assert seen, "the directory node recorded no security event"
    rendered = json.dumps(seen[0], default=str)
    for secret in ("hunter2", "sk-secret-value", "rt-secret"):
        assert (
            secret not in rendered
        ), f"{secret!r} reached the directory security record"
    # The KEY must survive so an auditor can still see which fields were
    # present; only the value is withheld.
    assert (
        "userPassword" in rendered
    ), "redaction dropped the key as well as the value, hiding what was there"


def test_redact_mapping_withholds_values_and_keeps_shape():
    from kailash.nodes.auth._log_hygiene import redact_mapping

    out = redact_mapping(
        {
            "email": "alice@test.invalid",
            "access_token": "at-secret",
            "totp_secret": "seed",
            "items": [{"password": "p"}, {"ok": 1}],
        }
    )
    assert out["email"] == "alice@test.invalid"
    assert out["access_token"] == "[REDACTED]"
    assert out["totp_secret"] == "[REDACTED]"
    assert out["items"][0]["password"] == "[REDACTED]"
    assert out["items"][1]["ok"] == 1


def test_redact_mapping_bounds_recursion_depth():
    """A self-referential attribute bag must not blow the stack inside a
    logging call."""
    from kailash.nodes.auth._log_hygiene import redact_mapping

    node: dict = {}
    node["self"] = node
    rendered = json.dumps(redact_mapping(node))
    assert "REDACTED_DEPTH" in rendered
