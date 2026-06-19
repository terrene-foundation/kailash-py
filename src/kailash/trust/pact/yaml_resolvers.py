# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Engine-application layer: resolve YAML governance specs to runtime types.

:func:`~kailash.trust.pact.yaml_loader.load_org_yaml` parses a unified YAML org
definition into a :class:`~kailash.trust.pact.yaml_loader.LoadedOrg` carrying
the ``OrgDefinition`` plus four governance-spec lists (``clearances``,
``envelopes``, ``bridges``, ``ksps``). Those specs hold RAW, pre-resolution
values (config role/unit ids, raw classification-level strings, constraint
dicts). This module is the layer that converts each ``*Spec`` to its runtime
type against a compiled organization and applies it to a live
:class:`~kailash.trust.pact.engine.GovernanceEngine` so YAML-authored governance
actually takes effect at enforcement time.

Every resolver fails CLOSED: an unresolvable address, an invalid classification
level, a NaN/Inf constraint, a path-traversal pattern, or a monotonic-tightening
violation raises (never silently skips), so a misauthored YAML org never
produces an engine that silently under-enforces.

Apply order (see :func:`apply_governance_specs`):

1. **clearances** -- independent; access decisions for SECRET/TOP_SECRET items
   depend on the requesting role's clearance, so grant them first.
2. **envelopes** -- applied parent-before-child (topological by the
   defining-role -> target-role chain) because
   :meth:`GovernanceEngine.set_role_envelope` validates each child against the
   defining role's EFFECTIVE envelope; a child applied before its parent would
   validate against a more-permissive structural default.
3. **bridges** -- a YAML-authored bridge expresses the org designer's intent,
   which IS the lowest-common-ancestor (LCA) approval that
   :meth:`GovernanceEngine.create_bridge` requires (fail-closed). The wiring
   therefore records the LCA approval (:meth:`GovernanceEngine.approve_bridge`)
   on the org author's behalf, then creates the bridge.
4. **ksps** -- no precondition. Deny-precedence (a matching-but-denying KSP
   suppressing a permissive bridge) is enforced at access time, so the
   bridge/KSP application order does not affect the decision.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from kailash.trust.pact.access import KnowledgeSharePolicy, PactBridge
from kailash.trust.pact.addressing import Address
from kailash.trust.pact.clearance import RoleClearance
from kailash.trust.pact.config import (
    ConfidentialityLevel,
    ConstraintEnvelopeConfig,
    GradientThresholdsConfig,
)
from kailash.trust.pact.envelopes import RoleEnvelope
from kailash.trust.pact.exceptions import PactError
from kailash.trust.pact.yaml_loader import (
    BridgeSpec,
    ClearanceSpec,
    ConfigurationError,
    EnvelopeSpec,
    KspSpec,
    LoadedOrg,
)

if TYPE_CHECKING:
    from kailash.trust.pact.compilation import CompiledOrg
    from kailash.trust.pact.engine import GovernanceEngine

logger = logging.getLogger(__name__)

__all__ = [
    "resolve_clearance",
    "resolve_envelope",
    "resolve_bridge",
    "resolve_ksp",
    "apply_governance_specs",
]

# Attribution recorded on clearances/KSPs resolved from a YAML org definition.
# The authority is the org-definition author (see apply_governance_specs'
# Security note); an empty grantor would read as "unknown/unattributed" in the
# audit trail, so we name the source explicitly.
_YAML_ORG_AUTHORITY = "yaml-org-definition"

# Cap on how many addresses an unresolved-reference error enumerates, so a
# caller that logs str(exc) cannot bleed the full org topology to aggregators
# (observability.md Rule 8 schema-revealing-names class).
_MAX_ADDRESS_SAMPLE = 20


# ---------------------------------------------------------------------------
# Shared resolution helpers (all fail-closed)
# ---------------------------------------------------------------------------


def _sample_addresses(compiled: CompiledOrg) -> str:
    """Render a bounded sample of known addresses for error messages."""
    addresses = sorted(compiled.nodes.keys())
    if len(addresses) <= _MAX_ADDRESS_SAMPLE:
        return f"{addresses}"
    shown = addresses[:_MAX_ADDRESS_SAMPLE]
    return f"{shown} (+{len(addresses) - _MAX_ADDRESS_SAMPLE} more)"


def _parse_level(raw: str, *, ctx: str) -> ConfidentialityLevel:
    """Map a raw level string to a ConfidentialityLevel, fail-closed."""
    try:
        return ConfidentialityLevel(raw)
    except ValueError as exc:
        valid = sorted(level.value for level in ConfidentialityLevel)
        raise ConfigurationError(
            f"{ctx}: invalid classification level '{raw}'. Valid levels: {valid}."
        ) from exc


