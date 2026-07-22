# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Canonical chain-state signing pre-image (#1912 Wave 2).

Wave 2 binds the WHOLE chain state under ONE Ed25519 signature by the genesis
authority, closing two store-writer vectors nothing else signs:

* MED-1 (whole-capability-set deletion) — deleting a capability that carries a
  constraint (while another capability still grants the action) silently drops
  the constraint. The capability id leaves ``capability_ids`` → the pre-image
  changes → the signature breaks.
* MED-2 (reasoning-suppression + directly-injected constraints) — the persisted
  ``ChainConstraintEnvelope`` is UNSIGNED; a store-writer strips a
  ``REASONING_REQUIRED`` (or any directly-injected) constraint with nothing to
  break. The constraint feeds ``constraint_hash`` in the pre-image → stripping
  it changes the recomputed hash → the signature breaks.

The pre-image is a DETERMINISTIC, reproducible-at-verify dict:

    {genesis_id, sorted(capability_ids), sorted(delegation_ids), constraint_hash}

Distinct from ``TrustLineageChain.hash()``:

* ``hash()`` (unsalted variant) reads the STORED ``constraint_envelope.constraint_hash``
  field verbatim. A store-writer who strips a constraint from
  ``active_constraints`` AND leaves the stored ``constraint_hash`` untouched
  would keep ``hash()`` unchanged. This pre-image RE-COMPUTES the constraint
  hash from ``active_constraints`` (via ``ChainConstraintEnvelope._compute_hash``),
  so a strip-without-rehash is still caught — the recomputed hash differs from
  the one the signature was made over.
* ``hash()`` also has a salted (deployment-local) linked-hashing variant; this
  pre-image never uses a salt, so it is byte-reproducible at verify across
  processes and stores.

Cross-SDK classification (``cross-sdk-inspection.md`` Rule 4d): the SIGNATURE is
deployment-local (it binds random ``gen-``/``cap-``/``del-`` UUIDs + a SHA-256
constraint hash, signed by the deployment's genesis-authority key), so there is
no fixed cross-deployment byte vector to pin. The pre-image ENCODING, however,
routes through ``serialize_for_signing`` — the shared cross-SDK trust-plane
canonical contract (sorted keys, ``ensure_ascii=True``, ``allow_nan=False``).
Chain-state signing is a NEW Python-only Wave-2 feature; the Rust SDK has no
equivalent yet, so a not-configured chain signs BYTE-IDENTICALLY to pre-Wave-2
(the field prunes-when-unset — see ``chain_state_serde``). If the sibling SDK
adds chain-state signing, it MUST mirror THIS pre-image dict shape + the
``serialize_for_signing`` encoding (a cross-SDK structure contract, filed
separately); a fixed-input canonical-form regression pins the encoding here as a
tripwire.
"""

from __future__ import annotations

from typing import Any, List, Optional, Protocol

from kailash.trust.signing.crypto import serialize_for_signing

__all__ = ["chain_state_canonical_payload", "chain_state_canonical_payload_str"]


class _EnvelopeLike(Protocol):
    """Structural type for the constraint envelope the pre-image reads."""

    active_constraints: List[Any]

    def _compute_hash(self) -> str: ...


class _GenesisLike(Protocol):
    id: str


class _ChainStateSource(Protocol):
    """Structural type for the chain fields the pre-image reads.

    A LOCAL Protocol (not an import of ``kailash.trust.chain.TrustLineageChain``)
    keeps this low-level signing module one-way dependent on ``chain`` — the
    high-level ``chain`` module imports THIS module at module scope, so a
    back-edge would form a load-time cycle (mirrors ``delegation_fold_serde`` /
    ``capability_fold_serde``). ``TrustLineageChain`` satisfies it structurally.
    """

    genesis: _GenesisLike
    capabilities: List[Any]
    delegations: List[Any]
    constraint_envelope: Optional[_EnvelopeLike]


def _constraint_component(env: Optional[_EnvelopeLike]) -> str:
    """RE-COMPUTE the constraint hash from ``active_constraints``.

    Mirrors ``ChainConstraintEnvelope.__post_init__``'s empty-case convention
    (an empty / absent envelope → ``""``) so a legitimate empty chain signs a
    stable pre-image. For a non-empty envelope the hash is RE-DERIVED from the
    live ``active_constraints`` (never the stored ``constraint_hash`` field), so
    a store-writer stripping a constraint without re-writing the stored hash is
    still detected at verify.
    """
    if env is None or not env.active_constraints:
        return ""
    return env._compute_hash()


def chain_state_canonical_payload(chain: _ChainStateSource) -> dict:
    """Build the deterministic chain-state pre-image dict (#1912 Wave 2)."""
    return {
        "genesis_id": chain.genesis.id,
        "capability_ids": sorted(c.id for c in chain.capabilities),
        "delegation_ids": sorted(d.id for d in chain.delegations),
        "constraint_hash": _constraint_component(chain.constraint_envelope),
    }


def chain_state_canonical_payload_str(chain: _ChainStateSource) -> str:
    """Serialize the chain-state pre-image for signing / verification.

    Routes through ``serialize_for_signing`` (the shared cross-SDK trust-plane
    canonical encoder: sorted keys, ``ensure_ascii=True``, ``allow_nan=False``),
    so the sign and verify sites recompute byte-identical pre-images.
    """
    return serialize_for_signing(chain_state_canonical_payload(chain))
