"""
Unit tests for SecurityAuditLogger Thread Safety (ROUND5-005).

Tests verify that SecurityAuditLogger handles concurrent access correctly:
- No data loss under concurrent logging
- No errors when reading while writing
- Correct trimming behavior under concurrent access

Following the 3-tier testing strategy - Tier 1 (Unit Tests).
Mocking is allowed for unit tests.
"""

import concurrent.futures
import threading
import time
from typing import List

import pytest
from kaizen.trust.security import (
    SecurityAuditLogger,
    SecurityEvent,
    SecurityEventSeverity,
    SecurityEventType,
)


class TestSecurityAuditLoggerThreadSafety:
    """Test thread-safety of SecurityAuditLogger (ROUND5-005).

    These tests verify that concurrent access to the security audit logger
    does not cause race conditions, data loss, or corruption.
    """

    def test_concurrent_logging_no_data_loss(self):
        """ROUND5-005: 10 threads x 100 events each, verify all events logged.

        Spawns multiple threads that log events concurrently, then verifies
        that all events are present in the log without data loss.
        """
        logger = SecurityAuditLogger(max_events=10000)
        num_threads = 10
        events_per_thread = 100
        expected_total = num_threads * events_per_thread
        errors: List[str] = []

        def log_events(thread_id: int):
            """Log events for a single thread."""
            for i in range(events_per_thread):
                try:
                    logger.log_security_event(
                        event_type=SecurityEventType.ESTABLISH_TRUST,
                        details={
                            "thread_id": thread_id,
                            "event_index": i,
                            "unique_key": f"thread-{thread_id}-event-{i}",
                        },
                        authority_id=f"authority-{thread_id}",
                        agent_id=f"agent-{thread_id}-{i}",
                        severity=SecurityEventSeverity.INFO,
                    )
                except Exception as e:
                    errors.append(f"Thread {thread_id} event {i} error: {e}")

        # Run logging from multiple threads concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [
                executor.submit(log_events, thread_id)
                for thread_id in range(num_threads)
            ]
            # Wait for all threads to complete
            for future in concurrent.futures.as_completed(futures, timeout=30.0):
                future.result()  # Raises if thread had an error

        # No errors should have occurred
        assert errors == [], f"Concurrent logging caused errors: {errors}"

        # Verify all events were logged
        all_events = logger.get_recent_events(count=expected_total)
        assert len(all_events) == expected_total, (
            f"ROUND5-005: Expected {expected_total} events, got {len(all_events)}. "
            f"Data loss detected under concurrent access!"
        )

        # Verify each thread's events are present
        for thread_id in range(num_threads):
            thread_events = [
                e for e in all_events if e.details.get("thread_id") == thread_id
            ]
            assert len(thread_events) == events_per_thread, (
                f"Thread {thread_id} has {len(thread_events)} events, "
                f"expected {events_per_thread}"
            )

    def test_concurrent_logging_and_reading(self):
        """ROUND5-005: Concurrent writes and reads cause no errors.

        Spawns threads that log events while other threads read events,
        verifying no exceptions occur during concurrent access.
        """
        logger = SecurityAuditLogger(max_events=5000)
        errors: List[str] = []
        write_count = 0
        read_count = 0
        write_lock = threading.Lock()
        read_lock = threading.Lock()

        def log_events(thread_id: int, count: int):
            """Log events for a single thread."""
            nonlocal write_count
            for i in range(count):
                try:
                    logger.log_security_event(
                        event_type=SecurityEventType.VERIFY_TRUST,
                        details={"writer_thread": thread_id, "index": i},
                        authority_id=f"writer-{thread_id}",
                        severity=SecurityEventSeverity.INFO,
                    )
                    with write_lock:
                        write_count += 1
                except Exception as e:
                    errors.append(f"Write thread {thread_id} error: {e}")
                time.sleep(0.0001)  # Small delay to interleave operations

        def read_events(thread_id: int, iterations: int):
            """Read events repeatedly."""
            nonlocal read_count
            for i in range(iterations):
                try:
                    # Read recent events
                    events = logger.get_recent_events(count=100)
                    # Verify it returns a list
                    assert isinstance(events, list)
                    with read_lock:
                        read_count += 1
                except Exception as e:
                    errors.append(f"Read thread {thread_id} iteration {i} error: {e}")
                time.sleep(0.0001)  # Small delay to interleave operations

        num_writers = 4
        num_readers = 4
        events_per_writer = 100
        reads_per_reader = 100

        # Run writers and readers concurrently
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=num_writers + num_readers
        ) as executor:
            writer_futures = [
                executor.submit(log_events, i, events_per_writer)
                for i in range(num_writers)
            ]
            reader_futures = [
                executor.submit(read_events, i, reads_per_reader)
                for i in range(num_readers)
            ]

            # Wait for all to complete
            all_futures = writer_futures + reader_futures
            for future in concurrent.futures.as_completed(all_futures, timeout=30.0):
                future.result()

        # No errors should have occurred
        assert errors == [], f"Concurrent read/write caused errors: {errors}"

        # Verify writes and reads happened
        expected_writes = num_writers * events_per_writer
        assert (
            write_count == expected_writes
        ), f"Expected {expected_writes} writes, got {write_count}"
        expected_reads = num_readers * reads_per_reader
        assert (
            read_count == expected_reads
        ), f"Expected {expected_reads} reads, got {read_count}"

    def test_trimming_under_concurrent_access(self):
        """ROUND5-005: Small max_events triggers frequent trimming under concurrent access.

        Uses a small max_events limit to force frequent trimming operations,
        verifying that concurrent access during trimming does not cause errors.
        """
        # Use small max_events to force frequent trimming
        max_events = 50
        logger = SecurityAuditLogger(max_events=max_events)
        errors: List[str] = []
        total_logged = 0
        log_lock = threading.Lock()

        def log_many_events(thread_id: int, count: int):
            """Log many events, triggering trimming."""
            nonlocal total_logged
            for i in range(count):
                try:
                    logger.log_security_event(
                        event_type=SecurityEventType.RATE_LIMIT_WARNING,
                        details={
                            "thread_id": thread_id,
                            "event_index": i,
                            "forcing_trim": True,
                        },
                        authority_id=f"trimmer-{thread_id}",
                        severity=SecurityEventSeverity.WARNING,
                    )
                    with log_lock:
                        total_logged += 1
                except Exception as e:
                    errors.append(f"Thread {thread_id} event {i} trim error: {e}")

        num_threads = 5
        events_per_thread = 100  # 500 total, forcing many trims with max_events=50

        # Run logging from multiple threads
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [
                executor.submit(log_many_events, i, events_per_thread)
                for i in range(num_threads)
            ]
            for future in concurrent.futures.as_completed(futures, timeout=30.0):
                future.result()

        # No errors should have occurred during trimming
        assert errors == [], f"Trimming under concurrent access caused errors: {errors}"

        # Verify total logged
        expected_total = num_threads * events_per_thread
        assert (
            total_logged == expected_total
        ), f"Expected {expected_total} total logged, got {total_logged}"

        # Verify events were trimmed correctly (should have at most max_events)
        all_events = logger.get_recent_events(count=max_events + 100)
        assert (
            len(all_events) <= max_events
        ), f"Events not trimmed correctly: {len(all_events)} > {max_events}"

    def test_logger_has_lock_attribute(self):
        """ROUND5-005: Verify SecurityAuditLogger has a threading lock for thread-safety."""
        logger = SecurityAuditLogger()

        assert hasattr(
            logger, "_lock"
        ), "SecurityAuditLogger missing _lock attribute for thread-safety"
        assert isinstance(
            logger._lock, type(threading.Lock())
        ), "_lock should be a threading.Lock instance"

    def test_get_recent_events_returns_copy(self):
        """ROUND5-005: Verify get_recent_events returns a copy, not internal list.

        Modifications to the returned list should not affect internal state.
        """
        logger = SecurityAuditLogger()

        # Log an event
        logger.log_security_event(
            event_type=SecurityEventType.ESTABLISH_TRUST,
            details={"test": "copy"},
            authority_id="test-authority",
        )

        # Get events twice
        events1 = logger.get_recent_events(count=10)
        events2 = logger.get_recent_events(count=10)

        # Should be equal but not the same object
        assert len(events1) == 1
        assert len(events2) == 1
        assert (
            events1 is not events2
        ), "get_recent_events should return different list objects"

        # Modifying returned list should not affect internal state
        events1.clear()
        assert len(events1) == 0

        events3 = logger.get_recent_events(count=10)
        assert (
            len(events3) == 1
        ), "Clearing returned list affected internal state - not a copy!"


