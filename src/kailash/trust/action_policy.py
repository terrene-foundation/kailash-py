# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Shared allowed/blocked-action restrictiveness model (GH #2218).

This module is the SINGLE place that decides what an ``allowed_actions`` value
means. Every enforcement surface -- the governance engine's ``verify_action``
path, the verification gradient, the governed-agent ``run()`` path, the bridge
scope validator -- and every monotonic-tightening validator consumes these
functions rather than re-spelling the check locally
(``security.md`` § Enforcement-Surface Parity).

The defect this closes
----------------------
``allowed_actions`` defaults to ``[]``. Before this module the surfaces
disagreed about what that meant::

    if action not in allowed_actions:            # empty => DENY every action
    if op.allowed_actions and action not in ...  # empty => PERMIT every action

The ``and`` short-circuits, so the *strictest-looking* configuration -- an
operator who tightened the allowlist down to nothing -- produced the *widest*
possible outcome at three of the four enforcement surfaces.

The restrictiveness model (one reading, everywhere)
---------------------------------------------------
An operational dimension's PERMITTED SET is ``allowed - blocked``. Deny wins.

* ``None`` operational dimension = the dimension is NOT CONFIGURED, which is
  the widest state (GH #390). This is a distinct state from a configured
  dimension holding an empty allowlist, and is deliberately preserved.
* An EMPTY allowlist ranks TIGHTEST: it permits nothing. Empty is not
  "unconstrained"; it is "no action is on the list".
* An UNRECOGNIZED / structurally malformed allowlist also ranks TIGHTEST --
  it permits nothing, and the reason is logged at ``ERROR`` and carried in the
  verdict. Nothing is swallowed and nothing fails open.
* Tightening compares ALLOWLISTS: a child's allowlist may only ever be a
  SUBSET of its parent's. An unrecognized-or-empty parent allowlist therefore
  permits nothing, so any non-empty child WIDENS and must be rejected. (The
  blocklist is a separate dimension with its own monotonicity rule; see
  :func:`allowed_actions_tightening_violation` for why it is deliberately not
  folded into this comparison.)

Because "empty" and "malformed" both collapse to the same tightest reading,
there is no configuration for which one surface permits and another denies.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "ActionPolicy",
    "ActionVerdict",
    "OperationalView",
    "operational_view",
    "read_action_policy",
    "permitted_action_set",
    "delegated_capabilities",
    "evaluate_action",
    "action_permitted",
    "evaluate_scope",
    "scope_permitted",
    "allowed_actions_tightening_violation",
]


# ---------------------------------------------------------------------------
# Verdict + policy types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ActionVerdict:
    """The outcome of evaluating an action (or a scope) against a dimension.

    Attributes:
        permitted: True when the action/scope is permitted.
        reason: Human-readable explanation. Always populated on a denial.
        rule: Stable machine-readable discriminator naming which clause of the
            restrictiveness model produced the verdict. One of
            ``dimension-absent``, ``blocked-list``, ``allowlist-empty``,
            ``not-in-allowlist``, ``in-allowlist``, ``no-scope-requested``,
            ``scope-in-allowlist`` or ``malformed``.
    """

    permitted: bool
    reason: str
    rule: str


@dataclass(frozen=True)
class ActionPolicy:
    """The normalized permitted/blocked sets of ONE operational dimension.

    Attributes:
        allowed: Normalized allowlist.
        blocked: Normalized blocklist.
        malformed: True when the source value could not be read as a
            collection of action names. A malformed policy permits NOTHING.
        malformed_reason: Why the source was unreadable. Empty unless
            ``malformed`` is True.
    """

    allowed: frozenset[str]
    blocked: frozenset[str]
    malformed: bool = False
    malformed_reason: str = ""

    @property
    def permitted(self) -> frozenset[str]:
        """The permitted set: ``allowed - blocked``, empty when malformed."""
        if self.malformed:
            return frozenset()
        return self.allowed - self.blocked


@dataclass(frozen=True)
class OperationalView:
    """A minimal operational dimension built from loose collections.

    Lets surfaces that hold raw constraint dicts -- the EATP delegation
    validator, for instance -- consume the same restrictiveness model as the
    surfaces that hold typed envelope objects, instead of re-spelling the
    subset check locally.
    """

    allowed_actions: Any = ()
    blocked_actions: Any = ()


def operational_view(allowed: Any = (), blocked: Any = ()) -> OperationalView:
    """Build an :class:`OperationalView` from raw allowed/blocked collections."""
    return OperationalView(allowed_actions=allowed, blocked_actions=blocked)


