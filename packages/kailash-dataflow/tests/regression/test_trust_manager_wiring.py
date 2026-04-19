# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests — ``TenantTrustManager`` facade wiring.

Per rules/facade-manager-detection.md MUST Rule 2, every manager-shape
class exposed as a property on the framework's top-level class MUST have
a Tier 2 test file named ``test_<lowercase_manager>_wiring.py``. This
file covers ``TenantTrustManager`` (formerly ``db._tenant_trust_manager``).
Split from the former monolithic ``test_phase_5_11_trust_wiring.py``
(issue #499 Finding 8).

Current contract (2026-04-18): ``_tenant_trust_manager`` was REMOVED from
the DataFlow facade because no framework hot path invoked its methods
(Phase 5.11-shaped orphan, per rules/orphan-detection.md MUST 3). The
class remains importable at ``dataflow.trust.multi_tenant.TenantTrustManager``
for standalone consumers, but is NOT a ``db.*`` facade.

When a production call site is wired in the future, the facade MUST be
re-added IN THE SAME PR as the call site, and this file's assertions
inverted (assert ``hasattr(db, "trust_manager")`` and exercise the wiring).

Origin: Phase 5.11 orphan fix (2026-04-18) + issue #499 Finding 8.
"""

import pytest

from dataflow import DataFlow

pytestmark = pytest.mark.regression


def test_tenant_trust_manager_not_attached_as_facade():
    """Regression: ``_tenant_trust_manager`` was removed from the DataFlow
    facade on 2026-04-18 because no framework hot path invoked its
    methods (Phase 5.11-shaped orphan). When a production call site is
    wired, the facade MUST be re-added in the SAME PR. Until then, this
    test asserts the facade is absent so reintroducing it without a
    call site fails loudly.

    See rules/orphan-detection.md MUST 1+3, specs/dataflow-core.md § 21.2,
    workspaces/issues-492-497/journal/0003-RISK-tenant-trust-manager-orphan.md.
    """
    db = DataFlow(
        "sqlite:///:memory:",
        multi_tenant=True,
        trust_enforcement_mode="permissive",
    )
    try:
        assert not hasattr(db, "_tenant_trust_manager"), (
            "Re-adding _tenant_trust_manager without a production call site "
            "recreates the Phase 5.11 orphan. Wire into features/express.py "
            "in the SAME PR."
        )
        # The class itself remains importable for standalone consumer use.
        from dataflow.trust.multi_tenant import TenantTrustManager

        assert TenantTrustManager is not None
    finally:
        db.close()
