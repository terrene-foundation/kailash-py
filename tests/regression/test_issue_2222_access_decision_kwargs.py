# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #2222 -- ``MiddlewareAccessControlManager`` built
every ``AccessDecision`` with keyword arguments the class rejects.

``AccessDecision`` (``kailash/access_control.py``) declares exactly six fields::

    ['allowed', 'reason', 'applied_rules', 'conditions_met', 'masked_fields',
     'redirect_node']

Every construction site in ``middleware/auth/access_control.py`` additionally
passed ``user_id=``, ``resource_id=`` and ``permission=``::

    TypeError: AccessDecision.__init__() got an unexpected keyword argument
               'user_id'

Measured against the tree, not inferred, and in three places the issue did not
record:

* The issue lists three sites (``:90``, ``:117``, ``:152``). There are **five**.
  ``check_api_access`` and the ``authorize_request`` default-deny branch carry
  the same defect. The default-deny branch is the one whose entire job is to
  refuse safely, and it could not produce a refusal.
* ``:152`` (``check_node_access``) does **not** raise on either shipped
  manager: both ``AccessControlManager`` and ``EnhancedAccessControlManager``
  define ``check_node_access``, so the delegating branch is taken and the
  broken ``else`` is dead. ``:117`` raises only under ``enable_abac=True``,
  because ``EnhancedAccessControlManager`` defines no ``check_workflow_access``.
  ``check_api_access`` raises under **both**.
* ``_emit_access_event`` read ``decision.user_id`` / ``decision.resource_id`` /
  ``decision.permission`` -- the same three absent fields. So wiring an event
  stream raised ``AttributeError`` even on the decisions that constructed
  cleanly. Repairing only the constructors would have moved the failure one
  line later, which is exactly what the issue says fixing #2166 alone would do.

The audit calls carried a parallel defect: ``AuditLogNode`` (an alias for
``EnterpriseAuditLogNode``) declares ``operation`` as its only required
parameter and carries the payload in ``event_data``, and ``Node.execute``
strips undeclared kwargs -- so ``event_type=``/``allowed=``/``reason=`` were
dropped and the call died on the missing ``operation``. ``permission_rule_created``
is not one of the 28 ``AuditEventType`` members either.

These tests are behavioural wherever a real object can reach the code, and
assert BOTH poles: a test that only shows "no longer raises" cannot distinguish
this fix from one that returns a constant deny.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

import pytest

from kailash.access_control import (
    NodePermission,
    PermissionEffect,
    PermissionRule,
    UserContext,
    WorkflowPermission,
    create_attribute_condition,
)
from kailash.middleware.auth.access_control import (
    MiddlewareAccessControlManager,
    MiddlewareAuthenticationMiddleware,
)
from kailash.middleware.communication.events import EventStream
from kailash.nodes.admin.audit_log import AuditEventType

MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "kailash"
    / "middleware"
    / "auth"
    / "access_control.py"
)

# The three names that do not exist on AccessDecision. Passing any of them to
# the constructor raises TypeError; reading any of them off an instance raises
# AttributeError.
REJECTED_FIELDS = ("user_id", "resource_id", "permission")


def _admin() -> UserContext:
    return UserContext(
        user_id="admin-1",
        tenant_id="tenant-a",
        email="admin@example.test",
        roles=["admin"],
        attributes={"department": "engineering"},
    )


def _guest() -> UserContext:
    return UserContext(
        user_id="guest-1",
        tenant_id="tenant-a",
        email="guest@example.test",
        roles=["guest"],
        attributes={"department": "sales"},
    )


def _rbac_manager() -> MiddlewareAccessControlManager:
    """A manager whose rules are real and whose decisions are genuinely computed.

    ``enable_abac=False`` selects ``AccessControlManager``, which evaluates
    plain role rules. No test doubles: the allow pole below is produced by the
    shipped rule evaluator, not by a stub.
    """
    manager = MiddlewareAccessControlManager(enable_abac=False, enable_audit=False)
    manager.access_manager.add_rule(
        PermissionRule(
            id="node-rule",
            resource_type="node",
            resource_id="node-1",
            permission=NodePermission.EXECUTE,
            effect=PermissionEffect.ALLOW,
            role="admin",
        )
    )
    manager.access_manager.add_rule(
        PermissionRule(
            id="workflow-rule",
            resource_type="workflow",
            resource_id="workflow-1",
            permission=WorkflowPermission.EXECUTE,
            effect=PermissionEffect.ALLOW,
            role="admin",
        )
    )
    return manager


