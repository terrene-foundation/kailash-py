"""Pin that every first-party package imports from THIS checkout, not site-packages.

The ambient interpreter carries stale, broken installs of `kailash`, `dataflow`,
`kaizen` and `nexus` (directories with no ``__init__.py``, so they import as
namespace packages and every ``from kailash import __version__`` fails).  If
``pythonpath`` in ``pytest.ini`` stops covering a package's source root, that
package's tests silently start exercising site-packages instead of the working
tree.  The failure is invisible: the import succeeds, so the suite stays green
while testing the wrong code.

This asserts the RESOLVED ``__file__`` in-process, which is the only signal that
discriminates repo-resolution from site-packages-resolution.
"""

import importlib
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


def _resolved_location(module):
    """Where a module actually came from, for regular AND namespace packages."""
    if getattr(module, "__file__", None):
        return os.path.realpath(module.__file__)
    paths = list(getattr(module, "__path__", []))
    return os.path.realpath(paths[0]) if paths else None


@pytest.mark.parametrize(
    ("module_name", "source_root"), sorted(EXPECTED_SOURCE_ROOT.items())
)
def test_package_imports_from_this_checkout(module_name, source_root):
    module = importlib.import_module(module_name)

    location = _resolved_location(module)
    assert location is not None, f"{module_name} resolved to no location at all"

    expected_prefix = os.path.realpath(os.path.join(REPO_ROOT, source_root))
    assert location.startswith(expected_prefix + os.sep), (
        f"{module_name} imported from {location}, not from {expected_prefix}. "
        f"pytest.ini::pythonpath is missing {source_root}, so this package's "
        f"tests are exercising an installed copy instead of the working tree."
    )


def test_kailash_exposes_version():
    """A namespace-package shadow imports fine but carries no attributes."""
    import kailash

    assert getattr(kailash, "__file__", None) is not None, (
        "kailash resolved as a namespace package (no __init__.py on the "
        "winning path entry) — every `from kailash import __version__` fails."
    )
    assert isinstance(kailash.__version__, str)
