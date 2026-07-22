# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""MCP governance enforcer -- the core enforcement engine for MCP tool calls.

Provides McpGovernanceEnforcer which checks MCP tool invocations against
governance policies and returns deterministic decisions. This is a PRIMITIVE
(no LLM, purely deterministic).

Security invariants (per pact-governance.md):
1. Default-deny: unregistered tools are BLOCKED (Rule 5)
2. NaN/Inf defense: math.isfinite() on all numeric fields (Rule 6)
3. Thread-safe: all shared state access acquires self._lock (Rule 8)
4. Fail-closed: all error paths return BLOCKED (Rule 4)
5. Bounded collections: audit trail uses deque(maxlen=N) (Rule 7)
6. Clearance authorization: a tool whose policy sets clearance_required is
   evaluated for caller clearance BEFORE the cost ladder; absent, unrecognized,
   or insufficient caller clearance fails closed to BLOCKED (Rule 4).
7. Tenant isolation (issue #1843): when McpGovernanceConfig.tenant_grants is
   non-empty, BOTH tools/call (keyed on tool name) and resources/read (keyed
   on URI) are scoped through ONE shared restrictiveness function
   (_tenant_isolation_decision), fail-closed on an absent, unrecognized, or
   ungranted tenant (security.md Enforcement-Surface Parity). A trusted
   McpCallerIdentity's tenant OVERWRITES any self-asserted
   metadata["tenant_id"] (impersonation defeat). Empty tenant_grants (the
   default) means isolation is OFF -- byte-neutral backward compatibility.
"""

from __future__ import annotations

import logging
import math
import threading
import warnings
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from kailash.trust import ConfidentialityLevel
from pact.mcp.audit import McpAuditTrail
from pact.mcp.types import (
    DefaultPolicy,
    McpActionContext,
    McpCallerIdentity,
    McpGovernanceConfig,
    McpResourceContext,
    McpTenantGrant,
    McpToolPolicy,
)

logger = logging.getLogger(__name__)

__all__ = [
    "GovernanceDecision",
    "McpGovernanceEnforcer",
]


# Confidentiality levels in ascending restrictiveness order, mirroring
# ConfidentialityLevel's PUBLIC < RESTRICTED < CONFIDENTIAL < SECRET < TOP_SECRET.
_CLEARANCE_LEVELS_ASCENDING = (
    ConfidentialityLevel.PUBLIC,
    ConfidentialityLevel.RESTRICTED,
    ConfidentialityLevel.CONFIDENTIAL,
    ConfidentialityLevel.SECRET,
    ConfidentialityLevel.TOP_SECRET,
)


def _clearance_restrictiveness(value: str | None) -> int:
    """Rank a policy ``clearance_required`` value by eval-time restrictiveness.

    Used by monotonic-tightening validation so a re-registration can only KEEP
    or RAISE a tool's clearance bar -- never lower or drop it (a privilege
    escalation that would silently strip the Layer-2 authorization gate).

    Ordering, widest (lowest) to tightest (highest):

    - ``None`` -- no clearance requirement; any caller passes the gate -> -1.
    - a recognized ``ConfidentialityLevel`` token -- its index in the ascending
      order above (0..4); a higher level admits fewer callers.
    - an unrecognized value -- fail-closed to BLOCKED-for-all at eval time (see
      :meth:`McpGovernanceEnforcer._check_clearance`), i.e. the TIGHTEST setting
      (no caller passes) -> ranked above every recognized level.
    """
    if value is None:
        return -1
    try:
        level = ConfidentialityLevel(str(value).strip().lower())
    except ValueError:
        return len(_CLEARANCE_LEVELS_ASCENDING)
    return _CLEARANCE_LEVELS_ASCENDING.index(level)


# Rate-tracker dict key: "agent_id:tool_name" (isolation off / no tenant) OR
# the tuple (tenant, agent_id, tool_name) (issue #1843, tenant resolved). A
# tuple -- not a colon-joined string -- makes the tenant-keyed form
# collision-free: a tenant/agent_id/tool_name containing a literal ":" can
# never make two distinct principals hash to the same string key.
_RateTrackerKey = str | tuple[str, str, str]


def _resolve_effective_tenant(
    metadata: Mapping[str, Any],
    caller_identity: McpCallerIdentity | None,
    *,
    verified_tenant: str | None = None,
    require_caller_identity: bool = False,
) -> str | None:
    """Resolve the AUTHORITATIVE tenant for an MCP call (issue #1843/#1878).

    Trust precedence, highest first:

    1. ``verified_tenant`` -- the first-class, SERVER-VERIFIED
       ``McpActionContext.tenant`` / ``McpResourceContext.tenant`` field
       (issue #1878), populated at the network boundary from the
       authenticated transport/token and never from the client body. When
       set, it is the authoritative tenant; nothing overrides it.
    2. ``caller_identity.tenant`` -- the sidecar trusted identity (issue
       #1843), also transport-resolved. Consulted when no first-class
       verified tenant is present.

    A client-asserted ``metadata["tenant_id"]`` is NEVER a trusted source of
    the effective tenant. Under the secure default
    (``require_caller_identity=True``) the body channel was never consulted.
    Under the documented weaker mode (``require_caller_identity=False``, the
    issue #1843 opt-in) it was previously consulted as a last-resort
    fallback; that fallback is DEPRECATED and no longer honored (issue
    #1919). A caller relying on it now gets a ``DeprecationWarning`` and the
    resolution returns ``None`` -- which fails the downstream tenant-isolation
    decision CLOSED (never fail-open). A caller can no longer influence the
    tenant decision by putting a tenant in the request body in ANY mode.

    Returns:
        The tenant string from a trusted source, or None if none resolves.
    """
    if verified_tenant is not None:
        return verified_tenant
    if caller_identity is not None and caller_identity.tenant is not None:
        return caller_identity.tenant
    if require_caller_identity:
        return None
    # require_caller_identity is False: the documented #1843 weaker mode. The
    # metadata["tenant_id"] fallback that this branch previously trusted is
    # DEPRECATED (#1919) -- a client-asserted tenant must never influence the
    # decision. If a caller was relying on that fallback (a str tenant_id is
    # present), warn with the migration path and return None so the
    # tenant-isolation decision fails CLOSED downstream.
    metadata_tenant = metadata.get("tenant_id") if metadata else None
    if isinstance(metadata_tenant, str):
        warnings.warn(
            "MCP tenant isolation: trusting a client-asserted "
            "metadata['tenant_id'] as the effective tenant is deprecated and "
            "is no longer honored (#1919). The request now fails closed (no "
            "tenant resolved). Migrate by providing a trusted caller identity "
            "(McpCallerIdentity.tenant) or a server-verified context tenant, "
            "or set McpGovernanceConfig.require_caller_identity=True.",
            DeprecationWarning,
            stacklevel=2,
        )
    return None


def _tenant_grant_permits(
    tenant_grants: Mapping[str, McpTenantGrant],
    tenant: str | None,
    kind: Literal["tool", "resource"],
    key: str,
) -> bool:
    """Shared restrictiveness check for MCP tenant isolation (issue #1843).

    This is the ONE function BOTH the tools/call path (keyed on tool name)
    and the resources/read path (keyed on URI) call to decide access --
    security.md Enforcement-Surface Parity: a single shared restrictiveness
    function so the two enforcement surfaces cannot silently diverge.

    Fail-closed: an absent tenant, an unrecognized tenant (not a key in
    ``tenant_grants``), or a tenant with no grant for ``key`` under ``kind``
    all return False. Only an explicit grant for ``key`` returns True.
    Callers MUST NOT invoke this when ``tenant_grants`` is empty -- that is
    the isolation-OFF case, handled entirely by the caller (see
    :meth:`McpGovernanceEnforcer._tenant_isolation_decision`).
    """
    if tenant is None:
        return False
    grant = tenant_grants.get(tenant)
    if grant is None:
        return False
    granted = grant.tools if kind == "tool" else grant.resources
    return key in granted


@dataclass(frozen=True)
class GovernanceDecision:
    """Result of an MCP governance check.

    frozen=True: decisions are immutable records of governance evaluations.

    Attributes:
        level: Verification gradient level. One of:
            "auto_approved" -- tool call is within all constraints
            "flagged" -- tool call is near a boundary (cost near limit)
            "held" -- tool call exceeds soft limit, needs approval
            "blocked" -- tool call violates a hard constraint
        tool_name: The MCP tool that was evaluated. For a resources/read
            decision (see McpGovernanceEnforcer.check_resource_read), this is
            "" and ``resource_uri`` carries the resource URI instead.
        agent_id: The agent that attempted the call.
        reason: Human-readable explanation of the decision.
        resource_uri: The MCP resource URI evaluated, for a resources/read
            decision (issue #1843). None for a tools/call decision. Additive
            field -- default None, semantically inert for a tools/call
            decision (to_dict() now includes "resource_uri": null on every
            tool-call decision's serialized dict; no existing consumer field
            is removed or renamed).
        timestamp: When the decision was made.
        policy_snapshot: Serialized policy that was evaluated, if any.
        metadata: Additional structured details.
    """

    level: str
    tool_name: str
    agent_id: str
    reason: str
    resource_uri: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    policy_snapshot: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        """True if the tool call is permitted (auto_approved or flagged).

        FLAGGED calls are allowed but should be logged for review.
        HELD and BLOCKED calls are not allowed.
        """
        return self.level in ("auto_approved", "flagged")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "level": self.level,
            "tool_name": self.tool_name,
            "agent_id": self.agent_id,
            "reason": self.reason,
            "resource_uri": self.resource_uri,
            "allowed": self.allowed,
            "timestamp": self.timestamp.isoformat(),
            "policy_snapshot": self.policy_snapshot,
            "metadata": self.metadata,
        }


class McpGovernanceEnforcer:
    """Core enforcement engine for MCP tool invocation governance.

    Evaluates MCP tool calls against governance policies and returns
    deterministic GovernanceDecision results. This is a PRIMITIVE -- no LLM
    involvement, purely rule-based.

    Security invariants:
    - Default-deny for unregistered tools (configurable to ALLOW, but DENY
      is the default and strongly recommended).
    - NaN/Inf defense on all numeric fields via math.isfinite().
    - Thread-safe: all shared state access acquires self._lock.
    - Fail-closed: all error paths return BLOCKED decisions.
    - Bounded audit trail via McpAuditTrail.

    Args:
        config: The MCP governance configuration with tool policies.
    """

    def __init__(self, config: McpGovernanceConfig) -> None:
        self._config = config
        self._lock = threading.Lock()
        self._audit_trail = McpAuditTrail(
            max_entries=config.max_audit_entries,
        )
        # Mutable overlay for runtime tool registration
        self._policy_overlay: dict[str, McpToolPolicy] = {}
        # Rate tracking: "agent_id:tool_name" (isolation off / no tenant) OR
        # (tenant, agent_id, tool_name) (issue #1843, tenant resolved) -> deque
        # of timestamps. The tenant-keyed form is a TUPLE, not a colon-joined
        # string, so a tenant/agent_id/tool_name containing a literal ":" can
        # never collide two distinct principals into the same bucket (a
        # string-join would: tenant="a:b" -- see _check_rate_limit).
        self._rate_tracker: dict[_RateTrackerKey, deque[datetime]] = {}
        # Observed-time high-water of the last window-expiry GC sweep. None until
        # the first rate-limited check. Amortizes the O(n) silent-pair sweep so
        # the hot path stays O(1) between sweeps (see _gc_expired_rate_entries).
        self._last_rate_gc_ts: float | None = None

    @property
    def config(self) -> McpGovernanceConfig:
        """The governance configuration (read-only)."""
        return self._config

    @property
    def audit_trail(self) -> McpAuditTrail:
        """The audit trail for governance decisions."""
        return self._audit_trail

    def check_tool_call(
        self,
        context: McpActionContext,
        *,
        caller_identity: McpCallerIdentity | None = None,
    ) -> GovernanceDecision:
        """Main entry point: evaluate an MCP tool call against governance policies.

        Implements the verification gradient:
        0. Check tenant isolation (issue #1843, fail-closed) -- SKIPPED
           entirely when McpGovernanceConfig.tenant_grants is empty (isolation
           OFF, byte-neutral backward compatibility); when non-empty, the
           trusted caller_identity's tenant (or the self-asserted
           metadata["tenant_id"] fallback) must hold a grant for this tool.
           Evaluated BEFORE tool registration so isolation applies uniformly
           regardless of default_policy (DENY or ALLOW).
        1. Check if tool is registered (default-deny for unregistered)
        2. Validate numeric fields (NaN/Inf defense)
        3. Check argument constraints (denied_args, allowed_args)
        4. Check clearance requirement (Layer-2 authorization, fail-closed) --
           evaluated BEFORE cost so an unmet-clearance caller is BLOCKED
           regardless of cost band
        5. Check cost constraints (max_cost)
        6. Check rate limits (re-keyed on (tenant, agent_id, tool) when a
           tenant resolved -- see _check_rate_limit)
        7. Return appropriate gradient level

        Fail-closed: any exception during evaluation returns BLOCKED.

        Args:
            context: The MCP action context describing the tool call.
            caller_identity: The trusted caller identity resolved by the
                transport/auth layer, if any. Its tenant (when set)
                OVERWRITES any self-asserted context.metadata["tenant_id"]
                (impersonation defeat). None means no trusted identity was
                supplied -- the enforcer falls back to the self-asserted
                metadata channel.

        Returns:
            A GovernanceDecision with the verdict.
        """
        try:
            decision = self._evaluate(context, caller_identity)
        except Exception as exc:
            logger.warning(
                "McpGovernanceEnforcer: evaluation failed for tool '%s': %s",
                context.tool_name,
                exc,
            )
            decision = GovernanceDecision(
                level="blocked",
                tool_name=context.tool_name,
                agent_id=context.agent_id,
                reason="Internal error during governance check -- fail-closed to BLOCKED",
                timestamp=context.timestamp,
            )

        # Record audit entry if enabled
        if self._config.audit_enabled:
            self._audit_trail.record(
                tool_name=context.tool_name,
                agent_id=context.agent_id,
                decision=decision.level,
                reason=decision.reason,
                cost_estimate=context.cost_estimate,
                metadata={
                    "args_keys": sorted(context.args.keys()) if context.args else [],
                    **(context.metadata or {}),
                },
            )

        return decision

    def check_resource_read(
        self,
        context: McpResourceContext,
        *,
        caller_identity: McpCallerIdentity | None = None,
    ) -> GovernanceDecision:
        """Evaluate an MCP resources/read invocation against tenant isolation.

        Prior to issue #1843, resources/read had NO governance layer at all.
        This entry point adds ONLY the tenant-isolation check -- there is no
        cost, argument, clearance, or rate-limit governance layer for
        resources yet (out of scope for #1843; see check_tool_call for that
        richer contract on the tools/call surface).

        When McpGovernanceConfig.tenant_grants is empty (isolation OFF), every
        resource read is auto_approved unconditionally -- byte-identical to
        the pre-existing (fully-ungoverned) resources/read behavior. When
        non-empty, the SAME shared restrictiveness function tools/call uses
        (_tenant_isolation_decision / _tenant_grant_permits) fail-closes on an
        absent, unrecognized, or ungranted tenant.

        Fail-closed: any exception during evaluation returns BLOCKED.

        Args:
            context: The MCP resource context describing the resources/read
                invocation.
            caller_identity: The trusted caller identity resolved by the
                transport/auth layer, if any. Its tenant (when set)
                OVERWRITES any self-asserted context.metadata["tenant_id"]
                (impersonation defeat), mirroring check_tool_call.

        Returns:
            A GovernanceDecision with the verdict.
        """
        try:
            decision = self._tenant_isolation_decision(
                kind="resource",
                key=context.uri,
                agent_id=context.agent_id,
                timestamp=context.timestamp,
                metadata=context.metadata,
                caller_identity=caller_identity,
                verified_tenant=context.tenant,
            )
            if decision is None:
                decision = GovernanceDecision(
                    level="auto_approved",
                    tool_name="",
                    resource_uri=context.uri,
                    agent_id=context.agent_id,
                    reason=(
                        f"resource '{context.uri}' read is within tenant "
                        f"isolation constraints"
                    ),
                    timestamp=context.timestamp,
                )
        except Exception as exc:
            logger.warning(
                "McpGovernanceEnforcer: evaluation failed for resource '%s': %s",
                context.uri,
                exc,
            )
            decision = GovernanceDecision(
                level="blocked",
                tool_name="",
                resource_uri=context.uri,
                agent_id=context.agent_id,
                reason="Internal error during governance check -- fail-closed to BLOCKED",
                timestamp=context.timestamp,
            )

        if self._config.audit_enabled:
            self._audit_trail.record(
                tool_name="",
                agent_id=context.agent_id,
                decision=decision.level,
                reason=decision.reason,
                metadata={
                    "resource_uri": context.uri,
                    **(context.metadata or {}),
                },
            )

        return decision

    def _tenant_isolation_decision(
        self,
        *,
        kind: Literal["tool", "resource"],
        key: str,
        agent_id: str,
        timestamp: datetime,
        metadata: Mapping[str, Any],
        caller_identity: McpCallerIdentity | None,
        verified_tenant: str | None = None,
    ) -> GovernanceDecision | None:
        """Shared tenant-isolation gate for BOTH tools/call and resources/read.

        This is the single decision-building function BOTH _evaluate (Step
        0, tools/call) and check_resource_read (resources/read) call --
        security.md Enforcement-Surface Parity: one shared function so the
        two enforcement surfaces cannot silently diverge. ``verified_tenant``
        is the first-class server-verified context field (issue #1878),
        threaded in from both surfaces so the enforcement point reads the
        verified value.

        Returns None (isolation OFF, or tenant check satisfied -- caller
        continues) or a BLOCKED GovernanceDecision (fail-closed).
        """
        tenant_grants = self._config.tenant_grants
        if not tenant_grants:
            # Isolation OFF: skip entirely -- byte-neutral backward
            # compatibility (issue #1843 acceptance criterion).
            return None

        tenant = _resolve_effective_tenant(
            metadata,
            caller_identity,
            verified_tenant=verified_tenant,
            require_caller_identity=self._config.require_caller_identity,
        )
        if tenant is None:
            reason = (
                f"tenant isolation is enabled but no tenant was declared for "
                f"{kind} '{key}' -- BLOCKED (fail-closed)"
            )
        elif tenant not in tenant_grants:
            reason = (
                f"tenant '{tenant}' is not a recognized tenant -- BLOCKED "
                f"(fail-closed)"
            )
        elif not _tenant_grant_permits(tenant_grants, tenant, kind, key):
            reason = (
                f"tenant '{tenant}' is not granted access to {kind} '{key}' "
                f"-- BLOCKED (fail-closed)"
            )
        else:
            return None

        return GovernanceDecision(
            level="blocked",
            tool_name=key if kind == "tool" else "",
            resource_uri=key if kind == "resource" else None,
            agent_id=agent_id,
            reason=reason,
            timestamp=timestamp,
        )

    # Sliding-window width for rate limiting (seconds). Single source of truth
    # for both the per-key prune cutoff and the silent-pair GC cutoff.
    _RATE_LIMIT_WINDOW_SECONDS = 60.0
    # Amortization cadence for the window-expiry GC sweep (seconds of observed
    # time). The map is reclaimed at most once per interval so the hot path
    # stays O(1) between sweeps; the size cap is the within-burst backstop.
    _RATE_GC_INTERVAL_SECONDS = 60.0
    # Hard backstop: max distinct (agent, tool) pairs retained. Only reached
    # when more than this many pairs are simultaneously ACTIVE within one
    # window (GC cannot reclaim active pairs); bounds memory under that extreme.
    _MAX_RATE_TRACKER_ENTRIES = 10_000

    def register_tool(self, policy: McpToolPolicy) -> None:
        """Register or update a tool policy at runtime.

        Enforces monotonic tightening: if a policy already exists for this tool
        (either from config or a prior registration), the new policy must be
        equal to or more restrictive than the existing one.

        Thread-safe: acquires self._lock.

        Args:
            policy: The tool policy to register.

        Raises:
            ValueError: If the new policy would widen constraints relative to
                the existing policy (monotonic tightening violation).
        """
        with self._lock:
            existing = self._policy_overlay.get(policy.tool_name)
            if existing is None:
                existing = self._config.tool_policies.get(policy.tool_name)
            if existing is not None:
                self._validate_monotonic_tightening(existing, policy)
            self._policy_overlay[policy.tool_name] = policy

    @staticmethod
    def _validate_monotonic_tightening(
        existing: McpToolPolicy, new: McpToolPolicy
    ) -> None:
        """Verify that ``new`` is equal to or more restrictive than ``existing``.

        Checks:
        - max_cost: new must be <= existing (None means "no limit" = wider)
        - rate_limit: new must be <= existing (None means "no limit" = wider)
        - allowed_args: new must be subset of existing (empty means "any" = wider)
        - denied_args: new must be superset of existing (wider deny = tighter)
        - clearance_required: new must be equal-or-tighter than existing (None
          means "no requirement" = widest; an unrecognized value fail-closes to
          BLOCKED-for-all = tightest). Lowering or dropping it is widening.

        Raises:
            ValueError: On any widening.
        """
        # max_cost: None means unlimited (widest). A number is tighter.
        # new=None when existing has a number -> widening
        # new > existing -> widening
        if existing.max_cost is not None:
            if new.max_cost is None:
                raise ValueError(
                    f"Monotonic tightening violation: max_cost widened from "
                    f"{existing.max_cost} to None (unlimited) for tool "
                    f"'{new.tool_name}'"
                )
            if new.max_cost > existing.max_cost:
                raise ValueError(
                    f"Monotonic tightening violation: max_cost widened from "
                    f"{existing.max_cost} to {new.max_cost} for tool "
                    f"'{new.tool_name}'"
                )

        # rate_limit: None means unlimited (widest). A number is tighter.
        if existing.rate_limit is not None:
            if new.rate_limit is None:
                raise ValueError(
                    f"Monotonic tightening violation: rate_limit widened from "
                    f"{existing.rate_limit} to None (unlimited) for tool "
                    f"'{new.tool_name}'"
                )
            if new.rate_limit > existing.rate_limit:
                raise ValueError(
                    f"Monotonic tightening violation: rate_limit widened from "
                    f"{existing.rate_limit} to {new.rate_limit} for tool "
                    f"'{new.tool_name}'"
                )

        # allowed_args: empty means "any arg allowed" (widest).
        # Non-empty must be subset of existing (or equal).
        if existing.allowed_args:
            if not new.allowed_args:
                raise ValueError(
                    f"Monotonic tightening violation: allowed_args widened from "
                    f"{sorted(existing.allowed_args)} to empty (any) for tool "
                    f"'{new.tool_name}'"
                )
            if not new.allowed_args <= existing.allowed_args:
                extra = sorted(new.allowed_args - existing.allowed_args)
                raise ValueError(
                    f"Monotonic tightening violation: allowed_args widened with "
                    f"extra args {extra} for tool '{new.tool_name}'"
                )

        # denied_args: new must be superset of existing (wider deny = tighter).
        if existing.denied_args:
            if not existing.denied_args <= new.denied_args:
                missing = sorted(existing.denied_args - new.denied_args)
                raise ValueError(
                    f"Monotonic tightening violation: denied_args narrowed, "
                    f"missing {missing} for tool '{new.tool_name}'"
                )

        # clearance_required: None = no requirement (widest); a recognized level
        # is tighter as it rises; an unrecognized value fail-closes to
        # BLOCKED-for-all (tightest). A re-registration may only KEEP or RAISE
        # the bar -- dropping it (e.g. secret -> None) or lowering it
        # (secret -> public) silently strips the Layer-2 clearance gate, a
        # privilege escalation (pact-governance.md Rule 2: monotonic tightening).
        if _clearance_restrictiveness(
            new.clearance_required
        ) < _clearance_restrictiveness(existing.clearance_required):
            raise ValueError(
                f"Monotonic tightening violation: clearance_required widened "
                f"from {existing.clearance_required!r} to "
                f"{new.clearance_required!r} for tool '{new.tool_name}'"
            )

    def _get_policy(self, tool_name: str) -> McpToolPolicy | None:
        """Resolve the effective policy for a tool.

        Checks the mutable overlay first (runtime registrations), then
        the immutable config.

        Args:
            tool_name: The tool to look up.

        Returns:
            The McpToolPolicy, or None if not registered.
        """
        with self._lock:
            overlay = self._policy_overlay.get(tool_name)
            if overlay is not None:
                return overlay
        return self._config.tool_policies.get(tool_name)

    def _check_clearance(
        self, policy: McpToolPolicy, context: McpActionContext
    ) -> GovernanceDecision | None:
        """Fail-closed clearance gate for a tool whose policy requires one.

        Returns a BLOCKED GovernanceDecision when the caller's clearance is
        absent, unrecognized, or below the tool's ``clearance_required`` level;
        returns None when the requirement is satisfied (the caller continues to
        the remaining checks).

        Clearance levels are ConfidentialityLevel values ordered
        PUBLIC < RESTRICTED < CONFIDENTIAL < SECRET < TOP_SECRET. Any value that
        does not parse to a known level fails closed to BLOCKED -- both an
        unrecognized policy requirement and an unrecognized caller clearance.
        """
        tool_name = context.tool_name
        agent_id = context.agent_id
        required_raw = policy.clearance_required

        def _blocked(reason: str) -> GovernanceDecision:
            return GovernanceDecision(
                level="blocked",
                tool_name=tool_name,
                agent_id=agent_id,
                reason=reason,
                timestamp=context.timestamp,
                policy_snapshot=policy.to_dict(),
            )

        # Parse the REQUIRED level (fail-closed on an unrecognized requirement).
        try:
            required = ConfidentialityLevel(str(required_raw).strip().lower())
        except ValueError:
            return _blocked(
                f"tool '{tool_name}' policy clearance_required={required_raw!r} is "
                f"not a recognized confidentiality level -- fail-closed to BLOCKED"
            )

        # Absent caller clearance against a required level -> BLOCKED.
        caller_raw = context.caller_clearance
        if caller_raw is None:
            return _blocked(
                f"tool '{tool_name}' requires clearance '{required.value}' but the "
                f"caller provided none -- BLOCKED"
            )

        # Parse the CALLER level (fail-closed on an unrecognized caller value).
        try:
            caller = ConfidentialityLevel(str(caller_raw).strip().lower())
        except ValueError:
            return _blocked(
                f"caller clearance {caller_raw!r} is not a recognized "
                f"confidentiality level -- fail-closed to BLOCKED"
            )

        # Insufficient caller clearance -> BLOCKED.
        if caller < required:
            return _blocked(
                f"caller clearance '{caller.value}' is below the required "
                f"'{required.value}' for tool '{tool_name}' -- BLOCKED"
            )

        # Clearance satisfied; continue evaluation.
        return None

    def _evaluate(
        self,
        context: McpActionContext,
        caller_identity: McpCallerIdentity | None = None,
    ) -> GovernanceDecision:
        """Internal evaluation logic. Caller handles exceptions.

        Returns:
            A GovernanceDecision with the appropriate gradient level.
        """
        tool_name = context.tool_name
        agent_id = context.agent_id

        # Step 0: Check tenant isolation (issue #1843, fail-closed). SKIPPED
        # entirely when tenant_grants is empty (isolation OFF -- byte-neutral
        # backward compatibility); see _tenant_isolation_decision. Evaluated
        # BEFORE tool registration (Step 1) so tenant scoping applies
        # uniformly regardless of default_policy -- under DefaultPolicy.ALLOW
        # an unregistered tool short-circuits to auto_approved at Step 1 with
        # no further checks, so tenant isolation MUST run first or it would
        # never fire for any unregistered tool.
        tenant_decision = self._tenant_isolation_decision(
            kind="tool",
            key=tool_name,
            agent_id=agent_id,
            timestamp=context.timestamp,
            metadata=context.metadata,
            caller_identity=caller_identity,
            verified_tenant=context.tenant,
        )
        if tenant_decision is not None:
            return tenant_decision

        # Step 1: Check tool registration
        policy = self._get_policy(tool_name)
        if policy is None:
            if self._config.default_policy == DefaultPolicy.DENY:
                return GovernanceDecision(
                    level="blocked",
                    tool_name=tool_name,
                    agent_id=agent_id,
                    reason=f"Tool '{tool_name}' is not registered -- default-deny policy",
                    timestamp=context.timestamp,
                )
            else:
                # ALLOW default -- permitted but not governed
                return GovernanceDecision(
                    level="auto_approved",
                    tool_name=tool_name,
                    agent_id=agent_id,
                    reason=f"Tool '{tool_name}' is not registered -- default-allow policy",
                    timestamp=context.timestamp,
                )

        # Step 2: Validate cost_estimate (NaN/Inf defense)
        cost = context.cost_estimate
        if cost is not None:
            cost_float = float(cost)
            if not math.isfinite(cost_float):
                return GovernanceDecision(
                    level="blocked",
                    tool_name=tool_name,
                    agent_id=agent_id,
                    reason=f"cost_estimate is not finite ({cost_float!r}) -- fail-closed to BLOCKED",
                    timestamp=context.timestamp,
                    policy_snapshot=policy.to_dict(),
                )
            if cost_float < 0:
                return GovernanceDecision(
                    level="blocked",
                    tool_name=tool_name,
                    agent_id=agent_id,
                    reason=f"cost_estimate is negative ({cost_float}) -- fail-closed to BLOCKED",
                    timestamp=context.timestamp,
                    policy_snapshot=policy.to_dict(),
                )

        # Step 3: Check argument constraints
        if context.args:
            arg_names = set(context.args.keys())

            # Denied args take precedence
            if policy.denied_args:
                denied_found = arg_names & policy.denied_args
                if denied_found:
                    return GovernanceDecision(
                        level="blocked",
                        tool_name=tool_name,
                        agent_id=agent_id,
                        reason=(
                            f"Arguments {sorted(denied_found)} are denied by "
                            f"tool policy for '{tool_name}'"
                        ),
                        timestamp=context.timestamp,
                        policy_snapshot=policy.to_dict(),
                    )

            # If allowed_args is set, only those args are permitted
            if policy.allowed_args:
                disallowed = arg_names - policy.allowed_args
                if disallowed:
                    return GovernanceDecision(
                        level="blocked",
                        tool_name=tool_name,
                        agent_id=agent_id,
                        reason=(
                            f"Arguments {sorted(disallowed)} are not in the allowed "
                            f"set for tool '{tool_name}'"
                        ),
                        timestamp=context.timestamp,
                        policy_snapshot=policy.to_dict(),
                    )

        # Step 3.5: Check clearance requirement (Layer-2 authorization).
        # Evaluated BEFORE cost constraints (Step 4) so a caller with
        # absent/insufficient clearance is BLOCKED regardless of where its
        # cost_estimate falls -- in particular, a caller landing in the
        # (0.8*max_cost, max_cost] soft-flag band MUST NOT receive the
        # allowed-but-flagged decision before its clearance is checked.
        # Fail-closed: an unmet, absent, or unrecognized clearance BLOCKS.
        if policy.clearance_required is not None:
            clearance_decision = self._check_clearance(policy, context)
            if clearance_decision is not None:
                return clearance_decision

        # Step 4: Check cost constraints
        if cost is not None and policy.max_cost is not None:
            cost_float = float(cost)
            max_cost = float(policy.max_cost)

            if cost_float > max_cost:
                return GovernanceDecision(
                    level="blocked",
                    tool_name=tool_name,
                    agent_id=agent_id,
                    reason=(
                        f"cost_estimate (${cost_float:.2f}) exceeds max_cost "
                        f"(${max_cost:.2f}) for tool '{tool_name}'"
                    ),
                    timestamp=context.timestamp,
                    policy_snapshot=policy.to_dict(),
                )

            # Flagged if within 20% of max_cost
            if max_cost > 0 and cost_float > max_cost * 0.8:
                return GovernanceDecision(
                    level="flagged",
                    tool_name=tool_name,
                    agent_id=agent_id,
                    reason=(
                        f"cost_estimate (${cost_float:.2f}) is within 20% of max_cost "
                        f"(${max_cost:.2f}) for tool '{tool_name}'"
                    ),
                    timestamp=context.timestamp,
                    policy_snapshot=policy.to_dict(),
                )

        # Step 5: Check rate limits, re-keyed on (tenant, agent_id, tool) when
        # tenant isolation is enabled (issue #1843) -- see _check_rate_limit.
        # tenant_decision is None here (isolation OFF or tenant satisfied);
        # re-resolving is cheap and keeps this step's tenant self-contained.
        if policy.rate_limit is not None:
            rate_tenant = (
                _resolve_effective_tenant(
                    context.metadata,
                    caller_identity,
                    verified_tenant=context.tenant,
                    require_caller_identity=self._config.require_caller_identity,
                )
                if self._config.tenant_grants
                else None
            )
            rate_decision = self._check_rate_limit(
                agent_id, tool_name, policy.rate_limit, context.timestamp, rate_tenant
            )
            if rate_decision is not None:
                return rate_decision

        # All checks passed
        return GovernanceDecision(
            level="auto_approved",
            tool_name=tool_name,
            agent_id=agent_id,
            reason=f"Tool '{tool_name}' call is within all governance constraints",
            timestamp=context.timestamp,
            policy_snapshot=policy.to_dict(),
        )

    def _check_rate_limit(
        self,
        agent_id: str,
        tool_name: str,
        rate_limit: int,
        now: datetime,
        tenant: str | None = None,
    ) -> GovernanceDecision | None:
        """Check rate limit for a specific agent+tool combination.

        Thread-safe: acquires self._lock.

        Args:
            agent_id: The agent making the call.
            tool_name: The tool being invoked.
            rate_limit: Maximum invocations per minute.
            now: Current timestamp.
            tenant: The resolved tenant (issue #1843), if tenant isolation is
                enabled. When set, the tracking key is re-keyed on the TUPLE
                (tenant, agent_id, tool) -- not a colon-joined string, so a
                tenant/agent_id/tool_name containing a literal ":" can never
                collide two distinct principals into the same rate bucket --
                so two tenants sharing an agent_id + tool do NOT share a rate
                budget. None (the default -- isolation OFF, or no tenant
                resolved) preserves the pre-existing "agent_id:tool_name"
                string key format BYTE-FOR-BYTE -- backward compatibility for
                every caller that never passes a tenant.

        Returns:
            A BLOCKED GovernanceDecision if rate limit exceeded, None otherwise.
        """
        key: _RateTrackerKey = (
            (tenant, agent_id, tool_name) if tenant else f"{agent_id}:{tool_name}"
        )
        cutoff = now.timestamp() - self._RATE_LIMIT_WINDOW_SECONDS
        with self._lock:
            # Window-expiry GC: reclaim "silent" pairs whose sliding window has
            # fully expired so the map tracks CURRENTLY-ACTIVE pairs, not every
            # pair ever seen. Amortized; never evicts an in-window (active) pair.
            self._gc_expired_rate_entries(cutoff, now)

            if key not in self._rate_tracker:
                # Hard backstop: if STILL at the cap after GC (more than the cap
                # of simultaneously-active pairs), evict to bound memory.
                if len(self._rate_tracker) >= self._MAX_RATE_TRACKER_ENTRIES:
                    self._evict_oldest_rate_entries(cutoff)
                # Bounded deque for rate tracking
                self._rate_tracker[key] = deque(maxlen=rate_limit + 1)

            tracker = self._rate_tracker[key]

            # Prune entries older than the rate-limit window
            while tracker and tracker[0].timestamp() < cutoff:
                tracker.popleft()

            if len(tracker) >= rate_limit:
                return GovernanceDecision(
                    level="blocked",
                    tool_name=tool_name,
                    agent_id=agent_id,
                    reason=(
                        f"Rate limit exceeded: {len(tracker)} calls in last "
                        f"{int(self._RATE_LIMIT_WINDOW_SECONDS)}s "
                        f"(limit: {rate_limit}/min) for tool '{tool_name}'"
                    ),
                    timestamp=now,
                )

            # Record this invocation timestamp
            tracker.append(now)

        return None

    def _gc_expired_rate_entries(self, cutoff: float, now: datetime) -> None:
        """Evict rate-tracker entries whose sliding window has fully expired.

        A "silent" pair is one whose most-recent invocation is older than the
        rate-limit window: pruning its deque would empty it, so it contributes
        nothing to enforcement (re-creating the deque on the next call yields
        identical behavior) yet retains memory until the size cap forces
        eviction. This proactive sweep keeps the map sized to CURRENTLY-ACTIVE
        pairs -- bounded by active load, not by the total number of distinct
        pairs ever seen -- closing the silent-pair accumulation surface
        (issue #1440 / cross-SDK parity with kailash-rs#1491).

        Window-expiry eviction NEVER removes an active pair (one whose last
        invocation is within the window), so enforcement fidelity is preserved.

        Amortized: runs at most once per ``_RATE_GC_INTERVAL_SECONDS`` of
        observed time so the hot path stays O(1) between sweeps. Out-of-order
        (earlier) timestamps simply skip the sweep; the size cap remains the
        within-burst backstop.

        Must be called while holding self._lock.
        """
        now_ts = now.timestamp()
        last = self._last_rate_gc_ts
        if last is not None and (now_ts - last) < self._RATE_GC_INTERVAL_SECONDS:
            return
        self._last_rate_gc_ts = now_ts

        expired = [
            k
            for k, dq in self._rate_tracker.items()
            if not dq or dq[-1].timestamp() < cutoff
        ]
        for k in expired:
            del self._rate_tracker[k]

        if expired:
            # Schema-safe: log the COUNT only -- never the (agent_id, tool) keys
            # (PII-adjacent per observability.md Rule 8). DEBUG so an amortized
            # sweep cannot flood aggregators.
            logger.debug(
                "McpGovernanceEnforcer: rate-tracker GC evicted %d silent "
                "pair(s); %d active pair(s) remain",
                len(expired),
                len(self._rate_tracker),
            )

    def _evict_oldest_rate_entries(self, cutoff: float) -> None:
        """Hard-cap backstop: bound the rate tracker at the size cap.

        Frees ~10% of entries. Evicts expired-window entries FIRST (safe -- they
        hold no active rate state); only if that does not free enough does it
        fall back to evicting the least-recently-active entries. Reaching the
        LRU fallback means more than ``_MAX_RATE_TRACKER_ENTRIES`` pairs are
        simultaneously ACTIVE within one window -- an overload in which memory
        protection takes precedence over per-pair enforcement fidelity (a
        deliberate DoS bound).

        Must be called while holding self._lock.
        """
        if not self._rate_tracker:
            return

        target = max(1, len(self._rate_tracker) // 10)

        # 1) Expired-window entries first -- safe, they hold no active state.
        expired = [
            k
            for k, dq in self._rate_tracker.items()
            if not dq or dq[-1].timestamp() < cutoff
        ]
        for k in expired:
            del self._rate_tracker[k]
        if len(expired) >= target:
            return

        # 2) Still over budget -> evict least-recently-active as a last resort.
        # Empty deques sort to epoch so they are evicted first.
        epoch = datetime.min.replace(tzinfo=UTC)

        def _last_ts(k: _RateTrackerKey) -> datetime:
            dq = self._rate_tracker[k]
            return dq[-1] if dq else epoch

        remaining = target - len(expired)
        sorted_keys = sorted(self._rate_tracker.keys(), key=_last_ts)
        for k in sorted_keys[:remaining]:
            del self._rate_tracker[k]
