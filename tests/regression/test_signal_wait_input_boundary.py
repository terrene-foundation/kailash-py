"""Signal waits validate canonical inputs before consuming real queued messages."""

import asyncio
import logging
from pathlib import Path

import pytest

from kailash.nodes.logic import signal_wait
from kailash.nodes.logic.signal_wait import SignalWaitNode
from kailash.runtime.signals import SignalChannel
from kailash.sdk_exceptions import NodeValidationError

pytestmark = [pytest.mark.regression, pytest.mark.asyncio]


class StrictSignalWait(SignalWaitNode):
    _strict_unknown_params = True

    def __init__(self, queue_label="internal", **kwargs):
        self.queue_label = queue_label
        super().__init__(**kwargs)


def prepared_node(**config):
    node = StrictSignalWait(**config)
    channel = SignalChannel()
    node.set_workflow_context("signal_channel", channel)
    return node, channel


async def test_source_is_pinned():
    root = Path(__file__).resolve().parents[2]
    assert Path(signal_wait.__file__).resolve() == (
        root / "src/kailash/nodes/logic/signal_wait.py"
    )


@pytest.mark.parametrize(
    "invalid",
    [{"unknown_option": True}, {"timeout": "not-a-number"}, {"queue_label": "runtime"}],
)
async def test_invalid_inputs_leave_queued_signal_available(invalid):
    node, channel = prepared_node(signal_name="event", timeout=1.0)
    channel.send("event", {"approval": True})
    with pytest.raises(NodeValidationError):
        await node.execute_async(**invalid)
    assert channel.has_pending("event")
    result = await node.execute_async()
    assert result["signal_data"] == {"approval": True}
    assert result["timed_out"] is False
    assert not channel.has_pending("event")


async def test_schema_coercion_selects_the_string_named_queue():
    node, channel = prepared_node(timeout=1.0)
    channel.send("42", "string queue")
    channel.send(42, "integer queue")
    result = await node.execute_async(signal_name=42, timeout="1.0")
    assert result["signal_name"] == "42"
    assert result["signal_data"] == "string queue"
    assert not channel.has_pending("42")
    assert channel.has_pending(42)


async def test_missing_required_name_does_not_consume_a_signal():
    node, channel = prepared_node(timeout=1.0)
    channel.send("event", "retained")
    with pytest.raises(NodeValidationError):
        await node.execute_async()
    assert channel.has_pending("event")
    assert (await node.execute_async(signal_name="event"))["signal_data"] == "retained"


@pytest.mark.parametrize("invalid_name", [None, False, 0, ""])
async def test_falsey_name_rejection_precedes_string_coercion(invalid_name):
    node, channel = prepared_node(signal_name="configured", timeout=1.0)
    channel.send("configured", "configured value")
    channel.send(invalid_name, "original key")
    if not isinstance(invalid_name, str):
        channel.send(str(invalid_name), "coerced key")
    with pytest.raises(NodeValidationError, match="signal_name is required"):
        await node.execute_async(signal_name=invalid_name)
    assert channel.has_pending("configured")
    assert channel.has_pending(invalid_name)
    assert channel.has_pending(str(invalid_name))


@pytest.mark.parametrize("nested", [False, True])
async def test_constructor_defaults_and_runtime_override_preserve_output(nested):
    defaults = {"signal_name": "default", "timeout": 1.0, "input_data": "default"}
    config = {"config": defaults} if nested else defaults
    node, channel = prepared_node(queue_label="constructor only", **config)
    assert node.config["queue_label"] == "constructor only"
    channel.send("default", "untouched")
    channel.send("runtime", {"approved": True})
    result = await node.execute_async(signal_name="runtime", input_data={"value": 23})
    assert result == {
        "signal_name": "runtime",
        "signal_data": {"approved": True},
        "input_data": {"value": 23},
        "timed_out": False,
    }
    assert channel.has_pending("default")
    assert node.queue_label == "constructor only"


async def test_default_unknown_parameter_warning_is_retained(caplog):
    # DataFlow deliberately raises this process-global logger to ERROR. Scope
    # this emission contract to WARNING and let caplog restore caller settings.
    caplog.set_level(logging.WARNING, logger="kailash.nodes.base")
    node = SignalWaitNode(signal_name="event", timeout=1.0)
    channel = SignalChannel()
    node.set_workflow_context("signal_channel", channel)
    channel.send("event", "received")
    result = await node.execute_async(unknown_option=True)
    assert result["signal_data"] == "received"
    assert len(caplog.records) == 1
    assert "Unknown parameter(s) for SignalWaitNode: ['unknown_option']" in (
        caplog.records[0].getMessage()
    )


async def test_timeout_preserves_typed_result_and_warning(caplog):
    node, channel = prepared_node(signal_name="missing", timeout=0.001)
    result = await node.execute_async(input_data="kept")
    assert result == {
        "signal_data": None,
        "signal_name": "missing",
        "input_data": "kept",
        "timed_out": True,
    }
    assert not channel.has_pending("missing")
    assert len(caplog.records) == 1
    assert "timed out waiting for signal 'missing'" in caplog.records[0].getMessage()


async def test_cancellation_propagates_and_later_signal_remains_deliverable():
    node, channel = prepared_node(signal_name="event")
    waiter = asyncio.create_task(node.execute_async())
    await asyncio.sleep(0)
    assert not waiter.done()
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    channel.send("event", {"after": "cancellation"})
    result = await node.execute_async(timeout=1.0)
    assert result["signal_data"] == {"after": "cancellation"}
    assert result["timed_out"] is False