# ---------------------------------------------------------------------------
# check_node_access -- both poles, both managers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_node_access_grants_and_denies_rbac():
    """The allow pole and the deny pole are BOTH produced, from real rules.

    A constant-deny implementation fails the first assertion; a constant-allow
    implementation fails the second.
    """
    manager = _rbac_manager()

    granted = await manager.check_node_access(
        _admin(), "node-1", NodePermission.EXECUTE
    )
    assert granted.allowed is True
    assert "node-rule" in granted.reason

    denied = await manager.check_node_access(_guest(), "node-1", NodePermission.EXECUTE)
    assert denied.allowed is False


@pytest.mark.asyncio
async def test_check_node_access_grants_and_denies_abac():
    """Same two poles through the DEFAULT manager (``enable_abac=True``).

    ``EnhancedAccessControlManager`` grants only on a rule whose attribute
    condition evaluates true, so the allow pole here exercises the ABAC
    evaluator rather than role matching.
    """
    manager = MiddlewareAccessControlManager(enable_abac=True, enable_audit=False)
    manager.access_manager.add_rule(
        PermissionRule(
            id="abac-node-rule",
            resource_type="node",
            resource_id="node-1",
            permission=NodePermission.EXECUTE,
            effect=PermissionEffect.ALLOW,
            conditions=create_attribute_condition(
                "user.attributes.department", "equals", "engineering"
            ),
        )
    )

    granted = await manager.check_node_access(
        _admin(), "node-1", NodePermission.EXECUTE
    )
    assert granted.allowed is True

    denied = await manager.check_node_access(_guest(), "node-1", NodePermission.EXECUTE)
    assert denied.allowed is False


# ---------------------------------------------------------------------------
# check_workflow_access -- both poles, plus the unsupported-manager branch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_workflow_access_grants_and_denies_rbac():
    manager = _rbac_manager()

    granted = await manager.check_workflow_access(
        _admin(), "workflow-1", WorkflowPermission.EXECUTE
    )
    assert granted.allowed is True
    assert "workflow-rule" in granted.reason

    denied = await manager.check_workflow_access(
        _guest(), "workflow-1", WorkflowPermission.EXECUTE
    )
    assert denied.allowed is False


@pytest.mark.asyncio
async def test_check_workflow_access_denies_when_manager_lacks_capability(caplog):
    """The ``:117`` branch the issue named -- reached in the SHIPPED default.

    ``EnhancedAccessControlManager`` defines no ``check_workflow_access``, so
    ``enable_abac=True`` (the default) falls into the ``else``. Before the fix
    that branch raised ``TypeError``.

    It must now DENY -- never allow -- and it must say so. A fail-closed path
    that went silent would be a regression of its own: the ``TypeError`` it
    replaced was at least loud.
    """
    manager = MiddlewareAccessControlManager(enable_abac=True, enable_audit=False)
    assert not hasattr(manager.access_manager, "check_workflow_access")

    with caplog.at_level(logging.WARNING):
        decision = await manager.check_workflow_access(
            _admin(), "workflow-1", WorkflowPermission.EXECUTE
        )

    assert decision.allowed is False
    assert "not supported" in decision.reason
    assert "missing_capability" in caplog.text


# ---------------------------------------------------------------------------
# check_api_access -- the fourth construction site, unrecorded in the issue
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("enable_abac", [True, False])
async def test_check_api_access_denies_loudly_on_both_managers(enable_abac, caplog):
    """``:183`` raised ``TypeError`` on BOTH managers before the fix.

    ``get_user_permissions`` is defined on neither manager, so this check can
    only deny. That deny is correct (fail closed) but must not be silent --
    otherwise repairing the constructor would swap a loud crash for an endpoint
    that refuses everyone for no stated reason.
    """
    manager = MiddlewareAccessControlManager(
        enable_abac=enable_abac, enable_audit=False
    )

    with caplog.at_level(logging.WARNING):
        decision = await manager.check_api_access(_admin(), "/v1/things", "GET")

    assert decision.allowed is False
    assert "denied" in decision.reason
    assert "missing_capability" in caplog.text


