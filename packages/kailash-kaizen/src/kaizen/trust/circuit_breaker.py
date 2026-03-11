"""Compatibility shim -- re-exports from eatp.

This module re-exports all public names from the EATP SDK.
Import directly from ``eatp.circuit_breaker`` for new code.
"""
from eatp.circuit_breaker import *  # noqa: F401,F403

# Preserve __all__ from eatp module for explicit re-export
from eatp.circuit_breaker import __all__  # noqa: F401
