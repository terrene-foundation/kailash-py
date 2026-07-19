# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression: the pytest LLM cost-guard actively withholds provider secrets.

Guards issue #1845 — a bare ``pytest`` must make ZERO billed LLM calls even when
a real provider credential sits in ``.env`` or is exported in the shell. These
tests pin the failure modes a security review found against the first
(decline-to-add) design: an incomplete name predicate (``AWS_BEARER_TOKEN_BEDROCK``),
re-injection via a later ``load_dotenv()``, and an inherited/exported key.
"""

import os

import pytest

from kailash.testing.env_cost_guard import (
    install_dotenv_guard,
    is_provider_secret,
    scrub_provider_secrets,
)

# Every provider-credential family a bare run must withhold — including the ones
# the original `*_API_KEY` / `*_SECRET` predicate missed.
SECRET_NAMES = [
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "DEEPSEEK_API_KEY",
    "MISTRAL_API_KEY",
    "AWS_BEARER_TOKEN_BEDROCK",  # live in this repo's .env; ends in neither _API_KEY nor _SECRET
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "REPLICATE_API_TOKEN",
    "HF_TOKEN",
    "HUGGING_FACE_HUB_TOKEN",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "AZURE_OPENAI_KEY",
    "AZURE_OPENAI_AD_TOKEN",
    "DB_PASSWORD",
]

# Non-secret config that MUST still load on a bare run.
NON_SECRET_NAMES = [
    "OPENAI_PROD_MODEL",
    "OPENAI_DEV_MODEL",
    "DEFAULT_LLM_MODEL",
    "DATABASE_URL",
    "REDIS_URL",
    "KAIZEN_ALLOW_REAL_LLM",
    "AWS_REGION",
    "OPENAI_API_VERSION",
]


@pytest.mark.regression
@pytest.mark.parametrize("name", SECRET_NAMES)
def test_predicate_flags_every_credential_family(name):
    assert is_provider_secret(name) is True, f"{name} must be treated as a secret"


@pytest.mark.regression
@pytest.mark.parametrize("name", NON_SECRET_NAMES)
def test_predicate_passes_non_secret_config(name):
    assert is_provider_secret(name) is False, f"{name} is non-secret config"


@pytest.mark.regression
def test_scrub_removes_secrets_keeps_config(monkeypatch):
    monkeypatch.delenv("KAIZEN_ALLOW_REAL_LLM", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-be-removed")
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "BedrockAPIKey-should-be-removed")
    monkeypatch.setenv("OPENAI_PROD_MODEL", "gpt-5.6-sol")

    removed = scrub_provider_secrets()

    assert "OPENAI_API_KEY" not in os.environ
    assert "AWS_BEARER_TOKEN_BEDROCK" not in os.environ
    assert set(removed) >= {"OPENAI_API_KEY", "AWS_BEARER_TOKEN_BEDROCK"}
    # Non-secret config is untouched.
    assert os.environ.get("OPENAI_PROD_MODEL") == "gpt-5.6-sol"


@pytest.mark.regression
def test_opt_in_preserves_secrets(monkeypatch):
    monkeypatch.setenv("KAIZEN_ALLOW_REAL_LLM", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-opted-in")
    assert scrub_provider_secrets() == []
    assert os.environ.get("OPENAI_API_KEY") == "sk-opted-in"


@pytest.mark.regression
def test_monkeypatched_load_dotenv_scrubs_reinjection(tmp_path, monkeypatch):
    """A later load_dotenv() (the C-2 re-injection vector) must self-scrub."""
    monkeypatch.delenv("KAIZEN_ALLOW_REAL_LLM", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text("OPENAI_API_KEY=sk-reinjected\nOPENAI_PROD_MODEL=gpt-5.6-sol\n")

    install_dotenv_guard()
    from dotenv import load_dotenv  # picks up the wrapped version

    load_dotenv(str(env))

    # The guard scrubbed the re-injected secret but kept the model.
    assert os.environ.get("OPENAI_API_KEY") is None
    assert os.environ.get("OPENAI_PROD_MODEL") == "gpt-5.6-sol"


@pytest.mark.regression
def test_bare_session_has_no_provider_secret_in_environ():
    """End-to-end: under this (bare) pytest session the real .env secrets are gone."""
    if os.environ.get("KAIZEN_ALLOW_REAL_LLM") == "1":
        pytest.skip("real-LLM opt-in on; secrets are intentionally present")
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "AWS_BEARER_TOKEN_BEDROCK"):
        assert os.environ.get(name) is None, f"{name} leaked into a bare pytest session"
