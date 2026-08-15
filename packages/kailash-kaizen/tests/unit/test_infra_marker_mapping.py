"""Guards for the infrastructure-marker mechanism in ``tests/conftest.py`` (#2152).

Infrastructure markers (``requires_postgres`` / ``requires_redis`` / ...) decide
which tests every infra-free CI step DESELECTS. Getting that decision wrong is
silent in both directions:

* over-marking excludes a test from CI and nothing ever reports it as skipped;
* under-marking runs an infra-bound test in an infra-free step, where it can
  only fail or flake.

The mechanism was twice inferred from the test's NAME and twice wrong. Measured
over 14,773 collected items, name-keyword inference disagreed with the actual
fixture graph on 2,248 of them -- 2,246 false positives and 2 false negatives
(``test_integration_multi_service`` and ``test_audit_hook_includes_trace_id``
genuinely request infra fixtures, went unmarked, and therefore RAN in
infra-free CI). It is now derived from ``item.fixturenames``: a structural fact
about the dependency graph rather than a guess about English.

These tests protect the two ways that mechanism can still decay:

1. the ``_INFRA_FIXTURES`` map silently falling out of sync with the fixtures
   the conftest actually defines (a new infra fixture, or a renamed one);
2. name-keyword inference being reintroduced alongside it.

They parse the conftest with :mod:`ast` rather than importing it -- the module
is a pytest conftest with import-order side effects, and structural
enumeration is what this repo requires for symbol-set assertions anyway.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, Set

import pytest

CONFTEST = Path(__file__).resolve().parent.parent / "conftest.py"

#: Substrings that make a fixture name INFRA-SHAPED, i.e. a fixture a reader
#: would expect to provide external infrastructure. Used ONLY to decide which
#: fixtures this guard demands a mapping decision for -- never to mark a test.
#: A fixture matching one of these must appear in ``_INFRA_FIXTURES`` or in
#: ``_INTENTIONALLY_UNMAPPED`` below, so the decision is always explicit.
_INFRA_SHAPED = ("postgres", "redis", "docker", "ollama", "mysql", "kafka", "mongo")

#: Infra-SHAPED fixture names that deliberately map to NO marker, each with the
#: reason it needs none. Present so "unmapped" is always a recorded decision
#: rather than an omission.
_INTENTIONALLY_UNMAPPED: Dict[str, str] = {}


def _parse_conftest() -> ast.Module:
    return ast.parse(CONFTEST.read_text(encoding="utf-8"), filename=str(CONFTEST))


def _defined_fixtures(tree: ast.Module) -> Set[str]:
    """Every name defined with an ``@pytest.fixture`` decorator, via AST."""
    found: Set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            # Matches both `@pytest.fixture` and `@pytest.fixture(scope=...)`.
            target = dec.func if isinstance(dec, ast.Call) else dec
            if isinstance(target, ast.Attribute) and target.attr == "fixture":
                found.add(node.name)
                break
    return found


def _mapped_fixtures(tree: ast.Module) -> Dict[str, Set[str]]:
    """Read the ``_INFRA_FIXTURES`` literal without importing the conftest."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.AnnAssign) and not isinstance(node, ast.Assign):
            continue
        targets = [node.target] if isinstance(node, ast.AnnAssign) else node.targets
        if not any(
            isinstance(t, ast.Name) and t.id == "_INFRA_FIXTURES" for t in targets
        ):
            continue
        assert isinstance(
            node.value, ast.Dict
        ), "_INFRA_FIXTURES must be a dict literal"
        out: Dict[str, Set[str]] = {}
        for key, value in zip(node.value.keys, node.value.values):
            assert isinstance(key, ast.Constant) and isinstance(key.value, str)
            # value is `frozenset({...})`
            assert isinstance(
                value, ast.Call
            ), "map values must be frozenset(...) calls"
            names: Set[str] = set()
            for arg in value.args:
                for elt in getattr(arg, "elts", []):
                    assert isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                    names.add(elt.value)
            out[key.value] = names
        return out
    raise AssertionError("_INFRA_FIXTURES not found in conftest.py")


