"""
Native File Tools

Provides file operation tools for autonomous agents:
- ReadFileTool: Read file contents with pagination
- WriteFileTool: Write content to files
- EditFileTool: String replacement editing
- GlobTool: Pattern matching file discovery
- GrepTool: Regex content search
- ListDirectoryTool: Directory listing
- FileExistsTool: Check file/directory existence

These tools are designed for LocalKaizenAdapter's autonomous execution loop.
"""

import asyncio
import glob as glob_module
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles

from kaizen.tools.builtin.file import validate_safe_path
from kaizen.tools.native.base import BaseTool, NativeToolResult
from kaizen.tools.types import DangerLevel, ToolCategory


class ReadFileTool(BaseTool):
    """
    Read file contents with optional offset and limit.

    Supports pagination for large files and returns line-numbered output
    similar to `cat -n`.

    Parameters:
        path: Absolute path to file
        offset: Line number to start from (0-based, default: 0)
        limit: Maximum lines to read (default: 2000)
    """

    name = "read_file"
    description = "Read the contents of a file at the given path with optional line offset and limit"
    danger_level = DangerLevel.SAFE
    category = ToolCategory.SYSTEM

    def __init__(self, allowed_base: Optional[str] = None):
        """
        Initialize ReadFileTool.

        Args:
            allowed_base: Optional base directory to restrict file access.
                          If None, no path restriction is applied.
        """
        super().__init__()
        self.allowed_base = allowed_base

    async def execute(
        self,
        path: str,
        offset: int = 0,
        limit: int = 2000,
    ) -> NativeToolResult:
        """Read file contents with pagination."""
        # Validate path
        if self.allowed_base:
            is_valid, error = validate_safe_path(path, self.allowed_base)
            if not is_valid:
                return NativeToolResult.from_error(f"Path validation failed: {error}")

        if not os.path.isabs(path):
            return NativeToolResult.from_error(f"Path must be absolute: {path}")

        try:
            async with aiofiles.open(
                path, "r", encoding="utf-8", errors="replace"
            ) as f:
                lines = await f.readlines()

            total_lines = len(lines)

            # Apply offset and limit
            selected_lines = lines[offset : offset + limit]

            # Format with line numbers (1-based)
            numbered_content = ""
            for i, line in enumerate(selected_lines, start=offset + 1):
                # Truncate very long lines
                if len(line) > 2000:
                    line = line[:2000] + "... [truncated]\n"
                numbered_content += f"{i:6d}\t{line}"

            return NativeToolResult.from_success(
                numbered_content,
                total_lines=total_lines,
                lines_read=len(selected_lines),
                offset=offset,
                truncated=len(selected_lines) < total_lines - offset,
            )
        except FileNotFoundError:
            return NativeToolResult.from_error(f"File not found: {path}")
        except PermissionError:
            return NativeToolResult.from_error(f"Permission denied: {path}")
        except UnicodeDecodeError as e:
            return NativeToolResult.from_error(f"Encoding error reading {path}: {e}")
        except Exception as e:
            return NativeToolResult.from_exception(e)

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path to the file to read",
                },
                "offset": {
                    "type": "integer",
                    "description": "Line number to start reading from (0-based)",
                    "default": 0,
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of lines to read",
                    "default": 2000,
                },
            },
            "required": ["path"],
        }


