"""
Coordination patterns module - Compatibility layer.

This module re-exports coordination pattern classes from their actual location
in kaizen.orchestration.core.patterns for backward compatibility.

The actual implementation is in kaizen/orchestration/core/patterns.py.
"""

# Re-export all pattern classes from orchestration.core.patterns
from kaizen.orchestration.core.patterns import (
    ConsensusCoordinationPattern,
    CoordinationPattern,
    CoordinationPatternRegistry,
    DebateCoordinationPattern,
    HierarchicalCoordinationPattern,
    TeamCoordinationPattern,
    get_global_pattern_registry,
)

__all__ = [
    "CoordinationPattern",
    "DebateCoordinationPattern",
    "ConsensusCoordinationPattern",
    "HierarchicalCoordinationPattern",
    "TeamCoordinationPattern",
    "CoordinationPatternRegistry",
    "get_global_pattern_registry",
]
