# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""EATP-12 per-(handle, generation) KEK-identity commitment registry (N12-CB-04(c)).

The registry is the restore-side source of truth the commitment-auth gate
(N12-FT-02 step 7) consults: ``back_up_vault_key`` REGISTERS the commitment it
computed for the resolved ``(vault_id, kek_generation)`` keyed by the recorded
``kek_commitment_alg``; ``restore_vault_key`` CONSULTS it to recompute the
commitment under the backup's recorded algorithm and discriminate the three
N12-CB-02 codes precisely:

* ``commitment-alg-mismatch`` — NO entry exists for ``(vault_id, captured gen)``
  under the recorded algorithm (the algorithm was never registered / recommitted
  for that vault/generation), NOT a mere difference from the current/latest alg.
* ``kek-commitment-mismatch`` — an entry IS registered under that algorithm but
  the restore's recompute does NOT equal it (injection / wrong passphrase /
  relabelled-generation whose ciphertexts reached step 7).
* ``key-identity-mismatch`` — the target handle's captured key-identity differs
  from the registered key-identity (intra-vault two-KEK-same-generation; N12-IN-04
  binds ``key_id`` at this registry layer, NOT in the §12.2 commitment pre-image).

**N12-IN-04 layering (the load-bearing decision).** The §12.2 commitment pre-image
is ``vault_id``-keyed and OMITS ``key_id`` to stay cross-SDK byte-exact (Wave-1
journal/0006 disposition). ``key_id`` is therefore bound HERE, at the registry
layer: each entry stores the resolved KEK's ``key_id`` alongside the commitment,
and the restore key-identity gate compares the target handle's captured ``key_id``
against the registered one. Until this landed, ``KEY_IDENTITY_MISMATCH`` + the
recorded ``key_id`` were orphaned controls (facade-manager-detection); C2a wires
the comparison.

**ADDITIVE registry (N12-CB-04(c)).** The per-``(vault_id, kek_generation)`` slot
maps ``kek_commitment_alg -> CommitmentEntry``. A recommit (C2b) ADDS a new-alg
entry WITHOUT deleting the prior; both stay live until an explicit retire (C2b)
marks the prior entry non-verifiable via its ``retired`` marker. C2a treats every
registered entry as live; it provides the retire-marker SLOT (``CommitmentEntry.retired``)
that C2b's ``vault_kek_retire`` path sets and the commitment-auth gate reads
(a retired entry → ``retired-commitment-alg``, distinct from the other two codes).

**Deployment persistence.** The conformant shape for this wave + the tests is an
in-memory registry constructed per deployment / per test. A real deployment
persists the registry (the durable record is derivable from the audited recovery-tier
``vault_key_backup`` / ``vault_kek_recommit`` / ``vault_kek_retire`` anchor chain —
the registry is the folded cache of that chain); the persistence backend is the
deployment's concern and out of scope for the in-memory conformant shape here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

__all__ = [
    "CommitmentEntry",
    "CommitmentRegistry",
    "RegistryLookup",
    "default_commitment_registry",
]


@dataclass(frozen=True)
class CommitmentEntry:
    """One registered KEK-identity commitment for a ``(vault_id, gen, alg)`` key.

    Frozen DTO (EATP convention): the commitment hex + the resolved ``key_id``
    (N12-IN-04 registry-layer binding) + the ``retired`` marker (C2b retire slot).

    Attributes:
        commitment: The N12-CB-01 KEK-identity commitment hex (lowercase, SHA-256
            for ``eatp-v1``), as computed and registered at backup time.
        key_id: The resolved KEK's stable key-id captured at backup (N12-IN-04).
            The restore key-identity gate compares the target handle's captured
            ``key_id`` against this; a divergence is a cross-vault / intra-vault
            two-KEK-same-generation re-install.
        retired: The retire marker (N12-CB-04(e)). C2a registers every entry as
            LIVE (``retired=False``); C2b's ``vault_kek_retire`` path sets it True
            and the commitment-auth gate maps a True entry to
            ``retired-commitment-alg`` (never silently verifying against it).
    """

    commitment: str
    key_id: str
    retired: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "commitment": self.commitment,
            "key_id": self.key_id,
            "retired": self.retired,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CommitmentEntry":
        return cls(
            commitment=d["commitment"],
            key_id=d["key_id"],
            retired=bool(d.get("retired", False)),
        )


@dataclass(frozen=True)
class RegistryLookup:
    """The result of consulting the registry for ``(vault_id, gen, alg)`` (restore).

    Discriminates the three N12-CB-02 outcomes WITHOUT performing the recompute
    itself (the commitment-auth gate does the constant-time compare via
    :func:`kailash.trust.vault.commitment.verify_commitment`):

    * ``entry is None`` → NO registered commitment for ``(vault_id, gen)`` under
      ``alg`` → the gate raises ``commitment-alg-mismatch``.
    * ``entry is not None and entry.retired`` → the alg's entry is retired → the
      gate raises ``retired-commitment-alg`` (C2b sets ``retired``; C2a always
      yields ``retired=False``).
    * ``entry is not None and not entry.retired`` → a LIVE entry; the gate
      recomputes + constant-time-compares → ``kek-commitment-mismatch`` on
      inequality, else proceeds to the key-identity gate.
    """

    entry: Optional[CommitmentEntry]


