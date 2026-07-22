# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#1912 re-signing migration — promote legacy chains to the Wave-3 posture.

#1912 hardened the trust plane in three waves:

* **Wave 1** bound each capability to its holder subject (``v1-subject-bound``),
  closing the cross-chain capability-transplant HIGH.
* **Wave 2** added ONE genesis-authority ``chain_state_signature`` over the
  chain-state pre-image, closing whole-capability-set deletion (MED-1) and
  constraint/REASONING_REQUIRED suppression (MED-2).
* **Wave 3 (A1)** flips :meth:`~kailash.trust.operations.TrustOperations.verify`
  to FAIL CLOSED: a legacy (un-subject-bound) capability is REJECTED, and a
  chain with NO chain-state signature is REJECTED (each gated by a distinct
  migration-window opt-out — ``allow_unbound_legacy_capabilities`` /
  ``allow_unsigned_chain_state`` — that default to ``False``).

The installed base — chains persisted before #1912 — carries legacy caps and
NO chain-state signature. Under Wave-3 fail-closed enforcement those chains
would be rejected on upgrade. This migration re-signs the installed base to the
Wave-3 posture so a deployment can flip enforcement on (clear both opt-outs)
without breaking existing agents.

STANDALONE, NOT auto-run
------------------------
This migration is a deliberate operator action, never triggered implicitly by
``verify`` / ``establish``. Run it once during the migration window, confirm the
report, then clear the opt-out flags.

TRUSTED-STORE PRECONDITION (``trust_store_placement``)
------------------------------------------------------
Promoting a legacy capability BINDS it to the chain it CURRENTLY sits in. A
legacy cap carries NO holder subject in its signed bytes (the exact Wave-1
transplant vulnerability), so the migration CANNOT cryptographically verify a
legacy cap's original holder — it can only trust the store's current placement.
A store-writer who transplanted a genuine legacy capability (signed by the same
authority) into another chain BEFORE the migration would have that transplant
laundered into a valid v1 cap. Therefore legacy-cap promotion is REFUSED by
default and requires ``migrate(trust_store_placement=True)``, which the operator
sets ONLY when running against a TRUSTED store state — a snapshot taken before
the store was exposed to untrusted writers, or a locked-down maintenance window
(the ``force_drop`` / ``force_downgrade`` safe-default idiom). Post-migration
every cap is v1-subject-bound, so the RUNTIME transplant defense is fully in
force and any FUTURE transplant is rejected by ``verify``.

What it does per chain (IDEMPOTENT — safe to re-run)
----------------------------------------------------
* With ``trust_store_placement=True``: promote every LOCALLY-SIGNABLE legacy
  capability to ``v1-subject-bound`` and re-sign it over the holder-subject
  pre-image (``genesis.agent_id``) with the chain's genesis-authority key. A cap
  already at v1 is left untouched. With ``trust_store_placement=False`` (default)
  legacy caps are REPORTED, not promoted.
* Add a genesis-authority ``chain_state_signature`` when the chain has none AND
  no legacy cap was left un-promoted (signing a set that still holds an
  un-enforceable legacy cap would attest an incompletely-migrated chain). FRESH
  chain-state signing ALSO requires ``trust_store_placement=True``: it re-signs
  over the chain's CURRENT constraint envelope + id-set, which the migration
  cannot verify (there is no prior chain-state signature to check against), so a
  store-writer who stripped a constraint AND the old signature would have the
  suppression blessed (MED-2/MED-1) — the same trust-the-store decision as
  legacy-cap promotion (RT-sec-w3r3 Finding D). A chain already carrying a VALID
  chain-state signature is left untouched (the ``is None`` guard), so idempotent
  re-runs and genuinely-signed chains need no ack. (Promoting a cap does NOT
  change ``capability_ids`` / ``constraint_hash``, so it never invalidates an
  existing chain-state signature.)

What it CANNOT migrate (reported, never silently dropped)
---------------------------------------------------------
* A capability whose ``attester_id`` is NOT the chain's genesis authority (an
  external attester the local genesis key cannot re-sign for). It is left legacy
  and reported — verifying it needs the external attester's own re-signing.
* A chain whose genesis-authority signing key is absent from the local
  ``TrustKeyManager`` (or whose authority cannot be resolved). Nothing on that
  chain can be re-signed locally; the whole chain is reported un-migratable.

