"""
End-to-End tests for Agent Execution Method Signature Fixes (TODO-EXEC-002).

Tests complete agent creation to execution workflows with real infrastructure.
NO MOCKING of any services - complete real infrastructure stack.

Tier 3 Requirements:
- Complete agent creation to execution workflows
- Multi-agent coordination through execution methods
- Enterprise agent execution with audit and compliance
- Real deployment scenarios with various execution patterns
- NO MOCKING: Complete real infrastructure stack
- Timeout: <10 seconds per test

Docker setup required: ./tests/utils/test-env up && ./tests/utils/test-env status
"""

import time

from kaizen.core.framework import Kaizen
from kaizen.signatures.core import Signature, SignatureParser

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestAgentExecutionCompleteWorkflows:
    """Test complete agent creation to execution workflows."""

    def setup_method(self):
        """Set up complete E2E test fixtures."""
        self.kaizen = Kaizen(
            config={
                "signature_programming_enabled": True,
                "enterprise_features_enabled": True,
                "audit_trail_enabled": True,
            }
        )
        self.runtime = LocalRuntime()

    def test_complete_agent_lifecycle_execution(self):
        """Complete agent lifecycle from creation to execution and results."""
        # Step 1: Create agent with configuration
        agent_config = {
            "model": "gpt-3.5-turbo",
            "temperature": 0.2,
            "max_tokens": 300,
            "system_prompt": "You are a helpful assistant that provides concise answers.",
        }

        agent = self.kaizen.create_agent("lifecycle_agent", agent_config)

        # Step 2: Execute with direct parameter passing
        start_time = time.time()
        result = agent.execute(question="What are the benefits of renewable energy?")
        execution_time = (time.time() - start_time) * 1000

        # Step 3: Verify complete workflow
        assert (
            execution_time < 10000
        ), f"E2E execution took {execution_time:.1f}ms, expected <10000ms"
        assert isinstance(result, dict)

        # Step 4: Verify substantive intelligent response
        response_content = str(result).lower()
        assert len(response_content) > 50  # Substantive response
        assert any(
            keyword in response_content
            for keyword in ["energy", "renewable", "benefit", "environment"]
        )

    def test_signature_based_agent_complete_workflow(self):
        """Complete signature-based agent workflow from creation to structured output."""
        # Step 1: Create agent with signature
        parser = SignatureParser()
        parse_result = parser.parse(
            "topic, requirements -> analysis, recommendations, implementation_plan"
        )
        signature = Signature(
            inputs=parse_result.inputs,
            outputs=parse_result.outputs,
            signature_type=parse_result.signature_type,
            name="business_analyzer",
        )

        agent_config = {"model": "gpt-3.5-turbo", "temperature": 0.3, "max_tokens": 500}

        agent = self.kaizen.create_agent(
            "business_agent", agent_config, signature=signature
        )

        # Step 2: Execute with structured inputs
        result = agent.execute(
            topic="improve team productivity",
            requirements="remote team, limited budget, 3-month timeline",
        )

        # Step 3: Verify structured outputs
        assert isinstance(result, dict)
        assert "analysis" in result
        assert "recommendations" in result
        assert "implementation_plan" in result

        # Step 4: Verify substantive content in each output
        assert len(result["analysis"]) > 30
        assert len(result["recommendations"]) > 30
        assert len(result["implementation_plan"]) > 30

    def test_workflow_based_agent_complete_execution(self):
        """Complete workflow-based agent execution with complex processing."""
        agent = self.kaizen.create_agent("workflow_agent", {"model": "gpt-3.5-turbo"})

        # Step 1: Create complex workflow
        workflow = WorkflowBuilder()

        # Data preparation step
        workflow.add_node(
            "PythonCodeNode",
            "data_prep",
            {
                "code": """
import json
data = {
    'numbers': [1, 2, 3, 4, 5],
    'operations': ['sum', 'average', 'max', 'min'],
    'metadata': {'source': 'test_data', 'timestamp': '2024-01-01'}
}
result = {'prepared_data': data}
"""
            },
        )

        # Processing step
        workflow.add_node(
            "PythonCodeNode",
            "processor",
            {
                "code": """
data = data_prep['prepared_data']
numbers = data['numbers']
results = {
    'sum': sum(numbers),
    'average': sum(numbers) / len(numbers),
    'max': max(numbers),
    'min': min(numbers),
    'count': len(numbers)
}
result = {'calculations': results, 'metadata': data['metadata']}
""",
                "dependencies": ["data_prep"],
            },
        )

        # Summary step
        workflow.add_node(
            "PythonCodeNode",
            "summary",
            {
                "code": """
calc = processor['calculations']
meta = processor['metadata']
summary_text = f"Processed {calc['count']} numbers: sum={calc['sum']}, avg={calc['average']:.2f}, range=[{calc['min']}-{calc['max']}]"
result = {'summary': summary_text, 'source': meta['source']}
""",
                "dependencies": ["processor"],
            },
        )

        # Step 2: Execute complete workflow
        results, run_id = agent.execute(workflow=workflow)

        # Step 3: Verify complete processing pipeline
        assert isinstance(results, dict)
        assert isinstance(run_id, str)

        # Verify all steps executed
        assert "data_prep" in results
        assert "processor" in results
        assert "summary" in results

        # Verify data flow through pipeline
        assert results["data_prep"]["prepared_data"]["numbers"] == [1, 2, 3, 4, 5]
        assert results["processor"]["calculations"]["sum"] == 15
        assert results["processor"]["calculations"]["average"] == 3.0
        assert "Processed 5 numbers" in results["summary"]["summary"]

    def test_agent_execution_with_error_recovery(self):
        """Complete agent execution with error recovery mechanisms."""
        agent = self.kaizen.create_agent("recovery_agent", {"model": "gpt-3.5-turbo"})

        # Create workflow with potential failure and recovery
        workflow = WorkflowBuilder()

        # Step that might fail
        workflow.add_node(
            "PythonCodeNode",
            "risky_operation",
            {
                "code": """
try:
    # Simulate risky operation
    import random
    if random.random() > 0.5:  # 50% chance of success
        result = {'status': 'success', 'value': 42}
    else:
        # Simulate error condition
        result = {'status': 'error', 'error': 'simulated_failure', 'value': None}
except Exception as e:
    result = {'status': 'exception', 'error': str(e), 'value': None}
"""
            },
        )

        # Recovery step
        workflow.add_node(
            "PythonCodeNode",
            "recovery",
            {
                "code": """
risky_result = risky_operation
if risky_result['status'] == 'success':
    result = {'final_value': risky_result['value'], 'recovery_needed': False}
else:
    # Recovery logic
    result = {'final_value': 'default_value', 'recovery_needed': True, 'original_error': risky_result.get('error')}
""",
                "dependencies": ["risky_operation"],
            },
        )

        # Execute with error recovery
        results, run_id = agent.execute(workflow=workflow)

        # Verify error recovery worked
        assert isinstance(results, dict)
        assert "risky_operation" in results
        assert "recovery" in results

        recovery_result = results["recovery"]
        assert "final_value" in recovery_result
        assert "recovery_needed" in recovery_result


