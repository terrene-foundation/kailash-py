"""Centralized data path utilities for examples.

This module provides standardized functions for accessing data files
in the centralized /data/ directory structure.

The centralized structure:
- data/inputs/ - Input data files (CSV, JSON, TXT, etc.)
- data/outputs/ - Generated output files
- data/templates/ - Template data files
- data/test/ - Test data files
- data/examples/ - Example-specific data
- data/tracking/ - Task tracking and metrics data
"""

from pathlib import Path
from typing import Union


def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent.parent.parent


def get_central_data_dir() -> Path:
    """Get the central data directory."""
    return get_project_root() / "data"


def get_input_data_path(filename: str, file_type: str = "csv") -> Path:
    """Get path to input data file in centralized location.

    Args:
        filename: Name of the file
        file_type: Type of file (csv, json, txt, etc.)

    Returns:
        Path to the file in data/inputs/{file_type}/
    """
    return get_central_data_dir() / "inputs" / file_type / filename


def get_output_data_path(filename: str, file_type: str = "csv") -> Path:
    """Get path to output data file in centralized location.

    Args:
        filename: Name of the file
        file_type: Type of file (csv, json, txt, etc.)

    Returns:
        Path to the file in data/outputs/{file_type}/
    """
    return get_central_data_dir() / "outputs" / file_type / filename


def get_template_data_path(filename: str, file_type: str = "csv") -> Path:
    """Get path to template data file in centralized location.

    Args:
        filename: Name of the file
        file_type: Type of file (csv, json, txt, etc.)

    Returns:
        Path to the file in data/templates/{file_type}/
    """
    return get_central_data_dir() / "templates" / file_type / filename


def get_test_data_path(filename: str, file_type: str = "csv") -> Path:
    """Get path to test data file in centralized location.

    Args:
        filename: Name of the file
        file_type: Type of file (csv, json, txt, etc.)

    Returns:
        Path to the file in data/test/{file_type}/
    """
    return get_central_data_dir() / "test" / file_type / filename


# Legacy support - these functions maintain backward compatibility
# while encouraging migration to centralized paths
def get_data_dir() -> Path:
    """Get data directory - now points to centralized location."""
    return get_central_data_dir() / "inputs"


def get_output_dir() -> Path:
    """Get output directory - now points to centralized location."""
    return get_central_data_dir() / "outputs"


# Convenience functions for common file types
def get_customer_csv_path() -> Path:
    """Get path to the standard customers.csv file."""
    return get_input_data_path("customers.csv", "csv")


def get_transactions_json_path() -> Path:
    """Get path to the standard transactions.json file."""
    return get_input_data_path("transactions.json", "json")


def ensure_output_dir_exists(file_type: str = "csv") -> Path:
    """Ensure output directory exists and return path."""
    output_dir = get_central_data_dir() / "outputs" / file_type
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def ensure_input_dir_exists(file_type: str = "csv") -> Path:
    """Ensure input directory exists and return path."""
    input_dir = get_central_data_dir() / "inputs" / file_type
    input_dir.mkdir(parents=True, exist_ok=True)
    return input_dir


# Migration helpers
def get_legacy_path_mapping() -> dict:
    """Get mapping of old paths to new centralized paths."""
    return {
        "examples/data/customers.csv": get_input_data_path("customers.csv"),
        "examples/data/transactions.json": get_input_data_path(
            "transactions.json", "json"
        ),
        "examples/data/input.csv": get_input_data_path("input.csv"),
        "examples/data/raw_customers.csv": get_input_data_path("raw_customers.csv"),
        "data/customers.csv": get_input_data_path("customers.csv"),
        "data/transactions.csv": get_input_data_path("transactions.csv"),
        "data/events.csv": get_input_data_path("events.csv"),
    }


def migrate_to_centralized_path(old_path: Union[str, Path]) -> Path:
    """Convert old scattered path to new centralized path.

    Args:
        old_path: Old path to data file

    Returns:
        New centralized path, or original path if no mapping exists
    """
    old_path_str = str(old_path)
    mapping = get_legacy_path_mapping()

    # Check for exact match
    if old_path_str in mapping:
        return mapping[old_path_str]

    # Check for relative matches
    for old, new in mapping.items():
        if old_path_str.endswith(old) or old.endswith(old_path_str):
            return new

    # If no mapping found, return original path
    return Path(old_path)
