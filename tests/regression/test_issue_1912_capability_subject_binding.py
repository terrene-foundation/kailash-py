# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression: #1912 capability subject-binding (transplant defense).

Before #1912, ``CapabilityAttestation.to_signing_payload()`` bound the ATTESTER
but NO subject ``agent_id``, and ``_verify_capability_signature`` verified the
signature with NO check that the cap was attested FOR the verifying chain's
holder. A genuine capability copied from chain A into chain B verified fine —
the cross-chain transplant vulnerability.

Wave 1 makes NEW caps ``v1-subject-bound``: the signature covers the holder
chain's ``genesis.agent_id``, and verify dispatches on the persisted version.

Scenarios (task step 9), all against REAL Ed25519, NO mocking:

  (a) a v1 cap signed for chain A, copied into chain B, fails verify against B;
  (b) a v1 cap in its OWN chain verifies TRUE (no false positive);
  (c) a v1 cap whose ``signing_payload_version`` is stripped fails verify
      (downgrade resistance — it defaults to legacy and the legacy re-verify,
      recomputed WITHOUT the subject, no longer matches the v1 signature);
  (d) #1912 Wave 3 A1 enforcement: a legacy (un-subject-bound) cap is REJECTED
      by default (fail-closed — legacy caps are transplantable), and ACCEPTED
      only under the migration-window opt-out
      ``allow_unbound_legacy_capabilities=True``.

Plus an end-to-end proof that ``establish`` → store → ``verify`` at STANDARD
authorizes a v1 cap on its own chain (the happy path is not broken).
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from typing import Dict, List, Optional

import pytest

from kailash.trust.authority import AuthorityPermission, OrganizationalAuthority
from kailash.trust.chain import (
    CAPABILITY_SIGNING_VERSION_LEGACY,
    CAPABILITY_SIGNING_VERSION_V1,
    AuthorityType,
    CapabilityAttestation,
    CapabilityType,
    GenesisRecord,
    TrustLineageChain,
    VerificationLevel,
)
from kailash.trust.chain_store.memory import InMemoryTrustStore
from kailash.trust.exceptions import AuthorityInactiveError, AuthorityNotFoundError
from kailash.trust.operations import (
    CapabilityRequest,
    TrustKeyManager,
    TrustOperations,
)
from kailash.trust.signing.crypto import generate_keypair

pytestmark = pytest.mark.regression

FIXED_TS = datetime(2026, 3, 11, 14, 30, 0, tzinfo=timezone.utc)


class SimpleAuthorityRegistry:
    """Real in-memory authority registry (NOT a mock)."""

    def __init__(self) -> None:
        self._authorities: Dict[str, OrganizationalAuthority] = {}

    async def initialize(self) -> None:
        pass

    def register(self, authority: OrganizationalAuthority) -> None:
        self._authorities[authority.id] = authority

    async def get_authority(
        self, authority_id: str, include_inactive: bool = False
    ) -> OrganizationalAuthority:
        authority = self._authorities.get(authority_id)
        if authority is None:
            raise AuthorityNotFoundError(authority_id)
        if not authority.is_active and not include_inactive:
            raise AuthorityInactiveError(authority_id)
        return authority

    async def update_authority(self, authority: OrganizationalAuthority) -> None:
        self._authorities[authority.id] = authority


@pytest.fixture
def keypair():
    return generate_keypair()


@pytest.fixture
def authority(keypair):
    _, public_key = keypair
    return OrganizationalAuthority(
        id="org-test",
        name="Test Corp",
        authority_type=AuthorityType.ORGANIZATION,
        public_key=public_key,
        signing_key_id="test-key-001",
        permissions=[
            AuthorityPermission.CREATE_AGENTS,
            AuthorityPermission.DELEGATE_TRUST,
            AuthorityPermission.GRANT_CAPABILITIES,
        ],
    )


@pytest.fixture
def registry(authority):
    reg = SimpleAuthorityRegistry()
    reg.register(authority)
    return reg


@pytest.fixture
def key_manager(keypair):
    private_key, _ = keypair
    km = TrustKeyManager()
    km.register_key("test-key-001", private_key)
    return km


@pytest.fixture
async def memory_store():
    store = InMemoryTrustStore()
    await store.initialize()
    return store


