"""Tests for DurableRequest._create_workflow.

Verifies that the durable request system correctly parses workflow
configurations from the request body and builds a Workflow via
WorkflowBuilder.
"""

import pytest

from src.kailash.middleware.gateway.durable_request import (
    DurableRequest,
    RequestMetadata,
)


def _make_metadata(body: dict | None = None) -> RequestMetadata:
    """Helper to build a RequestMetadata with the given body."""
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    return RequestMetadata(
        request_id="req_test",
        method="POST",
        path="/api/workflow",
        headers={},
        query_params={},
        body=body,
        client_ip="127.0.0.1",
        user_id=None,
        tenant_id=None,
        idempotency_key=None,
        created_at=now,
        updated_at=now,
    )


class TestCreateWorkflowValidation:
    """Tests for _create_workflow input validation."""

    @pytest.mark.asyncio
    async def test_missing_body_raises(self):
        """Request with no body raises ValueError."""
        meta = _make_metadata(body=None)
        req = DurableRequest(metadata=meta)
        req.state = req.state  # INITIALIZED
        with pytest.raises(ValueError, match="Request body required"):
            await req._create_workflow()

    @pytest.mark.asyncio
    async def test_missing_workflow_key_raises(self):
        """Body without 'workflow' key raises ValueError."""
        meta = _make_metadata(body={"something": "else"})
        req = DurableRequest(metadata=meta)
        with pytest.raises(ValueError, match="'workflow' key"):
            await req._create_workflow()

    @pytest.mark.asyncio
    async def test_empty_nodes_raises(self):
        """Workflow config with empty nodes list raises ValueError."""
        meta = _make_metadata(body={"workflow": {"name": "test", "nodes": []}})
        req = DurableRequest(metadata=meta)
        with pytest.raises(ValueError, match="non-empty 'nodes'"):
            await req._create_workflow()

    @pytest.mark.asyncio
    async def test_node_missing_type_raises(self):
        """Node spec without 'type' raises ValueError."""
        meta = _make_metadata(
            body={
                "workflow": {
                    "name": "test",
                    "nodes": [{"id": "n1"}],
                }
            }
        )
        req = DurableRequest(metadata=meta)
        with pytest.raises(ValueError, match="missing 'type'"):
            await req._create_workflow()

    @pytest.mark.asyncio
    async def test_node_missing_id_raises(self):
        """Node spec without 'id' raises ValueError."""
        meta = _make_metadata(
            body={
                "workflow": {
                    "name": "test",
                    "nodes": [{"type": "PythonCodeNode"}],
                }
            }
        )
        req = DurableRequest(metadata=meta)
        with pytest.raises(ValueError, match="missing 'id'"):
            await req._create_workflow()


class TestCreateWorkflowSuccess:
    """Tests for successful workflow creation."""

    @pytest.mark.asyncio
    async def test_single_node_workflow(self):
        """Workflow with a single valid node builds successfully."""
        meta = _make_metadata(
            body={
                "workflow": {
                    "name": "SingleNode",
                    "nodes": [
                        {
                            "type": "PythonCodeNode",
                            "id": "code1",
                            "params": {"code": "result = 42"},
                        }
                    ],
                }
            }
        )
        req = DurableRequest(metadata=meta)
        await req._create_workflow()

        assert req.workflow is not None
        assert req.workflow_id == f"wf_{req.id}"
        assert "code1" in req.workflow.nodes
        assert req.checkpoint_count >= 1  # at least the workflow_created checkpoint

    @pytest.mark.asyncio
    async def test_invalid_connection_format_raises(self):
        """Connection without dot notation raises ValueError."""
        meta = _make_metadata(
            body={
                "workflow": {
                    "name": "BadConn",
                    "nodes": [
                        {
                            "type": "PythonCodeNode",
                            "id": "a",
                            "params": {"code": "x=1"},
                        },
                        {
                            "type": "PythonCodeNode",
                            "id": "b",
                            "params": {"code": "y=2"},
                        },
                    ],
                    "connections": [{"from": "a", "to": "b"}],
                }
            }
        )
        req = DurableRequest(metadata=meta)
        with pytest.raises(ValueError, match="dot notation"):
            await req._create_workflow()
