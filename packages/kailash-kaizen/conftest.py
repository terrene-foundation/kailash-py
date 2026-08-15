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
from typing import Iterator, Tuple

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


def _shadowed_first_party_packages() -> Iterator[Tuple[str, Path, Path]]:
    """Yield (module, imported_from, repo_source) for siblings resolved OUTSIDE
    this checkout.

    Only inspects modules ALREADY in ``sys.modules``, so it costs no imports and
    reports exactly what the run actually used.
    """
    repo_root = Path(__file__).resolve().parents[2]
    packages_dir = repo_root / "packages"
    if not packages_dir.is_dir():
        return

    for src_dir in sorted(packages_dir.glob("*/src")):
        for candidate in sorted(src_dir.iterdir()):
            if not (candidate / "__init__.py").is_file():
                continue
            module = sys.modules.get(candidate.name)
            imported_from = getattr(module, "__file__", None)
            if imported_from is None:
                continue
            imported_path = Path(imported_from).resolve()
            if repo_root not in imported_path.parents:
                yield candidate.name, imported_path, candidate


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Report first-party packages served from outside this checkout.

    A sibling package installed as a NON-editable wheel shadows the repo source
    silently, so the suite tests the wheel's code while reporting on the repo's.
    Both failure directions are expensive and neither is self-evident from the
    output: a stale wheel reds tests whose repo source is already correct (and
    the fix gets misattributed to product or test code, which is how correct
    code gets "fixed"), and a wheel NEWER than the branch greens a regression
    the branch actually has.

    Advisory rather than fatal: testing against a released wheel on purpose is
    legitimate, and failing the run would red every suite on any machine with a
    stale sibling. It is printed in the summary, where the reader is already
    looking when results surprise them.
    """
    shadowed = sorted(_shadowed_first_party_packages())
    if not shadowed:
        return

    terminalreporter.section("first-party packages NOT served from this checkout")
    for module, imported_path, repo_source in shadowed:
        package_dir = repo_source.parent.parent
        terminalreporter.write_line(f"  {module}: imported from {imported_path}")
        terminalreporter.write_line(f"  {' ' * len(module)}  repo source {repo_source}")
        terminalreporter.write_line(
            f"  {' ' * len(module)}  fix: uv pip install -e "
            f"{package_dir.relative_to(package_dir.parent.parent)}"
        )
    terminalreporter.write_line(
        "Results above describe the INSTALLED code, not this branch."
    )


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