# ---------------------------------------------------------------------------
# Normalization -- unrecognized ranks TIGHTEST
# ---------------------------------------------------------------------------


def _normalize(value: Any, field_name: str) -> tuple[frozenset[str], str]:
    """Normalize one action collection.

    Returns:
        ``(names, error)``. ``error`` is empty on success; when non-empty the
        value was unreadable and ``names`` is empty (the tightest reading).
    """
    if value is None:
        # An unset collection is legitimately empty -- not an error.
        return frozenset(), ""
    if isinstance(value, (str, bytes, bytearray)):
        # A bare string is a config mistake: iterating it yields characters,
        # which would silently produce a nonsense allowlist.
        return (
            frozenset(),
            f"{field_name} must be a collection of action names, got the bare "
            f"{type(value).__name__} {value!r}",
        )
    if isinstance(value, Mapping):
        # A mapping iterates its KEYS, so {"transfer_funds": False} would
        # normalize to an allowlist containing "transfer_funds" -- a disabled
        # entry silently becoming an ALLOW. Fail closed instead.
        return (
            frozenset(),
            f"{field_name} must be a collection of action names, got a "
            f"{type(value).__name__}; a mapping's values are not consulted",
        )
    if not isinstance(value, (list, tuple, set, frozenset)):
        # Deliberately a CONCRETE-type allowlist rather than an `Iterable`
        # check: a generator satisfies `Iterable` but is ONE-SHOT, and the
        # bridge validator normalizes the same requested scope once per
        # endpoint role. The second read of an exhausted generator would
        # normalize to EMPTY, which `evaluate_scope` reads as "no scope
        # requested" and PERMITS -- silently skipping the second endpoint's
        # check. Refusing the type closes that fail-open by construction.
        return (
            frozenset(),
            f"{field_name} must be a list, tuple, set or frozenset of action "
            f"names, got {type(value).__name__}",
        )
    names: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            return (
                frozenset(),
                f"{field_name} must contain only action-name strings, got "
                f"{type(item).__name__} ({item!r})",
            )
        names.add(item)
    return frozenset(names), ""


def read_action_policy(operational: Any) -> ActionPolicy | None:
    """Read an operational dimension into its normalized :class:`ActionPolicy`.

    Args:
        operational: Any object exposing ``allowed_actions`` and
            ``blocked_actions`` -- ``pact.config.OperationalConstraintConfig``,
            ``trust.envelope.OperationalConstraint`` and
            ``trust.plane.models.OperationalConstraints`` all qualify -- or
            ``None``.

    Returns:
        ``None`` when ``operational`` is ``None`` (the dimension is not
        configured, which is the widest state). Otherwise the normalized
        policy; a policy that could not be read is marked ``malformed`` and
        permits nothing.
    """
    if operational is None:
        return None

    allowed_raw = getattr(operational, "allowed_actions", None)
    blocked_raw = getattr(operational, "blocked_actions", None)

    allowed, allowed_err = _normalize(allowed_raw, "allowed_actions")
    blocked, blocked_err = _normalize(blocked_raw, "blocked_actions")

    error = allowed_err or blocked_err
    if error:
        logger.error(
            "Unreadable operational action policy on %s -- ranking TIGHTEST "
            "(permits nothing): %s",
            type(operational).__name__,
            error,
        )
        return ActionPolicy(
            allowed=frozenset(),
            blocked=frozenset(),
            malformed=True,
            malformed_reason=error,
        )

    return ActionPolicy(allowed=allowed, blocked=blocked)


def permitted_action_set(operational: Any) -> frozenset[str] | None:
    """Return the permitted action set, or ``None`` if the dimension is absent.

    ``None`` means "not configured" (widest). An empty frozenset means
    "configured, and it permits nothing" (tightest).
    """
    policy = read_action_policy(operational)
    return None if policy is None else policy.permitted


