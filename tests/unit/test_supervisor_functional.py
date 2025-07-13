"""Functional tests for core/actors/supervisor.py that verify supervision strategies."""

import asyncio
import time
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch

import pytest


class TestSupervisorStrategies:
    """Test different supervision strategies and restart behaviors."""

    @pytest.mark.asyncio
    async def test_one_for_one_strategy(self):
        """Test one-for-one supervision strategy - restart only failed actor."""
        try:
            from kailash.core.actors.connection_actor import (
                ActorConnection,
                ConnectionState,
            )
            from kailash.core.actors.supervisor import (
                ActorSupervisor,
                RestartDecision,
                SupervisionStrategy,
            )

            # Create supervisor with one-for-one strategy
            supervisor = ActorSupervisor(
                name="test_supervisor",
                strategy=SupervisionStrategy.ONE_FOR_ONE,
                max_restarts=3,
                restart_window=60.0,
                restart_delay=0.1,
            )

            # Create mock actors
            actors = []
            for i in range(3):
                mock_actor = Mock(spec=ActorConnection)
                mock_actor.connection_id = f"actor_{i}"
                mock_actor.state = ConnectionState.HEALTHY
                mock_actor.start = AsyncMock()
                mock_actor.stop = AsyncMock()
                mock_actor.is_healthy = Mock(return_value=True)
                actors.append(mock_actor)

            # Add actors to supervisor
            for actor in actors:
                supervisor.add_actor(actor.connection_id, actor)

            await supervisor.start()

            # Simulate failure of one actor
            actors[1].state = ConnectionState.FAILED
            actors[1].is_healthy.return_value = False

            # Trigger failure detection
            await supervisor._handle_actor_failure("actor_1", Exception("Test failure"))

            # Only the failed actor should be restarted
            assert actors[1].stop.called
            assert actors[1].start.call_count >= 2  # Initial start + restart

            # Other actors should not be restarted
            assert actors[0].start.call_count == 1  # Only initial start
            assert actors[2].start.call_count == 1  # Only initial start

            await supervisor.stop()

        except ImportError:
            pytest.skip("ActorSupervisor not available")

    @pytest.mark.asyncio
    async def test_one_for_all_strategy(self):
        """Test one-for-all supervision strategy - restart all actors on any failure."""
        try:
            from kailash.core.actors.connection_actor import (
                ActorConnection,
                ConnectionState,
            )
            from kailash.core.actors.supervisor import (
                ActorSupervisor,
                SupervisionStrategy,
            )

            supervisor = ActorSupervisor(
                name="test_supervisor",
                strategy=SupervisionStrategy.ONE_FOR_ALL,
                restart_delay=0.1,
            )

            # Create mock actors
            actors = []
            for i in range(3):
                mock_actor = Mock(spec=ActorConnection)
                mock_actor.connection_id = f"actor_{i}"
                mock_actor.state = ConnectionState.HEALTHY
                mock_actor.start = AsyncMock()
                mock_actor.stop = AsyncMock()
                mock_actor.is_healthy = Mock(return_value=True)
                actors.append(mock_actor)

            # Add actors
            for actor in actors:
                supervisor.add_actor(actor.connection_id, actor)

            await supervisor.start()

            # Simulate failure of one actor
            actors[0].state = ConnectionState.FAILED
            actors[0].is_healthy.return_value = False

            # Trigger failure handling
            await supervisor._handle_actor_failure("actor_0", Exception("Test failure"))

            # All actors should be restarted
            for actor in actors:
                assert actor.stop.called, f"{actor.connection_id} should be stopped"
                assert (
                    actor.start.call_count >= 2
                ), f"{actor.connection_id} should be restarted"

            await supervisor.stop()

        except ImportError:
            pytest.skip("ActorSupervisor not available")

    @pytest.mark.asyncio
    async def test_rest_for_one_strategy(self):
        """Test rest-for-one strategy - restart failed actor and all after it."""
        try:
            from kailash.core.actors.connection_actor import (
                ActorConnection,
                ConnectionState,
            )
            from kailash.core.actors.supervisor import (
                ActorSupervisor,
                SupervisionStrategy,
            )

            supervisor = ActorSupervisor(
                name="test_supervisor",
                strategy=SupervisionStrategy.REST_FOR_ONE,
                restart_delay=0.1,
            )

            # Create mock actors in specific order
            actors = []
            for i in range(4):
                mock_actor = Mock(spec=ActorConnection)
                mock_actor.connection_id = f"actor_{i}"
                mock_actor.state = ConnectionState.HEALTHY
                mock_actor.start = AsyncMock()
                mock_actor.stop = AsyncMock()
                mock_actor.is_healthy = Mock(return_value=True)
                actors.append(mock_actor)

            # Add actors in order
            for actor in actors:
                supervisor.add_actor(actor.connection_id, actor)

            await supervisor.start()

            # Simulate failure of actor_1 (second actor)
            actors[1].state = ConnectionState.FAILED
            actors[1].is_healthy.return_value = False

            # Trigger failure handling
            await supervisor._handle_actor_failure("actor_1", Exception("Test failure"))

            # Actor 0 should not be restarted
            assert actors[0].start.call_count == 1  # Only initial start

            # Actors 1, 2, 3 should be restarted
            for i in range(1, 4):
                assert actors[i].stop.called, f"actor_{i} should be stopped"
                assert actors[i].start.call_count >= 2, f"actor_{i} should be restarted"

            await supervisor.stop()

        except ImportError:
            pytest.skip("ActorSupervisor not available")


