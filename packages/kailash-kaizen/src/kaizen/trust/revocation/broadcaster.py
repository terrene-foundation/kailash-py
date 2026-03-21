"""Compatibility shim -- re-exports from kailash.trust.

This module re-exports all public names from kailash.trust.
Import directly from ``kailash.trust.revocation.broadcaster`` for new code.
"""

from kailash.trust.revocation.broadcaster import *  # noqa: F401,F403

# Preserve __all__ from kailash.trust module for explicit re-export
from kailash.trust.revocation.broadcaster import __all__  # noqa: F401