# ---------------------------------------------------------------------------
# The identity the rejected kwargs were carrying is preserved
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_decision_reason_carries_subject_resource_and_permission():
    """The kwargs were dropped; the information they conveyed was not.

    ``AccessDecision`` has no field for the subject, the resource or the
    permission, and widening that public dataclass is a schema decision this
    module does not own. The values are folded into ``reason``, the field that
    exists.
    """
    manager = _rbac_manager()
    decision = await manager.check_node_access(
        _guest(), "node-1", NodePermission.EXECUTE
    )

    assert "guest-1" in decision.reason
    assert "node-1" in decision.reason
    assert NodePermission.EXECUTE.value in decision.reason


# ---------------------------------------------------------------------------
# _emit_access_event -- the AttributeError the issue never recorded
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_event_emission_carries_identity_and_does_not_raise():
    """Wiring an event stream raised ``AttributeError`` on EVERY decision.

    ``check_node_access`` delegates to the manager and never touched a broken
    constructor, so this failure survives a constructor-only fix. The emitted
    payload must still carry the subject, resource and permission -- the event
    consumers are the reason those values were being threaded at all.
    """
    stream = EventStream()
    manager = _rbac_manager()
    manager.event_stream = stream

    decision = await manager.check_node_access(
        _admin(), "node-1", NodePermission.EXECUTE
    )
    assert decision.allowed is True

    assert len(stream.event_history) == 1
    payload = stream.event_history[0].data["access_decision"]
    assert payload["allowed"] is True
    assert payload["user_id"] == "admin-1"
    assert payload["resource_id"] == "node-1"
    assert payload["permission"] == NodePermission.EXECUTE.value
    assert payload["resource_type"] == "node"


@pytest.mark.asyncio
async def test_event_emission_reports_the_deny_pole():
    """The emitted payload tracks the decision rather than a constant."""
    stream = EventStream()
    manager = _rbac_manager()
    manager.event_stream = stream

    await manager.check_node_access(_guest(), "node-1", NodePermission.EXECUTE)

    payload = stream.event_history[0].data["access_decision"]
    assert payload["allowed"] is False
    assert payload["user_id"] == "guest-1"


# ---------------------------------------------------------------------------
# check_session_access -- the site MASKED by #2166
# ---------------------------------------------------------------------------


class _RecordingPermissionCheckNode:
    """Stands in for ``PermissionCheckNode`` at the manager's own seam.

    This substitution is deliberate and narrow. ``check_session_access`` calls
    ``PermissionCheckNode.execute(user_context=..., resource_type=...,
    action=...)``, and that node declares none of those three parameters, so it
    raises ``NodeValidationError`` BEFORE control reaches the ``AccessDecision``
    construction at ``:90``. That is issue #2166, which is on hold pending a
    co-owner schema decision and is deliberately NOT fixed here.

    The construction at ``:90`` carries the #2222 defect regardless, and it is
    the thing under test. Substituting at this seam is the only way to reach it
    without implementing #2166; when #2166 is fixed, the real node takes this
    place and these assertions continue to hold.
    """

    def __init__(self, allowed: bool, reason: str):
        self._result = {"allowed": allowed, "reason": reason}
        self.calls: list[dict] = []

    def execute(self, **kwargs):
        self.calls.append(kwargs)
        return dict(self._result)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("allowed", "reason"),
    [(True, "session owner"), (False, "session belongs to another user")],
)
async def test_check_session_access_builds_decision_for_both_poles(allowed, reason):
    """``:90`` must construct an ``AccessDecision``, for allow AND for deny.

    Both poles matter here specifically: the underlying node result is the only
    thing that decides, so a fix that hardcoded either outcome would pass one
    parametrisation and fail the other.
    """
    manager = MiddlewareAccessControlManager(enable_abac=True, enable_audit=False)
    manager.permission_check_node = _RecordingPermissionCheckNode(allowed, reason)

    decision = await manager.check_session_access(_admin(), "session-9", "access")

    assert decision.allowed is allowed
    assert reason in decision.reason
    assert "session-9" in decision.reason
    assert "session.access" in decision.reason