@pytest.fixture
async def ops(registry, key_manager, memory_store):
    operations = TrustOperations(
        authority_registry=registry,
        key_manager=key_manager,
        trust_store=memory_store,
    )
    await operations.initialize()
    return operations


async def _establish(ops: TrustOperations, agent_id: str, caps: List[str]):
    await ops.establish(
        agent_id=agent_id,
        authority_id="org-test",
        capabilities=[
            CapabilityRequest(capability=c, capability_type=CapabilityType.ACTION)
            for c in caps
        ],
    )
    return await ops.trust_store.get_chain(agent_id)


# ---------------------------------------------------------------------------
# Sign-time posture: establish now produces v1-subject-bound caps
# ---------------------------------------------------------------------------


async def test_establish_produces_v1_subject_bound_caps(ops):
    chain = await _establish(ops, "agent-a", ["read_data"])
    assert chain.capabilities, "establish produced no capabilities"
    for cap in chain.capabilities:
        assert cap.signing_payload_version == CAPABILITY_SIGNING_VERSION_V1, (
            "establish must produce v1-subject-bound caps (#1912), got "
            f"{cap.signing_payload_version!r}"
        )


# ---------------------------------------------------------------------------
# (a) TRANSPLANT: a v1 cap from chain A fails verify against chain B
# ---------------------------------------------------------------------------


async def test_v1_capability_transplant_into_other_chain_fails(ops):
    chain_a = await _establish(ops, "agent-a", ["read_data"])
    chain_b = await _establish(ops, "agent-b", ["write_data"])
    cap_from_a = chain_a.capabilities[0]

    # Sanity: the genuine cap verifies in its OWN chain (b) below.
    ok_own = await ops._verify_capability_signature(chain_a, cap_from_a)
    assert ok_own is True, "fixture bug: genuine cap must verify in its own chain"

    # Transplant: the SAME genuine, validly-signed cap verified against chain B
    # (a DIFFERENT holder) recomputes a different subject → signature fails.
    transplanted = await ops._verify_capability_signature(chain_b, cap_from_a)
    assert transplanted is False, (
        "a genuine v1 cap transplanted from chain A into chain B verified — the "
        "#1912 cross-chain transplant is NOT closed"
    )


# ---------------------------------------------------------------------------
# (b) NO FALSE POSITIVE: a v1 cap verifies in its own chain
# ---------------------------------------------------------------------------


async def test_v1_capability_verifies_in_own_chain(ops):
    chain_a = await _establish(ops, "agent-a", ["read_data"])
    cap = chain_a.capabilities[0]
    assert await ops._verify_capability_signature(chain_a, cap) is True


# ---------------------------------------------------------------------------
# (c) DOWNGRADE RESISTANCE: stripping the version fails verify
# ---------------------------------------------------------------------------


async def test_v1_capability_with_version_stripped_fails(ops):
    chain_a = await _establish(ops, "agent-a", ["read_data"])
    cap = chain_a.capabilities[0]
    # Simulate a store-writer stripping the version discriminator (a
    # from_dict-of-a-tampered-record defaults to legacy). The v1 signature was
    # made over the subject-bound pre-image; the legacy re-verify (no subject)
    # no longer matches.
    downgraded = dataclasses.replace(
        cap, signing_payload_version=CAPABILITY_SIGNING_VERSION_LEGACY
    )
    assert await ops._verify_capability_signature(chain_a, downgraded) is False, (
        "a v1 cap whose signing_payload_version was stripped to legacy still "
        "verified — downgrade resistance is broken"
    )


# ---------------------------------------------------------------------------
# (d) #1912 Wave 3 A1: a legacy cap is REJECTED by default, ACCEPTED under opt-out
# ---------------------------------------------------------------------------


def _build_legacy_cap_chain(key_manager_signature: str = "") -> TrustLineageChain:
    """A LEGACY cap (pre-#1912, no subject in the pre-image) in its own chain."""
    legacy_cap = CapabilityAttestation(
        id="cap-legacy",
        capability="read_data",
        capability_type=CapabilityType.ACTION,
        constraints=["read_only"],
        attester_id="org-test",
        attested_at=FIXED_TS,
        signature=key_manager_signature,
        signing_payload_version=CAPABILITY_SIGNING_VERSION_LEGACY,
    )
    genesis = GenesisRecord(
        id="gen-legacy",
        agent_id="agent-legacy",
        authority_id="org-test",
        authority_type=AuthorityType.ORGANIZATION,
        created_at=FIXED_TS,
        signature="gs",
    )
    return TrustLineageChain(genesis=genesis, capabilities=[legacy_cap])


