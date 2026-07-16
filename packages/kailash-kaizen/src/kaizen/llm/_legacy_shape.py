# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#1720 Wave-2 — legacy/four-axis response shape reconciliation.

Pure, side-effect-free helpers used by the dual-run shadow validation in
``kaizen.nodes.ai.llm_agent.LLMAgentNode._provider_llm_response``. Neither
function performs I/O, logging, or raises on malformed input — they are
defensive on missing/None keys so the shadow path (which must NEVER affect
the live response) can call them unconditionally.

Two shapes are reconciled:

* **Legacy** (``kaizen.providers.*`` ``chat()`` return value):
  ``{content, tool_calls, finish_reason, usage: {prompt_tokens,
  completion_tokens, total_tokens}, model, ...}``.
* **Four-axis** (``kaizen.llm.client.LlmClient.complete()`` return value):
  ``{text, tool_calls?, stop_reason, usage: {input_tokens, output_tokens,
  total_tokens}, model}``.

``to_legacy_shape`` maps a four-axis result onto legacy field names so the
two can be diffed field-by-field with ``diff_legacy_vs_fouraxis``. Neither
function is ever fed back into the live response — the shadow path exists
purely to compare, log, and discard.

Per ``rules/observability.md`` § 8 and this Wave's governance, divergence
descriptions returned by ``diff_legacy_vs_fouraxis`` MUST NOT embed raw
generated text, tool-call arguments, or any secret — only field names,
booleans, lengths, and counts.
"""

from __future__ import annotations

from typing import Any, Dict, List


def to_legacy_shape(four_axis: Dict[str, Any]) -> Dict[str, Any]:
    """Map an ``LlmClient.complete()`` result onto legacy response field names.

    Defensive on a non-dict / partially-populated input — every read goes
    through ``.get()`` with a safe default. ``total_tokens`` is computed
    from the coerced input/output counts when the four-axis usage dict
    omits it (mirrors the existing coercion in ``_provider_llm_response``
    for the live legacy path, issue #487).
    """
    if not isinstance(four_axis, dict):
        four_axis = {}

    usage_in = four_axis.get("usage")
    if not isinstance(usage_in, dict):
        usage_in = {}

    prompt_tokens = usage_in.get("input_tokens")
    completion_tokens = usage_in.get("output_tokens")
    total_tokens = usage_in.get("total_tokens")
    if total_tokens is None:
        total_tokens = (prompt_tokens or 0) + (completion_tokens or 0)

    legacy: Dict[str, Any] = {
        "content": four_axis.get("text"),
        "finish_reason": four_axis.get("stop_reason"),
        "model": four_axis.get("model"),
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        },
    }
    # tool_calls is passed through verbatim ONLY when the four-axis result
    # carries it — mirrors the legacy shape's optional key, never fabricated.
    if "tool_calls" in four_axis:
        legacy["tool_calls"] = four_axis.get("tool_calls")

    return legacy


def _safe_text_repr(value: Any) -> str:
    """Normalize a text-shaped value for equality comparison.

    Used ONLY to detect a mismatch and to report its length — the returned
    string itself is never embedded in a divergence description (governance:
    no raw generated content in log output).
    """
    if isinstance(value, str):
        return value
    # Non-string content (e.g. a provider SDK object) — coerce defensively.
    try:
        return str(value)
    except Exception:
        return repr(value)


def _safe_len(value: Any) -> int:
    """Return ``len(value)`` for a list-shaped value, tolerating non-lists."""
    try:
        return len(value)
    except TypeError:
        return 1 if value else 0


def diff_legacy_vs_fouraxis(
    legacy: Dict[str, Any], mapped_fouraxis: Dict[str, Any]
) -> List[str]:
    """Return field-level divergence descriptions between the two shapes.

    Empty list == parity. Every description names the FIELD plus a
    boolean/length/count-level mismatch signal — never the raw generated
    text, tool-call arguments, or any credential (``rules/observability.md``
    § 8; this Wave's governance). Defensive on non-dict input.
    """
    if not isinstance(legacy, dict):
        legacy = {}
    if not isinstance(mapped_fouraxis, dict):
        mapped_fouraxis = {}

    divergences: List[str] = []

    # --- content -----------------------------------------------------
    # Equality is checked on the normalized text (never printed); the
    # divergence string reports only presence + length, per governance
    # (no raw generated content in log output).
    legacy_content = legacy.get("content")
    mapped_content = mapped_fouraxis.get("content")
    legacy_is_none = legacy_content is None
    mapped_is_none = mapped_content is None
    legacy_text = "" if legacy_is_none else _safe_text_repr(legacy_content)
    mapped_text = "" if mapped_is_none else _safe_text_repr(mapped_content)
    if legacy_is_none != mapped_is_none or legacy_text != mapped_text:
        divergences.append(
            "content: text mismatch "
            f"(legacy_present={not legacy_is_none}, legacy_len={len(legacy_text)}, "
            f"four_axis_present={not mapped_is_none}, four_axis_len={len(mapped_text)})"
        )

    # --- tool_calls ----------------------------------------------------
    legacy_tool_calls = legacy.get("tool_calls")
    mapped_tool_calls = mapped_fouraxis.get("tool_calls")
    legacy_has_tools = bool(legacy_tool_calls)
    mapped_has_tools = bool(mapped_tool_calls)
    if legacy_has_tools != mapped_has_tools:
        divergences.append(
            "tool_calls: presence mismatch "
            f"(legacy_present={legacy_has_tools}, four_axis_present={mapped_has_tools})"
        )
    elif legacy_has_tools and mapped_has_tools:
        legacy_count = _safe_len(legacy_tool_calls)
        mapped_count = _safe_len(mapped_tool_calls)
        if legacy_count != mapped_count:
            divergences.append(
                "tool_calls: count mismatch "
                f"(legacy_count={legacy_count}, four_axis_count={mapped_count})"
            )

    # --- finish_reason ---------------------------------------------------
    if legacy.get("finish_reason") != mapped_fouraxis.get("finish_reason"):
        divergences.append("finish_reason: value mismatch")

    # --- usage / token counts --------------------------------------------
    legacy_usage = legacy.get("usage")
    if not isinstance(legacy_usage, dict):
        legacy_usage = {}
    mapped_usage = mapped_fouraxis.get("usage")
    if not isinstance(mapped_usage, dict):
        mapped_usage = {}

    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        legacy_value = legacy_usage.get(key)
        mapped_value = mapped_usage.get(key)
        if legacy_value != mapped_value:
            divergences.append(
                f"usage.{key}: count mismatch "
                f"(legacy={legacy_value!r}, four_axis={mapped_value!r})"
            )

    return divergences


__all__ = ["to_legacy_shape", "diff_legacy_vs_fouraxis"]
