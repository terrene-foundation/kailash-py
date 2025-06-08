"""
Pre-built MCP servers for common use cases.

Available servers:
- AIRegistryServer: Provides access to AI use case registry data
- FileSystemServer: Provides access to local file system
- DatabaseServer: Provides access to database resources
"""

from .ai_registry import AIRegistryServer

__all__ = ["AIRegistryServer"]
