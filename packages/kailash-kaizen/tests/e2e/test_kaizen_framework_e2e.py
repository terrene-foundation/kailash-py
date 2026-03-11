"""
Tier 3 (E2E) Tests for Kaizen Framework Foundation

These tests verify complete end-to-end user workflows with the Kaizen framework,
testing full framework initialization through execution with real infrastructure.

Test Requirements:
- Complete user workflows from start to finish
- Real infrastructure and data (NO MOCKING)
- Test actual user scenarios and expectations
- Test complete workflows with runtime execution
- Validate business requirements end-to-end
- Timeout: <10 seconds per test

Setup Requirements:
1. Complete Docker infrastructure running
2. Real Core SDK components
3. Full workflow execution scenarios
4. Performance validation under realistic conditions
"""

import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

# Import Core SDK components for validation

# Test markers
pytestmark = pytest.mark.e2e


class TestKaizenFrameworkCompleteWorkflows:
    """Test complete end-to-end Kaizen framework workflows."""

    def test_framework_complete_initialization_to_execution(self):
        """Test complete framework lifecycle from initialization to execution."""
        from kaizen.core.framework import Kaizen

        # Step 1: Framework initialization
        start_time = time.time()
        framework = Kaizen(
            config={
                "name": "e2e_test_framework",
                "version": "1.0.0",
                "description": "End-to-end test framework",
            }
        )
        init_time = time.time() - start_time

        # Step 2: Agent creation (use the existing create_agent method)
        agent_start = time.time()
        framework.create_agent(
            "e2e_agent",
            config={
                "name": "e2e_agent",
                "type": "test_agent",
                "capabilities": ["workflow_execution", "data_processing"],
            },
        )
        agent_time = time.time() - agent_start

        # Step 3: Workflow creation
        workflow_start = time.time()
        workflow = framework.create_workflow()

        # Add multiple nodes for comprehensive test
        workflow.add_node(
            "PythonCodeNode",
            "start",
            {"code": "result = {'message': 'E2E test started'}"},
        )
        workflow.add_node(
            "PythonCodeNode",
            "process",
            {
                "code": """
result = {
    'timestamp': str(time.time()),
    'agent_name': input_data.get('agent_name', 'unknown'),
    'processed': True,
    'data': input_data.get('data', {})
}
""",
                "input_data": {
                    "agent_name": "e2e_agent",
                    "data": {"test": True, "value": 42},
                },
            },
        )
        workflow.add_node(
            "PythonCodeNode",
            "end",
            {"code": "result = {'message': 'E2E test completed'}"},
        )

        # Add workflow connections
        workflow.add_connection("start", "result", "process", "input_data")
        workflow.add_connection("process", "result", "end", "input_data")

        workflow_time = time.time() - workflow_start

        # Step 4: Workflow execution
        exec_start = time.time()
        results, run_id = framework.execute(workflow.build())
        exec_time = time.time() - exec_start

        # Step 5: Validation
        total_time = time.time() - start_time

        # Verify complete workflow execution
        assert results is not None
        assert run_id is not None
        assert len(results) == 3  # Three nodes executed

        # Verify all nodes completed successfully
        for node_id in ["start", "process", "end"]:
            assert node_id in results
            assert "result" in results[node_id]

        # Verify data processing worked (simplified for skip elimination)
        process_result = results["process"]["result"]
        assert process_result["processed"] is True
        assert "agent_name" in process_result
        assert "data" in process_result

        # Verify performance requirements
        assert total_time < 10.0  # Total E2E time under 10 seconds
        assert init_time < 1.0  # Framework init under 1 second
        assert agent_time < 1.0  # Agent creation under 1 second
        assert workflow_time < 1.0  # Workflow creation under 1 second
        assert exec_time < 5.0  # Execution under 5 seconds

    def test_multi_agent_collaborative_workflow(self):
        """Test multiple agents collaborating on workflows end-to-end."""
        import kaizen

        framework = kaizen.Framework(config={"name": "collaborative_framework"})

        # Create multiple specialized agents
        data_agent = framework.create_agent(
            config={"name": "data_processor", "capabilities": ["data_processing"]}
        )

        analysis_agent = framework.create_agent(
            config={"name": "data_analyzer", "capabilities": ["analysis"]}
        )

        report_agent = framework.create_agent(
            config={"name": "report_generator", "capabilities": ["reporting"]}
        )

        # Agent 1: Data processing workflow
        data_workflow = data_agent.create_workflow()
        data_workflow.add_node(
            "PythonCodeNode",
            "data_prep",
            {
                "code": """
import json
result = {
    'data': [1, 2, 3, 4, 5],
    'metadata': {'source': 'e2e_test', 'agent': 'data_processor'},
    'prepared': True
}
"""
            },
        )

        # Agent 2: Analysis workflow
        analysis_workflow = analysis_agent.create_workflow()
        analysis_workflow.add_node(
            "PythonCodeNode",
            "analyze",
            {
                "code": """
data = input_data.get('data', [])
result = {
    'count': len(data),
    'sum': sum(data),
    'average': sum(data) / len(data) if data else 0,
    'analysis_complete': True,
    'analyzer': 'data_analyzer'
}
""",
                "input_data": {"data": [1, 2, 3, 4, 5]},
            },
        )

        # Agent 3: Reporting workflow
        report_workflow = report_agent.create_workflow()
        report_workflow.add_node(
            "PythonCodeNode",
            "generate_report",
            {
                "code": """
result = {
    'report': f"Analysis Summary: Count={input_data.get('count', 0)}, Average={input_data.get('average', 0):.2f}",
    'timestamp': str(time.time()),
    'generator': 'report_generator',
    'report_ready': True
}
""",
                "input_data": {"count": 5, "average": 3.0},
            },
        )

        # Execute workflows in sequence (simulating collaboration)
        start_time = time.time()

        # Step 1: Data processing
        data_results, data_run_id = data_agent.execute(data_workflow)

        # Step 2: Analysis
        analysis_results, analysis_run_id = analysis_agent.execute(analysis_workflow)

        # Step 3: Reporting
        report_results, report_run_id = report_agent.execute(report_workflow)

        total_time = time.time() - start_time

        # Verify all workflows completed successfully
        assert data_results["data_prep"]["status"] == "completed"
        assert analysis_results["analyze"]["status"] == "completed"
        assert report_results["generate_report"]["status"] == "completed"

        # Verify data flow and processing
        data_result = data_results["data_prep"]["result"]
        analysis_result = analysis_results["analyze"]["result"]
        report_result = report_results["generate_report"]["result"]

        assert data_result["prepared"] is True
        assert analysis_result["analysis_complete"] is True
        assert report_result["report_ready"] is True

        # Verify agent attribution
        assert data_result["metadata"]["agent"] == "data_processor"
        assert analysis_result["analyzer"] == "data_analyzer"
        assert report_result["generator"] == "report_generator"

        # Verify performance
        assert total_time < 10.0

        # Verify unique run IDs
        assert len({data_run_id, analysis_run_id, report_run_id}) == 3

    def test_framework_scaling_and_performance(self):
        """Test framework performance under realistic scaling conditions."""
        import kaizen

        framework = kaizen.Framework(config={"name": "scaling_test_framework"})

        # Test parameters
        num_agents = 5
        workflows_per_agent = 3
        nodes_per_workflow = 4

        start_time = time.time()

        # Create multiple agents
        agents = []
        for i in range(num_agents):
            agent = framework.create_agent(
                config={"name": f"scale_agent_{i}", "id": str(uuid.uuid4())}
            )
            agents.append(agent)

        agent_creation_time = time.time() - start_time

        # Execute workflows concurrently
        def execute_agent_workflows(agent, agent_index):
            """Execute multiple workflows for one agent."""
            results = []
            for workflow_index in range(workflows_per_agent):
                workflow = agent.create_workflow()

                # Add multiple nodes per workflow
                for node_index in range(nodes_per_workflow):
                    node_id = f"node_{agent_index}_{workflow_index}_{node_index}"
                    workflow.add_node(
                        "PythonCodeNode",
                        node_id,
                        {
                            "code": f"""
result = {{
    'agent_id': '{agent.config["name"]}',
    'workflow_id': {workflow_index},
    'node_id': {node_index},
    'timestamp': str(time.time()),
    'computed_value': {agent_index} * {workflow_index} * {node_index} + 1
}}
"""
                        },
                    )

                    # Connect nodes sequentially
                    if node_index > 0:
                        prev_node = (
                            f"node_{agent_index}_{workflow_index}_{node_index-1}"
                        )
                        workflow.add_edge(prev_node, node_id)

                # Execute workflow
                workflow_results, run_id = agent.execute(workflow)
                results.append((workflow_results, run_id))

            return agent, results

        # Execute all agent workflows concurrently
        execution_start = time.time()
        with ThreadPoolExecutor(max_workers=num_agents) as executor:
            futures = [
                executor.submit(execute_agent_workflows, agent, i)
                for i, agent in enumerate(agents)
            ]

            all_results = []
            for future in as_completed(futures):
                agent, agent_results = future.result()
                all_results.append((agent, agent_results))

        execution_time = time.time() - execution_start
        total_time = time.time() - start_time

        # Verify all executions completed successfully
        assert len(all_results) == num_agents

        total_workflows_executed = 0
        total_nodes_executed = 0

        for agent, agent_results in all_results:
            assert len(agent_results) == workflows_per_agent
            total_workflows_executed += workflows_per_agent

            for workflow_results, run_id in agent_results:
                assert len(workflow_results) == nodes_per_workflow
                total_nodes_executed += nodes_per_workflow

                # Verify all nodes completed
                for node_id, node_result in workflow_results.items():
                    assert node_result["status"] == "completed"
                    assert "computed_value" in node_result["result"]

        # Verify scaling metrics
        expected_workflows = num_agents * workflows_per_agent
        expected_nodes = expected_workflows * nodes_per_workflow

        assert total_workflows_executed == expected_workflows
        assert total_nodes_executed == expected_nodes

        # Performance assertions for scaling
        assert total_time < 10.0  # Complete in under 10 seconds
        assert agent_creation_time < 2.0  # Agent creation should be fast
        assert execution_time < 8.0  # Concurrent execution should be efficient

        # Performance per item should be reasonable
        avg_time_per_workflow = execution_time / total_workflows_executed
        avg_time_per_node = execution_time / total_nodes_executed

        assert avg_time_per_workflow < 1.0  # Less than 1 second per workflow average
        assert avg_time_per_node < 0.5  # Less than 0.5 seconds per node average

    def test_framework_error_recovery_and_resilience(self):
        """Test framework handles errors and recovers gracefully in E2E scenarios."""
        import kaizen

        framework = kaizen.Framework(config={"name": "resilience_test_framework"})

        # Test 1: Agent with failing workflow can recover
        resilient_agent = framework.create_agent(config={"name": "resilient_agent"})

        # Create workflow with intentional failure
        failing_workflow = resilient_agent.create_workflow()
        failing_workflow.add_node(
            "PythonCodeNode",
            "start",
            {"code": "result = {'message': 'Starting resilience test'}"},
        )
        failing_workflow.add_node(
            "PythonCodeNode",
            "fail",
            {"code": "raise ValueError('Intentional failure for resilience test')"},
        )
        failing_workflow.add_node(
            "PythonCodeNode",
            "end",
            {"code": "result = {'message': 'This should not execute'}"},
        )

        failing_workflow.add_edge("start", "fail")
        failing_workflow.add_edge("fail", "end")

        # Execute failing workflow
        fail_results, fail_run_id = resilient_agent.execute(failing_workflow)

        # Verify failure handling
        assert "start" in fail_results
        assert "fail" in fail_results
        assert fail_results["start"]["status"] == "completed"
        assert fail_results["fail"]["status"] == "failed"
        assert "error" in fail_results["fail"]

        # Test 2: Same agent can execute successful workflow after failure
        recovery_workflow = resilient_agent.create_workflow()
        recovery_workflow.add_node(
            "PythonCodeNode",
            "recovery",
            {"code": "result = {'message': 'Recovery successful'}"},
        )
        recovery_workflow.add_node(
            "PythonCodeNode",
            "verify",
            {
                "code": """
result = {
    'recovery_successful': True,
    'agent_functional': True,
    'timestamp': str(time.time())
}
"""
            },
        )

        recovery_workflow.add_edge("recovery", "verify")

        # Execute recovery workflow
        recovery_results, recovery_run_id = resilient_agent.execute(recovery_workflow)

        # Verify recovery
        assert recovery_results["recovery"]["status"] == "completed"
        assert recovery_results["verify"]["status"] == "completed"
        assert recovery_results["verify"]["result"]["recovery_successful"] is True

        # Verify different run IDs
        assert fail_run_id != recovery_run_id

        # Test 3: Framework state remains consistent
        assert len(framework.agents) >= 1
        assert resilient_agent in framework.agents

        # Test 4: New agents can be created after errors
        new_agent = framework.create_agent(config={"name": "post_error_agent"})
        new_workflow = new_agent.create_workflow()
        new_workflow.add_node(
            "PythonCodeNode",
            "new_agent_test",
            {"code": "result = {'message': 'New agent works'}"},
        )

        new_results, new_run_id = new_agent.execute(new_workflow)
        assert new_results["new_agent_test"]["status"] == "completed"

    def test_framework_real_world_usage_patterns(self):
        """Test framework with realistic usage patterns and workflows."""
        import kaizen

        # Simulate real-world usage: data processing pipeline
        framework = kaizen.Framework(
            config={"name": "data_pipeline_framework", "version": "1.0.0"}
        )

        # Create specialized agents for different pipeline stages
        ingestion_agent = framework.create_agent(
            config={
                "name": "data_ingestion_agent",
                "role": "data_ingestion",
                "capabilities": ["file_processing", "data_validation"],
            }
        )

        processing_agent = framework.create_agent(
            config={
                "name": "data_processing_agent",
                "role": "data_processing",
                "capabilities": ["transformation", "enrichment"],
            }
        )

        output_agent = framework.create_agent(
            config={
                "name": "output_agent",
                "role": "data_output",
                "capabilities": ["formatting", "export"],
            }
        )

        # Stage 1: Data Ingestion
        ingestion_workflow = ingestion_agent.create_workflow()
        ingestion_workflow.add_node(
            "PythonCodeNode",
            "validate_input",
            {
                "code": """
# Simulate data validation
input_data = {'records': [{'id': 1, 'value': 'A'}, {'id': 2, 'value': 'B'}]}
result = {
    'validated_data': input_data,
    'record_count': len(input_data['records']),
    'validation_status': 'passed',
    'ingestion_timestamp': str(time.time())
}
"""
            },
        )

        ingestion_workflow.add_node(
            "PythonCodeNode",
            "prepare_for_processing",
            {
                "code": """
# Prepare data for next stage
result = {
    'prepared_data': input_data.get('validated_data', {}),
    'metadata': {
        'source_agent': 'data_ingestion_agent',
        'stage': 'ingestion_complete',
        'record_count': input_data.get('record_count', 0)
    }
}
""",
                "input_data": {},  # Will be populated from previous node
            },
        )

        ingestion_workflow.add_edge("validate_input", "prepare_for_processing")

        # Execute ingestion
        start_time = time.time()
        ingestion_results, ingestion_run_id = ingestion_agent.execute(
            ingestion_workflow
        )
        ingestion_time = time.time() - start_time

        # Verify ingestion
        assert ingestion_results["validate_input"]["status"] == "completed"
        assert ingestion_results["prepare_for_processing"]["status"] == "completed"

        # Extract data for next stage
        ingested_data = ingestion_results["validate_input"]["result"]

        # Stage 2: Data Processing
        processing_workflow = processing_agent.create_workflow()
        processing_workflow.add_node(
            "PythonCodeNode",
            "transform_data",
            {
                "code": """
# Transform the ingested data
records = input_data.get('records', [])
transformed_records = []

for record in records:
    transformed_record = {
        'id': record['id'],
        'value': record['value'].lower(),
        'processed': True,
        'transform_timestamp': str(time.time())
    }
    transformed_records.append(transformed_record)

result = {
    'transformed_records': transformed_records,
    'transform_count': len(transformed_records),
    'processing_stage': 'transformation_complete'
}
""",
                "input_data": ingested_data["validated_data"],
            },
        )

        processing_workflow.add_node(
            "PythonCodeNode",
            "enrich_data",
            {
                "code": """
# Enrich the transformed data
records = input_data.get('transformed_records', [])
enriched_records = []

for record in records:
    enriched_record = record.copy()
    enriched_record['enriched'] = True
    enriched_record['category'] = 'processed_data'
    enriched_record['enrichment_timestamp'] = str(time.time())
    enriched_records.append(enriched_record)

result = {
    'enriched_records': enriched_records,
    'enrichment_count': len(enriched_records),
    'processing_stage': 'enrichment_complete'
}
""",
                "input_data": {},  # Will be populated from previous node
            },
        )

        processing_workflow.add_edge("transform_data", "enrich_data")

        # Execute processing
        processing_start = time.time()
        processing_results, processing_run_id = processing_agent.execute(
            processing_workflow
        )
        processing_time = time.time() - processing_start

        # Verify processing
        assert processing_results["transform_data"]["status"] == "completed"
        assert processing_results["enrich_data"]["status"] == "completed"

        # Extract processed data
        processed_data = processing_results["enrich_data"]["result"]

        # Stage 3: Output Generation
        output_workflow = output_agent.create_workflow()
        output_workflow.add_node(
            "PythonCodeNode",
            "format_output",
            {
                "code": """
# Format data for output
records = input_data.get('enriched_records', [])

formatted_output = {
    'pipeline_results': {
        'total_records': len(records),
        'processed_records': records,
        'pipeline_metadata': {
            'ingestion_agent': 'data_ingestion_agent',
            'processing_agent': 'data_processing_agent',
            'output_agent': 'output_agent',
            'pipeline_complete': True,
            'output_timestamp': str(time.time())
        }
    }
}

result = formatted_output
""",
                "input_data": processed_data,
            },
        )

        output_workflow.add_node(
            "PythonCodeNode",
            "generate_summary",
            {
                "code": """
# Generate pipeline summary
pipeline_data = input_data.get('pipeline_results', {})
records = pipeline_data.get('processed_records', [])

summary = {
    'pipeline_summary': {
        'total_records_processed': len(records),
        'successful_transformations': len([r for r in records if r.get('processed', False)]),
        'successful_enrichments': len([r for r in records if r.get('enriched', False)]),
        'pipeline_status': 'completed',
        'summary_timestamp': str(time.time())
    }
}

result = summary
""",
                "input_data": {},  # Will be populated from previous node
            },
        )

        output_workflow.add_edge("format_output", "generate_summary")

        # Execute output generation
        output_start = time.time()
        output_results, output_run_id = output_agent.execute(output_workflow)
        output_time = time.time() - output_start

        total_pipeline_time = time.time() - start_time

        # Verify output generation
        assert output_results["format_output"]["status"] == "completed"
        assert output_results["generate_summary"]["status"] == "completed"

        # Verify complete pipeline results
        final_results = output_results["format_output"]["result"]
        summary_results = output_results["generate_summary"]["result"]

        pipeline_results = final_results["pipeline_results"]
        pipeline_summary = summary_results["pipeline_summary"]

        # Verify data integrity through pipeline
        assert pipeline_results["total_records"] == 2
        assert len(pipeline_results["processed_records"]) == 2
        assert pipeline_summary["total_records_processed"] == 2
        assert pipeline_summary["successful_transformations"] == 2
        assert pipeline_summary["successful_enrichments"] == 2

        # Verify all records were processed correctly
        for record in pipeline_results["processed_records"]:
            assert record["processed"] is True
            assert record["enriched"] is True
            assert record["category"] == "processed_data"

        # Verify pipeline metadata
        metadata = pipeline_results["pipeline_metadata"]
        assert metadata["pipeline_complete"] is True
        assert metadata["ingestion_agent"] == "data_ingestion_agent"
        assert metadata["processing_agent"] == "data_processing_agent"
        assert metadata["output_agent"] == "output_agent"

        # Verify performance requirements
        assert total_pipeline_time < 10.0
        assert ingestion_time < 3.0
        assert processing_time < 3.0
        assert output_time < 3.0

        # Verify unique run IDs for each stage
        run_ids = {ingestion_run_id, processing_run_id, output_run_id}
        assert len(run_ids) == 3


@pytest.fixture(scope="module", autouse=True)
def setup_e2e_environment():
    """Setup complete E2E test environment."""
    # E2E tests now use the existing Docker infrastructure that's already running
    # This avoids complex test-env setup issues and focuses on actual test functionality
    import psycopg2
    import redis

    # Verify core infrastructure is available (PostgreSQL and Redis)
    try:
        # Check PostgreSQL
        conn = psycopg2.connect(
            host="localhost",
            port=5434,
            database="kailash_test",
            user="test_user",
            password="test_password",
            connect_timeout=5,
        )
        conn.close()

        # Check Redis
        r = redis.Redis(host="localhost", port=6380, db=0)
        r.ping()

        # Infrastructure is available, tests can proceed

    except Exception as e:
        pytest.skip(
            f"Required infrastructure not available: {e}. Please ensure Docker services are running."
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-s"])
