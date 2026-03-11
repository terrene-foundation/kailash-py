"""
Interface compatibility module for Kaizen framework.

This module provides backward compatibility imports for the interface classes
used in the Kaizen framework.
"""

# Import AINodeBase from nodes module
from ..nodes.base_advanced import AINodeBase

# Import the actual implementations from config module
from .config import IntegrationPattern, KaizenConfig, MemoryProvider, OptimizationEngine
from .framework import Kaizen

# NOTE: SignatureBase removed - use kaizen.signatures.Signature (Option 3: DSPy-inspired)


# Backward compatibility alias
Framework = Kaizen

# Export all interface classes
__all__ = [
    "AINodeBase",
    "KaizenConfig",
    "MemoryProvider",
    "OptimizationEngine",
    "IntegrationPattern",
    "Framework",
    "Kaizen",
]
