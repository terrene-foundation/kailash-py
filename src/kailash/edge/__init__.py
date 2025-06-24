"""Edge computing infrastructure for global distribution.

This module provides edge computing capabilities for Kailash SDK,
enabling global distribution of compute and data with sub-10ms latency.
"""

from .compliance import ComplianceRouter
from .discovery import EdgeDiscovery, EdgeSelectionStrategy
from .location import EdgeLocation

__all__ = [
    "EdgeLocation",
    "EdgeDiscovery",
    "EdgeSelectionStrategy",
    "ComplianceRouter",
]
