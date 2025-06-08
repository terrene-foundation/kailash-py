"""Node mixins for adding capabilities to nodes.

This module provides mixins that can be combined with node classes
to add additional functionality without inheritance complexity.
"""

from .mcp import MCPCapabilityMixin

__all__ = [
    "MCPCapabilityMixin",
]
