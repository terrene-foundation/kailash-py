# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #2057 -- four dead attribute guards.

Each guard probed an attribute name that is defined NOWHERE, so the branch it
protected was structurally unreachable. Measured before the fix, not inferred:

* ``middleware/auth/access_control.py`` probed ``add_permission_rule`` (0
  definitions repo-wide) and then emitted ``permission_rule_created`` to the
  audit log and returned ``{"success": True}`` from OUTSIDE the guard -- an
  audit trail asserting a permission rule that was never registered. The same
  method also constructed ``PermissionRule(resource_pattern=...)``, a field the
  dataclass does not have, so it raised ``TypeError`` before it ever reached
  the guard::

      TypeError: PermissionRule.__init__() got an unexpected keyword argument
                 'resource_pattern'

* ``nodes/data/workflow_connection_pool.py`` guarded on
  ``hasattr(self.runtime, ...)``. ``WorkflowConnectionPool`` has no ``runtime``
  attribute at all, so the read raised and the enclosing ``except Exception``
  returned an error dict on EVERY call::

      _start_monitoring_dashboard() ->
          {'error': "'WorkflowConnectionPool' object has no attribute 'runtime'"}

* ``nexus/core.py`` stopped ``self._ws_server`` -- never assigned anywhere (the
  real attribute is ``_ws_transport``) -- and did so from an ``elif`` chain, so
  even a correct name would have been skipped whenever an MCP channel was live.

* ``nexus/auth/tenant/resolver.py`` OR-ed in a ``token_claims`` fallback
  "for compatibility". Nothing has ever set that name; only ``token_payload``
  is assigned (``nexus/auth/jwt.py:175`` for API keys, ``:219`` for JWTs).

The structural pins below are deliberately source-level: a behavioural test
cannot distinguish "the guard is correct" from "the guard is always False", so
reintroducing a dead name has to be caught by looking at the code.
"""

from __future__ import annotations

import ast
import asyncio
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _strip_comments_and_docstrings(source: str) -> str:
    """Return ``source`` with comments and string literals removed.

    The fix commentary necessarily *names* the dead attributes it removed, so a
    naive substring search would match the explanation rather than live code.
    """
    tree = ast.parse(source)
    spans: list[tuple[int, int, int, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.end_lineno is not None and node.end_col_offset is not None:
                spans.append(
                    (node.lineno, node.col_offset, node.end_lineno, node.end_col_offset)
                )

    lines = source.splitlines()
    for start_line, start_col, end_line, end_col in spans:
        for lineno in range(start_line, end_line + 1):
            line = lines[lineno - 1]
            lo = start_col if lineno == start_line else 0
            hi = end_col if lineno == end_line else len(line)
            lines[lineno - 1] = line[:lo] + " " * (hi - lo) + line[hi:]

    # Comments survive AST parsing, so strip them lexically afterwards.
    return "\n".join(re.sub(r"#.*$", "", line) for line in lines)


# ---------------------------------------------------------------------------
# Control for the source-scanning instrument used by the structural pins.
#
# instrument-discipline MUST-3: an empty result from a matcher never shown to
# fire here is not evidence. These two tests establish that the scrubber both
# removes commentary AND still reports genuine code references.
# ---------------------------------------------------------------------------


def test_control_scrubber_removes_commentary_but_keeps_code():
    """The instrument the structural pins rely on must discriminate."""
    source = (
        "# mentions _ws_server in a comment\n"
        'DOC = """mentions _ws_server in a docstring"""\n'
        "def f(self):\n"
        "    return self._ws_server\n"
    )
    scrubbed = _strip_comments_and_docstrings(source)
    assert scrubbed.count("_ws_server") == 1, scrubbed

    commentary_only = (
        "# mentions _ws_server in a comment\n"
        'DOC = """mentions _ws_server in a docstring"""\n'
    )
    assert "_ws_server" not in _strip_comments_and_docstrings(commentary_only)


# ---------------------------------------------------------------------------
# Site 1 -- middleware/auth/access_control.py: falsified audit of a security
# control.
# ---------------------------------------------------------------------------


class _RecordingAudit:
    """Stand-in for the audit node; records what would have been written."""

    def __init__(self):
        self.calls: list[dict] = []

    def execute(self, **kwargs):
        self.calls.append(kwargs)
        return {"logged": True}


class _ManagerWithoutAddRule:
    """An access manager that cannot register rules."""


def _manager(audit):
    from kailash.middleware.auth.access_control import MiddlewareAccessControlManager

    mgr = MiddlewareAccessControlManager(enable_audit=True)
    mgr.audit_node = audit
    return mgr


def test_create_permission_rule_actually_registers_the_rule():
    audit = _RecordingAudit()
    mgr = _manager(audit)

    result = asyncio.run(
        mgr.create_permission_rule(
            {
                "permission": "api.get.reports",
                "resource_pattern": "/reports",
                "role": "analyst",
            },
            "admin",
        )
    )

    registered = mgr.access_manager.rules
    assert len(registered) == 1, "rule was not registered on the access manager"
    assert result["success"] is True
    # The id must come from the registration, not from hash(str(rule)) (#2057).
    assert result["rule_id"] == registered[0].id
    assert registered[0].resource_id == "/reports"
    assert registered[0].created_by == "admin"


def test_create_permission_rule_audits_only_after_registration():
    audit = _RecordingAudit()
    mgr = _manager(audit)

    asyncio.run(
        mgr.create_permission_rule(
            {"permission": "api.get.reports", "resource_id": "/reports"}, "admin"
        )
    )

    assert len(audit.calls) == 1
    assert audit.calls[0]["event_type"] == "permission_rule_created"
    # The audit record must reference the rule that actually exists.
    assert audit.calls[0]["rule_id"] == mgr.access_manager.rules[0].id


def test_unregisterable_rule_raises_and_writes_no_audit_event():
    """The core of #2057: no fake success, no falsified audit trail."""
    from kailash.sdk_exceptions import KailashConfigError

    audit = _RecordingAudit()
    mgr = _manager(audit)
    mgr.access_manager = _ManagerWithoutAddRule()

    with pytest.raises(KailashConfigError) as excinfo:
        asyncio.run(
            mgr.create_permission_rule(
                {"permission": "api.get.reports", "resource_id": "/reports"}, "admin"
            )
        )

    assert "add_rule" in str(excinfo.value)
    assert audit.calls == [], "audited a rule that was never registered"


