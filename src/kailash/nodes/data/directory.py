"""Directory processing nodes for file discovery and batch operations."""

import mimetypes
import os
from datetime import datetime
from typing import Any

from kailash.nodes.base import Node, NodeParameter, register_node
from kailash.security import validate_file_path


@register_node()
class DirectoryReaderNode(Node):
    """
    Discovers and catalogs files in a directory with metadata extraction.

    This node provides comprehensive directory scanning capabilities, handling
    file discovery, metadata extraction, and filtering. It's designed for
    batch file processing workflows and dynamic data source discovery.

    Design Philosophy:
        The DirectoryReaderNode embodies the principle of "dynamic data discovery."
        Instead of hardcoding file paths, workflows can dynamically discover
        available data sources at runtime. This makes workflows more flexible
        and adaptable to changing data environments.

    Features:
        - Recursive directory scanning
        - File type detection and filtering
        - Metadata extraction (size, timestamps, MIME types)
        - Pattern-based filtering
        - Security-validated path operations

    Use Cases:
        - Batch file processing workflows
        - Dynamic data pipeline creation
        - File monitoring and cataloging
        - Multi-format document processing
        - Data lake exploration

    Output Format:
        Returns a structured catalog of discovered files with:
        - File paths and names
        - File types and MIME types
        - File sizes and timestamps
        - Directory structure information
    """

    def get_parameters(self) -> dict[str, NodeParameter]:
        """Define input parameters for directory scanning."""
        return {
            "directory_path": NodeParameter(
                name="directory_path",
                type=str,
                required=True,
                description="Path to the directory to scan",
            ),
            "recursive": NodeParameter(
                name="recursive",
                type=bool,
                required=False,
                default=False,
                description="Whether to scan subdirectories recursively",
            ),
            "file_patterns": NodeParameter(
                name="file_patterns",
                type=list,
                required=False,
                default=[],
                description="List of file patterns to include (e.g., ['*.csv', '*.json'])",
            ),
            "exclude_patterns": NodeParameter(
                name="exclude_patterns",
                type=list,
                required=False,
                default=[],
                description="List of file patterns to exclude",
            ),
            "include_hidden": NodeParameter(
                name="include_hidden",
                type=bool,
                required=False,
                default=False,
                description="Whether to include hidden files (starting with .)",
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        """Execute directory scanning operation.

        Returns:
            Dictionary containing:
            - discovered_files: List of file information dictionaries
            - files_by_type: Files grouped by type
            - directory_stats: Summary statistics
        """
        directory_path = kwargs.get("directory_path")
        recursive = kwargs.get("recursive", False)
        file_patterns = kwargs.get("file_patterns", [])
        exclude_patterns = kwargs.get("exclude_patterns", [])
        include_hidden = kwargs.get("include_hidden", False)

        # Validate directory path for security
        validated_path = validate_file_path(directory_path, operation="directory scan")

        if not os.path.isdir(validated_path):
            raise FileNotFoundError(f"Directory not found: {directory_path}")

        discovered_files = []

        try:
            if recursive:
                # Recursive scan
                for root, dirs, files in os.walk(validated_path):
                    for filename in files:
                        file_path = os.path.join(root, filename)
                        file_info = self._extract_file_info(
                            file_path,
                            filename,
                            include_hidden,
                            file_patterns,
                            exclude_patterns,
                        )
                        if file_info:
                            discovered_files.append(file_info)
            else:
                # Single directory scan
                for filename in os.listdir(validated_path):
                    file_path = os.path.join(validated_path, filename)

                    # Skip directories in non-recursive mode
                    if os.path.isdir(file_path):
                        continue

                    file_info = self._extract_file_info(
                        file_path,
                        filename,
                        include_hidden,
                        file_patterns,
                        exclude_patterns,
                    )
                    if file_info:
                        discovered_files.append(file_info)

        except PermissionError as e:
            raise PermissionError(f"Permission denied accessing directory: {e}")
        except Exception as e:
            raise RuntimeError(f"Error scanning directory: {e}")

        # Group files by type
        files_by_type = {}
        for file_info in discovered_files:
            file_type = file_info["file_type"]
            if file_type not in files_by_type:
                files_by_type[file_type] = []
            files_by_type[file_type].append(file_info)

        # Generate directory statistics
        directory_stats = {
            "total_files": len(discovered_files),
            "file_types": list(files_by_type.keys()),
            "files_by_type_count": {
                file_type: len(files) for file_type, files in files_by_type.items()
            },
            "total_size": sum(f["file_size"] for f in discovered_files),
            "scan_time": datetime.now().isoformat(),
            "directory_path": directory_path,
            "recursive": recursive,
        }

        return {
            "discovered_files": discovered_files,
            "files_by_type": files_by_type,
            "directory_stats": directory_stats,
        }

    def _extract_file_info(
        self,
        file_path: str,
        filename: str,
        include_hidden: bool,
        file_patterns: list[str],
        exclude_patterns: list[str],
    ) -> dict[str, Any] | None:
        """Extract metadata from a single file.

        Args:
            file_path: Full path to the file
            filename: Name of the file
            include_hidden: Whether to include hidden files
            file_patterns: Patterns to include
            exclude_patterns: Patterns to exclude

        Returns:
            File information dictionary or None if file should be excluded
        """
        # Skip hidden files if not included
        if not include_hidden and filename.startswith("."):
            return None

        # Check exclude patterns
        for pattern in exclude_patterns:
            if self._matches_pattern(filename, pattern):
                return None

        # Check include patterns (if specified)
        if file_patterns:
            included = any(
                self._matches_pattern(filename, pattern) for pattern in file_patterns
            )
            if not included:
                return None

        try:
            # Get file statistics
            file_stat = os.stat(file_path)
            file_ext = os.path.splitext(filename)[1].lower()

            # Map extensions to types
            ext_to_type = {
                ".csv": "csv",
                ".json": "json",
                ".txt": "txt",
                ".xml": "xml",
                ".md": "markdown",
                ".py": "python",
                ".js": "javascript",
                ".html": "html",
                ".css": "css",
                ".pdf": "pdf",
                ".doc": "word",
                ".docx": "word",
                ".xls": "excel",
                ".xlsx": "excel",
                ".png": "image",
                ".jpg": "image",
                ".jpeg": "image",
                ".gif": "image",
                ".svg": "image",
            }

            file_type = ext_to_type.get(file_ext, "unknown")

            # Get MIME type
            mime_type, _ = mimetypes.guess_type(file_path)
            if not mime_type:
                mime_type = "application/octet-stream"

            return {
                "file_path": file_path,
                "file_name": filename,
                "file_type": file_type,
                "file_extension": file_ext,
                "file_size": file_stat.st_size,
                "mime_type": mime_type,
                "created_time": datetime.fromtimestamp(file_stat.st_ctime).isoformat(),
                "modified_time": datetime.fromtimestamp(file_stat.st_mtime).isoformat(),
                "discovered_at": datetime.now().isoformat(),
            }

        except (OSError, PermissionError) as e:
            # Log error but continue with other files
            self.logger.warning(f"Could not process file {file_path}: {e}")
            return None

    def _matches_pattern(self, filename: str, pattern: str) -> bool:
        """Check if filename matches a glob-style pattern.

        Args:
            filename: Name of the file to check
            pattern: Glob pattern (e.g., '*.csv', 'data*', 'file?.txt')

        Returns:
            True if filename matches pattern
        """
        import fnmatch

        return fnmatch.fnmatch(filename, pattern)
