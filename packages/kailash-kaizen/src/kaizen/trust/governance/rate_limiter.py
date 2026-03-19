"""Compatibility shim -- re-exports from eatp.

This module re-exports all public names from the EATP SDK.
Import directly from ``eatp.governance.rate_limiter`` for new code.
"""

from eatp.governance.rate_limiter import *  # noqa: F401,F403

# Preserve __all__ from eatp module for explicit re-export
from eatp.governance.rate_limiter import __all__  # noqa: F401
