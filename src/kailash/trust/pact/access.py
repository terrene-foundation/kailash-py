# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Access enforcement -- 5-step algorithm combining addresses, clearance, and bridges.

Implements the PACT access enforcement algorithm:
    Step 1: Resolve role clearance (fail if missing or non-ACTIVE vetting)
    Step 2: Classification check (effective clearance >= item classification)
    Step 3: Compartment check (SECRET/TOP_SECRET: role must hold all item compartments)
    Step 4: Containment check (5 sub-paths):
        4a: Same unit -> ALLOW
        4b: Downward (role address is prefix of item owner) -> ALLOW
        4c: T-inherits-D (role in T, item in parent D) -> ALLOW
        4d: KSP exists -> ALLOW up to KSP max_classification
        4e: Bridge exists -> ALLOW up to bridge max_classification
    Step 5: No access path found -> DENY (fail-closed)

DEFAULT IS DENY. This is fail-closed by design.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from kailash.trust.pact.clearance import (
    _CLEARANCE_ORDER,
    RoleClearance,
    VettingStatus,
    effective_clearance,
)
from kailash.trust.pact.compilation import CompiledOrg
from kailash.trust.pact.config import ConfidentialityLevel, TrustPostureLevel
from kailash.trust.pact.knowledge import KnowledgeItem

logger = logging.getLogger(__name__)

__all__ = [
    "AccessDecision",
    "KnowledgeSharePolicy",
    "PactBridge",
    "can_access",
]


# ---------------------------------------------------------------------------
# Path scoping + condition helpers (shared by KSP and bridge enforcement)
# ---------------------------------------------------------------------------

# Recognized KSP condition keys. An unrecognized key fails closed at access
# time so a policy author cannot set a condition the engine silently ignores.
_KNOWN_CONDITION_KEYS: frozenset[str] = frozenset({"time_window", "environment"})

# Strict zero-padded 24h HH:MM (00:00-23:59). A time_window bound that is a
# str but NOT this exact shape MUST fail closed -- a non-padded value like
# "9" sorts lexicographically ABOVE "17" and would silently invert the
# window comparison into a grant (the strftime("%H:%M") current-time is
# always zero-padded, so only zero-padded bounds compare correctly).
_HHMM_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _path_has_traversal(path: str) -> bool:
    """Return True if a path contains a ``..`` segment (traversal attempt).

    Knowledge paths are LOGICAL, ``/``-delimited identifiers (e.g.
    ``/finance/q3``), NOT filesystem paths: there is no OS path resolution,
    no URL-decoding layer, and ``\\`` is an ordinary character, not a
    separator. The guard therefore splits on ``/`` only and rejects a literal
    ``..`` segment. This is the same `".." in path.split("/")` invariant the
    envelope data-access path uses (engine.py).
    """
    return ".." in path.split("/")


def _reject_traversal_patterns(patterns: tuple[str, ...], *, owner: str) -> None:
    """Raise ValueError if any pattern contains a ``..`` segment (fail-closed).

    Called from KnowledgeSharePolicy / PactBridge ``__post_init__`` so a
    policy carrying a path-traversal pattern can never be constructed,
    stored, or round-tripped.
    """
    for pat in patterns:
        if _path_has_traversal(pat):
            raise ValueError(
                f"{owner}: shared_paths pattern {pat!r} contains a '..' "
                f"traversal segment (rejected fail-closed)"
            )


def _path_matches(item_path: str | None, patterns: tuple[str, ...]) -> bool:
    """Check whether an item path matches any of the (non-empty) patterns.

    Grammar:
        ``*``         -> matches any (non-traversal) path
        ``prefix/*``  -> matches ``prefix`` and anything under ``prefix/``
        ``exact``     -> matches only the exact path

    Fail-closed: returns False when ``item_path`` is None (untagged item) or
    contains a ``..`` segment, and skips any pattern that contains ``..``.
    Callers MUST only invoke this when ``patterns`` is non-empty -- an empty
    pattern collection means "no narrowing" and is handled by the caller.
    """
    if item_path is None:
        return False
    if _path_has_traversal(item_path):
        return False
    for pat in patterns:
        if _path_has_traversal(pat):
            # Defense in depth: __post_init__ rejects these at construction,
            # but a hand-built / deserialized policy could still carry one.
            continue
        if pat == "*":
            return True
        if pat.endswith("/*"):
            prefix = pat[:-2]
            if item_path == prefix or item_path.startswith(prefix + "/"):
                return True
        elif item_path == pat:
            return True
    return False


def _time_in_window(now: datetime, window: Any) -> bool | None:
    """Evaluate whether ``now`` falls within a {"start","end"} HH:MM window.

    Returns True/False for a well-formed window, or None if the window is
    malformed (caller treats None as fail-closed). Overnight ranges
    (start > end, e.g. 22:00-06:00) are supported.
    """
    if not isinstance(window, dict):
        return None
    start = window.get("start")
    end = window.get("end")
    if not isinstance(start, str) or not isinstance(end, str):
        return None
    # A str-typed-but-non-HH:MM bound (e.g. "9", "25:00") must fail closed:
    # lexicographic comparison against the zero-padded current time would
    # otherwise silently invert the window into a grant (zero-tolerance 3c).
    if not _HHMM_RE.match(start) or not _HHMM_RE.match(end):
        return None
    current = now.strftime("%H:%M")
    if start <= end:
        return start <= current <= end
    # Overnight range: in-window if at/after start OR at/before end
    return current >= start or current <= end


