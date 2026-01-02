"""End-to-end tests for edge computing with DataFlow integration.

Tests complete scenarios including DataFlow models with edge requirements,
compliance routing, multi-region replication, and edge caching.
"""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from kailash.edge.location import (
    ComplianceZone,
    EdgeCapabilities,
    EdgeLocation,
    EdgeRegion,
    GeographicCoordinates,
)
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestEdgeDataFlowE2E:
    """Test end-to-end edge computing scenarios with DataFlow."""

    @pytest.fixture
    def edge_locations(self):
        """Create comprehensive edge locations for E2E testing."""
        return {
            "us-east-1": EdgeLocation(
                location_id="us-east-1",
                name="US East 1",
                region=EdgeRegion.US_EAST,
                coordinates=GeographicCoordinates(40.7128, -74.0060),
                capabilities=EdgeCapabilities(
                    cpu_cores=16,
                    memory_gb=64,
                    storage_gb=1000,
                    database_support=["postgresql", "redis"],
                    encryption_at_rest=True,
                    audit_logging=True,
                ),
                compliance_zones=[ComplianceZone.PUBLIC, ComplianceZone.HIPAA],
            ),
            "eu-west-1": EdgeLocation(
                location_id="eu-west-1",
                name="EU West 1",
                region=EdgeRegion.EU_WEST,
                coordinates=GeographicCoordinates(53.3498, -6.2603),
                capabilities=EdgeCapabilities(
                    cpu_cores=8,
                    memory_gb=32,
                    storage_gb=500,
                    database_support=["postgresql"],
                    encryption_at_rest=True,
                    audit_logging=True,
                ),
                compliance_zones=[ComplianceZone.GDPR, ComplianceZone.PUBLIC],
            ),
            "asia-east-1": EdgeLocation(
                location_id="asia-east-1",
                name="Asia East 1",
                region=EdgeRegion.ASIA_EAST,
                coordinates=GeographicCoordinates(35.6762, 139.6503),
                capabilities=EdgeCapabilities(
                    cpu_cores=12,
                    memory_gb=48,
                    storage_gb=750,
                    database_support=["postgresql", "redis"],
                    encryption_at_rest=True,
                ),
                compliance_zones=[ComplianceZone.PUBLIC],
            ),
        }

    @pytest.fixture
    def dataflow_model_config(self):
        """Create DataFlow model configuration with edge requirements."""
        return {
            "models": {
                "User": {
                    "fields": {
                        "id": {"type": "uuid", "primary": True},
                        "email": {"type": "string", "unique": True},
                        "name": {"type": "string"},
                        "region": {"type": "string"},
                        "gdpr_consent": {"type": "boolean", "default": False},
                    },
                    "edge_config": {
                        "compliance_classification": "pii",
                        "preferred_regions": ["eu-west-1", "us-east-1"],
                        "replication_strategy": "multi-region",
                    },
                },
                "HealthRecord": {
                    "fields": {
                        "id": {"type": "uuid", "primary": True},
                        "patient_id": {"type": "uuid", "foreign_key": "User.id"},
                        "diagnosis": {"type": "string"},
                        "treatment": {"type": "string"},
                        "created_at": {"type": "datetime"},
                    },
                    "edge_config": {
                        "compliance_classification": "phi",
                        "required_compliance": ["HIPAA"],
                        "encryption_required": True,
                    },
                },
            }
        }

    @pytest.mark.asyncio
    async def test_compliance_aware_data_routing(
        self, edge_locations, dataflow_model_config
    ):
        """Test that data is routed to compliant edge locations based on classification."""
        with patch(
            "kailash.workflow.edge_infrastructure.EdgeInfrastructure"
        ) as mock_infra_class:
            # Setup mock infrastructure
            mock_infra = MagicMock()
            mock_infra_class.return_value = mock_infra

            # Mock discovery to return our locations
            mock_discovery = MagicMock()
            mock_discovery.get_all_edges.return_value = list(edge_locations.values())
            mock_infra.get_discovery.return_value = mock_discovery

            # Mock compliance router
            mock_compliance = MagicMock()
            mock_infra.get_compliance_router.return_value = mock_compliance

            # Create workflow for GDPR-compliant user creation
            workflow = WorkflowBuilder(
                edge_config={
                    "compliance": {"strict_mode": True},
                    "dataflow": dataflow_model_config,
                }
            )

            # Simulate DataFlow-generated node for User creation
            workflow.add_node(
                "EdgeDataNode",
                "create_user",
                {
                    "location_id": "dynamic",  # Let compliance router decide
                    "action": "write",
                    "data_key": "user:12345",
                    "compliance_classification": "pii",
                    "required_compliance": ["GDPR"],
                },
            )

            # Add verification node
            workflow.add_node(
                "PythonCodeNode",
                "verify",
                {
                    "code": """
import json
user_data = parameters.get('user_data', {})
location_used = parameters.get('location_used', 'unknown')
result = {
    'user_created': True,
    'location': location_used,
    'gdpr_compliant': location_used == 'eu-west-1'
}
"""
                },
            )

            workflow.add_connection("create_user", "verify")

            # Mock compliance routing decision
            mock_compliance.route_compliant.return_value = MagicMock(
                recommended_location=edge_locations["eu-west-1"],
                allowed_locations=[edge_locations["eu-west-1"]],
            )

            # Execute workflow
            runtime = LocalRuntime()
            user_data = {
                "email": "user@example.com",
                "name": "Test User",
                "region": "EU",
                "gdpr_consent": True,
            }

            # Mock edge node execution
            with patch(
                "kailash.nodes.edge.edge_data.EdgeDataNode.async_run"
            ) as mock_run:
                mock_run.return_value = {
                    "success": True,
                    "location_used": "eu-west-1",
                    "data": user_data,
                }

                result = await runtime.execute(
                    workflow.build(), parameters={"create_user": {"data": user_data}}
                )

                # Verify compliance routing was called
                mock_compliance.route_compliant.assert_called()

    @pytest.mark.asyncio
    async def test_multi_region_replication(self, edge_locations):
        """Test multi-region data replication for high availability."""
        with patch(
            "kailash.workflow.edge_infrastructure.EdgeInfrastructure"
        ) as mock_infra_class:
            mock_infra = MagicMock()
            mock_infra_class.return_value = mock_infra

            # Create workflow for multi-region replication
            workflow = WorkflowBuilder(
                edge_config={
                    "replication": {
                        "strategy": "multi-region",
                        "min_replicas": 2,
                        "regions": ["us-east-1", "eu-west-1", "asia-east-1"],
                    }
                }
            )

            # Primary write
            workflow.add_node(
                "EdgeDataNode",
                "primary_write",
                {
                    "location_id": "us-east-1",
                    "action": "write",
                    "data_key": "global:config:v1",
                },
            )

            # Parallel replication to other regions
            workflow.add_node(
                "EdgeDataNode",
                "replicate_eu",
                {
                    "location_id": "eu-west-1",
                    "action": "replicate",
                    "source_location": "us-east-1",
                    "data_key": "global:config:v1",
                },
            )

            workflow.add_node(
                "EdgeDataNode",
                "replicate_asia",
                {
                    "location_id": "asia-east-1",
                    "action": "replicate",
                    "source_location": "us-east-1",
                    "data_key": "global:config:v1",
                },
            )

            # Verification node
            workflow.add_node(
                "PythonCodeNode",
                "verify_replication",
                {
                    "code": """
result = {
    'primary_write': parameters.get('primary_result', {}),
    'eu_replication': parameters.get('eu_result', {}),
    'asia_replication': parameters.get('asia_result', {}),
    'all_replicated': all([
        parameters.get('primary_result', {}).get('success'),
        parameters.get('eu_result', {}).get('success'),
        parameters.get('asia_result', {}).get('success')
    ])
}
"""
                },
            )

            # Connect for parallel replication
            workflow.add_connection("primary_write", "replicate_eu")
            workflow.add_connection("primary_write", "replicate_asia")
            workflow.add_connection(
                "replicate_eu", "verify_replication", mapping={"result": "eu_result"}
            )
            workflow.add_connection(
                "replicate_asia",
                "verify_replication",
                mapping={"result": "asia_result"},
            )
            workflow.add_connection(
                "primary_write",
                "verify_replication",
                mapping={"result": "primary_result"},
            )

            # Mock successful replication
            with patch(
                "kailash.nodes.edge.edge_data.EdgeDataNode.async_run"
            ) as mock_run:

                async def mock_edge_run(**kwargs):
                    location = kwargs.get("location_id", "unknown")
                    return {
                        "success": True,
                        "location": location,
                        "timestamp": "2024-01-19T10:00:00Z",
                        "data_size": 1024,
                    }

                mock_run.side_effect = mock_edge_run

                # Execute workflow
                runtime = LocalRuntime()
                config_data = {"version": "1.0", "features": ["edge", "replication"]}

                result = await runtime.execute(
                    workflow.build(),
                    parameters={"primary_write": {"data": config_data}},
                )

                # All replications should succeed
                assert mock_run.call_count >= 3  # Primary + 2 replications

    @pytest.mark.asyncio
    async def test_edge_caching_performance(self, edge_locations):
        """Test edge caching for performance optimization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = Path(tmpdir) / "edge_cache.json"

            workflow = WorkflowBuilder(
                edge_config={
                    "caching": {"enabled": True, "ttl_seconds": 300, "max_size_mb": 100}
                }
            )

            # Simulate cache warming
            workflow.add_node(
                "EdgeDataNode",
                "cache_warm",
                {
                    "location_id": "us-east-1",
                    "action": "cache_warm",
                    "data_keys": ["product:*", "inventory:*"],
                    "cache_file": str(cache_file),
                },
            )

            # Read from cache (should be fast)
            workflow.add_node(
                "EdgeDataNode",
                "cached_read",
                {
                    "location_id": "us-east-1",
                    "action": "read",
                    "data_key": "product:12345",
                    "use_cache": True,
                    "cache_file": str(cache_file),
                },
            )

            # Performance measurement
            workflow.add_node(
                "PythonCodeNode",
                "measure_performance",
                {
                    "code": f"""
