"""Issue #2023 — CI lint: root-editable installs must declare their siblings.

A workflow step that installs the root ``kailash`` package editable from the
branch, but lets a sibling package (kailash-dataflow, kailash-ml,
kailash-align, ...) resolve from PyPI, is testing a combination the monorepo
never ships: branch-core + released-sibling. When the branch changes a
cross-package interface, that step fails in a way no source inspection
explains — or, worse, passes while the real shipped pairing is broken.

#2023 cost one debugging cycle to that class:

    TypeError: _validate_identifier() missing 1 required keyword-only
    argument: max_length
    .venv/lib/python3.12/site-packages/dataflow/core/nodes.py:3620

Root ``kailash`` came from the branch (carrying #1971's now-required
keyword-only ``max_length``); ``kailash-dataflow`` came from PyPI at 2.19.1,
which still called it positionally.

The fix #2023 asks for is per-step reasoning, not a blanket install: install a
sibling editable when the step actually exercises that sibling, and RECORD the
determination in a comment so the next reader does not re-derive it. This test
is the enforcement half of that — AC#3 of #2023.

RATCHET SEMANTICS
-----------------
``GRANDFATHERED`` below lists sites that predate this lint and have not yet had
their sibling determination measured. The list may only SHRINK. Removing an
entry means someone measured that step's real import graph (see
``MEASUREMENT_RECIPE``) and wrote the answer into the step. Adding an entry is
a regression and should not pass review.

TRIGGER GAP (recorded deliberately)
-----------------------------------
This test lives in ``tests/regression/``, which unified-ci.yml gates on every
PR as of #2002. That workflow's ``paths:`` filter covers ``src/**``,
``packages/**``, ``tests/**``, ``pyproject.toml``, ``uv.lock`` and
``unified-ci.yml`` — it does NOT cover ``.github/workflows/**`` generally. So a
PR that ONLY edits, say, ``test-kailash-ml.yml`` does not run this lint. Closing
that would mean firing the full 4-version matrix on every workflow-only edit,
a compute trade-off that belongs to whoever owns the CI budget, not to this
test. Documented rather than silently assumed.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.regression

WORKFLOWS_DIR = Path(__file__).resolve().parents[2] / ".github" / "workflows"

# `uv pip install -e "."` or `-e ".[extras]"` — the root package, editable.
ROOT_EDITABLE_RE = re.compile(r'uv\s+pip\s+install\s+-e\s+"\.(\[[^"]*\])?"')

# The marker a compliant step carries. Grep-able on purpose.
DECLARATION_MARKER = "#2023 SIBLING DECLARATION"

# A step begins at a `- name:` or `- uses:` list item.
STEP_START_RE = re.compile(r"^\s*-\s+(name|uses):")
STEP_NAME_RE = re.compile(r"^\s*-\s+name:\s*(.+?)\s*$")

MEASUREMENT_RECIPE = """
To retire a GRANDFATHERED entry, MEASURE the step rather than guessing.

Write a pytest plugin that reports sibling module residency, e.g.:

    # sibprobe.py
    import sys
    def pytest_collection_finish(session):
        for mod in ("dataflow", "kailash_align", "kailash_ml", "kailash"):
            hit = [k for k in sys.modules if k == mod or k.startswith(mod + ".")]
            print(f"SIBPROBE {mod}: {len(hit)}")

then run the step's EXACT pytest selection through it:

    PYTHONPATH=. pytest <the step's paths> -m '<the step's marker expr>' \\
        -p sibprobe --collect-only -q

