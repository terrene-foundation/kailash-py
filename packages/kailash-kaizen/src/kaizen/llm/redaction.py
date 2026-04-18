# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Classification-aware prompt redaction (§6.5).

LLM prompts are user-controlled text that routinely carries PII -- a
completion request containing `{"role": "user", "content": "my email is
alice@example.com"}` has exactly the same classification surface as a
DataFlow row with `@classify("email", PII)`. Shipping the raw prompt to
an external provider is a cross-boundary data movement; the
classification layer MUST apply before the wire adapter emits anything.

# Scope

This module exposes the single helper every wire adapter calls before
serializing a `CompletionRequest`:

    from kaizen.llm.redaction import redact_messages

    redacted = redact_messages(
        request_messages=req.messages,
        policy=policy,
        model_name="ChatTurn",
        caller_clearance=clearance,
    )

`policy` is a DataFlow `ClassificationPolicy` (duck-typed via the
`apply_masking_to_record` method). If no policy is installed on the
`LlmClient`, `redact_messages` is a no-op -- the wire adapter ships
messages unchanged.

# Contract

* `request_messages` is a list of dicts with `role` / `content` / and
  arbitrary extra keys. Each dict is treated as a record keyed by the
  caller-supplied `model_name`.
* `policy.apply_masking_to_record(model_name, record, caller_clearance)`
  mutates a copy -- we never mutate the caller's list.
* Return value is a NEW list of dicts -- the input list is never
  rewritten in place, because the caller may retain a reference for
  audit / retry logic that expects the raw content.

# Cross-SDK parity

The `redact_messages` contract is semantic-match with the Rust
`llm::redaction::redact_messages` function. Field names on the resulting
message dicts are byte-identical so log aggregators can join prompts
across SDKs.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, List, Mapping, Optional

logger = logging.getLogger(__name__)


def redact_messages(
    *,
    request_messages: Iterable[Mapping[str, Any]],
    policy: Optional[Any] = None,
    model_name: str = "LlmPromptMessage",
    caller_clearance: Optional[Any] = None,
) -> List[dict]:
    """Apply classification masking to every message in a completion request.

    Returns a NEW list of dicts; the input is not mutated. When `policy`
    is None (no classification installed) the function is a pure copy:
    the caller's messages pass through unchanged.

    Observability: emits a DEBUG log line per masked field count (not
    per field name -- schema-revealing field names stay at DEBUG per
    `rules/observability.md` § 8).
    """
    copied: List[dict] = [dict(m) for m in request_messages]
    if policy is None:
        return copied
    apply = getattr(policy, "apply_masking_to_record", None)
    if apply is None or not callable(apply):
        # Policy doesn't expose the expected hook -- pass through with
        # a WARN so the operator sees that the redaction path was
        # installed but inert.
        logger.warning(
            "llm.redaction.policy_missing_apply_masking_to_record",
            extra={
                "policy_class": type(policy).__name__,
            },
        )
        return copied
    masked: List[dict] = []
    masked_fields_total = 0
    for record in copied:
        result = apply(model_name, record, caller_clearance)
        # The DataFlow apply_masking_to_record may return the same dict
        # (non-dict short-circuit) or a new dict. Normalise to dict.
        if not isinstance(result, dict):
            masked.append(record)
            continue
        # Count masked fields by comparing against the input record.
        for k, v in result.items():
            if k in record and record[k] != v:
                masked_fields_total += 1
        masked.append(result)
    if masked_fields_total > 0:
        logger.debug(
            "llm.redaction.applied",
            extra={
                "model_name": model_name,
                "masked_field_count": masked_fields_total,
                "message_count": len(masked),
            },
        )
    return masked


__all__ = ["redact_messages"]
