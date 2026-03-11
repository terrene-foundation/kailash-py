"""
Permission system for safe autonomous agent operation.

Provides runtime permission management, budget enforcement, and tool restrictions.
"""

from kaizen.core.autonomy.permissions.context import ExecutionContext
from kaizen.core.autonomy.permissions.types import PermissionMode, ToolPermission

__all__ = [
    "ExecutionContext",
    "PermissionMode",
    "ToolPermission",
]
