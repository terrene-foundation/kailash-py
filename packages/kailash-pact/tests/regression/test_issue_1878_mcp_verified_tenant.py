# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #1878 -- first-class, server-verified ``tenant``
field on ``McpActionContext`` / ``McpResourceContext`` for robust tenant
isolation.

Issue #1843 routed the tenant through the free-form, self-asserted
``metadata["tenant_id"]`` channel (client-body-copyable) plus a sidecar
``McpCallerIdentity``. #1878 promotes the verified tenant to a FIRST-CLASS
field ON the context, DISTINCT from the free-form metadata map:

* AC#1 -- ``McpActionContext`` / ``McpResourceContext`` expose a first-class
  ``tenant`` field, separate from ``metadata``.
* AC#2 -- governance enforcement reads the VERIFIED first-class field, not
  ``metadata["tenant_id"]``.
* AC#3 -- any body-supplied ``tenant`` / ``tenant_id`` is stripped / not
  trusted on network transports: the verified field is populated at the
  network boundary from the authenticated transport/token, NEVER from the
  wire body (``from_network_transport`` strips it; ``from_dict`` never reads
  the first-class field; ``to_dict`` never emits it -- byte-neutral wire
  contract preserved, so NO cross-SDK wire lockstep is required).
* AC#4 -- fail-closed: isolation active + no verified tenant resolves =>
  access DENIED (never defaulted / allowed).

The verified field is SERVER-SIDE ONLY -- it is a dataclass field but is
excluded from the wire serialization (``to_dict`` / ``from_dict``), exactly
as ``McpCallerIdentity`` is deliberately non-serialized. This keeps the
issue #1843 byte-neutral wire contract intact: a Rust peer's on-the-wire
``McpActionContext`` bytes are unchanged.

All tests are BEHAVIORAL -- they construct real enforcers / middleware and
assert the resulting decision. The governance path is NEVER mocked
(testing.md Tier-2; the spoof-attempt test is mandatory, security-relevant).
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from typing import Any

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

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _config(
    tenant_grants: dict[str, McpTenantGrant] | None = None,
    tool_policies: dict[str, McpToolPolicy] | None = None,
    default_policy: DefaultPolicy = DefaultPolicy.ALLOW,
    require_caller_identity: bool | None = None,
) -> McpGovernanceConfig:
    kwargs: dict[str, Any] = {}
    if require_caller_identity is not None:
        kwargs["require_caller_identity"] = require_caller_identity
    return McpGovernanceConfig(
        default_policy=default_policy,
        tool_policies=tool_policies or {},
        tenant_grants=tenant_grants or {},
        audit_enabled=False,
        **kwargs,
    )


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


# ---------------------------------------------------------------------------
# AC#1 -- first-class tenant field, distinct from the metadata map
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestFirstClassTenantField:
    def test_action_context_exposes_first_class_tenant_field(self) -> None:
        field_names = {f.name for f in dataclasses.fields(McpActionContext)}
        assert "tenant" in field_names
        assert "metadata" in field_names
        assert "tenant" != "metadata"  # distinct surfaces

    def test_resource_context_exposes_first_class_tenant_field(self) -> None:
        field_names = {f.name for f in dataclasses.fields(McpResourceContext)}
        assert "tenant" in field_names
        assert "metadata" in field_names

    def test_tenant_field_defaults_none(self) -> None:
        assert McpActionContext(tool_name="t").tenant is None
        assert McpResourceContext(uri="u").tenant is None

    def test_tenant_field_is_separate_from_metadata(self) -> None:
        ctx = McpActionContext(
            tool_name="t", tenant="tenant-a", metadata={"tenant_id": "tenant-b"}
        )
        # The verified field and the free-form channel hold DISTINCT values --
        # they are not aliased.
        assert ctx.tenant == "tenant-a"
        assert ctx.metadata["tenant_id"] == "tenant-b"

    def test_non_string_tenant_rejected(self) -> None:
        with pytest.raises(ValueError, match="tenant must be a string or None"):
            McpActionContext(tool_name="t", tenant=123)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="tenant must be a string or None"):
            McpResourceContext(uri="u", tenant=123)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# AC#2 -- governance reads the VERIFIED field, not metadata["tenant_id"]
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.security
class TestGovernanceReadsVerifiedField:
    def test_verified_tenant_grants_own_tool(self) -> None:
        enf = McpGovernanceEnforcer(_config(tenant_grants=_two_tenant_grants()))
        ctx = McpActionContext(tool_name="tool-a", tenant="tenant-a", timestamp=_T0)
        decision = enf.check_tool_call(ctx)
        assert decision.level == "auto_approved"

    def test_verified_tenant_denied_other_tenant_tool(self) -> None:
        enf = McpGovernanceEnforcer(_config(tenant_grants=_two_tenant_grants()))
        ctx = McpActionContext(tool_name="tool-b", tenant="tenant-a", timestamp=_T0)
        decision = enf.check_tool_call(ctx)
        assert decision.level == "blocked"
        assert "tenant-a" in decision.reason

    def test_verified_tenant_used_over_metadata_tenant_id(self) -> None:
        """The verified field says tenant-a; the body metadata claims
        tenant-b (which owns tool-b). Governance MUST evaluate as tenant-a
        (the verified field) and BLOCK the tool-b call -- proving the
        decision reads the verified field, not metadata."""
        enf = McpGovernanceEnforcer(_config(tenant_grants=_two_tenant_grants()))
        ctx = McpActionContext(
            tool_name="tool-b",
            tenant="tenant-a",
            metadata={"tenant_id": "tenant-b"},
            timestamp=_T0,
        )
        decision = enf.check_tool_call(ctx)
        assert decision.level == "blocked"
        assert "tenant-a" in decision.reason
        assert "tenant-b" not in decision.reason

    def test_verified_tenant_read_on_resource_surface(self) -> None:
        enf = McpGovernanceEnforcer(_config(tenant_grants=_two_tenant_grants()))
        ctx = McpResourceContext(
            uri="resource://tenant-b/doc", tenant="tenant-a", timestamp=_T0
        )
        decision = enf.check_resource_read(ctx)
        assert decision.level == "blocked"
        assert "tenant-a" in decision.reason

    def test_verified_tenant_ranks_over_caller_identity_and_metadata(self) -> None:
        """Verified first-class field is the highest-trust source: even a
        caller_identity carrying a different tenant does not override the
        first-class verified field."""
        enf = McpGovernanceEnforcer(_config(tenant_grants=_two_tenant_grants()))
        ctx = McpActionContext(tool_name="tool-a", tenant="tenant-a", timestamp=_T0)
        identity = McpCallerIdentity(agent_id="x", tenant="tenant-b")
        decision = enf.check_tool_call(ctx, caller_identity=identity)
        # tenant-a (verified field) owns tool-a -> approved. If caller_identity
        # (tenant-b) had won, tool-a would be BLOCKED for tenant-b.
        assert decision.level == "auto_approved"