def _resolve_role_address(compiled: CompiledOrg, role_id: str, *, ctx: str) -> str:
    """Resolve a config role id (or positional address) to a positional address.

    Accepts a value that is already a positional D/T/R address (returned
    unchanged) or a config ``role_id`` (resolved via the compiled org).
    Fail-closed: an unresolvable identifier raises ConfigurationError.
    """
    if role_id in compiled.nodes:
        return role_id
    node = compiled.get_node_by_role_id(role_id)
    if node is not None:
        return node.address
    raise ConfigurationError(
        f"{ctx}: cannot resolve role '{role_id}' to a positional address or "
        f"config role id in the compiled organization. "
        f"Known addresses (sample): {_sample_addresses(compiled)}."
    )


def _resolve_unit_address(compiled: CompiledOrg, unit_id: str, *, ctx: str) -> str:
    """Resolve a config dept/team id (or positional address) to a unit address.

    KSP source/target are authored as raw config unit ids; units carry
    positional addresses too (e.g. ``"D1-R1-D3"``). Fail-closed.
    """
    if unit_id in compiled.nodes:
        return unit_id
    node = compiled.get_node_by_unit_id(unit_id)
    if node is not None:
        return node.address
    raise ConfigurationError(
        f"{ctx}: cannot resolve unit '{unit_id}' to a positional address or "
        f"config department/team id in the compiled organization. "
        f"Known addresses (sample): {_sample_addresses(compiled)}."
    )


# ---------------------------------------------------------------------------
# Per-spec resolvers
# ---------------------------------------------------------------------------


def resolve_clearance(
    spec: ClearanceSpec, compiled: CompiledOrg
) -> tuple[str, RoleClearance]:
    """Resolve a ClearanceSpec to (role_address, RoleClearance). Fail-closed."""
    ctx = f"clearance for role '{spec.role_id}'"
    role_address = _resolve_role_address(compiled, spec.role_id, ctx=ctx)
    max_clearance = _parse_level(spec.level, ctx=ctx)
    clearance = RoleClearance(
        role_address=role_address,
        max_clearance=max_clearance,
        compartments=frozenset(spec.compartments),
        granted_by_role_address=_YAML_ORG_AUTHORITY,
        nda_signed=spec.nda_signed,
    )
    return role_address, clearance


def resolve_ksp(spec: KspSpec, compiled: CompiledOrg) -> KnowledgeSharePolicy:
    """Resolve a KspSpec to a KnowledgeSharePolicy. Fail-closed."""
    ctx = f"KSP '{spec.id}'"
    source = _resolve_unit_address(compiled, spec.source, ctx=f"{ctx} source")
    target = _resolve_unit_address(compiled, spec.target, ctx=f"{ctx} target")
    max_classification = _parse_level(spec.max_classification, ctx=ctx)
    shared_classifications = frozenset(
        _parse_level(level, ctx=f"{ctx} shared_classifications")
        for level in spec.shared_classifications
    )
    min_clearance = (
        _parse_level(spec.min_clearance, ctx=f"{ctx} min_clearance")
        if spec.min_clearance is not None
        else None
    )
    try:
        return KnowledgeSharePolicy(
            id=spec.id,
            source_unit_address=source,
            target_unit_address=target,
            max_classification=max_classification,
            compartments=frozenset(spec.compartments),
            shared_paths=tuple(spec.shared_paths),
            shared_types=frozenset(spec.shared_types),
            shared_classifications=shared_classifications,
            min_clearance=min_clearance,
            conditions=dict(spec.conditions),
            created_by_role_address=_YAML_ORG_AUTHORITY,
            active=True,
        )
    except (ValueError, PactError) as exc:
        # KnowledgeSharePolicy.__post_init__ rejects '..' traversal patterns.
        raise ConfigurationError(f"{ctx}: {exc}") from exc


def resolve_bridge(spec: BridgeSpec, compiled: CompiledOrg) -> PactBridge:
    """Resolve a BridgeSpec to a PactBridge. Fail-closed.

    Application (LCA approval) is handled by :func:`apply_governance_specs`.
    """
    ctx = f"bridge '{spec.id}'"
    role_a = _resolve_role_address(compiled, spec.role_a, ctx=f"{ctx} role_a")
    role_b = _resolve_role_address(compiled, spec.role_b, ctx=f"{ctx} role_b")
    max_classification = _parse_level(spec.max_classification, ctx=ctx)
    try:
        return PactBridge(
            id=spec.id,
            role_a_address=role_a,
            role_b_address=role_b,
            bridge_type=spec.bridge_type,
            max_classification=max_classification,
            bilateral=spec.bilateral,
        )
    except (ValueError, PactError) as exc:
        # PactBridge.__post_init__ rejects '..' traversal patterns.
        raise ConfigurationError(f"{ctx}: {exc}") from exc