async def test_legacy_capability_rejected_by_default(ops, key_manager, caplog):
    """#1912 Wave 3 A1: a legacy (un-subject-bound) cap is fail-closed REJECTED.

    A legacy cap verifies IDENTICALLY on any chain (no holder subject in the
    pre-image) — the transplant HIGH. With the default fail-closed posture
    (allow_unbound_legacy_capabilities=False) it is REJECTED even though its
    signature is cryptographically valid over the legacy pre-image.
    """
    import logging

    from kailash.trust.signing.crypto import serialize_for_signing

    chain = _build_legacy_cap_chain()
    legacy_cap = chain.capabilities[0]
    payload = serialize_for_signing(legacy_cap.to_signing_payload())
    legacy_cap.signature = await key_manager.sign(payload, "test-key-001")

    with caplog.at_level(logging.WARNING, logger="kailash.trust.operations"):
        result = await ops._verify_capability_signature(chain, legacy_cap)
    assert result is False, (
        "a legacy (un-subject-bound) cap must be REJECTED by default — #1912 "
        "Wave 3 A1 fail-closed enforcement (legacy caps are transplantable)"
    )
    assert any(
        "REJECTING legacy" in r.message for r in caplog.records
    ), "the fail-closed reject must emit the loud A1 WARN naming the migration path"


async def test_legacy_capability_accepted_with_opt_out(
    registry, key_manager, memory_store, caplog
):
    """The migration-window opt-out accepts a legacy cap over its legacy pre-image.

    allow_unbound_legacy_capabilities=True restores the pre-Wave-3 behavior
    (accept a legacy cap whose signature is valid over the no-subject pre-image)
    so a deployment can keep running WHILE its chains are re-signed by the #1912
    migration — with a loud one-time WARN that the transplant defense is OFF.
    """
    import logging

    from kailash.trust.signing.crypto import serialize_for_signing

    ops_optout = TrustOperations(
        authority_registry=registry,
        key_manager=key_manager,
        trust_store=memory_store,
        allow_unbound_legacy_capabilities=True,
    )
    await ops_optout.initialize()

    chain = _build_legacy_cap_chain()
    legacy_cap = chain.capabilities[0]
    payload = serialize_for_signing(legacy_cap.to_signing_payload())
    legacy_cap.signature = await key_manager.sign(payload, "test-key-001")

    with caplog.at_level(logging.WARNING, logger="kailash.trust.operations"):
        result = await ops_optout._verify_capability_signature(chain, legacy_cap)
    assert result is True, (
        "with allow_unbound_legacy_capabilities=True a legacy cap valid over its "
        "legacy pre-image must be ACCEPTED (migration window)"
    )
    assert any(
        "allow_unbound_legacy_capabilities=True" in r.message for r in caplog.records
    ), "the opt-out accept must emit the loud one-time WARN that the defense is OFF"


# ---------------------------------------------------------------------------
# Empty-subject invariant (#1912 RT-sec LOW): a v1 pre-image MUST bind a
# non-empty holder. Sign time raises loudly (caller bug); verify fail-closes
# (never crashes) on an anomalous chain whose genesis.agent_id is empty.
# ---------------------------------------------------------------------------


def test_v1_pre_image_rejects_empty_subject_at_sign_time():
    cap = CapabilityAttestation(
        id="cap-x",
        capability="read_data",
        capability_type=CapabilityType.ACTION,
        constraints=[],
        attester_id="org-test",
        attested_at=FIXED_TS,
        signature="",
        signing_payload_version=CAPABILITY_SIGNING_VERSION_V1,
    )
    for bad in ("", None):
        with pytest.raises(ValueError, match="non-empty subject_agent_id"):
            cap.to_signing_payload(subject_agent_id=bad)
    # A legacy cap ignores the subject entirely — no raise (byte-neutral).
    legacy = dataclasses.replace(
        cap, signing_payload_version=CAPABILITY_SIGNING_VERSION_LEGACY
    )
    assert "subject_agent_id" not in legacy.to_signing_payload(subject_agent_id="")