Reversibility
-------------
The apply is failure-atomic: every CHANGED chain is snapshotted (a byte-exact
pre-migration copy) BEFORE any write; on ANY apply error every snapshot is
restored and :class:`SubjectBindingMigrationError` is raised, so a failed run
leaves the store exactly as it found it. The snapshots are also returned on the
report, so a SUCCESSFUL migration is explicitly reversible via
:meth:`SubjectBindingMigration.rollback` (a byte-exact restore — NOT a
security-downgrading logical demote, which this migration deliberately does not
offer). ``dry_run=True`` computes the full report and changes nothing.
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from kailash.trust.chain import (
    CAPABILITY_SIGNING_VERSION_LEGACY,
    CAPABILITY_SIGNING_VERSION_V1,
    TrustLineageChain,
)
from kailash.trust.exceptions import (
    AuthorityInactiveError,
    AuthorityNotFoundError,
    InvalidSignatureError,
    TrustError,
)
from kailash.trust.signing.chain_state_signing import chain_state_canonical_payload_str
from kailash.trust.signing.crypto import serialize_for_signing

__all__ = [
    "SubjectBindingMigration",
    "SubjectBindingMigrationError",
    "MigrationReport",
    "UnmigratableItem",
]

logger = logging.getLogger(__name__)


class SubjectBindingMigrationError(TrustError):
    """Raised when the #1912 re-signing migration fails to apply.

    On apply failure the store is restored to its pre-migration state (see the
    module docstring § Reversibility) before this is raised.
    """


@dataclass
class UnmigratableItem:
    """A chain or capability the local genesis key could not re-sign."""

    agent_id: str
    kind: str  # "capability" | "chain"
    reason: str
    capability_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "kind": self.kind,
            "reason": self.reason,
            "capability_id": self.capability_id,
        }


@dataclass
class MigrationReport:
    """Outcome of a #1912 re-signing migration run."""

    total_chains: int = 0
    migrated_chains: int = 0
    promoted_capabilities: int = 0
    added_chain_state_signatures: int = 0
    already_current_chains: int = 0
    unmigratable: List[UnmigratableItem] = field(default_factory=list)
    dry_run: bool = False
    # Byte-exact pre-migration copies of every CHANGED chain, keyed by agent_id.
    # Populated on a non-dry-run apply; consumed by ``rollback``. Excluded from
    # ``to_dict`` (it holds full chain objects, not a serialisable summary).
    snapshots: Dict[str, TrustLineageChain] = field(default_factory=dict)

    @property
    def fully_migrated(self) -> bool:
        """True when every chain reached the Wave-3 posture (no un-migratable items)."""
        return not self.unmigratable

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_chains": self.total_chains,
            "migrated_chains": self.migrated_chains,
            "promoted_capabilities": self.promoted_capabilities,
            "added_chain_state_signatures": self.added_chain_state_signatures,
            "already_current_chains": self.already_current_chains,
            "unmigratable": [u.to_dict() for u in self.unmigratable],
            "fully_migrated": self.fully_migrated,
            "dry_run": self.dry_run,
        }


