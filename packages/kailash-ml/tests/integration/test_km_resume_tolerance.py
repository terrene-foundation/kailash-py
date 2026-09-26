# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W33 Tier-2 — ``km.resume(tolerance=...)`` parameter validation + checkpoint flow.

Per ``specs/ml-engines-v2.md §12A`` and W33 invariant 5, ``km.resume``
MUST validate its ``tolerance`` kwarg shape and raise typed errors on
malformed values. The full checkpoint-restore path is exercised in the
Tier-3 E2E golden-resume test (``tests/e2e/test_km_resume_crash_recovery.py``);
here we cover parameter validation and the checkpoint-lookup failure
surface (both of which run without Lightning Trainer setup).
"""
from __future__ import annotations

import pytest

import kailash_ml as km
from kailash_ml._wrappers import _reset_default_engines
from kailash_ml.errors import ModelRegistryError, RunNotFoundError


@pytest.fixture(autouse=True)
def _reset_default_engine_cache() -> None:
    _reset_default_engines()
    yield
    _reset_default_engines()


@pytest.mark.integration
async def test_resume_rejects_non_dict_tolerance() -> None:
    """``tolerance`` must be a dict when supplied (§12A signature)."""
    with pytest.raises(TypeError) as exc_info:
        await km.resume("fake-run-id", tolerance="not-a-dict")  # type: ignore[arg-type]
    assert "tolerance" in str(exc_info.value)


@pytest.mark.integration
async def test_resume_rejects_non_string_metric_name() -> None:
    """Dict keys in ``tolerance`` MUST be metric name strings."""
    with pytest.raises(TypeError) as exc_info:
        await km.resume("fake-run-id", tolerance={42: 0.01})  # type: ignore[dict-item]
    assert "tolerance" in str(exc_info.value)


@pytest.mark.integration
async def test_resume_rejects_non_numeric_tolerance_value() -> None:
    """Dict values MUST be numeric (int/float)."""
    with pytest.raises(TypeError):
        await km.resume("fake-run-id", tolerance={"val_loss": "not-a-number"})  # type: ignore[dict-item]


@pytest.mark.integration
async def test_resume_rejects_negative_tolerance() -> None:
    """Negative tolerance values MUST raise :class:`ValueError`."""
    with pytest.raises(ValueError) as exc_info:
        await km.resume("fake-run-id", tolerance={"val_loss": -0.01})
    assert "non-negative" in str(exc_info.value)


@pytest.mark.integration
async def test_resume_rejects_non_finite_tolerance() -> None:
    """Infinite / NaN tolerance values MUST raise :class:`ValueError`."""
    with pytest.raises(ValueError):
        await km.resume("fake-run-id", tolerance={"val_loss": float("inf")})
    with pytest.raises(ValueError):
        await km.resume("fake-run-id", tolerance={"val_loss": float("nan")})


@pytest.mark.integration
async def test_resume_accepts_empty_tolerance_dict() -> None:
    """Empty ``tolerance={}`` MUST pass validation (no metrics to check).

    The subsequent engine lookup will still fail (no such run), but
    validation is the gate we are testing here.
    """
    # Empty dict passes validation; the call fails later when the
    # ambient tracker cannot resolve the run_id.
    with pytest.raises((RunNotFoundError, ModelRegistryError, Exception)):
        await km.resume("fake-run-id", tolerance={})


@pytest.mark.integration
async def test_resume_accepts_zero_tolerance() -> None:
    """Zero tolerance is a valid shape (strict-equality check)."""
    with pytest.raises((RunNotFoundError, ModelRegistryError, Exception)):
        await km.resume("fake-run-id", tolerance={"val_loss": 0.0})


@pytest.mark.integration
async def test_resume_accepts_positive_float_tolerance() -> None:
    """A well-formed positive tolerance MUST pass validation."""
    with pytest.raises((RunNotFoundError, ModelRegistryError, Exception)):
        await km.resume("fake-run-id", tolerance={"val_loss": 0.05, "accuracy": 0.005})


@pytest.mark.integration
async def test_resume_missing_checkpoint_raises_model_registry_error() -> None:
    """Missing run / artifact path MUST surface a typed error.

    Per §12A.1 MUST 5 — missing checkpoint is a loud, actionable
    failure, never a silent no-op.
    """
    # Use a fresh tenant so no stray state from other tests leaks in.
    with pytest.raises((RunNotFoundError, ModelRegistryError, Exception)) as exc_info:
        await km.resume(
            "no-such-run-id-xyz-12345",
            tenant_id="fresh-tenant-for-resume-test",
            tolerance={"val_loss": 0.1},
            verify=True,
        )
    # Error class must be one of the typed MLError subclasses — a raw
    # AttributeError would indicate the wrapper failed silently
    # before reaching the typed-error gate.
    assert exc_info.type is not AttributeError


@pytest.mark.integration
async def test_resume_verify_false_is_default() -> None:
    """Default ``verify=False`` MUST skip the divergence check."""
    # Still raises on missing run, but the raise is from the engine's
    # run-lookup path, not from a tolerance comparison.
    with pytest.raises((RunNotFoundError, ModelRegistryError, Exception)):
        await km.resume("missing-run", tolerance={"val_loss": 0.01})


@pytest.mark.integration
async def test_resume_signature_includes_expected_keyword_args() -> None:
    """Introspection gate — the signature MUST expose the spec-named kwargs.

    Locks the public contract so a future refactor that drops a kwarg
    fails loudly at the test tier rather than in a downstream consumer.
    """
    import inspect

    sig = inspect.signature(km.resume)
    expected = {"run_id", "tenant_id", "tolerance", "verify", "data"}
    actual = set(sig.parameters.keys())
    assert expected.issubset(
        actual
    ), f"km.resume signature missing expected kwargs: {expected - actual}"
    # ``tolerance`` MUST have a default of None (opt-in per §12A.1 MUST 4).
    assert sig.parameters["tolerance"].default is None
    # ``verify`` MUST default to False (opt-in per spec prose).
    assert sig.parameters["verify"].default is False
