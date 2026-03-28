"""Unit tests for the WorkflowScheduler module.

Tests schedule creation, cancellation, listing, and graceful degradation
when APScheduler is not installed.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


class TestScheduleInfoDataclass:
    """Tests for the ScheduleInfo dataclass."""

    def test_schedule_info_defaults(self):
        """ScheduleInfo should have sensible defaults."""
        from kailash.runtime.scheduler import ScheduleInfo, ScheduleType

        info = ScheduleInfo(
            schedule_id="sched-abc123",
            schedule_type=ScheduleType.CRON,
        )

        assert info.schedule_id == "sched-abc123"
        assert info.schedule_type == ScheduleType.CRON
        assert info.workflow_name == ""
        assert info.trigger_args == {}
        assert info.next_run_time is None
        assert info.enabled is True
        assert info.kwargs == {}

    def test_schedule_info_with_all_fields(self):
        """ScheduleInfo should accept all optional fields."""
        from kailash.runtime.scheduler import ScheduleInfo, ScheduleType

        now = datetime.now(UTC)
        info = ScheduleInfo(
            schedule_id="sched-xyz789",
            schedule_type=ScheduleType.INTERVAL,
            workflow_name="etl_pipeline",
            trigger_args={"seconds": 300},
            created_at=now,
            next_run_time=now + timedelta(seconds=300),
            enabled=True,
            kwargs={"timeout": 60},
        )

        assert info.schedule_id == "sched-xyz789"
        assert info.workflow_name == "etl_pipeline"
        assert info.trigger_args == {"seconds": 300}
        assert info.kwargs == {"timeout": 60}


class TestScheduleType:
    """Tests for the ScheduleType enum."""

    def test_schedule_types_exist(self):
        """All three schedule types should be defined."""
        from kailash.runtime.scheduler import ScheduleType

        assert ScheduleType.CRON == "cron"
        assert ScheduleType.INTERVAL == "interval"
        assert ScheduleType.ONCE == "once"

    def test_schedule_type_is_string_backed(self):
        """ScheduleType should be usable as a string."""
        from kailash.runtime.scheduler import ScheduleType

        assert isinstance(ScheduleType.CRON, str)
        assert ScheduleType.CRON.value == "cron"
        assert str(ScheduleType.CRON) in ("cron", "ScheduleType.CRON")


class TestGracefulDegradation:
    """Tests for graceful degradation when APScheduler is missing."""

    def test_import_without_apscheduler_succeeds(self):
        """Module import should succeed even without APScheduler."""
        # The module itself should always be importable
        import kailash.runtime.scheduler as mod

        assert hasattr(mod, "WorkflowScheduler")
        assert hasattr(mod, "ScheduleInfo")
        assert hasattr(mod, "ScheduleType")

    def test_instantiation_without_apscheduler_raises_import_error(self):
        """Instantiating WorkflowScheduler should raise ImportError with helpful message."""
        from kailash.runtime.scheduler import WorkflowScheduler, _check_apscheduler

        with patch("kailash.runtime.scheduler._apscheduler_available", None):
            with patch.dict("sys.modules", {"apscheduler": None}):
                with patch(
                    "kailash.runtime.scheduler._check_apscheduler", return_value=False
                ):
                    with pytest.raises(ImportError, match="pip install"):
                        WorkflowScheduler()


class TestWorkflowSchedulerInit:
    """Tests for WorkflowScheduler initialization."""

    @patch("kailash.runtime.scheduler._check_apscheduler", return_value=True)
    @patch("kailash.runtime.scheduler.AsyncIOScheduler", create=True)
    def test_init_with_defaults(self, mock_scheduler_cls, mock_check):
        """WorkflowScheduler should initialize with default settings."""
        with patch("kailash.runtime.scheduler.SQLAlchemyJobStore", create=True):
            from kailash.runtime.scheduler import WorkflowScheduler

            # We need to mock the imports inside __init__
            mock_jobstore = MagicMock()
            mock_scheduler_instance = MagicMock()

            with patch.dict(
                "sys.modules",
                {
                    "apscheduler": MagicMock(),
                    "apscheduler.schedulers.asyncio": MagicMock(
                        AsyncIOScheduler=MagicMock(return_value=mock_scheduler_instance)
                    ),
                    "apscheduler.jobstores.sqlalchemy": MagicMock(
                        SQLAlchemyJobStore=MagicMock(return_value=mock_jobstore)
                    ),
                },
            ):
                scheduler = WorkflowScheduler()
                assert scheduler._schedules == {}
                assert scheduler._timezone == "UTC"

    @patch("kailash.runtime.scheduler._check_apscheduler", return_value=True)
    def test_init_with_memory_store(self, mock_check):
        """WorkflowScheduler should work with in-memory storage."""
        mock_scheduler_instance = MagicMock()

        with patch.dict(
            "sys.modules",
            {
                "apscheduler": MagicMock(),
                "apscheduler.schedulers.asyncio": MagicMock(
                    AsyncIOScheduler=MagicMock(return_value=mock_scheduler_instance)
                ),
                "apscheduler.jobstores.sqlalchemy": MagicMock(),
            },
        ):
            from kailash.runtime.scheduler import WorkflowScheduler

            scheduler = WorkflowScheduler(job_store_path=None)
            assert scheduler._schedules == {}


class TestWorkflowSchedulerOperations:
    """Tests for schedule creation, cancellation, and listing."""

    def _make_scheduler(self):
        """Create a WorkflowScheduler with mocked APScheduler internals."""
        from kailash.runtime.scheduler import WorkflowScheduler

        mock_scheduler = MagicMock()
        mock_scheduler.running = False

        with patch("kailash.runtime.scheduler._check_apscheduler", return_value=True):
            with patch.dict(
                "sys.modules",
                {
                    "apscheduler": MagicMock(),
                    "apscheduler.schedulers.asyncio": MagicMock(
                        AsyncIOScheduler=MagicMock(return_value=mock_scheduler)
                    ),
                    "apscheduler.jobstores.sqlalchemy": MagicMock(),
                },
            ):
                scheduler = WorkflowScheduler(job_store_path=None)

        return scheduler, mock_scheduler

    def test_schedule_cron_creates_schedule(self):
        """schedule_cron should create a schedule entry and add a job."""
        scheduler, mock_apscheduler = self._make_scheduler()
        mock_builder = MagicMock()

        with patch.dict(
            "sys.modules",
            {
                "apscheduler.triggers.cron": MagicMock(),
            },
        ):
            schedule_id = scheduler.schedule_cron(
                mock_builder, "0 */6 * * *", name="every_6h"
            )

        assert schedule_id.startswith("sched-")
        assert schedule_id in scheduler._schedules
        info = scheduler._schedules[schedule_id]
        assert info.workflow_name == "every_6h"
        assert info.trigger_args == {"cron_expression": "0 */6 * * *"}
        mock_apscheduler.add_job.assert_called_once()

    def test_schedule_cron_invalid_expression_raises(self):
        """schedule_cron should reject invalid cron expressions."""
        scheduler, _ = self._make_scheduler()
        mock_builder = MagicMock()

        with pytest.raises(ValueError, match="5 fields"):
            scheduler.schedule_cron(mock_builder, "invalid cron")

        with pytest.raises(ValueError, match="5 fields"):
            scheduler.schedule_cron(mock_builder, "* * *")

    def test_schedule_interval_creates_schedule(self):
        """schedule_interval should create a schedule with interval trigger."""
        scheduler, mock_apscheduler = self._make_scheduler()
        mock_builder = MagicMock()

        schedule_id = scheduler.schedule_interval(
            mock_builder, seconds=300, name="every_5_min"
        )

        assert schedule_id.startswith("sched-")
        assert schedule_id in scheduler._schedules
        info = scheduler._schedules[schedule_id]
        assert info.trigger_args == {"seconds": 300}
        mock_apscheduler.add_job.assert_called_once()

    def test_schedule_interval_rejects_non_positive(self):
        """schedule_interval should reject zero and negative intervals."""
        scheduler, _ = self._make_scheduler()
        mock_builder = MagicMock()

        with pytest.raises(ValueError, match="positive"):
            scheduler.schedule_interval(mock_builder, seconds=0)

        with pytest.raises(ValueError, match="positive"):
            scheduler.schedule_interval(mock_builder, seconds=-10)

    def test_schedule_once_creates_schedule(self):
        """schedule_once should create a one-shot schedule."""
        scheduler, mock_apscheduler = self._make_scheduler()
        mock_builder = MagicMock()
        run_at = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)

        schedule_id = scheduler.schedule_once(
            mock_builder, run_at=run_at, name="one_shot"
        )

        assert schedule_id.startswith("sched-")
        info = scheduler._schedules[schedule_id]
        assert info.next_run_time == run_at
        assert info.workflow_name == "one_shot"
        mock_apscheduler.add_job.assert_called_once()

    def test_cancel_removes_schedule(self):
        """cancel should remove the schedule from both internal tracking and APScheduler."""
        scheduler, mock_apscheduler = self._make_scheduler()
        mock_builder = MagicMock()

        schedule_id = scheduler.schedule_interval(mock_builder, seconds=60)
        assert schedule_id in scheduler._schedules

        scheduler.cancel(schedule_id)

        assert schedule_id not in scheduler._schedules
        mock_apscheduler.remove_job.assert_called_once_with(schedule_id)

    def test_cancel_nonexistent_raises_key_error(self):
        """cancel should raise KeyError for unknown schedule IDs."""
        scheduler, _ = self._make_scheduler()

        with pytest.raises(KeyError, match="not found"):
            scheduler.cancel("nonexistent-id")

    def test_list_schedules_returns_all(self):
        """list_schedules should return all registered schedules."""
        scheduler, mock_apscheduler = self._make_scheduler()
        mock_builder = MagicMock()

        # Mock get_job to return a job with next_run_time
        mock_job = MagicMock()
        mock_job.next_run_time = datetime.now(UTC)
        mock_apscheduler.get_job.return_value = mock_job

        id1 = scheduler.schedule_interval(mock_builder, seconds=60)
        id2 = scheduler.schedule_interval(mock_builder, seconds=120)

        schedules = scheduler.list_schedules()

        assert len(schedules) == 2
        schedule_ids = {s.schedule_id for s in schedules}
        assert id1 in schedule_ids
        assert id2 in schedule_ids

    def test_list_schedules_empty(self):
        """list_schedules should return empty list when no schedules exist."""
        scheduler, _ = self._make_scheduler()
        assert scheduler.list_schedules() == []

    def test_start_and_shutdown(self):
        """start and shutdown should delegate to APScheduler."""
        scheduler, mock_apscheduler = self._make_scheduler()
        mock_apscheduler.running = False

        scheduler.start()
        mock_apscheduler.start.assert_called_once()

        mock_apscheduler.running = True
        scheduler.shutdown(wait=True)
        mock_apscheduler.shutdown.assert_called_once_with(wait=True)

    def test_start_idempotent_when_running(self):
        """start should be idempotent when scheduler is already running."""
        scheduler, mock_apscheduler = self._make_scheduler()
        mock_apscheduler.running = True

        scheduler.start()
        mock_apscheduler.start.assert_not_called()

    def test_shutdown_idempotent_when_not_running(self):
        """shutdown should be idempotent when scheduler is not running."""
        scheduler, mock_apscheduler = self._make_scheduler()
        mock_apscheduler.running = False

        scheduler.shutdown()
        mock_apscheduler.shutdown.assert_not_called()

    def test_generate_schedule_id_unique(self):
        """Generated schedule IDs should be unique."""
        from kailash.runtime.scheduler import WorkflowScheduler

        ids = {WorkflowScheduler._generate_schedule_id() for _ in range(100)}
        assert len(ids) == 100

    def test_generate_schedule_id_format(self):
        """Schedule IDs should have the sched- prefix."""
        from kailash.runtime.scheduler import WorkflowScheduler

        sid = WorkflowScheduler._generate_schedule_id()
        assert sid.startswith("sched-")
        assert len(sid) == 18  # "sched-" + 12 hex chars

    def test_schedule_cron_passes_kwargs(self):
        """Extra kwargs should be stored in ScheduleInfo."""
        scheduler, mock_apscheduler = self._make_scheduler()
        mock_builder = MagicMock()

        with patch.dict(
            "sys.modules",
            {
                "apscheduler.triggers.cron": MagicMock(),
            },
        ):
            schedule_id = scheduler.schedule_cron(
                mock_builder, "0 0 * * *", timeout=120
            )

        info = scheduler._schedules[schedule_id]
        assert info.kwargs == {"timeout": 120}