# ---------------------------------------------------------------------------
# AC#3 -- body-supplied tenant stripped / not trusted on network transports
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.security
class TestBodySuppliedTenantStripped:
    def test_from_network_transport_strips_body_top_level_tenant(self) -> None:
        """A client that puts a first-class-looking ``tenant`` in the wire
        body cannot set the verified field -- the network deserializer
        ignores it and uses the authenticated transport value."""
        body = {"tool_name": "tool-a", "tenant": "tenant-b", "agent_id": "x"}
        ctx = McpActionContext.from_network_transport(body, verified_tenant="tenant-a")
        assert ctx.tenant == "tenant-a"

    def test_from_network_transport_strips_metadata_tenant_id(self) -> None:
        body = {
            "tool_name": "tool-a",
            "metadata": {"tenant_id": "tenant-b", "trace": "keep-me"},
        }
        ctx = McpActionContext.from_network_transport(body, verified_tenant="tenant-a")
        assert ctx.tenant == "tenant-a"
        assert "tenant_id" not in ctx.metadata  # stripped
        assert ctx.metadata["trace"] == "keep-me"  # other metadata preserved

    def test_from_network_transport_no_verified_tenant_yields_none(self) -> None:
        """No authenticated transport tenant -> verified field is None (the
        fail-closed input); body tenant is still stripped, never trusted."""
        body = {"tool_name": "tool-a", "metadata": {"tenant_id": "tenant-b"}}
        ctx = McpActionContext.from_network_transport(body)
        assert ctx.tenant is None
        assert "tenant_id" not in ctx.metadata

    def test_network_transport_spoof_denied_end_to_end(self) -> None:
        """The full spoof-attack path: a tenant-a caller crafts a body that
        claims tenant-b (owner of tool-b). Under the secure default the
        deserialized context carries verified tenant-a and BLOCKS."""
        enf = McpGovernanceEnforcer(_config(tenant_grants=_two_tenant_grants()))
        malicious_body = {
            "tool_name": "tool-b",
            "tenant": "tenant-b",
            "metadata": {"tenant_id": "tenant-b"},
        }
        ctx = McpActionContext.from_network_transport(
            malicious_body, verified_tenant="tenant-a"
        )
        decision = enf.check_tool_call(ctx)
        assert decision.level == "blocked"
        assert "tenant-a" in decision.reason

    def test_from_network_transport_resource_strips_body_tenant(self) -> None:
        body = {
            "uri": "resource://tenant-b/doc",
            "tenant": "tenant-b",
            "metadata": {"tenant_id": "tenant-b"},
        }
        ctx = McpResourceContext.from_network_transport(
            body, verified_tenant="tenant-a"
        )
        assert ctx.tenant == "tenant-a"
        assert "tenant_id" not in ctx.metadata


