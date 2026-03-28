"""Unit tests for SignalChannel and QueryRegistry.

Tests the core signal/query primitives independent of the runtime
and workflow execution machinery.
"""

import asyncio

import pytest

from kailash.runtime.signals import QueryRegistry, SignalChannel


class TestSignalChannel:
    """Tests for SignalChannel send/wait_for mechanics."""

    @pytest.fixture
    def channel(self):
        return SignalChannel()

    @pytest.mark.asyncio
    async def test_send_and_wait_for(self, channel):
        """Signal sent before wait_for should be received immediately."""
        channel.send("test_signal", {"key": "value"})
        data = await channel.wait_for("test_signal", timeout=1.0)
        assert data == {"key": "value"}

    @pytest.mark.asyncio
    async def test_send_none_data(self, channel):
        """Sending without data should deliver None."""
        channel.send("test_signal")
        data = await channel.wait_for("test_signal", timeout=1.0)
        assert data is None

    @pytest.mark.asyncio
    async def test_send_string_data(self, channel):
        """Sending a string payload should work."""
        channel.send("msg", "hello world")
        data = await channel.wait_for("msg", timeout=1.0)
        assert data == "hello world"

    @pytest.mark.asyncio
    async def test_send_integer_data(self, channel):
        """Sending an integer payload should work."""
        channel.send("count", 42)
        data = await channel.wait_for("count", timeout=1.0)
        assert data == 42

    @pytest.mark.asyncio
    async def test_multiple_signals_queued(self, channel):
        """Multiple signals to the same name should be queued in order."""
        channel.send("events", {"seq": 1})
        channel.send("events", {"seq": 2})
        channel.send("events", {"seq": 3})

        data1 = await channel.wait_for("events", timeout=1.0)
        data2 = await channel.wait_for("events", timeout=1.0)
        data3 = await channel.wait_for("events", timeout=1.0)

        assert data1 == {"seq": 1}
        assert data2 == {"seq": 2}
        assert data3 == {"seq": 3}

    @pytest.mark.asyncio
    async def test_different_signal_names_independent(self, channel):
        """Signals with different names should be independent."""
        channel.send("alpha", "a_data")
        channel.send("beta", "b_data")

        # Read in reverse order
        b = await channel.wait_for("beta", timeout=1.0)
        a = await channel.wait_for("alpha", timeout=1.0)

        assert a == "a_data"
        assert b == "b_data"

    @pytest.mark.asyncio
    async def test_wait_for_timeout(self, channel):
        """wait_for should raise TimeoutError when timeout expires."""
        with pytest.raises(
            TimeoutError, match="Timed out waiting for signal 'missing'"
        ):
            await channel.wait_for("missing", timeout=0.05)

    @pytest.mark.asyncio
    async def test_wait_for_receives_later_signal(self, channel):
        """wait_for should block until a signal arrives from another task."""

        async def send_after_delay():
            await asyncio.sleep(0.05)
            channel.send("delayed", {"arrived": True})

        task = asyncio.create_task(send_after_delay())
        data = await channel.wait_for("delayed", timeout=2.0)
        assert data == {"arrived": True}
        await task

    def test_has_pending_true(self, channel):
        """has_pending should return True when signals are queued."""
        channel.send("check", "data")
        assert channel.has_pending("check") is True

    def test_has_pending_false_no_queue(self, channel):
        """has_pending should return False for nonexistent signal names."""
        assert channel.has_pending("nonexistent") is False

    @pytest.mark.asyncio
    async def test_has_pending_false_after_consume(self, channel):
        """has_pending should return False after all signals are consumed."""
        channel.send("consume", "data")
        await channel.wait_for("consume", timeout=1.0)
        assert channel.has_pending("consume") is False

    def test_pending_count_zero(self, channel):
        """pending_count should return 0 for unknown signal names."""
        assert channel.pending_count("unknown") == 0

    def test_pending_count_tracks_sends(self, channel):
        """pending_count should track the number of queued signals."""
        channel.send("counted", 1)
        channel.send("counted", 2)
        channel.send("counted", 3)
        assert channel.pending_count("counted") == 3

    @pytest.mark.asyncio
    async def test_pending_count_decreases_on_consume(self, channel):
        """pending_count should decrease as signals are consumed."""
        channel.send("dec", "a")
        channel.send("dec", "b")
        assert channel.pending_count("dec") == 2

        await channel.wait_for("dec", timeout=1.0)
        assert channel.pending_count("dec") == 1

        await channel.wait_for("dec", timeout=1.0)
        assert channel.pending_count("dec") == 0

    def test_signal_names_empty(self, channel):
        """signal_names should be empty initially."""
        assert channel.signal_names == []

    def test_signal_names_tracks_usage(self, channel):
        """signal_names should include all signal names that have been used."""
        channel.send("first", None)
        channel.send("second", None)
        names = channel.signal_names
        assert "first" in names
        assert "second" in names

    @pytest.mark.asyncio
    async def test_concurrent_senders(self, channel):
        """Multiple concurrent senders should all deliver their signals."""
        num_senders = 10

        async def sender(i):
            await asyncio.sleep(0.01 * i)
            channel.send("concurrent", i)

        tasks = [asyncio.create_task(sender(i)) for i in range(num_senders)]

        received = []
        for _ in range(num_senders):
            data = await channel.wait_for("concurrent", timeout=5.0)
            received.append(data)

        await asyncio.gather(*tasks)
        assert sorted(received) == list(range(num_senders))


