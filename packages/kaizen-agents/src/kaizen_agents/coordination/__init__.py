"""
Multi-agent coordination patterns and state management.

This module provides coordination patterns for managing teams of agents
and their collaborative state, including advanced coordination patterns
with A2A integration and enterprise features.
"""

from .patterns import (
    ConsensusCoordinationPattern,
    CoordinationPattern,
    CoordinationPatternRegistry,
    DebateCoordinationPattern,
    HierarchicalCoordinationPattern,
    TeamCoordinationPattern,
    get_global_pattern_registry,
)
from .teams import AgentTeam, TeamCoordinator

__all__ = [
    "AgentTeam",
    "TeamCoordinator",
    "CoordinationPattern",
    "DebateCoordinationPattern",
    "ConsensusCoordinationPattern",
    "HierarchicalCoordinationPattern",
    "TeamCoordinationPattern",
    "CoordinationPatternRegistry",
    "get_global_pattern_registry",
]
