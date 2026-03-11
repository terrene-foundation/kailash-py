"""
Teams module - Compatibility layer.

This module re-exports team classes from their actual location
in kaizen.orchestration.core.teams for backward compatibility.

The actual implementation is in kaizen/orchestration/core/teams.py.
"""

# Re-export all team classes from orchestration.core.teams
from kaizen.orchestration.core.teams import AgentTeam, TeamCoordinator

__all__ = [
    "AgentTeam",
    "TeamCoordinator",
]
