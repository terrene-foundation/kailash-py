# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression pins for #1720 Wave B2b — pure-data provider NAME registry.

Wave B2b extracted the provider NAME set and the model-prefix dispatch table
off ``kaizen.providers.registry`` (which eager-loads every provider CLASS) into
a pure-data module ``kaizen.providers.provider_names``, so that
``kaizen.production.metrics`` — a pure-Prometheus module — bounds its
``model``/``provider`` labels against the pure-data names WITHOUT its OWN source
importing ``kaizen.providers.registry`` (and hence without SOURCE-level coupling
to the provider classes).

These tests pin the invariants the extraction actually guarantees:

(a) ``PROVIDER_NAMES`` stays consistent with the ``PROVIDERS`` class-map keys
    (the drift tripwire the extraction depends on).
(b) ``MODEL_PREFIX_MAP`` still maps the known family prefixes it always did.
(c) SOURCE-LEVEL zero-coupling — AST-parse the two touched files and assert
    (i) ``provider_names.py`` imports NOTHING from ``kaizen.providers.llm.*`` /
        ``kaizen.providers.base`` / ``kaizen.providers.registry`` (pure
        literals — the CRITICAL requirement), AND
    (ii) ``metrics.py`` no longer imports ``kaizen.providers.registry`` at all.
    Plus an in-process check that ``provider_names`` exposes no provider class.
(d) ``metrics``'s label-bounding functions behave identically post-extraction.

RUNTIME ``sys.modules`` decoupling (asserting ``kaizen.providers.registry`` is
absent after importing ``metrics``/``provider_names`` in a fresh subprocess) is
DELIBERATELY NOT asserted here: it is NOT achievable by this extraction, because
the ROOT package ``kaizen/__init__.py`` eager-imports ``kaizen.nodes.ai``, whose
``__init__`` eager-imports ``kaizen.providers.registry`` + ``llm.openai`` — so
``import kaizen`` (which precedes ANY ``kaizen.*`` import) already loads the
registry regardless of this module's imports. Achieving the runtime decoupling
requires lazifying ``kaizen/__init__.py`` (the whole top-level public API), a
separate, far larger change. This test pins the source-level contract the
extraction owns; the runtime-graph blocker is a distinct concern surfaced to the
plan.

All offline — no network, no model calls.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.regression


# ---------------------------------------------------------------------------
# (a) PROVIDER_NAMES stays consistent with the PROVIDERS class-map keys.
# ---------------------------------------------------------------------------
def test_provider_names_matches_registry_provider_keys():
    """The pure-data name set equals the resolver's name -> class dict keys."""
    from kaizen.providers.provider_names import PROVIDER_NAMES
    from kaizen.providers.registry import PROVIDERS

    assert PROVIDER_NAMES == set(PROVIDERS.keys())


