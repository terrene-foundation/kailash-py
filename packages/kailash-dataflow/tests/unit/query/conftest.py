"""
Minimal conftest for query module tests.

This conftest pre-loads the dataflow.query subpackage WITHOUT triggering
the main dataflow.__init__.py, which has a pre-existing import error
(cannot import 'Node' from 'kailash.nodes.base').

Strategy: Insert a minimal stub for the 'dataflow' package into sys.modules
so that 'from dataflow.query.models import ...' resolves the query subpackage
directly from the src directory, bypassing the broken __init__.py chain.
"""

import importlib
import sys
import types
from pathlib import Path

# Path to the src directory containing the dataflow package
_SRC_DIR = Path(__file__).resolve().parent.parent.parent.parent / "src"
_QUERY_DIR = _SRC_DIR / "dataflow" / "query"


def _bootstrap_query_module() -> None:
    """Bootstrap dataflow.query into sys.modules without loading dataflow.__init__."""
    # If dataflow is already properly loaded, skip (should not happen in our case)
    if "dataflow.query.models" in sys.modules:
        return

    # Ensure src is on the path
    src_str = str(_SRC_DIR)
    if src_str not in sys.path:
        sys.path.insert(0, src_str)

    # Create a minimal stub for the 'dataflow' package if not already loaded
    if "dataflow" not in sys.modules:
        stub = types.ModuleType("dataflow")
        stub.__path__ = [str(_SRC_DIR / "dataflow")]
        stub.__package__ = "dataflow"
        sys.modules["dataflow"] = stub

    # Now Python can resolve 'dataflow.query' without executing dataflow/__init__.py
    # Import the query subpackage modules directly
    if "dataflow.query" not in sys.modules:
        # First import models (no external deps)
        query_pkg = types.ModuleType("dataflow.query")
        query_pkg.__path__ = [str(_QUERY_DIR)]
        query_pkg.__package__ = "dataflow.query"
        sys.modules["dataflow.query"] = query_pkg

    # Now let normal importlib handle the rest
    if "dataflow.query.models" not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            "dataflow.query.models",
            _QUERY_DIR / "models.py",
            submodule_search_locations=[],
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules["dataflow.query.models"] = mod
        spec.loader.exec_module(mod)

    if "dataflow.query.sql_builder" not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            "dataflow.query.sql_builder",
            _QUERY_DIR / "sql_builder.py",
            submodule_search_locations=[],
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules["dataflow.query.sql_builder"] = mod
        spec.loader.exec_module(mod)


# Bootstrap immediately when conftest is loaded (before test collection)
_bootstrap_query_module()
