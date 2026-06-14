# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""EATP-12 stale-generation guard substrate (§6 / N12-SG-02/03/05, N12-RT-05).

This module supplies the C3 ordinal-generation gate's two data sources plus the
RT-05 post-recovery posture trigger. It is consumed by
:func:`kailash.trust.vault.backup.restore_vault_key` at FT-02 **step 8**
(``ordinal-generation``):

* :func:`current_generation_from_chain` — derives the vault's CURRENT
  ``kek_generation`` from the AUDITED rotation chain (N12-RT-06): the latest
  ``vault_kek_rotation`` anchor for the vault in the recovery tier. The current
  generation MUST be derivable from the signed, dispatcher-mediated anchor chain,
  NOT a locally-mutable counter (N12-RT-06). When no rotation anchor exists, the
  vault is single-generation and the captured generation IS current — there is no
  staleness to compare.

* :class:`CompromisedGenerationDenylist` — a per-vault denylist of REVOKED /
  compromised generations (N12-SG-05). Injected exactly like the C2a
  :class:`~kailash.trust.vault.registry.CommitmentRegistry` (process singleton
  default; tests inject a fresh instance). A restore presenting a denylisted
  generation is refused with ``revoked-generation`` EVEN WHEN the generation
  equals current AND EVEN UNDER ``force_stale`` — the denylist is the one gate
  ``force_stale`` does NOT override.

* :func:`trigger_d6_posture_downgrade` — the N12-RT-05 trigger. ANY restore that
  MATERIALIZES the KEK (ordinary or forced-stale, NO re-wrap carve-out)
  downgrades the principal's posture to :attr:`~kailash.trust.posture.postures.TrustPosture.SUPERVISED`
  via the injected :class:`~kailash.trust.posture.posture_store.SQLitePostureStore`
  (or the :class:`~kailash.trust.posture.postures.PostureStore` Protocol) AND
  records a 7-day cooling-off start. This binding TRIGGERS D6 by reference to
  ``eatp/10-shamir-recovery.md@v1.0`` §8; it does NOT redefine D6. The Wave-4
  CL-04 cooling-off gate (B1) CONSUMES the recorded cooling-off start; C3 FIRES
  it. The downgrade is a fail-closed monotonic move toward SUPERVISED: when the
  principal already sits at or below SUPERVISED on the autonomy total order
  (D5), the posture is NOT escalated (no upgrade), but the cooling-off start is
  ALWAYS (re-)recorded so the clock restarts on every materializing restore.

