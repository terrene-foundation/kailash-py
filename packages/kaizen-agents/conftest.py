"""
Pytest configuration for kaizen-agents tests.

Ensures that the src directory is in sys.path for proper imports, and installs
the repo LLM cost-guard at the PACKAGE ROOT so an explicit
`pytest packages/kaizen-agents/examples/...` invocation is covered too (the
tests/-subtree conftest guard only covers `packages/kaizen-agents/tests`).
kaizen-agents declares its own pytest rootdir, so the repo-root conftest guard
never fires for `pytest packages/kaizen-agents` — and a bare run MUST make ZERO
billed LLM calls, so this rootdir MUST withhold/scrub provider secrets.

The cost-guard has TWO halves and this rootdir previously carried only one.
The repo-root conftest pairs the active secret scrub with an opt-in MARKER
GATE (`requires_real_llm` skipped unless `KAIZEN_ALLOW_REAL_LLM=1`); only the
scrub was ported here. A test that needs a live judge therefore ran anyway,
against a scrubbed credential, and "passed" through whatever fallback its
subject offered — the #1981 fake-pass shape. Both halves now live here, so
the marker is a real gate rather than a registered-but-unchecked one.
"""

import os
import sys
from pathlib import Path

import pytest

from kailash.testing.env_cost_guard import install_cost_guard, scrub_provider_secrets

_REAL_LLM_ENV_FLAG = "KAIZEN_ALLOW_REAL_LLM"
_REAL_LLM_MARKER = "requires_real_llm"

# Add src directory to sys.path
src_dir = Path(__file__).parent / "src"
if src_dir.exists() and str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

# LLM cost-guard: a bare `pytest packages/kaizen-agents` must make ZERO billed
# LLM calls even with a provider key in .env or exported in the shell.
install_cost_guard(Path(__file__).resolve().parents[2] / ".env")


def pytest_collection_finish(session):
    """Backstop: remove any provider secret re-injected during collection."""
    scrub_provider_secrets()


def pytest_collection_modifyitems(config, items):
    """Skip every `requires_real_llm` test unless the operator opted in.

    Mirrors the repo-root conftest's checked marker gate. Without it the
    marker is registered but never consulted — a fake gate, and the reason a
    real-LLM test could run credential-less and fake a pass off a fallback.
    """
    if os.environ.get(_REAL_LLM_ENV_FLAG) == "1":
        return
    skip_real_llm = pytest.mark.skip(
        reason=f"real-LLM opt-in off (set {_REAL_LLM_ENV_FLAG}=1)"
    )
    for item in items:
        if _REAL_LLM_MARKER in item.keywords:
            item.add_marker(skip_real_llm)
