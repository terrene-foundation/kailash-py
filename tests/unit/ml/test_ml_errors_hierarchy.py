# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 unit tests for the kailash.ml.errors hierarchy.

Exercises:
- Every family descends from MLError.
- The 2 cross-cutting errors sit directly under MLError.
- Every known subclass inherits the right family.
- BackendError (and UnsupportedPrecision, UnsupportedFamily) catch with
  ``except RuntimeError`` (0.x back-compat contract).
- MetricValueError / ParamValueError catch with ``except ValueError``.
- Fingerprint helper returns ``sha256:<8hex>`` shape.
- Error messages do not echo classified payload values.

See ``specs/ml-tracking.md §9.1`` and ``specs/kailash-core-ml-integration.md §3``.
"""
from __future__ import annotations

import pytest

from kailash.ml import errors as ml_errors
from kailash.ml.errors import (
    ActorRequiredError,
    AliasNotFoundError,
    AliasOccupiedError,
    ArtifactEncryptionError,
    ArtifactSizeExceededError,
    AuthorizationError,
    AutologError,
    AutologNoAmbientRunError,
    AutologUnknownFrameworkError,
    AutoMLError,
    BackendError,
    BudgetExhaustedError,
    CrossTenantLineageError,
    DashboardError,
    DiagnosticsError,
    DLDiagnosticsStateError,
    DriftMonitorError,
    DriftThresholdError,
    EnsembleFailureError,
    EnvVarDeprecatedError,
    ErasureRefusedError,
    ExperimentNotFoundError,
    FeatureNotFoundError,
    FeatureNotYetSupportedError,
    FeatureStoreError,
    ImmutableGoldenReferenceError,
    InferenceServerError,
    InsufficientSamplesError,
    InsufficientTrialsError,
    InvalidInputSchemaError,
    InvalidTenantIdError,
    LineageRequiredError,
    LiveStreamError,
    MetricValueError,
    MigrationFailedError,
    MigrationImportError,
    MLError,
    ModelLoadError,
    ModelNotFoundError,
    ModelRegistryError,
    ModelSignatureRequiredError,
    MultiTenantOpError,
    OnnxExportUnsupportedOpsError,
    ParamValueError,
    PointInTimeViolationError,
    ProtocolConformanceError,
    RateLimitExceededError,
    ReferenceNotFoundError,
    ReplayBufferUnderflowError,
    RewardModelRequiredError,
    RLEnvIncompatibleError,
    RLError,
    RLPolicyShapeMismatchError,
    RunNotFoundError,
    RunNotFoundInDashboardError,
    SeedReportError,
    ShadowDivergenceError,
    StaleFeatureError,
    TenantQuotaExceededError,
    TenantRequiredError,
    TrackerStoreInitError,
    TrackingError,
    UnknownTenantError,
    UnsupportedFamily,
    UnsupportedPrecision,
    UnsupportedTrainerError,
    WorkflowNodeMLContextError,
    fingerprint_classified_value,
)

# --- 11 families + 5 direct MLError children ---------------------------

DOMAIN_FAMILIES = [
    TrackingError,
    AutologError,
    RLError,
    BackendError,
    DriftMonitorError,
    InferenceServerError,
    ModelRegistryError,
    FeatureStoreError,
    AutoMLError,
    DiagnosticsError,
    DashboardError,
]

DIRECT_MLERROR_CHILDREN = [
    UnsupportedTrainerError,
    MultiTenantOpError,
    MigrationFailedError,
    WorkflowNodeMLContextError,
    EnvVarDeprecatedError,
]


@pytest.mark.parametrize("family", DOMAIN_FAMILIES)
def test_every_domain_family_descends_from_mlerror(family):
    assert issubclass(family, MLError)
    assert issubclass(family, Exception)


@pytest.mark.parametrize("cls", DIRECT_MLERROR_CHILDREN)
def test_cross_cutting_errors_inherit_directly_from_mlerror(cls):
    assert issubclass(cls, MLError)
    # Direct child: its __bases__ contains MLError (possibly via a single hop
    # but never via one of the 11 domain families).
    for family in DOMAIN_FAMILIES:
        assert not issubclass(cls, family), (
            f"{cls.__name__} MUST NOT inherit from domain family {family.__name__}; "
            "it is a direct MLError child per spec."
        )


# --- Tracking sub-types ----------------------------------------------


TRACKING_SUBCLASSES = [
    MetricValueError,
    ParamValueError,
    ActorRequiredError,
    TenantRequiredError,
    RunNotFoundError,
    ExperimentNotFoundError,
    TrackerStoreInitError,
    InvalidTenantIdError,
    ModelSignatureRequiredError,
    LineageRequiredError,
    ArtifactEncryptionError,
    ArtifactSizeExceededError,
    AliasNotFoundError,
    ErasureRefusedError,
    MigrationImportError,
]


@pytest.mark.parametrize("cls", TRACKING_SUBCLASSES)
def test_tracking_subclass_inherits_tracking_error(cls):
    assert issubclass(cls, TrackingError)
    assert issubclass(cls, MLError)


# --- ValueError multi-inherit (Phase-B Round 2b T-03 pattern) ---------


def test_metric_value_error_is_catchable_as_value_error():
    with pytest.raises(ValueError):
        raise MetricValueError(reason="NaN rejected")


def test_param_value_error_is_catchable_as_value_error():
    with pytest.raises(ValueError):
        raise ParamValueError(reason="Inf rejected")


# --- BackendError RuntimeError multi-inherit --------------------------


def test_backend_error_is_catchable_as_runtime_error():
    with pytest.raises(RuntimeError):
        raise BackendError(reason="probe failed")


def test_unsupported_precision_is_catchable_as_runtime_error():
    with pytest.raises(RuntimeError):
        raise UnsupportedPrecision(reason="fp16 on Pascal")


def test_unsupported_family_is_catchable_as_runtime_error():
    with pytest.raises(RuntimeError):
        raise UnsupportedFamily(reason="xgboost-gpu on ROCm")


# --- Family sub-type spot checks --------------------------------------


@pytest.mark.parametrize(
    "cls,family",
    [
        (AutologNoAmbientRunError, AutologError),
        (AutologUnknownFrameworkError, AutologError),
        (RLEnvIncompatibleError, RLError),
        (RLPolicyShapeMismatchError, RLError),
        (ReplayBufferUnderflowError, RLError),
        (RewardModelRequiredError, RLError),
        (FeatureNotYetSupportedError, RLError),
        (UnsupportedPrecision, BackendError),
        (UnsupportedFamily, BackendError),
        (ReferenceNotFoundError, DriftMonitorError),
        (InsufficientSamplesError, DriftMonitorError),
        (DriftThresholdError, DriftMonitorError),
        (ModelLoadError, InferenceServerError),
        (InvalidInputSchemaError, InferenceServerError),
        (RateLimitExceededError, InferenceServerError),
        (TenantQuotaExceededError, InferenceServerError),
        (ShadowDivergenceError, InferenceServerError),
        (OnnxExportUnsupportedOpsError, InferenceServerError),
        (ModelNotFoundError, ModelRegistryError),
        (AliasOccupiedError, ModelRegistryError),
        (CrossTenantLineageError, ModelRegistryError),
        (ImmutableGoldenReferenceError, ModelRegistryError),
        (FeatureNotFoundError, FeatureStoreError),
        (StaleFeatureError, FeatureStoreError),
        (PointInTimeViolationError, FeatureStoreError),
        (BudgetExhaustedError, AutoMLError),
        (InsufficientTrialsError, AutoMLError),
        (EnsembleFailureError, AutoMLError),
        (DLDiagnosticsStateError, DiagnosticsError),
        (ProtocolConformanceError, DiagnosticsError),
        (SeedReportError, DiagnosticsError),
        (UnknownTenantError, DashboardError),
        (AuthorizationError, DashboardError),
        (LiveStreamError, DashboardError),
        (RunNotFoundInDashboardError, DashboardError),
    ],
)
def test_subclass_inherits_correct_family(cls, family):
    assert issubclass(cls, family)
    assert issubclass(cls, MLError)


def test_no_subclass_multi_inherits_two_ml_families():
    """Spec invariant: no class multi-inherits from two domain families."""
    for cls in TRACKING_SUBCLASSES:
        mro_families = [f for f in DOMAIN_FAMILIES if issubclass(cls, f)]
        assert mro_families == [
            TrackingError
        ], f"{cls.__name__} inherits from more than one domain family: {mro_families}"


# --- Constructor contract ---------------------------------------------


def test_constructor_requires_reason_kw():
    with pytest.raises(TypeError):
        MLError()  # missing required kw 'reason'


def test_constructor_stores_context():
    err = ModelNotFoundError(
        reason="no such model",
        tenant_id="tenant-alice",
        actor_id="agent-42",
        resource_id="churn_v7",
        extra="x",
    )
    assert err.reason == "no such model"
    assert err.tenant_id == "tenant-alice"
    assert err.actor_id == "agent-42"
    assert err.resource_id == "churn_v7"
    assert err.context == {"extra": "x"}


def test_error_message_is_structured_not_raw_payload():
    """No classified value leaks into __str__/__repr__ verbatim."""
    raw_email = "alice@example.com"
    err = TenantRequiredError(
        reason="no tenant resolved",
        resource_id=fingerprint_classified_value(raw_email),
    )
    msg = str(err)
    assert raw_email not in msg
    assert "sha256:" in msg


# --- Fingerprint helper -----------------------------------------------


def test_fingerprint_classified_value_shape():
    fp = fingerprint_classified_value("alice@example.com")
    assert fp.startswith("sha256:")
    assert len(fp) == len("sha256:") + 8  # 8 hex chars


def test_fingerprint_classified_value_integer_passes_through():
    assert fingerprint_classified_value(42) == "42"


def test_fingerprint_classified_value_none_sentinel():
    assert fingerprint_classified_value(None) == "sha256:none"


def test_fingerprint_classified_value_deterministic():
    a = fingerprint_classified_value("alice@example.com")
    b = fingerprint_classified_value("alice@example.com")
    assert a == b


def test_fingerprint_distinguishes_different_values():
    a = fingerprint_classified_value("alice@example.com")
    b = fingerprint_classified_value("bob@example.com")
    assert a != b


# --- __all__ completeness --------------------------------------------


def test_all_exports_resolve():
    for name in ml_errors.__all__:
        assert hasattr(ml_errors, name), f"{name} missing from module"


def test_all_exception_classes_are_subclasses_of_mlerror():
    for name in ml_errors.__all__:
        obj = getattr(ml_errors, name)
        if isinstance(obj, type) and issubclass(obj, Exception):
            assert issubclass(obj, MLError), f"{name} is not an MLError"