The denylist + the current-generation chain-derivation are BOTH derivable from
the audited recovery-tier anchor chain (N12-SG-05: "derivable from the audited
rotation/denylist anchor chain, not a locally-mutable store"); the in-memory
forms here are the conformant shape for this wave + the Tier-2 tests, mirroring
the C2a registry's in-memory-folded-cache disposition. A real deployment folds
both from the durable anchor chain.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Set, Tuple

from kailash.trust.posture.postures import (
    PostureStore,
    PostureTransition,
    TransitionResult,
    TrustPosture,
)

logger = logging.getLogger(__name__)

__all__ = [
    "COOLING_OFF_DAYS",
    "RESTORE_STALE_CAPABILITY",
    "CompromisedGenerationDenylist",
    "default_compromised_generation_denylist",
    "current_generation_from_chain",
    "trigger_d6_posture_downgrade",
]

#: The D6 cooling-off interval (eatp/10-shamir-recovery.md@v1.0 §8): a restore
#: that materializes the KEK starts a 7-day cooling-off (N12-RT-05 / N12-CL-04).
#: The B1 CL-04 gate (Wave 4) reads the recorded start + this interval; C3 records
#: the start. The interval is named here so both halves cite ONE constant.
COOLING_OFF_DAYS: int = 7

#: The DISTINCT higher capability a forced-stale restore requires IN ADDITION to
#: ``vault:restore`` (N12-SG-03 / F-AUTHZ-9). A caller holding only
#: ``vault:restore`` with ``force_stale=True`` is refused with
#: ``missing-clearance``. (``vault:override`` is the spec's named alternative;
#: this binding gates on ``vault:restore-stale``.)
RESTORE_STALE_CAPABILITY: str = "vault:restore-stale"

#: The recovery-tier OUTCOME subtype that advances a vault's generation
#: (N12-RT-06). The current generation the stale guard consults is the LATEST
#: such anchor's ``kek_generation`` for the vault. ``vault_key_backup`` /
#: ``vault_holder_rotation`` establish a distribution but do NOT advance the
#: generation, so they are NOT consulted for current-generation derivation.
_KEK_ROTATION_SUBTYPE: str = "vault_kek_rotation"


def current_generation_from_chain(
    dispatcher: Any,
    *,
    vault_id: str,
    captured_generation: int,
) -> int:
    """Derive the vault's CURRENT ``kek_generation`` from the audited chain (N12-RT-06/SG-02).

    Scans the recovery-tier engine for the LATEST ``vault_kek_rotation`` anchor
    whose ``vault_id`` matches, returning its ``kek_generation``. When NO rotation
    anchor exists, the vault is single-generation: the ``captured_generation`` IS
    current (returned unchanged), so the ordinal staleness comparison is a no-op
    (captured == current).

    The current generation is sourced from the signed, dispatcher-mediated anchor
    chain — NOT a locally-mutable counter an attacker can edit (N12-RT-06 /
    EATP-08 D2c). A generation-rollback attempt (an attacker lowering a mutable
    counter to make a stale backup look current) is structurally impossible here:
    the chain is append-only and the LATEST rotation anchor's generation is the
    high-water mark.

    Args:
        dispatcher: The named-tier audit dispatcher (D1). Its recovery-tier engine
            holds the rotation/backup distribution anchors.
        vault_id: The vault whose current generation to derive.
        captured_generation: The captured generation being restored (the
            single-generation fallback when no rotation chain exists).

    Returns:
        The current generation: the latest ``vault_kek_rotation``'s
        ``kek_generation`` for ``vault_id``, or ``captured_generation`` when no
        such anchor exists.
    """
    engine = getattr(dispatcher, "_engines", {}).get("recovery")
    if engine is None:
        # No recovery-tier engine to consult → single-generation surface.
        return captured_generation
    current: Optional[int] = None
    for entry in engine.entries:
        payload = entry.event_payload
        if (
            payload.get("subtype") == _KEK_ROTATION_SUBTYPE
            and payload.get("vault_id") == vault_id
        ):
            gen = payload.get("kek_generation")
            if isinstance(gen, int) and not isinstance(gen, bool):
                # Latest-wins (entries are append-ordered); the chain is
                # monotonic so the last rotation anchor carries the high-water.
                current = gen
    if current is None:
        return captured_generation
    return current


class CompromisedGenerationDenylist:
    """Per-vault denylist of REVOKED/compromised KEK generations (N12-SG-05).

    Injected exactly like the C2a :class:`~kailash.trust.vault.registry.CommitmentRegistry`:
    ``restore_vault_key`` takes a ``denylist`` parameter so tests construct a fresh
    instance and a deployment wires its persisted one; a module singleton
    (:func:`default_compromised_generation_denylist`) backs callers that do not
    inject one.

    A revoked generation is refused with ``revoked-generation`` at FT-02 step 8
    EVEN WHEN it equals the current generation (the ordinal stale guard is purely
    ordinal and does not catch re-installing a current-but-compromised KEK before
    a rotation advances the counter — F-CRYPTO-6) AND EVEN UNDER ``force_stale``
    (the denylist is the one gate ``force_stale`` does NOT override — N12-SG-05).

    Shape (N12-SG-05): ``{(vault_id, kek_generation)}`` membership. The durable
    record is derivable from the audited denylist anchor chain; the in-memory set
    is the conformant shape for this wave + the Tier-2 tests (mirrors the C2a
    registry's in-memory-folded-cache disposition).
    """

    def __init__(self) -> None:
        self._revoked: Set[Tuple[str, int]] = set()

    def revoke(self, *, vault_id: str, kek_generation: int) -> None:
        """Mark ``(vault_id, kek_generation)`` REVOKED/compromised (N12-SG-05).

        Operationally a compromise report MUST ALSO advance/rotate the current
        generation (N12-RT-06) so the compromised one becomes stale AND
        denylisted; this method records the denylist half. Idempotent.
        """
        if (
            not isinstance(kek_generation, int)
            or isinstance(kek_generation, bool)
            or kek_generation < 0
        ):
            raise ValueError(
                f"kek_generation must be a non-negative int; got {kek_generation!r}"
            )
        if not vault_id or not isinstance(vault_id, str):
            raise ValueError("vault_id must be a non-empty string")
        self._revoked.add((vault_id, kek_generation))
        logger.warning(
            "vault.denylist.revoke",
            extra={"vault_id": vault_id, "kek_generation": kek_generation},
        )

    def is_revoked(self, *, vault_id: str, kek_generation: int) -> bool:
        """Membership check (N12-SG-05). Fail-closed: a malformed key → False here.

        The restore gate calls this on the ALREADY-AUTHENTICATED captured
        generation (step 7 ran first), so the inputs are well-formed; this guard
        returns False only for a key never revoked.
        """
        return (vault_id, kek_generation) in self._revoked


# ---------------------------------------------------------------------------
# Module singleton (deployment-default) — mirrors C2a's default registry
# ---------------------------------------------------------------------------

_DEFAULT_DENYLIST = CompromisedGenerationDenylist()


def default_compromised_generation_denylist() -> CompromisedGenerationDenylist:
    """Return the process-scoped default compromised-generation denylist.

    ``restore_vault_key`` falls back to this when no ``denylist`` is injected, so
    a revoke-then-restore in the SAME deployment process sees the revocation
    without the caller threading an instance. Tests inject a FRESH instance to
    isolate revocations. A real deployment injects its persisted denylist (the
    audited anchor chain is the durable source; this in-memory singleton is the
    conformant default).
    """
    return _DEFAULT_DENYLIST


# ---------------------------------------------------------------------------
# N12-RT-05 — D6 trigger by reference (PostureStore downgrade + cooling-off)
# ---------------------------------------------------------------------------

#: The metadata key the recorded transition carries the cooling-off start under.
#: The Wave-4 CL-04 gate (B1) reads ``metadata[COOLING_OFF_START_KEY]`` + the
#: COOLING_OFF_DAYS interval; C3 records it on every materializing restore.
COOLING_OFF_START_KEY: str = "cooling_off_start"
COOLING_OFF_END_KEY: str = "cooling_off_end"
RESTORE_D6_REASON: str = "post-recovery D6 downgrade (N12-RT-05): KEK materialized"


def trigger_d6_posture_downgrade(
    posture_store: PostureStore,
    *,
    principal: str,
    forced_stale: bool,
    now: Optional[datetime] = None,
) -> TransitionResult:
    """Fire the N12-RT-05 D6 trigger: downgrade to SUPERVISED + start cooling-off.

    Called by ``restore_vault_key`` AFTER a successful KEK-materializing restore
    (ordinary OR forced-stale — NO re-wrap carve-out; EVERY materializing restore
    triggers D6 by reference per N12-RT-05 / §5.4). This binding TRIGGERS D6; it
    does NOT redefine it (the SUPERVISED downgrade + 7-day cooling-off are owned by
    ``eatp/10-shamir-recovery.md@v1.0`` §8). The Wave-4 CL-04 gate consumes the
    recorded cooling-off start.

    The downgrade is fail-closed + monotonic toward SUPERVISED:

    * If the principal's current posture is MORE autonomous than SUPERVISED
      (AUTONOMOUS / DELEGATING per the D5 autonomy total order), set it to
      SUPERVISED (a downgrade).
    * If the principal already sits AT or BELOW SUPERVISED (SUPERVISED / TOOL /
      PSEUDO), the posture is NOT escalated — D6 never RAISES autonomy — but the
      cooling-off start is STILL (re-)recorded so the 7-day clock restarts on this
      materializing restore.

    The transition is persisted to ``posture_store`` via ``set_posture`` (the
    posture slot) AND ``record_transition`` (the durable cooling-off receipt the
    CL-04 gate reads). A trust-anchored ``now`` is supplied by the caller when
    available; otherwise UTC wall-clock is used (the recorded start is metadata,
    not the forgeable host-time the anchor's trust-anchored timestamp guards).

    Args:
        posture_store: The injected posture store (a real ``SQLitePostureStore``
            against a temp DB in Tier-2 — NO mock — or any ``PostureStore``).
        principal: The acting principal whose posture is downgraded.
        forced_stale: Whether the materializing restore was a forced-stale
            rollback (recorded in the transition metadata for the CL-04 gate's
            audit trail; does NOT change the SUPERVISED target — every
            materializing restore triggers D6 identically).
        now: Optional trust-anchored UTC datetime for the cooling-off start;
            defaults to ``datetime.now(timezone.utc)``.

    Returns:
        The :class:`~kailash.trust.posture.postures.TransitionResult` recorded
        (carries the cooling-off start/end in ``metadata`` + the SUPERVISED
        target). The caller does NOT need the result; it is returned for the
        Tier-2 test to assert the cooling-off receipt landed.
    """
    start = now if now is not None else datetime.now(timezone.utc)
    end = start + timedelta(days=COOLING_OFF_DAYS)

    current = posture_store.get_posture(principal)
    target = TrustPosture.SUPERVISED
    # Monotonic toward SUPERVISED: never RAISE autonomy. If the principal is
    # already at/below SUPERVISED, hold the current (lower-or-equal) posture as
    # the slot value but STILL record the cooling-off receipt.
    if current.autonomy_level <= target.autonomy_level:
        slot_posture = current
        transition_type = PostureTransition.MAINTAIN
    else:
        slot_posture = target
        transition_type = PostureTransition.DOWNGRADE

    posture_store.set_posture(principal, slot_posture)

    result = TransitionResult(
        success=True,
        from_posture=current,
        to_posture=slot_posture,
        transition_type=transition_type,
        reason=RESTORE_D6_REASON,
        timestamp=start,
        metadata={
            "agent_id": principal,
            "trigger": "vault_restore_materialized_kek",
            "forced_stale": forced_stale,
            COOLING_OFF_START_KEY: start.isoformat(),
            COOLING_OFF_END_KEY: end.isoformat(),
            "cooling_off_days": COOLING_OFF_DAYS,
        },
    )
    posture_store.record_transition(result)
    logger.info(
        "vault.restore.d6_triggered",
        extra={
            "principal": principal,
            "from_posture": current.value,
            "to_posture": slot_posture.value,
            "forced_stale": forced_stale,
            "cooling_off_end": end.isoformat(),
        },
    )
    return result