def delegated_capabilities(operational: Any) -> list[str]:
    """Return the capabilities a DelegationRecord should ADVERTISE (GH #2225).

    A ``DelegationRecord`` is a durable, signed EATP trust-chain artifact that
    an auditor or a downstream consumer reads to answer *"what was this agent
    delegated?"*. It MUST NOT advertise a capability the enforcement surfaces
    deny: the answer has to be a SUBSET of what the agent can actually do, never
    a superset.

    So the record's capability list is derived from the SAME reading of the
    operational dimension every enforcement surface uses -- the permitted set
    ``allowed - blocked`` produced by :func:`read_action_policy` and consumed by
    :func:`evaluate_action`. Because the record and enforcement now share ONE
    derivation, an action that is blocked (or not on the allowlist) cannot be
    advertised as delegated, and the two surfaces cannot drift apart again.

    The allowlist reaching this function has already been intersected with the
    delegator's effective allowlist by the monotonic-tightening validation that
    runs before a role/task envelope is persisted (child allowlist must be a
    SUBSET of the parent's), so ``allowed - blocked`` here IS the delegatee's
    effective permitted set for that envelope.

    Args:
        operational: The operational dimension of the delegated envelope, or
            ``None`` when the envelope does not configure one.

    Returns:
        The permitted actions, sorted for deterministic (signable) output. An
        ``None`` dimension is "not configured" (widest); there is no finite
        capability list to advertise, so the empty list is returned -- it
        UNDERSTATES, which is safe (it can never over-state a grant).
    """
    permitted = permitted_action_set(operational)
    if permitted is None:
        return []
    return sorted(permitted)


# ---------------------------------------------------------------------------
# Enforcement -- THE predicate every surface calls
# ---------------------------------------------------------------------------


def evaluate_action(operational: Any, action: str) -> ActionVerdict:
    """Decide whether ``action`` is permitted by an operational dimension.

    This is the ONLY implementation of the allow/block decision. Enforcement
    surfaces call it and translate the verdict into their own error type; they
    MUST NOT re-spell the check.

    Args:
        operational: The operational dimension, or ``None`` when the envelope
            does not configure one.
        action: The action name being requested.

    Returns:
        An :class:`ActionVerdict`. Denials always carry a populated ``reason``.
    """
    policy = read_action_policy(operational)
    if policy is None:
        return ActionVerdict(
            permitted=True,
            reason="No operational constraints configured",
            rule="dimension-absent",
        )

    if policy.malformed:
        return ActionVerdict(
            permitted=False,
            reason=(
                f"Operational action policy is unreadable -- fail-closed to "
                f"denied: {policy.malformed_reason}"
            ),
            rule="malformed",
        )

    # Deny wins: the blocklist is consulted first and is unconditional.
    if action in policy.blocked:
        return ActionVerdict(
            permitted=False,
            reason=f"Action '{action}' is explicitly blocked by operational constraints",
            rule="blocked-list",
        )

    if not policy.allowed:
        return ActionVerdict(
            permitted=False,
            reason=(
                f"Action '{action}' is not permitted: the operational envelope "
                f"declares an EMPTY allowed-actions list, which permits nothing"
            ),
            rule="allowlist-empty",
        )

    if action not in policy.allowed:
        return ActionVerdict(
            permitted=False,
            reason=(
                f"Action '{action}' is not in the allowed actions list: "
                f"{sorted(policy.allowed)}"
            ),
            rule="not-in-allowlist",
        )

    return ActionVerdict(permitted=True, reason="Action permitted", rule="in-allowlist")


def action_permitted(operational: Any, action: str) -> bool:
    """Boolean form of :func:`evaluate_action`."""
    return evaluate_action(operational, action).permitted


# ---------------------------------------------------------------------------
# Scope enforcement -- the bridge-path sibling
# ---------------------------------------------------------------------------