async def test_verify_fail_closes_on_empty_subject_v1_cap(ops):
    # A genuine v1 cap signed for a real holder...
    chain_a = await _establish(ops, "agent-a", ["read_data"])
    cap = chain_a.capabilities[0]

    # ...verified against an anomalous chain whose genesis.agent_id is empty
    # (a tampered/corrupt state). Verify must DENY (return False), never raise
    # the ValueError the empty-subject guard emits.
    empty_genesis = GenesisRecord(
        id="gen-empty",
        agent_id="",
        authority_id="org-test",
        authority_type=AuthorityType.ORGANIZATION,
        created_at=FIXED_TS,
        signature="gs",
    )
    empty_chain = TrustLineageChain(genesis=empty_genesis, capabilities=[cap])
    assert await ops._verify_capability_signature(empty_chain, cap) is False, (
        "verify must fail-closed (deny) on a v1 cap whose chain has an empty "
        "genesis.agent_id — not raise, not authorize"
    )


async def test_public_verify_fail_closes_on_empty_subject_chain_all_levels(
    ops, key_manager
):
    """The empty-subject guard MUST fail-closed at EVERY verify-path pre-image
    site, not just _verify_capability_signature. Drives the PUBLIC verify() API
    at STANDARD and FULL over an anomalous empty-genesis chain: STANDARD hits the
    matched-cap gate, FULL hits _derive_enforced_envelope's dedup key (ops:693)
    AND _verify_signatures (ops:1584). Before the sibling-site fix, FULL RAISED
    an uncaught ValueError on the primary security API (#1912 RT-corr round-2 BUG).
    """
    from kailash.trust.signing.crypto import serialize_for_signing

    # A genuine v1 cap signed for a real holder.
    src_chain = await _establish(ops, "agent-src", ["read_data"])
    v1_cap = src_chain.capabilities[0]

    # An anomalous chain: a VALIDLY-SIGNED genesis whose agent_id is empty,
    # holding the v1 cap. verify() loads it by agent_id and recomputes the
    # cap pre-image with subject="" → the guard raises → must fail closed.
    empty_genesis = GenesisRecord(
        id="gen-empty",
        agent_id="",
        authority_id="org-test",
        authority_type=AuthorityType.ORGANIZATION,
        created_at=FIXED_TS,
        signature="",
    )
    empty_genesis.signature = await key_manager.sign(
        serialize_for_signing(empty_genesis.to_signing_payload()), "test-key-001"
    )
    anomalous = TrustLineageChain(genesis=empty_genesis, capabilities=[v1_cap])
    await ops.trust_store.store_chain(anomalous)

    for level in (VerificationLevel.STANDARD, VerificationLevel.FULL):
        result = await ops.verify(agent_id="", action="read_data", level=level)
        assert result.valid is False, (
            f"public verify(level={level}) on an empty-subject v1-cap chain must "
            f"fail-closed (valid=False), not crash and not authorize; got "
            f"valid={result.valid} reason={result.reason!r}"
        )


# ---------------------------------------------------------------------------
# End-to-end: establish -> store -> verify authorizes a v1 cap (happy path)
# ---------------------------------------------------------------------------


async def test_establish_then_verify_authorizes_v1_cap_end_to_end(ops):
    await _establish(ops, "agent-a", ["read_data"])
    result = await ops.verify(
        agent_id="agent-a",
        action="read_data",
        level=VerificationLevel.STANDARD,
    )
    assert result.valid is True, (
        f"establish -> verify(STANDARD) denied a legitimately-established v1 cap: "
        f"{result.reason}"
    )


# ---------------------------------------------------------------------------
# Key rotation (#1912 RT-corr round-3 INVEST-NOW): the re-sign path
# (CredentialRotationManager) is a subject-binding SIGN site — the same class as
# the CLI-mint HIGH. It re-signs a v1 cap over the version-gated pre-image with
# the holder subject bound; WITHOUT the subject_agent_id= arg, a rotated v1 cap
# would be signed over the no-subject pre-image and FAIL verify after every
# rotation. This test is the regression guard for that sign site (previously
# uncovered by any behavioral test AND excluded from the structural parity
# sweep — a future arg-drop would otherwise break v1 verify silently).
# ---------------------------------------------------------------------------


