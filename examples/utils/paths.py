"""Path utilities for examples.

This module provides helper functions for constructing standardized paths
to data directories and files used in workflows and examples.
"""

from pathlib import Path
from typing import Union


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
    # Fallback to going up from examples/utils to project root
    return current.parent.parent


def get_data_dir() -> Path:
    """Get the data directory path.

    Returns:
        Path to the project's data directory
    """
    data_dir = get_project_root() / "data"
    data_dir.mkdir(exist_ok=True)
    return data_dir


def get_output_dir() -> Path:
    """Get the output directory path.

    Returns:
        Path to the project's output data directory
    """
    output_dir = get_data_dir() / "outputs"
    output_dir.mkdir(exist_ok=True)
    return output_dir


def get_input_dir() -> Path:
    """Get the input directory path.

    Returns:
        Path to the project's input data directory
    """
    input_dir = get_data_dir() / "inputs"
    input_dir.mkdir(exist_ok=True)
    return input_dir


def get_input_data_path(filename: str) -> str:
    """Get the full path to an input data file.

    Args:
        filename: Name of the input data file

    Returns:
        Full path to the input data file
    """
    return str(get_input_dir() / filename)


def get_output_data_path(filename: str) -> str:
    """Get the full path to an output data file.

    Args:
        filename: Name of the output data file

    Returns:
        Full path to the output data file
    """
    return str(get_output_dir() / filename)


def get_data_path(subfolder: str, filename: str) -> str:
    """Get the full path to a data file in a specific subfolder.

    Args:
        subfolder: Subfolder within the data directory (e.g., 'inputs', 'outputs', 'templates')
        filename: Name of the data file

    Returns:
        Full path to the data file
    """
    data_path = get_data_dir() / subfolder / filename

    # Ensure the directory exists for output-type operations
    if subfolder in ("outputs", "exports", "tracking"):
        data_path.parent.mkdir(parents=True, exist_ok=True)

    return str(data_path)