@pytest.mark.asyncio
async def test_check_session_access_emits_event_without_attribute_error():
    """The ``:90`` decision also flows through the emit path that was broken."""
    stream = EventStream()
    manager = MiddlewareAccessControlManager(enable_abac=True, enable_audit=False)
    manager.event_stream = stream
    manager.permission_check_node = _RecordingPermissionCheckNode(True, "owner")

    await manager.check_session_access(_admin(), "session-9", "access")

    payload = stream.event_history[0].data["access_decision"]
    assert payload["resource_id"] == "session-9"
    assert payload["permission"] == "session.access"
    assert payload["user_id"] == "admin-1"


# ---------------------------------------------------------------------------
# authorize_request -- the default-deny branch that could not deny
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_authorize_request_unknown_resource_type_denies():
    """The fail-closed branch must be able to produce a refusal.

    Before the fix it raised ``TypeError``. A caller wrapping authorization in
    ``except Exception`` and treating the error as "not denied" would have
    inverted the decision.
    """
    manager = _rbac_manager()
    middleware = MiddlewareAuthenticationMiddleware(manager)

    decision = await middleware.authorize_request(
        _admin(), "not-a-resource-type", "res-1", "act"
    )

    assert decision.allowed is False
    assert "Unknown resource type" in decision.reason


@pytest.mark.asyncio
async def test_authorize_request_routes_node_checks_to_both_poles():
    """The dispatcher reaches a real decision, not a constant."""
    manager = _rbac_manager()
    middleware = MiddlewareAuthenticationMiddleware(manager)

    granted = await middleware.authorize_request(_admin(), "node", "node-1", "execute")
    denied = await middleware.authorize_request(_guest(), "node", "node-1", "execute")

    assert granted.allowed is True
    assert denied.allowed is False


# ---------------------------------------------------------------------------
# Audit calls -- accepted kwarg set, real AuditEventType member
# ---------------------------------------------------------------------------


class _RecordingAuditNode:
    """Captures the kwargs the manager passes to ``AuditLogNode.execute``.

    The real node writes to a database that is not available in a unit test
    (measured without one: ``NodeExecutionError: ... password authentication
    failed``), so the assertion target is the CALL SHAPE, which is precisely
    what issue #2222 got wrong.
    """

    def __init__(self):
        self.calls: list[dict] = []

    def execute(self, **kwargs):
        self.calls.append(kwargs)
        return {"result": {"logged": True}}


@pytest.mark.asyncio
async def test_workflow_audit_uses_accepted_kwargs_and_real_event_type():
    manager = _rbac_manager()
    manager.enable_audit = True
    manager.audit_node = _RecordingAuditNode()

    await manager.check_workflow_access(
        _admin(), "workflow-1", WorkflowPermission.EXECUTE
    )

    assert len(manager.audit_node.calls) == 1
    call = manager.audit_node.calls[0]

    # The node declares `operation` as its ONLY required parameter and carries
    # the payload in `event_data`. Nothing else may be passed at top level:
    # `Node.execute` silently strips undeclared kwargs.
    assert set(call) == {"operation", "event_data"}
    assert call["operation"] == "log_event"

    event_data = call["event_data"]
    # Would raise ValueError if the event type were invented, as
    # `permission_rule_created` was.
    assert AuditEventType(event_data["event_type"]) is AuditEventType.PERMISSION_CHECKED
    for required in ("event_type", "action", "description"):
        assert required in event_data
    assert event_data["user_id"] == "admin-1"
    assert event_data["resource_id"] == "workflow-1"


@pytest.mark.asyncio
async def test_workflow_audit_event_type_tracks_the_decision():
    """Deny is audited as a denial, not as a generic check."""
    manager = _rbac_manager()
    manager.enable_audit = True
    manager.audit_node = _RecordingAuditNode()

    await manager.check_workflow_access(
        _guest(), "workflow-1", WorkflowPermission.EXECUTE
    )

    event_data = manager.audit_node.calls[0]["event_data"]
    assert AuditEventType(event_data["event_type"]) is AuditEventType.PERMISSION_DENIED


