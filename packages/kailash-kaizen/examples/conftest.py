"""
Conftest for examples - inherits from tests/conftest.py

This ensures that the mock provider patching from tests/conftest.py
is applied when running tests in the examples/ directory.
"""

import os

# Import all fixtures from parent tests/conftest.py
import sys

# Add tests directory to path so we can import the conftest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tests"))

# Import from tests conftest to inherit all fixtures and configuration
from conftest import *  # noqa: F401, F403

print("✅ Examples conftest.py loaded - inheriting tests/conftest.py configuration")
