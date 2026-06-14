# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""EATP-12 deployment-controlled shard-holder registry (N12-SH-01 / N12-SH-03).

The holder registry is the deployment-controlled set of named, attestable
principals a backup may distribute shards to. ``back_up_vault_key`` gate 3
consults it: every supplied holder id MUST be a registered holder before any
sharding occurs; an id not in the registry is rejected with
``unregistered-holder`` (N12-SH-01). This closes F-AUTHZ-6 — caller-arbitrary
holder identifiers would otherwise turn backup-to-attacker-holders into a
sanctioned exfiltration channel; the registry is the attribution gate that
fences it.

**Attribution, not custody.** Physical custody (the holder physically possesses
the paper shard per EATP-10 §5) is the default attribution mechanism and is
sufficient at the **Conformant** level. The registry records WHICH registered
holder identity a shard went to (by stable id, NEVER shard contents — N12-SH-01
/ N12-AU-01); it does NOT cryptographically wrap shards (that is N12-SH-02,
per-holder wrapping, a Complete-level R1 enhancement). The audit envelope's
``holders`` field records registry ids only — the same id strings the gate
validated — so "shard k was held by holder H" is reconstructable from the
audit record without ever recording shard bytes.

**N12-SH-03 (revocation does not weaken threshold below k).** Revoking a
departed holder's shard reduces the available holder set. :func:`check_revocation_k_floor`
is the guard that REFUSES to let the un-revoked holder count drop below the
ritual threshold ``k``: if a revocation would leave fewer than ``k`` un-revoked
holders, it raises a typed :class:`~kailash.trust.vault.errors.VaultBindingError`
whose disposition is "rotation required" (surfaced to the operator, naming the
§5 rotation as the resolution), NEVER silently dropping the set below ``k`` and
leaving the vault unrecoverable. The guard SURFACES the rotation requirement;
the actual for-cause generation-advancing rotation (N12-SH-04) is performed by a
later shard (R1 / Wave 5).