class TestQueryRegistry:
    """Tests for QueryRegistry."""

    @pytest.fixture
    def registry(self):
        return QueryRegistry()

    @pytest.mark.asyncio
    async def test_register_and_query_sync_handler(self, registry):
        """Sync query handlers should work."""
        registry.register("status", lambda: {"status": "running"})
        result = await registry.query("status")
        assert result == {"status": "running"}

    @pytest.mark.asyncio
    async def test_register_and_query_async_handler(self, registry):
        """Async query handlers should work."""

        async def get_status():
            return {"status": "healthy"}

        registry.register("health", get_status)
        result = await registry.query("health")
        assert result == {"status": "healthy"}

    @pytest.mark.asyncio
    async def test_query_with_kwargs(self, registry):
        """Query kwargs should be passed to the handler."""

        def get_node_output(node_id="default"):
            return {"node_id": node_id, "output": f"result_{node_id}"}

        registry.register("node_output", get_node_output)
        result = await registry.query("node_output", node_id="processor")
        assert result == {"node_id": "processor", "output": "result_processor"}

    @pytest.mark.asyncio
    async def test_query_nonexistent_raises_key_error(self, registry):
        """Querying an unregistered handler should raise KeyError."""
        with pytest.raises(KeyError, match="No handler registered for query 'missing'"):
            await registry.query("missing")

    def test_registered_queries_empty(self, registry):
        """registered_queries should be empty initially."""
        assert registry.registered_queries == []

    def test_registered_queries_lists_all(self, registry):
        """registered_queries should list all registered query names."""
        registry.register("a", lambda: "a")
        registry.register("b", lambda: "b")
        names = registry.registered_queries
        assert "a" in names
        assert "b" in names

    def test_has_handler_true(self, registry):
        """has_handler should return True for registered handlers."""
        registry.register("exists", lambda: True)
        assert registry.has_handler("exists") is True

    def test_has_handler_false(self, registry):
        """has_handler should return False for unregistered handlers."""
        assert registry.has_handler("missing") is False

    def test_unregister(self, registry):
        """unregister should remove the handler."""
        registry.register("temp", lambda: "temp")
        assert registry.has_handler("temp")
        registry.unregister("temp")
        assert not registry.has_handler("temp")

    def test_unregister_nonexistent_raises(self, registry):
        """unregister of nonexistent handler should raise KeyError."""
        with pytest.raises(KeyError):
            registry.unregister("nonexistent")

    @pytest.mark.asyncio
    async def test_register_replaces_existing(self, registry):
        """Registering the same name should replace the previous handler."""
        registry.register("version", lambda: "v1")
        result1 = await registry.query("version")
        assert result1 == "v1"

        registry.register("version", lambda: "v2")
        result2 = await registry.query("version")
        assert result2 == "v2"

    @pytest.mark.asyncio
    async def test_async_handler_with_kwargs(self, registry):
        """Async handlers should receive kwargs."""

        async def search(query="", limit=10):
            return {"query": query, "limit": limit, "results": []}

        registry.register("search", search)
        result = await registry.query("search", query="test", limit=5)
        assert result == {"query": "test", "limit": 5, "results": []}