class TestRestartDecisionLogic:
    """Test restart decision making and limits."""

    @pytest.mark.asyncio
    async def test_restart_limit_enforcement(self):
        """Test that restart limits are enforced within time window."""
        try:
            from kailash.core.actors.connection_actor import ActorConnection
            from kailash.core.actors.supervisor import (
                ActorSupervisor,
                RestartDecision,
                SupervisionStrategy,
            )

            supervisor = ActorSupervisor(
                name="test_supervisor",
                strategy=SupervisionStrategy.ONE_FOR_ONE,
                max_restarts=3,
                restart_window=1.0,  # 1 second window for testing
                restart_delay=0.05,
            )

            # Mock actor that always fails
            mock_actor = Mock(spec=ActorConnection)
            mock_actor.connection_id = "failing_actor"
            mock_actor.state = ConnectionState.FAILED
            mock_actor.start = AsyncMock()
            mock_actor.stop = AsyncMock()
            mock_actor.is_healthy = Mock(return_value=False)

            supervisor.add_actor("failing_actor", mock_actor)
            await supervisor.start()

            # Simulate multiple failures
            for i in range(5):
                decision = supervisor._decide_restart(
                    "failing_actor", Exception(f"Failure {i}")
                )

                if i < 3:  # Within max_restarts
                    assert decision == RestartDecision.RESTART
                    await supervisor._handle_actor_failure(
                        "failing_actor", Exception(f"Failure {i}")
                    )
                    await asyncio.sleep(0.1)
                else:  # Exceeded max_restarts
                    assert (
                        decision == RestartDecision.STOP
                        or decision == RestartDecision.ESCALATE
                    )

            # Verify restart count tracking
            assert len(supervisor.restart_counts["failing_actor"]) <= 3

            await supervisor.stop()

        except ImportError:
            pytest.skip("ActorSupervisor not available")

    @pytest.mark.asyncio
    async def test_restart_window_reset(self):
        """Test that restart counts reset after time window expires."""
        try:
            from kailash.core.actors.connection_actor import ActorConnection
            from kailash.core.actors.supervisor import (
                ActorSupervisor,
                RestartDecision,
                SupervisionStrategy,
            )

            supervisor = ActorSupervisor(
                name="test_supervisor",
                strategy=SupervisionStrategy.ONE_FOR_ONE,
                max_restarts=2,
                restart_window=0.5,  # 0.5 second window
                restart_delay=0.05,
            )

            mock_actor = Mock(spec=ActorConnection)
            mock_actor.connection_id = "test_actor"
            mock_actor.start = AsyncMock()
            mock_actor.stop = AsyncMock()

            supervisor.add_actor("test_actor", mock_actor)
            await supervisor.start()

            # First set of failures within window
            for i in range(2):
                decision = supervisor._decide_restart(
                    "test_actor", Exception(f"Failure {i}")
                )
                assert decision == RestartDecision.RESTART
                await supervisor._handle_actor_failure(
                    "test_actor", Exception(f"Failure {i}")
                )

            # Wait for window to expire
            await asyncio.sleep(0.6)

            # Should be able to restart again after window reset
            decision = supervisor._decide_restart(
                "test_actor", Exception("After window")
            )
            assert decision == RestartDecision.RESTART

            await supervisor.stop()

        except ImportError:
            pytest.skip("ActorSupervisor not available")

    @pytest.mark.asyncio
    async def test_escalation_decision(self):
        """Test escalation decision when supervisor cannot handle failure."""
        try:
            from kailash.core.actors.supervisor import (
                ActorSupervisor,
                RestartDecision,
                SupervisionStrategy,
            )

            supervisor = ActorSupervisor(
                name="test_supervisor",
                strategy=SupervisionStrategy.ONE_FOR_ONE,
                max_restarts=2,
                restart_window=60.0,
                escalate_on_critical=True,
            )

            # Set up escalation callback
            escalation_called = False
            escalation_error = None

            def on_escalation(error):
                nonlocal escalation_called, escalation_error
                escalation_called = True
                escalation_error = error

            supervisor.on_supervisor_failure = on_escalation

            mock_actor = Mock()
            mock_actor.connection_id = "critical_actor"
            mock_actor.is_critical = True  # Mark as critical
            mock_actor.start = AsyncMock()
            mock_actor.stop = AsyncMock()

            supervisor.add_actor("critical_actor", mock_actor)
            await supervisor.start()

            # Exhaust restart attempts
            for i in range(3):
                await supervisor._handle_actor_failure(
                    "critical_actor", Exception(f"Critical failure {i}")
                )

            # Should have escalated
            assert escalation_called
            assert escalation_error is not None

            await supervisor.stop()

        except ImportError:
            pytest.skip("ActorSupervisor not available")