def evaluate_scope(operational: Any, requested_scope: Any) -> ActionVerdict:
    """Decide whether an entire requested operational scope is permitted.

    Used by the bridge validator: a bridge may only carry operations both
    endpoint roles are themselves permitted to perform. Empty and malformed
    allowlists permit nothing, exactly as in :func:`evaluate_action`.

    Args:
        operational: The operational dimension, or ``None``.
        requested_scope: The collection of operation names the bridge requests.

    Returns:
        An :class:`ActionVerdict` over the whole scope.
    """
    policy = read_action_policy(operational)
    if policy is None:
        return ActionVerdict(
            permitted=True,
            reason="No operational constraints configured",
            rule="dimension-absent",
        )

    requested, requested_err = _normalize(requested_scope, "operational_scope")
    if requested_err:
        return ActionVerdict(
            permitted=False,
            reason=f"Requested scope is unreadable -- fail-closed to denied: {requested_err}",
            rule="malformed",
        )

    if not requested:
        return ActionVerdict(
            permitted=True, reason="No scope requested", rule="no-scope-requested"
        )

    if policy.malformed:
        return ActionVerdict(
            permitted=False,
            reason=(
                f"Operational action policy is unreadable -- fail-closed to "
                f"denied: {policy.malformed_reason}"
            ),
            rule="malformed",
        )

    blocked_hits = requested & policy.blocked
    if blocked_hits:
        return ActionVerdict(
            permitted=False,
            reason=(
                f"Requested scope {sorted(blocked_hits)} is explicitly blocked "
                f"by operational constraints"
            ),
            rule="blocked-list",
        )

    if not policy.allowed:
        return ActionVerdict(
            permitted=False,
            reason=(
                f"Requested scope {sorted(requested)} is not permitted: the "
                f"operational envelope declares an EMPTY allowed-actions list, "
                f"which permits nothing"
            ),
            rule="allowlist-empty",
        )

    extra = requested - policy.permitted
    if extra:
        return ActionVerdict(
            permitted=False,
            reason=(
                f"Requested scope {sorted(extra)} is not in the allowed actions "
                f"list: {sorted(policy.permitted)}"
            ),
            rule="not-in-allowlist",
        )

    return ActionVerdict(
        permitted=True, reason="Scope permitted", rule="scope-in-allowlist"
    )


def scope_permitted(operational: Any, requested_scope: Any) -> bool:
    """Boolean form of :func:`evaluate_scope`."""
    return evaluate_scope(operational, requested_scope).permitted


# ---------------------------------------------------------------------------
# Monotonic tightening -- the same restrictiveness model, one direction
# ---------------------------------------------------------------------------


def allowed_actions_tightening_violation(
    parent_operational: Any,
    child_operational: Any,
) -> str | None:
    """Return a WIDENING message if the child's allowlist exceeds the parent's.

    Uses the SAME reading of ``allowed_actions`` the enforcement surfaces
    consume -- empty and unreadable both rank TIGHTEST -- so a configuration
    that registers cannot then be evaluated under a different reading of the
    field.

    * Parent dimension ``None`` -> parent is unconfigured (widest); any child
      tightens. Returns ``None``.
    * Child dimension ``None`` while the parent HAS one -> the child drops the
      dimension entirely, which is a widening. Rejected.
    * Otherwise the child's ALLOWLIST must be a SUBSET of the parent's. An
      empty-or-malformed parent allowlist permits nothing, so any non-empty
      child is an unrecognized-to-recognized transition that WIDENS, and is
      rejected.

    SCOPE, deliberately: this compares ALLOWLISTS, not the eval-time permitted
    sets (``allowed - blocked``). The blocklist is a separate dimension with
    its own monotonicity rule -- child blocked must be a SUPERSET -- and the
    eval-time envelope intersection unions the blocklists and re-subtracts them
    from the allowlist. Folding the parent's blocklist into this comparison
    would reject a child that merely RESTATES an action its ancestor blocks,
    even though the intersection already denies it at evaluation. That is a
    different (and pre-existing, correctly-handled) concern from GH #2218, and
    entangling them here would widen this fix's blast radius without closing
    any gap.

    Returns:
        ``None`` when the child is tighter-or-equal, else a message naming the
        actions the child added.
    """
    if parent_operational is None:
        return None

    parent_policy = read_action_policy(parent_operational)
    if parent_policy is None:  # pragma: no cover - guarded above
        return None

    if child_operational is None:
        return (
            "allowed_actions widened: parent constrains operational actions "
            f"({sorted(parent_policy.allowed)}) but the child drops the "
            "operational dimension entirely"
        )

    child_policy = read_action_policy(child_operational)
    assert child_policy is not None  # child_operational is not None

    # A malformed policy permits nothing, so its ALLOWLIST is empty too.
    parent_allowed = frozenset() if parent_policy.malformed else parent_policy.allowed
    child_allowed = frozenset() if child_policy.malformed else child_policy.allowed

    extra = child_allowed - parent_allowed
    if not extra:
        return None

    if parent_policy.malformed:
        return (
            f"allowed_actions widened: child adds {sorted(extra)} but the "
            f"parent's action policy is unreadable and therefore permits "
            f"nothing ({parent_policy.malformed_reason})"
        )
    if not parent_allowed:
        return (
            f"allowed_actions widened: child adds {sorted(extra)} but the "
            f"parent declares an EMPTY allowed-actions list, which permits "
            f"nothing"
        )
    return (
        f"allowed_actions widened: child adds {sorted(extra)}, which is not in "
        f"the parent allowed set {sorted(parent_allowed)}"
    )