A count of 0 means the sibling is genuinely not exercised (leave it resolving
from PyPI and say so in-comment); a non-zero count means it IS exercised and
must be installed editable. Note that collection imports EVERY module under a
named directory BEFORE `-m` deselects anything, so a step naming a whole tests/
tree exercises whatever that tree imports at module scope, regardless of which
tests the marker filter finally selects.
"""

# (workflow filename, step name) pairs whose sibling determination has NOT yet
# been measured. MAY ONLY SHRINK.
#
# Note that a name is not unique within a file — "unified-ci.yml ::
# Install dependencies" covers FIVE distinct steps. An entry is therefore
# retired only when EVERY step sharing that name carries a declaration, which
# is what `test_grandfather_list_only_shrinks` enforces. Renaming the steps to
# something distinct would tighten this, and is worth doing when someone next
# measures that file.
GRANDFATHERED: set[tuple[str, str]] = {
    ("cross-sdk-interop.yml", "Install dependencies"),
    ("security-tests.yml", "Install dependencies"),
    ("test-kailash-kaizen.yml", "Install kailash-kaizen[dev] + sibling packages"),
    ("trust-tests.yml", "Install dependencies"),
    ("unified-ci.yml", "Install dependencies"),
}


def _iter_steps(text: str):
    """Yield (step_name, step_body) for each step block in a workflow file.

    Comment-preserving: this is a TEXT scan, not a YAML parse, because the
    declaration lives in `#` comments that any YAML loader discards.
    """
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if STEP_START_RE.match(line)]
    for idx, start in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else len(lines)
        block = lines[start:end]
        match = STEP_NAME_RE.match(lines[start])
        name = match.group(1).strip("\"'") if match else "<unnamed step>"
        yield name, "\n".join(block)


def _root_editable_sites() -> list[tuple[str, str, str]]:
    """Return (workflow_filename, step_name, step_body) for each install site."""
    sites = []
    for path in sorted(WORKFLOWS_DIR.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        if not ROOT_EDITABLE_RE.search(text):
            continue
        for step_name, body in _iter_steps(text):
            if ROOT_EDITABLE_RE.search(body):
                sites.append((path.name, step_name, body))
    return sites


def test_workflows_dir_is_discoverable():
    """Guard: the lint below is vacuous if the glob finds nothing."""
    assert WORKFLOWS_DIR.is_dir(), f"workflows dir not found at {WORKFLOWS_DIR}"
    sites = _root_editable_sites()
    assert len(sites) >= 10, (
        f"Only {len(sites)} root-editable install sites found under "
        f"{WORKFLOWS_DIR}. Expected at least 10. Either the workflows moved or "
        "ROOT_EDITABLE_RE stopped matching — in both cases the lint below is "
        "silently passing on an empty set and must be repaired, not deleted."
    )


def test_every_root_editable_install_declares_its_siblings():
    """Every step installing root kailash editable declares its siblings.

    #2023 AC#3. A step that resolves a sibling from PyPI while the root package
    comes from the branch is testing a pairing the monorepo never ships; the
    declaration is what stops the next reader re-deriving that reasoning, or
    (worse) not realising there was any to do.
    """
    undeclared = [
        (workflow, step)
        for workflow, step, body in _root_editable_sites()
        if DECLARATION_MARKER not in body and (workflow, step) not in GRANDFATHERED
    ]

    assert not undeclared, (
        "These workflow steps install root `kailash` editable without declaring "
        "which sibling packages they exercise and how each resolves:\n\n"
        + "\n".join(f"  {workflow} :: {step}" for workflow, step in undeclared)
        + "\n\nAdd a comment inside the step containing the marker "
        f"'{DECLARATION_MARKER}', naming each sibling and whether it is "
        "exercised, with the measured evidence.\n" + MEASUREMENT_RECIPE
    )


def test_grandfather_list_only_shrinks():
    """Every grandfathered entry still exists and still lacks a declaration.

    Without this, the list rots: an entry whose step was renamed or which
    quietly gained a declaration would sit there forever, and a NEW undeclared
    step reusing that (workflow, step-name) pair would inherit the exemption.
    """
    # A (workflow, step-name) key can cover MORE THAN ONE step — step names are
    # not unique within a file. Collect every body under the key, so a key is
    # only "now declared" when all of its steps are.
    sites: dict[tuple[str, str], list[str]] = {}
    for workflow, step, body in _root_editable_sites():
        sites.setdefault((workflow, step), []).append(body)

    stale_missing = sorted(key for key in GRANDFATHERED if key not in sites)
    assert not stale_missing, (
        "GRANDFATHERED names sites that no longer install root kailash editable "
        "(renamed or removed). Delete these entries:\n"
        + "\n".join(f"  {workflow} :: {step}" for workflow, step in stale_missing)
    )

    now_declared = sorted(
        key
        for key in GRANDFATHERED
        if all(DECLARATION_MARKER in body for body in sites[key])
    )
    assert not now_declared, (
        "These sites are grandfathered but now carry a sibling declaration. "
        "Delete them from GRANDFATHERED so the exemption cannot be reused:\n"
        + "\n".join(f"  {workflow} :: {step}" for workflow, step in now_declared)
    )
