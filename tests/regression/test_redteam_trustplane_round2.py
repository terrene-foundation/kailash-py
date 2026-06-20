# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression tests — holistic trust-plane redteam (round 2).

A holistic post-multi-wave redteam of the trust-plane surface (beyond the
2.41.1 PACT KSP/Bridge + cascade scope) surfaced ten confirmed defects.
This file pins the SIX that changed behavior; each test fails against the
pre-fix code and passes against the fix.

| ID         | Module                              | Defect (fixed)                                          |
| ---------- | ----------------------------------- | ------------------------------------------------------- |
| RS-01      | trust.operations.TrustKeyManager    | revoke_old_key emitted "revoked" audit but never        |
|            | + trust.signing.rotation            | invalidated the key (audit/store divergence)            |
| PR-2       | trust.plane.project.verify          | tamper check skipped when content_hash stripped         |
| PR-3       | trust.plane.project (posture load)  | corrupted posture silently downgraded to SUPERVISED     |
| PCI-R1-01  | trust.pact.audit.AuditChain         | from_dict docstring "Raises PactError" never raised     |
| EA-01      | trust.enforce.proximity             | NaN/Inf usage bypassed proximity escalation             |
| RS-03      | trust.revocation.broadcaster        | async-subscriber exceptions bypassed dead-letter queue  |

