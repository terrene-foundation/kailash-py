"""
Pytest configuration for DataFlow tests.

Ensures that the src directory is in sys.path for proper imports, and installs
the repo LLM cost-guard. DataFlow declares its own pytest rootdir, so the
repo-root conftest guard never fires for `pytest packages/kailash-dataflow` —
and `DataFlow.from_brief()` makes a real billed LLM call (`BaseAgent.run`), so
this rootdir MUST withhold/scrub provider secrets on a bare run.
"""

import sys
from pathlib import Path

from kailash.testing.env_cost_guard import install_cost_guard, scrub_provider_secrets

# Add src directory to sys.path
src_dir = Path(__file__).parent / "src"
if src_dir.exists() and str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

# LLM cost-guard: a bare `pytest packages/kailash-dataflow` must make ZERO billed
# LLM calls even with a provider key in .env or exported in the shell.
install_cost_guard(Path(__file__).resolve().parents[2] / ".env")


def pytest_collection_finish(session):
    """Backstop: remove any provider secret re-injected during collection."""
    scrub_provider_secrets()