class TestSecurityAuditLoggerBasic:
    """Basic functionality tests for SecurityAuditLogger."""

    def test_log_and_retrieve_events(self):
        """Test basic logging and retrieval."""
        logger = SecurityAuditLogger()

        logger.log_security_event(
            event_type=SecurityEventType.AUTHENTICATION_SUCCESS,
            details={"method": "oauth2"},
            authority_id="org-acme",
            agent_id="agent-001",
            severity=SecurityEventSeverity.INFO,
        )

        events = logger.get_recent_events(count=10)

        assert len(events) == 1
        assert events[0].event_type == SecurityEventType.AUTHENTICATION_SUCCESS
        assert events[0].authority_id == "org-acme"
        assert events[0].agent_id == "agent-001"
        assert events[0].details["method"] == "oauth2"

    def test_max_events_trimming(self):
        """Test that events are trimmed when max_events is exceeded."""
        max_events = 10
        logger = SecurityAuditLogger(max_events=max_events)

        # Log more than max_events
        for i in range(max_events + 5):
            logger.log_security_event(
                event_type=SecurityEventType.VERIFY_TRUST,
                details={"index": i},
                authority_id="test",
            )

        events = logger.get_recent_events(count=max_events + 10)

        # Should only have max_events
        assert len(events) == max_events

        # Should have the most recent events (indices 5-14)
        indices = [e.details["index"] for e in events]
        expected_indices = list(range(5, 15))
        assert sorted(indices) == expected_indices

    def test_filter_by_event_type(self):
        """Test filtering events by event type."""
        logger = SecurityAuditLogger()

        logger.log_security_event(
            event_type=SecurityEventType.ESTABLISH_TRUST,
            details={"action": "establish"},
            authority_id="test",
        )
        logger.log_security_event(
            event_type=SecurityEventType.VERIFY_TRUST,
            details={"action": "verify"},
            authority_id="test",
        )
        logger.log_security_event(
            event_type=SecurityEventType.ESTABLISH_TRUST,
            details={"action": "establish2"},
            authority_id="test",
        )

        establish_events = logger.get_recent_events(
            count=10,
            event_type=SecurityEventType.ESTABLISH_TRUST,
        )

        assert len(establish_events) == 2
        assert all(
            e.event_type == SecurityEventType.ESTABLISH_TRUST for e in establish_events
        )

    def test_filter_by_severity(self):
        """Test filtering events by severity."""
        logger = SecurityAuditLogger()

        logger.log_security_event(
            event_type=SecurityEventType.RATE_LIMIT_WARNING,
            details={},
            authority_id="test",
            severity=SecurityEventSeverity.WARNING,
        )
        logger.log_security_event(
            event_type=SecurityEventType.RATE_LIMIT_EXCEEDED,
            details={},
            authority_id="test",
            severity=SecurityEventSeverity.ERROR,
        )
        logger.log_security_event(
            event_type=SecurityEventType.INJECTION_ATTEMPT,
            details={},
            authority_id="test",
            severity=SecurityEventSeverity.CRITICAL,
        )

        critical_events = logger.get_recent_events(
            count=10,
            severity=SecurityEventSeverity.CRITICAL,
        )

        assert len(critical_events) == 1
        assert critical_events[0].severity == SecurityEventSeverity.CRITICAL
