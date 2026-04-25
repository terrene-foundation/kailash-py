# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Integration: real SLIP-0039 round-trip + rotate-holders (issue #606).

Tier 2 integration suite -- exercises the audited ``shamir-mnemonic``
reference library through the public ``kailash.trust.vault.shamir`` facade.

Per ``rules/orphan-detection.md`` Rule 2a (Crypto-Pair Round-Trip Through
Facade): paired crypto operations (``generate``/``reconstruct``,
``serialize_shard``/``deserialize_shard``) MUST have a Tier 2 test that
round-trips through the public surface, NOT the underlying library
directly. Isolated unit tests per half can drift silently; round-trip
is the only structural guarantee that the wrapper's contract holds end
to end.

Per ``rules/testing.md`` § 3-Tier: NO mocks. The real ``shamir-mnemonic``
library is used; the suite skips cleanly via :func:`pytest.importorskip`
when the optional ``shamir`` extra is not installed.

Cases:

* 3-of-5 round-trip across multiple shard subsets (any 3 of 5 reconstruct)
* Threshold-1 reconstruct fails (security invariant)
* serialize_shard / deserialize_shard round-trip
* rotate_holders 3-of-5 -> 2-of-3 preserves the secret
* rotate_holders 3-of-5 -> 5-of-7 preserves the secret
"""

from __future__ import annotations

import secrets

import pytest

# Real shamir-mnemonic library -- skip cleanly if the optional extra is
# not installed locally. The Tier 1 suite proves the absence-path
# contract without the lib; this suite proves the cryptographic round
# trip with the lib.
shamir_mnemonic = pytest.importorskip("shamir_mnemonic")  # noqa: F841

from kailash.trust.vault.shamir import (  # noqa: E402  -- import after skip gate
    ShamirRitual,
    deserialize_shard,
    generate,
    reconstruct,
    rotate_holders,
    serialize_shard,
)


# ---------------------------------------------------------------------------
# Generate / reconstruct round-trip
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_shamir_3_of_5_round_trip():
    """Any 3 of 5 shards reconstruct the original 32-byte secret.

    SLIP-0039 reference correctness: the wrapper MUST preserve the
    secret across any threshold-sized subset of the generated shards.
    Tested with 3 different subsets to assert no shard is privileged.
    """
    secret = secrets.token_bytes(32)
    ritual = ShamirRitual(threshold=3, total_shards=5)

    shards = generate(secret, ritual)
    assert len(shards) == 5
    assert all(isinstance(shard, list) for shard in shards)
    assert all(isinstance(word, str) for shard in shards for word in shard)

    # Subset (0, 1, 2) reconstructs.
    rec_a = reconstruct([shards[0], shards[1], shards[2]])
    assert rec_a == secret

    # Subset (1, 3, 4) reconstructs.
    rec_b = reconstruct([shards[1], shards[3], shards[4]])
    assert rec_b == secret

    # Subset (0, 2, 4) reconstructs.
    rec_c = reconstruct([shards[0], shards[2], shards[4]])
    assert rec_c == secret


@pytest.mark.integration
def test_shamir_threshold_minus_one_fails():
    """Reconstruction with threshold-1 shards raises (security invariant).

    The Shamir threshold is the security boundary: fewer than ``threshold``
    shards MUST NOT recover the secret. The underlying SLIP-0039 library
    raises ``MnemonicError`` (subclass of ``Exception``); the wrapper does
    not narrow this, so callers see the library's own typed exception.
    """
    secret = secrets.token_bytes(32)
    ritual = ShamirRitual(threshold=3, total_shards=5)

    shards = generate(secret, ritual)

    # Only 2 shards -- below threshold; library MUST refuse.
    with pytest.raises(Exception):  # noqa: B017 -- MnemonicError is a generic Exception
        reconstruct([shards[0], shards[1]])


# ---------------------------------------------------------------------------
# Serialize / deserialize paper-print round-trip
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_shamir_serialize_deserialize_round_trip():
    """Each generated shard round-trips through serialize/deserialize.

    The paper-print form is the interop surface across SDKs and the
    physical-medium form holders write to paper, engrave on metal, or
    print on cards. Round-trip equality MUST hold for every shard.
    """
    secret = secrets.token_bytes(32)
    ritual = ShamirRitual(threshold=3, total_shards=5)

    shards = generate(secret, ritual)

    for idx, shard in enumerate(shards):
        paper = serialize_shard(shard)
        assert isinstance(paper, str)
        assert " " in paper  # multi-word mnemonic
        recovered = deserialize_shard(paper)
        assert recovered == shard, f"shard[{idx}] round-trip drift"

    # And the round-tripped shards still reconstruct the secret.
    paper_shards = [serialize_shard(s) for s in shards[:3]]
    recovered_shards = [deserialize_shard(p) for p in paper_shards]
    assert reconstruct(recovered_shards) == secret


@pytest.mark.integration
def test_shamir_serialize_deserialize_whitespace_tolerant():
    """deserialize_shard tolerates extra whitespace from paper transcription."""
    secret = secrets.token_bytes(32)
    ritual = ShamirRitual(threshold=2, total_shards=3)

    shards = generate(secret, ritual)
    paper = serialize_shard(shards[0])

    # Insert double-space + leading/trailing whitespace; .split() collapses.
    transcribed = "  " + paper.replace(" ", "  ") + "  "
    recovered = deserialize_shard(transcribed)
    assert recovered == shards[0]


# ---------------------------------------------------------------------------
# Holder rotation
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_rotate_holders_3_of_5_to_2_of_3():
    """Rotation from 3-of-5 to 2-of-3 preserves the original secret.

    Operational scenario: holder set shrinks (two holders depart, the
    remaining three re-ritual under tighter threshold). Any 2 of the
    new 3 shards MUST reconstruct the original secret.
    """
    secret = secrets.token_bytes(32)
    old_ritual = ShamirRitual(threshold=3, total_shards=5)
    new_ritual = ShamirRitual(threshold=2, total_shards=3)

    old_shards = generate(secret, old_ritual)

    # Take any 3 of the 5 old shards as input to rotation.
    new_shards = rotate_holders(old_shards[:3], new_ritual)
    assert len(new_shards) == 3

    # Any 2 of the new 3 shards reconstruct the original secret.
    assert reconstruct([new_shards[0], new_shards[1]]) == secret
    assert reconstruct([new_shards[1], new_shards[2]]) == secret
    assert reconstruct([new_shards[0], new_shards[2]]) == secret


@pytest.mark.integration
def test_rotate_holders_3_of_5_to_5_of_7():
    """Rotation expanding holder set 3-of-5 -> 5-of-7 preserves the secret.

    Operational scenario: governance approves expanding the holder
    quorum. Reconstruction from any 5 of the 7 new shards MUST recover
    the original secret.
    """
    secret = secrets.token_bytes(32)
    old_ritual = ShamirRitual(threshold=3, total_shards=5)
    new_ritual = ShamirRitual(threshold=5, total_shards=7)

    old_shards = generate(secret, old_ritual)
    new_shards = rotate_holders(old_shards[:3], new_ritual)
    assert len(new_shards) == 7

    # 5 shards reconstruct.
    assert reconstruct(new_shards[:5]) == secret
    # A different subset of 5 also reconstructs.
    assert reconstruct(new_shards[2:7]) == secret


@pytest.mark.integration
def test_rotate_holders_below_old_threshold_fails():
    """rotate_holders refuses below-threshold input from the OLD ritual.

    Defense-in-depth: the recombine step inside rotation MUST refuse
    fewer than ``old_ritual.threshold`` shards. Library raises an
    exception; the wrapper propagates.
    """
    secret = secrets.token_bytes(32)
    old_ritual = ShamirRitual(threshold=3, total_shards=5)
    new_ritual = ShamirRitual(threshold=2, total_shards=3)

    old_shards = generate(secret, old_ritual)

    # Only 2 shards -- below the old threshold of 3; rotation MUST refuse.
    with pytest.raises(Exception):  # noqa: B017 -- MnemonicError generic Exception
        rotate_holders(old_shards[:2], new_ritual)
