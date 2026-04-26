# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Canonical ``MLError`` hierarchy for the kailash-ml wave.

This module is the single source of truth for every ML-lifecycle exception
raised anywhere across the seven-package wave release
(kailash 2.9.0 / kailash-dataflow 2.1.0 / kailash-nexus 2.2.0 /
kailash-kaizen 2.12.0 / kailash-pact 0.10.0 / kailash-align 0.5.0 /
kailash-ml 1.0.0).

Downstream packages import from here; kailash-ml additionally re-exports the
full surface at ``kailash_ml.errors`` with identity preservation so legacy
``from kailash_ml.errors import MLError`` imports continue to refer to the
same classes. See ``specs/kailash-core-ml-integration.md §3`` and
``specs/ml-tracking.md §9.1``.

Hierarchy (authoritative — matches ``ml-tracking.md §9.1.1`` tree)::

    MLError
    ├── TrackingError
    │   ├── MetricValueError (TrackingError, ValueError)
    │   ├── ParamValueError (TrackingError, ValueError)
    │   ├── ActorRequiredError
    │   ├── TenantRequiredError
    │   ├── RunNotFoundError
    │   ├── ExperimentNotFoundError
    │   ├── TrackerStoreInitError
    │   ├── InvalidTenantIdError
    │   ├── ModelSignatureRequiredError
    │   ├── LineageRequiredError
    │   ├── ArtifactEncryptionError
    │   ├── ArtifactSizeExceededError
    │   ├── AliasNotFoundError
    │   ├── ErasureRefusedError
    │   └── MigrationImportError
    ├── AutologError
    │   ├── AutologNoAmbientRunError
    │   ├── AutologUnknownFrameworkError
    │   ├── AutologAttachError
    │   ├── AutologDetachError
    │   └── AutologDoubleAttachError
    ├── RLError
    │   ├── RLEnvIncompatibleError
    │   ├── RLPolicyShapeMismatchError
    │   ├── ReplayBufferUnderflowError
    │   ├── RewardModelRequiredError
    │   └── FeatureNotYetSupportedError
    ├── BackendError (MLError, RuntimeError)
    │   ├── UnsupportedPrecision
    │   └── UnsupportedFamily
    ├── DriftMonitorError
    │   ├── ReferenceNotFoundError
    │   ├── InsufficientSamplesError
    │   └── DriftThresholdError
    ├── InferenceServerError
    │   ├── ModelLoadError
    │   ├── InvalidInputSchemaError
    │   ├── RateLimitExceededError
    │   ├── TenantQuotaExceededError
    │   ├── ShadowDivergenceError
    │   └── OnnxExportUnsupportedOpsError
    ├── ModelRegistryError
    │   ├── ModelNotFoundError
    │   ├── AliasOccupiedError
    │   ├── CrossTenantLineageError
    │   └── ImmutableGoldenReferenceError
    ├── FeatureStoreError
    │   ├── FeatureNotFoundError
    │   ├── StaleFeatureError
    │   └── PointInTimeViolationError
    ├── AutoMLError
    │   ├── BudgetExhaustedError
    │   ├── InsufficientTrialsError
    │   └── EnsembleFailureError
    ├── DiagnosticsError
    │   ├── DLDiagnosticsStateError
    │   ├── ProtocolConformanceError
    │   └── SeedReportError
    ├── DashboardError
    │   ├── UnknownTenantError
    │   ├── AuthorizationError
    │   ├── LiveStreamError
    │   └── RunNotFoundInDashboardError
    ├── UnsupportedTrainerError           (Decision 8 — cross-cutting)
    ├── MultiTenantOpError                (Decision 12 — cross-cutting)
    ├── MigrationFailedError              (Tracking migration — see §7)
    ├── MigrationRequiredError            (Tracking migration — see §7)
    ├── WorkflowNodeMLContextError        (workflow nodes — see §7)
    └── EnvVarDeprecatedError             (2.0 env-var sunset contract)

No subclass multi-inherits from two domain families. ``RateLimitExceededError``,
``TenantQuotaExceededError`` and ``AliasNotFoundError`` are DECLARED ONCE under
their canonical home and re-exported (as module names only, not as second base
classes) by sibling domains. Canonical homes:

- ``AliasNotFoundError`` — :class:`TrackingError` (alias resolution is
  tracker-adjacent; registry callers re-export the name).
- ``RateLimitExceededError`` — :class:`InferenceServerError` (first listed
  call site).
