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
        "cohere",
        "huggingface",
        "azure",
        "azure_openai",
        "azure_ai_foundry",
    }
)


# SPEC-02 §3.1 — model-name prefix dispatch.
#
# This is a declared structural mapping, NOT a classification of user intent.
# Every tuple on the left is a set of model-id prefixes owned by the provider
# on the right. New providers extend this table; the resolver's prefix scan
# has no keyword reasoning.
#
# #1720 Wave-2: the legacy chat providers (openai / anthropic / google / ollama
# / docker / perplexity / mock) were retired onto the four-axis LlmClient, whose
# ``kaizen.llm.deployment_resolver`` owns model-id -> wire dispatch. Their prefix
# rows were removed with them. The registry's remaining providers (cohere /
# huggingface embeddings, unified azure, azure_ai_foundry) resolve by explicit
# provider NAME, not model-id prefix, so this table is intentionally empty —
# ``get_provider_for_model`` now raises UnknownProviderError for every model,
# which is the retired-registry contract.
MODEL_PREFIX_MAP: tuple[tuple[tuple[str, ...], str], ...] = ()

# Backward-compatible alias for the underscore name used by
# ``kaizen.providers.registry`` (and its unit tests) before the extraction.
_MODEL_PREFIX_MAP = MODEL_PREFIX_MAP
