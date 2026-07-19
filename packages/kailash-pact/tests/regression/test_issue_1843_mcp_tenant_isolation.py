# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #1843 -- first-class tenant isolation for MCP
governance.

Before this fix, MCP governance had NO tenant isolation: a tenant-A caller
could reach tenant-B's tools/resources, and ``resources/read`` had NO
governance layer at all (not even default-deny). This is the byte-NEUTRAL
fix landed here (no serialized bytes change on the wire envelope), mirroring
the Rust SDK's approach:

* Tenant rides the existing free-form ``metadata["tenant_id"]`` channel on
  ``McpActionContext`` / ``McpResourceContext`` -- NO new first-class
  serialized field was added to either envelope.
* The caller identity (``McpCallerIdentity``, new, deliberately NOT
  serialized -- no ``to_dict``/``from_dict``) carries a trusted ``tenant``
  that OVERWRITES any self-asserted ``metadata["tenant_id"]`` (impersonation
  defeat).
* ``McpGovernanceConfig`` gains an ADDITIVE, OPTIONAL ``tenant_grants`` map.
  Empty (the default) means tenant isolation is OFF -- byte-identical to the
  pre-existing behavior for BOTH tools/call and resources/read.
* A NEW enforcement layer scopes BOTH ``tools/call`` (keyed on tool name) AND
  ``resources/read`` (keyed on URI) through ONE shared restrictiveness
  function (``McpGovernanceEnforcer._tenant_isolation_decision`` /
  ``_tenant_grant_permits``), fail-closed on an absent, unrecognized, or
  ungranted tenant.
* Rate windows are re-keyed on ``(tenant, agent_id, tool)`` when a tenant
  resolves; the pre-existing ``"agent_id:tool_name"`` key format is preserved
  BYTE-FOR-BYTE when tenant isolation is off (or no tenant resolves).

