"""
EATP v0.8.0 Migration: Add Human Origin Tracking.

This migration adds EATP (Enterprise Agent Trust Protocol) columns to
the trust database tables for complete human traceability.

Changes:
1. delegation_records table:
   - human_origin_id: Links to the human who authorized the delegation chain
   - human_origin_data: JSONB containing full HumanOrigin record
   - delegation_chain: Array of agent IDs from human to current agent
   - delegation_depth: Integer distance from the human (0 = direct)

2. audit_anchors table:
   - human_origin_id: Links to the human who ultimately authorized the action
   - human_origin_data: JSONB containing full HumanOrigin record

Usage:
    # From command line
    python -m kaizen.trust.migrations.eatp_human_origin

    # Or programmatically
    from kaizen.trust.migrations.eatp_human_origin import EATPMigration
    migration = EATPMigration(database_url)
    await migration.run()

Reference: docs/plans/eatp-integration/07-data-flows.md

Author: Kaizen Framework Team
Created: 2026-01-02
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import asyncpg

logger = logging.getLogger(__name__)


class EATPMigration:
    """
    EATP v0.8.0 database migration.

    Adds human origin tracking columns to trust tables for complete
    traceability from agent actions back to authorizing humans.

    This migration is:
    - Idempotent: Safe to run multiple times (checks before adding)
    - Backward Compatible: Old records work with NULL human_origin
    - Transactional: All changes rolled back on failure
    """

    VERSION = "0.8.0"
    MIGRATION_NAME = "eatp_human_origin"

    def __init__(self, database_url: Optional[str] = None):
        """
        Initialize migration.

        Args:
            database_url: PostgreSQL connection string.
                         Defaults to POSTGRES_URL environment variable.
        """
        self.database_url = database_url or os.getenv("POSTGRES_URL")
        if not self.database_url:
            raise ValueError(
                "No database URL provided. Set POSTGRES_URL environment variable "
                "or pass database_url parameter."
            )

    async def run(self) -> dict:
        """
        Run the EATP migration.

        Returns:
            Migration result with details of changes made

        Raises:
            Exception: If migration fails (with rollback)
        """
        logger.info(f"Starting EATP v{self.VERSION} migration: {self.MIGRATION_NAME}")

        conn = await asyncpg.connect(self.database_url)
        try:
            result = await self._run_migration(conn)
            logger.info(f"EATP migration completed successfully: {result}")
            return result
        except Exception as e:
            logger.error(f"EATP migration failed: {e}")
            raise
        finally:
            await conn.close()

    async def _run_migration(self, conn: asyncpg.Connection) -> dict:
        """
        Execute migration within a transaction.

        Args:
            conn: Database connection

        Returns:
            Migration result details
        """
        result = {
            "migration": self.MIGRATION_NAME,
            "version": self.VERSION,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "changes": [],
        }

        async with conn.transaction():
            # 1. Add EATP columns to delegation_records table
            delegation_changes = await self._migrate_delegation_records(conn)
            result["changes"].extend(delegation_changes)

            # 2. Add EATP columns to audit_anchors table
            audit_changes = await self._migrate_audit_anchors(conn)
            result["changes"].extend(audit_changes)

            # 3. Create indexes for efficient querying
            index_changes = await self._create_indexes(conn)
            result["changes"].extend(index_changes)

            # 4. Record migration in migrations table
            await self._record_migration(conn)
            result["changes"].append("Recorded migration in eatp_migrations table")

        result["completed_at"] = datetime.now(timezone.utc).isoformat()
        return result

    async def _migrate_delegation_records(self, conn: asyncpg.Connection) -> list:
        """
        Add EATP columns to delegation_records table.

        Columns added:
        - human_origin_id: VARCHAR(255) - Human ID from auth system
        - human_origin_data: JSONB - Full HumanOrigin record
        - delegation_chain: TEXT[] - Array of agent IDs in chain
        - delegation_depth: INTEGER - Distance from human (default 0)
        """
        changes = []

        # Check if table exists
        table_exists = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'delegation_records'
            )
            """
        )

        if not table_exists:
            # Create table with EATP columns if it doesn't exist
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS delegation_records (
                    id VARCHAR(255) PRIMARY KEY,
                    delegator_id VARCHAR(255) NOT NULL,
                    delegatee_id VARCHAR(255) NOT NULL,
                    task_id VARCHAR(255),
                    capabilities JSONB,
                    constraints JSONB,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    expires_at TIMESTAMP WITH TIME ZONE,
                    is_active BOOLEAN DEFAULT TRUE,
                    -- EATP v0.8.0 columns
                    human_origin_id VARCHAR(255),
                    human_origin_data JSONB,
                    delegation_chain TEXT[],
                    delegation_depth INTEGER DEFAULT 0
                )
                """
            )
            changes.append("Created delegation_records table with EATP columns")
        else:
            # Add columns if they don't exist
            columns_to_add = [
                ("human_origin_id", "VARCHAR(255)"),
                ("human_origin_data", "JSONB"),
                ("delegation_chain", "TEXT[]"),
                ("delegation_depth", "INTEGER DEFAULT 0"),
            ]

            for column_name, column_type in columns_to_add:
                column_exists = await conn.fetchval(
                    """
                    SELECT EXISTS (
                        SELECT FROM information_schema.columns
                        WHERE table_name = 'delegation_records'
                        AND column_name = $1
                    )
                    """,
                    column_name,
                )

                if not column_exists:
                    await conn.execute(
                        f"ALTER TABLE delegation_records ADD COLUMN {column_name} {column_type}"
                    )
                    changes.append(f"Added column {column_name} to delegation_records")

        return changes

    async def _migrate_audit_anchors(self, conn: asyncpg.Connection) -> list:
        """
        Add EATP columns to audit_anchors table.

        Columns added:
        - human_origin_id: VARCHAR(255) - Human ID from auth system
        - human_origin_data: JSONB - Full HumanOrigin record
        """
        changes = []

        # Check if table exists
        table_exists = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'audit_anchors'
            )
            """
        )

        if not table_exists:
            # Create table with EATP columns if it doesn't exist
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_anchors (
                    id VARCHAR(255) PRIMARY KEY,
                    agent_id VARCHAR(255) NOT NULL,
                    action VARCHAR(255) NOT NULL,
                    resource VARCHAR(255),
                    result VARCHAR(50),
                    context_data JSONB,
                    parent_anchor_id VARCHAR(255),
                    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    signature TEXT,
                    -- EATP v0.8.0 columns
                    human_origin_id VARCHAR(255),
                    human_origin_data JSONB
                )
                """
            )
            changes.append("Created audit_anchors table with EATP columns")
        else:
            # Add columns if they don't exist
            columns_to_add = [
                ("human_origin_id", "VARCHAR(255)"),
                ("human_origin_data", "JSONB"),
            ]

            for column_name, column_type in columns_to_add:
                column_exists = await conn.fetchval(
                    """
                    SELECT EXISTS (
                        SELECT FROM information_schema.columns
                        WHERE table_name = 'audit_anchors'
                        AND column_name = $1
                    )
                    """,
                    column_name,
                )

                if not column_exists:
                    await conn.execute(
                        f"ALTER TABLE audit_anchors ADD COLUMN {column_name} {column_type}"
                    )
                    changes.append(f"Added column {column_name} to audit_anchors")

        return changes

    async def _create_indexes(self, conn: asyncpg.Connection) -> list:
        """
        Create indexes for efficient EATP queries.

        Indexes:
        - idx_delegation_human_origin: Fast lookup by human_origin_id
        - idx_audit_human_origin: Fast lookup by human_origin_id
        - idx_delegation_depth: Efficient depth-based queries
        """
        changes = []

        indexes = [
            (
                "idx_delegation_human_origin",
                "delegation_records",
                "human_origin_id",
            ),
            (
                "idx_audit_human_origin",
                "audit_anchors",
                "human_origin_id",
            ),
            (
                "idx_delegation_depth",
                "delegation_records",
                "delegation_depth",
            ),
        ]

        for index_name, table_name, column_name in indexes:
            index_exists = await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT FROM pg_indexes
                    WHERE indexname = $1
                )
                """,
                index_name,
            )

            if not index_exists:
                await conn.execute(
                    f"CREATE INDEX {index_name} ON {table_name} ({column_name})"
                )
                changes.append(f"Created index {index_name} on {table_name}")

        return changes

    async def _record_migration(self, conn: asyncpg.Connection) -> None:
        """
        Record this migration in the migrations table.

        Creates eatp_migrations table if it doesn't exist.
        """
        # Create migrations table if not exists
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS eatp_migrations (
                id SERIAL PRIMARY KEY,
                version VARCHAR(50) NOT NULL,
                name VARCHAR(255) NOT NULL,
                applied_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                details JSONB,
                UNIQUE(version, name)
            )
            """
        )

        # Record migration (ignore if already recorded)
        await conn.execute(
            """
            INSERT INTO eatp_migrations (version, name, details)
            VALUES ($1, $2, $3)
            ON CONFLICT (version, name) DO NOTHING
            """,
            self.VERSION,
            self.MIGRATION_NAME,
            {"description": "Added human origin tracking for EATP v0.8.0"},
        )

    async def check_status(self) -> dict:
        """
        Check migration status without applying changes.

        Returns:
            Status dict with current state and pending changes
        """
        conn = await asyncpg.connect(self.database_url)
        try:
            status = {
                "version": self.VERSION,
                "migration": self.MIGRATION_NAME,
                "applied": False,
                "pending_changes": [],
            }

            # Check if migration was already applied
            try:
                applied = await conn.fetchval(
                    """
                    SELECT EXISTS (
                        SELECT FROM eatp_migrations
                        WHERE version = $1 AND name = $2
                    )
                    """,
                    self.VERSION,
                    self.MIGRATION_NAME,
                )
                status["applied"] = applied
            except asyncpg.UndefinedTableError:
                # eatp_migrations table doesn't exist yet
                pass

            if not status["applied"]:
                # Check what changes would be made
                status["pending_changes"] = await self._check_pending_changes(conn)

            return status
        finally:
            await conn.close()

    async def _check_pending_changes(self, conn: asyncpg.Connection) -> list:
        """
        Check what changes would be made by the migration.
        """
        pending = []

        # Check delegation_records columns
        for column in [
            "human_origin_id",
            "human_origin_data",
            "delegation_chain",
            "delegation_depth",
        ]:
            exists = await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.columns
                    WHERE table_name = 'delegation_records'
                    AND column_name = $1
                )
                """,
                column,
            )
            if not exists:
                pending.append(f"Add {column} to delegation_records")

        # Check audit_anchors columns
        for column in ["human_origin_id", "human_origin_data"]:
            exists = await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.columns
                    WHERE table_name = 'audit_anchors'
                    AND column_name = $1
                )
                """,
                column,
            )
            if not exists:
                pending.append(f"Add {column} to audit_anchors")

        return pending


async def main():
    """
    Run EATP migration from command line.
    """
    import argparse

    parser = argparse.ArgumentParser(description="EATP v0.8.0 Database Migration")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check migration status without applying changes",
    )
    parser.add_argument(
        "--database-url",
        help="PostgreSQL connection string (defaults to POSTGRES_URL env var)",
    )
    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    migration = EATPMigration(database_url=args.database_url)

    if args.check:
        status = await migration.check_status()
        print("\nEATP Migration Status:")
        print(f"  Version: {status['version']}")
        print(f"  Migration: {status['migration']}")
        print(f"  Applied: {status['applied']}")
        if status.get("pending_changes"):
            print("  Pending Changes:")
            for change in status["pending_changes"]:
                print(f"    - {change}")
    else:
        result = await migration.run()
        print("\nEATP Migration Result:")
        print(f"  Version: {result['version']}")
        print(f"  Migration: {result['migration']}")
        print(f"  Started: {result['started_at']}")
        print(f"  Completed: {result['completed_at']}")
        print("  Changes:")
        for change in result["changes"]:
            print(f"    - {change}")


if __name__ == "__main__":
    asyncio.run(main())