class TestSupervisorMonitoring:
    """Test supervisor monitoring and health checking."""

    @pytest.mark.asyncio
    async def test_periodic_health_monitoring(self):
        """Test periodic health monitoring of supervised actors."""
        try:
            from kailash.core.actors.connection_actor import ConnectionState
            from kailash.core.actors.supervisor import (
                ActorSupervisor,
                SupervisionStrategy,
            )

            supervisor = ActorSupervisor(
                name="test_supervisor",
                strategy=SupervisionStrategy.ONE_FOR_ONE,
                health_check_interval=0.1,  # Fast checks for testing
            )

            # Create actors with changing health
            health_states = [True, True, False]  # Third check fails
            check_count = 0

            mock_actor = Mock()
            mock_actor.connection_id = "monitored_actor"
            mock_actor.state = ConnectionState.HEALTHY

            def health_check():
                nonlocal check_count
                if check_count < len(health_states):
                    result = health_states[check_count]
                    check_count += 1
                    return result
                return False

            mock_actor.is_healthy = health_check
            mock_actor.start = AsyncMock()
            mock_actor.stop = AsyncMock()

            supervisor.add_actor("monitored_actor", mock_actor)
            await supervisor.start()

            # Let health checks run
            await asyncio.sleep(0.35)

            # Should have detected unhealthy state
            assert check_count >= 3
            assert mock_actor.stop.called  # Should restart unhealthy actor

            await supervisor.stop()

        except ImportError:
            pytest.skip("ActorSupervisor not available")

    @pytest.mark.asyncio
    async def test_supervisor_metrics_collection(self):
        """Test collection of supervisor metrics."""
        try:
            from kailash.core.actors.supervisor import (
                ActorSupervisor,
                SupervisionStrategy,
            )

            supervisor = ActorSupervisor(
                name="test_supervisor",
                strategy=SupervisionStrategy.ONE_FOR_ONE,
                collect_metrics=True,
            )

            # Create test actors
            actors = []
            for i in range(3):
                mock_actor = Mock()
                mock_actor.connection_id = f"actor_{i}"
                mock_actor.start = AsyncMock()
                mock_actor.stop = AsyncMock()
                mock_actor.is_healthy = Mock(return_value=True)
                mock_actor.get_stats = Mock(
                    return_value={
                        "queries_executed": 10 + i,
                        "errors_encountered": i,
                        "health_score": 90 - i * 10,
                    }
                )
                actors.append(mock_actor)
                supervisor.add_actor(mock_actor.connection_id, mock_actor)

            await supervisor.start()

            # Simulate some failures and restarts
            await supervisor._handle_actor_failure("actor_1", Exception("Test"))
            await asyncio.sleep(0.1)

            # Get supervisor metrics
            metrics = supervisor.get_metrics()

            assert "total_actors" in metrics
            assert metrics["total_actors"] == 3
            assert "total_restarts" in metrics
            assert metrics["total_restarts"] >= 1
            assert "uptime" in metrics
            assert metrics["uptime"] > 0

            # Get aggregate actor stats
            actor_stats = supervisor.get_aggregate_actor_stats()
            assert "total_queries" in actor_stats
            assert "total_errors" in actor_stats
            assert "average_health_score" in actor_stats

            await supervisor.stop()

        except ImportError:
            pytest.skip("ActorSupervisor not available")


