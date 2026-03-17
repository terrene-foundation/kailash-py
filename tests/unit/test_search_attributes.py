"""Tests for workflow search attributes (Feature 1).

Validates typed key-value storage on workflow runs and parameterized
search queries across the SQLiteStorage backend.
"""

import tempfile
from datetime import UTC, datetime

import pytest

from kailash.tracking.manager import TaskManager
from kailash.tracking.storage.database import SQLiteStorage


@pytest.fixture()
def storage(tmp_path):
    """Create a fresh SQLiteStorage instance per test."""
    db_path = str(tmp_path / "test_sa.db")
    s = SQLiteStorage(db_path)
    yield s
    s.close()


@pytest.fixture()
def task_manager(storage):
    """Create a TaskManager backed by the test storage."""
    return TaskManager(storage_backend=storage)


# -- Storage-level tests --------------------------------------------------


class TestUpsertAndQueryTextAttribute:
    def test_upsert_and_query_text_attribute(self, storage, task_manager):
        """Text attributes are stored and retrievable via search_runs."""
        run_id = task_manager.create_run("wf-text")
        storage.upsert_search_attributes(run_id, {"environment": "staging"})

        results = storage.search_runs({"environment": "staging"})
        assert len(results) == 1
        assert results[0]["run_id"] == run_id

    def test_text_attribute_no_match(self, storage, task_manager):
        """Non-matching text value returns no results."""
        run_id = task_manager.create_run("wf-text-2")
        storage.upsert_search_attributes(run_id, {"environment": "production"})

        results = storage.search_runs({"environment": "staging"})
        assert len(results) == 0


class TestUpsertAndQueryIntAttribute:
    def test_upsert_and_query_int_attribute(self, storage, task_manager):
        """Integer attributes are stored in int_value column and queryable."""
        run_id = task_manager.create_run("wf-int")
        storage.upsert_search_attributes(run_id, {"priority": 5})

        results = storage.search_runs({"priority": 5})
        assert len(results) == 1
        assert results[0]["run_id"] == run_id

    def test_int_attribute_no_match(self, storage, task_manager):
        """Non-matching int returns no results."""
        run_id = task_manager.create_run("wf-int-2")
        storage.upsert_search_attributes(run_id, {"priority": 5})

        results = storage.search_runs({"priority": 10})
        assert len(results) == 0


class TestSearchByMultipleAttributes:
    def test_search_by_multiple_attributes(self, storage, task_manager):
        """All filter attributes must match (AND semantics)."""
        run1 = task_manager.create_run("wf-multi-1")
        storage.upsert_search_attributes(run1, {"team": "platform", "priority": 1})

        run2 = task_manager.create_run("wf-multi-2")
        storage.upsert_search_attributes(run2, {"team": "platform", "priority": 2})

        run3 = task_manager.create_run("wf-multi-3")
        storage.upsert_search_attributes(run3, {"team": "data", "priority": 1})

        # Both attributes must match
        results = storage.search_runs({"team": "platform", "priority": 1})
        assert len(results) == 1
        assert results[0]["run_id"] == run1

        # Only team filter
        results = storage.search_runs({"team": "platform"})
        assert len(results) == 2
        run_ids = {r["run_id"] for r in results}
        assert run1 in run_ids
        assert run2 in run_ids


class TestSearchWithOrderingAndPagination:
    def test_search_with_ordering_and_pagination(self, storage, task_manager):
        """Pagination via limit and offset works correctly."""
        run_ids = []
        for i in range(5):
            rid = task_manager.create_run(f"wf-page-{i}")
            storage.upsert_search_attributes(rid, {"batch": "alpha"})
            run_ids.append(rid)

        # First page
        page1 = storage.search_runs({"batch": "alpha"}, limit=2, offset=0)
        assert len(page1) == 2

        # Second page
        page2 = storage.search_runs({"batch": "alpha"}, limit=2, offset=2)
        assert len(page2) == 2

        # Third page (remainder)
        page3 = storage.search_runs({"batch": "alpha"}, limit=2, offset=4)
        assert len(page3) == 1

        # All unique
        all_ids = {r["run_id"] for r in page1 + page2 + page3}
        assert len(all_ids) == 5

    def test_ordering_by_workflow_name(self, storage, task_manager):
        """Order by workflow_name ASC works."""
        for name in ["charlie", "alpha", "bravo"]:
            rid = task_manager.create_run(name)
            storage.upsert_search_attributes(rid, {"group": "test_order"})

        results = storage.search_runs(
            {"group": "test_order"}, order_by="workflow_name ASC"
        )
        names = [r["workflow_name"] for r in results]
        assert names == sorted(names)

    def test_invalid_order_by_column_raises(self, storage):
        """Invalid order_by column raises ValueError."""
        with pytest.raises(ValueError, match="Invalid order_by column"):
            storage.search_runs({}, order_by="DROP TABLE workflow_runs")


