# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Pure-data provider NAME registry — zero provider-class imports.

This module carries ONLY declared literals: the canonical set of provider
NAMES and the model-name-prefix -> provider-family dispatch table. It imports
NO provider classes (``kaizen.providers.llm.*`` / ``kaizen.providers.base`` /
``kaizen.providers.registry``), so a pure-Prometheus consumer such as
``kaizen.production.metrics`` can bound its ``model``/``provider`` labels
against these names WITHOUT eager-loading every provider class transitively.

``kaizen.providers.registry`` imports the prefix map from here (single
source of truth) and builds the name -> CLASS ``PROVIDERS`` dict on top of it;
this module is the name-only half that has no class dependency.

The prefix dispatch is declared structural data (config-branching, permitted
by ``agent-reasoning.md`` exception 5), NOT semantic classification of user
intent — it is a pure string-prefix table extended by new providers, never a
keyword classifier taught to an LLM.
"""

from __future__ import annotations

# Canonical observability CLASSIFICATION vocabulary — the full set of provider
# family NAMES ``kaizen.production.metrics`` bounds its Prometheus ``provider``
# label against (``_bound_provider_label``). This is a SUPERSET of the runtime
# ``kaizen.providers.registry.PROVIDERS`` name set: since #1720 Wave-2 the legacy
# chat providers (openai / anthropic / google / ollama / docker / perplexity /
# mock) are served by the four-axis ``LlmClient`` rather than the registry, but
# their calls still flow through ``track_llm_usage`` and MUST keep labelling to
# their own family (never collapsing to ``_other``). registry.py therefore
# asserts ``set(PROVIDERS.keys()) <= PROVIDER_NAMES`` (subset) as its drift
# tripwire — every registry provider is a known family, not the reverse.
PROVIDER_NAMES: frozenset[str] = frozenset(
    {
        "ollama",
        "openai",
        "anthropic",
        "cohere",
        "huggingface",
        "mock",
        "azure",
        "azure_openai",
        "azure_ai_foundry",
        "docker",
        "google",
        "gemini",
        "perplexity",
        "pplx",
    }
)


# SPEC-02 §3.1 — model-id prefix -> family CLASSIFICATION table.
#
# This is a declared structural mapping, NOT a classification of user intent.
# Every tuple on the left is a set of model-id prefixes owned by the family on
# the right. Since #1720 Wave-2 its sole consumer is
# ``kaizen.production.metrics._bound_model_label`` (Prometheus model-family
# label bounding) — model->wire DISPATCH now lives in
# ``kaizen.llm.deployment_resolver`` and ``get_provider_for_model`` is retired
# (raises). The table stays complete so a four-axis ``gpt-*`` / ``claude-*`` /
# ``gemini-*`` call still labels to its family. New families extend this table;
# the scan has no keyword reasoning.
MODEL_PREFIX_MAP: tuple[tuple[tuple[str, ...], str], ...] = (
    (("gpt-", "o1-", "o3-", "o4-", "o1", "o3", "o4-mini", "ft:gpt"), "openai"),
    (("claude-",), "anthropic"),
    (("gemini-",), "google"),
    (
        (
            "llama",
            "mistral",
            "mixtral",
            "qwen",
            "phi-",
            "phi3",
            "phi4",
            "codellama",
            "deepseek",
        ),
        "ollama",
    ),
    (("ai/",), "docker"),
    (
        (
            "sonar",
            "sonar-",
        ),
        "perplexity",
    ),
    (("mock-", "mock"), "mock"),
)

# Backward-compatible alias for the underscore name used by
# ``kaizen.providers.registry`` (and its unit tests) before the extraction.
_MODEL_PREFIX_MAP = MODEL_PREFIX_MAP
