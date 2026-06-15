# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""D2c signed-marker gate — EATP-08 §4.3.1 / §4.3.2 (issue #1316, Shard 1).

The pre-1.1 ``D2dWitness`` was a TRUSTED passed-in value: the gate never
verified a signature, so any caller asserting a pre-adoption witness downgraded
a pre-registry form to ``eatp-v1`` forever. EATP-08 §4.3 requires the marker to
be **signed-not-remembered**: the verifier holds a configured trusted key
(:class:`D2dVerifierKeys`) and verifies ``marker_sig`` over the §4.3.1 signed
core ``{principal, first_seen}`` INSIDE the gate.

This file pins the §4.3.2 detection rule — the five fail-closed checks of
:func:`assert_d2d_witness_pre_adoption` — both directly (the gate function) and
through the centralised production decode path (:func:`decode_wire_alg_id`,
which every signed-record ``from_dict`` consumer calls). All checks map to
``implicit-v1-witness-failure``.

Tests are behavioral (call the function; assert raise/return) per
rules/testing.md, against REAL Ed25519 crypto (PyNaCl) — no mocking.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

import pytest

from kailash.trust.signing import algorithm_id as _alg_id_mod
from kailash.trust.signing.algorithm_id import (
    ADOPTION_DATE_PARSED,
    ALGORITHM_DEFAULT,
    D2dVerifierKeys,
    D2dWitness,
    UnsupportedAlgorithmError,
    assert_d2d_witness_pre_adoption,
    d2d_legacy_acceptance_count,
    decode_wire_alg_id,
)
from kailash.trust.signing.crypto import generate_keypair, sign

UTC = timezone.utc

# A trusted verifier keypair fixed for the module so the signed-marker accept
# path is deterministic.
_PRIVATE_KEY, _PUBLIC_KEY = generate_keypair()
_OTHER_PRIVATE_KEY, _ = generate_keypair()  # an UNtrusted key (private half only)
_WITNESS_ID = "eatp08-1316-witness"

_PRINCIPAL = "chain:eatp08-1316"
_PRE_ADOPTION = datetime(2026, 1, 1, tzinfo=UTC)  # strictly before 2026-04-26
_ON_ADOPTION = datetime(
    ADOPTION_DATE_PARSED.year,
    ADOPTION_DATE_PARSED.month,
    ADOPTION_DATE_PARSED.day,
    tzinfo=UTC,
)


def _keys() -> D2dVerifierKeys:
    return D2dVerifierKeys(keys={_WITNESS_ID: _PUBLIC_KEY})


def _sign(
    principal: str | None, first_seen: datetime | None, key: str = _PRIVATE_KEY
) -> str:
    first_seen_repr = (
        first_seen.isoformat() if isinstance(first_seen, datetime) else first_seen
    )
    return sign({"principal": principal, "first_seen": first_seen_repr}, key)


def _valid_witness(**overrides) -> D2dWitness:
    """A complete, signed, pre-adoption marker that passes ALL five checks."""
    base: dict[str, Any] = dict(
        witnessed_at=_PRE_ADOPTION,
        chain_head_date=_PRE_ADOPTION,
        principal=_PRINCIPAL,
        first_seen=_PRE_ADOPTION,
        marker_sig=_sign(_PRINCIPAL, _PRE_ADOPTION),
        witness_id=_WITNESS_ID,
    )
    base.update(overrides)
    return D2dWitness(**base)


# The nested pre-registry form — the production D2d shape decode_wire_alg_id
# routes through the witness gate.
_NESTED_FORM = {"alg_id": {"algorithm": "ed25519+sha256"}}


# ---------------------------------------------------------------------------
# Accept path (all five checks hold) — direct gate AND through decode_wire_alg_id
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_valid_signed_marker_passes_gate_directly():
    # Returns silently when all five checks hold.
    assert_d2d_witness_pre_adoption(_valid_witness(), verifier_keys=_keys()) is None


@pytest.mark.regression
def test_valid_signed_marker_accepts_through_decode_wire():
    # Wiring: the production decode chokepoint accepts the nested pre-registry
    # form as eatp-v1 ONLY with a verified signed marker.
    got = decode_wire_alg_id(
        _NESTED_FORM, witness=_valid_witness(), verifier_keys=_keys()
    )
    assert got == ALGORITHM_DEFAULT == "eatp-v1"


# ---------------------------------------------------------------------------
# Check 1 — missing witness
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_check1_missing_witness_rejected():
    with pytest.raises(UnsupportedAlgorithmError) as exc:
        assert_d2d_witness_pre_adoption(None, verifier_keys=_keys())
    assert exc.value.code == "implicit-v1-witness-failure"


# ---------------------------------------------------------------------------
# Check 2 — signed-not-remembered (signature verification)
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_check2_unsigned_marker_rejected():
    # The pre-1.1 trusted-passed-in witness (no marker_sig) no longer rescues.
    with pytest.raises(UnsupportedAlgorithmError) as exc:
        assert_d2d_witness_pre_adoption(
            _valid_witness(marker_sig=None), verifier_keys=_keys()
        )
    assert exc.value.code == "implicit-v1-witness-failure"


