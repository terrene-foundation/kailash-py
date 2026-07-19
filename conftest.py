"""
Root conftest.py — Auto-loads .env for ALL pytest sessions, with an active LLM cost-guard.

Environment variables (model names, database URLs, non-secret config) are
available in every test without manual setup. Provider credentials are actively
withheld from a bare run.

Cost-guard (never spend on a bare test run)
-------------------------------------------
A bare ``pytest`` MUST make ZERO billed LLM calls — even when a real provider
credential sits in ``.env`` OR is exported in the shell. The guard is ACTIVE and
process-wide (see ``kailash.testing.env_cost_guard`` for the full rationale):

1. **Active secret scrub.** ``install_cost_guard`` loads ``.env`` with provider
   secret keys withheld, monkeypatches ``dotenv.load_dotenv`` so any later call
   (a sibling test module's module-scope ``load_dotenv()``, a runtime fixture)
   self-scrubs, and POPS any provider secret already in ``os.environ`` — closing
   the incomplete-name, re-injection, and inherited-key vectors a decline-to-add
   loader cannot. The comprehensive predicate covers every credential family
   (``*_API_KEY`` / ``*_SECRET`` / ``*_TOKEN`` / ``*_CREDENTIALS`` /
   ``AWS_BEARER_TOKEN_*`` / ``*ACCESS_KEY*`` …). Model names, DB URLs, and other
   non-secret vars still load; already-set non-secret vars are never overridden.
   ``pytest_collection_finish`` re-scrubs after every module is imported.

2. **Opt-in marker gate.** Tests marked ``@pytest.mark.requires_real_llm`` are
   SKIPPED unless ``KAIZEN_ALLOW_REAL_LLM=1`` (see ``pytest_collection_modifyitems``).
   The marker is registered in ``pytest.ini`` and checked here — a marker that is
   registered but never checked is a fake gate.

To run real-LLM tests deliberately (real calls, real cost):

    KAIZEN_ALLOW_REAL_LLM=1 .venv/bin/python -m pytest -m requires_real_llm

Real-LLM tests should request the ``dev_model`` fixture so they hit the cheap
model rather than an expensive default.
"""

import os
from pathlib import Path

import pytest

from kailash.testing.env_cost_guard import install_cost_guard, scrub_provider_secrets

_REAL_LLM_ENV_FLAG = "KAIZEN_ALLOW_REAL_LLM"
_REAL_LLM_MARKER = "requires_real_llm"


def _real_llm_allowed() -> bool:
    """True only when the operator has explicitly opted into real LLM calls."""
    return os.environ.get(_REAL_LLM_ENV_FLAG) == "1"


def pytest_configure(config):
    """Install the active cost-guard at the very start of the pytest session.

    Runs before collection, so the ``dotenv.load_dotenv`` monkeypatch is active
    before any nested conftest / test module imports and re-injects a secret.
    """
    install_cost_guard(Path(__file__).parent / ".env")


def pytest_collection_finish(session):
    """Backstop: after every module (and its module-scope ``load_dotenv``) is
    imported, remove any provider secret re-injected during collection."""
    scrub_provider_secrets()


def pytest_collection_modifyitems(config, items):
    """Skip every ``requires_real_llm`` test unless the operator opted in.

    This is the checked half of the marker gate — a marker registered in
    ``pytest.ini`` but never consulted would be a fake gate (BLOCKED).
    """
    if _real_llm_allowed():
        return
    skip_real_llm = pytest.mark.skip(
        reason=f"real-LLM opt-in off (set {_REAL_LLM_ENV_FLAG}=1)"
    )
    for item in items:
        if _REAL_LLM_MARKER in item.keywords:
            item.add_marker(skip_real_llm)


@pytest.fixture(scope="session")
def dev_model() -> str:
    """The cheap model real-LLM tests should use.

    Resolves from .env (per env-models.md: never hardcode the model choice),
    falling back to a low-cost default only as a last resort.
    """
    return (
        os.environ.get("OPENAI_DEV_MODEL")
        or os.environ.get("DEFAULT_LLM_MODEL")
        or "gpt-4o-mini"
    )
