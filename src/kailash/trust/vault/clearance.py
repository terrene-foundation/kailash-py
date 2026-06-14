# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""EATP-12 clearance evaluation — CL-01/02/02a token+scope + CL-04 cooling-off (W4-B1).

This module is the load-bearing authorization gate the vault binding runs at
FT-02 **step 1** (restore) and before key resolution (backup). It deepens I1's
``require_clearance`` presence-check (still the seed) into the full §4.2 control
the spec mandates:

* **N12-CL-01 / N12-CL-02** — the calling agent MUST hold the required
  ``vault:*`` token in the **bound role's capability set** (``CapabilitySet`` —
  the substrate axis the shipped ``DispatchSurface`` Invariant 3 reads, NOT the
  ``DelegateConstraintEnvelope``). The clearance gate is INDEPENDENT of the
  quorum / commitment / generation gates (each fails on its own axis).

* **N12-CL-02a (binding-OWNED tenant/domain scoping — the load-bearing new
  control)** — a ``vault:*`` token is NOT scope-free. The shipped capability
  gate (``dispatch.py:1441-1463``) reads only token membership and is
  domain-blind, and ``RoleScope`` (``types.py:579``) carries only ``domain`` and
  has NO tenant field. The binding therefore performs, IN ADDITION to token
  membership and in this **fail-closed order — tenant, then domain, then
  token**:

  - (a) the bound tenant (``ClearanceContext.tenant``, resolved from the
    clearance context, NEVER read off ``RoleScope``) MUST equal the vault's
    tenant resolved from the handle (``ResolvedKek.vault_tenant``);
  - (b) the bound role's domain (``ClearanceContext.domain``) MUST COVER the
    vault's domain (``ResolvedKek.vault_domain``) — an explicit binding-added
    check since the substrate gate is domain-blind;
  - (c) the token-membership check (CL-01/02).

  A ``vault:restore`` granted in tenant/domain A MUST fail ``missing-clearance``
  against a target in tenant/domain B EVEN with k valid shards.