class WriteFileTool(BaseTool):
    """
    Write content to a file.

    Creates parent directories if they don't exist.
    Overwrites existing file content.

    Parameters:
        path: Absolute path to file
        content: Content to write
    """

    name = "write_file"
    description = "Write content to a file, creating parent directories if needed"
    danger_level = DangerLevel.MEDIUM
    category = ToolCategory.SYSTEM

    def __init__(self, allowed_base: Optional[str] = None):
        super().__init__()
        self.allowed_base = allowed_base

    async def execute(self, path: str, content: str) -> NativeToolResult:
        """Write content to file."""
        # Validate path
        if self.allowed_base:
            is_valid, error = validate_safe_path(path, self.allowed_base)
            if not is_valid:
                return NativeToolResult.from_error(f"Path validation failed: {error}")

        if not os.path.isabs(path):
            return NativeToolResult.from_error(f"Path must be absolute: {path}")

        try:
            # Create parent directories
            parent_dir = os.path.dirname(path)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)

            async with aiofiles.open(path, "w", encoding="utf-8") as f:
                await f.write(content)

            return NativeToolResult.from_success(
                f"Successfully wrote {len(content)} bytes to {path}",
                bytes_written=len(content),
                path=path,
            )
        except PermissionError:
            return NativeToolResult.from_error(f"Permission denied: {path}")
        except Exception as e:
            return NativeToolResult.from_exception(e)

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path to the file to write",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file",
                },
            },
            "required": ["path", "content"],
        }


class EditFileTool(BaseTool):
    """
    Edit a file by replacing text.

    Performs exact string replacement in a file.
    Can replace single occurrence or all occurrences.

    Parameters:
        path: Absolute path to file
        old_string: Text to find and replace
        new_string: Replacement text
        replace_all: If True, replace all occurrences (default: False)
    """

    name = "edit_file"
    description = "Edit a file by replacing a specific string with new content"
    danger_level = DangerLevel.MEDIUM
    category = ToolCategory.SYSTEM

    def __init__(self, allowed_base: Optional[str] = None):
        super().__init__()
        self.allowed_base = allowed_base

    async def execute(
        self,
        path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> NativeToolResult:
        """Edit file with string replacement."""
        # Validate path
        if self.allowed_base:
            is_valid, error = validate_safe_path(path, self.allowed_base)
            if not is_valid:
                return NativeToolResult.from_error(f"Path validation failed: {error}")

        if not os.path.isabs(path):
            return NativeToolResult.from_error(f"Path must be absolute: {path}")

        if old_string == new_string:
            return NativeToolResult.from_error(
                "old_string and new_string must be different"
            )

        try:
            async with aiofiles.open(path, "r", encoding="utf-8") as f:
                content = await f.read()

            if old_string not in content:
                return NativeToolResult.from_error(
                    f"String not found in file: {old_string[:100]}{'...' if len(old_string) > 100 else ''}"
                )

            # Count occurrences
            occurrences = content.count(old_string)

            # Perform replacement
            if replace_all:
                new_content = content.replace(old_string, new_string)
                replacements = occurrences
            else:
                new_content = content.replace(old_string, new_string, 1)
                replacements = 1

            async with aiofiles.open(path, "w", encoding="utf-8") as f:
                await f.write(new_content)

            return NativeToolResult.from_success(
                f"Successfully edited {path}: {replacements} replacement(s)",
                replacements=replacements,
                total_occurrences=occurrences,
                path=path,
            )
        except FileNotFoundError:
            return NativeToolResult.from_error(f"File not found: {path}")
        except PermissionError:
            return NativeToolResult.from_error(f"Permission denied: {path}")
        except Exception as e:
            return NativeToolResult.from_exception(e)

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path to the file to edit",
                },
                "old_string": {
                    "type": "string",
                    "description": "The text to find and replace",
                },
                "new_string": {
                    "type": "string",
                    "description": "The replacement text",
                },
                "replace_all": {
                    "type": "boolean",
                    "description": "Replace all occurrences instead of just the first",
                    "default": False,
                },
            },
            "required": ["path", "old_string", "new_string"],
        }