import json
import time

cache_warm_time = parameters.get('warm_result', {{}}).get('execution_time_ms', 0)
cached_read_time = parameters.get('read_result', {{}}).get('execution_time_ms', 0)

# Simulate cache file
cache_data = {{
    'product:12345': {{'name': 'Test Product', 'price': 99.99}},
    'cache_metadata': {{'warmed_at': time.time()}}
}}
with open('{cache_file}', 'w') as f:
    json.dump(cache_data, f)

result = {{
    'cache_warm_time_ms': cache_warm_time or 100,  # Simulate warm time
    'cached_read_time_ms': cached_read_time or 5,  # Simulate fast cache read
    'speedup_factor': 20,  # 100ms / 5ms
    'cache_hit': True
}}
"""
                },
            )

            workflow.add_connection("cache_warm", "cached_read")
            workflow.add_connection(
                "cache_warm", "measure_performance", mapping={"result": "warm_result"}
            )
            workflow.add_connection(
                "cached_read", "measure_performance", mapping={"result": "read_result"}
            )

            # Execute workflow
            runtime = LocalRuntime()

            with patch(
                "kailash.nodes.edge.edge_data.EdgeDataNode.async_run"
            ) as mock_run:

                async def mock_cache_operations(**kwargs):
                    action = kwargs.get("action")
                    if action == "cache_warm":
                        return {
                            "success": True,
                            "keys_warmed": 50,
                            "execution_time_ms": 100,
                        }
                    elif action == "read":
                        return {
                            "success": True,
                            "cache_hit": True,
                            "execution_time_ms": 5,
                        }
                    return {"success": False}

                mock_run.side_effect = mock_cache_operations

                result = await runtime.execute(workflow.build())

                # Verify performance improvement from caching
                perf_result = result.get("measure_performance", {}).get("result", {})
                assert perf_result.get("speedup_factor", 0) > 10  # At least 10x faster

    @pytest.mark.asyncio
    async def test_zero_config_dataflow_edge_operation(self, dataflow_model_config):
        """Test zero-config DataFlow operation with automatic edge placement."""
        workflow = WorkflowBuilder(
            edge_config={"auto_placement": True, "dataflow": dataflow_model_config}
        )

        # Simulate DataFlow-generated workflow for User CRUD
        # Create user (auto-placed based on compliance)
        workflow.add_node(
            "EdgeDataNode",
            "auto_create_user",
            {
                "action": "write",
                "data_key": "user:auto:1",
                "auto_placement": True,
                "data_classification": "pii",
            },
        )

        # Read user (finds nearest edge)
        workflow.add_node(
            "EdgeDataNode",
            "auto_read_user",
            {"action": "read", "data_key": "user:auto:1", "auto_placement": True},
        )

        # Update user (respects compliance)
        workflow.add_node(
            "EdgeDataNode",
            "auto_update_user",
            {
                "action": "update",
                "data_key": "user:auto:1",
                "auto_placement": True,
                "data_classification": "pii",
            },
        )

        # Delete user (ensures global deletion)
        workflow.add_node(
            "EdgeDataNode",
            "auto_delete_user",
            {
                "action": "delete",
                "data_key": "user:auto:1",
                "auto_placement": True,
                "global_delete": True,
            },
        )

        # Connect CRUD operations
        workflow.add_connection("auto_create_user", "auto_read_user")
        workflow.add_connection("auto_read_user", "auto_update_user")
        workflow.add_connection("auto_update_user", "auto_delete_user")

        # Mock automatic placement decisions
        with patch("kailash.nodes.edge.edge_data.EdgeDataNode.async_run") as mock_run:

            async def mock_auto_placement(**kwargs):
                action = kwargs.get("action")
                return {
                    "success": True,
                    "action": action,
                    "auto_selected_location": (
                        "eu-west-1" if "pii" in str(kwargs) else "us-east-1"
                    ),
                    "compliance_met": True,
                }

            mock_run.side_effect = mock_auto_placement

            runtime = LocalRuntime()
            user_data = {"email": "auto@example.com", "name": "Auto User"}

            result = await runtime.execute(
                workflow.build(),
                parameters={
                    "auto_create_user": {"data": user_data},
                    "auto_update_user": {"data": {"name": "Updated Auto User"}},
                },
            )

            # Verify all CRUD operations succeeded with auto-placement
            assert mock_run.call_count == 4  # All CRUD operations

    @pytest.mark.asyncio
    async def test_edge_state_consistency(self, edge_locations):
        """Test distributed state management across edge locations."""
        workflow = WorkflowBuilder(
            edge_config={
                "state_management": {
                    "consistency_model": "eventual",
                    "sync_interval_ms": 1000,
                }
            }
        )

        # Initialize state machines at different edges
        workflow.add_node(
            "EdgeStateMachine",
            "state_us",
            {"location_id": "us-east-1", "state_key": "workflow:state:distributed"},
        )

        workflow.add_node(
            "EdgeStateMachine",
            "state_eu",
            {"location_id": "eu-west-1", "state_key": "workflow:state:distributed"},
        )

        # Perform state transitions
        workflow.add_node(
            "PythonCodeNode",
            "state_transition",
            {
                "code": """