Of the remaining three findings, two (RS-02 rotation "atomic" over-claim, PGC-03
context.py None-envelope doc contradiction) are documentation-accuracy
corrections with NO behavioral delta — covered by the unchanged-behavior existing
suites plus the corrected docstrings, so they carry no behavioral regression test
here. The third (the vault retire/recommit "clearance-tenant-domain" gate-label
over-claim) was a docs-only correction AT 2.42.0, but was SUBSEQUENTLY CLOSED
behaviorally by F-VAULT-630 — which wires the full CL-02a tenant/domain + CL-04
cooling-off ``evaluate_clearance`` gate into both surfaces, so the gate label is
now accurate by behavior rather than by walked-back docstring. Its behavioral
coverage lives in ``tests/regression/test_eatp12_vault_630_clearance_wiring.py``.
"""

from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.regression


# ---------------------------------------------------------------------------
# RS-01 — revoke_old_key MUST invalidate the key (audit/store divergence)
# ---------------------------------------------------------------------------


def test_rs01_remove_key_tombstones_material() -> None:
    """TrustKeyManager.remove_key clears material (tombstone) and reports hit."""
    from kailash.trust.operations import TrustKeyManager

    km = TrustKeyManager()
    km.register_key("k1", "private-material")
    assert km.get_key("k1") == "private-material"

    assert km.remove_key("k1") is True
    # Tombstone: material cleared (falsy), distinct from None (never registered).
    assert km.get_key("k1") == ""
    # A second remove of an absent/already-removed key reports miss.
    assert km.remove_key("absent") is False


async def test_rs01_removed_key_cannot_sign() -> None:
    """After remove_key, the key is no longer usable for signing."""
    from kailash.trust.operations import TrustKeyManager

    km = TrustKeyManager()
    km.register_key("k1", "private-material")
    km.remove_key("k1")
    # sign() raises because the tombstoned material is falsy ("key not found").
    with pytest.raises(ValueError):
        await km.sign("payload", "k1")


# ---------------------------------------------------------------------------
# PR-2 — verify() MUST treat a missing content_hash as a verification failure
# ---------------------------------------------------------------------------


async def _project_with_one_decision(trust_dir):
    from kailash.trust.plane.models import DecisionRecord, DecisionType
    from kailash.trust.plane.project import TrustProject

    project = await TrustProject.create(
        trust_dir=trust_dir, project_name="RedteamR2", author="tester"
    )
    await project.record_decision(
        DecisionRecord(
            decision_type=DecisionType.SCOPE,
            decision="d",
            rationale="r",
        )
    )
    return project


async def test_pr2_verify_nonstrict_flags_missing_content_hash(tmp_path) -> None:
    """A decision record stripped of content_hash fails non-strict verification."""
    trust_dir = tmp_path / "tp"
    project = await _project_with_one_decision(trust_dir)

    dfile = next((trust_dir / "decisions").glob("*.json"))
    data = json.loads(dfile.read_text())
    # Tamper the decision content AND strip its content_hash — the pre-fix
    # truthiness short-circuit (`if stored_hash and ...`) skipped the check.
    data["decision"] = "TAMPERED"
    del data["content_hash"]
    dfile.write_text(json.dumps(data))

    report = await project.verify(strict=False)
    assert report["chain_valid"] is False
    assert any("content_hash" in issue for issue in report["integrity_issues"])


async def test_pr2_verify_strict_raises_on_missing_content_hash(tmp_path) -> None:
    """Strict verification raises on a record missing its content_hash."""
    from kailash.trust.plane.exceptions import ChainHashMismatchError

    trust_dir = tmp_path / "tp"
    project = await _project_with_one_decision(trust_dir)

    dfile = next((trust_dir / "decisions").glob("*.json"))
    data = json.loads(dfile.read_text())
    data["decision"] = "TAMPERED"
    del data["content_hash"]
    dfile.write_text(json.dumps(data))

    with pytest.raises(ChainHashMismatchError):
        await project.verify(strict=True)


# ---------------------------------------------------------------------------
# PR-3 — corrupted persisted posture MUST fail-closed to PSEUDO, not downgrade
# ---------------------------------------------------------------------------


async def _create_then_reload_with_posture(trust_dir, posture_value):
    from kailash.trust.plane.project import TrustProject

    await TrustProject.create(
        trust_dir=trust_dir, project_name="PostureR2", author="tester"
    )
    manifest_path = trust_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest.setdefault("metadata", {})["trust_posture"] = posture_value
    manifest_path.write_text(json.dumps(manifest))
    return await TrustProject.load(trust_dir)


async def test_pr3_corrupt_posture_fails_closed_to_pseudo(tmp_path) -> None:
    """An unrecognized persisted posture restores to PSEUDO (most restrictive)."""
    from kailash.trust.posture.postures import TrustPosture

    loaded = await _create_then_reload_with_posture(
        tmp_path / "tp", "not-a-real-posture-xyz"
    )
    restored = loaded._posture_machine.get_posture(loaded._agent_id)
    # Fail-closed: NOT the permissive SUPERVISED constructor default.
    assert restored == TrustPosture.PSEUDO


async def test_pr3_valid_posture_still_restores(tmp_path) -> None:
    """Regression guard: a valid persisted posture still restores correctly."""
    from kailash.trust.posture.postures import TrustPosture

    loaded = await _create_then_reload_with_posture(tmp_path / "tp", "tool")
    assert loaded._posture_machine.get_posture(loaded._agent_id) == TrustPosture.TOOL


async def test_pr3_legacy_posture_alias_still_restores(tmp_path) -> None:
    """A legacy posture alias (handled by _missing_) restores, not fail-closed."""
    from kailash.trust.posture.postures import TrustPosture

    loaded = await _create_then_reload_with_posture(tmp_path / "tp", "pseudo_agent")
    assert loaded._posture_machine.get_posture(loaded._agent_id) == TrustPosture.PSEUDO


# ---------------------------------------------------------------------------
# PCI-R1-01 — AuditChain.from_dict MUST raise on a corrupted chain
# ---------------------------------------------------------------------------


def _build_chain():
    from kailash.trust.pact.audit import AuditChain
    from kailash.trust.pact.config import VerificationLevel

    chain = AuditChain(chain_id="redteam-r2")
    chain.append("agent-1", "act-1", VerificationLevel.AUTO_APPROVED, result="ok")
    chain.append("agent-1", "act-2", VerificationLevel.FLAGGED, result="ok")
    return chain


def test_pci_r1_01_valid_chain_round_trips() -> None:
    """A pristine chain deserializes without raising."""
    from kailash.trust.pact.audit import AuditChain

    data = _build_chain().to_dict()
    restored = AuditChain.from_dict(data)
    assert len(restored.anchors) == 2


def test_pci_r1_01_corrupted_chain_raises_pacterror() -> None:
    """A tampered anchor hash raises PactError (honors the documented contract)."""
    from kailash.trust.pact.audit import AuditChain
    from kailash.trust.pact.exceptions import PactError

    data = _build_chain().to_dict()
    # Tamper the genesis anchor's content_hash — breaks both its own seal
    # verification AND the next anchor's previous_hash linkage.
    data["anchors"][0]["content_hash"] = "0" * 64

    with pytest.raises(PactError):
        AuditChain.from_dict(data)


# ---------------------------------------------------------------------------
# EA-01 — proximity scan MUST fail-closed on non-finite usage (NaN/Inf)
# ---------------------------------------------------------------------------


def _scan(used, limit):
    from kailash.trust.constraints.dimension import ConstraintCheckResult
    from kailash.trust.enforce.proximity import ProximityScanner

    scanner = ProximityScanner()
    return scanner.scan(
        [ConstraintCheckResult(satisfied=True, reason="", used=used, limit=limit)],
        "cost_limit",
    )


def test_ea01_nan_usage_escalates_to_held() -> None:
    """A NaN usage value escalates to HELD instead of silently emitting no alert."""
    from kailash.trust.enforce.strict import Verdict

    alerts = _scan(float("nan"), 100.0)
    assert len(alerts) == 1
    assert alerts[0].escalated_verdict == Verdict.HELD


def test_ea01_inf_usage_escalates_to_held() -> None:
    from kailash.trust.enforce.strict import Verdict

    alerts = _scan(float("inf"), 100.0)
    assert len(alerts) == 1
    assert alerts[0].escalated_verdict == Verdict.HELD


def test_ea01_nonfinite_limit_is_skipped_not_crash() -> None:
    """A non-finite limit is unmeasurable → skipped (no crash, no false alert)."""
    assert _scan(50.0, float("nan")) == []


def test_ea01_finite_usage_unaffected() -> None:
    """Regression guard: finite usage behaves exactly as before the fix."""
    from kailash.trust.enforce.strict import Verdict

    assert _scan(50.0, 100.0) == []  # 0.50 < flag 0.80
    high = _scan(99.0, 100.0)  # 0.99 >= hold 0.95
    assert len(high) == 1 and high[0].escalated_verdict == Verdict.HELD


# ---------------------------------------------------------------------------
# RS-03 — async revocation-subscriber failures MUST reach the dead-letter queue
# ---------------------------------------------------------------------------


async def test_rs03_async_subscriber_failure_is_dead_lettered() -> None:
    """An async subscriber that raises is recorded as a dead letter."""
    import asyncio

    from kailash.trust.revocation.broadcaster import (
        InMemoryRevocationBroadcaster,
        RevocationEvent,
        RevocationType,
    )

    broadcaster = InMemoryRevocationBroadcaster()

    async def failing_subscriber(event):
        raise RuntimeError("subscriber boom")

    broadcaster.subscribe(failing_subscriber)
    broadcaster.broadcast(
        RevocationEvent(
            event_id="rev-r2-1",
            revocation_type=RevocationType.AGENT_REVOKED,
            target_id="agent-x",
            revoked_by="admin",
            reason="redteam r2",
        )
    )
    # Let the detached coroutine run and its done-callback fire.
    await asyncio.sleep(0.05)

    dead_letters = broadcaster.get_dead_letters()
    assert len(dead_letters) == 1
    assert "boom" in dead_letters[0].error


async def test_rs03_clean_async_subscriber_records_nothing() -> None:
    """Regression guard: a clean async subscriber leaves the dead-letter queue empty."""
    import asyncio

    from kailash.trust.revocation.broadcaster import (
        InMemoryRevocationBroadcaster,
        RevocationEvent,
        RevocationType,
    )

    broadcaster = InMemoryRevocationBroadcaster()
    seen = []

    async def ok_subscriber(event):
        seen.append(event.event_id)

    broadcaster.subscribe(ok_subscriber)
    broadcaster.broadcast(
        RevocationEvent(
            event_id="rev-r2-2",
            revocation_type=RevocationType.AGENT_REVOKED,
            target_id="agent-y",
            revoked_by="admin",
            reason="redteam r2",
        )
    )
    await asyncio.sleep(0.05)

    assert seen == ["rev-r2-2"]
    assert broadcaster.get_dead_letters() == []
