"""Deferred (batched) storage backend for high-performance workflow execution.

P0D-007: The default FileSystemStorage writes to disk on every save_task() and save_run()
call, causing 5 disk writes per node (create_task, update_status(RUNNING),
update_status(COMPLETED), update_metrics, save_run). This adds ~130ms/node overhead.

DeferredStorageBackend is a pure in-memory storage backend during execution.
All writes are kept in memory with zero I/O. An optional flush() persists
the final state to a real backend (FileSystemStorage) after execution completes.

This reduces hot-path I/O from O(5*N) disk writes to O(0) during execution,
with an optional O(N) batch write after execution if persistence is desired.

Usage:
    from kailash.tracking.storage.deferred import DeferredStorageBackend

    # Pure in-memory during execution (no I/O)
    storage = DeferredStorageBackend()
    task_manager = TaskManager(storage_backend=storage)

    # ... execute workflow (all writes stay in memory) ...

    # Optional: persist to disk after execution
    storage.flush_to_filesystem()
"""

from __future__ import annotations

import logging

from ..models import TaskRun, TaskStatus, WorkflowRun
from .base import StorageBackend

logger = logging.getLogger(__name__)


class DeferredStorageBackend(StorageBackend):
    """Pure in-memory storage backend with optional deferred persistence.

    During workflow execution, all data stays in memory (zero I/O).
    After execution completes, flush_to_filesystem() can optionally
    persist the final state to disk.
    """

    def __init__(self) -> None:
        self._runs: dict[str, WorkflowRun] = {}
        self._tasks: dict[str, TaskRun] = {}
        self._audit_events: list = []  # For RuntimeAuditGenerator events

    # --- Write operations (in-memory only) ---

    def save_run(self, run: WorkflowRun) -> None:
        """Store run in memory."""
        self._runs[run.run_id] = run

    def save_task(self, task: TaskRun) -> None:
        """Store task in memory."""
        self._tasks[task.task_id] = task

    # --- Read operations (from memory) ---

    def load_run(self, run_id: str) -> WorkflowRun | None:
        """Load run from memory."""
        return self._runs.get(run_id)

    def load_task(self, task_id: str) -> TaskRun | None:
        """Load task from memory."""
        return self._tasks.get(task_id)

    def list_runs(
        self, workflow_name: str | None = None, status: str | None = None
    ) -> list[WorkflowRun]:
        """List runs from memory with optional filters."""
        result = []
        for run in self._runs.values():
            if workflow_name and run.workflow_name != workflow_name:
                continue
            if status and run.status != status:
                continue
            result.append(run)
        return result

    def list_tasks(
        self,
        run_id: str,
        node_id: str | None = None,
        status: TaskStatus | None = None,
    ) -> list[TaskRun]:
        """List tasks from memory with optional filters."""
        result = []
        for task in self._tasks.values():
            if task.run_id != run_id:
                continue
            if node_id and task.node_id != node_id:
                continue
            if status and task.status != status:
                continue
            result.append(task)
        return result

    # --- Audit event accumulation (P0E-002) ---

    def add_audit_events(self, events: list) -> None:
        """Accumulate audit events for inclusion in the next flush.

        Called by LocalRuntime._flush_deferred_storage_sqlite() before flush
        to pass RuntimeAuditGenerator events into the CARE audit record.
        Both task tracking data and EATP audit events are then written
        atomically to SQLite in a single transaction.

        Args:
            events: Serialized audit event dicts (from AuditEvent.to_dict()).
        """
        self._audit_events.extend(events)

    # --- Optional persistence ---

    def flush(self) -> None:
        """No-op during execution. Data stays in memory.

        For actual persistence, call flush_to_sqlite() or flush_to_filesystem() explicitly.
        This method exists to satisfy callers that expect a flush interface.
        """

    def flush_to_sqlite(self, db_path: str | None = None) -> None:
        """Persist all in-memory data to SQLite (CARE audit record).

        This is the primary flush target for P0E (SQLite storage optimization).
        Uses batch insert via executemany() for performance and single transaction
        for ACID compliance.

        Args:
            db_path: Override database path. Defaults to ~/.kailash/tracking/tracking.db
        """
        if not self._runs and not self._tasks and not self._audit_events:
            return

        from .database import SQLiteStorage

        storage = SQLiteStorage(db_path)
        try:
            # Save all runs first (for FK constraints)
            for run in self._runs.values():
                storage.save_run(run)

            # Batch insert all tasks in single transaction
            if self._tasks:
                storage.save_tasks_batch(list(self._tasks.values()))

            # Persist audit events if any
            if self._audit_events:
                storage.save_audit_events(self._audit_events)

        finally:
            storage.close()

        # Clear buffers after successful flush
        self._runs.clear()
        self._tasks.clear()
        self._audit_events.clear()

    def flush_to_filesystem(self, base_path: str | None = None) -> None:
        """Persist all in-memory data to filesystem (optional, post-execution).

        This performs a single batch write of all accumulated tracking data.
        Only the final state of each task/run is written (not intermediate updates).

        P0D-007b: Writes a SINGLE batch JSON file per run to `batch/{run_id}.json`.
        This avoids the bloated tasks/ directory (1M+ entries from historical runs)
        where even mkdir(exist_ok=True) takes ~8ms due to directory entry scanning.

        The batch file contains the complete CARE audit record:
        - Run metadata (workflow name, status, timestamps)
        - All task data (per-node status, timestamps, metrics)
        - Compact JSON for minimal I/O

        Total flush cost: ~0.5ms for 20 nodes (1 mkdir + 1 file write).

        Args:
            base_path: Override path for FileSystemStorage. Defaults to ~/.kailash/tracking.
        """
        if not self._runs and not self._tasks:
            return

        import json
        import os
        from pathlib import Path

        if base_path is None:
            base_path = os.path.expanduser("~/.kailash/tracking")

        batch_dir = Path(base_path) / "batch"
        batch_dir.mkdir(parents=True, exist_ok=True)

        errors: list[str] = []

        # Group tasks by run_id
        tasks_by_run: dict[str, list[dict]] = {}
        for task in self._tasks.values():
            rid = task.run_id or "unknown"
            if rid not in tasks_by_run:
                tasks_by_run[rid] = []
            task_dict = task.to_dict()
            # Include metrics inline if present
            if hasattr(task, "metrics") and task.metrics:
                task_dict["metrics"] = task.metrics.model_dump()
            tasks_by_run[rid].append(task_dict)

        # Write one batch file per run (CARE audit: complete execution record)
        for run_id, run in self._runs.items():
            try:
                batch_data = {
                    "run": run.to_dict(),
                    "tasks": tasks_by_run.get(run_id, []),
                }
                batch_path = batch_dir / f"{run_id}.json"
                with open(batch_path, "w") as f:
                    json.dump(batch_data, f, separators=(",", ":"))
            except Exception as e:
                errors.append(f"run {run_id}: {e}")

        # Write orphan tasks (tasks without a matching run)
        orphan_tasks = []
        run_ids = set(self._runs.keys())
        for task in self._tasks.values():
            if (task.run_id or "unknown") not in run_ids:
                task_dict = task.to_dict()
                if hasattr(task, "metrics") and task.metrics:
                    task_dict["metrics"] = task.metrics.model_dump()
                orphan_tasks.append(task_dict)

        if orphan_tasks:
            try:
                orphan_path = batch_dir / "_orphan_tasks.json"
                with open(orphan_path, "w") as f:
                    json.dump(orphan_tasks, f, separators=(",", ":"))
            except Exception as e:
                errors.append(f"orphan tasks: {e}")

        if errors:
            logger.warning(
                "DeferredStorageBackend persistence completed with %d errors: %s",
                len(errors),
                "; ".join(errors[:5]),
            )

        # Clear buffers after successful flush
        self._runs.clear()
        self._tasks.clear()
        self._audit_events.clear()

    # --- Housekeeping ---

    def clear(self) -> None:
        """Clear all in-memory data."""
        self._runs.clear()
        self._tasks.clear()
        self._audit_events.clear()

    def export_run(self, run_id: str, output_path: str) -> None:
        """Export run by flushing to filesystem first."""
        self.flush_to_filesystem()
        from .filesystem import FileSystemStorage

        FileSystemStorage().export_run(run_id, output_path)

    def import_run(self, input_path: str) -> str:
        """Import run from filesystem."""
        from .filesystem import FileSystemStorage

        return FileSystemStorage().import_run(input_path)
