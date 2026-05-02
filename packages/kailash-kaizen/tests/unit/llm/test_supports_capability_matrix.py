# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``LlmDeployment.supports()`` capability matrix.

Covers terrene-foundation/kailash-py#763 — cross-SDK parity with kailash-rs
PR #725 (``CapabilityMatrix::for_preset``). The matrix is a per-preset
five-axis capability negotiation surface: ``tools``, ``vision``, ``batch``,
``caching``, ``audio``.

Acceptance criteria from the issue:

- Returns a dict with five boolean fields.
- Per-preset matrix derived from current provider docs (NOT all-true /
  all-false everywhere).
- Unknown / future presets return all-False (fail-closed).
- Tier 2 test for ≥3 presets with provider-distinct matrices.
- Documentation example present.

Per ``rules/testing.md`` § 3-Tier Testing, these are Tier 1 unit tests —
the matrix is a pure function with no real infrastructure dependency. The
"Tier 2" framing in the issue is read as "exercised through the
``LlmDeployment.preset()`` public surface", which these tests do.
"""

from __future__ import annotations

import pytest

from kaizen.llm.capabilities import ALL_FALSE_CAPABILITIES, CAPABILITY_KEYS, for_preset
from kaizen.llm.deployment import Endpoint, LlmDeployment, WireProtocol

# ---------------------------------------------------------------------------
# Shape: every result is a dict with the five canonical keys
# ---------------------------------------------------------------------------


def test_supports_returns_dict_with_five_keys() -> None:
    dep = LlmDeployment.openai("sk-test", model="gpt-4o-mini")
    caps = dep.supports()
    assert isinstance(caps, dict)
    assert set(caps.keys()) == set(CAPABILITY_KEYS)
    assert set(CAPABILITY_KEYS) == {"tools", "vision", "batch", "caching", "audio"}
    assert all(isinstance(v, bool) for v in caps.values())


def test_capability_keys_byte_match_cross_sdk_contract() -> None:
    """Names + count are part of the cross-SDK contract — pin them.

    A drift here breaks every kailash-rs ``CapabilityMatrix`` consumer that
    ports its assertion strings to Python or vice-versa.
    """
    assert CAPABILITY_KEYS == ("tools", "vision", "batch", "caching", "audio")


# ---------------------------------------------------------------------------
# Per-preset matrices — provider-distinct rows (issue AC: ≥3 presets)
# ---------------------------------------------------------------------------


def test_openai_supports_full_matrix() -> None:
    dep = LlmDeployment.openai("sk-test", model="gpt-4o")
    caps = dep.supports()
    assert caps == {
        "tools": True,
        "vision": True,
        "batch": True,
        "caching": True,
        "audio": True,
    }


def test_anthropic_supports_no_audio() -> None:
    dep = LlmDeployment.anthropic("sk-ant-test", model="claude-sonnet-4-6")
    caps = dep.supports()
    assert caps == {
        "tools": True,
        "vision": True,
        "batch": True,
        "caching": True,
        "audio": False,
    }


def test_ollama_supports_local_subset() -> None:
    dep = LlmDeployment.ollama("http://localhost:11434", model="llama3.1")
    caps = dep.supports()
    # Local server presets carry tools + vision but NOT batch / caching /
    # audio adjacency — distinct from the SaaS providers above.
    assert caps == {
        "tools": True,
        "vision": True,
        "batch": False,
        "caching": False,
        "audio": False,
    }


def test_perplexity_supports_minimal_matrix() -> None:
    """Perplexity is the all-false direct provider on kailash-rs row."""
    dep = LlmDeployment.perplexity("pplx-test", model="sonar")
    caps = dep.supports()
    assert caps == {
        "tools": False,
        "vision": False,
        "batch": False,
        "caching": False,
        "audio": False,
    }


def test_bedrock_claude_supports_no_audio() -> None:
    """Bedrock Claude carries every capability except audio (parity row).

    `bedrock_claude` constructs `AwsBearerToken(api_key, region)` internally
    — bearer-token form does not require botocore at construction time. The
    region is the closest published Bedrock region to North America.
    """
    dep = LlmDeployment.bedrock_claude(
        api_key="aws-test-token-not-a-real-credential",
        region="us-east-1",
        model="claude-sonnet-4-6",
    )
    caps = dep.supports()
    assert caps == {
        "tools": True,
        "vision": True,
        "batch": True,
        "caching": True,
        "audio": False,
    }


# ---------------------------------------------------------------------------
# Fail-closed: unknown presets and manual constructions return all-False
# ---------------------------------------------------------------------------


def test_unknown_preset_name_returns_all_false() -> None:
    """Forward-compatibility: a preset that has not yet had its capability
    row wired returns all-False until the wiring lands."""
    caps = for_preset("future_preset_we_havent_invented_yet")
    assert caps == dict(ALL_FALSE_CAPABILITIES)
    assert all(v is False for v in caps.values())


def test_manual_construction_with_none_preset_name_returns_all_false() -> None:
    """`preset_name=None` (manual construction) — fail-closed default."""
    from kaizen.llm.auth.bearer import ApiKey, ApiKeyBearer, ApiKeyHeaderKind

    dep = LlmDeployment(
        wire=WireProtocol.OpenAiChat,
        endpoint=Endpoint(base_url="https://example.com", path_prefix="/v1"),
        auth=ApiKeyBearer(
            kind=ApiKeyHeaderKind.Authorization_Bearer,
            key=ApiKey("sk-test"),
        ),
        default_model="some-model",
        preset_name=None,
    )
    caps = dep.supports()
    assert caps == {
        "tools": False,
        "vision": False,
        "batch": False,
        "caching": False,
        "audio": False,
    }


# ---------------------------------------------------------------------------
# Independence: returned dicts are fresh copies — no shared mutable state
# ---------------------------------------------------------------------------


def test_supports_returns_independent_copy() -> None:
    dep_a = LlmDeployment.openai("sk-test", model="gpt-4o")
    dep_b = LlmDeployment.openai("sk-test-2", model="gpt-4o-mini")
    caps_a = dep_a.supports()
    caps_b = dep_b.supports()
    # Mutate caps_a — caps_b MUST be untouched.
    caps_a["tools"] = False
    caps_a["custom_axis"] = True  # type: ignore[assignment]
    assert caps_b["tools"] is True
    assert "custom_axis" not in caps_b
    # And a fresh call returns the canonical row again.
    assert dep_a.supports()["tools"] is True


def test_for_preset_returns_independent_copy_of_all_false() -> None:
    """ALL_FALSE_CAPABILITIES is the canonical fail-closed row — callers
    MUST NOT be able to corrupt it through the function's return value."""
    caps_1 = for_preset("unknown_xyz")
    caps_2 = for_preset("unknown_abc")
    caps_1["tools"] = True
    assert caps_2["tools"] is False  # caps_1's mutation did NOT bleed


