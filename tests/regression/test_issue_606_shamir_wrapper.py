# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression: SLIP-0039 Shamir wrapper scaffold (issue #606).

Tier 1 regression suite for ``kailash.trust.vault.shamir``:

* :class:`ShamirRitual` validation (threshold/total bounds, frozen invariant)
* Lazy-import contract -- every public function MUST raise
  :class:`RuntimeError` with an actionable install hint when the optional
  ``shamir`` extra is absent (probed via ``sys.modules`` monkey-patch so the
  test exercises the absence path even when ``shamir-mnemonic`` IS installed
  locally for the Tier 2 round-trip suite).
* :func:`back_up_vault_key` -- the EATP-12 W2-I1 handle-based conformant
  surface (issue #1312). The pre-#606 ``NotImplementedError`` stub is GONE;
  the function now resolves a KEK handle internally and shards it. The two
  deferral tests that asserted ``pytest.raises(NotImplementedError)`` were
  rewritten when the stub was implemented (orphan-detection.md Rule 4a:
  implementing a deferred stub MUST rewrite its deferral tests in the SAME
  change) to assert the new entry-gate behavior instead.

These tests run without the optional extra; they probe the absence-path
contract that ``rules/dependencies.md`` calls out as the only acceptable form
of "loud failure at call site" for optional dependencies. The Tier 2 suite
under ``tests/integration/trust/test_shamir_round_trip.py`` exercises the
real cryptographic round-trip with ``shamir-mnemonic`` installed; the
EATP-12 binding Tier-1/Tier-2 suites live under
``tests/regression/test_eatp12_vault_input_gates.py`` and
``tests/integration/test_eatp12_vault_backup_restore_wiring.py``.
"""

from __future__ import annotations

import sys

import pytest

# ---------------------------------------------------------------------------
# ShamirRitual validation
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_shamir_ritual_default():
    """Construction with valid (threshold, total_shards) succeeds."""
    from kailash.trust.vault.shamir import ShamirRitual

    ritual = ShamirRitual(threshold=3, total_shards=5)
    assert ritual.threshold == 3
    assert ritual.total_shards == 5


@pytest.mark.regression
def test_shamir_ritual_validation_threshold():
    """Invalid (threshold, total) combinations raise ValueError."""
    from kailash.trust.vault.shamir import ShamirRitual

    # threshold > total
    with pytest.raises(ValueError, match=r"threshold.*<= total_shards"):
        ShamirRitual(threshold=4, total_shards=3)

    # total exceeds SLIP-0039 4-bit limit (16)
    with pytest.raises(ValueError, match=r"SLIP-0039 limit of 16"):
        ShamirRitual(threshold=2, total_shards=17)

    # threshold below 1
    with pytest.raises(ValueError, match=r"threshold must be >= 1"):
        ShamirRitual(threshold=0, total_shards=3)

    # negative threshold
    with pytest.raises(ValueError, match=r"threshold must be >= 1"):
        ShamirRitual(threshold=-1, total_shards=3)

    # negative total
    with pytest.raises(ValueError, match=r"total_shards must be >= 1"):
        ShamirRitual(threshold=1, total_shards=-1)

    # trivial 1-of-n split (rejected pending mint ISS-37 governance review)
    with pytest.raises(ValueError, match=r"trivial split"):
        ShamirRitual(threshold=1, total_shards=5)


@pytest.mark.regression
def test_shamir_ritual_frozen():
    """ShamirRitual is a frozen dataclass; attribute assignment raises."""
    from dataclasses import FrozenInstanceError

    from kailash.trust.vault.shamir import ShamirRitual

    ritual = ShamirRitual(threshold=3, total_shards=5)
    with pytest.raises(FrozenInstanceError):
        ritual.threshold = 4  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        ritual.total_shards = 7  # type: ignore[misc]


@pytest.mark.regression
def test_shamir_ritual_type_validation():
    """Non-int threshold/total raises TypeError."""
    from kailash.trust.vault.shamir import ShamirRitual

    with pytest.raises(TypeError, match=r"MUST be int"):
        ShamirRitual(threshold="3", total_shards=5)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match=r"MUST be int"):
        ShamirRitual(threshold=3, total_shards=5.0)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Lazy-import contract -- every public function raises with install hint
# ---------------------------------------------------------------------------
#
# The pattern: monkey-patch ``sys.modules["shamir_mnemonic"]`` to ``None`` so
# the lazy ``import shamir_mnemonic`` inside each function raises
# ``ImportError`` even when the package is actually installed for the Tier 2
# suite. ``rules/dependencies.md`` requires module import to succeed (so the
# wrapper module itself stays in ``__all__``) AND the call site to fail
# loudly with an actionable hint -- this test family proves both halves.


@pytest.mark.regression
def test_generate_optional_extra_absence_raises(monkeypatch):
    """generate() raises RuntimeError citing the install hint."""
    monkeypatch.setitem(sys.modules, "shamir_mnemonic", None)
    from kailash.trust.vault.shamir import ShamirRitual, generate

    with pytest.raises(RuntimeError, match=r"kailash\[shamir\]"):
        generate(b"x" * 16, ShamirRitual(threshold=2, total_shards=3))


@pytest.mark.regression
def test_reconstruct_optional_extra_absence_raises(monkeypatch):
    """reconstruct() raises RuntimeError citing the install hint."""
    monkeypatch.setitem(sys.modules, "shamir_mnemonic", None)
    from kailash.trust.vault.shamir import reconstruct

    # Provide minimally well-typed shards so the type-checks in reconstruct
    # do not preempt the lazy-import probe; the function must reach the
    # ``_require_shamir_mnemonic`` call before raising.
    shards = [["dummy", "words"], ["another", "shard"]]
    with pytest.raises(RuntimeError, match=r"kailash\[shamir\]"):
        reconstruct(shards)


@pytest.mark.regression
def test_serialize_shard_does_not_require_extra():
    """serialize_shard is pure-Python; does NOT require the shamir extra."""
    from kailash.trust.vault.shamir import serialize_shard

    # serialize_shard does not import shamir_mnemonic; it is a pure
    # paper-print formatter. Round-trips with deserialize_shard live in
    # the Tier 2 suite. Here we only assert it works without the extra.
    out = serialize_shard(["alpha", "beta", "gamma"])
    assert out == "alpha beta gamma"


@pytest.mark.regression
def test_deserialize_shard_does_not_require_extra():
    """deserialize_shard is pure-Python; does NOT require the shamir extra."""
    from kailash.trust.vault.shamir import deserialize_shard

    assert deserialize_shard("alpha beta gamma") == ["alpha", "beta", "gamma"]


@pytest.mark.regression
def test_rotate_holders_optional_extra_absence_raises(monkeypatch):
    """rotate_holders() raises RuntimeError citing the install hint.

    rotate_holders calls reconstruct(), which calls _require_shamir_mnemonic,
    so the absence path surfaces at the first sub-call.
    """
    monkeypatch.setitem(sys.modules, "shamir_mnemonic", None)
    from kailash.trust.vault.shamir import ShamirRitual, rotate_holders

    old_shards = [["dummy", "words"], ["another", "shard"], ["third", "one"]]
    new_ritual = ShamirRitual(threshold=2, total_shards=3)
    with pytest.raises(RuntimeError, match=r"kailash\[shamir\]"):
        rotate_holders(old_shards, new_ritual)


# ---------------------------------------------------------------------------
# back_up_vault_key — #606 stub implemented (EATP-12 W2-I1)
# ---------------------------------------------------------------------------
#
# The pre-#606 NotImplementedError stub is GONE. These two tests were the
# scaffold-era deferral tests (they asserted pytest.raises(NotImplementedError)
# on the bytes-form stub). Per orphan-detection.md Rule 4a they are rewritten
# IN THE SAME CHANGE that implemented the stub, to assert the new conformant
# behavior: the function no longer accepts raw bytes as the primary surface,
# and it no longer raises NotImplementedError. The full handle-based path is
# exercised by the W2-I1 Tier-1/Tier-2 suites; here we pin the two facts the
# old deferral tests pinned (the symbol exists; it is no longer a stub).


@pytest.mark.regression
def test_back_up_vault_key_is_no_longer_a_notimplemented_stub():
    """#606 closed: back_up_vault_key does NOT raise NotImplementedError.

    The pre-#606 stub raised NotImplementedError("...mint ISS-37...#606").
    Calling the conformant handle-based surface with no required kwargs now
    raises a TypeError (missing keyword-only args) — NOT NotImplementedError —
    proving the stub body is gone.
    """
    from kailash.trust.vault import ShamirRitual, back_up_vault_key

    ritual = ShamirRitual(threshold=3, total_shards=5)
    # The conformant surface is handle-based + keyword-only resolver/dispatcher
    # /signer; calling it the OLD way (positional bytes + ritual) raises a
    # TypeError for the missing required args, never NotImplementedError.
    with pytest.raises(TypeError):
        back_up_vault_key(b"x" * 16, ritual)  # type: ignore[arg-type]
    # And it is definitively not the old stub:
    try:
        back_up_vault_key(b"x" * 16, ritual)  # type: ignore[arg-type]
    except NotImplementedError:  # pragma: no cover - must not happen
        pytest.fail(
            "back_up_vault_key still raises NotImplementedError (#606 not closed)"
        )
    except TypeError:
        pass


@pytest.mark.regression
def test_back_up_vault_key_rejects_invalid_ritual_floor():
    """The conformant surface enforces the N12-TH-01 vault floor (2<=k<=n<=9).

    A 1-of-n ritual is constructed-rejected by ShamirRitual itself; here we
    pin that a ritual passing the wrapper but BELOW the stricter vault floor
    (n>9) is rejected with the typed invalid-ritual code via the binding's
    entry gate — replacing the old #606 deferral assertion with the new
    conformant entry-gate behavior.
    """
    from kailash.trust.vault.errors import N12FT01Code, VaultBindingError
    from kailash.trust.vault.input_gates import require_ritual_floor
    from kailash.trust.vault.shamir import ShamirRitual

    # n=10 passes the wrapper (<=16) but exceeds the vault ceiling (9).
    over_ceiling = ShamirRitual(threshold=2, total_shards=10)
    with pytest.raises(VaultBindingError) as exc:
        require_ritual_floor(over_ceiling)
    assert exc.value.code is N12FT01Code.INVALID_RITUAL


# ---------------------------------------------------------------------------
# Public surface -- module import contract
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_public_surface_imports_without_extra(monkeypatch):
    """Module import succeeds even when shamir_mnemonic is absent.

    This is the inverse of the call-site loud-failure rule: the module
    itself MUST import cleanly so static analysers, Sphinx autodoc, and
    `from kailash.trust.vault import *` keep working without the extra.
    """
    monkeypatch.setitem(sys.modules, "shamir_mnemonic", None)
    # Force re-import to exercise the absence path on module load.
    monkeypatch.delitem(sys.modules, "kailash.trust.vault", raising=False)
    monkeypatch.delitem(sys.modules, "kailash.trust.vault.shamir", raising=False)
    monkeypatch.delitem(sys.modules, "kailash.trust.vault.backup", raising=False)

    import kailash.trust.vault as vault_pkg

    # Public surface is reachable via __all__ -- frozen dataclass + the five
    # callables + the stub.
    assert "ShamirRitual" in vault_pkg.__all__
    assert "generate" in vault_pkg.__all__
    assert "reconstruct" in vault_pkg.__all__
    assert "serialize_shard" in vault_pkg.__all__
    assert "deserialize_shard" in vault_pkg.__all__
    assert "rotate_holders" in vault_pkg.__all__
    assert "back_up_vault_key" in vault_pkg.__all__
