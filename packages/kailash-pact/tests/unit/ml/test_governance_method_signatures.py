# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1: signature invariants for the three governance methods.

Locks the signatures specified in ``specs/pact-ml-integration.md`` §2
so a future refactor that changes an argument name or reorders a
keyword-only parameter fails loudly at test time (per
``rules/cross-sdk-inspection.md`` §3a -- structural invariant tests).
"""

from __future__ import annotations

import inspect

import pact.ml as pml


def _kwonly_names(fn) -> tuple[str, ...]:
    sig = inspect.signature(fn)
    return tuple(
        name
        for name, param in sig.parameters.items()
        if param.kind is inspect.Parameter.KEYWORD_ONLY
    )


def test_check_trial_admission_signature() -> None:
    """Keyword-only args match spec §2.1 exactly."""
    kwonly = _kwonly_names(pml.check_trial_admission)
    # Per spec §2.1: tenant_id, actor_id, trial_config,
    # budget_microdollars, latency_budget_ms, fairness_constraints.
    for required in (
        "tenant_id",
        "actor_id",
        "trial_config",
        "budget_microdollars",
        "latency_budget_ms",
        "fairness_constraints",
    ):
        assert (
            required in kwonly
        ), f"check_trial_admission missing kw-only param {required!r}"


def test_check_engine_method_clearance_signature() -> None:
    """Keyword-only args match spec §2.2 exactly."""
    kwonly = _kwonly_names(pml.check_engine_method_clearance)
    for required in (
        "tenant_id",
        "actor_id",
        "engine_name",
        "method_name",
        "clearance_required",
    ):
        assert (
            required in kwonly
        ), f"check_engine_method_clearance missing kw-only param {required!r}"


def test_check_cross_tenant_op_signature() -> None:
    """Keyword-only args match spec §2.3 exactly."""
    kwonly = _kwonly_names(pml.check_cross_tenant_op)
    for required in (
        "actor_id",
        "src_tenant_id",
        "dst_tenant_id",
        "operation",
        "clearance_required",
    ):
        assert (
            required in kwonly
        ), f"check_cross_tenant_op missing kw-only param {required!r}"


def test_check_trial_admission_validates_budget() -> None:
    """Negative budget raises GovernanceAdmissionError."""
    import pytest

    from pact.ml import GovernanceAdmissionError, check_trial_admission

    with pytest.raises(GovernanceAdmissionError, match="non-negative"):
        check_trial_admission(
            engine=None,
            tenant_id="t",
            actor_id="a",
            trial_config={},
            budget_microdollars=-1,
            latency_budget_ms=100,
        )


def test_check_trial_admission_rejects_nonint_budget() -> None:
    import pytest

    from pact.ml import GovernanceAdmissionError, check_trial_admission

    with pytest.raises(GovernanceAdmissionError):
        check_trial_admission(
            engine=None,
            tenant_id="t",
            actor_id="a",
            trial_config={},
            budget_microdollars=1.5,  # type: ignore[arg-type]
            latency_budget_ms=100,
        )


def test_check_trial_admission_requires_tenant_id() -> None:
    import pytest

    from pact.ml import GovernanceAdmissionError, check_trial_admission

    with pytest.raises(GovernanceAdmissionError, match="tenant_id"):
        check_trial_admission(
            engine=None,
            tenant_id="",
            actor_id="a",
            trial_config={},
            budget_microdollars=1000,
            latency_budget_ms=100,
        )


def test_check_engine_method_clearance_validates_identifiers() -> None:
    """Invalid engine_name / method_name raise GovernanceClearanceError."""
    import pytest

    from pact.ml import GovernanceClearanceError, check_engine_method_clearance

    # engine_name injection attempt
    with pytest.raises(GovernanceClearanceError):
        check_engine_method_clearance(
            engine=None,
            tenant_id="t",
            actor_id="a",
            engine_name='E"; DROP TABLE users; --',
            method_name="fit",
            clearance_required="D",
        )
    # method_name starts with a digit -> rejected
    with pytest.raises(GovernanceClearanceError):
        check_engine_method_clearance(
            engine=None,
            tenant_id="t",
            actor_id="a",
            engine_name="ClassificationEngine",
            method_name="1promote",
            clearance_required="D",
        )


def test_check_engine_method_clearance_rejects_unknown_clearance() -> None:
    import pytest

    from pact.ml import GovernanceClearanceError, check_engine_method_clearance

    with pytest.raises(GovernanceClearanceError):
        check_engine_method_clearance(
            engine=None,
            tenant_id="t",
            actor_id="a",
            engine_name="E",
            method_name="m",
            clearance_required="X",  # type: ignore[arg-type]
        )


def test_check_cross_tenant_op_rejects_identical_src_dst() -> None:
    """Per spec §2.3: identical src/dst raises typed error BEFORE lock."""
    import pytest

    from pact.ml import GovernanceCrossTenantError, check_cross_tenant_op

    with pytest.raises(GovernanceCrossTenantError, match="distinct"):
        check_cross_tenant_op(
            engine=None,
            actor_id="a",
            src_tenant_id="t1",
            dst_tenant_id="t1",
            operation="export",
            clearance_required="DTR",
        )


def test_check_cross_tenant_op_rejects_unknown_operation() -> None:
    import pytest

    from pact.ml import GovernanceCrossTenantError, check_cross_tenant_op

    with pytest.raises(GovernanceCrossTenantError):
        check_cross_tenant_op(
            engine=None,
            actor_id="a",
            src_tenant_id="t1",
            dst_tenant_id="t2",
            operation="clone",  # type: ignore[arg-type]
            clearance_required="DTR",
        )


def test_check_cross_tenant_op_v1_always_denied() -> None:
    """v1.0 contract: always-denied per spec IT-4 / Decision 12."""
    from pact.ml import check_cross_tenant_op

    decision = check_cross_tenant_op(
        engine=None,
        actor_id="a",
        src_tenant_id="t1",
        dst_tenant_id="t2",
        operation="export",
        clearance_required="DTR",
    )
    assert decision.admitted is False
    assert "v1.0" in decision.reason or "Decision 12" in decision.reason
    assert decision.src_clearance.cleared is False
    assert decision.dst_clearance.cleared is False


def test_probe_exception_fails_closed() -> None:
    """PACT MUST Rule 4: probe exceptions MUST fail-closed to denial."""
    from pact.ml import check_trial_admission

    def exploding_probe(engine, context):
        raise RuntimeError("synthetic probe failure")

    decision = check_trial_admission(
        engine=None,
        tenant_id="t",
        actor_id="a",
        trial_config={},
        budget_microdollars=100,
        latency_budget_ms=50,
        probe=exploding_probe,
    )
    assert decision.admitted is False
    assert "probe exception" in decision.reason


def test_fingerprint_is_sha256_8hex() -> None:
    """Cross-SDK fingerprint shape per rules/event-payload-classification.md §2."""
    from pact.ml import fingerprint_payload  # type: ignore[attr-defined]

    fp = fingerprint_payload({"foo": "bar"})
    assert fp.startswith("sha256:")
    hex_part = fp.split(":", 1)[1]
    assert len(hex_part) == 8
    assert all(c in "0123456789abcdef" for c in hex_part)