def resolve_envelope(spec: EnvelopeSpec, compiled: CompiledOrg) -> RoleEnvelope:
    """Resolve an EnvelopeSpec to a RoleEnvelope. Fail-closed.

    The constraint dicts are coerced + validated by Pydantic
    (``ConstraintEnvelopeConfig`` / ``GradientThresholdsConfig``), which rejects
    NaN/Inf threshold values and unknown keys; any ValidationError is surfaced
    as a fail-closed ConfigurationError. Monotonic-tightening is validated when
    the envelope is applied (see :func:`apply_governance_specs`).
    """
    target = _resolve_role_address(
        compiled, spec.target, ctx=f"envelope target '{spec.target}'"
    )
    defining = _resolve_role_address(
        compiled, spec.defined_by, ctx=f"envelope defined_by '{spec.defined_by}'"
    )
    envelope_id = f"yaml-env-{spec.target}"
    config_kwargs: dict[str, Any] = {"id": envelope_id}
    if spec.financial is not None:
        config_kwargs["financial"] = spec.financial
    if spec.operational is not None:
        config_kwargs["operational"] = spec.operational
    if spec.temporal is not None:
        config_kwargs["temporal"] = spec.temporal
    if spec.data_access is not None:
        config_kwargs["data_access"] = spec.data_access
    if spec.communication is not None:
        config_kwargs["communication"] = spec.communication
    # Top-level governance fields beyond the five CARE dimensions. Pydantic
    # coerces the clearance string -> ConfidentialityLevel (its enum values are
    # exactly the loader's _VALID_CLEARANCE_LEVELS) and re-validates the gt=0
    # delegation-depth bound; a bad value surfaces as the fail-closed
    # ConfigurationError below. Forwarding these is what makes a YAML-authored
    # confidentiality ceiling / delegation cap actually reach enforcement
    # (issue #1386 follow-up — they were silently dropped before).
    if spec.confidentiality_clearance is not None:
        config_kwargs["confidentiality_clearance"] = spec.confidentiality_clearance
    if spec.max_delegation_depth is not None:
        config_kwargs["max_delegation_depth"] = spec.max_delegation_depth
    try:
        envelope_config = ConstraintEnvelopeConfig(**config_kwargs)
        gradient = (
            GradientThresholdsConfig(**spec.gradient_thresholds)
            if spec.gradient_thresholds is not None
            else None
        )
    except ValidationError as exc:
        raise ConfigurationError(
            f"envelope target '{spec.target}': invalid constraint config: {exc}"
        ) from exc
    return RoleEnvelope(
        id=envelope_id,
        defining_role_address=defining,
        target_role_address=target,
        envelope=envelope_config,
        gradient_thresholds=gradient,
    )


# ---------------------------------------------------------------------------
# Apply orchestrator
# ---------------------------------------------------------------------------


def _order_envelopes(
    specs: list[EnvelopeSpec], compiled: CompiledOrg
) -> list[EnvelopeSpec]:
    """Topologically order envelopes parent-before-child (fail-closed on cycle).

    Envelope E must be applied after envelope F when E's defining role IS F's
    target role -- i.e. the supervisor whose boundary E tightens is itself
    governed by a YAML envelope F. ``set_role_envelope`` validates each child
    against the defining role's effective envelope, so the parent must be in
    place first.
    """
    n = len(specs)
    targets: list[str] = []
    definings: list[str] = []
    for spec in specs:
        targets.append(
            _resolve_role_address(
                compiled, spec.target, ctx=f"envelope target '{spec.target}'"
            )
        )
        definings.append(
            _resolve_role_address(
                compiled,
                spec.defined_by,
                ctx=f"envelope defined_by '{spec.defined_by}'",
            )
        )
    by_target: dict[str, int] = {t: i for i, t in enumerate(targets)}

    # Edge parent -> child when child's defining role IS parent's target role,
    # so the parent envelope is applied first. child_indegree[i] counts how many
    # parents envelope i must wait for (0 or 1: a role has one defining role).
    children: list[list[int]] = [[] for _ in range(n)]
    child_indegree = [0] * n
    for i in range(n):
        parent = by_target.get(definings[i])
        if parent is not None and parent != i:
            children[parent].append(i)
            child_indegree[i] += 1

    queue = [i for i in range(n) if child_indegree[i] == 0]
    ordered: list[EnvelopeSpec] = []
    while queue:
        node = queue.pop(0)
        ordered.append(specs[node])
        for child in children[node]:
            child_indegree[child] -= 1
            if child_indegree[child] == 0:
                queue.append(child)

    if len(ordered) != n:
        cyclic = [specs[i].target for i in range(n) if child_indegree[i] > 0]
        raise ConfigurationError(
            f"envelope definitions form a cycle in the defining-role -> "
            f"target-role chain (cannot order parent-before-child): "
            f"targets involved {sorted(cyclic)}."
        )
    return ordered