Byte-diff verdict (issue #1843 acceptance criterion): the Rust SDK
deliberately did NOT add a first-class serialized ``tenant_id`` FIELD to its
``McpActionContext`` equivalent -- it kept the envelope frozen and routed
tenant through the existing free-form metadata channel instead. This Python
port makes the SAME choice for the SAME reason: adding a first-class
serialized field would be a byte-CHANGING wire-envelope change requiring
cross-SDK lockstep (cross-sdk-inspection.md Rule 4b); the byte-neutral
metadata-channel form needs no such lockstep. The field form is NOT adopted
here; adopt it only if ecosystems later converge on that shape.

Fail-closed semantics (pact-governance.md Rule 4): absent, unrecognized, or
ungranted tenant BLOCKS. Behavioral tests: each calls check_tool_call /
check_resource_read / middleware invoke methods and asserts the resulting
decision -- never grep over source.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta

import pytest

from pact.mcp.enforcer import McpGovernanceEnforcer
from pact.mcp.middleware import McpGovernanceMiddleware
from pact.mcp.types import (
    DefaultPolicy,
    McpActionContext,
    McpCallerIdentity,
    McpGovernanceConfig,
    McpResourceContext,
    McpTenantGrant,
    McpToolPolicy,
)

# Fixed base instant so every test is fully deterministic (no wall-clock).
_T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _config(
    tenant_grants: dict[str, McpTenantGrant] | None = None,
    tool_policies: dict[str, McpToolPolicy] | None = None,
    default_policy: DefaultPolicy = DefaultPolicy.ALLOW,
) -> McpGovernanceConfig:
    """Default-ALLOW isolates the tenant-isolation gate under test from the
    Step-1 default-deny registration gate; tests that need to prove ordering
    against a registered tool's policy pass explicit tool_policies."""
    return McpGovernanceConfig(
        default_policy=default_policy,
        tool_policies=tool_policies or {},
        tenant_grants=tenant_grants or {},
        audit_enabled=False,
    )


def _tool_ctx(
    tool_name: str = "search",
    agent_id: str = "agent-1",
    metadata: dict | None = None,
    timestamp: datetime | None = None,
) -> McpActionContext:
    return McpActionContext(
        tool_name=tool_name,
        agent_id=agent_id,
        metadata=metadata or {},
        timestamp=timestamp or _T0,
    )


def _resource_ctx(
    uri: str = "resource://docs/1",
    agent_id: str = "agent-1",
    metadata: dict | None = None,
    timestamp: datetime | None = None,
) -> McpResourceContext:
    return McpResourceContext(
        uri=uri,
        agent_id=agent_id,
        metadata=metadata or {},
        timestamp=timestamp or _T0,
    )


# ---------------------------------------------------------------------------
# Isolation OFF (empty tenant_grants) -- byte-identical backward compat
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestIsolationOffBackwardCompat:
    """Empty tenant_grants (the default) is a byte-neutral no-op on both
    tools/call and resources/read."""

    def test_tool_call_auto_approved_with_no_tenant_grants(self) -> None:
        enf = McpGovernanceEnforcer(_config())
        decision = enf.check_tool_call(_tool_ctx())
        assert decision.level == "auto_approved"
        assert decision.allowed is True

    def test_resource_read_auto_approved_with_no_tenant_grants(self) -> None:
        """resources/read had NO governance layer before #1843; with
        isolation off it stays unconditionally auto_approved."""
        enf = McpGovernanceEnforcer(_config())
        decision = enf.check_resource_read(_resource_ctx())
        assert decision.level == "auto_approved"
        assert decision.allowed is True
        assert decision.resource_uri == "resource://docs/1"

    def test_tool_call_ignores_caller_identity_when_isolation_off(self) -> None:
        """Even a caller_identity with NO tenant grant is irrelevant when
        tenant_grants is empty -- the tenant gate is skipped entirely."""
        enf = McpGovernanceEnforcer(_config())
        identity = McpCallerIdentity(agent_id="agent-1", tenant="unknown-tenant")
        decision = enf.check_tool_call(_tool_ctx(), caller_identity=identity)
        assert decision.level == "auto_approved"

    def test_rate_tracker_key_format_unchanged_when_isolation_off(self) -> None:
        """The pre-existing "agent_id:tool_name" rate-tracker key format is
        preserved BYTE-FOR-BYTE when isolation is off (no tenant prefix)."""
        policy = McpToolPolicy(tool_name="t", rate_limit=5, max_cost=None)
        enf = McpGovernanceEnforcer(_config(tool_policies={"t": policy}))
        enf.check_tool_call(_tool_ctx(tool_name="t", agent_id="agent-1"))
        assert "agent-1:t" in enf._rate_tracker
        assert not any(":" in k and k.count(":") > 1 for k in enf._rate_tracker)

    def test_rate_tracker_key_format_unchanged_with_caller_identity_but_no_tenant(
        self,
    ) -> None:
        """A caller_identity with tenant=None still preserves the old key
        format even when passed explicitly."""
        policy = McpToolPolicy(tool_name="t", rate_limit=5, max_cost=None)
        enf = McpGovernanceEnforcer(_config(tool_policies={"t": policy}))
        identity = McpCallerIdentity(agent_id="agent-1", tenant=None)
        enf.check_tool_call(
            _tool_ctx(tool_name="t", agent_id="agent-1"), caller_identity=identity
        )
        assert "agent-1:t" in enf._rate_tracker


# ---------------------------------------------------------------------------
# Cross-tenant denial (isolation ON) -- tool AND resource
# ---------------------------------------------------------------------------


def _two_tenant_grants() -> dict[str, McpTenantGrant]:
    return {
        "tenant-a": McpTenantGrant(
            tenant="tenant-a",
            tools=frozenset({"tool-a"}),
            resources=frozenset({"resource://tenant-a/doc"}),
        ),
        "tenant-b": McpTenantGrant(
            tenant="tenant-b",
            tools=frozenset({"tool-b"}),
            resources=frozenset({"resource://tenant-b/doc"}),
        ),
    }


@pytest.mark.regression
@pytest.mark.security
class TestCrossTenantDenied:
    """tenant-A is denied tenant-B's tool AND tenant-B's resource (issue
    #1843 acceptance criterion), through the SAME shared restrictiveness
    function on both surfaces."""

    def test_tenant_a_denied_tenant_b_tool(self) -> None:
        enf = McpGovernanceEnforcer(_config(tenant_grants=_two_tenant_grants()))
        identity = McpCallerIdentity(agent_id="agent-1", tenant="tenant-a")
        decision = enf.check_tool_call(
            _tool_ctx(tool_name="tool-b"), caller_identity=identity
        )
        assert decision.level == "blocked"
        assert decision.allowed is False
        assert "tenant-a" in decision.reason
        assert "tool-b" in decision.reason

    def test_tenant_a_denied_tenant_b_resource(self) -> None:
        enf = McpGovernanceEnforcer(_config(tenant_grants=_two_tenant_grants()))
        identity = McpCallerIdentity(agent_id="agent-1", tenant="tenant-a")
        decision = enf.check_resource_read(
            _resource_ctx(uri="resource://tenant-b/doc"), caller_identity=identity
        )
        assert decision.level == "blocked"
        assert decision.allowed is False
        assert decision.resource_uri == "resource://tenant-b/doc"
        assert "tenant-a" in decision.reason

    def test_tenant_a_granted_own_tool(self) -> None:
        enf = McpGovernanceEnforcer(_config(tenant_grants=_two_tenant_grants()))
        identity = McpCallerIdentity(agent_id="agent-1", tenant="tenant-a")
        decision = enf.check_tool_call(
            _tool_ctx(tool_name="tool-a"), caller_identity=identity
        )
        assert decision.level == "auto_approved"

    def test_tenant_a_granted_own_resource(self) -> None:
        enf = McpGovernanceEnforcer(_config(tenant_grants=_two_tenant_grants()))
        identity = McpCallerIdentity(agent_id="agent-1", tenant="tenant-a")
        decision = enf.check_resource_read(
            _resource_ctx(uri="resource://tenant-a/doc"), caller_identity=identity
        )
        assert decision.level == "auto_approved"


# ---------------------------------------------------------------------------
# Fail-closed on absent/unknown/ungranted tenant
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.security
class TestFailClosed:
    """Fail-closed on absent, unrecognized, or ungranted tenant (both
    surfaces), per pact-governance.md Rule 4."""

    def test_absent_tenant_blocks_tool_call(self) -> None:
        """No caller_identity, no metadata tenant_id -> BLOCKED."""
        enf = McpGovernanceEnforcer(_config(tenant_grants=_two_tenant_grants()))
        decision = enf.check_tool_call(_tool_ctx(tool_name="tool-a"))
        assert decision.level == "blocked"
        assert "no tenant was declared" in decision.reason

    def test_absent_tenant_blocks_resource_read(self) -> None:
        enf = McpGovernanceEnforcer(_config(tenant_grants=_two_tenant_grants()))
        decision = enf.check_resource_read(_resource_ctx(uri="resource://tenant-a/doc"))
        assert decision.level == "blocked"
        assert "no tenant was declared" in decision.reason

    def test_unknown_tenant_blocks_tool_call(self) -> None:
        enf = McpGovernanceEnforcer(_config(tenant_grants=_two_tenant_grants()))
        identity = McpCallerIdentity(agent_id="agent-1", tenant="tenant-x")
        decision = enf.check_tool_call(
            _tool_ctx(tool_name="tool-a"), caller_identity=identity
        )
        assert decision.level == "blocked"
        assert "not a recognized tenant" in decision.reason

    def test_ungranted_tool_blocks_even_for_known_tenant(self) -> None:
        """tenant-a is a known/recognized tenant but is NOT granted
        "tool-b" -- distinct fail-closed path from an unknown tenant."""
        enf = McpGovernanceEnforcer(_config(tenant_grants=_two_tenant_grants()))
        identity = McpCallerIdentity(agent_id="agent-1", tenant="tenant-a")
        decision = enf.check_tool_call(
            _tool_ctx(tool_name="tool-b"), caller_identity=identity
        )
        assert decision.level == "blocked"
        assert "not granted access" in decision.reason

    def test_tenant_isolation_evaluated_before_clearance_and_cost(self) -> None:
        """Tenant isolation runs at Step 0 -- BEFORE registration and
        cost/args/clearance (Steps 1-5). A wrong-tenant caller with
        otherwise-perfect clearance and cost is still BLOCKED on the tenant
        reason, not clearance/cost."""
        policy = McpToolPolicy(
            tool_name="tool-a",
            max_cost=100.0,
            clearance_required="secret",
        )
        enf = McpGovernanceEnforcer(
            _config(
                tenant_grants=_two_tenant_grants(),
                tool_policies={"tool-a": policy},
                default_policy=DefaultPolicy.DENY,
            )
        )
        identity = McpCallerIdentity(agent_id="agent-1", tenant="tenant-b")
        ctx = McpActionContext(
            tool_name="tool-a",
            agent_id="agent-1",
            cost_estimate=1.0,
            caller_clearance="top_secret",
            timestamp=_T0,
        )
        decision = enf.check_tool_call(ctx, caller_identity=identity)
        assert decision.level == "blocked"
        assert "tenant" in decision.reason.lower()
        assert "clearance" not in decision.reason.lower()
        assert "cost" not in decision.reason.lower()


# ---------------------------------------------------------------------------
# Impersonation defeat: trusted caller_identity overwrites self-asserted
# metadata["tenant_id"]
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.security
class TestImpersonationDefeat:
    """A caller cannot widen its access by asserting a different tenant in
    the request body -- the trusted caller_identity always wins."""

    def test_caller_identity_overwrites_self_asserted_metadata_tenant(self) -> None:
        """Body claims tenant-b (which owns "tool-b"); the TRUSTED identity
        says tenant-a. The call MUST be evaluated as tenant-a and BLOCKED."""
        enf = McpGovernanceEnforcer(_config(tenant_grants=_two_tenant_grants()))
        identity = McpCallerIdentity(agent_id="agent-1", tenant="tenant-a")
        ctx = _tool_ctx(tool_name="tool-b", metadata={"tenant_id": "tenant-b"})
        decision = enf.check_tool_call(ctx, caller_identity=identity)
        assert decision.level == "blocked"
        # The reason cites the TRUSTED tenant (tenant-a), proving the
        # self-asserted tenant-b in metadata was overwritten, not honored.
        assert "tenant-a" in decision.reason
        assert "tenant-b" not in decision.reason

    def test_caller_identity_overwrite_also_defeats_resource_impersonation(
        self,
    ) -> None:
        enf = McpGovernanceEnforcer(_config(tenant_grants=_two_tenant_grants()))
        identity = McpCallerIdentity(agent_id="agent-1", tenant="tenant-a")
        ctx = _resource_ctx(
            uri="resource://tenant-b/doc", metadata={"tenant_id": "tenant-b"}
        )
        decision = enf.check_resource_read(ctx, caller_identity=identity)
        assert decision.level == "blocked"
        assert "tenant-a" in decision.reason

    def test_metadata_tenant_id_fallback_when_no_caller_identity_supplied(
        self,
    ) -> None:
        """When no trusted identity is supplied at all, the self-asserted
        metadata["tenant_id"] is consulted as a (weaker) fallback."""
        enf = McpGovernanceEnforcer(_config(tenant_grants=_two_tenant_grants()))
        ctx = _tool_ctx(tool_name="tool-a", metadata={"tenant_id": "tenant-a"})
        decision = enf.check_tool_call(ctx)
        assert decision.level == "auto_approved"

    def test_metadata_tenant_id_fallback_still_fails_closed_if_ungranted(
        self,
    ) -> None:
        enf = McpGovernanceEnforcer(_config(tenant_grants=_two_tenant_grants()))
        ctx = _tool_ctx(tool_name="tool-b", metadata={"tenant_id": "tenant-a"})
        decision = enf.check_tool_call(ctx)
        assert decision.level == "blocked"

    def test_caller_identity_with_no_tenant_falls_back_to_metadata(self) -> None:
        """caller_identity is supplied but its own tenant is None -- the
        metadata fallback still applies (not a hard override to "no tenant")."""
        enf = McpGovernanceEnforcer(_config(tenant_grants=_two_tenant_grants()))
        identity = McpCallerIdentity(agent_id="agent-1", tenant=None)
        ctx = _tool_ctx(tool_name="tool-a", metadata={"tenant_id": "tenant-a"})
        decision = enf.check_tool_call(ctx, caller_identity=identity)
        assert decision.level == "auto_approved"


# ---------------------------------------------------------------------------
# require_caller_identity: strict mode disables the metadata["tenant_id"]
# fallback entirely (security-reviewer HIGH-1 fix) -- deployments with no
# transport-level identity resolution can opt into a REAL isolation
# guarantee instead of the (documented, attacker-controlled) fallback.
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.security
class TestRequireCallerIdentity:
    """McpGovernanceConfig.require_caller_identity=True disables the
    self-asserted metadata["tenant_id"] fallback -- an absent (or
    tenant-less) trusted identity fails closed instead of trusting the body."""

    def _strict_config(self) -> McpGovernanceConfig:
        return McpGovernanceConfig(
            default_policy=DefaultPolicy.ALLOW,
            tenant_grants=_two_tenant_grants(),
            require_caller_identity=True,
            audit_enabled=False,
        )

    def test_metadata_fallback_disabled_blocks_without_caller_identity(self) -> None:
        """The exact HIGH-1 bypass: no caller_identity + a self-asserted
        metadata["tenant_id"] that WOULD otherwise be honored. In strict
        mode this is BLOCKED -- the metadata channel is never consulted."""
        enf = McpGovernanceEnforcer(self._strict_config())
        ctx = _tool_ctx(tool_name="tool-a", metadata={"tenant_id": "tenant-a"})
        decision = enf.check_tool_call(ctx)
        assert decision.level == "blocked"
        assert "no tenant was declared" in decision.reason

    def test_metadata_fallback_disabled_blocks_when_identity_tenant_is_none(
        self,
    ) -> None:
        """A caller_identity IS supplied but its own tenant is None -- strict
        mode does NOT fall back to metadata (unlike the default/non-strict
        behavior proven in TestImpersonationDefeat)."""
        enf = McpGovernanceEnforcer(self._strict_config())
        identity = McpCallerIdentity(agent_id="agent-1", tenant=None)
        ctx = _tool_ctx(tool_name="tool-a", metadata={"tenant_id": "tenant-a"})
        decision = enf.check_tool_call(ctx, caller_identity=identity)
        assert decision.level == "blocked"

    def test_metadata_fallback_disabled_still_honors_trusted_identity(self) -> None:
        """Strict mode does not break the trusted-identity path -- a genuine
        caller_identity.tenant is honored exactly as in non-strict mode."""
        enf = McpGovernanceEnforcer(self._strict_config())
        identity = McpCallerIdentity(agent_id="agent-1", tenant="tenant-a")
        decision = enf.check_tool_call(
            _tool_ctx(tool_name="tool-a"), caller_identity=identity
        )
        assert decision.level == "auto_approved"

    def test_metadata_fallback_disabled_also_applies_to_resource_read(self) -> None:
        enf = McpGovernanceEnforcer(self._strict_config())
        ctx = _resource_ctx(
            uri="resource://tenant-a/doc", metadata={"tenant_id": "tenant-a"}
        )
        decision = enf.check_resource_read(ctx)
        assert decision.level == "blocked"

    def test_require_caller_identity_defaults_false(self) -> None:
        """Additive + backward-compatible: constructing McpGovernanceConfig
        with no require_caller_identity argument preserves the (default)
        metadata-fallback behavior."""
        config = McpGovernanceConfig()
        assert config.require_caller_identity is False


# ---------------------------------------------------------------------------
# McpTenantGrant / McpCallerIdentity type-confusion defenses
# (security-reviewer MEDIUM-2 + LOW-3 fixes)
# ---------------------------------------------------------------------------


class TestTenantGrantTypeConfusion:
    """A bare string passed where an iterable of tool/resource names was
    intended must raise, not silently become a per-character frozenset
    (frozenset("admin") == {'a','d','m','i','n'}) -- an access-control
    allowlist silently misinterpreted this way both denies the intended
    name and grants unintended single-character names."""

    def test_direct_construction_bare_string_tools_rejected(self) -> None:
        with pytest.raises(ValueError, match="bare string"):
            McpTenantGrant(tenant="t", tools="admin")

    def test_direct_construction_bare_string_resources_rejected(self) -> None:
        with pytest.raises(ValueError, match="bare string"):
            McpTenantGrant(tenant="t", resources="admin")

    def test_direct_construction_non_string_element_rejected(self) -> None:
        with pytest.raises(ValueError, match="must contain only strings"):
            McpTenantGrant(tenant="t", tools=frozenset({1, 2}))  # type: ignore[arg-type]

    def test_from_dict_bare_string_tools_rejected_before_frozenset_split(self) -> None:
        """The from_dict guard MUST fire before frozenset(str) silently
        produces a per-character set -- by the time __post_init__ would see
        it, the damage is indistinguishable from a deliberate single-char
        grant."""
        with pytest.raises(ValueError, match="bare string"):
            McpTenantGrant.from_dict({"tenant": "t", "tools": "admin"})

    def test_from_dict_bare_string_resources_rejected(self) -> None:
        with pytest.raises(ValueError, match="bare string"):
            McpTenantGrant.from_dict({"tenant": "t", "resources": "docs"})

    def test_from_dict_proper_list_accepted(self) -> None:
        grant = McpTenantGrant.from_dict({"tenant": "t", "tools": ["search", "read"]})
        assert grant.tools == frozenset({"search", "read"})


class TestCallerIdentityValidation:
    def test_non_string_tenant_rejected(self) -> None:
        with pytest.raises(ValueError, match="tenant must be a string or None"):
            McpCallerIdentity(agent_id="a", tenant=12345)  # type: ignore[arg-type]

    def test_none_tenant_accepted(self) -> None:
        identity = McpCallerIdentity(agent_id="a", tenant=None)
        assert identity.tenant is None

    def test_string_tenant_accepted(self) -> None:
        identity = McpCallerIdentity(agent_id="a", tenant="tenant-a")
        assert identity.tenant == "tenant-a"


# ---------------------------------------------------------------------------
# Rate windows re-keyed on (tenant, agent_id, tool)
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestRateLimitReKeyedByTenant:
    """Two tenants sharing the same agent_id + tool do NOT share a rate
    budget once tenant isolation is enabled."""

    def test_separate_tenants_have_separate_rate_budgets(self) -> None:
        grants = {
            "tenant-a": McpTenantGrant(tenant="tenant-a", tools=frozenset({"t"})),
            "tenant-b": McpTenantGrant(tenant="tenant-b", tools=frozenset({"t"})),
        }
        policy = McpToolPolicy(tool_name="t", rate_limit=1, max_cost=None)
        enf = McpGovernanceEnforcer(
            _config(tenant_grants=grants, tool_policies={"t": policy})
        )
        id_a = McpCallerIdentity(agent_id="agent-1", tenant="tenant-a")
        id_b = McpCallerIdentity(agent_id="agent-1", tenant="tenant-b")

        # tenant-a consumes its 1-call/min budget.
        d1 = enf.check_tool_call(
            _tool_ctx(tool_name="t", agent_id="agent-1", timestamp=_T0),
            caller_identity=id_a,
        )
        assert d1.level == "auto_approved"

        # tenant-b, SAME agent_id + tool, is NOT blocked by tenant-a's usage.
        d2 = enf.check_tool_call(
            _tool_ctx(
                tool_name="t", agent_id="agent-1", timestamp=_T0 + timedelta(seconds=1)
            ),
            caller_identity=id_b,
        )
        assert d2.level == "auto_approved"

        # tenant-a's SECOND call within the window is blocked (its own budget
        # exhausted) -- proving isolation is per-tenant, not a shared bypass.
        d3 = enf.check_tool_call(
            _tool_ctx(
                tool_name="t", agent_id="agent-1", timestamp=_T0 + timedelta(seconds=2)
            ),
            caller_identity=id_a,
        )
        assert d3.level == "blocked"
        assert "Rate limit exceeded" in d3.reason

    def test_rate_tracker_keys_are_tuple_when_isolation_on(self) -> None:
        """The tenant-keyed rate-tracker key is a TUPLE (tenant, agent_id,
        tool), not a colon-joined string -- collision-free by construction
        (see test_colon_containing_identifiers_do_not_collide below)."""
        grants = {
            "tenant-a": McpTenantGrant(tenant="tenant-a", tools=frozenset({"t"})),
        }
        policy = McpToolPolicy(tool_name="t", rate_limit=5, max_cost=None)
        enf = McpGovernanceEnforcer(
            _config(tenant_grants=grants, tool_policies={"t": policy})
        )
        identity = McpCallerIdentity(agent_id="agent-1", tenant="tenant-a")
        enf.check_tool_call(
            _tool_ctx(tool_name="t", agent_id="agent-1"), caller_identity=identity
        )
        assert ("tenant-a", "agent-1", "t") in enf._rate_tracker

    def test_colon_containing_identifiers_do_not_collide(self) -> None:
        """A tuple key is collision-free even when tenant/agent_id contain a
        literal ":" -- a colon-JOINED string would let tenant="a:b", agent="c"
        collide with tenant="a", agent="b:c" (both -> "a:b:c:t"); the tuple
        form keeps them as distinct dict keys."""
        grants = {
            "a:b": McpTenantGrant(tenant="a:b", tools=frozenset({"t"})),
            "a": McpTenantGrant(tenant="a", tools=frozenset({"t"})),
        }
        policy = McpToolPolicy(tool_name="t", rate_limit=1, max_cost=None)
        enf = McpGovernanceEnforcer(
            _config(tenant_grants=grants, tool_policies={"t": policy})
        )
        id_1 = McpCallerIdentity(agent_id="c", tenant="a:b")
        id_2 = McpCallerIdentity(agent_id="b:c", tenant="a")

        d1 = enf.check_tool_call(
            _tool_ctx(tool_name="t", agent_id="c", timestamp=_T0), caller_identity=id_1
        )
        assert d1.level == "auto_approved"
        # A colliding string-join ("a:b:c:t" for both) would have this call
        # blocked (rate_limit=1 already consumed by id_1); the tuple form
        # keeps the two principals' budgets independent.
        d2 = enf.check_tool_call(
            _tool_ctx(
                tool_name="t", agent_id="b:c", timestamp=_T0 + timedelta(seconds=1)
            ),
            caller_identity=id_2,
        )
        assert d2.level == "auto_approved"
        assert ("a:b", "c", "t") in enf._rate_tracker
        assert ("a", "b:c", "t") in enf._rate_tracker


# ---------------------------------------------------------------------------
# Middleware integration -- both invoke() and invoke_resource_read()
# ---------------------------------------------------------------------------


class _RecordingHandler:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def __call__(self, tool_name: str, args: dict) -> str:
        self.calls.append((tool_name, args))
        return "tool-ok"


class _RecordingResourceHandler:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def __call__(self, uri: str) -> str:
        self.calls.append(uri)
        return f"content-of-{uri}"


@pytest.mark.regression
@pytest.mark.security
class TestMiddlewareTenantIsolation:
    """The middleware forwards caller_identity to the enforcer and never
    invokes the underlying handler on a cross-tenant-denied call."""

    @pytest.mark.asyncio
    async def test_invoke_forwards_caller_identity_and_blocks_cross_tenant(
        self,
    ) -> None:
        enf = McpGovernanceEnforcer(_config(tenant_grants=_two_tenant_grants()))
        handler = _RecordingHandler()
        mw = McpGovernanceMiddleware(enforcer=enf, handler=handler)
        identity = McpCallerIdentity(agent_id="agent-1", tenant="tenant-a")

        result = await mw.invoke(
            "tool-b", {}, agent_id="agent-1", caller_identity=identity
        )
        assert result.decision.level == "blocked"
        assert result.executed is False
        assert handler.calls == []

    @pytest.mark.asyncio
    async def test_invoke_allows_own_tenant_tool_and_calls_handler(self) -> None:
        enf = McpGovernanceEnforcer(_config(tenant_grants=_two_tenant_grants()))
        handler = _RecordingHandler()
        mw = McpGovernanceMiddleware(enforcer=enf, handler=handler)
        identity = McpCallerIdentity(agent_id="agent-1", tenant="tenant-a")

        result = await mw.invoke(
            "tool-a", {}, agent_id="agent-1", caller_identity=identity
        )
        assert result.decision.allowed is True
        assert result.executed is True
        assert handler.calls == [("tool-a", {})]

    @pytest.mark.asyncio
    async def test_invoke_resource_read_blocks_cross_tenant_resource(self) -> None:
        enf = McpGovernanceEnforcer(_config(tenant_grants=_two_tenant_grants()))
        handler = _RecordingHandler()
        resource_handler = _RecordingResourceHandler()
        mw = McpGovernanceMiddleware(
            enforcer=enf, handler=handler, resource_handler=resource_handler
        )
        identity = McpCallerIdentity(agent_id="agent-1", tenant="tenant-a")

        result = await mw.invoke_resource_read(
            "resource://tenant-b/doc", agent_id="agent-1", caller_identity=identity
        )
        assert result.decision.level == "blocked"
        assert result.executed is False
        assert resource_handler.calls == []

    @pytest.mark.asyncio
    async def test_invoke_resource_read_allows_own_tenant_and_calls_handler(
        self,
    ) -> None:
        enf = McpGovernanceEnforcer(_config(tenant_grants=_two_tenant_grants()))
        resource_handler = _RecordingResourceHandler()
        mw = McpGovernanceMiddleware(
            enforcer=enf, handler=_RecordingHandler(), resource_handler=resource_handler
        )
        identity = McpCallerIdentity(agent_id="agent-1", tenant="tenant-a")

        result = await mw.invoke_resource_read(
            "resource://tenant-a/doc", agent_id="agent-1", caller_identity=identity
        )
        assert result.decision.allowed is True
        assert result.executed is True
        assert result.tool_result == "content-of-resource://tenant-a/doc"
        assert resource_handler.calls == ["resource://tenant-a/doc"]

    @pytest.mark.asyncio
    async def test_invoke_resource_read_isolation_off_calls_handler(self) -> None:
        """Byte-neutral backward compat through the middleware surface too."""
        enf = McpGovernanceEnforcer(_config())
        resource_handler = _RecordingResourceHandler()
        mw = McpGovernanceMiddleware(
            enforcer=enf, handler=_RecordingHandler(), resource_handler=resource_handler
        )
        result = await mw.invoke_resource_read("resource://anything", agent_id="a")
        assert result.decision.level == "auto_approved"
        assert result.executed is True
        assert resource_handler.calls == ["resource://anything"]

    @pytest.mark.asyncio
    async def test_invoke_resource_read_with_no_handler_configured(self) -> None:
        """No resource_handler wired -- governance still evaluates, but
        nothing executes (no handler to call)."""
        enf = McpGovernanceEnforcer(_config())
        mw = McpGovernanceMiddleware(enforcer=enf, handler=_RecordingHandler())
        result = await mw.invoke_resource_read("resource://anything", agent_id="a")
        assert result.decision.level == "auto_approved"
        assert result.executed is False
        assert result.tool_result is None

    @pytest.mark.asyncio
    async def test_invoke_resource_read_handler_error_captured(self) -> None:
        enf = McpGovernanceEnforcer(_config())

        async def _raising_handler(uri: str) -> str:
            raise RuntimeError("backend unavailable")

        mw = McpGovernanceMiddleware(
            enforcer=enf, handler=_RecordingHandler(), resource_handler=_raising_handler
        )
        result = await mw.invoke_resource_read("resource://x", agent_id="a")
        assert result.decision.level == "auto_approved"
        assert result.executed is False
        assert result.tool_error == "Resource read failed"
        assert result.tool_result is None


# ---------------------------------------------------------------------------
# Structural invariants (cross-sdk-inspection.md Rule 3a-style pins) --
# byte-neutral envelope + non-serialized caller identity contract
# ---------------------------------------------------------------------------


class TestByteNeutralStructuralInvariants:
    """Pins the byte-diff verdict: NO first-class serialized tenant field
    was added to McpActionContext / McpResourceContext, and McpCallerIdentity
    is deliberately NOT serialized. If a future refactor adds a first-class
    ``tenant`` / ``tenant_id`` field to either wire envelope, or gives
    McpCallerIdentity to_dict/from_dict, this test forces a re-audit against
    the issue #1843 byte-neutral contract."""

    def test_mcp_action_context_carries_no_first_class_tenant_field(self) -> None:
        field_names = {f.name for f in dataclasses.fields(McpActionContext)}
        assert "tenant" not in field_names
        assert "tenant_id" not in field_names
        assert "metadata" in field_names  # the free-form channel

    def test_mcp_resource_context_carries_no_first_class_tenant_field(self) -> None:
        field_names = {f.name for f in dataclasses.fields(McpResourceContext)}
        assert "tenant" not in field_names
        assert "tenant_id" not in field_names
        assert "metadata" in field_names

    def test_mcp_caller_identity_is_not_serialized(self) -> None:
        """McpCallerIdentity has no to_dict/from_dict -- it is a trusted,
        transport-resolved, in-memory-only object, never round-tripped over
        the wire."""
        assert not hasattr(McpCallerIdentity, "to_dict")
        assert not hasattr(McpCallerIdentity, "from_dict")

    def test_mcp_action_context_metadata_still_round_trips_tenant_id(self) -> None:
        """The free-form metadata channel is the byte-neutral carrier --
        confirm it round-trips through to_dict/from_dict unchanged."""
        ctx = McpActionContext(
            tool_name="t", metadata={"tenant_id": "tenant-a"}, timestamp=_T0
        )
        restored = McpActionContext.from_dict(ctx.to_dict())
        assert restored.metadata["tenant_id"] == "tenant-a"

    def test_mcp_governance_config_tenant_grants_defaults_empty(self) -> None:
        """Additive + optional: constructing McpGovernanceConfig with no
        tenant_grants argument at all yields an empty map (isolation OFF)."""
        config = McpGovernanceConfig()
        assert dict(config.tenant_grants) == {}
