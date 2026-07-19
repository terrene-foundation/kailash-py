"""
Root conftest.py — Auto-loads .env for ALL pytest sessions, with an LLM cost-guard.

This ensures environment variables (model names, database URLs, non-secret config)
are available in every test without manual setup. Works with any Kailash project.

Cost-guard (defense-in-depth against accidental billed LLM calls)
-----------------------------------------------------------------
A bare ``pytest`` run MUST make ZERO real LLM calls — even on a machine where a
production provider key sits in ``.env``. Two independent layers enforce this:

1. **Provider-secret gating in .env injection.** When
   ``os.environ.get("KAIZEN_ALLOW_REAL_LLM") != "1"``, provider secret keys
   (``OPENAI_API_KEY``, ``ANTHROPIC_API_KEY``, ``GOOGLE_API_KEY``,
   ``GEMINI_API_KEY``, ``DEEPSEEK_API_KEY``, ``MISTRAL_API_KEY``, plus any
   ``*_API_KEY`` / ``*_SECRET``) are NOT injected from ``.env`` into the process
   environment. Model names, DB URLs, and every other non-secret var still load
   normally, and an already-set env var is never overridden. A test that would
   reach a provider therefore finds no credential and cannot bill.

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

# Explicit provider secret keys severed from the default pytest path.
_PROVIDER_SECRET_KEYS = frozenset(
    {
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "DEEPSEEK_API_KEY",
        "MISTRAL_API_KEY",
    }
)

_REAL_LLM_ENV_FLAG = "KAIZEN_ALLOW_REAL_LLM"
_REAL_LLM_MARKER = "requires_real_llm"


def _real_llm_allowed() -> bool:
    """True only when the operator has explicitly opted into real LLM calls."""
    return os.environ.get(_REAL_LLM_ENV_FLAG) == "1"


def _is_provider_secret(key: str) -> bool:
    """A key is a provider secret if it's an explicit provider key OR matches
    the generic ``*_API_KEY`` / ``*_SECRET`` secret-name conventions."""
    return (
        key in _PROVIDER_SECRET_KEYS
        or key.endswith("_API_KEY")
        or key.endswith("_SECRET")
    )


def pytest_configure(config):
    """Load .env at the very start of the pytest session."""
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        _load_env(env_path)


def _load_env(env_path: Path):
    """Parse .env and inject into os.environ (lightweight, no dependencies).

    Provider secret keys are withheld unless ``KAIZEN_ALLOW_REAL_LLM=1`` so a
    bare ``pytest`` run cannot make a billed LLM call from a key that only lives
    in ``.env``.
    """
    allow_real_llm = _real_llm_allowed()
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Handle `export VAR=value` syntax
        if line.startswith("export "):
            line = line[7:].strip()
        eq = line.find("=")
        if eq == -1:
            continue
        key = line[:eq].strip()
        val = line[eq + 1 :].strip()
        # Cost-guard: do NOT inject provider secret keys on the default path.
        # Model names, DB URLs, and other non-secret vars still load below.
        if not allow_real_llm and _is_provider_secret(key):
            continue
        # Strip surrounding quotes
        is_quoted = (val.startswith('"') and val.endswith('"') and len(val) >= 2) or (
            val.startswith("'") and val.endswith("'") and len(val) >= 2
        )
        if is_quoted:
            val = val[1:-1]
        else:
            # Strip inline comments for unquoted values (e.g. "value # comment")
            comment_idx = val.find(" #")
            if comment_idx > -1:
                val = val[:comment_idx].strip()
        # Only set if not already in environment (don't override explicit env)
        if key not in os.environ:
            os.environ[key] = val


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