class SubjectBindingMigration:
    """Re-sign the installed base to the #1912 Wave-3 fail-closed posture.

    Construct with the same three dependencies :class:`TrustOperations` uses, run
    :meth:`migrate`, inspect the :class:`MigrationReport`, then clear the
    ``allow_unbound_legacy_capabilities`` / ``allow_unsigned_chain_state``
    opt-outs to enforce.
    """

    def __init__(self, authority_registry: Any, key_manager: Any, trust_store: Any):
        self.authority_registry = authority_registry
        self.key_manager = key_manager
        self.trust_store = trust_store

    async def migrate(
        self,
        *,
        trust_store_placement: bool = False,
        dry_run: bool = False,
        batch_size: int = 100,
    ) -> MigrationReport:
        """Enumerate persisted chains and re-sign them to the Wave-3 posture.

        Args:
            trust_store_placement: Explicit acknowledgment (default ``False`` =
                REFUSE) required to PROMOTE a legacy capability. A legacy cap
                carries NO holder subject in its signed bytes (that is the exact
                Wave-1 transplant vulnerability), so the migration CANNOT
                cryptographically verify a legacy cap's original holder — it can
                only bind the cap to the chain it CURRENTLY sits in. A
                store-writer who transplanted a genuine legacy capability (signed
                by the same authority) into another chain BEFORE the migration
                would have that transplant blessed into a valid v1 cap
                (RT-sec-w3r2 Finding C). Set ``True`` ONLY when running against a
                TRUSTED store state — a snapshot taken before the store was
                exposed to untrusted writers, or a locked-down maintenance
                window. With ``False`` every legacy cap is REPORTED as requiring
                the acknowledgment and is NOT promoted (the codebase
                ``force_drop`` / ``force_downgrade`` safe-default idiom). This
                ALSO gates FRESH chain-state signing (adding a signature where the
                chain has none) — re-signing over the chain's current,
                unverifiable constraint envelope is the same trust-the-store
                decision (RT-sec-w3r3 Finding D). A chain already carrying a VALID
                chain-state signature is left untouched, so idempotent re-runs
                need no ack.
            dry_run: When True, compute the full report but write NOTHING.
            batch_size: Pagination size for ``trust_store.list_chains``.

        Returns:
            A :class:`MigrationReport`. On a non-dry-run it carries the
            pre-migration ``snapshots`` for :meth:`rollback`.

        Raises:
            SubjectBindingMigrationError: If a write fails; the store is restored
                to its pre-migration state before this is raised.
        """
        report = MigrationReport(dry_run=dry_run)
        # (agent_id, updated_chain, original_chain) for every CHANGED chain.
        updates: List[Tuple[str, TrustLineageChain, TrustLineageChain]] = []

        offset = 0
        while True:
            chains = await self.trust_store.list_chains(
                active_only=True, limit=batch_size, offset=offset
            )
            if not chains:
                break
            for chain in chains:
                report.total_chains += 1
                original = copy.deepcopy(chain)
                updated = copy.deepcopy(chain)
                changed = await self._migrate_chain_in_place(
                    updated, report, trust_store_placement
                )
                if changed:
                    updates.append((updated.genesis.agent_id, updated, original))
                else:
                    report.already_current_chains += 1
            if len(chains) < batch_size:
                break
            offset += batch_size

        report.migrated_chains = len(updates)
        if dry_run or not updates:
            return report

        await self._apply_atomically(updates, report)
        return report

    async def _migrate_chain_in_place(
        self,
        chain: TrustLineageChain,
        report: MigrationReport,
        trust_store_placement: bool,
    ) -> bool:
        """Promote legacy caps + add a chain-state signature. Returns True if changed.

        Reports (never silently drops) any cap/chain the local genesis key cannot
        re-sign, or any legacy cap the operator has not acknowledged trusting the
        placement of (``trust_store_placement``). A deep-COPY is passed in, so
        mutation here never touches the persisted original until
        :meth:`_apply_atomically` commits it.
        """
        gen_authority_id = chain.genesis.authority_id
        # Resolve the genesis authority + confirm the local key can sign. If not,
        # the WHOLE chain is un-migratable locally (report, change nothing).
        try:
            authority = await self.authority_registry.get_authority(
                gen_authority_id, include_inactive=True
            )
        except (AuthorityNotFoundError, AuthorityInactiveError):
            report.unmigratable.append(
                UnmigratableItem(
                    agent_id=chain.genesis.agent_id,
                    kind="chain",
                    reason=(
                        f"genesis authority {gen_authority_id!r} unresolved — "
                        "cannot re-sign locally"
                    ),
                )
            )
            return False

        signing_key_id = getattr(authority, "signing_key_id", None)
        if not signing_key_id or not self.key_manager.get_key(signing_key_id):
            report.unmigratable.append(
                UnmigratableItem(
                    agent_id=chain.genesis.agent_id,
                    kind="chain",
                    reason=(
                        f"genesis signing key {signing_key_id!r} absent from the "
                        "local key manager — cannot re-sign locally"
                    ),
                )
            )
            return False

        changed = False
        # Track whether any legacy cap was left un-promoted (external attester,
        # forged signature, or trust-placement not acknowledged). If so, the chain
        # still holds an un-enforceable cap, so a chain-state signature over that
        # set MUST NOT be added — signing it would attest a set the operator has
        # not fully migrated (RT-sec-w3r2 Q2 hardening).
        has_unpromoted_legacy = False

        # 1. Promote every locally-signable, placement-acknowledged legacy
        #    capability to v1-subject-bound.
        for cap in chain.capabilities:
            version = getattr(
                cap, "signing_payload_version", CAPABILITY_SIGNING_VERSION_LEGACY
            )
            if version != CAPABILITY_SIGNING_VERSION_LEGACY:
                continue  # already v1 (or a recognised non-legacy) — idempotent skip
            if getattr(cap, "attester_id", None) != gen_authority_id:
                # External attester — the local genesis key cannot re-sign FOR it.
                report.unmigratable.append(
                    UnmigratableItem(
                        agent_id=chain.genesis.agent_id,
                        kind="capability",
                        reason=(
                            f"capability attester {getattr(cap, 'attester_id', None)!r}"
                            f" != genesis authority {gen_authority_id!r} — needs the "
                            "external attester to re-sign"
                        ),
                        capability_id=cap.id,
                    )
                )
                has_unpromoted_legacy = True
                continue
            # SECURITY (#1912 Wave 3 — RT-sec-w3r2 Finding C, the TRANSPLANT axis):
            # a legacy cap carries NO holder subject in its signed bytes, so its
            # signature verifies IDENTICALLY on ANY chain under the same attester.
            # Promoting it binds it to the chain it CURRENTLY sits in — an
            # unverifiable trust-the-store-placement decision. A store-writer who
            # transplanted a genuine legacy cap into this chain before the
            # migration would have that transplant laundered into a valid v1 cap.
            # REFUSE unless the operator explicitly acknowledges a trusted store
            # snapshot (the force_drop / force_downgrade safe-default idiom).
            if not trust_store_placement:
                report.unmigratable.append(
                    UnmigratableItem(
                        agent_id=chain.genesis.agent_id,
                        kind="capability",
                        reason=(
                            "legacy capability promotion requires "
                            "trust_store_placement=True — the migration binds a "
                            "legacy cap to its CURRENT chain and cannot verify a "
                            "legacy cap's original holder (no subject in the signed "
                            "bytes); run against a TRUSTED store snapshot"
                        ),
                        capability_id=cap.id,
                    )
                )
                has_unpromoted_legacy = True
                continue
            # SECURITY (#1912 Wave 3 — RT-sec-w3 Finding A): VERIFY the cap's
            # EXISTING legacy signature BEFORE re-signing it. The migration is the
            # ONLY component holding the genesis key that touches persisted store
            # content, so re-signing an UN-verified legacy cap would launder a
            # store-writer's injected/tampered capability into a valid v1 cap — a
            # signature-laundering oracle that defeats the exact bounded-trust
            # store-writer threat model #1912 defends against (the attester_id
            # check above is NOT sufficient: attester_id is attacker-writable). A
            # cap whose existing legacy signature does not verify against the
            # genesis authority is REPORTED, never promoted. The legacy pre-image
            # is deterministic (no subject), so this is a cheap, exact check.
            legacy_payload = serialize_for_signing(cap.to_signing_payload())
            try:
                legacy_ok = await self.key_manager.verify(
                    legacy_payload, cap.signature, authority.public_key
                )
            except (InvalidSignatureError, ValueError):
                legacy_ok = False
            if not legacy_ok:
                report.unmigratable.append(
                    UnmigratableItem(
                        agent_id=chain.genesis.agent_id,
                        kind="capability",
                        reason=(
                            "existing legacy signature does not verify against the "
                            "genesis authority — refusing to re-sign (possible store "
                            "tamper / injection); re-issue this capability"
                        ),
                        capability_id=cap.id,
                    )
                )
                has_unpromoted_legacy = True
                continue
            cap.signing_payload_version = CAPABILITY_SIGNING_VERSION_V1
            cap_payload = serialize_for_signing(
                cap.to_signing_payload(subject_agent_id=chain.genesis.agent_id)
            )
            cap.signature = await self.key_manager.sign(cap_payload, signing_key_id)
            report.promoted_capabilities += 1
            changed = True

        # 2. Add a chain-state signature when absent — but ONLY if no legacy cap
        #    was left un-promoted (signing a chain-state that still contains an
        #    un-enforceable legacy cap would attest an incompletely-migrated set,
        #    RT-sec-w3r2 Q2). An EXISTING valid chain-state signature is preserved,
        #    not re-issued (the ``is None`` guard) — promoting a cap does not change
        #    capability_ids/constraint_hash, and idempotent re-runs need no ack.
        if (
            not has_unpromoted_legacy
            and getattr(chain, "chain_state_signature", None) is None
        ):
            # SECURITY (#1912 Wave 3 — RT-sec-w3r3 Finding D, enforcement-surface
            # parity with Finding C): FRESH chain-state signing re-signs over the
            # chain's CURRENT constraint envelope + id-set, which the migration
            # CANNOT verify (there is no prior chain-state signature to check
            # against — that is why we are adding one). A store-writer who stripped
            # a REASONING_REQUIRED / spend constraint AND the old signature leaves a
            # chain byte-shape-identical to a legitimate post-Wave-1/pre-Wave-2
            # target; re-signing it would BLESS the suppression (MED-2/MED-1 bypass).
            # This is the SAME trust-the-store-placement decision as legacy-cap
            # promotion, so it ALSO requires the trusted-snapshot acknowledgment.
            if not trust_store_placement:
                report.unmigratable.append(
                    UnmigratableItem(
                        agent_id=chain.genesis.agent_id,
                        kind="chain",
                        reason=(
                            "chain-state signing requires trust_store_placement="
                            "True — the migration re-signs over the chain's CURRENT "
                            "(unverified) constraint envelope and id-set; a store-"
                            "writer could have stripped a constraint AND the old "
                            "signature. Run against a TRUSTED store snapshot"
                        ),
                    )
                )
            else:
                cs_payload = chain_state_canonical_payload_str(chain)
                chain.chain_state_signature = await self.key_manager.sign(
                    cs_payload, signing_key_id
                )
                report.added_chain_state_signatures += 1
                changed = True

        return changed

    async def _apply_atomically(
        self,
        updates: List[Tuple[str, TrustLineageChain, TrustLineageChain]],
        report: MigrationReport,
    ) -> None:
        """Write every changed chain; roll back ALL on any failure.

        Snapshots (the pre-migration originals) are recorded on the report BEFORE
        any write, so a partial failure restores the store to its pre-migration
        state, and a SUCCESSFUL run remains reversible via :meth:`rollback`.
        """
        applied: List[str] = []
        for snap_agent_id, _updated, original in updates:
            report.snapshots[snap_agent_id] = original
        current_agent = ""
        try:
            for agent_id, updated, _original in updates:
                current_agent = agent_id
                await self.trust_store.update_chain(agent_id, updated)
                applied.append(agent_id)
        except Exception as exc:  # noqa: BLE001 — restore then re-raise (fail-closed)
            restore_failures = await self._restore(applied, report.snapshots)
            if restore_failures:
                logger.critical(
                    "subject_binding_1912 migration rollback INCOMPLETE — the "
                    "trust store is in an inconsistent state; agents whose "
                    "restore failed: %s",
                    restore_failures,
                )
            report.snapshots.clear()
            report.migrated_chains = 0
            raise SubjectBindingMigrationError(
                f"#1912 re-signing migration failed applying chain "
                f"{current_agent!r}: {exc}"
            ) from exc

    async def rollback(self, report: MigrationReport) -> int:
        """Byte-exact restore of every chain a prior :meth:`migrate` changed.

        Restores the pre-migration snapshots captured by the run that produced
        ``report``. This is a byte-exact revert, NOT a security-downgrading
        logical demote. Returns the number of chains restored.

        Raises:
            SubjectBindingMigrationError: If any restore write fails.
        """
        if not report.snapshots:
            return 0
        agent_ids = list(report.snapshots.keys())
        restore_failures = await self._restore(agent_ids, report.snapshots)
        if restore_failures:
            raise SubjectBindingMigrationError(
                f"#1912 migration rollback failed for chains: {restore_failures}"
            )
        return len(agent_ids)

    async def _restore(
        self, agent_ids: List[str], snapshots: Dict[str, TrustLineageChain]
    ) -> List[str]:
        """Best-effort restore of the given agents from snapshots.

        Returns the list of agent_ids whose restore write RAISED (so the caller
        can escalate an inconsistent-state CRITICAL), attempting every remaining
        restore rather than aborting on the first failure.
        """
        failures: List[str] = []
        for agent_id in agent_ids:
            original = snapshots.get(agent_id)
            if original is None:
                continue
            try:
                await self.trust_store.update_chain(agent_id, original)
            except Exception:  # noqa: BLE001 — collect, keep restoring
                logger.exception(
                    "subject_binding_1912: failed to restore chain %s during "
                    "rollback",
                    agent_id,
                )
                failures.append(agent_id)
        return failures