**Injection + process-singleton default (mirrors C2a's CommitmentRegistry).**
The registry is an INJECTED dependency: ``back_up_vault_key`` takes a
``holder_registry`` parameter so tests construct a fresh instance and a
deployment wires its persisted one. A module singleton
(:func:`default_holder_registry`) backs callers that do not inject one. The
singleton starts EMPTY and ENFORCING — fail-closed: an empty registry rejects
every holder, so a deployment MUST register its holders before the first
backup. A real deployment persists the registry (the durable record is the
deployment's roster of attestable principals); the in-memory shape here is the
conformant default, mirroring :class:`~kailash.trust.vault.registry.CommitmentRegistry`'s
in-memory-folded-cache disposition.
"""

from __future__ import annotations

import logging
from typing import Iterable, Sequence, Set

from kailash.trust.vault.errors import N12FT01Code, VaultBindingError

logger = logging.getLogger(__name__)

__all__ = [
    "HolderRegistry",
    "default_holder_registry",
    "require_registered_holders",
    "check_revocation_k_floor",
]


class HolderRegistry:
    """Deployment-controlled set of registered, attestable shard-holder ids (N12-SH-01).

    Membership-only: the registry records WHICH holder ids are deployment-approved
    to hold shards; it carries no shard contents and no cryptographic material
    (attribution, not custody). Mirrors the injection + process-singleton-default
    shape of :class:`~kailash.trust.vault.registry.CommitmentRegistry`.

    A backup consults the registry at gate 3 (:func:`require_registered_holders`):
    every supplied holder id MUST be registered, else ``unregistered-holder``
    BEFORE any sharding. The registry starts empty and fail-closed — an
    unregistered id is always rejected.
    """

    def __init__(self) -> None:
        # The deployment-approved holder-id set (stable ids; never shard contents).
        self._registered: Set[str] = set()

    def register(self, holder_id: str) -> None:
        """Register a deployment-approved holder id (N12-SH-01). Idempotent.

        A holder id is a non-empty stable string naming an attestable principal.
        Registering the same id twice is a no-op (idempotent — the registry is a
        membership set, not an append log).
        """
        if not isinstance(holder_id, str) or not holder_id:
            raise ValueError(
                f"holder_id MUST be a non-empty string (N12-SH-01); got {holder_id!r}"
            )
        self._registered.add(holder_id)
        logger.info(
            "vault.holder_registry.register.ok",
            extra={"holder_id": holder_id, "registered_count": len(self._registered)},
        )

    def register_all(self, holder_ids: Iterable[str]) -> None:
        """Register every id in ``holder_ids`` (convenience over :meth:`register`)."""
        for holder_id in holder_ids:
            self.register(holder_id)

    def is_registered(self, holder_id: str) -> bool:
        """Membership check (N12-SH-01). Fail-closed: a malformed id → False.

        An empty / non-string id is NOT registered by construction, so it is
        rejected at the gate exactly as an unknown id is — never silently
        treated as present.
        """
        if not isinstance(holder_id, str) or not holder_id:
            return False
        return holder_id in self._registered

    def __contains__(self, holder_id: object) -> bool:
        """``holder_id in registry`` — membership sugar over :meth:`is_registered`."""
        return isinstance(holder_id, str) and self.is_registered(holder_id)


# ---------------------------------------------------------------------------
# Module singleton (deployment-default) — mirrors C2a's default registry
# ---------------------------------------------------------------------------

_DEFAULT_HOLDER_REGISTRY = HolderRegistry()


def default_holder_registry() -> HolderRegistry:
    """Return the process-scoped default holder registry.

    ``back_up_vault_key`` falls back to this when no ``holder_registry`` is
    injected, so a register-then-backup in the SAME deployment process sees the
    registration without the caller threading an instance. The singleton starts
    EMPTY and FAIL-CLOSED — a deployment MUST register its holders before the
    first backup, else gate 3 rejects every holder with ``unregistered-holder``.
    Tests inject a FRESH :class:`HolderRegistry` (or register into this singleton
    and clear it between tests) to isolate registrations. A real deployment
    injects its persisted holder roster.
    """
    return _DEFAULT_HOLDER_REGISTRY


# ---------------------------------------------------------------------------
# Gate-3 deepening (N12-SH-01) + revocation k-floor guard (N12-SH-03)
# ---------------------------------------------------------------------------


def require_registered_holders(holders: object, registry: HolderRegistry) -> list[str]:
    """Gate 3 (deepened) — registry-membership holder attribution (N12-SH-01).

    Extends the basic presence check (:func:`~kailash.trust.vault.input_gates.require_holders_supplied`):
    preserves it (an empty / wrong-type / non-string-entry holder array still
    fails ``unregistered-holder``) AND adds the deployment-registry membership
    check — every supplied holder id MUST be registered in ``registry``, else
    ``unregistered-holder`` on the FIRST unregistered id, BEFORE any sharding
    (F-AUTHZ-6). Returns the validated holder-id list in verbatim order (the
    distribution order recorded on the audit envelope, N12-AU-04).

    Args:
        holders: The supplied holder-id distribution (n entries; ordered).
        registry: The deployment-controlled holder registry to check membership
            against.

    Returns:
        The validated holder-id list (verbatim order).

    Raises:
        VaultBindingError: ``unregistered-holder`` when the array is empty /
            wrong-type / carries a non-string-or-empty entry / carries an id not
            in ``registry``.
    """
    # Basic presence (preserves the existing gate-3 contract): non-empty ordered
    # array of non-empty holder-id strings.
    if not isinstance(holders, (list, tuple)):
        raise VaultBindingError(
            N12FT01Code.UNREGISTERED_HOLDER,
            f"holders MUST be a non-empty ordered array of holder-id strings "
            f"(N12-SH-01); got {type(holders).__name__}",
            details={"holders": repr(holders)},
        )
    out: list[str] = []
    for i, h in enumerate(holders):
        if not isinstance(h, str) or not h:
            raise VaultBindingError(
                N12FT01Code.UNREGISTERED_HOLDER,
                f"holders[{i}] MUST be a non-empty holder-id string "
                f"(N12-SH-01); got {h!r}",
                details={"index": i, "value": repr(h)},
            )
        out.append(h)
    if not out:
        raise VaultBindingError(
            N12FT01Code.UNREGISTERED_HOLDER,
            "holders MUST be non-empty (N12-SH-01): a backup MUST distribute "
            "to at least the n shards' holders",
            details={"holders": []},
        )

    # Registry membership (the deepening): every id MUST be a registered,
    # deployment-approved holder. Reject the FIRST unregistered id BEFORE
    # sharding (F-AUTHZ-6). NEVER name the registered set in the error (avoid
    # leaking the deployment roster); name only the offending id.
    for i, holder_id in enumerate(out):
        if not registry.is_registered(holder_id):
            logger.warning(
                "vault.holder_registry.unregistered_holder",
                extra={"index": i, "holder_id": holder_id},
            )
            raise VaultBindingError(
                N12FT01Code.UNREGISTERED_HOLDER,
                f"holders[{i}]={holder_id!r} is not in the deployment holder "
                f"registry (N12-SH-01, F-AUTHZ-6): a backup MUST distribute "
                f"shards only to registered, attestable holders",
                details={"index": i, "holder_id": holder_id},
            )
    return out


def check_revocation_k_floor(
    ritual_k: int,
    holders: Sequence[str],
    revoked: Iterable[str],
) -> None:
    """N12-SH-03 — revocation MUST NOT drop the un-revoked set below ``k``.

    Given the current ritual threshold ``k`` (``ShamirRitual.threshold``), the
    full current holder set, and the set of holders being revoked, REFUSE the
    revocation if it would leave fewer than ``k`` un-revoked holders — the vault
    would otherwise become silently unrecoverable. The guard raises a typed
    :class:`~kailash.trust.vault.errors.VaultBindingError` whose disposition is
    "rotation required" (surfaced to the operator, naming the §5 rotation as the
    resolution); it NEVER silently allows the set to drop below ``k``.

    The un-revoked count is computed over the INTERSECTION of ``revoked`` with
    the current holder set (revoking an id not in the current set has no effect
    on the threshold), de-duplicated by holder id.

    NOTE: this guard SURFACES the rotation requirement. The actual for-cause
    generation-advancing rotation (N12-SH-04 — advancing ``kek_generation`` so a
    departed holder's retained shard becomes stale, plus the ``for_cause``
    ``vault_kek_rotation`` anchor) is performed by a later shard (R1 / Wave 5).
    R1 consumes this guard's "rotation required" disposition.

    Args:
        ritual_k: The ritual threshold ``k`` (``ShamirRitual.threshold``).
        holders: The current (pre-revocation) holder-id set.
        revoked: The holder ids being revoked.

    Raises:
        VaultBindingError: ``revoked-holder`` with a "rotation required"
            disposition when the un-revoked count would fall below ``k``.
    """
    current = set(holders)
    revoked_in_set = set(revoked) & current
    remaining = len(current - revoked_in_set)
    if remaining < ritual_k:
        logger.warning(
            "vault.holder_registry.k_floor_breach",
            extra={
                "ritual_k": ritual_k,
                "current_holders": len(current),
                "revoked_in_set": len(revoked_in_set),
                "remaining": remaining,
            },
        )
        raise VaultBindingError(
            N12FT01Code.REVOKED_HOLDER,
            f"holder revocation refused (N12-SH-03): revoking "
            f"{len(revoked_in_set)} of {len(current)} holders would leave "
            f"{remaining} un-revoked holders, below the ritual threshold k="
            f"{ritual_k}; the vault would be unrecoverable. A KEK-rotation (§5, "
            f"N12-SH-04 for-cause generation-advancing rotation) is REQUIRED to "
            f"re-shard to a fresh holder set before this revocation can proceed. "
            f"Surface this to the operator.",
            details={
                "disposition": "rotation-required",
                "ritual_k": ritual_k,
                "current_holders": len(current),
                "revoked_holders": len(revoked_in_set),
                "remaining_holders": remaining,
            },
        )