def apply_governance_specs(engine: GovernanceEngine, loaded: LoadedOrg) -> None:
    """Apply every YAML-loaded governance spec to a live GovernanceEngine.

    Resolves each ``*Spec`` to its runtime type and applies it in the order
    clearances -> envelopes (parent-before-child) -> bridges (LCA-approved) ->
    ksps. Fail-closed throughout: any resolution or application error raises and
    aborts construction so a misauthored org never yields a silently
    under-enforcing engine. See the module docstring for the ordering rationale.

    Security -- the org-definition source is a TRUST ROOT. Authoring or
    modifying the YAML/dict an engine is built from confers full governance
    authority: it grants clearances, sets envelopes, mints KSPs, and (because a
    YAML-authored bridge IS the org designer's LCA approval) creates bridges
    WITHOUT the runtime's interactive LCA/compliance-approval ceremony. The org
    source MUST therefore be protected at the same level as signing keys
    (trusted provenance, restricted write access); never build an engine from
    an untrusted-input path. This is the same authority model the runtime
    ``approve_bridge`` gate assumes for the LCA role -- applied here to the
    org-definition author.
    """
    compiled = engine.get_org()

    # 1. Clearances (independent; access for classified items depends on them).
    for clearance_spec in loaded.clearances:
        role_address, clearance = resolve_clearance(clearance_spec, compiled)
        engine.grant_clearance(role_address, clearance)

    # 2. Envelopes, parent-before-child. set_role_envelope raises
    #    MonotonicTighteningError (widening) / ValueError (NaN/Inf) -- both
    #    propagate as fail-closed errors.
    for envelope_spec in _order_envelopes(list(loaded.envelopes), compiled):
        envelope = resolve_envelope(envelope_spec, compiled)
        engine.set_role_envelope(envelope)

    # 3. Bridges. A YAML-authored bridge expresses the org designer's intent,
    #    which IS the LCA approval create_bridge requires (fail-closed). Record
    #    that approval on the org author's behalf, then create the bridge.
    for bridge_spec in loaded.bridges:
        bridge = resolve_bridge(bridge_spec, compiled)
        _approve_and_create_bridge(engine, bridge)

    # 4. KSPs (no precondition; deny-precedence is an access-time concern).
    for ksp_spec in loaded.ksps:
        ksp = resolve_ksp(ksp_spec, compiled)
        engine.create_ksp(ksp)

    logger.info(
        "Applied YAML governance specs to engine '%s': "
        "%d clearances, %d envelopes, %d bridges, %d KSPs",
        engine.org_name,
        len(loaded.clearances),
        len(loaded.envelopes),
        len(loaded.bridges),
        len(loaded.ksps),
    )


def _approve_and_create_bridge(engine: GovernanceEngine, bridge: PactBridge) -> None:
    """Record the LCA approval for a YAML bridge, then create it (fail-closed).

    The org-definition author holds org-design authority, so a bridge declared
    in the YAML is the LCA's approval. We compute the LCA from the two role
    addresses and record the approval on its behalf before create_bridge (which
    fail-closes without a valid approval).
    """
    try:
        addr_a = Address.parse(bridge.role_a_address)
        addr_b = Address.parse(bridge.role_b_address)
    except Exception as exc:
        raise ConfigurationError(
            f"bridge '{bridge.id}': cannot parse role addresses "
            f"'{bridge.role_a_address}' / '{bridge.role_b_address}': {exc}"
        ) from exc

    lca = Address.lowest_common_ancestor(addr_a, addr_b)
    if lca is None:
        raise ConfigurationError(
            f"bridge '{bridge.id}': role addresses "
            f"'{bridge.role_a_address}' and '{bridge.role_b_address}' have no "
            f"common ancestor; a bridge requires an LCA to approve it."
        )

    engine.approve_bridge(bridge.role_a_address, bridge.role_b_address, str(lca))
    engine.create_bridge(bridge)