* **N12-CL-04 (cooling-off capability suspension; trust-anchored clock)** —
  during the 7-day cooling-off window after a materializing restore (C3's RT-05
  recorded the start in the PostureStore transition metadata via
  ``COOLING_OFF_START_KEY``), the recovered principal's
  ``vault:restore``/``vault:backup``/``vault:rotate`` tokens are SUSPENDED: a
  second such op by that principal MUST require the governance-approver HELD
  action (N12-CL-03) regardless of level, OR — when no approver is configured —
  be rejected with ``missing-clearance`` (the conformant Wave-4 disposition; the
  CL-03 HELD-approver override is the X1 seam, see :func:`evaluate_clearance`).
  The window determination MUST use the **trust-anchored clock** (the same
  trust-anchor that signed the recovery anchor's timestamp); a clock
  roll-forward MUST NOT lift the suspension, and on inability to consult
  trust-anchored time the suspension REMAINS in force (fail-closed). This is a
  binding-local consequence of D6; it does NOT redefine D6.

The CL-04 read sources the cooling-off start from the injected PostureStore's
transition history (``get_history`` → the latest transition whose metadata
carries :data:`~kailash.trust.vault.stale_guard.COOLING_OFF_START_KEY`). The
window is ``[start, start + COOLING_OFF_DAYS)``; ``now`` is the trust-anchored
clock the caller supplies (the same source C3 used). When no PostureStore is
available the cooling-off check cannot run — the conservative default is NOT to
suspend (no receipt = no prior materializing restore); but once a receipt
EXISTS, an inability to read a trust-anchored ``now`` keeps the suspension in
force (fail-closed).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from kailash.trust.posture.postures import PostureStore
from kailash.trust.vault.errors import N12FT01Code, VaultBindingError
from kailash.trust.vault.input_gates import ResolvedKek, require_clearance
from kailash.trust.vault.stale_guard import COOLING_OFF_DAYS, COOLING_OFF_START_KEY
from kailash.trust.vault.types import ClearanceContext

logger = logging.getLogger(__name__)

__all__ = [
    "ROTATE_CAPABILITY",
    "COOLING_OFF_SUSPENDED_CAPABILITIES",
    "domain_covers",
    "read_cooling_off_start",
    "is_in_cooling_off",
    "evaluate_clearance",
]

#: The capability token a KEK rotation requires. CL-04 suspends this token (with
#: ``vault:restore`` + ``vault:backup``) during the cooling-off window.
ROTATE_CAPABILITY: str = "vault:rotate"

#: The ``vault:*`` tokens CL-04 SUSPENDS during the 7-day cooling-off window
#: (N12-CL-04). A second op requiring ANY of these by the recovered principal
#: within the window is rejected with ``missing-clearance`` (no approver
#: configured) — the X1 HELD-approver override is documented in
#: :func:`evaluate_clearance`.
COOLING_OFF_SUSPENDED_CAPABILITIES: frozenset[str] = frozenset(
    {"vault:restore", "vault:backup", "vault:rotate"}
)


def domain_covers(bound_domain: str, vault_domain: str) -> bool:
    """Return True iff ``bound_domain`` COVERS ``vault_domain`` (N12-CL-02a(b)).

    PACT D/T/R domains are hierarchical path identifiers. A bound domain covers a
    vault domain when they are EQUAL or the vault domain is a strict descendant
    (path-prefix with a ``/`` boundary, so ``"prod"`` covers ``"prod/eu"`` but
    NOT ``"production"``). Fail-closed: a non-string or empty input never covers.

    The substrate capability gate is domain-blind (``dispatch.py:1441-1463``
    reads only token membership), so this is the binding-OWNED check the spec
    mandates the binding add — the binding MUST NOT rely on the substrate to
    perform a tenant/domain capability cascade.
    """
    if not isinstance(bound_domain, str) or not isinstance(vault_domain, str):
        return False
    if not bound_domain or not vault_domain:
        return False
    if bound_domain == vault_domain:
        return True
    return vault_domain.startswith(bound_domain + "/")


def read_cooling_off_start(
    posture_store: Optional[PostureStore], principal: str
) -> Optional[datetime]:
    """Read the principal's most-recent cooling-off start from the PostureStore.

    Sources the trust-anchored cooling-off start C3's RT-05 recorded into the
    transition metadata (``metadata[COOLING_OFF_START_KEY]``) via
    ``record_transition``. Scans ALL of the principal's transitions and returns
    the LATEST cooling-off start by parsed timestamp (NOT by history iteration
    order — the window must be independent of the store's ordering contract),
    parsed as a timezone-aware UTC datetime.

    Returns ``None`` when there is no PostureStore, no history, or no recorded
    cooling-off start (no prior materializing restore → no suspension to enforce
    — the conservative no-receipt default). A malformed / unparseable recorded
    start does NOT silently vanish: it is treated as a receipt-EXISTS-but-
    unreadable signal and surfaced via :class:`VaultBindingError` so the
    fail-closed branch in :func:`is_in_cooling_off` keeps the suspension in
    force (a receipt exists; the clock cannot be read).

    Raises:
        VaultBindingError: ``MISSING_CLEARANCE`` when a cooling-off receipt
            EXISTS but its recorded start cannot be parsed (fail-closed: the
            suspension stays in force when a receipt is present but the
            trust-anchored time cannot be consulted, N12-CL-04).
    """
    if posture_store is None:
        # No store to consult → the cooling-off check cannot run. No receipt =
        # no prior materializing restore = no suspension (the documented
        # conservative default). The SUSPENSION fail-closed only applies AFTER a
        # receipt exists.
        return None

    # MED (Wave-4 gate): the window MUST be computed from the LATEST cooling-off
    # start (the most recent materializing restore), selected by parsed timestamp
    # — NOT by get_history iteration order. A first-match return would, against a
    # store that yields oldest-first, compute the window from a principal's FIRST
    # restore and expire it ~7d early → under-suspending a twice-recovered
    # principal in-window (the exact CL-04 risk). Take the max over ALL matching
    # receipts so the result is independent of the store's ordering contract.
    history = posture_store.get_history(principal)
    latest: Optional[datetime] = None
    for transition in history:
        raw = transition.metadata.get(COOLING_OFF_START_KEY)
        if raw is None:
            continue
        # A receipt EXISTS for this principal. Parse the trust-anchored start.
        try:
            start = datetime.fromisoformat(str(raw))
        except (ValueError, TypeError) as exc:
            # Receipt present but the recorded start cannot be read → fail-closed
            # per N12-CL-04: keep the suspension in force; surface a typed deny
            # rather than silently treating an unreadable clock as "not in
            # cooling-off". An unparseable receipt cannot be ordered against the
            # parseable ones, so it cannot be ruled out as the newest — fail
            # closed (suspend) rather than risk under-suspension.
            raise VaultBindingError(
                N12FT01Code.MISSING_CLEARANCE,
                "cooling-off receipt exists for the principal but its recorded "
                "start is unparseable (N12-CL-04 fail-closed: suspension remains "
                "in force when trust-anchored time cannot be consulted)",
                details={"principal": principal},
            ) from exc
        if start.tzinfo is None:
            # Normalize a naive timestamp to UTC; the recorded start is the
            # trust-anchored UTC instant C3 wrote (always tz-aware in practice).
            start = start.replace(tzinfo=timezone.utc)
        if latest is None or start > latest:
            latest = start
    return latest


def is_in_cooling_off(
    posture_store: Optional[PostureStore],
    *,
    principal: str,
    now: Optional[datetime] = None,
) -> bool:
    """Return True iff ``principal`` is within the 7-day cooling-off window (N12-CL-04).

    The window is ``[start, start + COOLING_OFF_DAYS)`` where ``start`` is the
    trust-anchored cooling-off start the most-recent materializing restore
    recorded (:func:`read_cooling_off_start`). ``now`` is the trust-anchored
    clock the caller supplies — the SAME source C3 used to write the start, NEVER
    a locally-mutable wall clock. A clock roll-forward beyond ``start + 7d`` lets
    the window expire naturally; it does NOT *lift* an active suspension early.

    Fail-closed (N12-CL-04): when a cooling-off receipt EXISTS but the
    trust-anchored ``now`` cannot be consulted, the suspension REMAINS in force.
    :func:`read_cooling_off_start` already raises if the recorded start itself is
    unreadable; here, if ``now`` is unavailable AND a start exists, we treat the
    principal as suspended.

    Returns ``False`` only when there is genuinely no cooling-off receipt (no
    prior materializing restore) OR the window has provably expired under the
    trust-anchored clock.
    """
    start = read_cooling_off_start(posture_store, principal)
    if start is None:
        # No receipt → no prior materializing restore → not suspended.
        return False

    if now is None:
        # A receipt exists but the caller supplied no trust-anchored clock → the
        # window cannot be evaluated → fail-closed: suspension remains in force.
        logger.warning(
            "vault.clearance.cooling_off_clock_unavailable",
            extra={
                "principal": principal,
                "detail": (
                    "cooling-off receipt exists but no trust-anchored now was "
                    "supplied; N12-CL-04 fail-closed — suspension remains in "
                    "force"
                ),
            },
        )
        return True

    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    end = start + timedelta(days=COOLING_OFF_DAYS)
    # In-window iff start <= now < end. A roll-forward only ever moves `now`
    # toward/past `end` (window expires); it cannot move `now` before `start`,
    # so it cannot lift an active suspension early.
    return start <= now < end


def evaluate_clearance(
    clearance: ClearanceContext,
    resolved: ResolvedKek,
    required_token: str,
    *,
    posture_store: Optional[PostureStore] = None,
    now: Optional[datetime] = None,
    approver_configured: bool = False,
) -> None:
    """Evaluate the full §4.2 clearance gate (CL-01/02 + CL-02a + CL-04).

    Runs the binding-OWNED tenant/domain scoping in the **fail-closed order
    tenant → domain → token**, then the CL-04 cooling-off suspension. The gate is
    INDEPENDENT of the quorum/commitment/generation gates (N12-CL-02): it fails
    on its OWN axis (``missing-clearance``) regardless of shard validity.

    Order (each failure → ``missing-clearance``, fail-closed):

    1. **(CL-02a a) tenant** — ``clearance.tenant`` MUST equal
       ``resolved.vault_tenant`` (the vault's tenant resolved from the handle,
       NEVER read off ``RoleScope``). A wrong-tenant input surfaces HERE — before
       domain, before token.
    2. **(CL-02a b) domain** — ``clearance.domain`` MUST COVER
       ``resolved.vault_domain`` (:func:`domain_covers`).
    3. **(CL-01/02 c) token** — ``clearance`` MUST hold ``required_token`` in its
       capability set (delegates to I1's :func:`require_clearance`, the
       presence-check seed, now the third axis of the deepened gate).
    4. **(CL-04) cooling-off** — if ``required_token`` is one of
       :data:`COOLING_OFF_SUSPENDED_CAPABILITIES` AND the principal is within the
       7-day window (:func:`is_in_cooling_off`), the token is SUSPENDED. With NO
       governance-approver configured (the Wave-4 conformant disposition) the op
       is rejected ``missing-clearance``. **X1 seam:** when CL-03 lands, an
       ``approver_configured=True`` deployment routes a suspended op through the
       governance-approver HELD action instead of rejecting; until CL-03 is
       implemented, ``approver_configured=True`` STILL rejects fail-closed (the
       HELD path is not yet wired and MUST NOT silently fail open).

    Args:
        clearance: The bound authorization context (CL-02a tenant/domain source —
            tenant is read HERE, never off RoleScope).
        resolved: The resolved KEK carrying the vault's ``vault_tenant`` +
            ``vault_domain`` (the resolver is the trusted-module source of the
            vault's tenant/domain; the binding does NOT trust caller args for it).
        required_token: ``vault:backup`` / ``vault:restore`` / ``vault:rotate`` /
            ``vault:restore-stale`` — the token this operation requires.
        posture_store: The injected PostureStore the CL-04 read consults. When
            ``None`` the cooling-off check cannot run (no-receipt conservative
            default — see :func:`read_cooling_off_start`).
        now: The trust-anchored clock for the CL-04 window (the SAME source C3
            used to record the start). NEVER a locally-mutable wall clock.
        approver_configured: Whether a governance-approver (CL-03) is configured.
            The X1 seam: ``True`` will, once CL-03 lands, route a suspended op
            through the HELD action; until then it STILL rejects (no silent
            fail-open).

    Raises:
        VaultBindingError: ``MISSING_CLEARANCE`` on a tenant mismatch, a domain
            non-coverage, a missing token, or a cooling-off suspension.
    """
    if not isinstance(clearance, ClearanceContext):
        # Mirror require_clearance's typed guard so the tenant/domain reads below
        # never touch a non-ClearanceContext (fail-closed: unknown → deny).
        raise VaultBindingError(
            N12FT01Code.MISSING_CLEARANCE,
            "clearance MUST be a ClearanceContext (N12-CL-01/02a); got "
            f"{type(clearance).__name__}",
            details={"required_capability": required_token},
        )

    # (1) CL-02a(a) — tenant FIRST. The bound tenant comes from the clearance
    # context; the vault tenant comes from the resolver. NEVER read tenant off
    # RoleScope (it has no tenant field). A wrong-tenant token fails HERE even
    # with k valid shards.
    if clearance.tenant != resolved.vault_tenant:
        raise VaultBindingError(
            N12FT01Code.MISSING_CLEARANCE,
            "clearance tenant does not match the vault's tenant "
            "(N12-CL-02a(a) fail-closed: tenant checked first)",
            details={"required_capability": required_token},
        )

    # (2) CL-02a(b) — domain SECOND. The bound role's domain MUST cover the
    # vault's domain (substrate gate is domain-blind; this is binding-added).
    if not domain_covers(clearance.domain, resolved.vault_domain):
        raise VaultBindingError(
            N12FT01Code.MISSING_CLEARANCE,
            "clearance domain does not cover the vault's domain "
            "(N12-CL-02a(b) fail-closed: domain checked after tenant)",
            details={"required_capability": required_token},
        )

    # (3) CL-01/02 — token THIRD. I1's presence-check seed, now the token axis.
    require_clearance(clearance, required_token)

    # (4) CL-04 — cooling-off suspension. Only the materializing-op tokens are
    # suspended; a non-suspended token (e.g. a read-only capability) is unaffected.
    if required_token in COOLING_OFF_SUSPENDED_CAPABILITIES and is_in_cooling_off(
        posture_store, principal=clearance.principal, now=now
    ):
        # The recovered principal's vault:* token is suspended during the window.
        # X1 seam (N12-CL-03): a configured governance-approver would route the
        # op through the HELD action here. CL-03 is NOT yet implemented, so the
        # conformant Wave-4 disposition is to reject fail-closed — even when
        # approver_configured=True (no silent fail-open until the HELD path
        # lands).
        raise VaultBindingError(
            N12FT01Code.MISSING_CLEARANCE,
            "principal is within the 7-day post-recovery cooling-off window "
            f"(N12-CL-04): the {required_token!r} token is SUSPENDED. A second "
            "materializing op requires the governance-approver HELD action "
            "(N12-CL-03, an X1 seam not yet implemented) or is rejected; no "
            "approver is configured for this deployment, so the op is denied.",
            details={
                "required_capability": required_token,
                "approver_configured": approver_configured,
            },
        )