class TestSchemaMigrationV1ToV2:
    def test_schema_migration_v1_to_v2(self, tmp_path):
        """A v1 database is migrated to v2 on open."""
        db_path = str(tmp_path / "migrate.db")

        # Create a v1-only database manually
        import sqlite3

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Create v1 schema tables
        cursor.execute(
            """
            CREATE TABLE schema_version (
                version INTEGER PRIMARY KEY,
                upgraded_at TEXT NOT NULL
            )
        """
        )
        cursor.execute(
            "INSERT INTO schema_version (version, upgraded_at) VALUES (1, ?)",
            (datetime.now(UTC).isoformat(),),
        )

        # Minimal workflow_runs for foreign key
        cursor.execute(
            """
            CREATE TABLE workflow_runs (
                run_id TEXT PRIMARY KEY,
                workflow_name TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                metadata TEXT,
                error TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        cursor.execute(
            """
            CREATE TABLE tasks (
                task_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                node_type TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT,
                ended_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                result TEXT,
                error TEXT,
                metadata TEXT,
                input_data TEXT,
                output_data TEXT,
                metrics_duration REAL,
                metrics_cpu_usage REAL,
                metrics_memory_usage_mb REAL,
                metrics_custom TEXT,
                FOREIGN KEY (run_id) REFERENCES workflow_runs(run_id) ON DELETE CASCADE
            )
        """
        )
        cursor.execute(
            """
            CREATE TABLE audit_events (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                trace_id TEXT NOT NULL,
                result TEXT NOT NULL,
                workflow_id TEXT,
                node_id TEXT,
                agent_id TEXT,
                human_origin_id TEXT,
                action TEXT,
                resource TEXT,
                context TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        conn.commit()
        conn.close()

        # Now open with SQLiteStorage -- should auto-migrate to v2
        storage = SQLiteStorage(db_path)

        # Verify v2 table exists
        cursor = storage.conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='workflow_search_attributes'"
        )
        assert cursor.fetchone() is not None

        # Verify version is now 2
        cursor.execute(
            "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
        )
        assert cursor.fetchone()[0] == 2

        storage.close()


class TestSearchNoResults:
    def test_search_no_results(self, storage, task_manager):
        """Searching with no matching attributes returns empty list."""
        task_manager.create_run("wf-empty")
        results = storage.search_runs({"nonexistent_attr": "value"})
        assert results == []

    def test_search_empty_filters(self, storage, task_manager):
        """Empty filters return all runs."""
        task_manager.create_run("wf-all-1")
        task_manager.create_run("wf-all-2")

        results = storage.search_runs({})
        assert len(results) == 2


# -- Attribute name validation tests -----------------------------------------


class TestAttributeNameValidation:
    def test_invalid_attr_name_rejected(self, storage, task_manager):
        """Attribute names with path traversal or special chars are rejected."""
        run_id = task_manager.create_run("wf-validate")

        with pytest.raises(ValueError, match="Invalid attribute name"):
            storage.upsert_search_attributes(run_id, {"../traversal": "bad"})

        with pytest.raises(ValueError, match="Invalid attribute name"):
            storage.upsert_search_attributes(run_id, {"has space": "bad"})

    def test_invalid_filter_name_rejected(self, storage):
        """Filter names with special chars are rejected."""
        with pytest.raises(ValueError, match="Invalid filter attribute name"):
            storage.search_runs({"1starts_with_digit": "ok"})


# -- TaskManager-level tests -------------------------------------------------


class TestTaskManagerSearchAttributes:
    def test_set_search_attributes_via_manager(self, task_manager, storage):
        """TaskManager.set_search_attributes delegates to storage."""
        run_id = task_manager.create_run("wf-mgr")
        task_manager.set_search_attributes(run_id, {"owner": "alice", "version": 3})

        results = task_manager.search_runs({"owner": "alice"})
        assert len(results) == 1
        assert results[0]["run_id"] == run_id

    def test_search_runs_via_manager(self, task_manager, storage):
        """TaskManager.search_runs returns matching runs."""
        r1 = task_manager.create_run("wf-mgr-search-1")
        task_manager.set_search_attributes(r1, {"region": "us-east"})

        r2 = task_manager.create_run("wf-mgr-search-2")
        task_manager.set_search_attributes(r2, {"region": "eu-west"})

        results = task_manager.search_runs({"region": "us-east"})
        assert len(results) == 1
        assert results[0]["run_id"] == r1


# -- Type detection tests ----------------------------------------------------


class TestTypeDetection:
    def test_bool_attribute(self, storage, task_manager):
        """Boolean values are stored as int_value (1/0)."""
        run_id = task_manager.create_run("wf-bool")
        storage.upsert_search_attributes(run_id, {"is_test": True})

        results = storage.search_runs({"is_test": True})
        assert len(results) == 1

    def test_float_attribute(self, storage, task_manager):
        """Float values are stored in float_value column."""
        run_id = task_manager.create_run("wf-float")
        storage.upsert_search_attributes(run_id, {"score": 0.95})

        results = storage.search_runs({"score": 0.95})
        assert len(results) == 1

    def test_datetime_attribute(self, storage, task_manager):
        """Datetime values are stored as ISO strings in dt_value."""
        run_id = task_manager.create_run("wf-dt")
        dt = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)
        storage.upsert_search_attributes(run_id, {"scheduled_at": dt})

        results = storage.search_runs({"scheduled_at": dt})
        assert len(results) == 1

    def test_upsert_overwrites_existing(self, storage, task_manager):
        """Upserting the same attribute name replaces the old value."""
        run_id = task_manager.create_run("wf-upsert")
        storage.upsert_search_attributes(run_id, {"status_tag": "draft"})

        results = storage.search_runs({"status_tag": "draft"})
        assert len(results) == 1

        # Overwrite
        storage.upsert_search_attributes(run_id, {"status_tag": "published"})

        results_old = storage.search_runs({"status_tag": "draft"})
        assert len(results_old) == 0

        results_new = storage.search_runs({"status_tag": "published"})
        assert len(results_new) == 1
