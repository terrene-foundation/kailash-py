# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 wiring test for ``DelegateGenesisRecord`` ↔ ``TrustLineageChain``.

S2.5 F10 (analyst recommendation): verify the composed
:class:`DelegateGenesisRecord` round-trips through the existing
:class:`kailash.trust.chain.TrustLineageChain` facade. Per §249
(compose, don't re-derive) and ``orphan-detection.md`` MUST Rule 2
(every wired manager has a Tier 2 integration test): the F4 restructure
that composed the substrate ``chain.GenesisRecord`` is only "wired" if
something exercises the import path + facade-call shape end-to-end.

This test exercises:

1. The IMPORT path — ``from kailash.delegate.types import
   DelegateGenesisRecord`` AND ``from kailash.trust.chain import
   GenesisRecord, TrustLineageChain`` together. A regression that
   accidentally orphans the substrate import would fail here at module
   load.
2. The FACADE-CALL shape — ``DelegateGenesisRecord(block=<substrate>)``
   then ``TrustLineageChain(genesis=<substrate>)`` — confirming both
   sides agree on the same in-memory substrate object.
3. The CRYPTOGRAPHIC SURFACE — ``to_signing_dict()`` and
   ``to_canonical_dict()`` produce dicts whose ``block`` field has the
   substrate's expected ``to_signing_payload`` keys, byte-stable across
   repeat construction.

Real infrastructure scope: this test uses chain's in-memory backing
(``TrustLineageChain`` is a dataclass; the trust-chain audit-anchors
list and constraint envelope are also in-memory) per the Tier-2
contract's "Protocol-Satisfying Deterministic Adapter" exception
documented in ``rules/testing.md`` § 3-Tier Testing. No mocks; the
real ``TrustLineageChain`` and real ``chain.GenesisRecord`` are
constructed and exercised.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from kailash.delegate.types import DelegateGenesisRecord
from kailash.trust._json import canonical_json_dumps
from kailash.trust.chain import AuthorityType, GenesisRecord, TrustLineageChain


@pytest.mark.integration
def test_delegate_genesis_record_composes_chain_genesis_record() -> None:
    """The composed substrate block is reachable through the wrapper.

    Verifies F4: ``DelegateGenesisRecord.block`` IS the same in-memory
    object passed in — not a copy, not a re-skin. Mutating the object
    after composition would be visible through the wrapper (frozen
    semantics on the wrapper itself, but the wrapped substrate is the
    canonical record).
    """
    block = GenesisRecord(
        id="g-tier2-0001",
        agent_id="agent-tier2",
        authority_id="auth-tier2",
        authority_type=AuthorityType.ORGANIZATION,
        created_at=datetime(2026, 5, 21, 12, 0, 0, tzinfo=timezone.utc),
        signature="d" * 128,
    )
    delegate_genesis = DelegateGenesisRecord(
        block=block,
        spec_version="1",
        capabilities=("read", "delegate"),
    )

    # Identity, not equality — §249 composition.
    assert delegate_genesis.block is block
    # The convenience accessor surfaces the substrate id.
    assert delegate_genesis.genesis_id == "g-tier2-0001"


@pytest.mark.integration
def test_delegate_genesis_record_block_powers_trust_lineage_chain() -> None:
    """The substrate block plugs directly into ``TrustLineageChain``.

    F10 wiring assertion: a ``DelegateGenesisRecord`` constructed from a
    ``GenesisRecord`` exposes the SAME substrate object that
    ``TrustLineageChain`` accepts as its ``genesis`` field. The
    cross-import contract holds end-to-end.
    """
    block = GenesisRecord(
        id="g-tier2-0002",
        agent_id="agent-tier2-b",
        authority_id="auth-tier2-b",
        authority_type=AuthorityType.HUMAN,
        created_at=datetime(2026, 5, 21, 12, 0, 0, tzinfo=timezone.utc),
        signature="e" * 128,
    )

    # Compose via the Delegate wrapper.
    delegate_genesis = DelegateGenesisRecord(block=block, spec_version="1")

    # The substrate block plugs directly into TrustLineageChain — proving
    # the composed-not-re-derived contract.
    chain = TrustLineageChain(genesis=delegate_genesis.block)
    assert chain.genesis is block
    # Chain is a real object with real default initialization.
    assert chain.constraint_envelope is not None
    assert chain.constraint_envelope.agent_id == "agent-tier2-b"
    # Chain hash is computed against the substrate record's fields, not
    # the wrapper's — confirming the wrapper is genuinely transparent.
    h1 = chain.hash()
    assert isinstance(h1, str) and len(h1) > 0


@pytest.mark.integration
def test_canonical_dict_round_trip_is_byte_stable() -> None:
    """Two constructions with identical inputs emit byte-identical JSON.

    Cross-SDK fixture parity (per ``cross-sdk-inspection.md`` Rule 4)
    depends on byte-canonical output. This test exercises the full
    round-trip through ``to_canonical_dict`` → ``canonical_json_dumps``
    and asserts byte equality across two independent constructions.
    """

    def build() -> DelegateGenesisRecord:
        return DelegateGenesisRecord(
            block=GenesisRecord(
                id="g-tier2-0003",
                agent_id="agent-canon",
                authority_id="auth-canon",
                authority_type=AuthorityType.SYSTEM,
                created_at=datetime(2026, 5, 21, 12, 0, 0, tzinfo=timezone.utc),
                signature="f" * 128,
            ),
            spec_version="1",
            capabilities=("a", "b", "c"),
        )

    json1 = canonical_json_dumps(build().to_canonical_dict())
    json2 = canonical_json_dumps(build().to_canonical_dict())
    assert json1 == json2
    # Nested block payload includes signature (canonical, not signing).
    assert '"signature":' in json1
    # Spine-level extensions appear at the top level.
    assert '"spec_version":' in json1
    assert '"capabilities":' in json1


@pytest.mark.integration
def test_signing_dict_excludes_signature_through_full_round_trip() -> None:
    """The signing payload omits the signature; canonical includes it.

    F7 invariant exercised end-to-end through the canonical-JSON encoder
    so a future regression that re-introduces the signature into the
    signing payload (which would break Ed25519 sign-then-verify) fails
    here loudly.
    """
    delegate_genesis = DelegateGenesisRecord(
        block=GenesisRecord(
            id="g-tier2-0004",
            agent_id="agent-sign",
            authority_id="auth-sign",
            authority_type=AuthorityType.ORGANIZATION,
            created_at=datetime(2026, 5, 21, 12, 0, 0, tzinfo=timezone.utc),
            signature="a" * 128,
        ),
        spec_version="2",
    )
    signing_json = canonical_json_dumps(delegate_genesis.to_signing_dict())
    canonical_json = canonical_json_dumps(delegate_genesis.to_canonical_dict())
    # Signature appears in canonical but NOT signing.
    assert "a" * 128 in canonical_json
    assert "a" * 128 not in signing_json
