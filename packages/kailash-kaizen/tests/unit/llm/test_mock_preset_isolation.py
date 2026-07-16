# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for the test-only mock_preset module isolation (#788).

Cross-SDK parity with kailash-rs ``LlmDeployment::mock()`` at
``crates/kailash-kaizen/src/llm/deployment/presets.rs:1183``, which is
gated behind ``#[cfg(any(test, feature = "test-utils"))]``. Python's
structural defense is physical module separation —
``kaizen.llm.testing.mock_preset`` exists; ``LlmDeployment.mock`` does
not exist; ``kaizen.llm.presets.mock_preset`` does not exist.

This file is the structural-defense Tier-1 test suite. The tests
deliberately exercise the absence of symbols on the production import
surface so that any future regression (e.g. someone copies
``mock_preset`` to ``presets.py`` and forgets the gating intent)
fails loudly here.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

from kaizen.llm.deployment import Endpoint, LlmDeployment, WireProtocol

# ---------------------------------------------------------------------------
# Structural defense — mock symbol is absent from production import surface
# ---------------------------------------------------------------------------


def test_llm_deployment_has_no_mock_classmethod() -> None:
    """The production ``LlmDeployment`` class MUST NOT expose a
    ``mock`` classmethod. Cross-SDK parity with Rust's
    ``#[cfg(any(test, feature = "test-utils"))]`` gating.

    If this assertion fails, someone has wired ``mock_preset`` into the
    production ``LlmDeployment`` surface — undoing the structural
    defense per ``rules/zero-tolerance.md`` Rule 2 (no fake/simulated
    data on the production surface).
    """
    assert not hasattr(
        LlmDeployment, "mock"
    ), "LlmDeployment.mock() MUST NOT exist on the production surface"


def test_kaizen_llm_presets_does_not_export_mock_preset() -> None:
    """The production ``kaizen.llm.presets`` module MUST NOT export
    a ``mock_preset`` factory. Test code wanting a mock deployment
    MUST import from ``kaizen.llm.testing`` explicitly.
    """
    presets = importlib.import_module("kaizen.llm.presets")
    assert not hasattr(
        presets, "mock_preset"
    ), "kaizen.llm.presets.mock_preset MUST NOT exist (use kaizen.llm.testing)"


def test_mock_is_not_in_preset_registry() -> None:
    """The preset registry MUST NOT have a ``"mock"`` entry. Adding
    one would expose the mock factory through ``get_preset("mock")``
    and ``LlmDeployment.<name>`` classmethod attachment, defeating
    the testing-module isolation.
    """
    from kaizen.llm.presets import list_presets

    registered = list_presets()
    assert (
        "mock" not in registered
    ), "preset registry MUST NOT contain 'mock' (it lives in kaizen.llm.testing)"


# ---------------------------------------------------------------------------
# Functional — mock_preset constructs a working LlmDeployment
# ---------------------------------------------------------------------------


def test_mock_preset_constructs_llm_deployment() -> None:
    from kaizen.llm.testing import mock_preset

    dep = mock_preset()
    assert isinstance(dep, LlmDeployment)
    assert dep.preset_name == "mock"
    assert dep.default_model == "mock-model"
    assert dep.wire is WireProtocol.OpenAiChat


def test_mock_preset_default_model_matches_cross_sdk_literal() -> None:
    """Default model literal pinned for cross-SDK parity. Rust's
    ``LlmDeployment::mock()`` constructs deployments named ``"mock"``;
    the model string is the next consumer assertion surface in test
    code that ports between SDKs.
    """
    from kaizen.llm.testing import mock_preset

    dep = mock_preset()
    assert dep.default_model == "mock-model"


def test_mock_preset_endpoint_uses_rfc2606_test_host() -> None:
    """Mock endpoint MUST resolve under SSRF guard — uses the
    RFC-2606 reserved test host ``example.com``. Same literal as
    Rust's ``Endpoint::new("https://example.com")`` at
    ``presets.rs:1183``.
    """
    from kaizen.llm.testing import mock_preset

    dep = mock_preset()
    assert isinstance(dep.endpoint, Endpoint)
    # `HttpUrl` normalises to a trailing slash; pin the prefix.
    assert str(dep.endpoint.base_url).startswith("https://example.com")
    assert dep.endpoint.path_prefix == "/v1"


def test_mock_preset_accepts_caller_model_override() -> None:
    """Callers may override the default model for tests that need a
    specific literal in assertions (e.g. registry lookups keyed on
    model name).
    """
    from kaizen.llm.testing import mock_preset

    dep = mock_preset(model="custom-test-model")
    assert dep.default_model == "custom-test-model"
    assert dep.preset_name == "mock"  # preset literal unchanged


# ---------------------------------------------------------------------------
# Capability matrix — mock falls through to all-False (matches Rust)
# ---------------------------------------------------------------------------


def test_mock_preset_supports_returns_all_false() -> None:
    """Cross-SDK parity: Rust's ``CapabilityMatrix::for_preset("mock")``
    falls through to ``Self::all_false()`` because no explicit row
    exists at
    ``crates/kailash-kaizen/src/llm/deployment/capabilities.rs:120-250``.
    Python preserves the same behavior via fail-closed default.
    """
    from kaizen.llm.testing import mock_preset

    caps = mock_preset().supports()
    assert caps == {
        "tools": False,
        "vision": False,
        "batch": False,
        "caching": False,
        "audio": False,
    }