@pytest.mark.regression
def test_check2_missing_principal_rejected():
    with pytest.raises(UnsupportedAlgorithmError) as exc:
        assert_d2d_witness_pre_adoption(
            _valid_witness(principal=None), verifier_keys=_keys()
        )
    assert exc.value.code == "implicit-v1-witness-failure"


@pytest.mark.regression
def test_check2_no_verifier_keys_configured_rejected():
    # A signed marker with NO trusted-key config fails closed.
    with pytest.raises(UnsupportedAlgorithmError) as exc:
        assert_d2d_witness_pre_adoption(_valid_witness(), verifier_keys=None)
    assert exc.value.code == "implicit-v1-witness-failure"


@pytest.mark.regression
def test_check2_unknown_witness_id_rejected():
    # witness_id resolves to no key, and no default_key is set.
    with pytest.raises(UnsupportedAlgorithmError) as exc:
        assert_d2d_witness_pre_adoption(
            _valid_witness(witness_id="not-in-config"), verifier_keys=_keys()
        )
    assert exc.value.code == "implicit-v1-witness-failure"


@pytest.mark.regression
def test_check2_signature_by_untrusted_key_rejected():
    # The marker is signed by a different key than the configured trusted one.
    forged = _valid_witness(
        marker_sig=_sign(_PRINCIPAL, _PRE_ADOPTION, key=_OTHER_PRIVATE_KEY)
    )
    with pytest.raises(UnsupportedAlgorithmError) as exc:
        assert_d2d_witness_pre_adoption(forged, verifier_keys=_keys())
    assert exc.value.code == "implicit-v1-witness-failure"


@pytest.mark.regression
def test_check2_tampered_principal_breaks_signature():
    # marker_sig binds {principal, first_seen}; mutating principal after signing
    # breaks verification (the signed core no longer matches).
    tampered = _valid_witness(principal="chain:attacker")
    with pytest.raises(UnsupportedAlgorithmError) as exc:
        assert_d2d_witness_pre_adoption(tampered, verifier_keys=_keys())
    assert exc.value.code == "implicit-v1-witness-failure"


@pytest.mark.regression
def test_check2_default_key_resolves_when_witness_id_unset():
    # A marker with no witness_id verifies against the config default_key.
    w = _valid_witness(witness_id=None)
    keys = D2dVerifierKeys(keys={}, default_key=_PUBLIC_KEY)
    assert assert_d2d_witness_pre_adoption(w, verifier_keys=keys) is None


# ---------------------------------------------------------------------------
# Check 3 — first_seen corroboration (defeats backdated chain_head_date)
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_check3_missing_first_seen_rejected():
    # No signed first_seen => uncorroborated. (Sign over first_seen=None so the
    # signature itself verifies; check 3 then rejects on the missing field.)
    w = _valid_witness(first_seen=None, marker_sig=_sign(_PRINCIPAL, None))
    with pytest.raises(UnsupportedAlgorithmError) as exc:
        assert_d2d_witness_pre_adoption(w, verifier_keys=_keys())
    assert exc.value.code == "implicit-v1-witness-failure"


@pytest.mark.regression
def test_check3_fresh_record_backdated_head_rejected():
    # The V6(iii) attack: a FRESH record (post-adoption first_seen, signed by
    # the real witness) backdates its claimed chain_head_date to pre-adoption.
    # The SIGNED first_seen is post-adoption, so corroboration fails — the
    # attacker cannot obtain a pre-adoption signed first_seen for a fresh chain.
    post_adoption_first_seen = _ON_ADOPTION
    w = D2dWitness(
        witnessed_at=_PRE_ADOPTION,
        chain_head_date=_PRE_ADOPTION,  # attacker's backdated CLAIM
        principal=_PRINCIPAL,
        first_seen=post_adoption_first_seen,  # the SIGNED truth: post-adoption
        marker_sig=_sign(_PRINCIPAL, post_adoption_first_seen),
        witness_id=_WITNESS_ID,
    )
    with pytest.raises(UnsupportedAlgorithmError) as exc:
        assert_d2d_witness_pre_adoption(w, verifier_keys=_keys())
    assert exc.value.code == "implicit-v1-witness-failure"


# ---------------------------------------------------------------------------
# Check 4 — expiry
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_check4_expired_marker_rejected():
    now = datetime(2026, 2, 1, tzinfo=UTC)
    expired = _valid_witness(expires_at=datetime(2026, 1, 15, tzinfo=UTC))
    with pytest.raises(UnsupportedAlgorithmError) as exc:
        assert_d2d_witness_pre_adoption(expired, verifier_keys=_keys(), now=now)
    assert exc.value.code == "implicit-v1-witness-failure"


