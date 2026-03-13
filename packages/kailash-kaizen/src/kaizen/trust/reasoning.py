"""Compatibility shim -- re-exports from eatp.reasoning.

This module re-exports all public names from the EATP SDK reasoning module.
Import directly from ``eatp.reasoning`` for new code.

Key types:
- ConfidentialityLevel: Enterprise classification (PUBLIC..TOP_SECRET)
- ReasoningTrace: Structured WHY for delegation/audit decisions
"""

from eatp.reasoning import *  # noqa: F401,F403
