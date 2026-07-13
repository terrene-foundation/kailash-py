# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""from_env() Vertex selector + region-config tests (#1717).

Covers the env-config completion for Vertex-on-GCP:

* `KAILASH_LLM_PROVIDER=vertex_claude` / `vertex_gemini` resolves WITHOUT a
  full URI, reading GOOGLE_CLOUD_PROJECT / VERTEX_LOCATION / model env
  (deliverable #5).
* The service-account key is OPTIONAL -- an unset
  GOOGLE_APPLICATION_CREDENTIALS resolves keyless ADC (deliverable #4/#5).
* `_GCP_REGION_RE` accepts `us` / `eu` / `global` in addition to the
  `us-central1` shape (deliverable #7).
* The vertex catalog resolves `claude-opus-4-8` through the selector
  end-to-end (deliverable #6, exercised via the grammar).

Env-var reads go through monkeypatch with a clean-slate strip at the top of
each test, matching the sibling `test_from_env.py` pattern for the
KAILASH_LLM_* surface.
"""

from __future__ import annotations

import pytest

from kaizen.llm.deployment import WireProtocol
from kaizen.llm.errors import MissingCredential
from kaizen.llm.from_env import (
    ENV_DEPLOYMENT_URI,
    ENV_SELECTOR,
    _GCP_REGION_RE,
    resolve_env_deployment,
)

_VERTEX_ENV = (
    ENV_DEPLOYMENT_URI,
    ENV_SELECTOR,
    "GOOGLE_CLOUD_PROJECT",
    "VERTEX_LOCATION",
    "VERTEX_CLAUDE_MODEL_ID",
    "VERTEX_CLAUDE_MODEL",
    "VERTEX_GEMINI_MODEL_ID",
    "VERTEX_GEMINI_MODEL",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "DEEPSEEK_API_KEY",
)


@pytest.fixture
def _clean_env(monkeypatch: pytest.MonkeyPatch):
    for var in _VERTEX_ENV:
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


# ---------------------------------------------------------------------------
# Region regex broadening (#7)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "region", ["us", "eu", "global", "us-central1", "europe-west4", "asia-south1"]
)
def test_gcp_region_regex_accepts_multi_region_and_standard(region: str) -> None:
    assert _GCP_REGION_RE.match(region) is not None


@pytest.mark.parametrize(
    "region",
    ["", "US", "us_central1", "evil.com", "us-central1\r\nX", "eu-", "globalz1x"],
)
def test_gcp_region_regex_rejects_bad_shapes(region: str) -> None:
    # `globalz1x` does not equal the literal `global` and does not match the
    # `<area>-<locality><digit>` shape either -> rejected.
    assert _GCP_REGION_RE.match(region) is None


def test_gcp_region_regex_eu_passes_straight_through() -> None:
    """`eu` is accepted verbatim -- NOT mapped to `europe-west1` (#7)."""
    m = _GCP_REGION_RE.match("eu")
    assert m is not None and m.group(0) == "eu"


# ---------------------------------------------------------------------------
# Vertex selector — service-account key present (#5)
# ---------------------------------------------------------------------------


def test_vertex_claude_selector_with_sa_path(_clean_env, tmp_path) -> None:
    sa = tmp_path / "sa.json"
    sa.write_text("{}", encoding="utf-8")  # not read at construction
    _clean_env.setenv(ENV_SELECTOR, "vertex_claude")
    _clean_env.setenv("GOOGLE_CLOUD_PROJECT", "my-gcp-project")
    _clean_env.setenv("VERTEX_LOCATION", "us-central1")
    _clean_env.setenv("VERTEX_CLAUDE_MODEL_ID", "claude-3-opus")
    _clean_env.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(sa))
    dep = resolve_env_deployment()
    assert dep.wire == WireProtocol.AnthropicMessages
    assert dep.preset_name == "vertex_claude"
    assert dep.default_model == "claude-3-opus@20240229"
    assert dep.auth.auth_strategy_kind() == "gcp_oauth"


def test_vertex_gemini_selector_with_sa_path(_clean_env, tmp_path) -> None:
    sa = tmp_path / "sa.json"
    sa.write_text("{}", encoding="utf-8")
    _clean_env.setenv(ENV_SELECTOR, "vertex_gemini")
    _clean_env.setenv("GOOGLE_CLOUD_PROJECT", "my-gcp-project")
    _clean_env.setenv("VERTEX_LOCATION", "us-central1")
    _clean_env.setenv("VERTEX_GEMINI_MODEL_ID", "gemini-2.0-flash")
    _clean_env.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(sa))
    dep = resolve_env_deployment()
    assert dep.wire == WireProtocol.VertexGenerateContent
    assert dep.preset_name == "vertex_gemini"
    assert dep.default_model == "gemini-2.0-flash"


# ---------------------------------------------------------------------------
# Vertex selector — keyless ADC fallback (#4/#5)
# ---------------------------------------------------------------------------


def test_vertex_claude_selector_keyless_falls_back_to_adc(_clean_env) -> None:
    """GOOGLE_APPLICATION_CREDENTIALS unset -> keyless ADC, no hard-fail."""
    _clean_env.setenv(ENV_SELECTOR, "vertex_claude")
    _clean_env.setenv("GOOGLE_CLOUD_PROJECT", "my-gcp-project")
    _clean_env.setenv("VERTEX_LOCATION", "us-central1")
    _clean_env.setenv("VERTEX_CLAUDE_MODEL_ID", "claude-sonnet-4-6")
    dep = resolve_env_deployment()
    assert dep.preset_name == "vertex_claude"
    assert dep.auth.auth_strategy_kind() == "gcp_adc"


def test_vertex_selector_legacy_model_env_fallback(_clean_env) -> None:
    """VERTEX_CLAUDE_MODEL (no _ID suffix) is accepted when _ID is unset."""
    _clean_env.setenv(ENV_SELECTOR, "vertex_claude")
    _clean_env.setenv("GOOGLE_CLOUD_PROJECT", "my-gcp-project")
    _clean_env.setenv("VERTEX_LOCATION", "us-central1")
    _clean_env.setenv("VERTEX_CLAUDE_MODEL", "claude-3-haiku")
    dep = resolve_env_deployment()
    assert dep.default_model == "claude-3-haiku@20240307"


# ---------------------------------------------------------------------------
# Vertex catalog: claude-opus-4-8 resolves through the selector (#6)
# ---------------------------------------------------------------------------


def test_vertex_claude_selector_resolves_claude_opus_4_8(_clean_env) -> None:
    _clean_env.setenv(ENV_SELECTOR, "vertex_claude")
    _clean_env.setenv("GOOGLE_CLOUD_PROJECT", "my-gcp-project")
    _clean_env.setenv("VERTEX_LOCATION", "us-central1")
    _clean_env.setenv("VERTEX_CLAUDE_MODEL_ID", "claude-opus-4-8")
    dep = resolve_env_deployment()
    assert dep.default_model == "claude-opus-4-8@latest"


# ---------------------------------------------------------------------------
# Missing required config -> typed MissingCredential
# ---------------------------------------------------------------------------


def test_vertex_selector_missing_project_raises(_clean_env) -> None:
    _clean_env.setenv(ENV_SELECTOR, "vertex_claude")
    _clean_env.setenv("VERTEX_LOCATION", "us-central1")
    _clean_env.setenv("VERTEX_CLAUDE_MODEL_ID", "claude-3-opus")
    with pytest.raises(MissingCredential, match=r"GOOGLE_CLOUD_PROJECT"):
        resolve_env_deployment()


def test_vertex_selector_missing_region_raises(_clean_env) -> None:
    _clean_env.setenv(ENV_SELECTOR, "vertex_claude")
    _clean_env.setenv("GOOGLE_CLOUD_PROJECT", "my-gcp-project")
    _clean_env.setenv("VERTEX_CLAUDE_MODEL_ID", "claude-3-opus")
    with pytest.raises(MissingCredential, match=r"VERTEX_LOCATION"):
        resolve_env_deployment()


def test_vertex_selector_missing_model_raises(_clean_env) -> None:
    _clean_env.setenv(ENV_SELECTOR, "vertex_claude")
    _clean_env.setenv("GOOGLE_CLOUD_PROJECT", "my-gcp-project")
    _clean_env.setenv("VERTEX_LOCATION", "us-central1")
    with pytest.raises(MissingCredential, match=r"VERTEX_CLAUDE_MODEL"):
        resolve_env_deployment()


# ---------------------------------------------------------------------------
# Vertex URI keyless ADC fallback (#4)
# ---------------------------------------------------------------------------


def test_vertex_uri_keyless_falls_back_to_adc(_clean_env) -> None:
    _clean_env.setenv(
        ENV_DEPLOYMENT_URI, "vertex://my-gcp-project/us-central1/claude-3-opus"
    )
    dep = resolve_env_deployment()
    assert dep.preset_name == "vertex_claude"
    assert dep.auth.auth_strategy_kind() == "gcp_adc"
