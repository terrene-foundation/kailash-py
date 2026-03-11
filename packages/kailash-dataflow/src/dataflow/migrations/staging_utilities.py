#!/usr/bin/env python3
"""
Staging Environment Utilities - TODO-141 Phase 1

Provides utility functions and helpers for staging environment management,
configuration validation, and data sampling calculations.

UTILITY FUNCTIONS:
- Database name generation for staging environments
- Data sample size calculations and validation
- Configuration validation and sanitization
- Resource usage estimation and monitoring
- Cleanup scheduling and management

DESIGN PRINCIPLES:
- Pure functions for easy testing
- Comprehensive input validation
- Performance-optimized calculations
- Clear error messages and logging
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)


@dataclass
class StagingEnvironmentStats:
    """Statistics for staging environment resource usage."""

    estimated_disk_mb: float
    estimated_memory_mb: float
    estimated_cpu_percent: float
    estimated_connection_count: int
    estimated_duration_seconds: int


@dataclass
class DataSamplingStats:
    """Statistics for data sampling operations."""

    total_tables: int
    total_rows_estimated: int
    sample_rows_estimated: int
    estimated_sampling_time_seconds: float
    sampling_strategy: str = "RANDOM"


class StagingUtilities:
    """Utility functions for staging environment management."""

    @staticmethod
    def generate_staging_database_name(
        production_db_name: str,
        timestamp_suffix: bool = True,
        prefix: str = "staging",
        max_length: int = 63,  # PostgreSQL identifier limit
    ) -> str:
        """
        Generate a unique staging database name based on production database name.

        Args:
            production_db_name: Name of the production database
            timestamp_suffix: Whether to append timestamp suffix
            prefix: Prefix for staging database name
            max_length: Maximum length of database name (PostgreSQL limit is 63)

        Returns:
            str: Generated staging database name

        Raises:
            ValueError: Invalid database name or configuration
        """
        # Validate inputs
        if not production_db_name or not isinstance(production_db_name, str):
            raise ValueError("Production database name must be a non-empty string")

        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", production_db_name):
            raise ValueError(f"Invalid production database name: {production_db_name}")

        if not prefix or not isinstance(prefix, str):
            raise ValueError("Prefix must be a non-empty string")

        # Clean production database name
        clean_prod_name = production_db_name.lower().replace("-", "_")

        # Build staging name
        base_name = f"{prefix}_{clean_prod_name}"

        if timestamp_suffix:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            staging_name = f"{base_name}_{timestamp}"
        else:
            staging_name = base_name

        # Truncate if necessary
        if len(staging_name) > max_length:
            # Keep the timestamp if present, truncate the middle
            if timestamp_suffix:
                timestamp_part = f"_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                max_base_length = max_length - len(timestamp_part)
                truncated_base = base_name[:max_base_length]
                staging_name = f"{truncated_base}{timestamp_part}"
            else:
                staging_name = staging_name[:max_length]

        logger.debug(f"Generated staging database name: {staging_name}")
        return staging_name

    @staticmethod
    def calculate_data_sample_size(
        total_rows: int,
        sample_percentage: float,
        min_sample_rows: int = 100,
        max_sample_rows: int = 1000000,
    ) -> int:
        """
        Calculate the number of rows to sample based on percentage and constraints.

        Args:
            total_rows: Total number of rows in the table
            sample_percentage: Percentage to sample (0.0-100.0)
            min_sample_rows: Minimum number of rows to sample
            max_sample_rows: Maximum number of rows to sample

        Returns:
            int: Number of rows to sample

        Raises:
            ValueError: Invalid parameters
        """
        # Validate inputs
        if total_rows < 0:
            raise ValueError("Total rows must be non-negative")

        if not 0.0 <= sample_percentage <= 100.0:
            raise ValueError("Sample percentage must be between 0.0 and 100.0")

        if min_sample_rows < 0 or max_sample_rows < 0:
            raise ValueError("Sample row limits must be non-negative")

        if min_sample_rows > max_sample_rows:
            raise ValueError("Minimum sample rows cannot exceed maximum sample rows")

        # Calculate sample size
        calculated_sample = int(total_rows * (sample_percentage / 100.0))

        # Apply constraints
        if total_rows == 0:
            return 0

        sample_rows = max(min_sample_rows, min(calculated_sample, max_sample_rows))

        # Don't sample more rows than available
        sample_rows = min(sample_rows, total_rows)

        logger.debug(
            f"Calculated sample size: {sample_rows} from {total_rows} rows "
            f"({sample_percentage}% target)"
        )

        return sample_rows

    @staticmethod
    def validate_staging_environment_config(config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate staging environment configuration parameters.

        Args:
            config: Configuration dictionary to validate

        Returns:
            Dict[str, Any]: Validation result with errors and warnings
        """
        result = {"valid": True, "errors": [], "warnings": [], "sanitized_config": {}}

        # Required fields validation
        required_fields = [
            "default_data_sample_size",
            "max_staging_environments",
            "cleanup_timeout_seconds",
        ]

        for field in required_fields:
            if field not in config:
                result["errors"].append(f"Missing required field: {field}")
                result["valid"] = False

        # Data sample size validation
        if "default_data_sample_size" in config:
            sample_size = config["default_data_sample_size"]
            if (
                not isinstance(sample_size, (int, float))
                or not 0.0 <= sample_size <= 1.0
            ):
                result["errors"].append(
                    "default_data_sample_size must be a number between 0.0 and 1.0"
                )
                result["valid"] = False
            else:
                result["sanitized_config"]["default_data_sample_size"] = float(
                    sample_size
                )

        # Max environments validation
        if "max_staging_environments" in config:
            max_envs = config["max_staging_environments"]
            if not isinstance(max_envs, int) or max_envs <= 0:
                result["errors"].append(
                    "max_staging_environments must be a positive integer"
                )
                result["valid"] = False
            elif max_envs > 10:
                result["warnings"].append(
                    f"max_staging_environments ({max_envs}) is high, may consume significant resources"
                )
                result["sanitized_config"]["max_staging_environments"] = max_envs
            else:
                result["sanitized_config"]["max_staging_environments"] = max_envs

        # Cleanup timeout validation
        if "cleanup_timeout_seconds" in config:
            timeout = config["cleanup_timeout_seconds"]
            if not isinstance(timeout, int) or timeout <= 0:
                result["errors"].append(
                    "cleanup_timeout_seconds must be a positive integer"
                )
                result["valid"] = False
            elif timeout < 30:
                result["warnings"].append(
                    f"cleanup_timeout_seconds ({timeout}) is very low, may cause premature timeouts"
                )
                result["sanitized_config"]["cleanup_timeout_seconds"] = timeout
            else:
                result["sanitized_config"]["cleanup_timeout_seconds"] = timeout

        # Resource limits validation
        if "resource_limits" in config:
            limits = config["resource_limits"]
            if not isinstance(limits, dict):
                result["errors"].append("resource_limits must be a dictionary")
                result["valid"] = False
            else:
                sanitized_limits = {}

                # Validate memory limit
                if "max_memory_mb" in limits:
                    mem_limit = limits["max_memory_mb"]
                    if not isinstance(mem_limit, (int, float)) or mem_limit <= 0:
                        result["errors"].append(
                            "max_memory_mb must be a positive number"
                        )
                        result["valid"] = False
                    else:
                        sanitized_limits["max_memory_mb"] = float(mem_limit)
                        if mem_limit > 8192:  # 8GB
                            result["warnings"].append(
                                f"max_memory_mb ({mem_limit}) is very high"
                            )

                # Validate disk limit
                if "max_disk_mb" in limits:
                    disk_limit = limits["max_disk_mb"]
                    if not isinstance(disk_limit, (int, float)) or disk_limit <= 0:
                        result["errors"].append("max_disk_mb must be a positive number")
                        result["valid"] = False
                    else:
                        sanitized_limits["max_disk_mb"] = float(disk_limit)
                        if disk_limit > 51200:  # 50GB
                            result["warnings"].append(
                                f"max_disk_mb ({disk_limit}) is very high"
                            )

                result["sanitized_config"]["resource_limits"] = sanitized_limits

        return result

    @staticmethod
    def estimate_staging_environment_resources(
        table_count: int,
        estimated_total_rows: int,
        sample_percentage: float,
        include_indexes: bool = True,
        include_constraints: bool = True,
    ) -> StagingEnvironmentStats:
        """
        Estimate resource requirements for staging environment.

        Args:
            table_count: Number of tables to replicate
            estimated_total_rows: Estimated total rows across all tables
            sample_percentage: Data sampling percentage (0.0-100.0)
            include_indexes: Whether to include index creation
            include_constraints: Whether to include constraint creation

        Returns:
            StagingEnvironmentStats: Estimated resource requirements
        """
        # Base calculations
        sample_rows = int(estimated_total_rows * (sample_percentage / 100.0))

        # Disk estimation (rough heuristics)
        base_disk_mb = 10.0  # Base schema overhead
        data_disk_mb = sample_rows * 0.001  # ~1KB per row average
        index_disk_mb = (
            data_disk_mb * 0.3 if include_indexes else 0
        )  # ~30% overhead for indexes
        constraint_overhead_mb = table_count * 0.1 if include_constraints else 0

        total_disk_mb = (
            base_disk_mb + data_disk_mb + index_disk_mb + constraint_overhead_mb
        )

        # Memory estimation
        base_memory_mb = 50.0  # Base PostgreSQL overhead
        connection_memory_mb = 10.0  # Per connection memory
        work_memory_mb = min(
            sample_rows * 0.0001, 100.0
        )  # Working memory for operations

        total_memory_mb = base_memory_mb + connection_memory_mb + work_memory_mb

        # CPU estimation (percentage during operations)
        base_cpu_percent = 5.0  # Idle overhead
        operation_cpu_percent = min(
            sample_rows * 0.00001, 50.0
        )  # CPU for data operations

        total_cpu_percent = base_cpu_percent + operation_cpu_percent

        # Connection estimation
        estimated_connections = min(table_count // 10 + 2, 10)  # Conservative estimate

        # Duration estimation (seconds)
        schema_creation_time = table_count * 2  # ~2 seconds per table
        data_sampling_time = sample_rows * 0.0001  # ~0.1ms per row
        index_creation_time = (
            (table_count * 5) if include_indexes else 0
        )  # ~5 seconds per table

        total_duration = int(
            schema_creation_time + data_sampling_time + index_creation_time
        )

        stats = StagingEnvironmentStats(
            estimated_disk_mb=round(total_disk_mb, 2),
            estimated_memory_mb=round(total_memory_mb, 2),
            estimated_cpu_percent=round(total_cpu_percent, 1),
            estimated_connection_count=estimated_connections,
            estimated_duration_seconds=total_duration,
        )

        logger.debug(f"Estimated staging environment resources: {stats}")
        return stats

    @staticmethod
    def calculate_data_sampling_estimates(
        table_data: List[Dict[str, Any]], sample_percentage: float
    ) -> DataSamplingStats:
        """
        Calculate data sampling estimates for multiple tables.

        Args:
            table_data: List of table information dictionaries
            sample_percentage: Percentage to sample (0.0-100.0)

        Returns:
            DataSamplingStats: Sampling statistics and estimates
        """
        total_tables = len(table_data)
        total_rows = sum(table.get("row_count", 0) for table in table_data)
        sample_rows = int(total_rows * (sample_percentage / 100.0))

        # Estimate sampling time based on row count and complexity
        base_time_per_row = 0.001  # 1ms per row base time
        complexity_multiplier = 1.0

        # Adjust for table complexity
        for table in table_data:
            if table.get("has_foreign_keys", False):
                complexity_multiplier += 0.1
            if table.get("has_indexes", False):
                complexity_multiplier += 0.05
            if table.get("has_triggers", False):
                complexity_multiplier += 0.15

        complexity_multiplier = min(complexity_multiplier, 2.0)  # Cap at 2x

        estimated_time = sample_rows * base_time_per_row * complexity_multiplier

        stats = DataSamplingStats(
            total_tables=total_tables,
            total_rows_estimated=total_rows,
            sample_rows_estimated=sample_rows,
            estimated_sampling_time_seconds=round(estimated_time, 2),
            sampling_strategy="RANDOM",
        )

        logger.debug(f"Calculated data sampling estimates: {stats}")
        return stats

    @staticmethod
    def generate_cleanup_schedule(
        created_at: datetime,
        auto_cleanup_hours: int = 24,
        max_lifetime_hours: int = 168,  # 1 week
    ) -> Tuple[datetime, datetime]:
        """
        Generate cleanup schedule for staging environment.

        Args:
            created_at: When the staging environment was created
            auto_cleanup_hours: Hours after creation for auto cleanup
            max_lifetime_hours: Maximum lifetime in hours

        Returns:
            Tuple[datetime, datetime]: (scheduled_cleanup_time, max_lifetime_time)
        """
        if auto_cleanup_hours <= 0 or max_lifetime_hours <= 0:
            raise ValueError("Cleanup hours must be positive")

        if auto_cleanup_hours > max_lifetime_hours:
            raise ValueError("Auto cleanup time cannot exceed max lifetime")

        scheduled_cleanup = created_at + timedelta(hours=auto_cleanup_hours)
        max_lifetime = created_at + timedelta(hours=max_lifetime_hours)

        logger.debug(
            f"Generated cleanup schedule: auto at {scheduled_cleanup}, "
            f"max at {max_lifetime}"
        )

        return scheduled_cleanup, max_lifetime

    @staticmethod
    def sanitize_database_identifier(identifier: str, max_length: int = 63) -> str:
        """
        Sanitize database identifier to ensure it's valid for PostgreSQL.

        Args:
            identifier: Raw identifier to sanitize
            max_length: Maximum length for identifier

        Returns:
            str: Sanitized identifier

        Raises:
            ValueError: Invalid identifier that cannot be sanitized
        """
        if not identifier:
            raise ValueError("Identifier cannot be empty")

        # Convert to lowercase and replace invalid characters
        sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", identifier.lower())

        # Ensure it starts with letter or underscore
        if not re.match(r"^[a-zA-Z_]", sanitized):
            sanitized = f"_{sanitized}"

        # Truncate to max length
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length]

        # Ensure it doesn't end with underscore after truncation
        sanitized = sanitized.rstrip("_")

        if not sanitized:
            raise ValueError("Identifier results in empty string after sanitization")

        return sanitized

    @staticmethod
    def format_resource_usage(
        disk_mb: float, memory_mb: float, cpu_percent: float
    ) -> str:
        """
        Format resource usage for display.

        Args:
            disk_mb: Disk usage in MB
            memory_mb: Memory usage in MB
            cpu_percent: CPU usage percentage

        Returns:
            str: Formatted resource usage string
        """

        def format_bytes(mb: float) -> str:
            if mb < 1024:
                return f"{mb:.1f} MB"
            else:
                return f"{mb/1024:.1f} GB"

        return (
            f"Disk: {format_bytes(disk_mb)}, "
            f"Memory: {format_bytes(memory_mb)}, "
            f"CPU: {cpu_percent:.1f}%"
        )