async def test_v1_cap_survives_key_rotation_and_stays_transplant_resistant(
    ops, registry, key_manager, memory_store
):
    from kailash.trust.signing.rotation import CredentialRotationManager

    chain_a = await _establish(ops, "agent-a", ["read_data"])
    chain_b = await _establish(ops, "agent-b", ["write_data"])
    original_sig = chain_a.capabilities[0].signature
    assert (
        chain_a.capabilities[0].signing_payload_version == CAPABILITY_SIGNING_VERSION_V1
    )

    # Rotate the authority's signing key → re-signs every chain it attested,
    # binding each v1 cap to its holder's genesis.agent_id under the NEW key.
    mgr = CredentialRotationManager(
        key_manager=key_manager,
        trust_store=memory_store,
        authority_registry=registry,
    )
    await mgr.initialize()
    await mgr.rotate_key("org-test")

    rotated_a = await memory_store.get_chain("agent-a")
    rotated_cap = rotated_a.capabilities[0]

    # Re-signed (new key) and version PRESERVED (rotation never strips binding).
    assert rotated_cap.signature != original_sig, "rotation did not re-sign the cap"
    assert rotated_cap.signing_payload_version == CAPABILITY_SIGNING_VERSION_V1

    # The load-bearing assertion: the re-signed v1 cap verifies TRUE in its own
    # chain against the rotated authority key. This FAILS if the rotation re-sign
    # site drops subject_agent_id= (signs no-subject bytes; verify recomputes WITH
    # the subject → mismatch) — the silent-regression the guard exists to catch.
    assert await ops._verify_capability_signature(rotated_a, rotated_cap) is True, (
        "a v1 cap re-signed by key rotation failed verify in its own chain — the "
        "rotation re-sign site is not binding the holder subject (#1912)"
    )

    # And still transplant-resistant after rotation: into agent-b's chain → FALSE.
    assert await ops._verify_capability_signature(chain_b, rotated_cap) is False, (
        "a rotated v1 cap transplanted into another chain verified — rotation "
        "weakened the #1912 subject binding"
    )


# ---------------------------------------------------------------------------
# CLI surface (#1912 RT-sec/RT-corr HIGH): the `eatp` CLI establish + delegate
# commands must ALSO mint v1-subject-bound caps. Before this fix the CLI sign
# sites (cli/commands.py:453/:666) minted LEGACY caps, so every cap created via
# the CLI stayed cross-chain transplantable — the #1912 vuln open on a real,
# supported new-cap surface. These drive the ACTUAL click commands end-to-end.
# ---------------------------------------------------------------------------


def _cli_init_authority(runner, store_dir: str) -> str:
    import json as _json
    from pathlib import Path as _Path

    from kailash.trust.cli import main

    r = runner.invoke(main, ["--store-dir", store_dir, "init", "--name", "cli-auth"])
    assert r.exit_code == 0, f"init failed: {r.output}"
    auth_files = list((_Path(store_dir) / "authorities").glob("*.json"))
    return _json.loads(auth_files[0].read_text())["id"]


def test_cli_establish_mints_v1_and_is_transplant_resistant(tmp_path):
    from click.testing import CliRunner

    from kailash.trust.cli import main
    from kailash.trust.cli.commands import _create_store, _load_authority, _run_async

    runner = CliRunner()
    store_dir = str(tmp_path / ".eatp")
    (tmp_path / ".eatp").mkdir()
    authority_id = _cli_init_authority(runner, store_dir)

    for agent in ("agent-a", "agent-b"):
        r = runner.invoke(
            main,
            [
                "--store-dir",
                store_dir,
                "establish",
                agent,
                "--authority",
                authority_id,
                "--capabilities",
                "read_data",
            ],
        )
        assert r.exit_code == 0, f"establish {agent} failed: {r.output}"

    store = _create_store(store_dir)
    _run_async(store.initialize())
    chain_a = _run_async(store.get_chain("agent-a"))
    chain_b = _run_async(store.get_chain("agent-b"))

    # 1. CLI-created caps are v1-subject-bound (not legacy).
    assert chain_a.capabilities, "CLI establish produced no capabilities"
    for cap in chain_a.capabilities:
        assert cap.signing_payload_version == CAPABILITY_SIGNING_VERSION_V1, (
            "CLI `establish` must mint v1-subject-bound caps (#1912); got "
            f"{cap.signing_payload_version!r} — the CLI sign site is unmigrated"
        )

    # 2. Transplant a CLI-created cap into another holder's chain → verify FALSE.
    auth = _load_authority(store_dir, authority_id)
    reg = SimpleAuthorityRegistry()
    reg.register(auth)
    ops = TrustOperations(
        authority_registry=reg, key_manager=TrustKeyManager(), trust_store=store
    )
    _run_async(ops.initialize())
    cap_from_a = chain_a.capabilities[0]
    assert (
        _run_async(ops._verify_capability_signature(chain_a, cap_from_a)) is True
    ), "fixture bug: a CLI-established cap must verify in its OWN chain"
    assert _run_async(ops._verify_capability_signature(chain_b, cap_from_a)) is False, (
        "a CLI-established cap transplanted into another chain verified — the "
        "#1912 transplant defense does not cover the CLI surface"
    )


