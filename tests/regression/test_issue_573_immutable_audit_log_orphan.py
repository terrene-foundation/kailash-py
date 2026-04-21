"""Regression: #573 — `kailash.trust.immutable_audit_log` orphan removed.

Cross-SDK mirror of kailash-rs#461 (PR #466). The prior
``kailash.trust.immutable_audit_log`` module defined ``ImmutableAuditLog``
as a deque-based append-only log that NO production code in the SDK
imported. Per ``rules/orphan-detection.md`` §1 and §3 (Removed = Deleted,
Not Deprecated), the module was deleted entirely in kailash 2.8.12.

This regression test guards against re-introduction: if a future refactor
adds the orphan back without wiring it into a production call site, this
test fails and the agent must either wire it or leave it out.
"""

# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Terrene Foundation

from __future__ import annotations

import importlib
from pathlib import Path

import pytest


@pytest.mark.regression
class TestImmutableAuditLogOrphanRemoval:
    """Guard: the deleted orphan module does not come back."""

    def test_immutable_audit_log_module_is_not_importable(self) -> None:
        """Importing ``kailash.trust.immutable_audit_log`` MUST fail.

        The module was an orphan deleted in 2.8.12. A future re-introduction
        MUST be paired with a production call site (orphan-detection §1) and
        this test updated to prove the wiring, not silently resurrect the
        unused facade.
        """
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module("kailash.trust.immutable_audit_log")

    def test_immutable_audit_log_py_not_present_in_tree(self) -> None:
        """File-level assertion for the orphan removal."""
        repo_root = Path(__file__).resolve().parents[2]
        orphan = repo_root / "src" / "kailash" / "trust" / "immutable_audit_log.py"
        assert not orphan.exists(), (
            f"{orphan} came back — issue #573 deleted this file as a "
            "zero-production-consumer orphan (cross-SDK mirror of "
            "kailash-rs#461). If it was restored, wire it into a "
            "production call site or delete it again."
        )

    def test_trust_package_has_no_immutable_audit_log_reexport(self) -> None:
        """Regression: ``from kailash.trust import ImmutableAuditLog`` stays broken."""
        import kailash.trust as trust_pkg

        assert not hasattr(trust_pkg, "ImmutableAuditLog"), (
            "kailash.trust.ImmutableAuditLog was re-exported. The canonical "
            "audit-log surface is kailash.trust.audit_store (InMemoryAuditStore "
            "+ AuditStoreProtocol). Adding ImmutableAuditLog back without "
            "production consumers is the exact orphan pattern #573 deleted."
        )