def test_provider_names_is_the_expected_fourteen():
    """Pin the exact 14-name set so an accidental add/drop fails loudly."""
    from kaizen.providers.provider_names import PROVIDER_NAMES

    assert PROVIDER_NAMES == frozenset(
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
    assert len(PROVIDER_NAMES) == 14


# ---------------------------------------------------------------------------
# (b) MODEL_PREFIX_MAP still maps the known family prefixes.
# ---------------------------------------------------------------------------
def _family_for_prefix(prefix_map, model: str) -> str | None:
    normalized = model.strip().lower()
    for prefixes, family in prefix_map:
        if normalized.startswith(prefixes):
            return family
    return None


def test_model_prefix_map_known_mappings():
    """gpt- -> openai, claude- -> anthropic, gemini- -> google (and more)."""
    from kaizen.providers.provider_names import MODEL_PREFIX_MAP

    assert _family_for_prefix(MODEL_PREFIX_MAP, "gpt-4o") == "openai"
    assert _family_for_prefix(MODEL_PREFIX_MAP, "claude-3-opus") == "anthropic"
    assert _family_for_prefix(MODEL_PREFIX_MAP, "gemini-2.5-flash") == "google"
    assert _family_for_prefix(MODEL_PREFIX_MAP, "llama3") == "ollama"
    assert _family_for_prefix(MODEL_PREFIX_MAP, "totally-unknown-model") is None


def test_model_prefix_map_underscore_alias_is_same_object():
    """The backward-compat _MODEL_PREFIX_MAP alias IS the public map."""
    from kaizen.providers import provider_names

    assert provider_names._MODEL_PREFIX_MAP is provider_names.MODEL_PREFIX_MAP


def test_registry_underscore_alias_matches_pure_data_source():
    """registry.py re-exports the same prefix map (single source of truth)."""
    from kaizen.providers import provider_names, registry

    assert registry._MODEL_PREFIX_MAP is provider_names.MODEL_PREFIX_MAP


# ---------------------------------------------------------------------------
# (c) SOURCE-LEVEL zero-coupling contract (AST import audit).
# ---------------------------------------------------------------------------
_FORBIDDEN_PROVIDER_NAMES_IMPORT_PREFIXES = (
    "kaizen.providers.llm",
    "kaizen.providers.base",
    "kaizen.providers.registry",
)


def _module_source_imports(module) -> set[str]:
    """Return the set of dotted module names imported by ``module``'s SOURCE.

    Parses the file (not the runtime object) so ``from a.b import c`` yields
    ``a.b`` and ``import a.b`` yields ``a.b``.
    """
    source = Path(module.__file__).read_text()
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                imported.add(node.module)
    return imported


def test_provider_names_source_has_zero_provider_class_imports():
    """CRITICAL: provider_names.py imports nothing from llm.*/base/registry."""
    from kaizen.providers import provider_names

    imported = _module_source_imports(provider_names)
    offenders = {
        name
        for name in imported
        if name.startswith(_FORBIDDEN_PROVIDER_NAMES_IMPORT_PREFIXES)
    }
    assert not offenders, (
        "provider_names.py must be pure literals (zero provider-class imports); "
        f"found forbidden imports: {sorted(offenders)}"
    )


def test_metrics_source_no_longer_imports_registry():
    """metrics.py no longer imports kaizen.providers.registry at the source."""
    import kaizen.production.metrics as metrics

    imported = _module_source_imports(metrics)
    assert "kaizen.providers.registry" not in imported, (
        "metrics.py must not import kaizen.providers.registry; found it in "
        f"{sorted(i for i in imported if i.startswith('kaizen.providers'))}"
    )
    # ...and it DOES source the pure-data name registry instead.
    assert "kaizen.providers.provider_names" in imported


def test_provider_names_module_exposes_no_provider_class():
    """No attribute on the pure-data module is a provider class."""
    from kaizen.providers import provider_names
    from kaizen.providers.base import BaseProvider

    for name in dir(provider_names):
        value = getattr(provider_names, name)
        assert not (
            isinstance(value, type) and issubclass(value, BaseProvider)
        ), f"provider_names leaked a provider class via attribute {name!r}"


# ---------------------------------------------------------------------------
# (d) metrics label-bounding still behaves identically post-extraction.
# ---------------------------------------------------------------------------
def test_metrics_bound_provider_label_behaves_identically():
    from kaizen.production.metrics import _OTHER_LABEL, _bound_provider_label

    assert _bound_provider_label("openai") == "openai"
    assert _bound_provider_label("  Anthropic ") == "anthropic"
    assert _bound_provider_label("gemini") == "gemini"
    assert _bound_provider_label("not-a-provider") == _OTHER_LABEL
    assert _bound_provider_label("") == _OTHER_LABEL


def test_metrics_bound_model_label_behaves_identically():
    from kaizen.production.metrics import _OTHER_LABEL, _bound_model_label

    assert _bound_model_label("gpt-4o") == "openai"
    assert _bound_model_label("claude-3-opus-20240229") == "anthropic"
    assert _bound_model_label("gemini-2.5-flash") == "google"
    assert _bound_model_label("unknown-model-xyz") == _OTHER_LABEL
    assert _bound_model_label("") == _OTHER_LABEL


def test_bounded_providers_is_the_pure_data_name_set():
    """metrics._BOUNDED_PROVIDERS is now the pure-data PROVIDER_NAMES."""
    from kaizen.production.metrics import _BOUNDED_PROVIDERS
    from kaizen.providers.provider_names import PROVIDER_NAMES

    assert _BOUNDED_PROVIDERS is PROVIDER_NAMES