class TestSupervisorCallbacks:
    """Test supervisor callback mechanisms."""

    @pytest.mark.asyncio
    async def test_failure_callbacks(self):
        """Test actor failure callback notifications."""
        try:
            from kailash.core.actors.supervisor import (
                ActorSupervisor,
                SupervisionStrategy,
            )

            supervisor = ActorSupervisor(
                name="test_supervisor", strategy=SupervisionStrategy.ONE_FOR_ONE
            )

            # Track callback invocations
            failure_callbacks = []
            restart_callbacks = []

            def on_failure(actor_id, error):
                failure_callbacks.append((actor_id, str(error)))

            def on_restart(actor_id, attempt):
                restart_callbacks.append((actor_id, attempt))

            supervisor.on_actor_failure = on_failure
            supervisor.on_actor_restart = on_restart

            # Create failing actor
            mock_actor = Mock()
            mock_actor.connection_id = "callback_test"
            mock_actor.start = AsyncMock()
            mock_actor.stop = AsyncMock()

            supervisor.add_actor("callback_test", mock_actor)
            await supervisor.start()

            # Trigger failures
            test_error = Exception("Test failure")
            await supervisor._handle_actor_failure("callback_test", test_error)

            # Verify callbacks were invoked
            assert len(failure_callbacks) == 1
            assert failure_callbacks[0][0] == "callback_test"
            assert "Test failure" in failure_callbacks[0][1]

            assert len(restart_callbacks) >= 1
            assert restart_callbacks[0][0] == "callback_test"
            assert restart_callbacks[0][1] == 1  # First restart attempt

            await supervisor.stop()

        except ImportError:
            pytest.skip("ActorSupervisor not available")

    @pytest.mark.asyncio
    async def test_custom_restart_decision_callback(self):
        """Test custom restart decision callback."""
        try:
            from kailash.core.actors.supervisor import (
                ActorSupervisor,
                RestartDecision,
                SupervisionStrategy,
            )

            supervisor = ActorSupervisor(
                name="test_supervisor", strategy=SupervisionStrategy.ONE_FOR_ONE
            )

            # Custom restart decision logic
            def custom_restart_decider(actor_id, error, restart_count):
                # Custom logic: don't restart if error message contains "fatal"
                if "fatal" in str(error).lower():
                    return RestartDecision.STOP
                elif restart_count >= 5:
                    return RestartDecision.ESCALATE
                else:
                    return RestartDecision.RESTART

            supervisor.custom_restart_decider = custom_restart_decider

            mock_actor = Mock()
            mock_actor.connection_id = "custom_decision"
            mock_actor.start = AsyncMock()
            mock_actor.stop = AsyncMock()

            supervisor.add_actor("custom_decision", mock_actor)
            await supervisor.start()

            # Test non-fatal error (should restart)
            decision1 = supervisor._decide_restart(
                "custom_decision", Exception("Normal error")
            )
            assert decision1 == RestartDecision.RESTART

            # Test fatal error (should stop)
            decision2 = supervisor._decide_restart(
                "custom_decision", Exception("Fatal error occurred")
            )
            assert decision2 == RestartDecision.STOP

            await supervisor.stop()

        except ImportError:
            pytest.skip("ActorSupervisor not available")


class TestSupervisorEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_supervisor_with_no_actors(self):
        """Test supervisor behavior with no actors."""
        try:
            from kailash.core.actors.supervisor import (
                ActorSupervisor,
                SupervisionStrategy,
            )

            supervisor = ActorSupervisor(
                name="empty_supervisor", strategy=SupervisionStrategy.ONE_FOR_ONE
            )

            # Start with no actors
            await supervisor.start()
            assert supervisor._running

            # Get metrics should work
            metrics = supervisor.get_metrics()
            assert metrics["total_actors"] == 0

            # Stop should work
            await supervisor.stop()
            assert not supervisor._running

        except ImportError:
            pytest.skip("ActorSupervisor not available")

    @pytest.mark.asyncio
    async def test_adding_actors_after_start(self):
        """Test adding actors to running supervisor."""
        try:
            from kailash.core.actors.supervisor import (
                ActorSupervisor,
                SupervisionStrategy,
            )

            supervisor = ActorSupervisor(
                name="dynamic_supervisor", strategy=SupervisionStrategy.ONE_FOR_ONE
            )

            await supervisor.start()

            # Add actor after supervisor is running
            mock_actor = Mock()
            mock_actor.connection_id = "late_actor"
            mock_actor.start = AsyncMock()
            mock_actor.stop = AsyncMock()
            mock_actor.is_healthy = Mock(return_value=True)

            await supervisor.add_actor_async("late_actor", mock_actor)

            # Actor should be started automatically
            assert mock_actor.start.called
            assert "late_actor" in supervisor.actors

            # Should be monitored
            metrics = supervisor.get_metrics()
            assert metrics["total_actors"] == 1

            await supervisor.stop()

        except ImportError:
            pytest.skip("ActorSupervisor not available")

    @pytest.mark.asyncio
    async def test_removing_actors_from_running_supervisor(self):
        """Test removing actors from running supervisor."""
        try:
            from kailash.core.actors.supervisor import (
                ActorSupervisor,
                SupervisionStrategy,
            )

            supervisor = ActorSupervisor(
                name="dynamic_supervisor", strategy=SupervisionStrategy.ONE_FOR_ONE
            )

            # Add actors
            actors = []
            for i in range(3):
                mock_actor = Mock()
                mock_actor.connection_id = f"actor_{i}"
                mock_actor.start = AsyncMock()
                mock_actor.stop = AsyncMock()
                actors.append(mock_actor)
                supervisor.add_actor(mock_actor.connection_id, mock_actor)

            await supervisor.start()

            # Remove middle actor
            await supervisor.remove_actor_async("actor_1")

            # Actor should be stopped
            assert actors[1].stop.called
            assert "actor_1" not in supervisor.actors
            assert len(supervisor.actors) == 2

            # Remaining actors should still be supervised
            assert "actor_0" in supervisor.actors
            assert "actor_2" in supervisor.actors

            await supervisor.stop()

        except ImportError:
            pytest.skip("ActorSupervisor not available")

    @pytest.mark.asyncio
    async def test_concurrent_failures_handling(self):
        """Test handling of multiple concurrent actor failures."""
        try:
            from kailash.core.actors.supervisor import (
                ActorSupervisor,
                SupervisionStrategy,
            )

            supervisor = ActorSupervisor(
                name="concurrent_supervisor",
                strategy=SupervisionStrategy.ONE_FOR_ONE,
                restart_delay=0.1,
            )

            # Create multiple failing actors
            actors = []
            for i in range(5):
                mock_actor = Mock()
                mock_actor.connection_id = f"actor_{i}"
                mock_actor.start = AsyncMock()
                mock_actor.stop = AsyncMock()
                mock_actor.is_healthy = Mock(return_value=False)
                actors.append(mock_actor)
                supervisor.add_actor(mock_actor.connection_id, mock_actor)

            await supervisor.start()

            # Trigger concurrent failures
            tasks = []
            for i in range(5):
                task = supervisor._handle_actor_failure(
                    f"actor_{i}", Exception(f"Concurrent failure {i}")
                )
                tasks.append(task)

            # All failures should be handled
            await asyncio.gather(*tasks)

            # All actors should have been restarted
            for actor in actors:
                assert actor.stop.called
                assert actor.start.call_count >= 2

            await supervisor.stop()

        except ImportError:
            pytest.skip("ActorSupervisor not available")

    @pytest.mark.asyncio
    async def test_supervisor_shutdown_with_pending_restarts(self):
        """Test supervisor shutdown while restarts are pending."""
        try:
            from kailash.core.actors.supervisor import (
                ActorSupervisor,
                SupervisionStrategy,
            )

            supervisor = ActorSupervisor(
                name="shutdown_test",
                strategy=SupervisionStrategy.ONE_FOR_ALL,
                restart_delay=1.0,  # Long delay
            )

            # Add actors
            actors = []
            for i in range(3):
                mock_actor = Mock()
                mock_actor.connection_id = f"actor_{i}"
                mock_actor.start = AsyncMock()
                mock_actor.stop = AsyncMock()
                actors.append(mock_actor)
                supervisor.add_actor(mock_actor.connection_id, mock_actor)

            await supervisor.start()

            # Trigger failure (will start restart process)
            asyncio.create_task(
                supervisor._handle_actor_failure("actor_0", Exception("Test"))
            )

            # Immediately stop supervisor
            await asyncio.sleep(0.1)  # Let restart begin
            await supervisor.stop()

            # All actors should be stopped
            for actor in actors:
                assert actor.stop.called

            # Supervisor should be stopped cleanly
            assert not supervisor._running
            assert supervisor._monitor_task is None or supervisor._monitor_task.done()

        except ImportError:
            pytest.skip("ActorSupervisor not available")
