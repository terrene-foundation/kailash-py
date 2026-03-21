"""Compatibility shim -- re-exports from kailash.trust.reasoning.

This module re-exports all public names from kailash.trust.reasoning.
Import directly from ``kailash.trust.reasoning.traces`` for new code.

Key types:
- ConfidentialityLevel: Enterprise classification (PUBLIC..TOP_SECRET)
- ReasoningTrace: Structured WHY for delegation/audit decisions
"""

from kailash.trust.reasoning.traces import *  # noqa: F401,F403
