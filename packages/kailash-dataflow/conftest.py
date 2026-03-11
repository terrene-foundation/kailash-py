"""
Pytest configuration for DataFlow tests.

Ensures that the src directory is in sys.path for proper imports.
"""

import sys
from pathlib import Path

# Add src directory to sys.path
src_dir = Path(__file__).parent / "src"
if src_dir.exists() and str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))
