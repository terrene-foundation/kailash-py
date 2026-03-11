"""
Helper for safely importing example workflow modules.

This helper prevents sys.path collisions when importing workflow.py files
from different example directories during pytest runs.
"""

import importlib.util
import sys
from pathlib import Path
from typing import Any


def import_example_module(
    example_relative_path: str, module_name: str = "workflow"
) -> Any:
    """
    Import a module from an example directory without polluting sys.path.

    Args:
        example_relative_path: Path to example dir from repository root
                              e.g., "examples/1-single-agent/simple-qa"
        module_name: Name of the module file to import (default: "workflow")

    Returns:
        The imported module object

    Example:
        >>> workflow = import_example_module("examples/1-single-agent/simple-qa")
        >>> agent = workflow.SimpleQAAgent(config)
    """
    # Get repository root (3 levels up from this file)
    test_file = Path(__file__).resolve()
    repo_root = test_file.parent.parent.parent.parent

    # Build full path to module
    module_path = repo_root / example_relative_path / f"{module_name}.py"

    if not module_path.exists():
        raise FileNotFoundError(f"Module not found: {module_path}")

    # Create unique module name to avoid collisions
    unique_name = f"_{example_relative_path.replace('/', '_')}_{module_name}"

    # Load module from file without adding to sys.path
    spec = importlib.util.spec_from_file_location(unique_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load spec for {module_path}")

    module = importlib.util.module_from_spec(spec)

    # Add to sys.modules to allow relative imports within the module
    sys.modules[unique_name] = module

    # Execute the module
    spec.loader.exec_module(module)

    return module
