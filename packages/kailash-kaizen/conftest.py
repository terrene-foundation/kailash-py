"""
Pytest configuration for Kaizen tests.

Ensures that the src directory is in sys.path for proper imports, and installs
the repo LLM cost-guard at the PACKAGE ROOT so an explicit
`pytest packages/kailash-kaizen/examples/...` invocation is covered too (the
tests/-subtree conftest guard only covers `packages/kailash-kaizen/tests`).
kailash-kaizen declares its own pytest rootdir, so the repo-root conftest guard
never fires for `pytest packages/kailash-kaizen` — and a bare run MUST make ZERO
billed LLM calls, so this rootdir MUST withhold/scrub provider secrets.

The root conftest.py's ``requires_real_llm`` marker-skip enforcement
(``pytest_collection_modifyitems``) is duplicated here for the SAME reason:
a marker registered in ``pytest.ini`` (satisfying ``--strict-markers``) but
never actually CHECKED is a fake gate (rules/testing.md § "Pytest Plugin +
Marker Declaration Pair"; the checked half is a MUST, not optional) — every
``@pytest.mark.requires_real_llm`` test would otherwise run un-skipped
(and un-guarded) whenever invoked via kailash-kaizen's own rootdir, exactly
as the un-scrubbed-secret gap this file's cost-guard half already closes.
"""

import os
import sys
from pathlib import Path

import pytest

from kailash.testing.env_cost_guard import install_cost_guard, scrub_provider_secrets

# Add src directory to sys.path
src_dir = Path(__file__).parent / "src"
if src_dir.exists() and str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

# LLM cost-guard: a bare `pytest packages/kailash-kaizen` must make ZERO billed
# LLM calls even with a provider key in .env or exported in the shell.
install_cost_guard(Path(__file__).resolve().parents[2] / ".env")

_REAL_LLM_ENV_FLAG = "KAIZEN_ALLOW_REAL_LLM"
_REAL_LLM_MARKER = "requires_real_llm"


def pytest_collection_finish(session):
    """Backstop: remove any provider secret re-injected during collection."""
    scrub_provider_secrets()


def pytest_collection_modifyitems(config, items):
    """Skip every ``requires_real_llm`` test unless the operator opted in.

    Mirrors the root conftest.py's hook of the same name EXACTLY (same env
    flag, same marker name) — this is the checked half of the marker gate
    for invocations that resolve kailash-kaizen's own rootdir (which never
    loads the repo-root conftest.py — see module docstring).
    """
    if os.environ.get(_REAL_LLM_ENV_FLAG) == "1":
        return
    skip_real_llm = pytest.mark.skip(
        reason=f"real-LLM opt-in off (set {_REAL_LLM_ENV_FLAG}=1)"
    )
    for item in items:
        if _REAL_LLM_MARKER in item.keywords:
            item.add_marker(skip_real_llm)