@pytest.mark.regression
def test_check4_unexpired_marker_accepted():
    now = datetime(2026, 2, 1, tzinfo=UTC)
    fresh = _valid_witness(expires_at=datetime(2026, 3, 1, tzinfo=UTC))
    assert (
        assert_d2d_witness_pre_adoption(fresh, verifier_keys=_keys(), now=now) is None
    )


# ---------------------------------------------------------------------------
# Check 5 — temporal monotonic boundary (claimed dates strictly < adoption)
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_check5_chain_head_on_adoption_rejected():
    # Signature + first_seen corroboration pass, but the claimed chain_head_date
    # is ON the adoption date (not strictly before) => temporal-boundary reject.
    w = _valid_witness(chain_head_date=_ON_ADOPTION)
    with pytest.raises(UnsupportedAlgorithmError) as exc:
        assert_d2d_witness_pre_adoption(w, verifier_keys=_keys())
    assert exc.value.code == "implicit-v1-witness-failure"


@pytest.mark.regression
def test_check5_witnessed_at_on_adoption_rejected():
    w = _valid_witness(witnessed_at=_ON_ADOPTION)
    with pytest.raises(UnsupportedAlgorithmError) as exc:
        assert_d2d_witness_pre_adoption(w, verifier_keys=_keys())
    assert exc.value.code == "implicit-v1-witness-failure"


# ---------------------------------------------------------------------------
# Wiring: an unsigned witness through the production decode path is rejected
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_unsigned_witness_through_decode_wire_rejected():
    # The pre-1.1 acceptance path (trusted unsigned witness) is closed end-to-end.
    legacy_unsigned = D2dWitness(
        witnessed_at=_PRE_ADOPTION, chain_head_date=_PRE_ADOPTION
    )
    with pytest.raises(UnsupportedAlgorithmError) as exc:
        decode_wire_alg_id(_NESTED_FORM, witness=legacy_unsigned, verifier_keys=_keys())
    assert exc.value.code == "implicit-v1-witness-failure"


@pytest.mark.regression
def test_signed_witness_no_verifier_keys_through_decode_wire_rejected():
    # Forwarding a signed witness but no verifier_keys (the default consumer
    # call) fails closed — the marker cannot be verified.
    with pytest.raises(UnsupportedAlgorithmError) as exc:
        decode_wire_alg_id(_NESTED_FORM, witness=_valid_witness(), verifier_keys=None)
    assert exc.value.code == "implicit-v1-witness-failure"


# ---------------------------------------------------------------------------
# Shard 4 — Compatible-Legacy logging (EATP-08 §7.1)
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_s4_legacy_acceptance_increments_migration_counter():
    _alg_id_mod._reset_d2d_legacy_acceptance_count()
    assert d2d_legacy_acceptance_count() == 0
    decode_wire_alg_id(_NESTED_FORM, witness=_valid_witness(), verifier_keys=_keys())
    assert d2d_legacy_acceptance_count() == 1
    # The unsigned-`algorithm`-metadata form also counts.
    decode_wire_alg_id(
        {"algorithm": "ed25519+sha256"}, witness=_valid_witness(), verifier_keys=_keys()
    )
    assert d2d_legacy_acceptance_count() == 2


@pytest.mark.regression
def test_s4_legacy_acceptance_logs_at_warn(caplog):
    # §7.1 / observability.md Rule 3: a Compatible-Legacy acceptance is a
    # degraded path and MUST surface at WARN, not INFO.
    with caplog.at_level(logging.WARNING, logger=_alg_id_mod.logger.name):
        decode_wire_alg_id(
            _NESTED_FORM, witness=_valid_witness(), verifier_keys=_keys()
        )
    warns = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("Compatible-Legacy acceptance" in r.getMessage() for r in warns)


@pytest.mark.regression
def test_s4_principal_hashed_not_raw_at_warn(caplog):
    # observability.md Rule 8: the principal (a subject/chain id) MUST appear at
    # WARN only as an 8-char hash, never raw.
    with caplog.at_level(logging.WARNING, logger=_alg_id_mod.logger.name):
        decode_wire_alg_id(
            _NESTED_FORM, witness=_valid_witness(), verifier_keys=_keys()
        )
    warn_text = "\n".join(
        r.getMessage() for r in caplog.records if r.levelno == logging.WARNING
    )
    expected_hash = hashlib.sha256(_PRINCIPAL.encode("utf-8")).hexdigest()[:8]
    assert expected_hash in warn_text  # hashed correlation present
    assert _PRINCIPAL not in warn_text  # raw subject id NOT leaked at WARN


@pytest.mark.regression
def test_s4_principal_full_only_at_debug(caplog):
    with caplog.at_level(logging.DEBUG, logger=_alg_id_mod.logger.name):
        decode_wire_alg_id(
            _NESTED_FORM, witness=_valid_witness(), verifier_keys=_keys()
        )
    debug_text = "\n".join(
        r.getMessage() for r in caplog.records if r.levelno == logging.DEBUG
    )
    assert _PRINCIPAL in debug_text  # full principal available at DEBUG only
