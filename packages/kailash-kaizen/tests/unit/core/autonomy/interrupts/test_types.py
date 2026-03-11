"""
Unit tests for interrupt types.

Tests InterruptMode, InterruptSource, InterruptReason, and InterruptStatus.
"""

from datetime import datetime, timezone

from kaizen.core.autonomy.interrupts.types import (
    InterruptMode,
    InterruptReason,
    InterruptSource,
    InterruptStatus,
)


class TestInterruptMode:
    """Test InterruptMode enum"""

    def test_all_modes_defined(self):
        """Test all 2 interrupt modes are defined"""
        modes = list(InterruptMode)
        assert len(modes) == 2

    def test_graceful_mode(self):
        """Test GRACEFUL mode"""
        assert InterruptMode.GRACEFUL.value == "graceful"

    def test_immediate_mode(self):
        """Test IMMEDIATE mode"""
        assert InterruptMode.IMMEDIATE.value == "immediate"


class TestInterruptSource:
    """Test InterruptSource enum"""

    def test_all_sources_defined(self):
        """Test all 5 interrupt sources are defined"""
        sources = list(InterruptSource)
        assert len(sources) == 5

    def test_signal_source(self):
        """Test SIGNAL source"""
        assert InterruptSource.SIGNAL.value == "signal"

    def test_timeout_source(self):
        """Test TIMEOUT source"""
        assert InterruptSource.TIMEOUT.value == "timeout"

    def test_budget_source(self):
        """Test BUDGET source"""
        assert InterruptSource.BUDGET.value == "budget"

    def test_user_source(self):
        """Test USER source"""
        assert InterruptSource.USER.value == "user"

    def test_programmatic_source(self):
        """Test PROGRAMMATIC source"""
        assert InterruptSource.PROGRAMMATIC.value == "programmatic"


class TestInterruptReason:
    """Test InterruptReason dataclass"""

    def test_create_reason(self):
        """Test creating InterruptReason"""
        timestamp = datetime(2025, 1, 22, 12, 0, 0)

        reason = InterruptReason(
            source=InterruptSource.USER,
            mode=InterruptMode.GRACEFUL,
            message="User requested stop",
            timestamp=timestamp,
        )

        assert reason.source == InterruptSource.USER
        assert reason.mode == InterruptMode.GRACEFUL
        assert reason.message == "User requested stop"
        assert reason.timestamp == timestamp
        assert reason.metadata == {}

    def test_create_reason_with_metadata(self):
        """Test creating InterruptReason with metadata"""
        reason = InterruptReason(
            source=InterruptSource.TIMEOUT,
            mode=InterruptMode.GRACEFUL,
            message="Timeout exceeded",
            metadata={"timeout_seconds": 300},
        )

        assert reason.metadata == {"timeout_seconds": 300}

    def test_reason_default_timestamp(self):
        """Test reason gets default timestamp if not provided"""
        reason = InterruptReason(
            source=InterruptSource.USER,
            mode=InterruptMode.GRACEFUL,
            message="Test",
        )

        assert isinstance(reason.timestamp, datetime)
        # Should be recent (within 1 second)
        assert (
            abs((datetime.now(timezone.utc) - reason.timestamp).total_seconds()) < 1.0
        )

    def test_reason_str_representation(self):
        """Test InterruptReason string representation"""
        timestamp = datetime(2025, 1, 22, 12, 0, 0)

        reason = InterruptReason(
            source=InterruptSource.SIGNAL,
            mode=InterruptMode.GRACEFUL,
            message="SIGINT received",
            timestamp=timestamp,
        )

        str_repr = str(reason)
        assert "Interrupt" in str_repr
        assert "signal" in str_repr
        assert "graceful" in str_repr
        assert "SIGINT received" in str_repr

    def test_all_sources_with_all_modes(self):
        """Test creating reasons with all source/mode combinations"""
        for source in InterruptSource:
            for mode in InterruptMode:
                reason = InterruptReason(
                    source=source,
                    mode=mode,
                    message=f"Test {source.value} {mode.value}",
                )
                assert reason.source == source
                assert reason.mode == mode


class TestInterruptStatus:
    """Test InterruptStatus dataclass"""

    def test_create_status_not_interrupted(self):
        """Test creating InterruptStatus when not interrupted"""
        status = InterruptStatus(interrupted=False)

        assert status.interrupted is False
        assert status.reason is None
        assert status.checkpoint_id is None

    def test_create_status_interrupted(self):
        """Test creating InterruptStatus when interrupted"""
        reason = InterruptReason(
            source=InterruptSource.USER,
            mode=InterruptMode.GRACEFUL,
            message="User stop",
        )

        status = InterruptStatus(
            interrupted=True,
            reason=reason,
            checkpoint_id="ckpt_abc123",
        )

        assert status.interrupted is True
        assert status.reason == reason
        assert status.checkpoint_id == "ckpt_abc123"

    def test_can_resume_with_checkpoint(self):
        """Test can_resume() returns True when checkpoint exists"""
        status = InterruptStatus(
            interrupted=True,
            checkpoint_id="ckpt_abc123",
        )

        assert status.can_resume() is True

    def test_can_resume_without_checkpoint(self):
        """Test can_resume() returns False when no checkpoint"""
        status = InterruptStatus(
            interrupted=True,
            checkpoint_id=None,
        )

        assert status.can_resume() is False

    def test_status_with_all_fields(self):
        """Test InterruptStatus with all fields populated"""
        reason = InterruptReason(
            source=InterruptSource.TIMEOUT,
            mode=InterruptMode.GRACEFUL,
            message="Timeout exceeded",
            metadata={"timeout_seconds": 600},
        )

        status = InterruptStatus(
            interrupted=True,
            reason=reason,
            checkpoint_id="ckpt_final",
        )

        assert status.interrupted is True
        assert status.reason.source == InterruptSource.TIMEOUT
        assert status.reason.mode == InterruptMode.GRACEFUL
        assert status.checkpoint_id == "ckpt_final"
        assert status.can_resume() is True