def test_mock_is_not_in_preset_capabilities_table() -> None:
    """The capability table MUST NOT have a ``"mock"`` entry — the
    fail-closed default is the deliberate cross-SDK-parity behavior.
    Adding a row would diverge from Rust.
    """
    from kaizen.llm.capabilities import _PRESET_CAPABILITIES

    assert "mock" not in _PRESET_CAPABILITIES, (
        "kaizen.llm.capabilities._PRESET_CAPABILITIES MUST NOT have a 'mock' "
        "row — Rust's CapabilityMatrix::for_preset('mock') falls through to "
        "all-False (no row); Python parity requires the same"
    )


# ---------------------------------------------------------------------------
# Importability — module discoverability + no test-side imports leak
# ---------------------------------------------------------------------------


def test_kaizen_llm_testing_module_is_importable() -> None:
    """Sanity: the test-only module MUST be importable. If this
    fails, the package layout is broken.
    """
    mod = importlib.import_module("kaizen.llm.testing")
    assert hasattr(mod, "mock_preset")
    assert "mock_preset" in mod.__all__


def test_mock_preset_module_path_signals_test_only_intent() -> None:
    """The module path ``kaizen.llm.testing`` is the deliberate red
    flag: production code that imports from a module named
    ``testing`` is structurally identifiable by
    ``grep -rn 'kaizen.llm.testing' src/``. This test asserts the
    intended path so a future refactor doesn't quietly rename the
    module to something less obvious.
    """
    from kaizen.llm import testing as testing_module

    assert testing_module.__name__ == "kaizen.llm.testing"


# ---------------------------------------------------------------------------
# Future-proofing — explicit guard against re-introducing the gap
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name", ["mock", "Mock", "MOCK", "mock_preset", "test", "fake"]
)
def test_no_mock_aliased_classmethod_under_alternate_names(name: str) -> None:
    """Belt-and-suspenders: assert no alternate-cased mock attribute
    leaks onto the production surface either. If a future refactor
    needs to add a ``MockLlmDeployment`` class for some other reason,
    this test exists to force the author to revisit the gating
    intent rather than pattern-match an existing classmethod.
    """
    assert (
        not hasattr(LlmDeployment, name)
        or not callable(getattr(LlmDeployment, name, None))
        or name not in {"mock", "Mock", "MOCK", "mock_preset"}
    ), f"LlmDeployment.{name} MUST NOT be a callable mock surface"


# ---------------------------------------------------------------------------
# Transport isolation (#1720 Wave-1b MOCK) -- MockLlmHttpClient extends the
# same physical-separation invariant mock_preset() established: production
# code under src/kaizen/ MUST NOT import kaizen.llm.testing (housing BOTH
# mock_preset AND MockLlmHttpClient), and MockLlmHttpClient MUST be absent
# from the production entry points (kaizen.llm.client / kaizen.llm.http_client
# / kaizen.llm.presets) a downstream app would import for real HTTP traffic.
# ---------------------------------------------------------------------------


def test_grep_finds_no_production_importer_of_kaizen_llm_testing() -> None:
    """Structural invariant: `kaizen.llm.testing` MUST NOT be imported from
    any production module under `src/kaizen/`. The ONLY legitimate
    self-references are files inside the `testing/` package itself. Mirrors
    the module docstring's claim that this is `grep`-able
    (`grep -rn 'kaizen.llm.testing' src/kaizen/`) -- this test IS that grep,
    run mechanically instead of by hand.
    """
    src_root = Path(__file__).resolve().parents[3] / "src" / "kaizen"
    assert src_root.is_dir(), f"expected src root at {src_root}"

    pattern = re.compile(r"\bkaizen\.llm\.testing\b")
    violations: list[str] = []
    for path in sorted(src_root.rglob("*.py")):
        rel = path.relative_to(src_root)
        # The testing/ package's own files are allowed to self-reference
        # (docstrings, __init__ exports, intra-package imports).
        if rel.parts[:2] == ("llm", "testing"):
            continue
        text = path.read_text(encoding="utf-8")
        if pattern.search(text):
            violations.append(str(rel))

    assert not violations, (
        "Production modules under src/kaizen/ MUST NOT reference "
        f"kaizen.llm.testing (found in: {violations})"
    )


def test_mock_llm_http_client_absent_from_production_import_surface() -> None:
    """MockLlmHttpClient MUST NOT be reachable as an attribute of
    kaizen.llm.client, kaizen.llm.http_client, or kaizen.llm.presets -- the
    production entry points a downstream app imports for real LLM /
    real-transport traffic. Test code that wants the deterministic offline
    transport imports it explicitly from kaizen.llm.testing.
    """
    import kaizen.llm.client as client_module
    import kaizen.llm.http_client as http_client_module
    import kaizen.llm.presets as presets_module

    for module in (client_module, http_client_module, presets_module):
        assert not hasattr(module, "MockLlmHttpClient"), (
            f"{module.__name__} MUST NOT expose MockLlmHttpClient "
            "(test-only transport; import from kaizen.llm.testing instead)"
        )


def test_mock_llm_http_client_importable_only_from_testing_module() -> None:
    """Sanity + red-flag-path assertion: the ONE legitimate import path for
    MockLlmHttpClient is `kaizen.llm.testing` (re-exporting
    `kaizen.llm.testing.mock_transport.MockLlmHttpClient`).
    """
    from kaizen.llm.testing import MockLlmHttpClient
    from kaizen.llm.testing.mock_transport import MockLlmHttpClient as DirectImport

    assert MockLlmHttpClient is DirectImport
