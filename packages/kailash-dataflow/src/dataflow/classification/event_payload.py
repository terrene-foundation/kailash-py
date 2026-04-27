# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Event-payload classification helpers.

The ``DomainEvent`` surface is strictly wider than the log surface — every
subscriber, every tracing span, every third-party observability vendor, and
every downstream service sees event payloads. A classified field value that
leaks into an event payload is strictly harder to recall than one in a log
aggregator.

The log-surface rule (``rules/observability.md`` Rule 8) says schema-revealing
field names must be DEBUG-only or hashed. The event-surface rule is stricter:
filter or hash, never merely level-gate — events have no level.

This module exposes the single helper required for event-safe PK emission:
``format_record_id_for_event``. Callers pass the model name and the raw PK
value (typically sourced from a write result or caller input); the helper
returns:

* ``None``                              — when the caller passed ``None``
* ``str(value)``                         — integer / float PKs (safe by type;
  non-enumerable)
* ``str(value)``                         — unclassified string PKs (no leak)
* ``"sha256:XXXXXXXX"``                  — classified string PKs (8 hex chars,
  irreversible but still grep-able for forensic correlation across logs +
  events + DB audit trail)

Cross-SDK: this mirrors the kailash-rs v3.17.1 ``format_record_id_for_event``
helper (BP-048). The hash shape and prefix are intentionally identical
across SDKs so a log line emitted by one service and an event handled by a
Python subscriber in another service correlate on the same ``sha256:XXXX``
fingerprint.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Mapping, Optional

from dataflow.classification.policy import ClassificationPolicy

__all__ = ["format_record_id_for_event", "format_error_for_event"]


# Length of the hex prefix kept. 8 hex chars = 32 bits of entropy, sufficient
# for forensic correlation in event/log streams without making the full PK
# reversible by rainbow table.
_HASH_HEX_PREFIX = 8

# Sentinel inserted in place of any classified value scrubbed from an error
# string before emission. Uniform with the read-classification redaction
# sentinel (``apply_read_classification`` writes ``"[REDACTED]"``) so log /
# event / mutation-return audit trails grep cleanly through one token.
_ERROR_REDACTED_SENTINEL = "[REDACTED]"

# Minimum length for a classified value to be eligible for scrubbing. Single
# characters and 2-char tokens collide with common substrings of error
# messages (``"a"``, ``"id"``, ``"or"``); over-redacting them shreds the
# error string into unreadable noise without improving safety. The threshold
# matches kailash-rs ``format_error_for_event`` for cross-SDK parity.
_MIN_SCRUB_LEN = 3

logger = logging.getLogger(__name__)


def format_record_id_for_event(
    policy: Optional[ClassificationPolicy],
    model_name: str,
    record_id: Any,
    pk_field: str = "id",
) -> Optional[str]:
    """Return a loggable ``record_id`` for event payloads.

    Args:
        policy: The ``ClassificationPolicy`` to consult. ``None`` means no
            classifications are registered on this DataFlow instance — the
            helper passes values through as strings (safe; no policy means
            no classified PKs exist).
        model_name: Model name (e.g. ``"User"``).
        record_id: The raw PK value from the write result or caller input.
        pk_field: The PK field name on the model. Kailash DataFlow convention
            is ``"id"`` (see ``rules/patterns.md`` § DataFlow Models); caller
            can override for non-standard schemas.

    Returns:
        ``None``                            — if ``record_id is None``
        ``str(record_id)``                  — for integer/float PKs (safe)
        ``str(record_id)``                  — for unclassified string PKs
        ``"sha256:XXXXXXXX"``               — for classified string PKs
    """
    if record_id is None:
        return None

    # Integers and floats are safe — the PK space isn't classified data in
    # itself, and an integer PK can't accidentally leak an email / SSN / etc.
    if isinstance(record_id, (int, float)):
        return str(record_id)

    # String PK: consult the policy. If no policy OR this field isn't
    # classified, the value is safe to pass through.
    if policy is None:
        return str(record_id)

    field_classification = policy.get_field(model_name, pk_field)
    if field_classification is None:
        return str(record_id)

    # Classified string PK — hash it. SHA-256 is the cross-SDK choice
    # (matches kailash-rs); the 8-char prefix is enough entropy for
    # forensic correlation without being reversible.
    raw = str(record_id).encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()[:_HASH_HEX_PREFIX]
    return f"sha256:{digest}"


