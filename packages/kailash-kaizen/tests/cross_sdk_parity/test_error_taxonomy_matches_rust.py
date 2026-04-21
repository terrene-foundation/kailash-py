# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Cross-SDK parity: LlmClientError hierarchy matches Rust variant names.

Per ADR-0001 D6 + D9, the LLM deployment error surface MUST be
byte-identical across kailash-py and kailash-rs. Error class names in
Python correspond to Rust enum variant identifiers; both SDKs raise the
same typed error for the same failure mode so log aggregators, retry
middleware, and alerting rules work uniformly across polyglot deploys.

The fixture ``fixtures/rust_error_taxonomy.json`` pins the contract.
This test asserts:

1. Every Rust variant name exists as a Python exception class.
2. The Python hierarchy's tier-1 categories (LlmError, AuthError,
   EndpointError, ModelGrammarError, ConfigError) match Rust's.
3. Each tier-1 category's subclasses are a superset of the Rust
   variants under that category.
4. The root error (``LlmClientError``) is the MRO ancestor of every
   variant.
5. No Python-only error names leak into the public cross-SDK surface
   unless explicitly whitelisted (currently none).

EATP D6 compliance: when kailash-rs adds / renames a variant, refresh
``fixtures/rust_error_taxonomy.json`` in the same PR.

Origin: issue #498 Session 8 (S9).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def rust_fixture() -> dict:
    path = Path(__file__).parent / "fixtures" / "rust_error_taxonomy.json"
    return json.loads(path.read_text())


def test_every_rust_variant_exists_as_python_class(rust_fixture: dict) -> None:
    """Every Rust variant name is an importable Python Exception subclass."""
    import kaizen.llm.errors as errors_mod

    missing = []
    for name in rust_fixture["all_names_flat"]:
        cls = getattr(errors_mod, name, None)
        if cls is None or not isinstance(cls, type) or not issubclass(cls, Exception):
            missing.append(name)
    assert not missing, (
        f"Python SDK missing {len(missing)} error classes present in Rust: "
        f"{missing}. Cross-SDK error-taxonomy parity violated (EATP D6)."
    )


def test_root_is_llmclienterror(rust_fixture: dict) -> None:
    """LlmClientError is the MRO root of every variant."""
    import kaizen.llm.errors as errors_mod

    root = errors_mod.LlmClientError
    for name in rust_fixture["all_names_flat"]:
        if name == "LlmClientError":
            continue
        cls = getattr(errors_mod, name)
        assert issubclass(cls, root), (
            f"{name} does not inherit from LlmClientError; cross-SDK contract "
            f"requires every deployment-surface error to share a root."
        )


def test_tier1_categories_match_rust(rust_fixture: dict) -> None:
    """The five tier-1 categories exist and directly inherit from LlmClientError."""
    import kaizen.llm.errors as errors_mod

    root = errors_mod.LlmClientError
    for cat_name in rust_fixture["tier_1_categories"]:
        cat = getattr(errors_mod, cat_name, None)
        assert cat is not None, f"Tier-1 category '{cat_name}' not found in Python SDK"
        # Directly inherits from root (root is one MRO-step away).
        assert root in cat.__bases__, (
            f"{cat_name} does NOT directly inherit from LlmClientError "
            f"(MRO: {[b.__name__ for b in cat.__bases__]}); Rust has it as "
            f"a tier-1 enum, Python must mirror as a direct subclass."
        )


def test_every_variant_inherits_from_its_tier1_category(rust_fixture: dict) -> None:
    """Each variant inherits from its declared tier-1 category."""
    import kaizen.llm.errors as errors_mod

    for category, variants in rust_fixture["variants"].items():
        cat_cls = getattr(errors_mod, category)
        for variant_name in variants:
            variant_cls = getattr(errors_mod, variant_name)
            assert issubclass(variant_cls, cat_cls), (
                f"{variant_name} does NOT inherit from {category}; "
                f"cross-SDK contract groups this variant under {category}."
            )


def test_no_python_only_errors_leak_public_surface(rust_fixture: dict) -> None:
    """The errors module defines no public exception classes beyond the Rust catalog.

    Private helper classes (prefixed ``_``) are permitted. Any other public
    exception class that is NOT in the Rust fixture is a cross-SDK parity
    violation -- it silently ships a Python-only error taxonomy that breaks
    when code is ported to / from Rust.
    """
    import inspect

    import kaizen.llm.errors as errors_mod

    rust_names = set(rust_fixture["all_names_flat"])
    python_public_errors = {
        name
        for name, obj in inspect.getmembers(errors_mod, inspect.isclass)
        if issubclass(obj, Exception) and not name.startswith("_")
        # obj MUST be defined in this module (not re-exported stdlib).
        and obj.__module__ == "kaizen.llm.errors"
    }
    extras = python_public_errors - rust_names
    assert not extras, (
        f"Python SDK has {len(extras)} public error class(es) not in Rust: "
        f"{sorted(extras)}. Either add to Rust OR rename with a leading "
        f"underscore to mark private."
    )


def test_config_error_variants_complete(rust_fixture: dict) -> None:
    """ConfigError subfamily is the from_env() contract; assert explicit."""
    import kaizen.llm.errors as errors_mod

    expected = set(rust_fixture["variants"]["ConfigError"])
    assert expected == {"NoKeysConfigured", "InvalidUri", "InvalidPresetName"}

    for name in expected:
        cls = getattr(errors_mod, name)
        assert issubclass(cls, errors_mod.ConfigError), (
            f"{name} MUST inherit from ConfigError for cross-SDK "
            f"from_env() exception handlers to catch uniformly."
        )


def test_raising_and_catching_cross_sdk_stable() -> None:
    """Behavioural: catching LlmClientError catches every cross-SDK error.

    A caller that writes ``except LlmClientError`` MUST catch every
    deployment-surface error, matching the Rust ``LlmClientError`` match
    arm coverage. Verified by actually raising each typed error and
    confirming the catch-all arm fires.
    """
    import kaizen.llm.errors as errors_mod

    for name, args in [
        ("Timeout", (30.0,)),
        ("NoKeysConfigured", ("no keys",)),
        ("InvalidUri", ("bad uri",)),
        ("MissingCredential", ("OPENAI_API_KEY",)),
        ("ModelRequired", ("openai",)),
    ]:
        cls = getattr(errors_mod, name)
        try:
            raise cls(*args)
        except errors_mod.LlmClientError as exc:
            assert isinstance(exc, cls)
        else:
            pytest.fail(f"{name} was not caught by LlmClientError")
