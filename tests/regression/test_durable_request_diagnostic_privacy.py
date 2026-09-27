"""Request validation errors retain public detail without automatic disclosure."""

import io
import logging

import pytest

from kailash.middleware.gateway.durable_request import DurableRequest, RequestState
from kailash.sdk_exceptions import WorkflowValidationError


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", ["execute", "resume"])
@pytest.mark.parametrize("invalid", ["params", "node_type"])
async def test_request_error_preserves_state_without_private_diagnostics(
    entry, invalid, caplog
):
    private = "request-person@example.invalid"
    request = DurableRequest()
    node = {"type": "PythonCodeNode", "id": "node", "params": {}}
    if invalid == "params":
        node.update(id=private, params=["invalid"])
    else:
        node["type"] = private
    request.metadata.body = {"workflow": {"nodes": [node]}}
    if entry == "resume":
        await request.checkpoint("before_validation")
    logger_name = "kailash.middleware.gateway.durable_request"
    logger = logging.getLogger(logger_name)
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger.addHandler(handler)
    error_type = ValueError if invalid == "params" else WorkflowValidationError
    try:
        with caplog.at_level(logging.ERROR, logger=logger_name):
            with pytest.raises(error_type) as caught:
                await getattr(request, entry)()
    finally:
        logger.removeHandler(handler)
        handler.close()
    assert request.state is RequestState.FAILED
    assert request.error is caught.value
    assert private in str(caught.value)
    assert request.runtime is None and request._injected_runtime is None
    failures = request.journal.get_events("request_failed")
    expected = 1 if entry == "execute" else 2
    assert len(failures) == expected
    assert all(event["data"]["error"] == str(caught.value) for event in failures)
    assert request.checkpoints[-1].data == {
        "error": str(caught.value),
        "error_type": error_type.__name__,
    }
    records = [record for record in caplog.records if record.name == logger_name]
    assert len(records) == expected
    assert all(record.getMessage() == "Durable request failed" for record in records)
    assert all(record.error_type == error_type.__name__ for record in records)
    assert all(record.error_frames for record in records)
    assert all(record.exc_info is None for record in records)
    assert private not in repr([vars(record) for record in records])
    assert private not in stream.getvalue()
