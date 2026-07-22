# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #1919 -- deprecate the untrusted
metadata["tenant_id"] tenant fallback in MCP governance.

Background (issue #1843 → #1919): #1843 introduced first-class MCP tenant
isolation with a secure default (``require_caller_identity=True``) and a
documented WEAKER mode (``require_caller_identity=False``) that, as a
last-resort fallback, trusted a client-asserted ``metadata["tenant_id"]`` as
the effective tenant. That fallback let a client-supplied body value influence
a tenant-isolation decision -- exactly the impersonation surface first-class
tenant isolation exists to close, merely narrowed to one opt-in mode.

Issue #1919 (Option B, user-ratified): DEPRECATE that fallback so a
client-asserted tenant can NEVER influence tenant decisions in ANY mode. The
single enforcer decision chokepoint (``_resolve_effective_tenant``) no longer
trusts ``metadata["tenant_id"]`` in the weaker branch; when a caller exercises
the now-deprecated path a ``DeprecationWarning`` fires (naming the migration:
provide a trusted caller identity / server-verified tenant, or set
``require_caller_identity=True``) and the resolution returns ``None``, which
fails the downstream tenant-isolation decision CLOSED. A defense-in-depth
scrub at the middleware boundary drops ``metadata["tenant_id"]`` before the
context is built, so the client-asserted value never propagates into
audit/echo surfaces either.

Invariants exercised here:

1. Verified/trusted precedence unchanged (covered by #1843/#1878 suites).
2. Secure default (``require_caller_identity=True``) is byte-identical /
   inert to metadata AND does NOT warn (the deprecated path is never reached).
3. Under ``require_caller_identity=False`` a client-asserted
   ``metadata["tenant_id"]`` can NO LONGER influence the decision (AC#3) AND
   the decision fails CLOSED (never fail-open) when no trusted tenant resolves.
4. A ``DeprecationWarning`` fires EXACTLY when a caller exercises the
   now-deprecated fallback path -- never on the secure-default path.

Tier-2 real behavior: real ``McpGovernanceEnforcer`` / ``McpGovernanceConfig``
/ ``McpGovernanceMiddleware`` objects; the enforcement decision is NEVER
mocked. The middleware tests use a real capturing subclass that records the
context the middleware built and delegates the actual decision to
``super()``.
"""

from __future__ import annotations

import warnings
from datetime import UTC, datetime
from typing import Any

import pytest

from pact.mcp.enforcer import GovernanceDecision, McpGovernanceEnforcer
from pact.mcp.middleware import McpGovernanceMiddleware
from pact.mcp.types import (
    DefaultPolicy,
    McpActionContext,
    McpCallerIdentity,
    McpGovernanceConfig,
    McpResourceContext,
    McpTenantGrant,
)

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _grants() -> dict[str, McpTenantGrant]:
    return {
        "tenant-a": McpTenantGrant(
            tenant="tenant-a",
            tools=frozenset({"tool-a"}),
            resources=frozenset({"resource://tenant-a/doc"}),
        ),
    }


def _weaker_config() -> McpGovernanceConfig:
    """The documented #1843 weaker mode -- the ONLY mode that ever consulted
    the (now-deprecated) metadata fallback."""
    return McpGovernanceConfig(
        default_policy=DefaultPolicy.ALLOW,
        tenant_grants=_grants(),
        require_caller_identity=False,
        audit_enabled=False,
    )


def _secure_config() -> McpGovernanceConfig:
    """The secure default -- metadata is never consulted; no deprecation."""
    return McpGovernanceConfig(
        default_policy=DefaultPolicy.ALLOW,
        tenant_grants=_grants(),
        require_caller_identity=True,
        audit_enabled=False,
    )


# ---------------------------------------------------------------------------
# AC#3 -- a client-asserted metadata["tenant_id"] cannot influence the
# decision even under the weaker mode, on BOTH surfaces.
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.security
class TestMetadataTenantCannotInfluenceDecision:
    def test_tool_call_metadata_tenant_does_not_auto_approve(self) -> None:
        """A body-asserted tenant that names a GRANTED tenant/tool would, under
        the old fallback, have auto-approved. It now fails CLOSED (no tenant
        resolved) -- the metadata value has zero influence on the decision."""
        enf = McpGovernanceEnforcer(_weaker_config())
        ctx = McpActionContext(
            tool_name="tool-a",
            agent_id="agent-1",
            metadata={"tenant_id": "tenant-a"},  # matches a real grant
            timestamp=_T0,
        )
        with pytest.warns(DeprecationWarning):
            decision = enf.check_tool_call(ctx)
        assert decision.level == "blocked"
        assert decision.allowed is False
        assert "no tenant was declared" in decision.reason
        # The client-asserted tenant name must NOT appear as the resolved
        # tenant in the reason (it was not honored).
        assert "not a recognized tenant" not in decision.reason

    def test_resource_read_metadata_tenant_does_not_auto_approve(self) -> None:
        """Same as above for the resources/read surface (Enforcement-Surface
        Parity -- both surfaces share the one decision chokepoint)."""
        enf = McpGovernanceEnforcer(_weaker_config())
        ctx = McpResourceContext(
            uri="resource://tenant-a/doc",
            agent_id="agent-1",
            metadata={"tenant_id": "tenant-a"},
            timestamp=_T0,
        )
        with pytest.warns(DeprecationWarning):
            decision = enf.check_resource_read(ctx)
        assert decision.level == "blocked"
        assert decision.allowed is False
        assert "no tenant was declared" in decision.reason

    def test_trusted_identity_still_wins_over_body(self) -> None:
        """Precedence invariant #1: a trusted caller_identity.tenant still
        resolves the decision even under the weaker mode -- and because a
        trusted source resolved, the deprecated metadata branch is never
        reached, so NO DeprecationWarning fires."""
        enf = McpGovernanceEnforcer(_weaker_config())
        identity = McpCallerIdentity(agent_id="agent-1", tenant="tenant-a")
        ctx = McpActionContext(
            tool_name="tool-a",
            agent_id="agent-1",
            metadata={"tenant_id": "tenant-b"},  # a lie; must be ignored
            timestamp=_T0,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            decision = enf.check_tool_call(ctx, caller_identity=identity)
        assert decision.level == "auto_approved"


# ---------------------------------------------------------------------------
# Fail-closed -- a None effective tenant DENIES, never fail-open.
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.security
class TestFailsClosedOnNoTenant:
    def test_weaker_mode_no_metadata_no_identity_blocks(self) -> None:
        """Weaker mode, isolation ON, no tenant from any source and NO
        metadata tenant_id present (so no deprecated path exercised) -- the
        decision fails CLOSED with no warning."""
        enf = McpGovernanceEnforcer(_weaker_config())
        ctx = McpActionContext(tool_name="tool-a", agent_id="agent-1", timestamp=_T0)
        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            decision = enf.check_tool_call(ctx)
        assert decision.level == "blocked"
        assert decision.allowed is False
        assert "no tenant was declared" in decision.reason

    def test_non_string_metadata_tenant_does_not_warn_and_blocks(self) -> None:
        """A non-str metadata tenant_id (e.g. a nested dict) was never a valid
        fallback value; it does not trip the deprecation warning and still
        fails closed."""
        enf = McpGovernanceEnforcer(_weaker_config())
        ctx = McpActionContext(
            tool_name="tool-a",
            agent_id="agent-1",
            metadata={"tenant_id": {"nested": "obj"}},
            timestamp=_T0,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            decision = enf.check_tool_call(ctx)
        assert decision.level == "blocked"
        assert decision.allowed is False


# ---------------------------------------------------------------------------
# Secure default is unchanged AND does not warn.
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.security
class TestSecureDefaultUnchanged:
    def test_secure_default_blocks_body_tenant_without_warning(self) -> None:
        """Invariant #2: the secure default returns None BEFORE the metadata
        branch is ever reached, so a body-asserted tenant is inert AND no
        DeprecationWarning fires (the deprecated path is unreachable here)."""
        enf = McpGovernanceEnforcer(_secure_config())
        ctx = McpActionContext(
            tool_name="tool-a",
            agent_id="agent-1",
            metadata={"tenant_id": "tenant-a"},
            timestamp=_T0,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            decision = enf.check_tool_call(ctx)
        assert decision.level == "blocked"
        assert "no tenant was declared" in decision.reason

    def test_default_config_require_caller_identity_stays_true(self) -> None:
        """The secure default byte-identity guard: an unset
        require_caller_identity is True (unchanged by #1919)."""
        assert McpGovernanceConfig().require_caller_identity is True


# ---------------------------------------------------------------------------
# Middleware defense-in-depth: metadata["tenant_id"] is scrubbed at the
# boundary and never reaches the built context (audit/echo hygiene).
# ---------------------------------------------------------------------------


class _CapturingEnforcer(McpGovernanceEnforcer):
    """Records the context the middleware built, then delegates the REAL
    decision to ``super()``. Not a mock of the enforcement decision -- the
    actual governance logic runs; this only observes the context that was
    handed to it."""

    def __init__(self, config: McpGovernanceConfig) -> None:
        super().__init__(config)
        self.captured_tool_ctx: McpActionContext | None = None
        self.captured_resource_ctx: McpResourceContext | None = None

    def check_tool_call(
        self,
        context: McpActionContext,
        *,
        caller_identity: McpCallerIdentity | None = None,
    ) -> GovernanceDecision:
        self.captured_tool_ctx = context
        return super().check_tool_call(context, caller_identity=caller_identity)

    def check_resource_read(
        self,
        context: McpResourceContext,
        *,
        caller_identity: McpCallerIdentity | None = None,
    ) -> GovernanceDecision:
        self.captured_resource_ctx = context
        return super().check_resource_read(context, caller_identity=caller_identity)


async def _noop_handler(tool_name: str, args: dict[str, Any]) -> Any:
    return {"status": "ok"}


async def _noop_resource_handler(uri: str) -> Any:
    return {"body": "content"}


@pytest.mark.regression
@pytest.mark.security
class TestMiddlewareScrubsMetadataTenant:
    async def test_invoke_context_metadata_drops_tenant_id(self) -> None:
        enf = _CapturingEnforcer(_weaker_config())
        mw = McpGovernanceMiddleware(enf, _noop_handler)
        # A client-asserted tenant_id plus a legitimate sibling key.
        with warnings.catch_warnings():
            # The scrub removes tenant_id BEFORE the enforcer sees it, so the
            # deprecated fallback path is not exercised via the middleware --
            # no DeprecationWarning is expected here.
            warnings.simplefilter("error", DeprecationWarning)
            await mw.invoke(
                "tool-a",
                agent_id="agent-1",
                metadata={"tenant_id": "tenant-a", "trace": "keep-me"},
            )
        ctx = enf.captured_tool_ctx
        assert ctx is not None
        assert "tenant_id" not in ctx.metadata
        # Non-tenant metadata is preserved.
        assert ctx.metadata.get("trace") == "keep-me"
        # The verified tenant field is populated only from caller_identity
        # (absent here), never from the body.
        assert ctx.tenant is None

    async def test_invoke_resource_read_context_metadata_drops_tenant_id(
        self,
    ) -> None:
        enf = _CapturingEnforcer(_weaker_config())
        mw = McpGovernanceMiddleware(
            enf, _noop_handler, resource_handler=_noop_resource_handler
        )
        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            await mw.invoke_resource_read(
                "resource://tenant-a/doc",
                agent_id="agent-1",
                metadata={"tenant_id": "tenant-a", "trace": "keep-me"},
            )
        ctx = enf.captured_resource_ctx
        assert ctx is not None
        assert "tenant_id" not in ctx.metadata
        assert ctx.metadata.get("trace") == "keep-me"
        assert ctx.tenant is None

    async def test_invoke_verified_tenant_still_from_caller_identity(self) -> None:
        """The scrub does not disturb the verified tenant path: a trusted
        caller_identity.tenant still populates context.tenant."""
        enf = _CapturingEnforcer(_weaker_config())
        mw = McpGovernanceMiddleware(enf, _noop_handler)
        identity = McpCallerIdentity(agent_id="agent-1", tenant="tenant-a")
        result = await mw.invoke(
            "tool-a",
            agent_id="agent-1",
            caller_identity=identity,
            metadata={"tenant_id": "tenant-b"},  # lie; scrubbed + ignored
        )
        ctx = enf.captured_tool_ctx
        assert ctx is not None
        assert "tenant_id" not in ctx.metadata
        assert ctx.tenant == "tenant-a"
        # A granted tenant/tool → the call is allowed and the handler ran.
        assert result.decision.level == "auto_approved"
        assert result.executed is True