- ``TenantQuotaExceededError`` — :class:`InferenceServerError` (quota checks
  appear first at the serving layer).

Registry-specific tenant quota breaches raise :class:`TenantQuotaExceededError`
directly; catching callers can catch either the canonical family
(``InferenceServerError``) or the cross-cutting root (``MLError``).

All messages MUST NOT echo classified payload fields verbatim. Where an error
references classified content (a classified PK value, a classified column
value), the caller MUST fingerprint via :func:`fingerprint_classified_value`
before passing into ``reason``. See ``rules/event-payload-classification.md``.
"""
from __future__ import annotations

import hashlib
from typing import Any, Optional

__all__ = [
    # Fingerprint helper (classified-payload discipline)
    "fingerprint_classified_value",
    # --- Root ---
    "MLError",
    # --- 11 domain families ---
    "TrackingError",
    "AutologError",
    "RLError",
    "BackendError",
    "DriftMonitorError",
    "InferenceServerError",
    "ModelRegistryError",
    "FeatureStoreError",
    "AutoMLError",
    "DiagnosticsError",
    "DashboardError",
    # --- Cross-cutting (direct children of MLError) ---
    "UnsupportedTrainerError",
    "MultiTenantOpError",
    "MigrationFailedError",
    "MigrationRequiredError",
    "WorkflowNodeMLContextError",
    "EnvVarDeprecatedError",
    # --- TrackingError subclasses ---
    "MetricValueError",
    "ParamValueError",
    "ActorRequiredError",
    "TenantRequiredError",
    "RunNotFoundError",
    "ExperimentNotFoundError",
    "TrackerStoreInitError",
    "InvalidTenantIdError",
    "ModelSignatureRequiredError",
    "LineageRequiredError",
    "LineageNotImplementedError",
    "ArtifactEncryptionError",
    "ArtifactSizeExceededError",
    "AliasNotFoundError",
    "ErasureRefusedError",
    "MigrationImportError",
    # --- AutologError subclasses ---
    "AutologNoAmbientRunError",
    "AutologUnknownFrameworkError",
    "AutologAttachError",
    "AutologDetachError",
    "AutologDoubleAttachError",
    # --- RLError subclasses ---
    "RLEnvIncompatibleError",
    "RLPolicyShapeMismatchError",
    "ReplayBufferUnderflowError",
    "RewardModelRequiredError",
    "FeatureNotYetSupportedError",
    # --- BackendError subclasses ---
    "UnsupportedPrecision",
    "UnsupportedFamily",
    # --- DriftMonitorError subclasses ---
    "ReferenceNotFoundError",
    "InsufficientSamplesError",
    "DriftThresholdError",
    # --- InferenceServerError subclasses ---
    "ModelLoadError",
    "InvalidInputSchemaError",
    "RateLimitExceededError",
    "TenantQuotaExceededError",
    "ShadowDivergenceError",
    "OnnxExportUnsupportedOpsError",
    # --- ModelRegistryError subclasses ---
    "ModelNotFoundError",
    "AliasOccupiedError",
    "CrossTenantLineageError",
    "ImmutableGoldenReferenceError",
    # --- FeatureStoreError subclasses ---
    "FeatureNotFoundError",
    "StaleFeatureError",
    "PointInTimeViolationError",
    # --- AutoMLError subclasses ---
    "BudgetExhaustedError",
    "InsufficientTrialsError",
    "EnsembleFailureError",
    # --- DiagnosticsError subclasses ---
    "DLDiagnosticsStateError",
    "ProtocolConformanceError",
    "SeedReportError",
    # --- DashboardError subclasses ---
    "UnknownTenantError",
    "AuthorizationError",
    "LiveStreamError",
    "RunNotFoundInDashboardError",
]


def fingerprint_classified_value(value: Any) -> str:
    """Return ``sha256:<8hex>`` fingerprint for a classified-payload value.

    Parity with ``dataflow.classification.event_payload.format_record_id_for_event``
    and the kailash-rs cross-SDK helper: 32 bits of entropy — sufficient for
    forensic correlation, insufficient for rainbow-table reversal against
    typical PK spaces. See ``rules/event-payload-classification.md`` §2 and
    ``specs/kailash-core-ml-integration.md §3.4``.

    ``None`` → ``None``; integers pass through as ``str(value)`` unchanged (an
    integer PK cannot leak PII by value alone). Everything else is encoded
    ``utf-8`` then SHA-256-hashed.
    """
    if value is None:
        return "sha256:none"
    if isinstance(value, (int, float)):
        return str(value)
    raw = str(value).encode("utf-8")
    return f"sha256:{hashlib.sha256(raw).hexdigest()[:8]}"


# --- Root --------------------------------------------------------------


class MLError(Exception):
    """Root of every typed exception raised by kailash-ml or any wave package.

    All subclasses accept a keyword-only constructor with a required
    ``reason`` and optional ``tenant_id`` / ``actor_id`` / ``resource_id``.
    Arbitrary additional context may be passed as keyword arguments and is
    stored on the ``context`` attribute. The string form is deterministic:
    it names the class plus each attribute that was supplied, suitable for
    log aggregation without leaking classified payload contents.

    Error messages MUST NOT echo raw classified field values. Where a
    classified value would appear, pass the fingerprinted form produced by
    :func:`fingerprint_classified_value`.
    """

    def __init__(
        self,
        *,
        reason: str,
        tenant_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        resource_id: Optional[str] = None,
        **context: Any,
    ) -> None:
        self.reason = reason
        self.tenant_id = tenant_id
        self.actor_id = actor_id
        self.resource_id = resource_id
        self.context: dict[str, Any] = dict(context)
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        parts = [f"reason={self.reason!r}"]
        if self.tenant_id is not None:
            parts.append(f"tenant_id={self.tenant_id!r}")
        if self.actor_id is not None:
            parts.append(f"actor_id={self.actor_id!r}")
        if self.resource_id is not None:
            parts.append(f"resource_id={self.resource_id!r}")
        for key in sorted(self.context):
            parts.append(f"{key}={self.context[key]!r}")
        return f"{type(self).__name__}({', '.join(parts)})"

    def __repr__(self) -> str:
        return self._format_message()


# --- 11 domain families ------------------------------------------------


class TrackingError(MLError):
    """Raised by ExperimentTracker / ExperimentRun / tracker storage / tracking migrations."""


class AutologError(MLError):
    """Raised by ``km.autolog()`` instrumentation paths."""


class RLError(MLError):
    """Raised by RL primitives (``ml.rl``, trajectory bridge, SB3 wrappers)."""


class BackendError(MLError, RuntimeError):
    """Raised by device-detection / backend-compat-matrix loading.

    Multi-inherits :class:`RuntimeError` so 0.x callers using
    ``except RuntimeError`` continue to catch. This is the only family that
    multi-inherits a builtin — the discipline from ``rules/security.md``
    § Multi-Site Kwarg Plumbing applies: any refactor that narrows the MRO
    must patch every call site in the same PR.
    """


class DriftMonitorError(MLError):
    """Raised by DriftMonitor (statistical drift tests, retraining trigger)."""


class InferenceServerError(MLError):
    """Raised by InferenceServer / ServeHandle / channel dispatchers."""


class ModelRegistryError(MLError):
    """Raised by ModelRegistry (register, promote, alias, lineage)."""


class FeatureStoreError(MLError):
    """Raised by FeatureStore (feature materialisation, point-in-time queries)."""


class AutoMLError(MLError):
    """Raised by AutoMLEngine (search, budget, ensembling)."""


class DiagnosticsError(MLError):
    """Raised by DL/RL/Agent Diagnostics."""


class DashboardError(MLError):
    """Raised by :class:`MLDashboard` CLI and ``km.dashboard()``."""


# --- Cross-cutting (direct children of MLError) ------------------------


class UnsupportedTrainerError(MLError):
    """Raised by ``MLEngine.fit()`` when a :class:`Trainable.fit` path
    bypasses :class:`L.Trainer` (Decision 8 — hard Lightning lock-in).
    Spans every domain so it inherits directly from :class:`MLError`."""


class MultiTenantOpError(MLError):
    """Raised by any primitive that performs a cross-tenant admin operation
    without PACT D/T/R clearance (Decision 12). Canonical home is
    ``kailash.ml.errors`` so ``ml-registry-pact.md`` (post-1.0) subclasses
    can depend on kailash-core alone."""


class MigrationFailedError(MLError):
    """Raised by ``kailash.tracking.migrations`` when a migration's
    ``apply()`` raises or ``verify()`` returns ``False``. See
    ``kailash-core-ml-integration.md §7``."""


class MigrationRequiredError(MLError):
    """Raised when an engine detects that a required schema object
    (table / column / index) is absent at first use, indicating the
    operator has not run the corresponding numbered migration.

    Distinct from :class:`MigrationFailedError` (which fires on a
    migration's own ``apply()`` failure) and from
    :class:`MigrationImportError` (which fires when a migration module
    cannot be loaded). This error fires from inside the engine's hot
    path when persistence is degraded because the schema is missing —
    the typed signal lets operators differentiate "schema missing,
    please run migrations" from "migration ran but crashed" from
    "migration module failed to import" without log triage.

    Per ``rules/schema-migration.md`` MUST Rule 1, application code
    MUST NOT emit ``CREATE TABLE`` DDL inline; raising this error is
    the correct fail-loud disposition when an engine encounters a
    missing schema. See ``specs/ml-automl.md §8A.2`` and
    ``specs/kailash-core-ml-integration.md §4`` for the migration
    framework contract.
    """


class WorkflowNodeMLContextError(MLError):
    """Raised by ``kailash.workflow.nodes.ml.*`` when an ML node cannot
    find an ambient tracker where one is required. See
    ``kailash-core-ml-integration.md §7``."""


class EnvVarDeprecatedError(MLError):
    """Raised when a legacy ML env var is read in strict mode (2.0
    future-removal contract per ``ml-engines-v2.md §2.1 MUST 1b``)."""


# --- TrackingError subclasses ------------------------------------------


class MetricValueError(TrackingError, ValueError):
    """Raised by ``log_metric`` / ``log_metrics`` when a metric value is
    NaN/Inf/non-finite.

    Multi-inherits :class:`ValueError` per Phase-B Round 2b §A.1 T-03
    SAFE-DEFAULT so ``except ValueError`` continues to catch the rejection.
    This is permitted by the cross-domain rule only because
    :class:`ValueError` is a builtin, not an :class:`MLError` domain family.
    """


class ParamValueError(TrackingError, ValueError):
    """Raised by ``log_param`` / ``log_params`` when a param value is
    NaN/Inf/non-finite. Mirrors :class:`MetricValueError` — same
    multi-inherit pattern, same justification."""


class ActorRequiredError(TrackingError):
    """Raised when ``require_actor=True`` and no actor_id could be resolved
    from explicit kwarg / contextvar / env (``ml-tracking.md §8.1``)."""


class TenantRequiredError(TrackingError):
    """Raised when a multi-tenant operation is invoked without a
    ``tenant_id``. Canonical home: TrackingError. Other domains re-raise
    from this module rather than declaring a sibling class."""


class RunNotFoundError(TrackingError):
    """Raised when a run_id does not exist in the tracker store or is not
    visible to the caller's tenant scope."""


class ExperimentNotFoundError(TrackingError):
    """Raised when an experiment name does not resolve."""


class TrackerStoreInitError(TrackingError):
    """Raised when ``ExperimentTracker.create()`` fails to initialise its
    storage driver (migration lock contention, schema probe failure)."""


class InvalidTenantIdError(TrackingError):
    """Raised when a supplied tenant_id fails validation (shape, length,
    forbidden characters)."""


class ModelSignatureRequiredError(TrackingError):
    """Raised when ``log_model`` is invoked without a signature and the
    tracker is configured to require signatures."""


class LineageRequiredError(TrackingError):
    """Raised when a mutation requires ``dataset_hash`` and none is
    available."""


class LineageNotImplementedError(TrackingError):
    """Raised by ``km.lineage(...)`` while the cross-engine LineageGraph
    surface is deferred.

    Per ``rules/zero-tolerance.md`` Rule 1b, the canonical lineage
    primitive (``ModelRegistry.build_lineage_graph`` + the lineage DDL
    + traversal walker described in ``ml-tracking.md §6.3 / §7.1``) is
    declared deferred to a later wave. ``km.lineage()`` MUST raise this
    typed error rather than return a hollow placeholder graph (Rule 2 —
    fake data is BLOCKED). The deferral disposition is tracked in the
    associated GitHub issue; the message field carries the issue link
    so callers can find the design sketch.

    The exception is a strict :class:`TrackingError` per the canonical
    hierarchy in ``ml-tracking.md §9.1``; callers catching
    :class:`TrackingError` (or :class:`MLError`) continue to handle the
    not-implemented surface uniformly with the rest of the lineage
    error family (:class:`LineageRequiredError`, :class:`CrossTenantLineageError`).
    """


class ArtifactEncryptionError(TrackingError):
    """Raised when an artifact write cannot satisfy the configured
    encryption policy."""


class ArtifactSizeExceededError(TrackingError):
    """Raised when an artifact exceeds the configured per-tenant size
    budget."""


class AliasNotFoundError(TrackingError):
    """Raised when an alias (e.g. ``@production``) is not set for the
    requested model/tenant. Canonical home: TrackingError (alias
    resolution is tracker-adjacent). Registry callers re-export the name
    via the module but do not declare a second class."""


class ErasureRefusedError(TrackingError):
    """Raised by ``delete_data_subject`` / ``km.erase_subject`` when the
    affected run is referenced by a production alias. Operator must clear
    the alias before retrying (``ml-tracking.md §8.4``)."""


class MigrationImportError(TrackingError):
    """Raised when a legacy store migration fails to import a row during
    0.x → 1.0 consolidation."""


# --- AutologError subclasses -------------------------------------------


class AutologNoAmbientRunError(AutologError):
    """Raised when a monkey-patched framework hook fires but no ambient
    :class:`ExperimentRun` is active. Silent-skip mode converts this to a
    DEBUG log line instead of raising."""


class AutologUnknownFrameworkError(AutologError):
    """Raised when ``km.autolog(flavor=X)`` is called with an unknown
    framework name."""


class AutologAttachError(AutologError):
    """Raised when a :class:`FrameworkIntegration.attach` call fails.

    The inner exception from the framework (Lightning, sklearn, etc.) is
    preserved as ``__cause__`` per ``specs/ml-autolog.md §7.1``. Callers
    can catch :class:`AutologError` to handle any attach failure, or
    ``AutologAttachError`` specifically.
    """


class AutologDetachError(AutologError):
    """Raised when a :class:`FrameworkIntegration.detach` call fails on
    ``__aexit__``.

    Per ``specs/ml-autolog.md §7.1``, ``AutologDetachError`` MUST NOT
    swallow the user's in-flight exception — it re-raises the user's
    exception with the detach failure attached as ``__context__``.
    Losing the user's stack is a ``rules/zero-tolerance.md`` Rule 3
    violation.
    """


class AutologDoubleAttachError(AutologError):
    """Raised when :meth:`FrameworkIntegration.attach` is invoked twice
    on the same integration instance without an intervening
    :meth:`FrameworkIntegration.detach`.

    Guards against the "two ``async with km.autolog()`` blocks nested"
    failure mode where the inner block's ``detach`` silently dismantles
    the outer block's hooks. See ``specs/ml-autolog.md §3.2``.
    """


# --- RLError subclasses ------------------------------------------------


class RLEnvIncompatibleError(RLError):
    """Raised when a Gymnasium env's observation/action spaces are
    incompatible with the requested algorithm preset."""


class RLPolicyShapeMismatchError(RLError):
    """Raised when a saved policy's tensor shapes do not match the env
    spaces at load time."""


class ReplayBufferUnderflowError(RLError):
    """Raised when an off-policy algorithm tries to sample from an empty
    or under-filled replay buffer."""


class RewardModelRequiredError(RLError):
    """Raised by RLHF paths when a reward model reference is missing."""


class FeatureNotYetSupportedError(RLError):
    """Raised by RL entry points for 1.1-deferred features (offline RL
    batch replay, curriculum schedulers) surfaced in the public API but
    not yet implemented."""


# --- BackendError subclasses -------------------------------------------


class UnsupportedPrecision(BackendError):
    """Raised when the requested precision is unsupported by the detected
    hardware (e.g. fp16 on Pascal, bf16 on a GPU lacking bf16 ALUs).
    Inherits :class:`BackendError` which already multi-inherits
    :class:`RuntimeError`."""


class UnsupportedFamily(BackendError):
    """Raised when an estimator family (xgboost-gpu on ROCm,
    lightgbm-gpu without the CUDA build, torchrl on TPU) cannot run on
    the detected backend. Message MUST include the backend name and an
    actionable install hint."""


# --- DriftMonitorError subclasses --------------------------------------


class ReferenceNotFoundError(DriftMonitorError):
    """Raised when a drift comparison requests a reference baseline that
    does not exist."""


class InsufficientSamplesError(DriftMonitorError):
    """Raised when a drift test receives fewer samples than the minimum
    required for statistical validity."""


class DriftThresholdError(DriftMonitorError):
    """Raised when a configured drift threshold is invalid (negative,
    NaN, above 1.0 for PSI)."""


class ZeroVarianceReferenceError(DriftMonitorError):
    """Raised when a reference column has ``std == 0``.

    Per ``specs/ml-drift.md §3.6 MUST 2``, a reference column with zero
    variance MUST raise rather than silently collapse to a single-bin
    histogram — that is a data-quality finding routed to the
    ``data_quality`` axis, not a drift finding. Error message identifies
    the column by name.
    """


class ModelLoadError(InferenceServerError):
    """Raised when an :class:`InferenceServer` cannot load a model
    artifact (file missing, version mismatch, deserialization error)."""


class InvalidInputSchemaError(InferenceServerError):
    """Raised when a predict request payload does not conform to the
    model's declared input signature."""


class RateLimitExceededError(InferenceServerError):
    """Raised by the rate limiter when a tenant exceeds its per-second
    request budget. Canonical home: InferenceServerError. Dashboard and
    other layers re-export the name only."""


class TenantQuotaExceededError(InferenceServerError):
    """Raised when a tenant exceeds its serving / registry / feature-store
    quota. Canonical home: InferenceServerError (quota checks appear
    first at serving); registry and feature-store layers re-export."""


class ShadowDivergenceError(InferenceServerError):
    """Raised when shadow-traffic divergence exceeds the configured
    threshold and the guard policy is set to fail."""


class OnnxExportUnsupportedOpsError(InferenceServerError):
    """Raised when an ONNX export encounters model ops that the target
    opset does not support. Surfaces at registration time so the user
    sees the failure before attempting to serve."""


# --- ModelRegistryError subclasses -------------------------------------


class ModelNotFoundError(ModelRegistryError):
    """Raised when a ``(tenant_id, name, version)`` tuple does not
    resolve."""


class AliasOccupiedError(ModelRegistryError):
    """Raised when ``set_alias`` targets an alias already bound to a
    different version and ``force=False``."""


class CrossTenantLineageError(ModelRegistryError):
    """Raised when lineage traversal would cross a tenant boundary. The
    registry MUST NOT leak cross-tenant parent references."""


class ImmutableGoldenReferenceError(ModelRegistryError):
    """Raised when a mutation targets a registration flagged
    ``is_golden=True`` (reference runs are immutable)."""


# --- FeatureStoreError subclasses --------------------------------------


class FeatureNotFoundError(FeatureStoreError):
    """Raised when a feature name does not resolve for the tenant."""


class StaleFeatureError(FeatureStoreError):
    """Raised when a materialisation is older than the staleness
    threshold configured for the feature group."""


class PointInTimeViolationError(FeatureStoreError):
    """Raised when a point-in-time query would leak future values into a
    training set."""


# --- AutoMLError subclasses --------------------------------------------


class BudgetExhaustedError(AutoMLError):
    """Raised when an AutoML search exhausts its microdollar budget
    before producing a viable candidate."""


class InsufficientTrialsError(AutoMLError):
    """Raised when a search strategy cannot complete the minimum trial
    count (e.g. halving requires ``>=2`` rungs)."""


class EnsembleFailureError(AutoMLError):
    """Raised when ensembling the top-k candidates fails (incompatible
    signatures, serialization error)."""


# --- DiagnosticsError subclasses ---------------------------------------


class DLDiagnosticsStateError(DiagnosticsError):
    """Raised by :class:`DLDiagnostics` when a hook fires outside the
    expected lifecycle (before setup, after teardown)."""


class ProtocolConformanceError(DiagnosticsError):
    """Raised when a diagnostic adapter fails
    ``isinstance(adapter, RLDiagnostic)`` / ``Diagnostic`` conformance
    checks. See ``kailash-core-ml-integration.md §7``."""


class SeedReportError(DiagnosticsError):
    """Raised by ``km.seed()`` when a subsystem cannot be seeded
    (missing optional dep, explicit subsystem request for absent
    framework)."""


# --- DashboardError subclasses -----------------------------------------


class UnknownTenantError(DashboardError):
    """Raised when a dashboard request references a tenant that is not
    visible to the caller."""


class AuthorizationError(DashboardError):
    """Raised when a dashboard caller lacks the required clearance."""


class LiveStreamError(DashboardError):
    """Raised by the live-stream ingest path when a websocket frame is
    malformed or the back-pressure budget is exceeded."""


class RunNotFoundInDashboardError(DashboardError):
    """Raised when a dashboard run lookup fails. Distinct from
    :class:`RunNotFoundError` because the dashboard may filter runs by
    authz before reaching the tracker."""
