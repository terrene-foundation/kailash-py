# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests — ``TenantTrustManager`` orphan deletion.

Per ``rules/orphan-detection.md`` § 3 ("Removed = Deleted, Not Deprecated"),
``TenantTrustManager`` and ``CrossTenantDelegation`` were removed entirely
on 2026-04-27 (W6-006, finding F-B-05). The first stage of the deletion
(2026-04-18) removed the ``db._tenant_trust_manager`` facade but left the
class importable; the second stage (this PR) removes the class itself
because no production call site ever materialised.

The tests below assert BOTH:

1. The DataFlow facade does not expose ``_tenant_trust_manager``.
2. The class is no longer importable from ``dataflow.trust`` or
   ``dataflow.trust.multi_tenant``.

If a future PR resurrects either symbol without a production call site,
both assertions fire loudly. If a production cross-tenant delegation
requirement lands, design the new surface against the framework's hot
path (express, query engine) in the SAME PR — do NOT restore the orphan
from git history.

See:
    - rules/orphan-detection.md MUST 1, 3
    - specs/dataflow-core.md § 21.2
    - workspaces/issues-492-497/journal/0003-RISK-tenant-trust-manager-orphan.md
    - workspaces/portfolio-spec-audit/04-validate/W5-B-findings.md (F-B-05)
"""

import pytest

from dataflow import DataFlow

pytestmark = pytest.mark.regression


def test_tenant_trust_manager_facade_absent():
    """Regression: ``_tenant_trust_manager`` was removed from the DataFlow
    facade on 2026-04-18 (Phase 5.11-shaped orphan). Re-adding it without
    a production call site recreates the orphan.
    """
    db = DataFlow(
        "sqlite:///:memory:",
        multi_tenant=True,
        trust_enforcement_mode="permissive",
    )
    try:
        assert not hasattr(db, "_tenant_trust_manager"), (
            "Re-adding _tenant_trust_manager without a production call "
            "site recreates the Phase 5.11 orphan. Wire into "
            "features/express.py in the SAME PR."
        )
    finally:
        db.close()


def test_tenant_trust_manager_class_deleted():
    """Regression: the ``TenantTrustManager`` and ``CrossTenantDelegation``
    classes were deleted entirely on 2026-04-27 (W6-006). Restoring them
    without a production call site is BLOCKED per orphan-detection § 3.
    """
    # The submodule itself MUST be gone (deleted on 2026-04-27).
    with pytest.raises(ImportError):
        import dataflow.trust.multi_tenant  # noqa: F401

    # The re-exports from dataflow.trust MUST be gone.
    import dataflow.trust as trust_pkg

    assert not hasattr(trust_pkg, "TenantTrustManager"), (
        "TenantTrustManager was deleted on 2026-04-27 (W6-006). "
        "Restoring it without a production call site recreates the orphan. "
        "If you need cross-tenant delegation, design the surface against "
        "features/express.py or the query engine in the SAME PR."
    )
    assert not hasattr(trust_pkg, "CrossTenantDelegation"), (
        "CrossTenantDelegation was deleted on 2026-04-27 (W6-006). See "
        "TenantTrustManager assertion above."
    )

    # Verify __all__ no longer advertises them.
    assert "TenantTrustManager" not in trust_pkg.__all__
    assert "CrossTenantDelegation" not in trust_pkg.__all__