def format_error_for_event(
    policy: Optional[ClassificationPolicy],
    error_str: Optional[str],
    *,
    model_name: Optional[str] = None,
    known_field_values: Optional[Mapping[str, Any]] = None,
) -> Optional[str]:
    """Redact classified field values from an error string.

    Per ``rules/event-payload-classification.md`` § 1: emitter-level
    structural redaction. The caller may safely pass ``str(exc)`` even
    when the exception string interpolates row data (e.g. PostgreSQL's
    ``DETAIL: Failing row contains (alice@tenant.example, hunter2)``);
    this helper substitutes any value the policy classifies with the
    sentinel ``"[REDACTED]"`` before the string is published to the
    bus.

    The helper is the single filter point for the error surface — every
    emit-helper that accepts an ``error: Optional[str]`` argument MUST
    route through here so a future refactor of the policy / sentinel
    contract lands in one place rather than per-call-site.

    Args:
        policy: The active ``ClassificationPolicy`` (typically
            ``getattr(db, "_classification_policy", None)``). ``None``
            means no classifications are registered — the helper passes
            ``error_str`` through unchanged.
        error_str: The raw error message; ``None`` returns ``None``;
            empty / whitespace-only returns the input unchanged (no
            classified value can hide in zero bytes).
        model_name: Optional model name to scope the classified-field
            scan. When supplied, only fields registered under this
            model are considered for scrubbing. When ``None``, every
            classified field across every registered model is in
            scope — useful for ML training paths where the error may
            originate in any feature column.
        known_field_values: Optional ``{field_name: value}`` mapping
            providing the concrete values the caller knows are present
            in the error context (e.g. the row dict that was being
            written when the exception fired). When supplied, the
            helper scans for these values verbatim. When ``None``, the
            helper falls back to scanning the error string for any
            classified field NAME — this catches DB error messages
            that interpolate column names (``column "ssn" violates
            ...``) but cannot scrub raw VALUES the caller never told
            us about.

    Returns:
        ``None``                 — when ``error_str`` is ``None``
        unchanged ``error_str``  — when no classified content is found
                                    OR the policy is ``None``
        scrubbed ``error_str``   — with classified values / names
                                    replaced by ``"[REDACTED]"``

    Cross-SDK: mirrors the kailash-rs ``format_error_for_event``
    helper. Sentinel and minimum-scrub-length match so scrubbed
    payloads are byte-identical for the same input across SDKs.
    """
    if error_str is None:
        return None
    if not error_str or not error_str.strip():
        return error_str
    if policy is None:
        return error_str

    # Build the candidate set: classified field VALUES (when caller
    # supplied them) plus classified field NAMES (always — DB errors
    # interpolate column names with no ceremony).
    redacted = error_str

    # Step 1: scrub known classified VALUES. This is the strict-safety
    # half — any value the caller flagged as classified is guaranteed
    # gone from the emitted error.
    if known_field_values:
        for field_name, value in known_field_values.items():
            if value is None:
                continue
            # Only scrub when the field is classified under the policy.
            # If model_name is None, treat ANY classification across
            # ANY registered model as a hit — the ML path doesn't bind
            # to a single model_name at emit time.
            if not _is_field_classified(policy, model_name, field_name):
                continue
            value_str = str(value)
            if len(value_str) < _MIN_SCRUB_LEN:
                continue
            if value_str in redacted:
                redacted = redacted.replace(value_str, _ERROR_REDACTED_SENTINEL)
                logger.debug(
                    "event_payload.error_value_redacted",
                    extra={
                        "model_name": model_name,
                        "field_name": field_name,
                    },
                )

    # Step 2: scrub classified field NAMES that appear verbatim in the
    # error string. DB-engine errors routinely leak schema-revealing
    # column names (`column "ssn" violates check constraint`); per
    # ``rules/observability.md`` Rule 8, classified field names are
    # schema-level sensitive themselves.
    for candidate_name in _classified_field_names(policy, model_name):
        if len(candidate_name) < _MIN_SCRUB_LEN:
            continue
        if candidate_name in redacted:
            redacted = redacted.replace(candidate_name, _ERROR_REDACTED_SENTINEL)
            logger.debug(
                "event_payload.error_fieldname_redacted",
                extra={"model_name": model_name},
            )

    return redacted


def _is_field_classified(
    policy: ClassificationPolicy,
    model_name: Optional[str],
    field_name: str,
) -> bool:
    """Return True if the named field is classified under the policy.

    When ``model_name`` is ``None``, returns True if the field is
    classified under ANY registered model. This supports the ML
    training surface where the active model name is not known at
    emit time.
    """
    if model_name is not None:
        return policy.get_field(model_name, field_name) is not None
    # Scan every registered model.
    # ``_registry`` is the canonical store; access via the lock-aware
    # ``get_model_fields`` API to avoid touching internals directly.
    # We iterate the full registry — small (one entry per registered
    # model) and only invoked on emit-error paths.
    registry = getattr(policy, "_registry", {})
    for model in list(registry.keys()):
        if policy.get_field(model, field_name) is not None:
            return True
    return False


def _classified_field_names(
    policy: ClassificationPolicy,
    model_name: Optional[str],
) -> "list[str]":
    """Return the set of classified field NAMES to scan for in errors.

    Scoped to ``model_name`` when supplied; otherwise spans every
    registered model.
    """
    if model_name is not None:
        return list(policy.get_model_fields(model_name).keys())
    registry = getattr(policy, "_registry", {})
    names: list[str] = []
    for model in list(registry.keys()):
        names.extend(policy.get_model_fields(model).keys())
    # De-duplicate while preserving order.
    seen: set[str] = set()
    deduped: list[str] = []
    for name in names:
        if name not in seen:
            seen.add(name)
            deduped.append(name)
    return deduped
