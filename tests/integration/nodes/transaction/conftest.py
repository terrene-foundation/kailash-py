"""Shared fixtures for 2PC and saga integration tests.

Registers real participant nodes that handle prepare/commit/abort operations
so that RegistryNodeExecutor can resolve them. NO MOCKING — these are real
node implementations that track their invocations via shared state.
"""

from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode


@register_node("TestParticipantNode")
class TestParticipantNode(AsyncNode):
    """A real node that handles 2PC participant operations (prepare/commit/abort).

    This is a genuine node registered in the NodeRegistry, not a mock.
    It tracks all invocations in a class-level list for test assertions.
    """

    # Class-level invocation tracking (shared across all instances)
    invocations = []

    def get_parameters(self):
        return {
            "operation": NodeParameter(
                name="operation",
                type=str,
                default="prepare",
                description="2PC operation: prepare, commit, or abort",
            ),
            "transaction_id": NodeParameter(
                name="transaction_id",
                type=str,
                required=False,
                description="Transaction ID",
            ),
        }

    async def async_run(self, **inputs):
        operation = inputs.get("operation", "prepare")
        tx_id = inputs.get("transaction_id", "unknown")

        TestParticipantNode.invocations.append(
            {
                "operation": operation,
                "transaction_id": tx_id,
                "node_name": self.name if hasattr(self, "name") else "unknown",
            }
        )

        if operation == "prepare":
            return {"status": "success", "vote": "prepared", "transaction_id": tx_id}
        elif operation == "commit":
            return {"status": "success", "committed": True, "transaction_id": tx_id}
        elif operation == "abort":
            return {"status": "success", "aborted": True, "transaction_id": tx_id}
        else:
            return {"status": "success", "operation": operation}

    @classmethod
    def reset_invocations(cls):
        cls.invocations.clear()