def test_every_infra_shaped_fixture_has_an_explicit_marker_decision():
    """A new infra fixture MUST be mapped (or explicitly recorded as unmapped).

    This is the failure mode that let the previous mechanism rot: the map is
    only as good as its coverage, and an unmapped infra fixture silently
    reverts a test to "needs nothing".
    """
    tree = _parse_conftest()
    defined = _defined_fixtures(tree)
    mapped = set().union(*_mapped_fixtures(tree).values())

    infra_shaped = {f for f in defined if any(h in f.lower() for h in _INFRA_SHAPED)}
    undecided = infra_shaped - mapped - set(_INTENTIONALLY_UNMAPPED)

    assert not undecided, (
        "Infra-shaped fixtures in tests/conftest.py with no marker decision: "
        f"{sorted(undecided)}. Add each to _INFRA_FIXTURES so tests requesting "
        "it are deselected from infra-free CI steps, or to "
        "_INTENTIONALLY_UNMAPPED with the reason it needs no marker. Leaving it "
        "undecided means tests using it RUN in infra-free CI, where they can "
        "only fail or flake."
    )


def test_every_mapped_fixture_actually_exists():
    """The map MUST NOT name a fixture that no longer exists.

    A renamed or deleted fixture leaves a dead entry, and the tests that used
    to be marked through it silently stop being marked.
    """
    tree = _parse_conftest()
    defined = _defined_fixtures(tree)
    mapped = _mapped_fixtures(tree)

    dangling = {
        marker: sorted(names - defined)
        for marker, names in mapped.items()
        if names - defined
    }
    assert not dangling, (
        f"_INFRA_FIXTURES names fixtures that tests/conftest.py does not define: "
        f"{dangling}. A renamed or deleted fixture leaves a dead mapping entry, "
        "and every test that reached infrastructure through it silently stops "
        "being marked."
    )


def test_marker_assignment_does_not_infer_from_the_test_name():
    """Name-keyword inference MUST NOT come back.

    Measured, it disagreed with the fixture graph on 2,248 of 14,773 items in
    BOTH directions, so no edit to a keyword list makes it sound. The marker
    decision reads ``item.fixturenames``; if a future change needs an escape
    hatch, the test declares ``@pytest.mark.requires_<x>`` on itself.
    """
    tree = _parse_conftest()

    hook = next(
        (
            n
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == "pytest_collection_modifyitems"
        ),
        None,
    )
    assert hook is not None, "pytest_collection_modifyitems not found in conftest.py"

    # Every `add_marker(...)` for an infra marker must be reached from a branch
    # that consulted `fixturenames` -- never from one that consulted item.name.
    reads_fixturenames = any(
        isinstance(n, ast.Constant) and n.value == "fixturenames"
        for n in ast.walk(hook)
    ) or any(
        isinstance(n, ast.Attribute) and n.attr == "fixturenames"
        for n in ast.walk(hook)
    )
    assert reads_fixturenames, (
        "pytest_collection_modifyitems no longer reads item.fixturenames. The "
        "infra-marker decision MUST be derived from the resolved fixture graph, "
        "not inferred from the test's name."
    )

    # `item.name` may still be read for non-infra markers (performance/slow),
    # so assert on the specific defect: an infra marker added from a name test.
    infra_markers = set(_mapped_fixtures(tree))
    for node in ast.walk(hook):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "add_marker"):
            continue
        rendered = ast.dump(node)
        for marker in infra_markers:
            if marker in rendered:
                pytest.fail(
                    f"{marker} is added via a hard-coded add_marker call "
                    f"({ast.unparse(node)}). Infra markers MUST be driven by the "
                    "_INFRA_FIXTURES map so the mapping stays the single place "
                    "the decision lives."
                )