class CommitmentRegistry:
    """Process/deployment-scoped per-(handle, generation) commitment registry.

    Shape (N12-CB-04(c)): ``{(vault_id, kek_generation): {kek_commitment_alg:
    CommitmentEntry}}``. Backup REGISTERS; restore CONSULTS. ADDITIVE — a register
    under a new algorithm for an existing ``(vault_id, gen)`` adds a sibling entry
    without disturbing the prior algorithm's entry; C2b's recommit relies on this.

    The registry is an INJECTED dependency: ``back_up_vault_key`` /
    ``restore_vault_key`` take a ``registry`` parameter so tests construct a fresh
    instance and a deployment wires its persisted one. A module singleton
    (:func:`default_commitment_registry`) backs callers that do not inject one,
    so backup-then-restore in the SAME deployment process finds the registration.
    """

    def __init__(self) -> None:
        # (vault_id, kek_generation) -> {kek_commitment_alg -> CommitmentEntry}
        self._store: Dict[Tuple[str, int], Dict[str, CommitmentEntry]] = {}

    def register(
        self,
        *,
        vault_id: str,
        kek_generation: int,
        kek_commitment_alg: str,
        commitment: str,
        key_id: str,
    ) -> CommitmentEntry:
        """Register (ADDITIVELY) a commitment for ``(vault_id, gen)`` under ``alg``.

        Called by ``back_up_vault_key`` after it computes the commitment. Adds the
        entry to the per-(vault_id, gen) algorithm map without deleting siblings.
        A re-register of the SAME ``(vault_id, gen, alg)`` with an identical
        commitment + key_id is idempotent; a re-register with a DIFFERENT commitment
        OR key_id under the same key is a registration conflict and raises (the
        registry is append-/recommit-only, never silently overwritten — overwrite
        would erase the anti-injection anchor a prior backup registered).

        Returns the registered :class:`CommitmentEntry`.
        """
        slot = self._store.setdefault((vault_id, kek_generation), {})
        existing = slot.get(kek_commitment_alg)
        new_entry = CommitmentEntry(commitment=commitment, key_id=key_id, retired=False)
        if existing is not None:
            if (
                existing.commitment == new_entry.commitment
                and existing.key_id == new_entry.key_id
            ):
                # Idempotent re-register (same backup re-run) — keep the entry.
                logger.debug(
                    "vault.registry.register.idempotent",
                    extra={
                        "vault_id": vault_id,
                        "kek_generation": kek_generation,
                        "kek_commitment_alg": kek_commitment_alg,
                    },
                )
                return existing
            raise ValueError(
                "commitment registry conflict: a DIFFERENT commitment/key_id is "
                f"already registered for (vault_id={vault_id!r}, "
                f"kek_generation={kek_generation}) under alg "
                f"{kek_commitment_alg!r}; the registry is additive (recommit adds a "
                "new-alg entry) and MUST NOT silently overwrite an existing one"
            )
        slot[kek_commitment_alg] = new_entry
        logger.info(
            "vault.registry.register.ok",
            extra={
                "vault_id": vault_id,
                "kek_generation": kek_generation,
                "kek_commitment_alg": kek_commitment_alg,
                "key_id": key_id,
                "live_algs": sorted(slot.keys()),
            },
        )
        return new_entry

    def lookup(
        self,
        *,
        vault_id: str,
        kek_generation: int,
        kek_commitment_alg: str,
    ) -> RegistryLookup:
        """Consult the registry for ``(vault_id, gen)`` under ``alg`` (restore).

        Returns a :class:`RegistryLookup` whose ``entry`` is ``None`` when no
        commitment is registered for that ``(vault_id, gen)`` under that exact
        algorithm (the recorded-alg-never-registered case → the gate raises
        ``commitment-alg-mismatch``). Looks up under the backup's RECORDED
        algorithm, NEVER the current/latest — a superseded-but-registered algorithm
        still resolves (N12-CB-04(b)).
        """
        slot = self._store.get((vault_id, kek_generation))
        if slot is None:
            return RegistryLookup(entry=None)
        return RegistryLookup(entry=slot.get(kek_commitment_alg))

    def live_algs(self, *, vault_id: str, kek_generation: int) -> Tuple[str, ...]:
        """The non-retired algorithm tokens registered for ``(vault_id, gen)``.

        The operator-surfaced growth metric (N12-CB-04(c)) reads over this; C2b's
        recommit/retire path uses it to enforce a per-(vault_id, gen) live-entry
        cap. C2a exposes it so the additive accretion is observable.
        """
        slot = self._store.get((vault_id, kek_generation), {})
        return tuple(sorted(alg for alg, entry in slot.items() if not entry.retired))


# ---------------------------------------------------------------------------
# Module singleton (deployment-default) — backup-then-restore in one process
# ---------------------------------------------------------------------------

_DEFAULT_REGISTRY = CommitmentRegistry()


def default_commitment_registry() -> CommitmentRegistry:
    """Return the process-scoped default registry.

    ``back_up_vault_key`` / ``restore_vault_key`` fall back to this when no
    ``registry`` is injected, so a backup-then-restore in the SAME deployment
    process finds the registration without the caller threading an instance.
    Tests inject a FRESH :class:`CommitmentRegistry` to isolate registrations.
    A real deployment injects its persisted registry (the audited anchor chain
    is the durable source; this in-memory singleton is the conformant default).
    """
    return _DEFAULT_REGISTRY