class GlobTool(BaseTool):
    """
    Find files matching a glob pattern.

    Supports recursive patterns like `**/*.py`.
    Results are sorted by modification time (most recent first).

    Parameters:
        pattern: Glob pattern (e.g., "**/*.py", "src/**/*.ts")
        path: Base directory to search in (default: current directory)
    """

    name = "glob"
    description = "Find files matching a glob pattern, sorted by modification time"
    danger_level = DangerLevel.SAFE
    category = ToolCategory.SYSTEM

    async def execute(
        self,
        pattern: str,
        path: str = ".",
    ) -> NativeToolResult:
        """Find files matching glob pattern."""
        try:
            # Construct full pattern
            if os.path.isabs(pattern):
                full_pattern = pattern
            else:
                full_pattern = os.path.join(path, pattern)

            # Find matches
            matches = glob_module.glob(full_pattern, recursive=True)

            # Filter to files only (exclude directories)
            file_matches = [m for m in matches if os.path.isfile(m)]

            # Sort by modification time (most recent first)
            file_matches.sort(key=lambda x: os.path.getmtime(x), reverse=True)

            # Limit results
            max_results = 100
            truncated = len(file_matches) > max_results
            file_matches = file_matches[:max_results]

            return NativeToolResult.from_success(
                file_matches,
                total_matches=len(matches),
                files_found=len(file_matches),
                truncated=truncated,
            )
        except Exception as e:
            return NativeToolResult.from_exception(e)

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern to match (e.g., '**/*.py', 'src/**/*.ts')",
                },
                "path": {
                    "type": "string",
                    "description": "Base directory to search in",
                    "default": ".",
                },
            },
            "required": ["pattern"],
        }


class GrepTool(BaseTool):
    """
    Search file contents using regex.

    Tries to use ripgrep (rg) if available, falls back to Python regex.
    Returns matching lines with file paths and line numbers.

    Parameters:
        pattern: Regex pattern to search for
        path: Directory to search in (default: current directory)
        file_glob: File pattern to filter (default: "*")
        case_insensitive: Case-insensitive search (default: False)
    """

    name = "grep"
    description = "Search for a regex pattern in files"
    danger_level = DangerLevel.SAFE
    category = ToolCategory.SYSTEM

    async def execute(
        self,
        pattern: str,
        path: str = ".",
        file_glob: str = "*",
        case_insensitive: bool = False,
    ) -> NativeToolResult:
        """Search for pattern in files."""
        try:
            # Try ripgrep first
            result = await self._try_ripgrep(pattern, path, file_glob, case_insensitive)
            if result is not None:
                return result

            # Fallback to Python regex
            return await self._python_grep(pattern, path, file_glob, case_insensitive)
        except Exception as e:
            return NativeToolResult.from_exception(e)

    async def _try_ripgrep(
        self,
        pattern: str,
        path: str,
        file_glob: str,
        case_insensitive: bool,
    ) -> Optional[NativeToolResult]:
        """Try to use ripgrep for search."""
        try:
            cmd = ["rg", "--line-number", "--no-heading"]
            if case_insensitive:
                cmd.append("-i")
            if file_glob != "*":
                cmd.extend(["-g", file_glob])
            cmd.extend([pattern, path])

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=30.0,
            )

            if process.returncode == 0:
                output = stdout.decode("utf-8", errors="replace")
                lines = output.strip().split("\n") if output.strip() else []
                return NativeToolResult.from_success(
                    output[:30000],  # Limit output size
                    total_matches=len(lines),
                    search_engine="ripgrep",
                    truncated=len(output) > 30000,
                )
            elif process.returncode == 1:
                # No matches found
                return NativeToolResult.from_success(
                    "No matches found",
                    total_matches=0,
                    search_engine="ripgrep",
                )
            else:
                # Error occurred, try Python fallback
                return None
        except FileNotFoundError:
            # ripgrep not installed
            return None
        except asyncio.TimeoutError:
            return NativeToolResult.from_error("Search timed out after 30 seconds")

    async def _python_grep(
        self,
        pattern: str,
        path: str,
        file_glob: str,
        case_insensitive: bool,
    ) -> NativeToolResult:
        """Python regex fallback for grep."""
        flags = re.IGNORECASE if case_insensitive else 0
        try:
            regex = re.compile(pattern, flags)
        except re.error as e:
            return NativeToolResult.from_error(f"Invalid regex pattern: {e}")

        matches = []
        files_searched = 0

        # Find files to search
        file_pattern = os.path.join(path, "**", file_glob)
        files = glob_module.glob(file_pattern, recursive=True)

        for filepath in files:
            if not os.path.isfile(filepath):
                continue

            files_searched += 1
            try:
                async with aiofiles.open(
                    filepath, "r", encoding="utf-8", errors="replace"
                ) as f:
                    for line_num, line in enumerate(await f.readlines(), 1):
                        if regex.search(line):
                            matches.append(f"{filepath}:{line_num}:{line.rstrip()}")

                            # Limit total matches
                            if len(matches) >= 500:
                                output = "\n".join(matches)
                                return NativeToolResult.from_success(
                                    output[:30000],
                                    total_matches=len(matches),
                                    files_searched=files_searched,
                                    search_engine="python",
                                    truncated=True,
                                )
            except (IOError, OSError):
                continue

        output = "\n".join(matches) if matches else "No matches found"
        return NativeToolResult.from_success(
            output,
            total_matches=len(matches),
            files_searched=files_searched,
            search_engine="python",
        )

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regex pattern to search for",
                },
                "path": {
                    "type": "string",
                    "description": "Directory to search in",
                    "default": ".",
                },
                "file_glob": {
                    "type": "string",
                    "description": "File pattern to filter (e.g., '*.py', '*.ts')",
                    "default": "*",
                },
                "case_insensitive": {
                    "type": "boolean",
                    "description": "Perform case-insensitive search",
                    "default": False,
                },
            },
            "required": ["pattern"],
        }


