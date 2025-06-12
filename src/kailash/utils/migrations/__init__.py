"""Database migration framework for Kailash SDK.

This module provides a Django-inspired but async-first migration system
for managing database schema changes across different database backends.

Key Features:
- Async-first design for non-blocking migrations
- Support for PostgreSQL, MySQL, and SQLite
- Forward and backward migrations
- Dependency management between migrations
- Dry-run capability
- Migration history tracking
- Schema versioning
"""

from kailash.utils.migrations.generator import MigrationGenerator
from kailash.utils.migrations.models import Migration, MigrationHistory
from kailash.utils.migrations.runner import MigrationRunner

__all__ = [
    "Migration",
    "MigrationHistory",
    "MigrationRunner",
    "MigrationGenerator",
]
