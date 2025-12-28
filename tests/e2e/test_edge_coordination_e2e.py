"""End-to-end tests for edge coordination workflows."""

import asyncio
from datetime import datetime

import pytest
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestEdgeCoordinationE2E:
    """E2E tests for edge coordination in real workflows."""

    @pytest.mark.asyncio
    async def test_coordinated_cache_invalidation_workflow(self):
        """Test workflow using coordination for cache invalidation."""
        # Build workflow with coordination
        workflow = WorkflowBuilder(
            edge_config={
                "discovery": {"locations": ["us-east-1", "eu-west-1", "ap-south-1"]}
            }
        )

        # Add coordination node for leader election
        workflow.add_node(
            "EdgeCoordinationNode",
            "coordinator",
            {
                "operation": "elect_leader",
                "coordination_group": "cache_cluster",
                "peers": [],  # Single node for simplicity
            },
        )

        # Get current leader
        workflow.add_node(
            "EdgeCoordinationNode",
            "get_leader",
            {"operation": "get_leader", "coordination_group": "cache_cluster"},
        )

        # Execute workflow
        runtime = LocalRuntime()
        results, run_id = await runtime.execute_async(workflow.build())

        # Verify coordination worked
        assert results["coordinator"]["success"] is True
        # In single-node setup, should elect self as leader
        assert results["coordinator"]["leader"] is not None

        assert results["get_leader"]["success"] is True
        assert results["get_leader"]["leader"] is not None

    @pytest.mark.asyncio
    async def test_distributed_rate_limiting_workflow(self):
        """Test global rate limiting using edge coordination."""
        workflow = WorkflowBuilder(
            edge_config={"discovery": {"locations": ["us-east-1", "eu-west-1"]}}
        )

        # Global rate limit configuration
        workflow.add_node(
            "EdgeCoordinationNode",
            "rate_limit_config",
            {
                "operation": "propose",
                "coordination_group": "rate_limiters",
                "proposal": {
                    "action": "set_rate_limit",
                    "api": "/api/v1/generate",
                    "limit": 1000,
                    "window": "1m",
                },
            },
        )

        # Check current usage across edges
        workflow.add_node(
            "PythonCodeNode",
            "aggregate_usage",
            {
                "code": """
# Simulate aggregating usage from all edges
# In PythonCodeNode, parameters are available as individual variables
try:
    us_east_1_usage_val = us_east_1_usage
except NameError:
    us_east_1_usage_val = 0

try:
    eu_west_1_usage_val = eu_west_1_usage
except NameError:
    eu_west_1_usage_val = 0

try:
    limit_val = limit
except NameError:
    limit_val = 1000

total_usage = us_east_1_usage_val + eu_west_1_usage_val

result = {
    'total_usage': total_usage,
    'limit': limit_val,
    'remaining': max(0, limit_val - total_usage)
}
"""
            },
        )

        # Coordinate rate limit decision
        workflow.add_node(
            "EdgeCoordinationNode",
            "coordinate_decision",
            {"operation": "global_order", "coordination_group": "rate_limiters"},
        )

        # Connect nodes - EdgeCoordinationNode outputs 'success', not 'accepted'
        workflow.add_connection(
            "rate_limit_config", "success", "aggregate_usage", "config"
        )
        workflow.add_connection(
            "aggregate_usage", "result", "coordinate_decision", "events"
        )

        # Execute
        runtime = LocalRuntime()
        results, run_id = await runtime.execute_async(
            workflow.build(),
            parameters={
                "aggregate_usage": {
                    "us_east_1_usage": 400,
                    "eu_west_1_usage": 300,
                    "limit": 1000,
                }
            },
        )

        # Verify rate limiting coordination
        assert results["rate_limit_config"]["success"] is True
        assert results["aggregate_usage"]["total_usage"] == 700
        assert results["aggregate_usage"]["remaining"] == 300

    @pytest.mark.asyncio
    async def test_coordinated_deployment_workflow(self):
        """Test coordinated deployment across multiple edges."""
        workflow = WorkflowBuilder(
            edge_config={
                "discovery": {
                    "locations": ["us-east-1", "us-west-2", "eu-west-1", "ap-south-1"]
                }
            }
        )

        # Elect deployment coordinator
        workflow.add_node(
            "EdgeCoordinationNode",
            "elect_coordinator",
            {"operation": "elect_leader", "coordination_group": "deployment_group"},
        )

        # Create deployment plan
        workflow.add_node(
            "PythonCodeNode",
            "create_plan",
            {
                "code": """
# Create phased deployment plan
deployment_plan = {
    'version': '2.0.0',
    'phases': [
        {'edges': ['us-west-2'], 'percentage': 10},  # Canary
        {'edges': ['us-east-1', 'us-west-2'], 'percentage': 50},  # Partial
        {'edges': ['all'], 'percentage': 100}  # Full
    ],
    'rollback_criteria': {
        'error_rate': 0.05,
        'latency_p99': 100
    }
}

# Get timestamp parameter
try:
    timestamp_val = timestamp
except NameError:
    timestamp_val = 'default_timestamp'

result = {
    'proposal': {
        'action': 'deploy',
        'plan': deployment_plan,
        'timestamp': timestamp_val
    }
}
"""
            },
        )

        # Propose deployment through consensus
        workflow.add_node(
            "EdgeCoordinationNode",
            "propose_deployment",
            {"operation": "propose", "coordination_group": "deployment_group"},
        )

        # Simulate deployment execution
        workflow.add_node(
            "PythonCodeNode",
            "execute_deployment",
            {
                "code": """
# Simulate checking if proposal was accepted
try:
    accepted_val = accepted
except NameError:
    accepted_val = False
if accepted_val:
    result = {
        'status': 'deployment_started',
        'phase': 1,
        'edges': ['us-west-2'],
        'message': 'Canary deployment initiated'
    }
else:
    result = {
        'status': 'deployment_rejected',
        'reason': 'Consensus not reached'
    }
"""
            },
        )

        # Connect workflow - EdgeCoordinationNode outputs 'success', not 'leader' or 'accepted'
        workflow.add_connection(
            "elect_coordinator", "success", "create_plan", "coordinator"
        )
        workflow.add_connection(
            "create_plan", "proposal", "propose_deployment", "proposal"
        )
        workflow.add_connection(
            "propose_deployment", "success", "execute_deployment", "accepted"
        )

        # Execute
        runtime = LocalRuntime()
        results, run_id = await runtime.execute_async(
            workflow.build(),
            parameters={"create_plan": {"timestamp": datetime.now().isoformat()}},
        )

        # Verify coordinated deployment
        assert results["elect_coordinator"]["success"] is True
        assert results["propose_deployment"]["success"] is True

        deployment_status = results["execute_deployment"]
        if deployment_status["status"] == "deployment_started":
            assert deployment_status["phase"] == 1
            assert deployment_status["edges"] == ["us-west-2"]

    @pytest.mark.asyncio
    async def test_distributed_transaction_coordination(self):
        """Test distributed transaction using edge coordination."""
        workflow = WorkflowBuilder(
            edge_config={
                "discovery": {"locations": ["us-east-1", "eu-west-1", "ap-south-1"]}
            }
        )

        # Start distributed transaction
        workflow.add_node(
            "EdgeCoordinationNode",
            "start_transaction",
            {
                "operation": "propose",
                "coordination_group": "transaction_managers",
                "proposal": {
                    "action": "start_transaction",
                    "tx_id": "tx_12345",
                    "participants": ["db_us", "db_eu", "db_ap"],
                },
            },
        )

        # Prepare phase
        workflow.add_node(
            "PythonCodeNode",
            "prepare_transaction",
            {
                "code": """
# Simulate prepare phase
prepare_results = {
    'db_us': {'vote': 'yes', 'locks_acquired': True},
    'db_eu': {'vote': 'yes', 'locks_acquired': True},
    'db_ap': {'vote': 'yes', 'locks_acquired': True}
}

all_prepared = all(r['vote'] == 'yes' for r in prepare_results.values())

result = {
    'prepared': all_prepared,
    'prepare_results': prepare_results,
    'decision': 'commit' if all_prepared else 'abort'
}
"""
            },
        )

        # Coordinate commit decision
        workflow.add_node(
            "EdgeCoordinationNode",
            "coordinate_commit",
            {"operation": "propose", "coordination_group": "transaction_managers"},
        )

        # Global ordering for transaction log
        workflow.add_node(
            "EdgeCoordinationNode",
            "order_transaction",
            {"operation": "global_order", "coordination_group": "transaction_managers"},
        )

        # Connect nodes - EdgeCoordinationNode outputs 'success', not 'accepted'
        workflow.add_connection(
            "start_transaction", "success", "prepare_transaction", "tx_info"
        )
        workflow.add_connection(
            "prepare_transaction", "result", "coordinate_commit", "proposal"
        )
        workflow.add_connection(
            "coordinate_commit", "success", "order_transaction", "events"
        )

        # Execute
        runtime = LocalRuntime()
        results, run_id = await runtime.execute_async(workflow.build())

        # Verify transaction coordination
        assert results["start_transaction"]["success"] is True
        assert results["prepare_transaction"]["prepared"] is True
        assert results["prepare_transaction"]["decision"] == "commit"
        assert results["coordinate_commit"]["success"] is True