# ---------------------------------------------------------------------------
# KnowledgeSharePolicy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KnowledgeSharePolicy:
    """A policy granting one organizational unit read access to another's knowledge.

    KSPs are directional: source_unit shares knowledge WITH target_unit.
    The max_classification caps what classification level may be shared.

    Scope fields (``shared_paths`` / ``shared_types`` / ``shared_classifications``
    / ``min_clearance`` / ``conditions``) are NARROWING filters: an empty
    collection (or ``None``) means "no narrowing on this dimension" and
    preserves the policy's broad grant; a non-empty value means an item
    must satisfy that dimension to be granted. A KSP that matches the
    source/target addressing but fails ANY narrowing filter is a
    *matching-but-denying* KSP and suppresses the bridge fallback
    (see ``_check_ksps`` deny-precedence).

    Attributes:
        id: Unique policy identifier.
        source_unit_address: D/T prefix sharing knowledge.
        target_unit_address: D/T prefix receiving access.
        max_classification: Maximum classification level shared (ceiling).
        compartments: Restrict sharing to specific compartments (empty = all).
            This is a per-KSP NARROWING filter (enforced at step 4d as the
            7th narrowing condition), NOT a hard compartment ceiling on the
            source->target edge: an item is shareable under THIS KSP only if
            every compartment it carries is authorized here
            (``item.compartments`` subset of this set). Like the other
            narrowing conditions, it composes under KSP deny-precedence
            (#1372) -- a sibling KSP that affirmatively grants (e.g. one with
            empty ``compartments``) still wins, so this field narrows THIS
            policy, it does not ceiling the edge. The absolute compartment
            ceiling for SECRET/TOP_SECRET items is the step-3 clearance check
            (the requesting role's clearance must independently hold every
            item compartment), which no KSP composition can bypass.
        created_by_role_address: Role that created this policy (audit trail).
        active: Whether this policy is currently active.
        expires_at: When this policy expires (None = no expiry).
        min_clearance: Recipient clearance floor -- the requesting role's
            ``max_clearance`` MUST be at or above this level. ``None`` = no
            floor (any cleared recipient that passes the global checks).
        shared_paths: Path-prefix patterns the shared item path must match
            (``*`` = all, ``prefix/*`` = prefix match, exact match otherwise).
            Empty = no path narrowing. A pattern containing a ``..`` segment
            is rejected at construction (fail-closed).
        shared_types: Set of knowledge types the item type must be a member
            of. Empty = no type narrowing.
        shared_classifications: Set of classification levels the item
            classification must be a member of. Empty = ceiling-only
            (``max_classification``). When non-empty, membership is required
            IN ADDITION to the ceiling -- expresses a non-contiguous allowed
            set (e.g. {RESTRICTED, CONFIDENTIAL} but not SECRET).
        conditions: Request-context conditions evaluated at access time.
            Supported keys: ``"time_window"`` ({"start": "HH:MM", "end":
            "HH:MM"}, evaluated against the ``now`` arg, overnight ranges
            supported) and ``"environment"`` (a dict of required key->value
            pairs matched against the ``environment`` arg). An unrecognized
            condition key is rejected fail-closed at access time.
    """

    id: str
    source_unit_address: str  # D/T prefix sharing knowledge
    target_unit_address: str  # D/T prefix receiving access
    max_classification: ConfidentialityLevel
    compartments: frozenset[str] = field(default_factory=frozenset)
    created_by_role_address: str = ""
    active: bool = True
    expires_at: datetime | None = None
    min_clearance: ConfidentialityLevel | None = None
    shared_paths: tuple[str, ...] = ()
    shared_types: frozenset[str] = field(default_factory=frozenset)
    shared_classifications: frozenset[ConfidentialityLevel] = field(
        default_factory=frozenset
    )
    conditions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Reject ``..`` traversal segments in shared_paths (fail-closed)."""
        _reject_traversal_patterns(self.shared_paths, owner=f"KSP '{self.id}'")


# ---------------------------------------------------------------------------
# PactBridge
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PactBridge:
    """A Cross-Functional Bridge connecting two roles across organizational boundaries.

    Bridges grant role-level access paths. A Standing bridge is permanent,
    a Scoped bridge is limited to specific operations, and an Ad-Hoc bridge
    is temporary.

    When bilateral=True, both roles can access each other's unit data.
    When bilateral=False, only role_a can access role_b's unit data
    (unilateral: A reads B, but B cannot read A).

    Attributes:
        id: Unique bridge identifier.
        role_a_address: First role in the bridge.
        role_b_address: Second role in the bridge.
        bridge_type: One of "standing", "scoped", "ad_hoc".
        max_classification: Maximum classification accessible via this bridge.
        operational_scope: Limit bridge to specific operations (empty = all).
        bilateral: Whether both roles have mutual access.
        expires_at: When this bridge expires (None = no expiry).
        active: Whether this bridge is currently active.
        shared_paths: Path patterns the shared item path must match
            (``*`` = all, ``prefix/*`` = prefix match, exact match otherwise).
            Empty = no path narrowing (preserves the bridge's broad grant).
            A pattern containing a ``..`` segment is rejected at construction
            (fail-closed); an item path containing ``..`` is denied at
            enforcement time.
    """

    id: str
    role_a_address: str
    role_b_address: str
    bridge_type: str  # "standing", "scoped", "ad_hoc"
    max_classification: ConfidentialityLevel
    operational_scope: tuple[str, ...] = ()
    bilateral: bool = True
    expires_at: datetime | None = None
    active: bool = True
    shared_paths: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Reject ``..`` traversal segments in shared_paths (fail-closed)."""
        _reject_traversal_patterns(self.shared_paths, owner=f"bridge '{self.id}'")


# ---------------------------------------------------------------------------
# AccessDecision
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AccessDecision:
    """The result of a can_access() evaluation.

    Attributes:
        allowed: Whether access is granted.
        reason: Human-readable explanation of the decision.
        step_failed: Which step (1-5) denied access, or None if allowed.
        audit_details: Structured details for audit logging.
        valid_until: When this access decision expires, based on the
            minimum expiry of any KSP or bridge that granted access.
            None means no expiry (structural access or permanent policy).
            Only set for ALLOW decisions via KSP or bridge paths.
    """

    allowed: bool
    reason: str
    step_failed: int | None = None  # 1-5, or None if allowed
    audit_details: dict[str, Any] = field(default_factory=dict)
    valid_until: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict suitable for JSON encoding.

        Returns:
            A dict representation of this access decision.
            Datetimes serialize as ``.isoformat()``.
        """
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "step_failed": self.step_failed,
            "audit_details": self.audit_details,
            "valid_until": (
                self.valid_until.isoformat() if self.valid_until is not None else None
            ),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AccessDecision:
        """Deserialize from a dictionary.

        Args:
            data: Dict with serialized AccessDecision fields.

        Returns:
            An AccessDecision instance.

        Raises:
            KeyError: If required fields are missing.
        """
        valid_until = data.get("valid_until")
        if isinstance(valid_until, str):
            valid_until = datetime.fromisoformat(valid_until)
        return cls(
            allowed=data["allowed"],
            reason=data["reason"],
            step_failed=data.get("step_failed"),
            audit_details=data.get("audit_details", {}),
            valid_until=valid_until,
        )


@dataclass(frozen=True)
class KspDenyDetail:
    """Structured deny-context for a single failing KSP narrowing condition.

    A *matching-but-denying* KSP (one whose source/target addressing matched
    but which failed a narrowing filter) carries this structured detail so the
    deny is SIEM-queryable, mirroring the discrete audit fields the step-3
    clearance compartment-deny already emits. The ``code`` discriminator names
    WHICH condition failed; ``message`` is the human-readable string preserved
    for backward compatibility; ``fields`` carries the discrete, queryable
    values for that condition (e.g. ``missing_compartments``), spread as
    top-level keys into the deny ``AccessDecision.audit_details``.

    Attributes:
        code: Which narrowing condition failed. One of
            ``"classification_ceiling"``, ``"classification_set"``,
            ``"min_clearance"``, ``"path_scope"``, ``"type_scope"``,
            ``"condition"``, ``"compartment_scope"``.
        message: Human-readable deny reason (back-compat with the prior
            string return of ``_evaluate_ksp_conditions``).
        fields: Discrete, machine-queryable values for the failed condition.
    """

    code: str
    message: str
    fields: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Knowledge cascade helper functions
# ---------------------------------------------------------------------------


def _get_containment_unit(role_address: str, compiled_org: CompiledOrg) -> str | None:
    """Find the nearest D or T ancestor for a role address.

    Walks backward through the address segments to find the most specific
    D or T unit the role belongs to.

    For example:
        D1-R1-D2-R1-T1-R1 -> "D1-R1-D2-R1-T1" (the team)
        D1-R1-D2-R1 -> "D1-R1-D2" (the department)
        D1-R1 -> "D1" (the top department)
        R1 -> None (standalone role, no containment unit)
    """
    parts = role_address.split("-")
    # Walk backward to find the last D or T segment
    for i in range(len(parts) - 1, -1, -1):
        seg = parts[i]
        if seg and seg[0] in ("D", "T"):
            return "-".join(parts[: i + 1])
    return None


def _is_same_unit(
    role_address: str,
    item_owning_address: str,
    compiled_org: CompiledOrg,
) -> bool:
    """Check if the role is in the same organizational unit as the item owner.

    A role is in the same unit if its containment unit (nearest D or T ancestor)
    matches the item's owning unit address or is a prefix match.

    Args:
        role_address: The D/T/R address of the requesting role.
        item_owning_address: The D/T address that owns the knowledge item.
        compiled_org: The compiled organization for structural lookups.

    Returns:
        True if the role is within the item's owning unit.
    """
    role_unit = _get_containment_unit(role_address, compiled_org)
    if role_unit is None:
        return False

    # Exact match: role's containment unit is the item's owning unit
    if role_unit == item_owning_address:
        return True

    # The role's unit is a child of the item's owning unit AND
    # the role address starts with the item owner (structural containment)
    if role_unit.startswith(item_owning_address + "-"):
        return True

    return False


def _is_downward(role_address: str, item_owning_address: str) -> bool:
    """Check if the role address is an ancestor of the item owning address.

    A role at D1-R1 has downward visibility to everything under D1-R1-*,
    including D1-R1-T1, D1-R1-D2, etc.

    Args:
        role_address: The D/T/R address of the requesting role.
        item_owning_address: The D/T address that owns the knowledge item.

    Returns:
        True if the role address is a proper prefix of the item owner address.
    """
    # role_address must be a prefix of item_owning_address
    # e.g., "D1-R1" is a prefix of "D1-R1-T1" or "D1-R1-D2"
    if item_owning_address.startswith(role_address + "-"):
        return True
    return False


def _t_inherits_d(
    role_address: str,
    item_owning_address: str,
    compiled_org: CompiledOrg,
) -> bool:
    """Check if a role in a Team (T) can access its parent Department (D) data.

    T-inherits-D: roles in a team inherit read access to data owned by
    the department that contains the team.

    For example, if role is at D1-R1-D2-R1-T1-R1 (in team T1 under dept D2),
    and the item is owned by D1-R1-D2 (dept D2), then the role inherits access
    because T1 is contained within D2.

    Additionally, the role might be deeply nested. We walk up the role's ancestry
    to find any D prefix that matches the item's owning address.

    Args:
        role_address: The D/T/R address of the requesting role.
        item_owning_address: The D/T address that owns the knowledge item.
        compiled_org: The compiled organization for structural lookups.

    Returns:
        True if the role is in a team that is a descendant of the item's owning
        department, or if any ancestor D/T of the role matches the item owner.
    """
    # Walk up the role's address, looking for the item owner as an ancestor
    parts = role_address.split("-")
    for i in range(len(parts)):
        prefix = "-".join(parts[: i + 1])
        if prefix == item_owning_address:
            return True
    return False


# ---------------------------------------------------------------------------
# The 5-step access enforcement algorithm
# ---------------------------------------------------------------------------


def can_access(
    role_address: str,
    knowledge_item: KnowledgeItem,
    posture: TrustPostureLevel,
    compiled_org: CompiledOrg,
    clearances: dict[str, RoleClearance],  # address -> clearance
    ksps: list[KnowledgeSharePolicy],
    bridges: list[PactBridge],
    *,
    now: datetime | None = None,
    environment: dict[str, Any] | None = None,
) -> AccessDecision:
    """5-step access enforcement algorithm.

    Step 1: Resolve role clearance (must exist and be ACTIVE)
    Step 2: Classification check (effective clearance >= item classification)
    Step 3: Compartment check (SECRET/TOP_SECRET: role must have all item compartments)
    Step 4: Containment check (5 sub-steps):
        4a: Same unit -> ALLOW
        4b: Downward (role address is prefix of item owner) -> ALLOW
        4c: T-inherits-D (role in T, item in parent D) -> ALLOW
        4d: KSP check -> ALLOW if an applicable KSP grants; DENY (suppressing
            the bridge fallback) if a KSP matches the addressing but fails a
            narrowing condition; fall through only when NO KSP applies.
        4e: Bridge exists -> ALLOW up to bridge max_classification
    Step 5: No access path -> DENY

    DEFAULT IS DENY. This is fail-closed.

    Args:
        role_address: The D/T/R address of the requesting role.
        knowledge_item: The knowledge item being accessed.
        posture: The current trust posture level of the role.
        compiled_org: The compiled organization structure.
        clearances: Map of role addresses to their clearance assignments.
        ksps: All active Knowledge Share Policies.
        bridges: All active Cross-Functional Bridges.
        now: Evaluation time for KSP ``time_window`` conditions. Defaults to
            the current UTC time when not supplied.
        environment: Request-context facts (e.g. ``{"network_zone": "internal"}``)
            matched against KSP ``conditions["environment"]`` requirements.

    Returns:
        An AccessDecision indicating allow/deny with reason and audit details.
    """
    item = knowledge_item
    if now is None:
        now = datetime.now(UTC)

    # --- Step 1: Resolve role clearance ---
    role_clearance = clearances.get(role_address)
    if role_clearance is None:
        logger.warning(
            "Access denied (step 1): no clearance found for role_address=%s",
            role_address,
        )
        return AccessDecision(
            allowed=False,
            reason=f"No clearance found for role at address '{role_address}'",
            step_failed=1,
            audit_details={
                "role_address": role_address,
                "item_id": item.item_id,
                "step": 1,
                "detail": "missing_clearance",
            },
        )

    # Check vetting status -- only ACTIVE clearances are valid
    if role_clearance.vetting_status != VettingStatus.ACTIVE:
        logger.warning(
            "Access denied (step 1): vetting status is %s for role_address=%s",
            role_clearance.vetting_status.value,
            role_address,
        )
        return AccessDecision(
            allowed=False,
            reason=(
                f"Clearance vetting status is '{role_clearance.vetting_status.value}' "
                f"for role at '{role_address}'; only ACTIVE clearances grant access"
            ),
            step_failed=1,
            audit_details={
                "role_address": role_address,
                "item_id": item.item_id,
                "step": 1,
                "detail": "vetting_not_active",
                "vetting_status": role_clearance.vetting_status.value,
            },
        )

    # --- Step 2: Classification check ---
    eff_clearance = effective_clearance(role_clearance, posture)
    eff_level = _CLEARANCE_ORDER[eff_clearance]
    item_level = _CLEARANCE_ORDER[item.classification]

    if eff_level < item_level:
        logger.info(
            "Access denied (step 2): effective_clearance=%s < item_classification=%s "
            "for role_address=%s, item_id=%s",
            eff_clearance.value,
            item.classification.value,
            role_address,
            item.item_id,
        )
        return AccessDecision(
            allowed=False,
            reason=(
                f"Effective clearance '{eff_clearance.value}' is below item "
                f"classification '{item.classification.value}'"
            ),
            step_failed=2,
            audit_details={
                "role_address": role_address,
                "item_id": item.item_id,
                "step": 2,
                "effective_clearance": eff_clearance.value,
                "item_classification": item.classification.value,
                "posture": posture.value,
                "role_max_clearance": role_clearance.max_clearance.value,
            },
        )

    # --- Step 3: Compartment check (SECRET and TOP_SECRET only) ---
    if item_level >= _CLEARANCE_ORDER[ConfidentialityLevel.SECRET]:
        if item.compartments:
            missing = item.compartments - role_clearance.compartments
            if missing:
                logger.info(
                    "Access denied (step 3): missing compartments %s for role_address=%s, "
                    "item_id=%s",
                    missing,
                    role_address,
                    item.item_id,
                )
                return AccessDecision(
                    allowed=False,
                    reason=(
                        f"Missing compartments: {sorted(missing)}. "
                        f"Role has {sorted(role_clearance.compartments)}, "
                        f"item requires {sorted(item.compartments)}"
                    ),
                    step_failed=3,
                    audit_details={
                        "role_address": role_address,
                        "item_id": item.item_id,
                        "step": 3,
                        "missing_compartments": sorted(missing),
                        "role_compartments": sorted(role_clearance.compartments),
                        "item_compartments": sorted(item.compartments),
                    },
                )

    # --- Step 4: Containment check ---

    # Step 4a: Same unit
    if _is_same_unit(role_address, item.owning_unit_address, compiled_org):
        logger.debug(
            "Access allowed (step 4a): same unit — role_address=%s, " "item_owner=%s",
            role_address,
            item.owning_unit_address,
        )
        return AccessDecision(
            allowed=True,
            reason=f"Same unit access: role is within '{item.owning_unit_address}'",
            audit_details={
                "role_address": role_address,
                "item_id": item.item_id,
                "step": "4a",
                "access_path": "same_unit",
            },
        )

    # Step 4b: Downward (role address is prefix of item owner)
    if _is_downward(role_address, item.owning_unit_address):
        logger.debug(
            "Access allowed (step 4b): downward visibility — role_address=%s, "
            "item_owner=%s",
            role_address,
            item.owning_unit_address,
        )
        return AccessDecision(
            allowed=True,
            reason=(
                f"Downward visibility: role at '{role_address}' is ancestor of "
                f"item owner '{item.owning_unit_address}'"
            ),
            audit_details={
                "role_address": role_address,
                "item_id": item.item_id,
                "step": "4b",
                "access_path": "downward",
            },
        )

    # Step 4c: T-inherits-D (role in T can access parent D's data)
    if _t_inherits_d(role_address, item.owning_unit_address, compiled_org):
        logger.debug(
            "Access allowed (step 4c): T-inherits-D — role_address=%s, "
            "item_owner=%s",
            role_address,
            item.owning_unit_address,
        )
        return AccessDecision(
            allowed=True,
            reason=(
                f"T-inherits-D: role at '{role_address}' inherits access to "
                f"data owned by ancestor unit '{item.owning_unit_address}'"
            ),
            audit_details={
                "role_address": role_address,
                "item_id": item.item_id,
                "step": "4c",
                "access_path": "t_inherits_d",
            },
        )

    # Step 4d: KSP check (deny-precedence: a matching-but-denying KSP
    # suppresses the bridge fallback below)
    ksp_decision = _check_ksps(
        role_address,
        item,
        compiled_org,
        ksps,
        clearances,
        now=now,
        environment=environment,
    )
    if ksp_decision is not None:
        return ksp_decision

    # Step 4e: Bridge check
    bridge_decision = _check_bridges(role_address, item, compiled_org, bridges, now=now)
    if bridge_decision is not None:
        return bridge_decision

    # --- Step 5: No access path found -> DENY ---
    logger.info(
        "Access denied (step 5): no access path found — role_address=%s, "
        "item_id=%s, item_owner=%s",
        role_address,
        item.item_id,
        item.owning_unit_address,
    )
    return AccessDecision(
        allowed=False,
        reason=(
            f"No access path found: role at '{role_address}' has no structural, "
            f"KSP, or bridge path to data owned by '{item.owning_unit_address}'"
        ),
        step_failed=5,
        audit_details={
            "role_address": role_address,
            "item_id": item.item_id,
            "step": 5,
            "detail": "no_access_path",
            "item_owner": item.owning_unit_address,
        },
    )


# ---------------------------------------------------------------------------
# Step 4d: KSP check helper
# ---------------------------------------------------------------------------


def _evaluate_conditions(
    conditions: dict[str, Any],
    now: datetime,
    environment: dict[str, Any] | None,
) -> str | None:
    """Evaluate a KSP ``conditions`` dict against request context.

    Returns a human-readable deny-reason string if any condition fails (or
    is malformed / unrecognized -- fail-closed), or None if all conditions
    pass. An empty ``conditions`` dict always passes (no narrowing).
    """
    if not conditions:
        return None

    # Fail-closed on any condition key the engine does not know how to
    # evaluate -- a silently-ignored condition is the documented-but-unenforced
    # failure mode (zero-tolerance Rule 3c) at the policy-data level.
    for key in conditions:
        if key not in _KNOWN_CONDITION_KEYS:
            return (
                f"unrecognized condition key '{key}' "
                f"(known: {sorted(_KNOWN_CONDITION_KEYS)}; fail-closed)"
            )

    time_window = conditions.get("time_window")
    if time_window is not None:
        in_window = _time_in_window(now, time_window)
        if in_window is None:
            return "malformed time_window condition (fail-closed)"
        if not in_window:
            return f"current time outside time_window {time_window}"

    env_required = conditions.get("environment")
    if env_required is not None:
        if not isinstance(env_required, dict):
            return "malformed environment condition (fail-closed)"
        env = environment or {}
        for req_key, req_value in env_required.items():
            if env.get(req_key) != req_value:
                return (
                    f"environment requirement '{req_key}={req_value!r}' "
                    f"not satisfied"
                )

    return None


def _evaluate_ksp_conditions(
    ksp: KnowledgeSharePolicy,
    item: KnowledgeItem,
    role_clearance: RoleClearance | None,
    now: datetime,
    environment: dict[str, Any] | None,
) -> KspDenyDetail | None:
    """Evaluate every narrowing condition on an addressing-matched KSP.

    Conditions, evaluated in order (first failure short-circuits):
      1. Classification ceiling (max_classification)
      2. Classification set membership (shared_classifications, #1371)
      3. Recipient clearance floor (min_clearance, #1368)
      4. Path scope (shared_paths, #1369)
      5. Type scope (shared_types, #1370)
      6. Request-context conditions (time_window / environment, #1374)
      7. Compartment scope (compartments, #1375 follow-up) -- item compartments
         MUST be a subset of the KSP's authorized compartment set; empty
         ksp.compartments = no narrowing (empty = all).

    Returns a :class:`KspDenyDetail` carrying the deny ``code`` discriminator,
    the human ``message`` (back-compat), and discrete ``fields`` for the FIRST
    failing condition; or None if the item satisfies every condition (the KSP
    grants).
    """
    # 1. Classification ceiling (max_classification)
    if _CLEARANCE_ORDER[item.classification] > _CLEARANCE_ORDER[ksp.max_classification]:
        return KspDenyDetail(
            code="classification_ceiling",
            message=(
                f"item classification '{item.classification.value}' exceeds KSP "
                f"max_classification ceiling '{ksp.max_classification.value}'"
            ),
            fields={
                "item_classification": item.classification.value,
                "ksp_max_classification": ksp.max_classification.value,
            },
        )

    # 2. Classification SET membership (shared_classifications, #1371)
    if (
        ksp.shared_classifications
        and item.classification not in ksp.shared_classifications
    ):
        allowed = sorted(c.value for c in ksp.shared_classifications)
        return KspDenyDetail(
            code="classification_set",
            message=(
                f"item classification '{item.classification.value}' not in KSP "
                f"shared_classifications set {allowed}"
            ),
            fields={
                "item_classification": item.classification.value,
                "ksp_shared_classifications": allowed,
            },
        )

    # 3. Recipient clearance floor (min_clearance, #1368)
    if ksp.min_clearance is not None:
        have_level = (
            _CLEARANCE_ORDER[role_clearance.max_clearance]
            if role_clearance is not None
            else -1
        )
        if have_level < _CLEARANCE_ORDER[ksp.min_clearance]:
            have = role_clearance.max_clearance.value if role_clearance else "none"
            return KspDenyDetail(
                code="min_clearance",
                message=(
                    f"recipient clearance '{have}' is below KSP min_clearance floor "
                    f"'{ksp.min_clearance.value}'"
                ),
                fields={
                    "recipient_clearance": have,
                    "ksp_min_clearance": ksp.min_clearance.value,
                },
            )

    # 4. Path scope (shared_paths, #1369)
    if ksp.shared_paths and not _path_matches(item.path, ksp.shared_paths):
        return KspDenyDetail(
            code="path_scope",
            message=(
                f"item path {item.path!r} does not match KSP shared_paths "
                f"{list(ksp.shared_paths)}"
            ),
            fields={
                "item_path": item.path,
                "ksp_shared_paths": list(ksp.shared_paths),
            },
        )

    # 5. Type scope (shared_types, #1370)
    if ksp.shared_types and (
        item.knowledge_type is None or item.knowledge_type not in ksp.shared_types
    ):
        return KspDenyDetail(
            code="type_scope",
            message=(
                f"item knowledge_type {item.knowledge_type!r} not in KSP "
                f"shared_types {sorted(ksp.shared_types)}"
            ),
            fields={
                "item_knowledge_type": item.knowledge_type,
                "ksp_shared_types": sorted(ksp.shared_types),
            },
        )

    # 6. Request-context conditions (time_window / environment, #1374)
    cond_detail = _evaluate_conditions(ksp.conditions, now, environment)
    if cond_detail is not None:
        return KspDenyDetail(
            code="condition",
            message=cond_detail,
            fields={"condition_detail": cond_detail},
        )

    # 7. Compartment scope (ksp.compartments, #1375 follow-up)
    # Mirrors the step-3 clearance compartment-dominance check (the
    # `item.compartments - role_clearance.compartments` subset test) --
    # an item is shareable under this KSP only if EVERY compartment it carries
    # is authorized by the KSP's compartment set (item.compartments subset of
    # ksp.compartments). Empty ksp.compartments = no narrowing (empty = all).
    if ksp.compartments:
        missing = item.compartments - ksp.compartments
        if missing:
            return KspDenyDetail(
                code="compartment_scope",
                message=(
                    f"item compartments {sorted(missing)} not authorized by KSP "
                    f"compartments {sorted(ksp.compartments)}"
                ),
                fields={
                    "missing_compartments": sorted(missing),
                    "item_compartments": sorted(item.compartments),
                    "ksp_compartments": sorted(ksp.compartments),
                },
            )

    return None


def _check_ksps(
    role_address: str,
    item: KnowledgeItem,
    compiled_org: CompiledOrg,
    ksps: list[KnowledgeSharePolicy],
    clearances: dict[str, RoleClearance],
    *,
    now: datetime,
    environment: dict[str, Any] | None = None,
) -> AccessDecision | None:
    """Evaluate cross-unit KSP access with deny-precedence (#1372).

    A KSP is *applicable* when it is active, non-expired, and its
    source/target addressing matches (source owns the item, target contains
    the requesting role). An applicable KSP then either GRANTS (every
    narrowing condition passes) or DENIES (some condition fails).

    Composition rule:
      - Any applicable KSP that grants -> ALLOW (a granting sibling KSP wins
        over a denying one; deny-precedence is over the bridge, not over
        another KSP that affirmatively grants).
      - At least one applicable KSP but NONE grant -> DENY, suppressing the
        bridge fallback. This is the #1372 fix: a deliberate KSP deny is no
        longer bypassable via a more permissive bridge.
      - No applicable KSP -> None (the bridge path remains available).

    Returns:
        AccessDecision(allowed=True) if a KSP grants; AccessDecision(
        allowed=False, step_failed=4) if applicable KSPs all deny; None if
        no KSP applies.
    """
    role_unit = _get_containment_unit(role_address, compiled_org)
    role_clearance = clearances.get(role_address)

    last_deny: tuple[str, KspDenyDetail] | None = None  # (ksp_id, deny_detail)

    for ksp in ksps:
        if not ksp.active:
            continue

        # Expired KSP treated as non-existent (C1 security fix)
        if ksp.expires_at is not None and ksp.expires_at < now:
            continue

        # Source must match item owner (exact or prefix)
        source_matches = (
            item.owning_unit_address == ksp.source_unit_address
            or item.owning_unit_address.startswith(ksp.source_unit_address + "-")
        )
        if not source_matches:
            continue

        # Target must contain the requesting role
        target_matches = False
        if role_unit is not None:
            target_matches = (
                role_unit == ksp.target_unit_address
                or role_unit.startswith(ksp.target_unit_address + "-")
            )
        if not target_matches:
            # Also check if role_address itself starts with target unit
            target_matches = role_address.startswith(ksp.target_unit_address + "-")
        if not target_matches:
            continue

        # This KSP APPLIES (addressing matched). It now grants or denies.
        deny_detail = _evaluate_ksp_conditions(
            ksp, item, role_clearance, now, environment
        )
        if deny_detail is not None:
            # Matching-but-denying KSP -- record it and keep scanning for a
            # sibling KSP that grants.
            last_deny = (ksp.id, deny_detail)
            continue

        logger.debug(
            "Access allowed (step 4d): KSP=%s — role_address=%s, item_owner=%s",
            ksp.id,
            role_address,
            item.owning_unit_address,
        )
        return AccessDecision(
            allowed=True,
            reason=(
                f"KSP '{ksp.id}' grants access: "
                f"source='{ksp.source_unit_address}' -> target='{ksp.target_unit_address}'"
            ),
            audit_details={
                "role_address": role_address,
                "item_id": item.item_id,
                "step": "4d",
                "access_path": "ksp",
                "ksp_id": ksp.id,
            },
            valid_until=ksp.expires_at,
        )

    if last_deny is None:
        # No KSP applied -- leave the bridge fallback available.
        return None

    # >=1 applicable KSP but none granted -> DENY, suppressing the bridge.
    deny_ksp_id, deny_detail = last_deny
    logger.info(
        "Access denied (step 4d): KSP=%s denies (%s: %s) — role_address=%s, "
        "item_id=%s; bridge fallback suppressed",
        deny_ksp_id,
        deny_detail.code,
        deny_detail.message,
        role_address,
        item.item_id,
    )
    # Discrete, SIEM-queryable deny context: deny_code names which narrowing
    # condition failed; deny_detail.fields spreads as top-level keys (e.g.
    # missing_compartments) mirroring the step-3 clearance-deny audit shape.
    # deny_reason (the human string) is retained for backward compatibility.
    return AccessDecision(
        allowed=False,
        reason=(
            f"KSP '{deny_ksp_id}' denies access ({deny_detail.message}); a "
            f"matching deny-KSP suppresses the bridge fallback"
        ),
        step_failed=4,
        audit_details={
            "role_address": role_address,
            "item_id": item.item_id,
            "step": "4d",
            "access_path": "ksp_deny",
            "ksp_id": deny_ksp_id,
            "deny_reason": deny_detail.message,
            "deny_code": deny_detail.code,
            **deny_detail.fields,
        },
    )


# ---------------------------------------------------------------------------
# Step 4e: Bridge check helper
# ---------------------------------------------------------------------------


def _check_bridges(
    role_address: str,
    item: KnowledgeItem,
    compiled_org: CompiledOrg,
    bridges: list[PactBridge],
    *,
    now: datetime,
) -> AccessDecision | None:
    """Check if any active bridge grants access.

    A bridge grants access when:
    1. The bridge is active.
    2. One side of the bridge matches the requesting role (or the role's
       ancestor -- a bridge to a dept head covers the entire dept).
    3. The other side of the bridge connects to the item's owning unit
       (the bridged role is within or has authority over the item owner).
    4. The item's classification <= bridge max_classification.
    5. If bilateral=False, only role_a can access role_b's data
       (A -> B direction only).

    Bridge expiry is evaluated against the injected ``now`` (symmetric with
    the KSP expiry check in ``_check_ksps``) so the whole time-evaluated
    access path is deterministic under an injected clock.

    Returns:
        An AccessDecision(allowed=True) if a bridge grants access, or None
        if no bridge applies.
    """
    for bridge in bridges:
        if not bridge.active:
            continue

        # Expired bridge treated as non-existent (C1 security fix). Uses the
        # injected ``now`` for determinism parity with KSP expiry.
        if bridge.expires_at is not None and bridge.expires_at < now:
            continue

        # Determine direction: which side matches the requesting role,
        # and which side connects to the item owner?
        direction = _bridge_direction(
            role_address, item.owning_unit_address, bridge, compiled_org
        )
        if direction is None:
            continue

        requesting_side, item_side, is_a_to_b = direction

        # If unilateral (bilateral=False), only A->B direction is allowed
        # A->B means role_a is the one accessing role_b's data
        # So the requesting role must match role_a
        if not bridge.bilateral and not is_a_to_b:
            continue

        # Classification cap
        bridge_level = _CLEARANCE_ORDER[bridge.max_classification]
        item_level = _CLEARANCE_ORDER[item.classification]
        if item_level > bridge_level:
            continue

        # Path scope (#1373): when shared_paths is set, the item path MUST
        # match a pattern (``*`` / ``prefix/*`` / exact). An item path
        # containing a ``..`` segment fails closed (no match). An empty
        # shared_paths preserves the bridge's broad, path-agnostic grant.
        if bridge.shared_paths and not _path_matches(item.path, bridge.shared_paths):
            logger.info(
                "Access not granted via bridge=%s: item path %r outside "
                "shared_paths %s — role_address=%s, item_id=%s",
                bridge.id,
                item.path,
                list(bridge.shared_paths),
                role_address,
                item.item_id,
            )
            continue

        logger.debug(
            "Access allowed (step 4e): bridge=%s — role_address=%s, " "item_owner=%s",
            bridge.id,
            role_address,
            item.owning_unit_address,
        )
        return AccessDecision(
            allowed=True,
            reason=(
                f"Bridge '{bridge.id}' ({bridge.bridge_type}) grants access: "
                f"'{requesting_side}' <-> '{item_side}'"
            ),
            audit_details={
                "role_address": role_address,
                "item_id": item.item_id,
                "step": "4e",
                "access_path": "bridge",
                "bridge_id": bridge.id,
                "bridge_type": bridge.bridge_type,
            },
            valid_until=bridge.expires_at,
        )

    return None


def _bridge_direction(
    role_address: str,
    item_owner: str,
    bridge: PactBridge,
    compiled_org: CompiledOrg,
) -> tuple[str, str, bool] | None:
    """Determine if a bridge connects the requesting role to the item owner.

    Returns:
        A tuple (requesting_side, item_side, is_a_to_b) if the bridge connects
        the role to the item, or None if the bridge does not apply.

        is_a_to_b is True when the requesting role is on the A side and the
        item owner is on the B side. This matters for unilateral bridges.
    """
    role_a = bridge.role_a_address
    role_b = bridge.role_b_address

    # Check A->B direction: requesting role matches A side, item is in B's domain
    if _role_matches_bridge_side(role_address, role_a) and _item_in_bridge_domain(
        item_owner, role_b, compiled_org
    ):
        return (role_a, role_b, True)

    # Check B->A direction: requesting role matches B side, item is in A's domain
    if _role_matches_bridge_side(role_address, role_b) and _item_in_bridge_domain(
        item_owner, role_a, compiled_org
    ):
        return (role_b, role_a, False)

    return None


def _role_matches_bridge_side(role_address: str, bridge_role: str) -> bool:
    """Check if the requesting role matches a bridge endpoint.

    Bridges are role-level access paths -- only the exact bridge endpoint
    role matches, not descendants. If VP Admin (D1-R1-D2-R1) has a bridge,
    the Finance Director (D1-R1-D2-R1-T2-R1) does NOT inherit that access.
    Descendant access is governed by KSPs (unit-level), not bridges (role-level).
    """
    return role_address == bridge_role


def _item_in_bridge_domain(
    item_owner: str,
    bridge_role: str,
    compiled_org: CompiledOrg,
) -> bool:
    """Check if the item owner is in the domain of a bridge role.

    The bridge role's domain includes:
    1. The role's own containment unit
    2. All descendants of the role's containment unit
    3. The role address itself and its descendants (for downward access)
    """
    # The bridge role's containment unit
    bridge_unit = _get_containment_unit(bridge_role, compiled_org)

    if bridge_unit is not None:
        # Item is in the bridge role's unit or a descendant
        if item_owner == bridge_unit or item_owner.startswith(bridge_unit + "-"):
            return True

    # Item owner is a descendant of the bridge role address
    if item_owner == bridge_role or item_owner.startswith(bridge_role + "-"):
        return True

    return False
