"""Pin top-level import resolution to this checkout without loading optional extras.

The core CI environment need not install every package's runtime dependencies.
A top-level ModuleSpec identifies the loader and source that an import will use,
without executing that package's __init__. The separate core import check below
still verifies the installed core runtime exports its version.
"""

import importlib.util
import os

import pytest

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", ".."))

# module name -> source root, relative to the repo root
EXPECTED_SOURCE_ROOT = {
    "kailash": "src",
    "dataflow": "packages/kailash-dataflow/src",
    "kaizen": "packages/kailash-kaizen/src",
    "nexus": "packages/kailash-nexus/src",
    "pact": "packages/kailash-pact/src",
    "kailash_mcp": "packages/kailash-mcp/src",
    "kailash_ml": "packages/kailash-ml/src",
    "kailash_align": "packages/kailash-align/src",
    "kaizen_agents": "packages/kaizen-agents/src",
}


def _resolved_location(spec):
    """Resolve regular and namespace package locations from their import specs."""
    if spec.origin and spec.origin not in {"built-in", "frozen"}:
        return os.path.realpath(spec.origin)
    paths = list(spec.submodule_search_locations or [])
    return os.path.realpath(paths[0]) if paths else None


def _assert_checkout_location(module_name, source_root):
    spec = importlib.util.find_spec(module_name)
    assert spec is not None, f"{module_name} has no import spec"
    location = _resolved_location(spec)
    assert location is not None, f"{module_name} resolved to no location at all"
    expected_prefix = os.path.realpath(source_root)
    assert location.startswith(expected_prefix + os.sep), (
        f"{module_name} resolves to {location}, not to {expected_prefix}. "
        "Check pytest.ini::pythonpath before running package tests."
    )


@pytest.mark.parametrize(
    ("module_name", "source_root"), sorted(EXPECTED_SOURCE_ROOT.items())
)
def test_package_resolves_from_this_checkout(module_name, source_root):
    _assert_checkout_location(module_name, os.path.join(REPO_ROOT, source_root))


@pytest.mark.parametrize("namespace", [False, True])
def test_resolution_check_rejects_another_checkout(tmp_path, monkeypatch, namespace):
    """A different source tree must fail even when importing it would succeed."""
    foreign = tmp_path / "foreign"
    package = foreign / "checkout_resolution_control"
    package.mkdir(parents=True)
    if not namespace:
        (package / "__init__.py").write_text(
            "raise AssertionError('resolution must not execute package code')\n"
        )
    monkeypatch.syspath_prepend(str(foreign))
    _assert_checkout_location("checkout_resolution_control", str(foreign))
    with pytest.raises(AssertionError, match="resolves to"):
        _assert_checkout_location(
            "checkout_resolution_control", str(tmp_path / "expected")
        )


def test_kailash_exposes_version():
    """A namespace-package shadow imports fine but carries no attributes."""
    import kailash

    assert getattr(kailash, "__file__", None) is not None, (
        "kailash resolved as a namespace package (no __init__.py on the "
        "winning path entry) — every `from kailash import __version__` fails."
    )
    assert isinstance(kailash.__version__, str)
