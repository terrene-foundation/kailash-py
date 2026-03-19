"""Compatibility shim -- re-exports from eatp.

This module re-exports all public names from the EATP SDK.
Import directly from ``eatp.governance.policy_engine`` for new code.
"""

from eatp.governance.policy_engine import *  # noqa: F401,F403

# Preserve __all__ from eatp module for explicit re-export
from eatp.governance.policy_engine import __all__  # noqa: F401
