# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""GDPR subject-erasure surface (``km.erase_subject``).

Implements ``specs/ml-tracking.md`` §8.4 Decision 2 — the forensic-safe
erasure path: every run, artifact, metric, param, tag, and model-version
row for the subject is DELETED, but the ``experiment_audit`` rows are
PRESERVED so the audit chain is never broken. A new audit row is
appended with ``action='erase'`` and the subject id fingerprinted via
:func:`fingerprint_classified_value` (``sha256:<8hex>``) — forensic
correlation without raw-PII leakage.

The erasure refuses (``ErasureRefusedError``) when any affected run is
referenced by a production alias per spec §9.1 (M5 registry integration
— today the check is a stub that never refuses since the model-alias
surface lands in W18; the hook is wired so the refusal path activates
the moment W18 ships, without a follow-up edit to this module).
"""
from __future__ import annotations

import logging
from typing import Optional

from kailash_ml.errors import (
    ErasureRefusedError,
    MultiTenantOpError,
    TenantRequiredError,
    fingerprint_classified_value,
)
from kailash_ml.tracking.runner import (
    SINGLE_TENANT_SENTINEL,
    _iso_utc,
    _resolve_actor_id,
    _resolve_store_path,
    _resolve_tenant_id,
)
from kailash_ml.tracking.storage import AbstractTrackerStore, SqliteTrackerStore

__all__ = ["erase_subject", "EraseResult"]

logger = logging.getLogger(__name__)


class EraseResult(dict):
    """Return shape of :func:`erase_subject`.

    Dict-typed for painless JSON serialisation. Keys:

    - ``tenant_id`` (str)
    - ``subject_fingerprint`` (str) — ``sha256:<8hex>``
    - ``runs`` (int) — affected run_ids
    - ``params`` / ``metrics`` / ``artifacts`` / ``tags`` / ``model_versions``
      / ``subjects`` (int) — rows deleted per resource
    - ``audit_preserved`` (bool) — always ``True``; present for explicit
      operator-facing confirmation.
    """


async def erase_subject(
    subject_id: str,
    *,
    tenant_id: Optional[str] = None,
    actor_id: Optional[str] = None,
    backend: Optional[AbstractTrackerStore] = None,
    store: Optional[str] = None,
    multi_tenant: bool = True,
) -> EraseResult:
    """Erase every run-scoped trace of ``subject_id`` for ``tenant_id``.

    Per spec §8.4:

    - Deletes ``experiment_metrics`` / ``experiment_artifacts`` /
      ``experiment_tags`` / ``experiment_model_versions`` /
      ``experiment_run_subjects`` rows for every run linked to
      ``subject_id`` under ``tenant_id``.
    - Nulls out ``experiment_runs.params`` on those runs (the run-row
      shell persists so audit cross-references still resolve).
    - Preserves every ``experiment_audit`` row unchanged and APPENDS a
      new row with ``action='erase'``, ``resource_kind='data_subject'``,
      ``resource_id=fingerprint_classified_value(subject_id)``, and
      ``new_state`` recording per-resource counts.

    Raises :class:`TenantRequiredError` when ``tenant_id`` is unresolved
    and ``multi_tenant`` defaults (``True``). Callers intentionally
    operating on the single-tenant dev sentinel MUST pass
    ``multi_tenant=False`` AND rely on the ``_single`` fallback, OR
    pass ``tenant_id=kailash_ml.tracking.SINGLE_TENANT_SENTINEL``
    explicitly.

    Raises :class:`ErasureRefusedError` if any affected run is currently
    referenced by a production alias (spec §8.4 cross-reference to §9.1).
    Spec alias-protection lands in W18; the hook is wired here so the
    refusal activates automatically when W18 ships.

    Raises :class:`MultiTenantOpError` when the caller supplies an empty
    ``subject_id`` — erasure with no subject is a destructive scan that
    the spec does not authorise.
    """
    if not subject_id or not str(subject_id).strip():
        raise MultiTenantOpError(reason="erase_subject requires a non-empty subject_id")

    # Tenant resolution follows the same priority chain as km.track() so
    # operators can scope erasure to the session tenant without plumbing.
    try:
        resolved_tenant = _resolve_tenant_id(tenant_id, multi_tenant=multi_tenant)
    except TenantRequiredError:
        # Re-raise with an erase-specific message so the stacktrace is
        # self-documenting — the operator reading the trace knows the
        # failure came from erase_subject, not from a background
        # km.track() call.
        raise TenantRequiredError(
            reason=(
                "erase_subject(multi_tenant=True) requires a tenant_id; "
                "pass tenant_id=... or set KAILASH_TENANT_ID "
                "(spec ml-tracking.md §7.2 rule 5)"
            )
        ) from None

    resolved_actor = _resolve_actor_id(actor_id) or "_unset"

    owns_backend = False
    if backend is None:
        backend = SqliteTrackerStore(_resolve_store_path(store))
        owns_backend = True
    # ``backend`` is non-None from here on — the type-checker cannot
    # infer that through the conditional construction above without a
    # local alias. Bind one so subsequent ``.erase_subject_content``
    # etc. resolve without ``Optional`` friction.
    active_backend: AbstractTrackerStore = backend

    fingerprint = fingerprint_classified_value(subject_id)

    try:
        # Alias-protection hook — spec §8.4 cross-references §9.1. The
        # W18 model-registry surface lands the real check; today we
        # ask the backend for an optional ``has_production_alias``
        # method and treat its absence as "no production aliases in
        # this backend". This preserves forward-compat without a
        # follow-up edit to the erasure module.
        _ = resolved_tenant, subject_id  # keep the hook symbol alive
        alias_check = getattr(active_backend, "has_production_alias_for_subject", None)
        if alias_check is not None:
            refused = await alias_check(
                tenant_id=resolved_tenant, subject_id=subject_id
            )
            if refused:
                raise ErasureRefusedError(
                    reason=(
                        "erase_subject refused: subject linked to a run "
                        "aliased as 'production'. Clear the alias first "
                        "(spec ml-tracking.md §8.4 / §9.1)."
                    ),
                    tenant_id=resolved_tenant,
                    resource_id=fingerprint,
                )

        # Hot-path erasure: the backend deletes the content rows and
        # returns per-resource counters. Audit rows are NEVER touched
        # here — the immutability triggers installed at migration
        # time would refuse any UPDATE/DELETE on `experiment_audit`
        # and we MUST preserve the trail per §8.4.
        counters = await active_backend.erase_subject_content(
            tenant_id=resolved_tenant, subject_id=subject_id
        )

        # Append the erasure audit row. Running AFTER the content
        # delete gives the row a deterministic sequence: any prior
        # audit row about the subject precedes this one in timestamp
        # order.
        writer = getattr(active_backend, "insert_audit_row", None)
        if writer is not None:
            import json as _json  # local import to avoid module-level churn

            await writer(
                tenant_id=resolved_tenant,
                actor_id=resolved_actor,
                timestamp=_iso_utc(),
                resource_kind="data_subject",
                resource_id=fingerprint,
                action="erase",
                prev_state=None,
                new_state=_json.dumps(counters, default=str),
            )
        logger.info(
            "tracking.erase_subject.ok",
            extra={
                "tenant_id": resolved_tenant,
                "subject_fingerprint": fingerprint,
                "runs_affected": counters.get("runs", 0),
            },
        )
    finally:
        if owns_backend and backend is not None:
            await backend.close()

    _ = SINGLE_TENANT_SENTINEL  # keep the cross-spec sentinel imported
    return EraseResult(
        tenant_id=resolved_tenant,
        subject_fingerprint=fingerprint,
        audit_preserved=True,
        **counters,
    )
