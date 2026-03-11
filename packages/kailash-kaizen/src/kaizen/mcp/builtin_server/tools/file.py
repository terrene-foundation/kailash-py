"""
File Tools for MCP - File System Operations

Provides 5 MCP tools for file operations:
- read_file: Read file contents
- write_file: Write content to file
- delete_file: Delete a file
- list_directory: List directory contents
- file_exists: Check if file exists

Security Features:
- Path traversal protection (blocks '..' patterns)
- Dangerous system path blocking (/etc, /sys, /proc, /dev, /boot, /root)
- Optional sandboxing (allowed_base parameter)

All tools preserve security validations from original implementations.
All tools use @tool decorator for MCP compliance.
"""

import os
from pathlib import Path
from typing import Optional, Tuple

from kaizen.mcp.builtin_server.decorators import mcp_tool

# Security constants (from original implementation)
DANGEROUS_SYSTEM_PATHS = {
    "/etc",  # System configuration
    "/sys",  # Kernel interface
    "/proc",  # Process information
    "/dev",  # Device files
    "/boot",  # Boot files
    "/root",  # Root user home
}


def validate_safe_path(
    path: str, allowed_base: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """
    Validate file path for security (path traversal protection).

    Validates that:
    1. Path does not contain '..' (path traversal)
    2. Path does not target dangerous system directories
    3. Path is within allowed_base if specified (sandboxing)

    Args:
        path: File path to validate
        allowed_base: Optional base directory for sandboxing

    Returns:
        Tuple of (is_valid, error_message)
        - is_valid: True if path is safe, False otherwise
        - error_message: None if valid, error description otherwise

    Note: This function is copied from kaizen/tools/builtin/file.py
    """
    if not path:
        return False, "Path cannot be empty"

    try:
        # Normalize path (resolves .., //, etc.)
        normalized_path = Path(path)

        # Convert to absolute path for security checks
        abs_path_str = os.path.abspath(str(normalized_path))
        abs_path = Path(abs_path_str)

        # Check for path traversal attempts (..)
        path_parts = abs_path.parts
        for part in path_parts:
            if part == "..":
                return False, f"Path traversal detected (contains '..'): {path}"

        # Also check the original path string for .. patterns
        if ".." in path:
            return False, f"Path traversal detected (contains '..'): {path}"

        # Check for dangerous system paths
        for dangerous_path in DANGEROUS_SYSTEM_PATHS:
            try:
                abs_path.relative_to(dangerous_path)
                return False, f"Access to system path is not allowed: {dangerous_path}"
            except ValueError:
                continue

        # Optional: Check sandboxing (path must be within allowed_base)
        if allowed_base is not None:
            allowed_base_path = Path(os.path.abspath(allowed_base))
            try:
                abs_path.relative_to(allowed_base_path)
            except ValueError:
                return (
                    False,
                    f"Path is outside allowed base directory. Path: {abs_path_str}, Allowed base: {allowed_base}",
                )

        return True, None

    except Exception as e:
        return False, f"Invalid path: {str(e)}"


# =============================================================================
# MCP Tools (5 total)
# =============================================================================


@mcp_tool(
    name="read_file",
    description="Read contents of a file",
    parameters={
        "path": {"type": "string", "description": "File path to read"},
        "encoding": {
            "type": "string",
            "description": "File encoding (default 'utf-8')",
        },
    },
)
async def read_file(path: str, encoding: str = "utf-8") -> dict:
    """
    Read file contents (MCP tool implementation).

    Args:
        path: File path to read
        encoding: File encoding (default 'utf-8')

    Returns:
        Dictionary with:
            - content (str): File contents
            - size (int): File size in bytes
            - exists (bool): True if file exists
            - error (str, optional): Error message if failed

    Security:
        - Path validation (no '..' traversal)
        - Dangerous system paths blocked
    """
    # Security validation
    is_valid, error = validate_safe_path(path)
    if not is_valid:
        return {
            "content": "",
            "size": 0,
            "exists": False,
            "error": f"Path validation failed: {error}",
        }

    try:
        file_path = Path(path)
        if not file_path.exists():
            return {
                "content": "",
                "size": 0,
                "exists": False,
                "error": "File not found",
            }

        if not file_path.is_file():
            return {
                "content": "",
                "size": 0,
                "exists": True,
                "error": "Path is not a file",
            }

        content = file_path.read_text(encoding=encoding)
        size = file_path.stat().st_size

        return {"content": content, "size": size, "exists": True}

    except Exception as e:
        return {"content": "", "size": 0, "exists": False, "error": str(e)}


@mcp_tool(
    name="write_file",
    description="Write content to a file",
    parameters={
        "path": {"type": "string", "description": "File path to write"},
        "content": {"type": "string", "description": "Content to write"},
        "encoding": {
            "type": "string",
            "description": "File encoding (default 'utf-8')",
        },
        "create_dirs": {
            "type": "boolean",
            "description": "Create parent directories if needed (default True)",
        },
    },
)
async def write_file(
    path: str, content: str, encoding: str = "utf-8", create_dirs: bool = True
) -> dict:
    """
    Write content to a file (MCP tool implementation).

    Args:
        path: File path to write
        content: Content to write
        encoding: File encoding (default 'utf-8')
        create_dirs: Create parent directories if needed (default True)

    Returns:
        Dictionary with:
            - written (bool): True if write succeeded
            - size (int): Bytes written
            - path (str): Absolute file path
            - error (str, optional): Error message if failed

    Security:
        - Path validation (no '..' traversal)
        - Dangerous system paths blocked
    """
    # Security validation
    is_valid, error = validate_safe_path(path)
    if not is_valid:
        return {
            "written": False,
            "size": 0,
            "path": path,
            "error": f"Path validation failed: {error}",
        }

    try:
        file_path = Path(path)

        # Create parent directories if needed
        if create_dirs and not file_path.parent.exists():
            file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write file
        file_path.write_text(content, encoding=encoding)
        size = file_path.stat().st_size

        return {
            "written": True,
            "size": size,
            "path": str(file_path.absolute()),
        }

    except Exception as e:
        return {"written": False, "size": 0, "path": path, "error": str(e)}


@mcp_tool(
    name="delete_file",
    description="Delete a file",
    parameters={
        "path": {"type": "string", "description": "File path to delete"},
    },
)
async def delete_file(path: str) -> dict:
    """
    Delete a file (MCP tool implementation).

    Args:
        path: File path to delete

    Returns:
        Dictionary with:
            - deleted (bool): True if deletion succeeded
            - existed (bool): True if file existed before deletion
            - path (str): File path
            - error (str, optional): Error message if failed

    Security:
        - Path validation (no '..' traversal)
        - Dangerous system paths blocked
    """
    # Security validation
    is_valid, error = validate_safe_path(path)
    if not is_valid:
        return {
            "deleted": False,
            "existed": False,
            "path": path,
            "error": f"Path validation failed: {error}",
        }

    try:
        file_path = Path(path)
        existed = file_path.exists()

        if existed:
            if file_path.is_file():
                file_path.unlink()
                return {"deleted": True, "existed": True, "path": path}
            else:
                return {
                    "deleted": False,
                    "existed": True,
                    "path": path,
                    "error": "Path is not a file",
                }
        else:
            return {"deleted": False, "existed": False, "path": path}

    except Exception as e:
        return {"deleted": False, "existed": False, "path": path, "error": str(e)}


@mcp_tool(
    name="list_directory",
    description="List files and directories in a directory",
    parameters={
        "path": {"type": "string", "description": "Directory path to list"},
        "recursive": {
            "type": "boolean",
            "description": "List recursively (default False)",
        },
        "include_hidden": {
            "type": "boolean",
            "description": "Include hidden files (default False)",
        },
    },
)
async def list_directory(
    path: str, recursive: bool = False, include_hidden: bool = False
) -> dict:
    """
    List files and directories in a directory (MCP tool implementation).

    Args:
        path: Directory path to list
        recursive: List recursively (default False)
        include_hidden: Include hidden files (default False)

    Returns:
        Dictionary with:
            - files (list[str]): List of file paths
            - directories (list[str]): List of directory paths
            - count (int): Total number of items
            - path (str): Directory path
            - error (str, optional): Error message if failed
    """
    try:
        dir_path = Path(path)
        if not dir_path.exists():
            return {
                "files": [],
                "directories": [],
                "count": 0,
                "path": path,
                "error": "Directory not found",
            }

        if not dir_path.is_dir():
            return {
                "files": [],
                "directories": [],
                "count": 0,
                "path": path,
                "error": "Path is not a directory",
            }

        files = []
        directories = []

        if recursive:
            pattern = "**/*"
        else:
            pattern = "*"

        for item in dir_path.glob(pattern):
            # Skip hidden files unless requested
            if not include_hidden and item.name.startswith("."):
                continue

            relative_path = str(item.relative_to(dir_path))

            if item.is_file():
                files.append(relative_path)
            elif item.is_dir():
                directories.append(relative_path)

        return {
            "files": sorted(files),
            "directories": sorted(directories),
            "count": len(files) + len(directories),
            "path": path,
        }

    except Exception as e:
        return {
            "files": [],
            "directories": [],
            "count": 0,
            "path": path,
            "error": str(e),
        }


@mcp_tool(
    name="file_exists",
    description="Check if a file exists",
    parameters={
        "path": {"type": "string", "description": "File path to check"},
    },
)
async def file_exists(path: str) -> dict:
    """
    Check if a file exists (MCP tool implementation).

    Args:
        path: File path to check

    Returns:
        Dictionary with:
            - exists (bool): True if file exists
            - is_file (bool): True if path is a file
            - is_directory (bool): True if path is a directory
            - path (str): File path
            - error (str, optional): Error message if failed
    """
    try:
        file_path = Path(path)
        exists = file_path.exists()

        return {
            "exists": exists,
            "is_file": file_path.is_file() if exists else False,
            "is_directory": file_path.is_dir() if exists else False,
            "path": path,
        }

    except Exception as e:
        return {
            "exists": False,
            "is_file": False,
            "is_directory": False,
            "path": path,
            "error": str(e),
        }
