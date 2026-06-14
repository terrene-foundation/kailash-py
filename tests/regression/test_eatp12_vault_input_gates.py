# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier-1 (deterministic) tests for the EATP-12 vault input surface (W2-I1).

Exercises the entry gates of ``kailash.trust.vault.input_gates`` and the
public ``back_up_vault_key`` / ``restore_vault_key`` entry surface WITHOUT the
SLIP-0039 extra or a real audit dispatcher — every test here fails at a gate
BEFORE any sharding / dispatch, so no real crypto infra is needed.

Conformance coverage (EATP-12 §4.1 / §3.3):

- N12-IN-03 — escape hatch disabled by default → ``escape-hatch-disabled``.
- N12-TH-01 — ritual floor rejects (k=1 via wrapper, n>9, k>n) →
  ``invalid-ritual``.
- N12-CRY-PIN(d) — escape-hatch secret length reject → ``invalid-secret-length``.
- N12-IN-02 — DATA-class resolved key → ``not-a-kek``.
- N12-CL-01/02 — clearance without the token → ``missing-clearance``.
- N12-CRY-PIN(e) — CSPRNG structural: the public ``back_up_vault_key`` carries
  NO entropy/seed parameter.
"""

from __future__ import annotations

import inspect

import pytest

from kailash.trust.key_manager import KeyClass
from kailash.trust.vault.errors import N12FT01Code, VaultBindingError
from kailash.trust.vault.input_gates import (
    ResolvedKek,
    master_secret_bits,
    require_clearance,
    require_escape_hatch_enabled,
    require_holders_supplied,
    require_kek_class,
    require_ritual_floor,
    require_secret_length,
)
from kailash.trust.vault.shamir import ShamirRitual
from kailash.trust.vault.types import ClearanceContext


def _clearance(*caps: str) -> ClearanceContext:
    return ClearanceContext(
        principal="agent-1",
        tenant="t1",
        domain="d1",
        capabilities=tuple(caps),
    )


# ---------------------------------------------------------------------------
# N12-IN-03 — escape hatch disabled by default
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_escape_hatch_disabled_by_default_raises():
    """A raw-bytes invocation with the flag absent → escape-hatch-disabled."""
    with pytest.raises(VaultBindingError) as exc:
        require_escape_hatch_enabled(escape_hatch_enabled=False)
    assert exc.value.code is N12FT01Code.ESCAPE_HATCH_DISABLED


@pytest.mark.regression
def test_escape_hatch_enabled_flag_passes_the_entry_gate():
    """With the explicit flag the entry gate passes (the rest fails closed)."""
    # The entry gate alone returns None; the full enabled path is a later
    # shard (back_up_raw_vault_key still fails-closed after this gate).
    assert require_escape_hatch_enabled(escape_hatch_enabled=True) is None


@pytest.mark.regression
def test_back_up_raw_vault_key_disabled_by_default():
    """The public raw-bytes entrypoint is disabled by default (N12-IN-03)."""
    from kailash.trust.vault import back_up_raw_vault_key

    with pytest.raises(VaultBindingError) as exc:
        back_up_raw_vault_key(
            b"x" * 16,
            ShamirRitual(threshold=2, total_shards=3),
            _clearance("vault:backup"),
            ["h1", "h2", "h3"],
        )
    assert exc.value.code is N12FT01Code.ESCAPE_HATCH_DISABLED


@pytest.mark.regression
def test_back_up_raw_vault_key_enabled_still_fails_closed():
    """Even with the flag set, the unimplemented enabled path fails closed.

    No silent security hole: the enabled path's HELD + dual-emit is a later
    shard, so a flag-enabled raw backup still raises escape-hatch-disabled
    rather than shipping a partial high-risk surface (after passing the
    secret-length pre-check).
    """
    from kailash.trust.vault import back_up_raw_vault_key

    with pytest.raises(VaultBindingError) as exc:
        back_up_raw_vault_key(
            b"x" * 16,
            ShamirRitual(threshold=2, total_shards=3),
            _clearance("vault:backup"),
            ["h1", "h2", "h3"],
            escape_hatch_enabled=True,
        )
    assert exc.value.code is N12FT01Code.ESCAPE_HATCH_DISABLED


# ---------------------------------------------------------------------------
# N12-TH-01 — ritual floor
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_ritual_floor_rejects_k_above_ceiling_n():
    """n > 9 (above the vault ceiling) → invalid-ritual."""
    ritual = ShamirRitual(threshold=2, total_shards=10)  # wrapper allows (<=16)
    with pytest.raises(VaultBindingError) as exc:
        require_ritual_floor(ritual)
    assert exc.value.code is N12FT01Code.INVALID_RITUAL


@pytest.mark.regression
def test_ritual_floor_rejects_k_equals_1_via_wrapper():
    """k=1 is rejected by ShamirRitual itself (1-of-n trivial split).

    The vault floor (k>=2) is stricter; the wrapper already rejects k=1 with
    total>1, so the floor's k>=2 invariant is enforced at construction. We
    pin that the wrapper rejects it (the binding never sees a k=1 ritual).
    """
    with pytest.raises(ValueError, match=r"trivial split"):
        ShamirRitual(threshold=1, total_shards=5)


@pytest.mark.regression
def test_ritual_floor_accepts_valid_floor():
    """A 2<=k<=n<=9 ritual passes the floor gate."""
    assert require_ritual_floor(ShamirRitual(threshold=2, total_shards=3)) is None
    assert require_ritual_floor(ShamirRitual(threshold=9, total_shards=9)) is None


# ---------------------------------------------------------------------------
# N12-CRY-PIN(d) — secret length
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_secret_length_rejects_non_pinned_length():
    """A 17-byte escape-hatch secret → invalid-secret-length."""
    with pytest.raises(VaultBindingError) as exc:
        require_secret_length(b"x" * 17)
    assert exc.value.code is N12FT01Code.INVALID_SECRET_LENGTH


@pytest.mark.regression
def test_secret_length_accepts_128_and_256_bit():
    """16-byte (128-bit) and 32-byte (256-bit) secrets pass."""
    assert require_secret_length(b"x" * 16) == b"x" * 16
    assert require_secret_length(b"y" * 32) == b"y" * 32


@pytest.mark.regression
def test_master_secret_bits_maps_pinned_lengths():
    """master_secret_bits maps 16→128 and 32→256; rejects other lengths."""
    assert master_secret_bits(b"x" * 16) == 128
    assert master_secret_bits(b"x" * 32) == 256
    with pytest.raises(VaultBindingError) as exc:
        master_secret_bits(b"x" * 24)
    assert exc.value.code is N12FT01Code.INVALID_SECRET_LENGTH


# ---------------------------------------------------------------------------
# N12-IN-02 — not-a-kek
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_data_class_resolved_key_rejected_not_a_kek():
    """A DATA-class resolved key → not-a-kek (never shard a data key)."""
    resolved = ResolvedKek(
        master_secret=b"x" * 16,
        key_class=KeyClass.DATA,
        kek_generation=1,
        key_id="k-data",
        passphrase_provenance="vault-derived:v1",
    )
    with pytest.raises(VaultBindingError) as exc:
        require_kek_class(resolved)
    assert exc.value.code is N12FT01Code.NOT_A_KEK


@pytest.mark.regression
def test_kek_class_resolved_key_passes():
    """A KEK-class resolved key passes the type gate."""
    resolved = ResolvedKek(
        master_secret=b"x" * 16,
        key_class=KeyClass.KEK,
        kek_generation=1,
        key_id="k-kek",
        passphrase_provenance="vault-derived:v1",
    )
    assert require_kek_class(resolved) is None


# ---------------------------------------------------------------------------
# N12-CL-01/02 — missing clearance
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_clearance_without_capability_rejected():
    """A clearance lacking the required token → missing-clearance."""
    clearance = _clearance("vault:read")  # has SOME cap, not vault:backup
    with pytest.raises(VaultBindingError) as exc:
        require_clearance(clearance, "vault:backup")
    assert exc.value.code is N12FT01Code.MISSING_CLEARANCE


@pytest.mark.regression
def test_clearance_with_capability_passes():
    """A clearance carrying the token passes."""
    assert require_clearance(_clearance("vault:backup"), "vault:backup") is None


@pytest.mark.regression
def test_clearance_wrong_type_fails_closed():
    """A non-ClearanceContext clearance fails closed → missing-clearance."""
    with pytest.raises(VaultBindingError) as exc:
        require_clearance(None, "vault:backup")  # type: ignore[arg-type]
    assert exc.value.code is N12FT01Code.MISSING_CLEARANCE


# ---------------------------------------------------------------------------
# N12-SH-01 (basic) — holders supplied
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_holders_empty_rejected():
    """An empty holder set → unregistered-holder."""
    with pytest.raises(VaultBindingError) as exc:
        require_holders_supplied([])
    assert exc.value.code is N12FT01Code.UNREGISTERED_HOLDER


@pytest.mark.regression
def test_holders_preserve_order():
    """Holder order is preserved verbatim (distribution order recorded)."""
    assert require_holders_supplied(["c", "a", "b"]) == ["c", "a", "b"]


# ---------------------------------------------------------------------------
# N12-CRY-PIN(e) — CSPRNG structural (no caller-seedable entropy)
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_back_up_vault_key_has_no_entropy_parameter():
    """The public backup surface carries NO entropy/seed param (N12-CRY-PIN(e)).

    EntropySource is a reserved alias no public function accepts; entropy is
    sourced internally from the wrapper's CSPRNG. Enforced structurally.
    """
    from kailash.trust.vault import back_up_vault_key

    params = set(inspect.signature(back_up_vault_key).parameters)
    forbidden = {"entropy", "seed", "entropy_source", "rng", "random_source"}
    leaked = params & forbidden
    assert not leaked, f"back_up_vault_key leaks entropy params: {leaked}"


@pytest.mark.regression
def test_restore_vault_key_has_no_entropy_parameter():
    """restore_vault_key likewise carries no caller-seedable entropy param."""
    from kailash.trust.vault import restore_vault_key

    params = set(inspect.signature(restore_vault_key).parameters)
    forbidden = {"entropy", "seed", "entropy_source", "rng", "random_source"}
    assert not (params & forbidden)


@pytest.mark.regression
def test_resolved_kek_zeroize_drops_secret():
    """ResolvedKek.zeroize replaces the secret bytes (residence minimization)."""
    resolved = ResolvedKek(
        master_secret=b"super-secret-kek",
        key_class=KeyClass.KEK,
        kek_generation=1,
        key_id="k1",
        passphrase_provenance="vault-derived:v1",
    )
    resolved.zeroize()
    assert resolved.master_secret == b""
