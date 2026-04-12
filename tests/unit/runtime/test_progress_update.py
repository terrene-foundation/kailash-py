"""Tests for ProgressUpdate contract — issue #374.

Tier 1 unit tests covering:
- ProgressUpdate dataclass behavior (fraction, immutability, indeterminate)
- ProgressRegistry (emit, multi-callback, unregister, thread safety)
- report_progress() convenience function (no-op safety, end-to-end with context)
"""

import threading
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from kailash.runtime.progress import (
    ProgressCallback,
    ProgressRegistry,
    ProgressUpdate,
    _current_node_id,
    _current_progress_registry,
    report_progress,
)


class TestProgressUpdateFraction:
    """Verify fraction calculation for determinate and edge-case progress."""

    def test_progress_update_fraction(self) -> None:
        """Fraction returns current/total as a float between 0.0 and 1.0."""
        update = ProgressUpdate(node_id="n1", current=50, total=100)
        assert update.fraction == pytest.approx(0.5)

    def test_progress_update_fraction_complete(self) -> None:
        """Fraction is 1.0 when current equals total."""
        update = ProgressUpdate(node_id="n1", current=100, total=100)
        assert update.fraction == pytest.approx(1.0)

    def test_progress_update_fraction_zero_progress(self) -> None:
        """Fraction is 0.0 when current is zero with a known total."""
        update = ProgressUpdate(node_id="n1", current=0, total=200)
        assert update.fraction == pytest.approx(0.0)

    def test_progress_update_fraction_partial(self) -> None:
        """Fraction handles non-round divisions correctly."""
        update = ProgressUpdate(node_id="n1", current=1, total=3)
        assert update.fraction == pytest.approx(1 / 3)


class TestProgressUpdateIndeterminate:
    """Verify behavior when total is unknown (indeterminate progress)."""

    def test_progress_update_indeterminate(self) -> None:
        """Fraction returns None when total is None."""
        update = ProgressUpdate(node_id="n1", current=42, total=None)
        assert update.fraction is None

    def test_progress_update_zero_total(self) -> None:
        """Fraction returns None when total is zero (division guard)."""
        update = ProgressUpdate(node_id="n1", current=0, total=0)
        assert update.fraction is None


class TestProgressUpdateFrozen:
    """Verify immutability of ProgressUpdate."""

    def test_progress_update_frozen(self) -> None:
        """Frozen dataclass rejects attribute mutation."""
        update = ProgressUpdate(node_id="n1", current=10, total=100)
        with pytest.raises(AttributeError):
            update.current = 20  # type: ignore[misc]
        with pytest.raises(AttributeError):
            update.node_id = "n2"  # type: ignore[misc]

    def test_progress_update_has_timestamp(self) -> None:
        """Timestamp is populated automatically and is timezone-aware."""
        before = datetime.now(UTC)
        update = ProgressUpdate(node_id="n1", current=0)
        after = datetime.now(UTC)
        assert before <= update.timestamp <= after

    def test_progress_update_default_message(self) -> None:
        """Default message is empty string."""
        update = ProgressUpdate(node_id="n1", current=0)
        assert update.message == ""

    def test_progress_update_custom_message(self) -> None:
        """Custom message is preserved."""
        update = ProgressUpdate(node_id="n1", current=5, total=10, message="halfway")
        assert update.message == "halfway"


class TestProgressRegistryEmit:
    """Verify single-callback emit behavior."""

    def test_progress_registry_emit(self) -> None:
        """Registered callback receives the emitted update."""
        registry = ProgressRegistry()
        received: list[ProgressUpdate] = []
        registry.register(received.append)

        update = ProgressUpdate(node_id="n1", current=1, total=10)
        registry.emit(update)

        assert len(received) == 1
        assert received[0] is update

    def test_progress_registry_emit_multiple_updates(self) -> None:
        """Callback receives every emitted update in order."""
        registry = ProgressRegistry()
        received: list[ProgressUpdate] = []
        registry.register(received.append)

        for i in range(5):
            registry.emit(ProgressUpdate(node_id="n1", current=i, total=5))

        assert len(received) == 5
        assert [u.current for u in received] == [0, 1, 2, 3, 4]


