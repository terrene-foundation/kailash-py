# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Reasoning-model sampling-param filter for OpenAI o1/o3/gpt-5 (#1720 Wave-1b).

The four-axis ``openai_chat`` wire shaper (``build_request_payload``) only
switches the token-limit field NAME (``max_tokens`` vs
``max_completion_tokens``) by model family — it does NOT drop sampling
params OpenAI's reasoning models reject outright. A caller passing
``temperature`` to an o1/o3 model takes a live HTTP 400
(``"temperature" is not supported with this model``); gpt-5 REQUIRES
``temperature=1.0`` and 400s on anything else.

This module ports the equivalent per-instance helpers from the legacy
``kaizen.providers.llm.openai.OpenAIProvider``
(``_is_reasoning_model`` / ``_requires_temperature_1`` /
``_filter_reasoning_model_params``, see
``src/kaizen/providers/llm/openai.py``) to module-level, provider-agnostic
functions so the four-axis wire layer can reuse the exact same filtering
behavior without depending on the legacy provider class.

Model-family matching is on a documented PREFIX (``o1`` / ``o3`` / ``gpt-5``),
not a full hardcoded model id — this is the ``rules/env-models.md`` carve-out
for provider-API constraints (OpenAI's own reasoning-model naming scheme),
not a hardcoded-model violation. Unknown / unmatched models are left
untouched (byte-neutral passthrough).
"""

from __future__ import annotations

import re
from typing import Any, Dict

# Reasoning models that DON'T support `temperature` at all (o1, o3, o4
# families). `^o4` added at /redteam Round-1 (#1720 Wave-1b) — o4-mini is an
# o-series reasoning model (see `openai_chat._MAX_COMPLETION_TOKENS_MODEL_PREFIXES
# = ("gpt-5", "o1", "o3", "o4")`) that rejects `temperature`/`top_p` outright
# just like o1/o3; the original `_REASONING_MODEL_PATTERNS` (ported from the
# legacy per-instance helper) omitted it, so every o4-mini call carrying a
# caller-set `temperature` took a live HTTP 400.
_REASONING_MODEL_PATTERNS = [
    r"^o1",
    r"^o3",
    r"^o4",
]

# Models that REQUIRE `temperature=1.0` (GPT-5 family).
# Ported verbatim from `OpenAIProvider._TEMPERATURE_1_ONLY_PATTERNS`.
_TEMPERATURE_1_ONLY_PATTERNS = [
    r"^gpt-?5",
]


def is_reasoning_model(model: str) -> bool:
    """True for OpenAI's o1/o3 reasoning-model family.

    These models reject `temperature` / `top_p` / `frequency_penalty` /
    `presence_penalty` outright (HTTP 400) — they do not clamp or ignore the
    values, they refuse the request.
    """
    if not model:
        return False
    model_lower = model.lower()
    return any(
        re.search(pattern, model_lower, re.IGNORECASE)
        for pattern in _REASONING_MODEL_PATTERNS
    )


def requires_temperature_1(model: str) -> bool:
    """True for OpenAI's gpt-5 family, which requires `temperature=1.0`.

    Unlike o1/o3, gpt-5 does not reject `temperature` outright — it rejects
    any value OTHER than 1.0. `top_p` / `frequency_penalty` /
    `presence_penalty` are still unsupported and dropped.
    """
    if not model:
        return False
    model_lower = model.lower()
    return any(
        re.search(pattern, model_lower, re.IGNORECASE)
        for pattern in _TEMPERATURE_1_ONLY_PATTERNS
    )


def filter_reasoning_model_params(model: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Drop/force sampling params a reasoning-model family cannot accept.

    * **gpt-5 family** (`requires_temperature_1`): drops `top_p` /
      `frequency_penalty` / `presence_penalty` when present, and FORCES
      `temperature` to `1.0` unconditionally (even when the caller never set
      `temperature` — gpt-5 400s on the server-side default too).
    * **o1/o3 family** (`is_reasoning_model`): drops `temperature` / `top_p`
      / `frequency_penalty` / `presence_penalty` when present. Nothing is
      added — the model simply does not accept these keys.
    * **Any other model**: `params` is returned as a shallow COPY, unchanged
      — the byte-neutral passthrough case. Ported behavior from the legacy
      `OpenAIProvider._filter_reasoning_model_params` (see
      `src/kaizen/providers/llm/openai.py`), which also returns the input
      unmodified for non-reasoning models.

    `params` itself is never mutated — every branch returns a new dict.
    """
    if requires_temperature_1(model):
        filtered = dict(params)
        for key in ("top_p", "frequency_penalty", "presence_penalty"):
            filtered.pop(key, None)
        filtered["temperature"] = 1.0
        return filtered

    if not is_reasoning_model(model):
        return dict(params)

    filtered = dict(params)
    for key in ("temperature", "top_p", "frequency_penalty", "presence_penalty"):
        filtered.pop(key, None)
    return filtered


__all__ = [
    "is_reasoning_model",
    "requires_temperature_1",
    "filter_reasoning_model_params",
]
