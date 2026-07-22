# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""MCP governance types -- frozen dataclasses for tool policy, config, and action context.

All dataclasses are frozen=True (immutable after construction) per pact-governance.md
Rule 5 (MUST NOT Construct as Mutable). All numeric fields are validated with
math.isfinite() per pact-governance.md Rule 6.
"""

from __future__ import annotations

import logging
import math
import types as _builtin_types
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "DefaultPolicy",
    "McpActionContext",
    "McpCallerIdentity",
    "McpGovernanceConfig",
    "McpResourceContext",
    "McpTenantGrant",
    "McpToolPolicy",
]


class DefaultPolicy(str, Enum):
    """Default policy for unregistered tools."""

    DENY = "DENY"
    ALLOW = "ALLOW"


@dataclass(frozen=True)
class McpToolPolicy:
    """Policy for a single MCP tool.

    Defines what constraints apply when an agent invokes a specific MCP tool.
    frozen=True prevents mutation after construction.

    Attributes:
        tool_name: The MCP tool name this policy applies to.
        allowed_args: Frozenset of allowed argument name patterns. Empty means
            all arguments are allowed (no arg-level restriction).
        denied_args: Frozenset of explicitly denied argument name patterns.
            Takes precedence over allowed_args.
        max_cost: Maximum cost (USD) for a single invocation of this tool.
            None means no cost limit.
        clearance_required: Minimum confidentiality level required to invoke
            this tool. None means no clearance requirement.
        rate_limit: Maximum number of invocations per minute. None means
            no rate limit.
        description: Human-readable description of this policy.

    Raises:
        ValueError: If max_cost or rate_limit is NaN, Inf, or negative.
    """

    tool_name: str
    allowed_args: frozenset[str] = field(default_factory=frozenset)
    denied_args: frozenset[str] = field(default_factory=frozenset)
    max_cost: float | None = None
    clearance_required: str | None = None
    rate_limit: int | None = None
    description: str = ""

    def __post_init__(self) -> None:
        if not self.tool_name:
            raise ValueError("tool_name must not be empty")
        if self.max_cost is not None:
            cost = float(self.max_cost)
            if not math.isfinite(cost):
                raise ValueError(f"max_cost must be finite, got {self.max_cost!r}")
            if cost < 0:
                raise ValueError(
                    f"max_cost must be non-negative, got {self.max_cost!r}"
                )
        if self.rate_limit is not None:
            if self.rate_limit < 1:
                raise ValueError(f"rate_limit must be >= 1, got {self.rate_limit!r}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "tool_name": self.tool_name,
            "allowed_args": sorted(self.allowed_args),
            "denied_args": sorted(self.denied_args),
            "max_cost": self.max_cost,
            "clearance_required": self.clearance_required,
            "rate_limit": self.rate_limit,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> McpToolPolicy:
        """Deserialize from a dictionary."""
        return cls(
            tool_name=data["tool_name"],
            allowed_args=frozenset(data.get("allowed_args", [])),
            denied_args=frozenset(data.get("denied_args", [])),
            max_cost=data.get("max_cost"),
            clearance_required=data.get("clearance_required"),
            rate_limit=data.get("rate_limit"),
            description=data.get("description", ""),
        )


@dataclass(frozen=True)
class McpTenantGrant:
    """Per-tenant grant of MCP tool and resource access (issue #1843).

    Config-level allowlist entry: which tools (keyed on tool name) and which
    resources (keyed on URI) a tenant may reach. frozen=True prevents mutation
    after construction.

    Attributes:
        tenant: The tenant this grant applies to. Non-empty.
        tools: Frozenset of tool names this tenant may invoke via tools/call.
            Empty means this tenant is granted no tools.
        resources: Frozenset of resource URIs this tenant may read via
            resources/read. Empty means this tenant is granted no resources.

    Raises:
        ValueError: If tenant is empty, or tools/resources is a bare string
            or contains a non-string element (a bare string passed where an
            iterable of names was intended silently becomes a per-character
            frozenset via ``frozenset(str)`` -- this is an access-control
            allowlist, so that silent split is both a false-deny of the
            intended name AND a false-grant of the individual characters as
            tool/resource names; see security.md's redactor-contract framing
            of the analogous substring-matching failure mode).
    """

    tenant: str
    tools: frozenset[str] = field(default_factory=frozenset)
    resources: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not self.tenant:
            raise ValueError("tenant must not be empty")
        for field_name, value in (("tools", self.tools), ("resources", self.resources)):
            if isinstance(value, str):
                raise ValueError(
                    f"{field_name} must be an iterable of tool/resource "
                    f"names, not a bare string {value!r} -- frozenset(str) "
                    f"would silently split it into individual characters"
                )
            if not all(isinstance(item, str) for item in value):
                raise ValueError(
                    f"{field_name} must contain only strings, got {value!r}"
                )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "tenant": self.tenant,
            "tools": sorted(self.tools),
            "resources": sorted(self.resources),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> McpTenantGrant:
        """Deserialize from a dictionary.

        Raises ValueError on a bare-string "tools" / "resources" value
        BEFORE wrapping in frozenset() -- catching the type-confusion at the
        untrusted-deserialization boundary, one step earlier than
        __post_init__ can (by the time __post_init__ runs on this path, a
        bare string would already be a silently-wrong per-character
        frozenset, indistinguishable from a deliberate set of single-char
        names).
        """
        raw_tools = data.get("tools", [])
        raw_resources = data.get("resources", [])
        for field_name, raw_value in (
            ("tools", raw_tools),
            ("resources", raw_resources),
        ):
            if isinstance(raw_value, str):
                raise ValueError(
                    f"{field_name} must be a list of tool/resource names, "
                    f"not a bare string {raw_value!r} -- frozenset(str) "
                    f"would silently split it into individual characters"
                )
        return cls(
            tenant=data["tenant"],
            tools=frozenset(raw_tools),
            resources=frozenset(raw_resources),
        )


@dataclass(frozen=True)
class McpGovernanceConfig:
    """Configuration for MCP governance enforcement.

    Defines the default policy and per-tool policies for an MCP governance
    enforcer instance. frozen=True prevents mutation after construction.

    Attributes:
        default_policy: Whether unregistered tools are denied (DENY) or
            allowed (ALLOW). DENY is strongly recommended per pact-governance.md
            Rule 5 (default-deny tool registration).
        tool_policies: Mapping of tool name to McpToolPolicy.
        audit_enabled: Whether to record audit entries for tool invocations.
        max_audit_entries: Maximum audit trail entries (bounded collection).
        tenant_grants: Mapping of tenant to McpTenantGrant (issue #1843).
            ADDITIVE and OPTIONAL. Empty (the default) means tenant isolation
            is OFF -- tools/call and resources/read behave exactly as before
            this field existed (byte-neutral backward compatibility). A
            non-empty map turns isolation ON: every tools/call and
            resources/read invocation is then scoped to the caller's tenant,
            fail-closed on an absent, unrecognized, or ungranted tenant. See
            ``McpGovernanceEnforcer._tenant_isolation_decision`` (enforcer.py)
            -- the ONE shared restrictiveness function both surfaces call.
        require_caller_identity: When True (the default), the tenant resolver
            resolves the tenant ONLY from the server-verified context tenant or
            a trusted ``McpCallerIdentity``; an absent, or tenant-less, trusted
            identity resolves straight to no-tenant (fail-closed). SECURE BY
            DEFAULT: closes the bypass where a deployment sets tenant_grants but
            never wires caller_identity. As of issue #1919 the self-asserted
            ``metadata["tenant_id"]`` fallback is DEPRECATED and no longer
            honored in ANY mode: passing False no longer opts into a trusted
            metadata channel -- a caller that relied on it now receives a
            ``DeprecationWarning`` and the decision fails closed (no tenant
            resolved). False is retained only for the documented #1843
            weaker-mode surface and no longer grants the metadata channel.
            A no-op when tenant_grants is empty (isolation OFF).

    Raises:
        ValueError: If max_audit_entries is < 1, or a tenant_grants key does
            not match its McpTenantGrant.tenant.
    """

    default_policy: DefaultPolicy = DefaultPolicy.DENY
    tool_policies: dict[str, McpToolPolicy] = field(default_factory=dict)
    audit_enabled: bool = True
    max_audit_entries: int = 10_000
    tenant_grants: dict[str, McpTenantGrant] = field(default_factory=dict)
    require_caller_identity: bool = True

    def __post_init__(self) -> None:
        if self.max_audit_entries < 1:
            raise ValueError(
                f"max_audit_entries must be >= 1, got {self.max_audit_entries}"
            )
        # Validate each policy tool_name matches its dict key
        for key, policy in self.tool_policies.items():
            if key != policy.tool_name:
                raise ValueError(
                    f"tool_policies key '{key}' does not match "
                    f"policy.tool_name '{policy.tool_name}'"
                )
        # Validate each tenant grant's tenant matches its dict key.
        for key, grant in self.tenant_grants.items():
            if key != grant.tenant:
                raise ValueError(
                    f"tenant_grants key '{key}' does not match "
                    f"grant.tenant '{grant.tenant}'"
                )
        # C3: Replace mutable dict with immutable MappingProxyType.
        # Use object.__setattr__ because the dataclass is frozen.
        object.__setattr__(
            self,
            "tool_policies",
            _builtin_types.MappingProxyType(dict(self.tool_policies)),
        )
        object.__setattr__(
            self,
            "tenant_grants",
            _builtin_types.MappingProxyType(dict(self.tenant_grants)),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "default_policy": self.default_policy.value,
            "tool_policies": {
                name: policy.to_dict() for name, policy in self.tool_policies.items()
            },
            "audit_enabled": self.audit_enabled,
            "max_audit_entries": self.max_audit_entries,
            "tenant_grants": {
                name: grant.to_dict() for name, grant in self.tenant_grants.items()
            },
            "require_caller_identity": self.require_caller_identity,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> McpGovernanceConfig:
        """Deserialize from a dictionary."""
        policies = {}
        for name, pdata in data.get("tool_policies", {}).items():
            policies[name] = McpToolPolicy.from_dict(pdata)
        grants = {}
        for name, gdata in data.get("tenant_grants", {}).items():
            grants[name] = McpTenantGrant.from_dict(gdata)
        return cls(
            default_policy=DefaultPolicy(data.get("default_policy", "DENY")),
            tool_policies=policies,
            require_caller_identity=data.get("require_caller_identity", True),
            tenant_grants=grants,
            audit_enabled=data.get("audit_enabled", True),
            max_audit_entries=data.get("max_audit_entries", 10_000),
        )


@dataclass(frozen=True)
class McpActionContext:
    """Context for a single MCP tool invocation being evaluated.

    Carries all the information needed for the enforcer to make a governance
    decision about an MCP tool call. frozen=True prevents mutation.

    Attributes:
        tool_name: The MCP tool being invoked.
        args: Arguments being passed to the tool.
        agent_id: Identifier of the agent making the call.
        timestamp: When the invocation was initiated.
        cost_estimate: Estimated cost (USD) for this invocation.
            None means no cost estimate available.
        caller_clearance: The confidentiality clearance level held by the
            CALLER making this invocation (one of the ConfidentialityLevel
            values: "public", "restricted", "confidential", "secret",
            "top_secret"). None means the caller provided no clearance; a tool
            whose policy sets ``clearance_required`` is then BLOCKED (fail-closed).
            Mirrors how ``cost_estimate`` carries the caller-supplied cost.
        metadata: Additional context for governance evaluation. Carries the
            free-form, SELF-ASSERTED ``metadata["tenant_id"]`` channel
            (issue #1843) -- a caller-supplied value the enforcer treats as
            untrusted input. As of issue #1919 it is NEVER consulted for the
            tenant governance decision in ANY mode; a caller that still sets it
            under the deprecated ``require_caller_identity=False`` weaker mode
            receives a ``DeprecationWarning`` and the decision fails closed.
        tenant: The FIRST-CLASS, SERVER-VERIFIED tenant for this call (issue
            #1878), DISTINCT from the free-form ``metadata`` map. This is the
            AUTHORITATIVE tenant-isolation input: governance enforcement reads
            THIS field (highest trust), ranking it above the sidecar
            ``McpCallerIdentity``; the self-asserted ``metadata["tenant_id"]``
            is no longer a ranked resolution source (issue #1919). It is
            populated SERVER-SIDE at the
            network boundary from the authenticated transport/token (see
            ``from_network_transport`` and ``McpGovernanceMiddleware``), NEVER
            from the client wire body. Deliberately EXCLUDED from the wire
            serialization (``to_dict`` never emits it; ``from_dict`` never
            reads it) so a client cannot assert an arbitrary tenant by copying
            it into the request body, AND so the on-the-wire envelope stays
            byte-identical to the issue #1843 contract -- no cross-SDK wire
            lockstep is required (mirrors how ``McpCallerIdentity`` is
            deliberately non-serialized). None means no verified tenant was
            resolved; under active isolation that fails closed (BLOCKED).

    Raises:
        ValueError: If cost_estimate is NaN, Inf, or negative; or if tenant
            is neither a string nor None.
    """

    tool_name: str
    args: dict[str, Any] = field(default_factory=dict)
    agent_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    cost_estimate: float | None = None
    caller_clearance: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    tenant: str | None = None

    def __post_init__(self) -> None:
        if not self.tool_name:
            raise ValueError("tool_name must not be empty")
        if self.cost_estimate is not None:
            cost = float(self.cost_estimate)
            if not math.isfinite(cost):
                raise ValueError(
                    f"cost_estimate must be finite, got {self.cost_estimate!r}"
                )
            if cost < 0:
                raise ValueError(
                    f"cost_estimate must be non-negative, got {self.cost_estimate!r}"
                )
        # Defense-in-depth: the verified tenant is a dict-key for grant lookup;
        # a non-str value would silently never match. Mirror McpCallerIdentity.
        if self.tenant is not None and not isinstance(self.tenant, str):
            raise ValueError(
                f"tenant must be a string or None, got {type(self.tenant).__name__}"
            )
        # H3: Replace mutable dicts with immutable MappingProxyType.
        object.__setattr__(
            self,
            "args",
            _builtin_types.MappingProxyType(dict(self.args)),
        )
        object.__setattr__(
            self,
            "metadata",
            _builtin_types.MappingProxyType(dict(self.metadata)),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary.

        The first-class ``tenant`` field is DELIBERATELY omitted -- it is a
        server-verified, in-memory-only field (issue #1878), never part of
        the wire envelope, so the serialized bytes stay identical to the
        issue #1843 byte-neutral contract.
        """
        return {
            "tool_name": self.tool_name,
            "args": self.args,
            "agent_id": self.agent_id,
            "timestamp": self.timestamp.isoformat(),
            "cost_estimate": self.cost_estimate,
            "caller_clearance": self.caller_clearance,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> McpActionContext:
        """Deserialize from a dictionary.

        NEVER populates the server-verified ``tenant`` field from ``data`` --
        a wire body cannot set the verified tenant (issue #1878). Use
        ``from_network_transport`` at the network boundary to populate the
        verified field from the authenticated transport/token.
        """
        ts = data.get("timestamp")
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        return cls(
            tool_name=data["tool_name"],
            args=data.get("args", {}),
            agent_id=data.get("agent_id", ""),
            timestamp=ts or datetime.now(UTC),
            cost_estimate=data.get("cost_estimate"),
            caller_clearance=data.get("caller_clearance"),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def from_network_transport(
        cls,
        data: dict[str, Any],
        *,
        verified_tenant: str | None = None,
    ) -> McpActionContext:
        """Deserialize an UNTRUSTED wire body at the network boundary (#1878).

        This is the deserializer a network transport (HTTP/SSE/WebSocket) MUST
        use for a client-supplied body. Unlike ``from_dict`` it:

        * STRIPS any body-supplied top-level ``tenant`` / ``tenant_id`` key --
          a client cannot set the verified field by putting it in the body.
        * STRIPS ``metadata["tenant_id"]`` -- the self-asserted tenant channel
          is not trusted on a network transport; the verified field replaces
          it.
        * Sets the first-class ``tenant`` field ONLY from ``verified_tenant``,
          which the caller resolves from the AUTHENTICATED transport/token
          (NOT the request body). None means the transport resolved no tenant
          -- under active isolation the enforcer then fails closed.

        Args:
            data: The untrusted, client-supplied wire body.
            verified_tenant: The server-verified tenant from the authenticated
                transport/token, or None if none resolved.
        """
        ts = data.get("timestamp")
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        raw_metadata = data.get("metadata", {})
        # Strip the self-asserted tenant_id from the body metadata -- it is
        # never trusted on a network transport.
        scrubbed_metadata = {
            k: v for k, v in dict(raw_metadata).items() if k != "tenant_id"
        }
        return cls(
            tool_name=data["tool_name"],
            args=data.get("args", {}),
            agent_id=data.get("agent_id", ""),
            timestamp=ts or datetime.now(UTC),
            cost_estimate=data.get("cost_estimate"),
            caller_clearance=data.get("caller_clearance"),
            metadata=scrubbed_metadata,
            # NEVER data.get("tenant") -- the body cannot set the verified field.
            tenant=verified_tenant,
        )


@dataclass(frozen=True)
class McpResourceContext:
    """Context for a single MCP ``resources/read`` invocation being evaluated.

    Sibling of :class:`McpActionContext`, keyed on resource URI rather than
    tool name. frozen=True prevents mutation. Introduced for issue #1843
    (first-class tenant isolation): prior to this, resources/read had NO
    governance layer at all -- this context is the enforcement entry point
    for :meth:`McpGovernanceEnforcer.check_resource_read`, which currently
    performs ONLY the tenant-isolation check (fail-closed when the enforcer's
    ``McpGovernanceConfig.tenant_grants`` is non-empty; auto-approved,
    unconditionally, when it is empty -- byte-identical to the pre-existing,
    fully-ungoverned resources/read behavior).

    Attributes:
        uri: The MCP resource URI being read.
        agent_id: Identifier of the agent making the call.
        timestamp: When the invocation was initiated.
        metadata: Additional context for governance evaluation. Carries the
            same free-form, self-asserted ``metadata["tenant_id"]`` channel
            as :attr:`McpActionContext.metadata` -- never consulted for the
            tenant decision in any mode (issue #1919); exercising it under the
            deprecated weaker mode emits a ``DeprecationWarning``.
        tenant: The FIRST-CLASS, SERVER-VERIFIED tenant for this resource read
            (issue #1878), DISTINCT from the free-form ``metadata`` map and
            the authoritative tenant-isolation input -- see
            :attr:`McpActionContext.tenant` for the full contract. Populated
            server-side at the network boundary; EXCLUDED from the wire
            serialization (byte-neutral). None fails closed under active
            isolation.

    Raises:
        ValueError: If uri is empty; or if tenant is neither a string nor None.
    """

    uri: str
    agent_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)
    tenant: str | None = None

    def __post_init__(self) -> None:
        if not self.uri:
            raise ValueError("uri must not be empty")
        if self.tenant is not None and not isinstance(self.tenant, str):
            raise ValueError(
                f"tenant must be a string or None, got {type(self.tenant).__name__}"
            )
        object.__setattr__(
            self,
            "metadata",
            _builtin_types.MappingProxyType(dict(self.metadata)),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary.

        The first-class ``tenant`` field is DELIBERATELY omitted (issue
        #1878) -- server-verified, in-memory-only, never on the wire.
        """
        return {
            "uri": self.uri,
            "agent_id": self.agent_id,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> McpResourceContext:
        """Deserialize from a dictionary.

        NEVER populates the server-verified ``tenant`` field from ``data``
        (issue #1878); use ``from_network_transport`` at the network boundary.
        """
        ts = data.get("timestamp")
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        return cls(
            uri=data["uri"],
            agent_id=data.get("agent_id", ""),
            timestamp=ts or datetime.now(UTC),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def from_network_transport(
        cls,
        data: dict[str, Any],
        *,
        verified_tenant: str | None = None,
    ) -> McpResourceContext:
        """Deserialize an UNTRUSTED wire body at the network boundary (#1878).

        Strips any body-supplied top-level ``tenant`` and
        ``metadata["tenant_id"]``; sets the verified ``tenant`` field ONLY
        from ``verified_tenant`` (the authenticated transport/token). See
        :meth:`McpActionContext.from_network_transport` for the full contract.
        """
        ts = data.get("timestamp")
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        raw_metadata = data.get("metadata", {})
        scrubbed_metadata = {
            k: v for k, v in dict(raw_metadata).items() if k != "tenant_id"
        }
        return cls(
            uri=data["uri"],
            agent_id=data.get("agent_id", ""),
            timestamp=ts or datetime.now(UTC),
            metadata=scrubbed_metadata,
            tenant=verified_tenant,
        )


@dataclass(frozen=True)
class McpCallerIdentity:
    """Trusted caller identity for MCP tenant-isolation enforcement (#1843).

    Resolved by the transport/auth layer BEFORE governance evaluation --
    e.g. from a verified session token or an mTLS client certificate -- and
    passed alongside the request context to
    :meth:`McpGovernanceEnforcer.check_tool_call` /
    :meth:`McpGovernanceEnforcer.check_resource_read`.

    Deliberately carries NO ``to_dict()`` / ``from_dict()``: this object is
    NOT part of the wire-serialized MCP envelope (``McpActionContext`` /
    ``McpResourceContext`` stay frozen -- byte-neutral per the issue #1843
    contract). Its ``tenant`` is the AUTHORITATIVE tenant for the call when no
    server-verified context tenant is present -- the impersonation-defeat
    mechanism: a caller cannot widen its own access by putting a different
    tenant in the request body, because the self-asserted
    ``metadata["tenant_id"]`` is no longer consulted for tenant resolution
    (issue #1919).

    Attributes:
        agent_id: Identifier of the authenticated agent/caller.
        tenant: The tenant this caller was authenticated as. None means the
            transport layer did not resolve a tenant for this caller; under
            active isolation the decision then fails closed -- the
            self-asserted ``metadata["tenant_id"]`` is no longer consulted
            (issue #1919).

    Raises:
        ValueError: If tenant is not a string or None.
    """

    agent_id: str = ""
    tenant: str | None = None

    def __post_init__(self) -> None:
        # Symmetric with the untrusted metadata["tenant_id"] path in
        # _resolve_effective_tenant (enforcer.py), which guards with
        # isinstance(..., str) -- this trusted construction path gets the
        # same defense-in-depth rather than silently carrying a non-str
        # tenant through to a dict-key lookup that would just never match.
        if self.tenant is not None and not isinstance(self.tenant, str):
            raise ValueError(
                f"tenant must be a string or None, got " f"{type(self.tenant).__name__}"
            )