@pytest.mark.parametrize(
    "rule_data",
    [
        {"resource_id": "/reports"},  # no permission
        {"permission": "api.get.reports"},  # no resource
    ],
)
def test_rule_that_could_match_nothing_is_rejected(rule_data):
    """A rule missing permission or resource matches no check -- fail closed."""
    audit = _RecordingAudit()
    mgr = _manager(audit)

    with pytest.raises(ValueError):
        asyncio.run(mgr.create_permission_rule(rule_data, "admin"))

    assert mgr.access_manager.rules == []
    assert audit.calls == []


def test_add_permission_rule_has_no_definition_anywhere():
    """Pin the premise: the old guard could never have fired.

    If someone later implements ``add_permission_rule``, this test reds and the
    fix above should be revisited rather than silently diverging.
    """
    hits = []
    for root in (REPO_ROOT / "src", REPO_ROOT / "packages"):
        for path in root.rglob("*.py"):
            if "def add_permission_rule" in path.read_text(encoding="utf-8"):
                hits.append(str(path))
    assert hits == [], f"add_permission_rule now exists: {hits}"


def test_effective_permissions_expose_real_permission_rule_fields():
    """``rule.resource_pattern`` does not exist; reading it raised."""
    from kailash.access_control import (
        NodePermission,
        PermissionEffect,
        PermissionRule,
        UserContext,
    )

    rules = [
        PermissionRule(
            id="a",
            resource_type="node",
            resource_id="n1",
            permission=NodePermission.READ_OUTPUT,
            effect=PermissionEffect.ALLOW,
        ),
        PermissionRule(
            id="b",
            resource_type="api",
            resource_id="/x",
            permission="api.get.x",  # middleware API rules carry str permissions
            effect=PermissionEffect.DENY,
        ),
    ]

    class _Manager:
        def get_user_permissions(self, _user):
            return rules

    mgr = _manager(_RecordingAudit())
    mgr.access_manager = _Manager()
    user = UserContext(user_id="u1", tenant_id="t", email="e@x.y", roles=[])

    rows = asyncio.run(mgr.get_user_effective_permissions(user))

    assert [row["resource_id"] for row in rows] == ["n1", "/x"]
    assert [row["resource_type"] for row in rows] == ["node", "api"]
    # Dual-shape permission is dispatched on type, not probed for `.value`.
    assert [row["permission"] for row in rows] == ["read_output", "api.get.x"]
    assert [row["effect"] for row in rows] == ["allow", "deny"]
    assert all("resource_pattern" not in row for row in rows)