class ListDirectoryTool(BaseTool):
    """
    List directory contents with metadata.

    Returns files and subdirectories with size and modification time.

    Parameters:
        path: Directory path to list
    """

    name = "list_directory"
    description = (
        "List the contents of a directory with file sizes and modification times"
    )
    danger_level = DangerLevel.SAFE
    category = ToolCategory.SYSTEM

    async def execute(self, path: str) -> NativeToolResult:
        """List directory contents."""
        if not os.path.isabs(path):
            return NativeToolResult.from_error(f"Path must be absolute: {path}")

        if not os.path.exists(path):
            return NativeToolResult.from_error(f"Path does not exist: {path}")

        if not os.path.isdir(path):
            return NativeToolResult.from_error(f"Path is not a directory: {path}")

        try:
            entries = []
            for entry in os.scandir(path):
                try:
                    stat = entry.stat()
                    entries.append(
                        {
                            "name": entry.name,
                            "type": "directory" if entry.is_dir() else "file",
                            "size": stat.st_size if entry.is_file() else None,
                            "modified": stat.st_mtime,
                        }
                    )
                except (PermissionError, OSError):
                    entries.append(
                        {
                            "name": entry.name,
                            "type": "unknown",
                            "size": None,
                            "modified": None,
                            "error": "Permission denied",
                        }
                    )

            # Sort: directories first, then files, alphabetically
            entries.sort(key=lambda e: (e["type"] != "directory", e["name"].lower()))

            return NativeToolResult.from_success(
                entries,
                total_entries=len(entries),
                path=path,
            )
        except PermissionError:
            return NativeToolResult.from_error(f"Permission denied: {path}")
        except Exception as e:
            return NativeToolResult.from_exception(e)

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path to the directory to list",
                },
            },
            "required": ["path"],
        }


class FileExistsTool(BaseTool):
    """
    Check if a file or directory exists.

    Parameters:
        path: Path to check
    """

    name = "file_exists"
    description = "Check if a file or directory exists at the given path"
    danger_level = DangerLevel.SAFE
    category = ToolCategory.SYSTEM

    async def execute(self, path: str) -> NativeToolResult:
        """Check if file/directory exists."""
        try:
            exists = os.path.exists(path)
            is_file = os.path.isfile(path) if exists else None
            is_dir = os.path.isdir(path) if exists else None

            return NativeToolResult.from_success(
                exists,
                exists=exists,
                is_file=is_file,
                is_directory=is_dir,
                path=path,
            )
        except Exception as e:
            return NativeToolResult.from_exception(e)

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to check for existence",
                },
            },
            "required": ["path"],
        }