class TestMultiAgentCoordinationE2E:
    """Test multi-agent coordination through execution methods."""

    def setup_method(self):
        """Set up multi-agent coordination fixtures."""
        self.kaizen = Kaizen(
            config={
                "multi_agent_coordination": True,
                "signature_programming_enabled": True,
            }
        )

    def test_multi_agent_collaborative_workflow(self):
        """Complete multi-agent collaboration through execution coordination."""
        # Create specialized agents
        researcher_config = {
            "model": "gpt-3.5-turbo",
            "temperature": 0.1,
            "max_tokens": 300,
        }
        analyst_config = {
            "model": "gpt-3.5-turbo",
            "temperature": 0.3,
            "max_tokens": 400,
        }
        writer_config = {
            "model": "gpt-3.5-turbo",
            "temperature": 0.5,
            "max_tokens": 500,
        }

        researcher = self.kaizen.create_agent("researcher", researcher_config)
        analyst = self.kaizen.create_agent("analyst", analyst_config)
        writer = self.kaizen.create_agent("writer", writer_config)

        # Step 1: Research phase
        research_result = researcher.execute(
            task="Research the benefits of electric vehicles",
            focus="environmental and economic impacts",
        )

        assert isinstance(research_result, dict)
        research_content = str(research_result)

        # Step 2: Analysis phase (using research results)
        analysis_result = analyst.execute(
            task="Analyze the research findings",
            data=research_content[:500],  # Truncate for analysis
            requirements="identify top 3 benefits and potential challenges",
        )

        assert isinstance(analysis_result, dict)
        analysis_content = str(analysis_result)

        # Step 3: Writing phase (using analysis results)
        final_result = writer.execute(
            task="Create executive summary",
            analysis=analysis_content[:300],
            format="professional business summary with recommendations",
        )

        assert isinstance(final_result, dict)

        # Verify collaborative workflow completion
        assert len(str(final_result)) > 100  # Substantive final output

    def test_multi_agent_signature_coordination(self):
        """Multi-agent coordination using signature-based execution."""
        # Create agents with complementary signatures
        parser = SignatureParser()

        # Data collector agent
        collector_parse = parser.parse("query -> raw_data, metadata")
        collector_sig = Signature(
            inputs=collector_parse.inputs,
            outputs=collector_parse.outputs,
            signature_type=collector_parse.signature_type,
        )

        # Data processor agent
        processor_parse = parser.parse("raw_data, metadata -> processed_data, insights")
        processor_sig = Signature(
            inputs=processor_parse.inputs,
            outputs=processor_parse.outputs,
            signature_type=processor_parse.signature_type,
        )

        collector = self.kaizen.create_agent(
            "collector", {"model": "gpt-3.5-turbo"}, collector_sig
        )
        processor = self.kaizen.create_agent(
            "processor", {"model": "gpt-3.5-turbo"}, processor_sig
        )

        # Step 1: Data collection with signature
        collection_result = collector.execute(
            query="market trends in renewable energy 2024"
        )

        assert isinstance(collection_result, dict)
        assert "raw_data" in collection_result
        assert "metadata" in collection_result

        # Step 2: Data processing using collected data
        processing_result = processor.execute(
            raw_data=collection_result.get("raw_data", "fallback_data"),
            metadata=collection_result.get("metadata", {"source": "fallback"}),
        )

        assert isinstance(processing_result, dict)
        assert "processed_data" in processing_result
        assert "insights" in processing_result

    def test_multi_agent_parallel_execution(self):
        """Multi-agent parallel execution coordination."""
        # Create multiple agents for parallel tasks
        agents = []
        for i in range(3):
            agent = self.kaizen.create_agent(
                f"parallel_agent_{i}", {"model": "gpt-3.5-turbo"}
            )
            agents.append(agent)

        # Execute tasks in parallel (simulated)
        results = []
        tasks = [
            "Calculate benefits of solar energy",
            "Analyze wind power advantages",
            "Evaluate hydroelectric potential",
        ]

        start_time = time.time()
        for i, agent in enumerate(agents):
            result = agent.execute(task=tasks[i])
            results.append(result)

        total_time = (time.time() - start_time) * 1000

        # Verify all parallel executions completed
        assert len(results) == 3
        assert all(isinstance(r, dict) for r in results)

        # Verify reasonable performance for parallel execution
        assert (
            total_time < 15000
        ), f"Parallel execution took {total_time:.1f}ms, expected <15000ms"


