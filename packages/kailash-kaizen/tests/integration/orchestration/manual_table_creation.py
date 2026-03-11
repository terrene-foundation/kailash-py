"""
Manual table creation for OrchestrationStateManager integration tests.

WORKAROUND for DataFlow async deadlock bug (DataFlow v0.9.1):
- ConnectionManagerAdapter uses LocalRuntime() instead of AsyncLocalRuntime()
- Causes deadlock when migration lock system runs in async context
- Solution: Manually create tables via raw SQL, then disable DataFlow migrations

This workaround should be REMOVED once DataFlow v0.9.2+ fixes the bug.

Bug Report: https://github.com/kailash-dataflow/issues/XXX
Investigation: See DATAFLOW_ASYNC_DEADLOCK_INVESTIGATION.md
"""

import logging
import os
import tempfile
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def create_postgres_tables(db_url: str) -> None:
    """
    Create OrchestrationStateManager tables in PostgreSQL via raw SQL.

    Args:
        db_url: PostgreSQL connection URL (postgresql://user:pass@host:port/db)

    Raises:
        ImportError: If psycopg2 not installed
        Exception: If table creation fails
    """
    try:
        import psycopg2
    except ImportError:
        raise ImportError(
            "psycopg2 required for PostgreSQL table creation. "
            "Run: pip install psycopg2-binary"
        )

    parsed = urlparse(db_url)
    conn = psycopg2.connect(
        host=parsed.hostname,
        port=parsed.port or 5432,
        database=parsed.path.lstrip("/"),
        user=parsed.username,
        password=parsed.password,
    )
    conn.autocommit = True
    cursor = conn.cursor()

    try:
        # Table 1: WorkflowStateModel (workflow execution state)
        # DataFlow naming: WorkflowState class → workflow_state_models table
        logger.info("Creating workflow_state_models table...")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS workflow_state_models (
                id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                status TEXT NOT NULL,
                start_time TIMESTAMP NOT NULL,
                end_time TIMESTAMP,
                runtime_id TEXT NOT NULL,
                routing_strategy TEXT NOT NULL,
                max_concurrent INTEGER DEFAULT 10,
                total_tasks INTEGER DEFAULT 0,
                completed_tasks INTEGER DEFAULT 0,
                failed_tasks INTEGER DEFAULT 0,
                success_rate REAL DEFAULT 0.0,
                error_message TEXT,
                error_type TEXT,
                metadata JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Table 2: AgentExecutionRecordModel (agent task execution records)
        # DataFlow naming: AgentExecutionRecord class → agent_execution_record_models table
        logger.info("Creating agent_execution_record_models table...")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_execution_record_models (
                id TEXT PRIMARY KEY,
                workflow_state_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                agent_type TEXT NOT NULL,
                task_description TEXT NOT NULL,
                task_index INTEGER NOT NULL,
                status TEXT NOT NULL,
                retry_count INTEGER DEFAULT 0,
                max_retries INTEGER DEFAULT 3,
                start_time TIMESTAMP NOT NULL,
                end_time TIMESTAMP,
                execution_time_seconds REAL DEFAULT 0.0,
                result JSONB,
                error TEXT,
                error_stack_trace TEXT,
                cost_usd REAL DEFAULT 0.0,
                budget_remaining_usd REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Table 3: WorkflowCheckpointModel (incremental checkpoints)
        # DataFlow naming: WorkflowCheckpoint class → workflow_checkpoint_models table
        logger.info("Creating workflow_checkpoint_models table...")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS workflow_checkpoint_models (
                id TEXT PRIMARY KEY,
                workflow_state_id TEXT NOT NULL,
                checkpoint_number INTEGER NOT NULL,
                checkpoint_type TEXT NOT NULL,
                snapshot_data JSONB,
                created_at_timestamp TIMESTAMP NOT NULL,
                size_bytes INTEGER DEFAULT 0,
                compression_ratio REAL DEFAULT 1.0,
                parent_checkpoint_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        logger.info(
            "✅ PostgreSQL tables created successfully (workflow_state_models, "
            "agent_execution_record_models, workflow_checkpoint_models)"
        )

    except Exception as e:
        logger.error(f"Failed to create PostgreSQL tables: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


def create_sqlite_tables(db_url: str) -> None:
    """
    Create OrchestrationStateManager tables in SQLite via raw SQL.

    Args:
        db_url: SQLite connection URL (sqlite:///path/to/db.sqlite)

    Raises:
        Exception: If table creation fails
    """
    import sqlite3

    # Extract file path from URL
    db_path = db_url.replace("sqlite:///", "")

    # Ensure directory exists
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Table 1: WorkflowStateModel (workflow execution state)
        # DataFlow naming: WorkflowState class → workflow_state_models table
        logger.info("Creating workflow_state_models table (SQLite)...")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS workflow_state_models (
                id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                status TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT,
                runtime_id TEXT NOT NULL,
                routing_strategy TEXT NOT NULL,
                max_concurrent INTEGER DEFAULT 10,
                total_tasks INTEGER DEFAULT 0,
                completed_tasks INTEGER DEFAULT 0,
                failed_tasks INTEGER DEFAULT 0,
                success_rate REAL DEFAULT 0.0,
                error_message TEXT,
                error_type TEXT,
                metadata TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Table 2: AgentExecutionRecordModel (agent task execution records)
        # DataFlow naming: AgentExecutionRecord class → agent_execution_record_models table
        logger.info("Creating agent_execution_record_models table (SQLite)...")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_execution_record_models (
                id TEXT PRIMARY KEY,
                workflow_state_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                agent_type TEXT NOT NULL,
                task_description TEXT NOT NULL,
                task_index INTEGER NOT NULL,
                status TEXT NOT NULL,
                retry_count INTEGER DEFAULT 0,
                max_retries INTEGER DEFAULT 3,
                start_time TEXT NOT NULL,
                end_time TEXT,
                execution_time_seconds REAL DEFAULT 0.0,
                result TEXT,
                error TEXT,
                error_stack_trace TEXT,
                cost_usd REAL DEFAULT 0.0,
                budget_remaining_usd REAL DEFAULT 0.0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Table 3: WorkflowCheckpointModel (incremental checkpoints)
        # DataFlow naming: WorkflowCheckpoint class → workflow_checkpoint_models table
        logger.info("Creating workflow_checkpoint_models table (SQLite)...")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS workflow_checkpoint_models (
                id TEXT PRIMARY KEY,
                workflow_state_id TEXT NOT NULL,
                checkpoint_number INTEGER NOT NULL,
                checkpoint_type TEXT NOT NULL,
                snapshot_data TEXT,
                created_at_timestamp TEXT NOT NULL,
                size_bytes INTEGER DEFAULT 0,
                compression_ratio REAL DEFAULT 1.0,
                parent_checkpoint_id TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        conn.commit()
        logger.info(
            "✅ SQLite tables created successfully (workflow_state_models, "
            "agent_execution_record_models, workflow_checkpoint_models)"
        )

    except Exception as e:
        logger.error(f"Failed to create SQLite tables: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


def initialize_orchestration_tables(db_url: str) -> None:
    """
    Initialize OrchestrationStateManager tables based on database type.

    Detects database type from URL and creates appropriate tables.

    Args:
        db_url: Database connection URL (postgresql:// or sqlite://)

    Raises:
        ValueError: If database type is unsupported
        Exception: If table creation fails
    """
    if "postgresql" in db_url:
        logger.info(f"Detected PostgreSQL database: {db_url}")
        create_postgres_tables(db_url)
    elif "sqlite" in db_url:
        logger.info(f"Detected SQLite database: {db_url}")
        create_sqlite_tables(db_url)
    else:
        raise ValueError(
            f"Unsupported database type in URL: {db_url}. "
            "Only PostgreSQL and SQLite are supported."
        )


# Cleanup function for test teardown
def cleanup_tables(db_url: str) -> None:
    """
    Drop OrchestrationStateManager tables for test cleanup.

    Args:
        db_url: Database connection URL

    Note:
        Use with caution - this deletes all data in tables!
    """
    if "postgresql" in db_url:
        import psycopg2

        parsed = urlparse(db_url)
        conn = psycopg2.connect(
            host=parsed.hostname,
            port=parsed.port or 5432,
            database=parsed.path.lstrip("/"),
            user=parsed.username,
            password=parsed.password,
        )
        conn.autocommit = True
        cursor = conn.cursor()

        try:
            cursor.execute("DROP TABLE IF EXISTS workflow_checkpoint_models CASCADE")
            cursor.execute("DROP TABLE IF EXISTS agent_execution_record_models CASCADE")
            cursor.execute("DROP TABLE IF EXISTS workflow_state_models CASCADE")
            logger.info("✅ PostgreSQL tables dropped successfully")
        finally:
            cursor.close()
            conn.close()

    elif "sqlite" in db_url:
        db_path = db_url.replace("sqlite:///", "")
        if os.path.exists(db_path):
            os.remove(db_path)
            logger.info(f"✅ SQLite database deleted: {db_path}")
