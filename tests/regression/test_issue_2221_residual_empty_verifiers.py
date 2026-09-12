# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Regression tests: residual "absence rendered as a success" verifiers (#2221/#2189).

The parent sweep (#2189) and the first #2221 lane closed three named sites --
``AuditStoreProtocol.verify_chain`` in both concrete stores, the
``all_conditions_met`` resume gate, and the ``len(registry) >= 0`` health check.

This module covers the residual SIBLINGS of the identical class found by
re-sweeping ``src/kailash/trust`` for verifiers with an emptiness guard. Each is
a mechanism that learned NOTHING returning the same value as one that checked
and passed:

* ``SqliteAuditLog.verify_integrity()``  -- empty/wiped table -> ``(True, None)``
* ``GovernanceEngine.verify_audit_integrity()`` -- no audit log -> ``(True, None)``
  (its own docstring called this "vacuously valid")
* ``LinkedHashChain.verify_chain_linkage()`` -- the method the SECURITY NOTE on
  ``verify_chain`` designates as the FULL cryptographic verification path,
  returning ``(True, None)`` for an empty hash list
* ``LinkedHashChain.verify_chain()`` -- empty chain "structurally valid"
* ``AuditChain.verify_chain_integrity()`` -- ``len(errors) == 0`` over a loop
  that never ran (shape 5: counting failures instead of asserting successes)

Every probe is paired with a CONTROL asserting the POPULATED/INTACT case still
verifies True, so none of these fixes can be satisfied by "now always False".
"""

from __future__ import annotations

import pytest

from kailash.trust.chain import LinkedHashChain
from kailash.trust.pact.audit import AuditChain, VerificationLevel
from kailash.trust.pact.compilation import CompiledOrg, OrgNode
from kailash.trust.pact.stores.sqlite import SqliteAuditLog

pytestmark = pytest.mark.regression


def _make_compiled_org(org_id: str = "resid-org") -> CompiledOrg:
    from kailash.trust.pact.addressing import NodeType

    org = CompiledOrg(org_id=org_id)
    org.nodes["D1"] = OrgNode(
        address="D1", node_type=NodeType.DEPARTMENT, name="Eng", node_id="eng"
    )
    org.nodes["D1-R1"] = OrgNode(
        address="D1-R1",
        node_type=NodeType.ROLE,
        name="Lead",
        node_id="lead",
        parent_address="D1",
    )
    return org


class TestSqliteAuditLogEmptyFailsClosed:
    """A wiped persisted audit table must not verify as intact."""

    def test_empty_log_is_not_valid(self) -> None:
        """PROBE: a log with no rows is unverifiable, not verified."""
        log = SqliteAuditLog(":memory:")
        is_valid, error = log.verify_integrity()
        assert is_valid is False
        assert error is not None
        assert "empty" in error.lower()

    def test_wiped_log_is_not_valid(self) -> None:
        """PROBE (both poles on one log): populated verifies, wiped does not."""
        log = SqliteAuditLog(":memory:")
        for i in range(3):
            log.append(f"action_{i}", {"index": i})

        # Pole 1 -- CONTROL: the populated, intact chain still verifies.
        assert log.verify_integrity() == (True, None)

        # Wipe the table, as an attacker deleting the audit trail would.
        conn = log._get_connection()
        conn.execute("DELETE FROM pact_audit_log")
        conn.commit()

        # Pole 2: the emptied table must NOT read as intact.
        is_valid, error = log.verify_integrity()
        assert is_valid is False
        assert error is not None

    def test_populated_log_still_valid(self) -> None:
        """CONTROL: the fix is not 'always False'."""
        log = SqliteAuditLog(":memory:")
        log.append("action", {"k": "v"})
        assert log.verify_integrity() == (True, None)

    def test_tampered_log_still_detected(self) -> None:
        """CONTROL: real tamper detection is unchanged by the empty-case fix."""
        log = SqliteAuditLog(":memory:")
        log.append("action_1", {"original": True})
        conn = log._get_connection()
        conn.execute(
            "UPDATE pact_audit_log SET details_json = ? WHERE id = 1", ('{"t":1}',)
        )
        conn.commit()
        is_valid, error = log.verify_integrity()
        assert is_valid is False
        assert error is not None and "Tamper" in error


class TestEngineVerifyAuditIntegrityFailsClosed:
    """`no audit log configured` is not the same fact as `the audit log is intact`."""

    def test_no_audit_log_is_not_valid(self) -> None:
        """PROBE: an engine with no persisted audit log cannot claim integrity."""
        from kailash.trust.pact.engine import GovernanceEngine

        engine = GovernanceEngine(_make_compiled_org("no-audit"))
        is_valid, error = engine.verify_audit_integrity()
        assert is_valid is False
        assert error is not None
        assert "unverifiable" in error.lower() or "no " in error.lower()

    def test_configured_engine_with_entries_still_valid(self) -> None:
        """CONTROL: a real sqlite-backed engine with audit entries still verifies."""
        from kailash.trust.pact.clearance import RoleClearance, VettingStatus
        from kailash.trust.pact.config import ConfidentialityLevel
        from kailash.trust.pact.engine import GovernanceEngine

        engine = GovernanceEngine(
            _make_compiled_org("audit-ok"), store_backend="sqlite", store_url=":memory:"
        )
        engine.grant_clearance(
            "D1-R1",
            RoleClearance(
                role_address="D1-R1",
                max_clearance=ConfidentialityLevel.CONFIDENTIAL,
                granted_by_role_address="R1",
                vetting_status=VettingStatus.ACTIVE,
            ),
        )
        assert engine.verify_audit_integrity() == (True, None)


class TestLinkedHashChainEmptyFailsClosed:
    """The designated cryptographic verification path must not pass on nothing."""

    def test_verify_chain_linkage_empty_is_not_valid(self) -> None:
        """PROBE: zero original hashes prove nothing about the chain."""
        chain = LinkedHashChain()
        valid, _break_idx = chain.verify_chain_linkage([])
        assert valid is False

    def test_verify_chain_linkage_populated_still_valid(self) -> None:
        """CONTROL: a genuine matching linkage still verifies."""
        chain = LinkedHashChain()
        chain.add_hash("a1", "hash_1")
        chain.add_hash("a2", "hash_2")
        assert chain.verify_chain_linkage(["hash_1", "hash_2"]) == (True, None)

    def test_verify_chain_linkage_tampered_still_detected(self) -> None:
        """CONTROL: tamper detection is unchanged."""
        chain = LinkedHashChain()
        chain.add_hash("a1", "hash_1")
        chain.add_hash("a2", "hash_2")
        valid, break_idx = chain.verify_chain_linkage(["hash_1", "TAMPERED"])
        assert valid is False
        assert break_idx == 1

    def test_verify_chain_empty_is_not_valid(self) -> None:
        """PROBE: an empty chain is an absent chain, not a sound one."""
        chain = LinkedHashChain()
        valid, _break_idx = chain.verify_chain()
        assert valid is False

    def test_verify_chain_populated_still_valid(self) -> None:
        """CONTROL: a well-formed populated chain still verifies."""
        chain = LinkedHashChain()
        chain.add_hash("a1", "h1")
        chain.add_hash("a2", "h2")
        assert chain.verify_chain() == (True, None)


class TestAuditChainVerifyChainIntegrityFailsClosed:
    """`len(errors) == 0` over a loop that never ran is not a verification."""

    def test_empty_chain_is_not_valid(self) -> None:
        """PROBE: no anchors -> nothing was verified, so not valid."""
        chain = AuditChain(chain_id="empty-chain")
        is_valid, errors = chain.verify_chain_integrity()
        assert is_valid is False
        assert errors and any("empty" in e.lower() for e in errors)

    def test_populated_chain_still_valid(self) -> None:
        """CONTROL: a real sealed chain still verifies clean."""
        chain = AuditChain(chain_id="ok-chain")
        chain.append("agent-1", "act-1", VerificationLevel.AUTO_APPROVED)
        chain.append("agent-1", "act-2", VerificationLevel.AUTO_APPROVED)
        is_valid, errors = chain.verify_chain_integrity()
        assert is_valid is True
        assert errors == []