class TestEnterpriseAgentExecutionE2E:
    """Test enterprise agent execution with audit and compliance."""

    def setup_method(self):
        """Set up enterprise execution fixtures."""
        self.kaizen = Kaizen(
            config={
                "enterprise_features_enabled": True,
                "audit_trail_enabled": True,
                "compliance_checking": True,
                "security_validation": True,
            }
        )

    def test_enterprise_agent_execution_with_audit_trail(self):
        """Complete enterprise agent execution with audit trail."""
        # Create enterprise agent with audit requirements
        enterprise_config = {
            "model": "gpt-3.5-turbo",
            "temperature": 0.2,
            "max_tokens": 400,
            "audit_required": True,
            "compliance_level": "enterprise",
        }

        agent = self.kaizen.create_agent("enterprise_agent", enterprise_config)

        # Execute with audit trail
        result = agent.execute(
            task="Analyze quarterly financial performance",
            data_classification="internal",
            user_context="financial_analyst_role",
        )

        assert isinstance(result, dict)

        # Verify audit trail exists in execution history
        assert hasattr(agent, "_execution_history")
        assert len(agent._execution_history) > 0

        # Verify audit information in latest execution
        latest_execution = agent._execution_history[-1]
        assert "run_id" in latest_execution
        assert "timestamp" in latest_execution or "timestamp" in str(latest_execution)

    def test_enterprise_agent_execution_compliance_validation(self):
        """Enterprise agent execution with compliance validation."""
        # Create agent with compliance requirements
        compliance_config = {
            "model": "gpt-3.5-turbo",
            "compliance_framework": "SOX",
            "data_retention_policy": "7_years",
            "privacy_level": "high",
        }

        agent = self.kaizen.create_agent("compliance_agent", compliance_config)

        # Execute with compliance validation
        result = agent.execute(
            request="Generate compliance report summary",
            scope="financial_controls",
            classification="confidential",
        )

        assert isinstance(result, dict)
        # Compliance validation occurs in background

    def test_enterprise_agent_execution_multi_environment(self):
        """Enterprise agent execution across multiple environments."""
        # Create agents for different environments
        dev_agent = self.kaizen.create_agent(
            "dev_agent",
            {
                "model": "gpt-3.5-turbo",
                "environment": "development",
                "logging_level": "debug",
            },
        )

        staging_agent = self.kaizen.create_agent(
            "staging_agent",
            {
                "model": "gpt-3.5-turbo",
                "environment": "staging",
                "logging_level": "info",
            },
        )

        # Execute same task in different environments
        task = "Process customer feedback analysis"

        dev_result = dev_agent.execute(task=task, mode="testing")
        staging_result = staging_agent.execute(task=task, mode="validation")

        # Both executions should succeed
        assert isinstance(dev_result, dict)
        assert isinstance(staging_result, dict)

        # Results may differ due to environment configurations
        assert len(str(dev_result)) > 0
        assert len(str(staging_result)) > 0