def test_cli_delegate_mints_v1_caps(tmp_path):
    from click.testing import CliRunner

    from kailash.trust.cli import main
    from kailash.trust.cli.commands import _create_store, _run_async

    runner = CliRunner()
    store_dir = str(tmp_path / ".eatp")
    (tmp_path / ".eatp").mkdir()
    authority_id = _cli_init_authority(runner, store_dir)

    r = runner.invoke(
        main,
        [
            "--store-dir",
            store_dir,
            "establish",
            "agent-root",
            "--authority",
            authority_id,
            "--capabilities",
            "read_data",
        ],
    )
    assert r.exit_code == 0, f"establish failed: {r.output}"

    r = runner.invoke(
        main,
        [
            "--store-dir",
            store_dir,
            "delegate",
            "--from",
            "agent-root",
            "--to",
            "agent-child",
            "--capabilities",
            "read_data",
        ],
    )
    assert r.exit_code == 0, f"delegate failed: {r.output}"

    store = _create_store(store_dir)
    _run_async(store.initialize())
    child = _run_async(store.get_chain("agent-child"))
    assert child.capabilities, "CLI delegate produced no capabilities"
    for cap in child.capabilities:
        assert cap.signing_payload_version == CAPABILITY_SIGNING_VERSION_V1, (
            "CLI `delegate` must mint v1-subject-bound caps (#1912); got "
            f"{cap.signing_payload_version!r} — the delegate sign site is unmigrated"
        )


# ---------------------------------------------------------------------------
# Cross-SDK byte-pin tripwire for the v1 (subject-bound) pre-image
# (cross-sdk-inspection.md Rule 4b/4d — the CONFIGURED case is the lockstep case)
# ---------------------------------------------------------------------------


def test_v1_capability_preimage_is_pinned():
    """Pin the canonical v1 (subject-bound) capability pre-image on a fixed input.

    The legacy (not-configured) pre-image is byte-identical to pre-#1912 and is
    pinned separately (test_capability_serializer_set_parity). This pins the
    CONFIGURED v1 shape — sorted keys, sorted constraints, ``subject_agent_id``
    bound — which is the cross-SDK signing-format LOCKSTEP case
    (cross-sdk-inspection.md Rule 4d): a change here diverges every v1 signature
    from the sibling SDK and MUST break this tripwire loudly. Re-pin ONLY in
    lockstep with the sibling SDK.
    """
    from kailash.trust.signing.crypto import serialize_for_signing

    cap = CapabilityAttestation(
        id="cap-fixed",
        capability="read_data",
        capability_type=CapabilityType.ACTION,
        constraints=["read_only", "no_export"],
        attester_id="org-test",
        attested_at=FIXED_TS,
        signature="",
        signing_payload_version=CAPABILITY_SIGNING_VERSION_V1,
    )
    payload = cap.to_signing_payload(subject_agent_id="agent-fixed")
    assert payload == {
        "id": "cap-fixed",
        "capability": "read_data",
        "capability_type": "action",
        "constraints": ["no_export", "read_only"],
        "attester_id": "org-test",
        "attested_at": "2026-03-11T14:30:00+00:00",
        "expires_at": None,
        "scope": None,
        "subject_agent_id": "agent-fixed",
    }
    expected = (
        '{"attested_at":"2026-03-11T14:30:00+00:00","attester_id":"org-test",'
        '"capability":"read_data","capability_type":"action",'
        '"constraints":["no_export","read_only"],"expires_at":null,'
        '"id":"cap-fixed","scope":null,"subject_agent_id":"agent-fixed"}'
    )
    assert serialize_for_signing(payload) == expected, (
        "v1 capability pre-image encoding changed — this is a cross-SDK signing-"
        "format change; re-pin ONLY in lockstep with the sibling SDK (#1912)"
    )
