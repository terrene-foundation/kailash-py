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
from typing import Any, Optional

from dataflow.classification.policy import ClassificationPolicy

__all__ = ["format_record_id_for_event"]


# Length of the hex prefix kept. 8 hex chars = 32 bits of entropy, sufficient
# for forensic correlation in event/log streams without making the full PK
# reversible by rainbow table.
_HASH_HEX_PREFIX = 8


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