class TestProgressRegistryMultipleCallbacks:
    """Verify all registered callbacks receive updates."""

    def test_progress_registry_multiple_callbacks(self) -> None:
        """All registered callbacks receive the same update."""
        registry = ProgressRegistry()
        received_a: list[ProgressUpdate] = []
        received_b: list[ProgressUpdate] = []
        registry.register(received_a.append)
        registry.register(received_b.append)

        update = ProgressUpdate(node_id="n1", current=3, total=10)
        registry.emit(update)

        assert len(received_a) == 1
        assert len(received_b) == 1
        assert received_a[0] is update
        assert received_b[0] is update

    def test_progress_registry_failing_callback_does_not_block_others(self) -> None:
        """A callback that raises does not prevent other callbacks from firing."""
        registry = ProgressRegistry()
        received: list[ProgressUpdate] = []

        def bad_callback(update: ProgressUpdate) -> None:
            raise RuntimeError("boom")

        registry.register(bad_callback)
        registry.register(received.append)

        update = ProgressUpdate(node_id="n1", current=1, total=1)
        registry.emit(update)

        assert len(received) == 1
        assert received[0] is update


class TestProgressRegistryUnregister:
    """Verify unregister stops callback delivery."""

    def test_progress_registry_unregister(self) -> None:
        """Unregistered callback stops receiving updates."""
        registry = ProgressRegistry()
        received: list[ProgressUpdate] = []
        registry.register(received.append)

        registry.emit(ProgressUpdate(node_id="n1", current=1, total=2))
        assert len(received) == 1

        registry.unregister(received.append)
        registry.emit(ProgressUpdate(node_id="n1", current=2, total=2))
        assert len(received) == 1  # no new update

    def test_progress_registry_unregister_unknown_is_noop(self) -> None:
        """Unregistering a callback that was never registered does not raise."""
        registry = ProgressRegistry()
        registry.unregister(lambda u: None)  # should not raise

    def test_progress_registry_clear(self) -> None:
        """Clear removes all callbacks."""
        registry = ProgressRegistry()
        received: list[ProgressUpdate] = []
        registry.register(received.append)
        registry.clear()

        registry.emit(ProgressUpdate(node_id="n1", current=1, total=1))
        assert len(received) == 0


class TestProgressRegistryThreadSafety:
    """Verify concurrent emit/register from multiple threads."""

    def test_progress_registry_thread_safety(self) -> None:
        """Concurrent register and emit from multiple threads without errors."""
        registry = ProgressRegistry()
        errors: list[Exception] = []
        total_emits = 100
        total_threads = 8

        def emitter(thread_id: int) -> None:
            try:
                received: list[ProgressUpdate] = []
                registry.register(received.append)
                for i in range(total_emits):
                    registry.emit(
                        ProgressUpdate(
                            node_id=f"thread-{thread_id}",
                            current=i,
                            total=total_emits,
                        )
                    )
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=emitter, args=(t,)) for t in range(total_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Thread safety errors: {errors}"


class TestReportProgressNoRegistry:
    """Verify report_progress is a safe no-op without active context."""

    def test_report_progress_no_registry(self) -> None:
        """report_progress does nothing when no registry is active."""
        # This must not raise — backward compatibility guarantee
        report_progress(current=1, total=10, message="should be ignored")

    def test_report_progress_no_node_id(self) -> None:
        """report_progress does nothing when registry exists but node_id is unset."""
        registry = ProgressRegistry()
        received: list[ProgressUpdate] = []
        registry.register(received.append)

        token = _current_progress_registry.set(registry)
        try:
            report_progress(current=1, total=10)
        finally:
            _current_progress_registry.reset(token)

        assert len(received) == 0


class TestReportProgressWithRegistry:
    """End-to-end test with context variables set up as Node.execute() would."""

    def test_report_progress_with_registry(self) -> None:
        """report_progress emits to registry when both context vars are set."""
        registry = ProgressRegistry()
        received: list[ProgressUpdate] = []
        registry.register(received.append)

        registry_token = _current_progress_registry.set(registry)
        node_id_token = _current_node_id.set("test-node-42")
        try:
            report_progress(current=5, total=20, message="processing")
        finally:
            _current_node_id.reset(node_id_token)
            _current_progress_registry.reset(registry_token)

        assert len(received) == 1
        update = received[0]
        assert update.node_id == "test-node-42"
        assert update.current == 5
        assert update.total == 20
        assert update.message == "processing"
        assert update.fraction == pytest.approx(0.25)

    def test_report_progress_indeterminate_with_registry(self) -> None:
        """report_progress works for indeterminate progress (total=None)."""
        registry = ProgressRegistry()
        received: list[ProgressUpdate] = []
        registry.register(received.append)

        registry_token = _current_progress_registry.set(registry)
        node_id_token = _current_node_id.set("scanner")
        try:
            report_progress(current=42, message="scanning...")
        finally:
            _current_node_id.reset(node_id_token)
            _current_progress_registry.reset(registry_token)

        assert len(received) == 1
        assert received[0].total is None
        assert received[0].fraction is None
        assert received[0].message == "scanning..."