# ---------------------------------------------------------------------------
# AC#4 -- fail-closed when isolation active and no verified tenant resolves
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.security
class TestFailClosedNoVerifiedTenant:
    def test_no_verified_tenant_blocks_tool_call(self) -> None:
        """Isolation ON, no verified field, no caller_identity, secure
        default (require_caller_identity=True) -> the untrusted metadata
        channel is never consulted -> BLOCKED."""
        enf = McpGovernanceEnforcer(_config(tenant_grants=_two_tenant_grants()))
        ctx = McpActionContext(
            tool_name="tool-a", metadata={"tenant_id": "tenant-a"}, timestamp=_T0
        )
        decision = enf.check_tool_call(ctx)
        assert decision.level == "blocked"
        assert "no tenant was declared" in decision.reason

    def test_no_verified_tenant_blocks_resource_read(self) -> None:
        enf = McpGovernanceEnforcer(_config(tenant_grants=_two_tenant_grants()))
        ctx = McpResourceContext(
            uri="resource://tenant-a/doc",
            metadata={"tenant_id": "tenant-a"},
            timestamp=_T0,
        )
        decision = enf.check_resource_read(ctx)
        assert decision.level == "blocked"
        assert "no tenant was declared" in decision.reason

    def test_empty_string_verified_tenant_treated_as_absent(self) -> None:
        """An empty verified tenant is not a real tenant -> fail-closed."""
        enf = McpGovernanceEnforcer(_config(tenant_grants=_two_tenant_grants()))
        ctx = McpActionContext(tool_name="tool-a", tenant="", timestamp=_T0)
        decision = enf.check_tool_call(ctx)
        assert decision.level == "blocked"

    def test_unknown_verified_tenant_blocks(self) -> None:
        enf = McpGovernanceEnforcer(_config(tenant_grants=_two_tenant_grants()))
        ctx = McpActionContext(tool_name="tool-a", tenant="tenant-x", timestamp=_T0)
        decision = enf.check_tool_call(ctx)
        assert decision.level == "blocked"
        assert "not a recognized tenant" in decision.reason


# ---------------------------------------------------------------------------
# Wire contract unchanged -- verified field is server-side only (byte-neutral)
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestVerifiedFieldNotWireSerialized:
    def test_to_dict_does_not_emit_verified_tenant(self) -> None:
        ctx = McpActionContext(tool_name="t", tenant="tenant-a", timestamp=_T0)
        assert "tenant" not in ctx.to_dict()

    def test_resource_to_dict_does_not_emit_verified_tenant(self) -> None:
        ctx = McpResourceContext(uri="u", tenant="tenant-a", timestamp=_T0)
        assert "tenant" not in ctx.to_dict()

    def test_from_dict_never_populates_verified_tenant_from_body(self) -> None:
        """Even if a crafted wire body carries a top-level ``tenant`` key,
        the generic ``from_dict`` deserializer never trusts it."""
        restored = McpActionContext.from_dict(
            {"tool_name": "t", "tenant": "tenant-evil"}
        )
        assert restored.tenant is None

    def test_metadata_tenant_id_still_round_trips_through_wire(self) -> None:
        """The free-form metadata channel remains byte-neutral (issue #1843
        backward-compat) -- to_dict/from_dict round-trips it untouched."""
        ctx = McpActionContext(
            tool_name="t", metadata={"tenant_id": "tenant-a"}, timestamp=_T0
        )
        restored = McpActionContext.from_dict(ctx.to_dict())
        assert restored.metadata["tenant_id"] == "tenant-a"


# ---------------------------------------------------------------------------
# Middleware populates the verified field at the network boundary
# ---------------------------------------------------------------------------


class _RecordingHandler:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def __call__(self, tool_name: str, args: dict) -> str:
        self.calls.append((tool_name, args))
        return "ok"


@pytest.mark.regression
@pytest.mark.security
class TestMiddlewarePopulatesVerifiedField:
    @pytest.mark.asyncio
    async def test_invoke_populates_verified_tenant_from_caller_identity(self) -> None:
        """The middleware is the network boundary: it derives the verified
        tenant from the authenticated caller_identity, so a cross-tenant tool
        is blocked even though no metadata tenant is set."""
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
    async def test_invoke_allows_own_tenant_via_populated_verified_field(self) -> None:
        enf = McpGovernanceEnforcer(_config(tenant_grants=_two_tenant_grants()))
        handler = _RecordingHandler()
        mw = McpGovernanceMiddleware(enforcer=enf, handler=handler)
        identity = McpCallerIdentity(agent_id="agent-1", tenant="tenant-a")

        result = await mw.invoke(
            "tool-a", {}, agent_id="agent-1", caller_identity=identity
        )
        assert result.decision.allowed is True
        assert result.executed is True

    @pytest.mark.asyncio
    async def test_invoke_body_metadata_tenant_cannot_override_verified(self) -> None:
        """A caller passes a spoofed metadata tenant_id (tenant-b, owner of
        tool-b) but the authenticated identity is tenant-a. The verified
        field wins -> tool-b BLOCKED."""
        enf = McpGovernanceEnforcer(_config(tenant_grants=_two_tenant_grants()))
        handler = _RecordingHandler()
        mw = McpGovernanceMiddleware(enforcer=enf, handler=handler)
        identity = McpCallerIdentity(agent_id="agent-1", tenant="tenant-a")

        result = await mw.invoke(
            "tool-b",
            {},
            agent_id="agent-1",
            caller_identity=identity,
            metadata={"tenant_id": "tenant-b"},
        )
        assert result.decision.level == "blocked"
        assert "tenant-a" in result.decision.reason
        assert handler.calls == []
