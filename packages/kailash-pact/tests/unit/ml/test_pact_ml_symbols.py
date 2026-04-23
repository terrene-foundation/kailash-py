# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1: symbol presence + top-level re-export smoke tests.

Covers orphan-detection.md Rule 6 (eager module-scope imports
appear in __all__) and the public-API contract from
specs/pact-ml-integration.md §2.
"""

from __future__ import annotations


def test_pact_ml_module_importable() -> None:
    """pact.ml module loads cleanly -- no missing imports, no syntax errors."""
    import pact.ml  # noqa: F401


def test_required_symbols_on_pact_ml() -> None:
    """All three governance methods + their decision dataclasses exist."""
    import pact.ml as pml

    for name in (
        "check_trial_admission",
        "check_engine_method_clearance",
        "check_cross_tenant_op",
        "AdmissionDecision",
        "ClearanceDecision",
        "CrossTenantDecision",
        "ClearanceRequirement",
        "MLGovernanceContext",
        "GovernanceAdmissionError",
        "GovernanceClearanceError",
        "GovernanceCrossTenantError",
    ):
        assert hasattr(pml, name), f"pact.ml missing symbol: {name}"


def test_symbols_re_exported_at_top_level_pact() -> None:
    """Top-level `pact` re-exports ml symbols per spec §2."""
    import pact

    for name in (
        "check_trial_admission",
        "check_engine_method_clearance",
        "check_cross_tenant_op",
        "AdmissionDecision",
        "ClearanceDecision",
        "CrossTenantDecision",
        "ClearanceRequirement",
        "MLGovernanceContext",
    ):
        assert hasattr(pact, name), f"pact top-level missing: {name}"
        assert (
            name in pact.__all__
        ), f"pact.__all__ missing {name} (orphan-detection.md Rule 6)"


def test_version_bumped_to_0_10_0() -> None:
    """Version consistency -- zero-tolerance.md Rule 5."""
    import pact

    assert pact.__version__ == "0.10.0"


def test_admission_decision_is_frozen_dataclass() -> None:
    """PACT MUST Rule 1: frozen decisions."""
    from dataclasses import FrozenInstanceError
    from datetime import UTC, datetime

    import pytest

    from pact.ml import AdmissionDecision

    d = AdmissionDecision(
        admitted=False,
        reason="test",
        binding_constraint=None,
        tenant_id="t1",
        actor_id="a1",
        decided_at=datetime.now(UTC),
        decision_id="d1",
    )
    with pytest.raises(FrozenInstanceError):
        d.admitted = True  # type: ignore[misc]


def test_clearance_decision_is_frozen_dataclass() -> None:
    from dataclasses import FrozenInstanceError
    from datetime import UTC, datetime

    import pytest

    from pact.ml import ClearanceDecision

    d = ClearanceDecision(
        cleared=False,
        reason="missing",
        missing_dimensions=("D",),
        tenant_id="t1",
        actor_id="a1",
        engine_name="E",
        method_name="m",
        decided_at=datetime.now(UTC),
        decision_id="d1",
    )
    with pytest.raises(FrozenInstanceError):
        d.cleared = True  # type: ignore[misc]


def test_cross_tenant_decision_is_frozen_dataclass() -> None:
    from dataclasses import FrozenInstanceError
    from datetime import UTC, datetime

    import pytest

    from pact.ml import ClearanceDecision, CrossTenantDecision

    cd = ClearanceDecision(
        cleared=False,
        reason="r",
        missing_dimensions=("D",),
        tenant_id="t",
        actor_id="a",
        engine_name="E",
        method_name="m",
        decided_at=datetime.now(UTC),
        decision_id="d",
    )
    ct = CrossTenantDecision(
        admitted=False,
        reason="r",
        src_clearance=cd,
        dst_clearance=cd,
        operation="export",
        actor_id="a",
        decided_at=datetime.now(UTC),
        decision_id="d",
    )
    with pytest.raises(FrozenInstanceError):
        ct.admitted = True  # type: ignore[misc]


def test_error_hierarchy_inherits_pacterror() -> None:
    """All governance errors inherit from PactError (pact-governance.md MUST NOT)."""
    from kailash.trust.pact.exceptions import PactError

    from pact.ml import (
        GovernanceAdmissionError,
        GovernanceClearanceError,
        GovernanceCrossTenantError,
    )

    assert issubclass(GovernanceAdmissionError, PactError)
    assert issubclass(GovernanceClearanceError, PactError)
    assert issubclass(GovernanceCrossTenantError, PactError)