@pytest.mark.asyncio
async def test_permission_rule_audit_uses_accepted_kwargs_and_real_event_type():
    """``permission_rule_created`` is not an ``AuditEventType`` member.

    It survives as the ``action``, which is free text; the ``event_type`` is
    now a real member.
    """
    manager = _rbac_manager()
    manager.enable_audit = True
    manager.audit_node = _RecordingAuditNode()

    result = await manager.create_permission_rule(
        {
            "permission": "api.get.v1.things",
            "resource_id": "/v1/things",
            "resource_type": "api",
            "effect": "allow",
            "role": "admin",
        },
        created_by="admin-1",
    )
    assert result["success"] is True

    call = manager.audit_node.calls[0]
    assert set(call) == {"operation", "event_data"}
    assert call["operation"] == "log_event"

    event_data = call["event_data"]
    assert (
        AuditEventType(event_data["event_type"]) is AuditEventType.SYSTEM_CONFIG_CHANGED
    )
    assert event_data["action"] == "permission_rule_created"
    assert event_data["metadata"]["rule_id"] == result["rule_id"]


@pytest.mark.asyncio
async def test_audit_failure_does_not_break_the_authorization_decision(caplog):
    """A failing audit sink must not convert a computed DENY into an exception.

    It must also not vanish silently -- an audit trail that drops events
    quietly is the #2057 defect this module was already repaired for.
    """

    class _ExplodingAuditNode:
        def execute(self, **kwargs):
            raise RuntimeError("audit database unreachable")

    manager = _rbac_manager()
    manager.enable_audit = True
    manager.audit_node = _ExplodingAuditNode()

    with caplog.at_level(logging.WARNING):
        decision = await manager.check_workflow_access(
            _guest(), "workflow-1", WorkflowPermission.EXECUTE
        )

    assert decision.allowed is False
    assert "audit_write_failed" in caplog.text


# ---------------------------------------------------------------------------
# Structural pin -- the rejected kwargs cannot come back
# ---------------------------------------------------------------------------


def _module_tree() -> ast.Module:
    return ast.parse(MODULE_PATH.read_text(encoding="utf-8"))


def test_no_access_decision_construction_passes_rejected_kwargs():
    """AST pin over live code.

    A behavioural test cannot cover a construction site that no shipped manager
    reaches -- ``:152`` is dead on both managers today, and was still wrong.
    The fix commentary necessarily NAMES these fields, so this walks the AST
    rather than grepping text.
    """
    offenders = []
    for node in ast.walk(_module_tree()):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name != "AccessDecision":
            continue
        for keyword in node.keywords:
            if keyword.arg in REJECTED_FIELDS:
                offenders.append((node.lineno, keyword.arg))

    assert offenders == [], (
        f"AccessDecision constructed with fields it does not declare: {offenders}. "
        f"AccessDecision has only allowed/reason/applied_rules/conditions_met/"
        f"masked_fields/redirect_node."
    )


def test_no_rejected_attribute_is_read_off_a_decision():
    """``decision.user_id`` and friends raise ``AttributeError`` at runtime."""
    offenders = []
    for node in ast.walk(_module_tree()):
        if not isinstance(node, ast.Attribute):
            continue
        value = node.value
        if isinstance(value, ast.Name) and value.id == "decision":
            if node.attr in REJECTED_FIELDS:
                offenders.append((node.lineno, node.attr))

    assert (
        offenders == []
    ), f"Read of a field AccessDecision does not have: {offenders}."


def test_every_audit_event_type_named_in_the_module_is_a_real_member():
    """Guards the ``permission_rule_created`` class of defect.

    ``AuditLogNode`` resolves the event type through ``AuditEventType(...)`` at
    log time, so an invented name fails deep inside the node, only when audit
    is enabled AND a database is reachable.
    """
    valid = {member.value for member in AuditEventType}
    offenders = []
    for node in ast.walk(_module_tree()):
        if not isinstance(node, ast.Attribute):
            continue
        if isinstance(node.value, ast.Name) and node.value.id == "AuditEventType":
            if node.attr not in {m.name for m in AuditEventType}:
                offenders.append((node.lineno, node.attr))

    assert offenders == [], f"Not AuditEventType members: {offenders}"
    assert "permission_rule_created" not in valid