# ---------------------------------------------------------------------------
# Compatible-endpoint presets (#761 / #762) inherit OpenAI / Anthropic rows
# ---------------------------------------------------------------------------


def test_openai_compatible_inherits_openai_capabilities() -> None:
    # `example.com` is the RFC-2606 reserved test host that resolves under
    # SSRF guard's DNS check (mirrors the pattern in
    # `test_preset_name_and_compatible.py`).
    dep = LlmDeployment.openai_compatible("https://example.com/v1", "sk-proxy-test")
    assert dep.supports() == LlmDeployment.openai("sk-test", model="x").supports()


def test_anthropic_compatible_inherits_anthropic_capabilities() -> None:
    dep = LlmDeployment.anthropic_compatible("https://example.com/v1", "sk-or-test")
    assert (
        dep.supports()
        == LlmDeployment.anthropic("sk-ant", model="claude-sonnet-4-6").supports()
    )


# ---------------------------------------------------------------------------
# Cross-SDK parity — every kailash-rs row has a Python row
# ---------------------------------------------------------------------------


# Documented presets with at least one True capability bit per
# kailash-rs ``CapabilityMatrix::for_preset``. Used to verify the row
# was actually wired (vs. accidentally falling through to the all-False
# default).
_NON_EMPTY_PRESETS = (
    "openai",
    "openai_compatible",
    "anthropic",
    "anthropic_compatible",
    "google",
    "azure_openai",
    "vertex_claude",
    "vertex_gemini",
    "bedrock_claude",
    "bedrock_llama",
    "bedrock_titan",
    "bedrock_mistral",
    "bedrock_cohere",
    "groq",
    "ollama",
    "ollama_default",
    "cohere",
    "mistral",
)
# Documented presets that ARE intentionally all-False per kailash-rs.
# Distinct from "unknown preset" — the entry IS in the table; verifying
# the value matches the canonical all-False contract is the test.
_ALL_FALSE_PRESETS = ("perplexity", "huggingface")


@pytest.mark.parametrize("preset_name", _NON_EMPTY_PRESETS)
def test_every_non_empty_preset_has_capability_row(preset_name: str) -> None:
    """Per ``rules/cross-sdk-inspection.md`` § 3a, every preset name listed
    in kailash-rs ``CapabilityMatrix::for_preset`` MUST have a Python row.

    For presets carrying ≥1 capability, the row MUST NOT be all-False
    (would mean the row was never wired despite the entry existing).
    """
    caps = for_preset(preset_name)
    assert set(caps.keys()) == set(CAPABILITY_KEYS)
    assert caps != dict(
        ALL_FALSE_CAPABILITIES
    ), f"preset {preset_name!r} returns all-False — capability row missing"


@pytest.mark.parametrize("preset_name", _ALL_FALSE_PRESETS)
def test_documented_all_false_presets_match_kailash_rs(preset_name: str) -> None:
    """Some kailash-rs rows are intentionally all-False
    (perplexity / huggingface). The Python row MUST match — the
    structural invariant is "row is wired", not "row is non-empty".
    """
    caps = for_preset(preset_name)
    assert caps == dict(ALL_FALSE_CAPABILITIES)