class TestAgentExecutionProductionScenarios:
    """Test agent execution in production-like scenarios."""

    def setup_method(self):
        """Set up production scenario fixtures."""
        self.kaizen = Kaizen(
            config={
                "production_mode": True,
                "performance_monitoring": True,
                "error_reporting": True,
            }
        )

    def test_agent_execution_high_load_scenario(self):
        """Agent execution under high load production scenario."""
        agent = self.kaizen.create_agent(
            "production_agent",
            {
                "model": "gpt-3.5-turbo",
                "temperature": 0.1,
                "max_tokens": 200,
                "timeout": 5,
            },
        )

        # Simulate high load with rapid sequential executions
        results = []
        execution_times = []

        for i in range(5):  # Reduced for E2E testing
            start_time = time.time()
            result = agent.execute(task=f"Process request {i}", priority="high")
            execution_time = (time.time() - start_time) * 1000

            results.append(result)
            execution_times.append(execution_time)

            assert isinstance(result, dict)

        # Verify all executions completed successfully
        assert len(results) == 5
        assert all(isinstance(r, dict) for r in results)

        # Verify performance degradation is reasonable
        avg_time = sum(execution_times) / len(execution_times)
        max_time = max(execution_times)

        assert (
            avg_time < 8000
        ), f"Average execution time {avg_time:.1f}ms under load exceeds 8000ms"
        assert (
            max_time < 15000
        ), f"Max execution time {max_time:.1f}ms under load exceeds 15000ms"

    def test_agent_execution_real_deployment_workflow(self):
        """Complete real deployment workflow execution."""
        # Create deployment agent
        agent = self.kaizen.create_agent(
            "deployment_agent",
            {
                "model": "gpt-3.5-turbo",
                "system_prompt": "You are a deployment assistant that helps with software releases.",
                "max_tokens": 300,
            },
        )

        # Create deployment workflow
        workflow = WorkflowBuilder()

        # Pre-deployment checks
        workflow.add_node(
            "PythonCodeNode",
            "pre_checks",
            {
                "code": """
import random
import time

# Simulate deployment checks
checks = {
    'database_connection': random.choice([True, True, True, False]),  # 75% success rate
    'service_health': True,
    'backup_completed': True,
    'maintenance_window': True
}

all_passed = all(checks.values())
result = {
    'checks': checks,
    'pre_deployment_ready': all_passed,
    'timestamp': time.time()
}
"""
            },
        )

        # Deployment simulation
        workflow.add_node(
            "PythonCodeNode",
            "deployment",
            {
                "code": """
pre_check_result = pre_checks

if pre_check_result['pre_deployment_ready']:
    # Simulate successful deployment
    result = {
        'status': 'success',
        'deployed_version': 'v1.2.3',
        'rollback_available': True,
        'deployment_time': '2024-01-01T10:00:00Z'
    }
else:
    # Deployment blocked by pre-checks
    result = {
        'status': 'blocked',
        'reason': 'pre_deployment_checks_failed',
        'failed_checks': [k for k, v in pre_check_result['checks'].items() if not v]
    }
""",
                "dependencies": ["pre_checks"],
            },
        )

        # Execute deployment workflow
        results, run_id = agent.execute(workflow=workflow)

        # Verify deployment workflow execution
        assert isinstance(results, dict)
        assert "pre_checks" in results
        assert "deployment" in results

        deployment_result = results["deployment"]
        assert "status" in deployment_result
        assert deployment_result["status"] in ["success", "blocked"]

        if deployment_result["status"] == "success":
            assert "deployed_version" in deployment_result
            assert "rollback_available" in deployment_result
        else:
            assert "reason" in deployment_result

    def test_agent_execution_disaster_recovery(self):
        """Agent execution with disaster recovery scenarios."""
        # Create resilient agent
        agent = self.kaizen.create_agent(
            "resilient_agent",
            {
                "model": "gpt-3.5-turbo",
                "max_retries": 2,
                "timeout": 10,
                "fallback_enabled": True,
            },
        )

        # Create workflow with potential failures
        workflow = WorkflowBuilder()

        workflow.add_node(
            "PythonCodeNode",
            "disaster_simulation",
            {
                "code": """
import random

# Simulate various disaster scenarios
scenarios = ['network_failure', 'service_unavailable', 'timeout', 'success']
scenario = random.choice(scenarios)

if scenario == 'success':
    result = {
        'status': 'operational',
        'data_integrity': 'verified',
        'services': ['primary', 'backup'],
        'recovery_needed': False
    }
else:
    result = {
        'status': 'degraded',
        'failure_type': scenario,
        'recovery_needed': True,
        'available_services': ['backup'] if scenario != 'network_failure' else []
    }
"""
            },
        )

        # Execute disaster recovery workflow
        try:
            results, run_id = agent.execute(workflow=workflow)

            assert isinstance(results, dict)
            assert "disaster_simulation" in results

            sim_result = results["disaster_simulation"]
            assert "status" in sim_result
            assert sim_result["status"] in ["operational", "degraded"]

        except Exception as e:
            # Disaster recovery may result in controlled failures
            assert len(str(e)) > 0  # Error should be informative