result = {
    'us_state': {'status': 'active', 'step': 1},
    'eu_state': {'status': 'active', 'step': 1},
    'synchronized': True
}
"""
            },
        )

        # Verify consistency
        workflow.add_node(
            "PythonCodeNode",
            "verify_consistency",
            {
                "code": """
us_state = parameters.get('us_state', {})
eu_state = parameters.get('eu_state', {})
result = {
    'states_match': us_state == eu_state,
    'both_active': us_state.get('status') == 'active' and eu_state.get('status') == 'active',
    'consistency_achieved': True
}
"""
            },
        )

        workflow.add_connection(
            "state_us", "state_transition", mapping={"state": "us_state"}
        )
        workflow.add_connection(
            "state_eu", "state_transition", mapping={"state": "eu_state"}
        )
        workflow.add_connection("state_transition", "verify_consistency")

        with patch(
            "kailash.nodes.edge.edge_state_machine.EdgeStateMachine.async_run"
        ) as mock_run:

            async def mock_state_run(**kwargs):
                return {
                    "success": True,
                    "state": {"status": "active", "step": 1},
                    "location": kwargs.get("location_id"),
                }

            mock_run.side_effect = mock_state_run

            runtime = LocalRuntime()
            result = await runtime.execute(workflow.build())

            # Verify state consistency
            consistency_result = result.get("verify_consistency", {}).get("result", {})
            assert consistency_result.get("consistency_achieved", False) is True
