"""Data path utilities for examples and PythonCodeNode execution.

This module provides helper functions for constructing standardized paths
to input and output data files used in workflows and examples.
"""

import os
from pathlib import Path


def get_project_root() -> Path:
    """Get the project root directory.

    Returns:
        Path to the kailash_python_sdk project root
    """
    # Find the project root by looking for setup.py or pyproject.toml
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "setup.py").exists() or (parent / "pyproject.toml").exists():
            return parent
    # Fallback to going up from src/kailash/utils to project root
    return current.parent.parent.parent


def get_input_data_path(filename: str) -> str:
    """Get the full path to an input data file.

    Args:
        filename: Name of the input data file

    Returns:
        Full path to the input data file
    """
    project_root = get_project_root()
    return str(project_root / "data" / "inputs" / filename)


def get_output_data_path(filename: str) -> str:
    """Get the full path to an output data file.

    Args:
        filename: Name of the output data file

    Returns:
        Full path to the output data file
    """
    project_root = get_project_root()
    output_path = project_root / "data" / "outputs" / filename

    # Ensure the output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    return str(output_path)


def get_data_path(subfolder: str, filename: str) -> str:
    """Get the full path to a data file in a specific subfolder.

    Args:
        subfolder: Subfolder within the data directory (e.g., 'inputs', 'outputs', 'templates')
        filename: Name of the data file

    Returns:
        Full path to the data file
    """
    project_root = get_project_root()
    data_path = project_root / "data" / subfolder / filename

    # Ensure the directory exists for output-type operations
    if subfolder in ("outputs", "exports", "tracking"):
        data_path.parent.mkdir(parents=True, exist_ok=True)

    return str(data_path)
