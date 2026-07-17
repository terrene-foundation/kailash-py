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

# Canonical set of provider NAMES. MUST stay consistent with the keys of
# ``kaizen.providers.registry.PROVIDERS`` (the name -> class dict); that module
# asserts equality at load as a drift tripwire.
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


# SPEC-02 §3.1 — model-name prefix dispatch.
#
# This is a declared structural mapping, NOT a classification of user intent.
# Every tuple on the left is a set of model-id prefixes owned by the provider
# on the right. New providers extend this table; the resolver's prefix scan
# has no keyword reasoning.
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
