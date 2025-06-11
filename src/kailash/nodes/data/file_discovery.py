"""File discovery and analysis nodes for file system operations."""

import hashlib
import mimetypes
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kailash.nodes.base import Node, NodeParameter, register_node


@register_node()
class FileDiscoveryNode(Node):
    """
    Discovers and analyzes files and directories in the file system.

    This node provides comprehensive file discovery capabilities, replacing
    DataTransformer with embedded Python code for file processing tasks.
    It can scan directories, analyze file properties, detect file types,
    and generate detailed file system reports.

    Design Philosophy:
        File system operations require robust discovery and analysis capabilities.
        This node eliminates the need for custom file processing code in
        DataTransformer nodes by providing dedicated, configurable file
        discovery with filtering, analysis, and reporting features.

    Upstream Dependencies:
        - Path configuration nodes
        - Filter criteria nodes
        - Authentication/permission nodes
        - Schedule/trigger nodes

    Downstream Consumers:
        - File processing nodes
        - Content analysis nodes
        - Backup and archival nodes
        - Security scanning nodes
        - Compliance reporting nodes

    Configuration:
        - Search paths and patterns
        - File type filters
        - Size and date criteria
        - Analysis depth and options
        - Output format preferences

    Implementation Details:
        - Recursive directory traversal
        - File metadata extraction
        - Content type detection
        - Permission and ownership analysis
        - Hash calculation for integrity

    Error Handling:
        - Permission denied gracefully handled
        - Broken symlinks detected
        - Invalid paths reported
        - Partial results on errors

    Side Effects:
        - File system access (read-only by default)
        - Temporary file creation for analysis
        - Metadata caching for performance
        - Logging of discovery activities

    Examples:
        >>> # Discover all Python files in a project
        >>> discovery = FileDiscoveryNode(
        ...     search_paths=['/path/to/project'],
        ...     file_patterns=['*.py'],
        ...     include_metadata=True,
        ...     max_depth=5
        ... )
        >>> result = discovery.execute()
        >>> assert 'discovered_files' in result
        >>> assert all(f['name'].endswith('.py') for f in result['discovered_files'])
        >>>
        >>> # Find large files for cleanup
        >>> discovery = FileDiscoveryNode(
        ...     search_paths=['/var/log', '/tmp'],
        ...     min_size_mb=100,
        ...     older_than_days=30,
        ...     include_checksums=True
        ... )
        >>> result = discovery.execute()
        >>> large_files = result['discovered_files']
    """

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "search_paths": NodeParameter(
                name="search_paths",
                type=list,
                required=True,
                description="List of paths to search for files",
            ),
            "file_patterns": NodeParameter(
                name="file_patterns",
                type=list,
                required=False,
                default=["*"],
                description="File name patterns to match (glob-style)",
            ),
            "exclude_patterns": NodeParameter(
                name="exclude_patterns",
                type=list,
                required=False,
                default=[],
                description="File name patterns to exclude",
            ),
            "max_depth": NodeParameter(
                name="max_depth",
                type=int,
                required=False,
                default=10,
                description="Maximum directory depth to search",
            ),
            "include_metadata": NodeParameter(
                name="include_metadata",
                type=bool,
                required=False,
                default=True,
                description="Include detailed file metadata",
            ),
            "include_checksums": NodeParameter(
                name="include_checksums",
                type=bool,
                required=False,
                default=False,
                description="Calculate file checksums (slower but more thorough)",
            ),
            "min_size_mb": NodeParameter(
                name="min_size_mb",
                type=float,
                required=False,
                description="Minimum file size in megabytes",
            ),
            "max_size_mb": NodeParameter(
                name="max_size_mb",
                type=float,
                required=False,
                description="Maximum file size in megabytes",
            ),
            "older_than_days": NodeParameter(
                name="older_than_days",
                type=int,
                required=False,
                description="Only include files older than N days",
            ),
            "newer_than_days": NodeParameter(
                name="newer_than_days",
                type=int,
                required=False,
                description="Only include files newer than N days",
            ),
            "follow_symlinks": NodeParameter(
                name="follow_symlinks",
                type=bool,
                required=False,
                default=False,
                description="Follow symbolic links during traversal",
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        search_paths = kwargs["search_paths"]
        file_patterns = kwargs.get("file_patterns", ["*"])
        exclude_patterns = kwargs.get("exclude_patterns", [])
        max_depth = kwargs.get("max_depth", 10)
        include_metadata = kwargs.get("include_metadata", True)
        include_checksums = kwargs.get("include_checksums", False)
        min_size_mb = kwargs.get("min_size_mb")
        max_size_mb = kwargs.get("max_size_mb")
        older_than_days = kwargs.get("older_than_days")
        newer_than_days = kwargs.get("newer_than_days")
        follow_symlinks = kwargs.get("follow_symlinks", False)

        start_time = time.time()
        discovered_files = []
        discovery_stats = {
            "total_directories_scanned": 0,
            "total_files_found": 0,
            "total_files_matching": 0,
            "access_errors": 0,
            "broken_symlinks": 0,
        }

        for search_path in search_paths:
            try:
                path_files, path_stats = self._discover_files_in_path(
                    search_path=search_path,
                    file_patterns=file_patterns,
                    exclude_patterns=exclude_patterns,
                    max_depth=max_depth,
                    include_metadata=include_metadata,
                    include_checksums=include_checksums,
                    min_size_mb=min_size_mb,
                    max_size_mb=max_size_mb,
                    older_than_days=older_than_days,
                    newer_than_days=newer_than_days,
                    follow_symlinks=follow_symlinks,
                )

                discovered_files.extend(path_files)

                # Aggregate stats
                for key, value in path_stats.items():
                    discovery_stats[key] += value

            except Exception as e:
                discovery_stats["access_errors"] += 1
                # Add error entry to results
                discovered_files.append(
                    {
                        "type": "discovery_error",
                        "path": search_path,
                        "error": str(e),
                        "timestamp": datetime.now(UTC).isoformat() + "Z",
                    }
                )

        execution_time = time.time() - start_time

        # Generate summary
        summary = self._generate_discovery_summary(
            discovered_files, discovery_stats, execution_time
        )

        return {
            "discovered_files": discovered_files,
            "discovery_summary": summary,
            "discovery_stats": discovery_stats,
            "total_files": len(
                [f for f in discovered_files if f.get("type") != "discovery_error"]
            ),
            "execution_time": execution_time,
            "timestamp": datetime.now(UTC).isoformat() + "Z",
        }

    def _discover_files_in_path(
        self,
        search_path: str,
        file_patterns: list[str],
        exclude_patterns: list[str],
        max_depth: int,
        include_metadata: bool,
        include_checksums: bool,
        min_size_mb: float | None,
        max_size_mb: float | None,
        older_than_days: int | None,
        newer_than_days: int | None,
        follow_symlinks: bool,
    ) -> tuple[list[dict[str, Any]], dict[str, int]]:
        """Discover files in a specific path."""

        discovered_files = []
        stats = {
            "total_directories_scanned": 0,
            "total_files_found": 0,
            "total_files_matching": 0,
            "access_errors": 0,
            "broken_symlinks": 0,
        }

        try:
            search_path_obj = Path(search_path)
            if not search_path_obj.exists():
                raise FileNotFoundError(f"Search path does not exist: {search_path}")

            # Walk the directory tree
            for root, dirs, files in os.walk(search_path, followlinks=follow_symlinks):
                current_depth = len(Path(root).relative_to(search_path_obj).parts)

                # Skip if max depth exceeded
                if current_depth > max_depth:
                    dirs[:] = []  # Don't descend further
                    continue

                stats["total_directories_scanned"] += 1

                for file_name in files:
                    file_path = os.path.join(root, file_name)
                    stats["total_files_found"] += 1

                    try:
                        # Check if file matches patterns
                        if not self._matches_patterns(
                            file_name, file_patterns, exclude_patterns
                        ):
                            continue

                        file_info = self._analyze_file(
                            file_path=file_path,
                            include_metadata=include_metadata,
                            include_checksums=include_checksums,
                        )

                        # Apply size filters
                        if min_size_mb is not None:
                            if file_info.get("size_mb", 0) < min_size_mb:
                                continue

                        if max_size_mb is not None:
                            if file_info.get("size_mb", 0) > max_size_mb:
                                continue

                        # Apply date filters
                        if older_than_days is not None or newer_than_days is not None:
                            if not self._matches_date_criteria(
                                file_info, older_than_days, newer_than_days
                            ):
                                continue

                        discovered_files.append(file_info)
                        stats["total_files_matching"] += 1

                    except (OSError, PermissionError) as e:
                        stats["access_errors"] += 1
                        # Add error info for this specific file
                        discovered_files.append(
                            {
                                "type": "file_access_error",
                                "path": file_path,
                                "name": file_name,
                                "error": str(e),
                                "timestamp": datetime.now(UTC).isoformat() + "Z",
                            }
                        )

        except Exception:
            stats["access_errors"] += 1
            raise

        return discovered_files, stats

    def _matches_patterns(
        self, file_name: str, include_patterns: list[str], exclude_patterns: list[str]
    ) -> bool:
        """Check if filename matches include patterns and doesn't match exclude patterns."""
        import fnmatch

        # Check exclude patterns first
        for pattern in exclude_patterns:
            if fnmatch.fnmatch(file_name, pattern):
                return False

        # Check include patterns
        if not include_patterns or include_patterns == ["*"]:
            return True

        for pattern in include_patterns:
            if fnmatch.fnmatch(file_name, pattern):
                return True

        return False

    def _analyze_file(
        self, file_path: str, include_metadata: bool, include_checksums: bool
    ) -> dict[str, Any]:
        """Analyze a single file and return its information."""

        file_path_obj = Path(file_path)
        file_info = {
            "type": "file",
            "path": str(file_path),
            "name": file_path_obj.name,
            "directory": str(file_path_obj.parent),
        }

        try:
            # Basic file stats
            stat_info = file_path_obj.stat()

            file_info.update(
                {
                    "size_bytes": stat_info.st_size,
                    "size_mb": stat_info.st_size / (1024 * 1024),
                    "created_timestamp": stat_info.st_ctime,
                    "modified_timestamp": stat_info.st_mtime,
                    "accessed_timestamp": stat_info.st_atime,
                    "created_date": datetime.fromtimestamp(
                        stat_info.st_ctime, UTC
                    ).isoformat()
                    + "Z",
                    "modified_date": datetime.fromtimestamp(
                        stat_info.st_mtime, UTC
                    ).isoformat()
                    + "Z",
                    "accessed_date": datetime.fromtimestamp(
                        stat_info.st_atime, UTC
                    ).isoformat()
                    + "Z",
                }
            )

            if include_metadata:
                # File type detection
                mime_type, encoding = mimetypes.guess_type(file_path)
                file_info.update(
                    {
                        "mime_type": mime_type,
                        "encoding": encoding,
                        "extension": file_path_obj.suffix.lower(),
                    }
                )

                # File permissions
                file_info.update(
                    {
                        "permissions": oct(stat_info.st_mode)[-3:],
                        "owner_uid": stat_info.st_uid,
                        "group_gid": stat_info.st_gid,
                        "is_readable": os.access(file_path, os.R_OK),
                        "is_writable": os.access(file_path, os.W_OK),
                        "is_executable": os.access(file_path, os.X_OK),
                    }
                )

                # Symbolic link detection
                if file_path_obj.is_symlink():
                    try:
                        link_target = os.readlink(file_path)
                        file_info.update(
                            {
                                "is_symlink": True,
                                "link_target": link_target,
                                "link_target_exists": os.path.exists(link_target),
                            }
                        )
                    except OSError:
                        file_info.update(
                            {
                                "is_symlink": True,
                                "link_target": None,
                                "link_target_exists": False,
                            }
                        )
                else:
                    file_info["is_symlink"] = False

                # Content analysis for text files
                if mime_type and mime_type.startswith("text/"):
                    try:
                        with open(file_path, encoding="utf-8", errors="ignore") as f:
                            content_sample = f.read(1024)  # Read first 1KB
                            file_info.update(
                                {
                                    "line_count": len(content_sample.splitlines()),
                                    "character_count": len(content_sample),
                                    "content_sample": (
                                        content_sample[:200] + "..."
                                        if len(content_sample) > 200
                                        else content_sample
                                    ),
                                }
                            )
                    except (UnicodeDecodeError, PermissionError):
                        pass

            if include_checksums:
                # Calculate file hashes
                file_info.update(self._calculate_checksums(file_path))

        except (OSError, PermissionError) as e:
            file_info.update(
                {
                    "error": str(e),
                    "accessible": False,
                }
            )

        file_info["timestamp"] = datetime.now(UTC).isoformat() + "Z"
        return file_info

    def _calculate_checksums(self, file_path: str) -> dict[str, str]:
        """Calculate MD5 and SHA256 checksums for a file."""
        checksums = {}

        try:
            md5_hash = hashlib.md5()
            sha256_hash = hashlib.sha256()

            with open(file_path, "rb") as f:
                # Read file in chunks to handle large files efficiently
                for chunk in iter(lambda: f.read(4096), b""):
                    md5_hash.update(chunk)
                    sha256_hash.update(chunk)

            checksums.update(
                {
                    "md5": md5_hash.hexdigest(),
                    "sha256": sha256_hash.hexdigest(),
                }
            )
        except (OSError, PermissionError) as e:
            checksums.update(
                {
                    "checksum_error": str(e),
                }
            )

        return checksums

    def _matches_date_criteria(
        self,
        file_info: dict[str, Any],
        older_than_days: int | None,
        newer_than_days: int | None,
    ) -> bool:
        """Check if file matches date criteria."""

        modified_timestamp = file_info.get("modified_timestamp")
        if modified_timestamp is None:
            return True

        now = time.time()
        file_age_days = (now - modified_timestamp) / (24 * 3600)

        if older_than_days is not None and file_age_days < older_than_days:
            return False

        if newer_than_days is not None and file_age_days > newer_than_days:
            return False

        return True

    def _generate_discovery_summary(
        self,
        discovered_files: list[dict],
        discovery_stats: dict[str, int],
        execution_time: float,
    ) -> dict[str, Any]:
        """Generate summary of file discovery results."""

        # Count files by type/extension
        extension_counts = {}
        mime_type_counts = {}
        size_distribution = {"small": 0, "medium": 0, "large": 0, "very_large": 0}

        total_size_mb = 0
        error_count = 0

        for file_info in discovered_files:
            if file_info.get("type") in ["discovery_error", "file_access_error"]:
                error_count += 1
                continue

            # Extension analysis
            extension = file_info.get("extension", "")
            extension_counts[extension] = extension_counts.get(extension, 0) + 1

            # MIME type analysis
            mime_type = file_info.get("mime_type", "unknown")
            mime_type_counts[mime_type] = mime_type_counts.get(mime_type, 0) + 1

            # Size distribution
            size_mb = file_info.get("size_mb", 0)
            total_size_mb += size_mb

            if size_mb < 1:
                size_distribution["small"] += 1
            elif size_mb < 50:
                size_distribution["medium"] += 1
            elif size_mb < 500:
                size_distribution["large"] += 1
            else:
                size_distribution["very_large"] += 1

        # Find largest files
        file_sizes = [
            (f.get("size_mb", 0), f.get("path", ""))
            for f in discovered_files
            if f.get("type") == "file"
        ]
        largest_files = sorted(file_sizes, reverse=True)[:10]

        return {
            "execution_time": execution_time,
            "total_files_discovered": len(discovered_files) - error_count,
            "total_errors": error_count,
            "total_size_mb": total_size_mb,
            "average_file_size_mb": total_size_mb
            / max(1, len(discovered_files) - error_count),
            "extension_distribution": dict(
                sorted(extension_counts.items(), key=lambda x: x[1], reverse=True)
            ),
            "mime_type_distribution": dict(
                sorted(mime_type_counts.items(), key=lambda x: x[1], reverse=True)
            ),
            "size_distribution": size_distribution,
            "largest_files": [
                {"size_mb": size, "path": path} for size, path in largest_files[:5]
            ],
            "discovery_stats": discovery_stats,
        }