# ---------------------------------------------------------------------------
# Site 2 -- nodes/data/workflow_connection_pool.py: monitoring collected
# nothing.
# ---------------------------------------------------------------------------


class _FakeDashboard:
    """Avoids binding a real socket in a unit test."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.started = 0
        self.stopped = 0

    async def start(self):
        self.started += 1

    async def stop(self):
        self.stopped += 1


@pytest.fixture
def pool_module():
    from kailash.nodes.data import workflow_connection_pool as module

    original = module._shared_dashboard
    module._shared_dashboard = None
    try:
        yield module
    finally:
        module._shared_dashboard = original


@pytest.fixture
def pool(pool_module):
    from kailash.nodes.data.workflow_connection_pool import WorkflowConnectionPool

    return WorkflowConnectionPool(
        name="issue_2057_pool",
        database_type="sqlite",
        database=":memory:",
        min_connections=1,
        max_connections=2,
        enable_monitoring=True,
        dashboard_require_auth=False,
    )


def test_pool_has_no_runtime_attribute():
    """Pin the premise: every `self.runtime` guard read a missing attribute."""
    from kailash.nodes.data.workflow_connection_pool import WorkflowConnectionPool

    instance = WorkflowConnectionPool(
        name="probe",
        database_type="sqlite",
        database=":memory:",
        min_connections=1,
        max_connections=2,
    )
    assert not hasattr(instance, "runtime")


def test_pool_module_no_longer_reads_self_runtime():
    from kailash.nodes.data import workflow_connection_pool as module

    scrubbed = _strip_comments_and_docstrings(
        Path(module.__file__).read_text(encoding="utf-8")
    )
    assert "self.runtime" not in scrubbed


def test_monitoring_registers_the_pool_collector(monkeypatch, pool, pool_module):
    """`enable_monitoring=True` used to register nothing at this surface."""
    import kailash.nodes.monitoring.connection_dashboard as dash_module
    from kailash.core.monitoring import get_metrics_aggregator

    monkeypatch.setattr(dash_module, "ConnectionDashboardNode", _FakeDashboard)

    aggregator = get_metrics_aggregator()
    aggregator._collectors.pop(pool.metrics_collector.pool_name, None)

    result = asyncio.run(pool._start_monitoring_dashboard())

    assert result["status"] == "started"
    assert pool.metrics_collector.pool_name in aggregator._collectors
    assert (
        aggregator._collectors[pool.metrics_collector.pool_name]
        is pool.metrics_collector
    )


def test_metrics_aggregator_is_a_process_wide_singleton():
    from kailash.core.monitoring import MetricsAggregator, get_metrics_aggregator

    first = get_metrics_aggregator()
    assert isinstance(first, MetricsAggregator)
    assert get_metrics_aggregator() is first


def test_dashboard_start_stop_lifecycle(monkeypatch, pool, pool_module):
    import kailash.nodes.monitoring.connection_dashboard as dash_module

    monkeypatch.setattr(dash_module, "ConnectionDashboardNode", _FakeDashboard)

    assert asyncio.run(pool._start_monitoring_dashboard())["status"] == "started"
    dashboard = pool_module._shared_dashboard
    assert dashboard.started == 1

    # Second start shares the running dashboard rather than rebuilding it --
    # the old `not hasattr(self.runtime, ...)` guard rebuilt on every call.
    assert (
        asyncio.run(pool._start_monitoring_dashboard())["status"] == "already_running"
    )
    assert dashboard.started == 1

    assert asyncio.run(pool._stop_monitoring_dashboard())["status"] == "stopped"
    assert dashboard.stopped == 1
    assert asyncio.run(pool._stop_monitoring_dashboard())["status"] == "not_running"


def test_failed_dashboard_start_is_not_reported_as_already_running(
    monkeypatch, pool, pool_module
):
    """A failed start must not leave a claim behind -- that is fake success."""
    import kailash.nodes.monitoring.connection_dashboard as dash_module

    class _FailingDashboard(_FakeDashboard):
        async def start(self):
            raise RuntimeError("port in use")

    monkeypatch.setattr(dash_module, "ConnectionDashboardNode", _FailingDashboard)

    first = asyncio.run(pool._start_monitoring_dashboard())
    assert "error" in first
    assert pool_module._shared_dashboard is None

    monkeypatch.setattr(dash_module, "ConnectionDashboardNode", _FakeDashboard)
    assert asyncio.run(pool._start_monitoring_dashboard())["status"] == "started"


# ---------------------------------------------------------------------------
# Site 3 -- nexus/core.py: the websocket shutdown branch never ran.
# ---------------------------------------------------------------------------


class _StubTransport:
    def __init__(self):
        self.stopped = 0

    async def stop(self):
        self.stopped += 1


def _nexus_stop_double(**overrides):
    """A minimal stand-in carrying only the attributes ``Nexus.stop`` touches."""
    fake = SimpleNamespace(
        _running=True,
        _http_transport=SimpleNamespace(gateway=None),
        _mcp_channel=None,
        _ws_transport=None,
        _call_shutdown_hooks=lambda: None,
        close=lambda: None,
    )
    for key, value in overrides.items():
        setattr(fake, key, value)
    return fake


def test_nexus_core_no_longer_references_ws_server():
    import nexus.core as core

    scrubbed = _strip_comments_and_docstrings(
        Path(core.__file__).read_text(encoding="utf-8")
    )
    assert "_ws_server" not in scrubbed


def test_ws_server_is_assigned_nowhere():
    """Pin the premise: the branch could never have fired."""
    hits = []
    for root in (REPO_ROOT / "src", REPO_ROOT / "packages"):
        for path in root.rglob("*.py"):
            if re.search(r"\b_ws_server\s*=", path.read_text(encoding="utf-8")):
                hits.append(str(path))
    assert hits == [], f"_ws_server is now assigned: {hits}"


def test_stop_stops_the_websocket_transport():
    from nexus.core import Nexus

    transport = _StubTransport()
    Nexus.stop(_nexus_stop_double(_ws_transport=transport))
    assert transport.stopped == 1


def test_websocket_transport_stops_even_when_an_mcp_channel_is_running():
    """The old branch sat in an ``elif`` chain behind the MCP channel."""
    from nexus.core import Nexus

    transport = _StubTransport()
    channel = _StubTransport()
    Nexus.stop(_nexus_stop_double(_ws_transport=transport, _mcp_channel=channel))

    assert channel.stopped == 1
    assert transport.stopped == 1, "websocket transport was skipped again"


# ---------------------------------------------------------------------------
# Site 4 -- nexus/auth/tenant/resolver.py: dead token_claims alias.
# ---------------------------------------------------------------------------


def _request(state_kwargs, headers=None):
    return SimpleNamespace(
        headers=headers or {},
        state=SimpleNamespace(**state_kwargs),
    )


def _resolver():
    from kailash.trust.auth.context import TenantConfig
    from nexus.auth.tenant.resolver import TenantResolver

    return TenantResolver(
        TenantConfig(
            fallback_to_user_org=False,
            validate_tenant_exists=False,
            validate_tenant_active=False,
        )
    )


def test_tenant_resolves_from_token_payload():
    resolver = _resolver()
    info = asyncio.run(
        resolver.resolve(_request({"token_payload": {"tenant_id": "acme"}}))
    )
    assert info is not None
    assert info.tenant_id == "acme"


def test_token_claims_is_not_an_authenticated_source():
    """Nothing sets ``token_claims``; it must not resolve a tenant."""
    resolver = _resolver()
    assert (
        asyncio.run(resolver.resolve(_request({"token_claims": {"tenant_id": "acme"}})))
        is None
    )


def test_token_claims_is_assigned_nowhere():
    hits = []
    for root in (REPO_ROOT / "src", REPO_ROOT / "packages"):
        for path in root.rglob("*.py"):
            if re.search(
                r"\.token_claims\s*=|\btoken_claims\s*=",
                path.read_text(encoding="utf-8"),
            ):
                hits.append(str(path))
    assert hits == [], f"token_claims is now assigned: {hits}"
