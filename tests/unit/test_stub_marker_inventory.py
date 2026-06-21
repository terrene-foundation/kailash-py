"""CI guard for the Production/Stable stub-marker inventory (issue #1406).

`kailash` is published ``Development Status :: 5 - Production/Stable``
(``pyproject.toml:16``). That classifier promises a complete, supported public
surface. ``STUB-MARKER-INVENTORY.md`` is the auditable record backing the promise:
every stub marker in ``src/kailash`` is enumerated and categorised there.

This test pins the **per-file** marker counts to the machine-readable baseline
embedded in that inventory, so the marker population cannot grow (or shrink)
silently without the inventory being updated in the same change. The inventory is
the single source of truth — there is no separate baseline file to drift from it.

Mechanical only: it greps ``src/kailash`` with the canonical regex and compares.
The *categorisation* (false-positive vs sentinel vs gap) lives in the inventory and
is a human-reviewed concern; this guard just enforces that the raw set is accounted
for.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

# Canonical marker set: the tokens named in issue #1406 (TODO/FIXME/HACK/XXX/
# NotImplementedError) plus STUB from zero-tolerance.md Rule 2. Identical to the
# `grep -E` form documented in STUB-MARKER-INVENTORY.md.
MARKER_RE = re.compile(r"\b(?:TODO|FIXME|HACK|STUB|XXX)\b|NotImplementedError")

_BASELINE_BLOCK_RE = re.compile(
    r"<!--\s*STUB-MARKER-BASELINE-JSON\s*(?P<json>\{.*?\})\s*STUB-MARKER-BASELINE-JSON\s*-->",
    re.DOTALL,
)

_REGEN_HINT = (
    "Regenerate the per-file map with:\n"
    "  grep -rIlE '\\b(TODO|FIXME|HACK|STUB|XXX)\\b|NotImplementedError' "
    "src/kailash --include='*.py' | sort | while read -r f; do "
    "printf '%s %s\\n' \"$(grep -cE '\\b(TODO|FIXME|HACK|STUB|XXX)\\b|"
    'NotImplementedError\' "$f")" "$f"; done'
)


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file() and (
            parent / "src" / "kailash"
        ).is_dir():
            return parent
    raise AssertionError("could not locate repo root (pyproject.toml + src/kailash)")


def _load_baseline() -> dict:
    inv = _repo_root() / "STUB-MARKER-INVENTORY.md"
    assert inv.is_file(), (
        f"{inv} is missing — it is the auditable record for issue #1406 and the "
        "source of truth for this guard."
    )
    m = _BASELINE_BLOCK_RE.search(inv.read_text(encoding="utf-8"))
    assert m, (
        "Could not find the STUB-MARKER-BASELINE-JSON block in "
        "STUB-MARKER-INVENTORY.md. The block is delimited by "
        "'<!-- STUB-MARKER-BASELINE-JSON ... STUB-MARKER-BASELINE-JSON -->'."
    )
    return json.loads(m.group("json"))


def _current_per_file(scope: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in sorted(scope.rglob("*.py")):
        n = sum(
            1
            for line in path.read_text(encoding="utf-8").splitlines()
            if MARKER_RE.search(line)
        )
        if n:
            counts[path.relative_to(scope.parent.parent).as_posix()] = n
    return counts


@pytest.fixture(scope="module")
def baseline() -> dict:
    return _load_baseline()


def test_inventory_baseline_parses(baseline: dict) -> None:
    assert baseline["scope"] == "src/kailash"
    assert isinstance(baseline["per_file"], dict) and baseline["per_file"]


def test_per_file_marker_counts_match_inventory(baseline: dict) -> None:
    """The core guard: the live src/kailash marker set must match the inventory.

    A failure here means a stub marker was added, removed, or moved between files
    without ``STUB-MARKER-INVENTORY.md`` being updated. Resolve it by categorising
    the change in that file (false-positive / sentinel / gap, + public-reachability)
    and updating its baseline block in the same commit.
    """
    root = _repo_root()
    current = _current_per_file(root / "src" / "kailash")
    expected = baseline["per_file"]

    if current != expected:
        added = {f: current[f] for f in current.keys() - expected.keys()}
        removed = {f: expected[f] for f in expected.keys() - current.keys()}
        changed = {
            f: f"{expected[f]} -> {current[f]}"
            for f in current.keys() & expected.keys()
            if current[f] != expected[f]
        }
        raise AssertionError(
            "Stub-marker drift vs STUB-MARKER-INVENTORY.md "
            "(kailash is Production/Stable — every marker must be inventoried).\n"
            f"  files with NEW markers:     {added or '{}'}\n"
            f"  files with REMOVED markers: {removed or '{}'}\n"
            f"  files with COUNT CHANGE:    {changed or '{}'}\n"
            "Update STUB-MARKER-INVENTORY.md (categorise the change + its baseline "
            "block) in the same commit.\n"
            f"{_REGEN_HINT}"
        )


def test_total_matches_inventory(baseline: dict) -> None:
    root = _repo_root()
    current_total = sum(_current_per_file(root / "src" / "kailash").values())
    assert current_total == baseline["total"], (
        f"src/kailash has {current_total} stub-marker lines; "
        f"STUB-MARKER-INVENTORY.md baseline says {baseline['total']}. "
        "Update the inventory."
    )


def test_category_tally_is_internally_consistent(baseline: dict) -> None:
    tally = baseline["category_tally"]
    assert sum(tally.values()) == baseline["total"], (
        f"category_tally {tally} sums to {sum(tally.values())} but total is "
        f"{baseline['total']} — the inventory's own numbers disagree."
    )
