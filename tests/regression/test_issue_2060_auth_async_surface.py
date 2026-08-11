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
            collaborator = getattr(instance, owner.attr, None)
            if collaborator is None or isinstance(
                collaborator, (dict, list, set, tuple, str, int, float, bool)
            ):
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
    """The provider awaits four auth collaborators. Each must expose a
    coroutine ``async_run``; a sync callable satisfies ``hasattr`` but would
    make ``await`` raise at runtime."""
    node = _provider()
    for attr in ("session_node", "sso_node", "directory_node", "mfa_node"):
        collaborator = getattr(node, attr)
        method = getattr(collaborator, "async_run", None)
        assert method is not None, f"{attr} defines no async_run"
        assert inspect.iscoroutinefunction(method), (
            f"{attr}.async_run is not a coroutine function; awaiting it "
            f"would raise at runtime"
        )


def test_provider_http_client_exposes_an_awaitable_surface():
    """HTTPRequestNode has neither async_run nor execute_async, so the OAuth
    and social-token paths awaited a method that does not exist."""
    node = _provider()
    assert inspect.iscoroutinefunction(
        node.http_client.async_run
    ), f"{type(node.http_client).__name__} has no awaitable request surface"
