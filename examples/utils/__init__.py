"""
Utility functions and scripts for Kailash SDK examples.

This package provides:
- Path utilities for data and output directories
- Test runner for validating examples
- Maintenance utilities for path fixing and imports
"""

from .paths import ensure_example_directories, get_data_dir, get_output_dir

__all__ = [
    "get_data_dir",
    "get_output_dir",
    "ensure_example_directories",
]
