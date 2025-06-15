"""
Middleware Using Workflows and Runtime Properly

This example demonstrates how the refactored middleware now properly delegates
to the SDK's workflow and runtime system instead of reimplementing orchestration.

Key improvements shown:
1. WorkflowBuilder.from_dict() for dynamic workflow creation
2. SDK runtime handling all orchestration
3. TaskManager for execution tracking
4. Integration with SDK event system
5. Proper use of workflow templates
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict

from kailash.middleware import AgentUIMiddleware, create_gateway
from kailash.tracking import TaskManager, TaskStatus
from kailash.workflow.builder import WorkflowBuilder
from kailash.workflow.templates import BusinessWorkflowTemplates

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WorkflowRuntimeDemo:
    """Demonstrates proper SDK workflow and runtime usage in middleware."""

    def __init__(self):
        self.gateway = None
        self.session_id = None

    async def setup(self):
        """Set up middleware with proper SDK integration."""
        logger.info("🚀 Setting up middleware with proper workflow/runtime usage...")

        # Create gateway with refactored middleware using convenience function
        self.gateway = create_gateway(
            title="SDK-Integrated Middleware",
            description="Middleware properly using SDK workflows and runtime",
            enable_auth=True,
            database_url="sqlite+aiosqlite:///demo.db",
        )

        # Create session
        self.session_id = await self.gateway.agent_ui.create_session(
            user_id="demo_user", metadata={"demo": "workflow_runtime"}
        )

        logger.info(f"✅ Created session: {self.session_id}")

    async def demonstrate_workflow_builder_from_dict(self):
        """Show how middleware now uses WorkflowBuilder.from_dict()."""
        print("\n" + "=" * 60)
        print("📋 USING WorkflowBuilder.from_dict()")
        print("=" * 60)

        # Frontend sends this configuration
        workflow_config = {
            "name": "Data Processing Pipeline",
            "description": "Process customer data with validation",
            "nodes": [
                {
                    "id": "reader",
                    "type": "CSVReaderNode",
                    "config": {"file_path": "/data/inputs/customers.csv"},
                },
                {
                    "id": "validator",
                    "type": "DataTransformer",
                    "config": {
                        "transformations": [
                            {"type": "validate", "schema": "customer"},
                            {"type": "filter", "condition": "age >= 18"},
                        ]
                    },
                },
                {
                    "id": "enricher",
                    "type": "DataTransformer",
                    "config": {
                        "transformations": [
                            {
                                "type": "add_field",
                                "field": "processed_at",
                                "value": "now()",
                            },
                            {
                                "type": "add_field",
                                "field": "risk_score",
                                "value": "=calculate_risk(data)",
                            },
                        ]
                    },
                },
                {
                    "id": "writer",
                    "type": "SQLDatabaseNode",
                    "config": {
                        "connection_string": "sqlite:///customers.db",
                        "query": "INSERT INTO processed_customers VALUES (:data)",
                    },
                },
            ],
            "connections": [
                {"from": "reader", "to": "validator"},
                {"from": "validator", "to": "enricher"},
                {"from": "enricher", "to": "writer"},
            ],
        }

        # The middleware now uses WorkflowBuilder.from_dict() internally!
        workflow_id = await self.gateway.agent_ui.create_dynamic_workflow(
            session_id=self.session_id, workflow_config=workflow_config
        )

        print(f"✅ Created workflow using WorkflowBuilder.from_dict(): {workflow_id}")
        print("   - SDK handles node registry lookup")
        print("   - SDK validates connections")
        print("   - SDK manages node instantiation")
        print("   - No manual node creation needed!")

        return workflow_id

    async def demonstrate_sdk_runtime_execution(self, workflow_id: str):
        """Show how middleware delegates to SDK runtime."""
        print("\n" + "=" * 60)
        print("⚙️ SDK RUNTIME HANDLING EXECUTION")
        print("=" * 60)

        # Start execution - middleware delegates to SDK runtime
        execution_id = await self.gateway.agent_ui.execute_workflow(
            session_id=self.session_id,
            workflow_id=workflow_id,
            inputs={"batch_size": 1000},
        )

        print(f"✅ Started execution: {execution_id}")
        print("\n🔄 SDK Runtime is now handling:")
        print("   - Node orchestration and execution order")
        print("   - Error handling and automatic retries")
        print("   - Progress tracking via TaskManager")
        print("   - Resource management and parallelization")
        print("   - Cycle detection (if enabled)")

        # Wait for execution
        await asyncio.sleep(3)

        # Get status - this comes from SDK's TaskManager
        status = await self.gateway.agent_ui.get_execution_status(
            execution_id, self.session_id
        )

        if status:
            print("\n📊 Execution Status from SDK TaskManager:")
            print(f"   - Status: {status['status']}")
            print(f"   - Progress: {status.get('progress', 0):.1f}%")

        return execution_id

    async def demonstrate_task_manager_integration(self):
        """Show how TaskManager tracks execution progress."""
        print("\n" + "=" * 60)
        print("📊 TASKMANAGER INTEGRATION")
        print("=" * 60)

        # Create a simple workflow
        builder = WorkflowBuilder()

        # Add nodes
        node1 = builder.add_node(
            "PythonCodeNode",
            node_id="step1",
            config={
                "name": "step1",
                "code": "import time; time.sleep(1); result = {'step': 1}",
            },
        )

        node2 = builder.add_node(
            "PythonCodeNode",
            node_id="step2",
            config={
                "name": "step2",
                "code": "import time; time.sleep(1); result = {'step': 2}",
            },
        )

        node3 = builder.add_node(
            "PythonCodeNode",
            node_id="step3",
            config={
                "name": "step3",
                "code": "import time; time.sleep(1); result = {'step': 3}",
            },
        )

        # Connect them
        builder.add_connection(node1, "result", node2, "input")
        builder.add_connection(node2, "result", node3, "input")

        # Register workflow
        workflow_id = "task_manager_demo"
        await self.gateway.agent_ui.register_workflow(
            workflow_id, builder, self.session_id
        )

        # Subscribe to events to see TaskManager in action
        events_received = []

        def event_handler(event):
            events_received.append(event)
            event_type = (
                event.type.value if hasattr(event.type, "value") else str(event.type)
            )
            logger.info(f"📢 Event: {event_type}")

        await self.gateway.agent_ui.subscribe_to_events(
            "demo_subscriber", event_handler, session_id=self.session_id
        )

        # Execute and watch TaskManager events
        execution_id = await self.gateway.agent_ui.execute_workflow(
            session_id=self.session_id, workflow_id=workflow_id
        )

        print(f"✅ Executing workflow with TaskManager tracking: {execution_id}")
        print("\n⏱️ TaskManager is tracking:")

        # Poll for progress
        for i in range(5):
            await asyncio.sleep(1)
            status = await self.gateway.agent_ui.get_execution_status(
                execution_id, self.session_id
            )
            if status:
                print(
                    f"   Progress: {status.get('progress', 0):.0f}% - {status['status']}"
                )
                if status["status"] in ["completed", "failed"]:
                    break

        print(f"\n📊 Total events from TaskManager: {len(events_received)}")

    async def demonstrate_workflow_templates(self):
        """Show how to use SDK workflow templates."""
        print("\n" + "=" * 60)
        print("📐 USING SDK WORKFLOW TEMPLATES")
        print("=" * 60)

        # Use BusinessWorkflowTemplates from SDK
        templates = BusinessWorkflowTemplates()

        # Create a data pipeline workflow from template
        pipeline_workflow = templates.create_data_pipeline(
            source_type="csv",
            source_config={"file_path": "/data/sales.csv"},
            transformations=[
                {"type": "filter", "condition": "amount > 100"},
                {
                    "type": "aggregate",
                    "group_by": "region",
                    "operations": ["sum", "avg"],
                },
            ],
            destination_type="database",
            destination_config={
                "connection_string": "postgresql://localhost/analytics",
                "table": "sales_summary",
            },
        )

        # Register the template-based workflow
        await self.gateway.agent_ui.register_workflow(
            "sales_pipeline", pipeline_workflow, self.session_id
        )

        print("✅ Created workflow from SDK template:")
        print("   - Data pipeline with source → transform → destination")
        print("   - Template handles node creation and connections")
        print("   - Follows SDK best practices")

        # Execute template-based workflow
        execution_id = await self.gateway.agent_ui.execute_workflow(
            session_id=self.session_id,
            workflow_id="sales_pipeline",
            inputs={"date_range": "2024-01"},
        )

        print(f"✅ Executing template workflow: {execution_id}")

    async def demonstrate_runtime_features(self):
        """Show advanced runtime features being used."""
        print("\n" + "=" * 60)
        print("🚀 ADVANCED RUNTIME FEATURES")
        print("=" * 60)

        # Create workflow with cycles (SDK runtime handles this!)
        cycle_config = {
            "name": "Iterative Optimizer",
            "nodes": [
                {
                    "id": "optimizer",
                    "type": "PythonCodeNode",
                    "config": {
                        "code": """
# Optimization iteration
current_value = input_data.get('value', 100)
iteration = input_data.get('iteration', 0)
improved_value = current_value * 0.9  # Simulate optimization
result = {
    'value': improved_value,
    'iteration': iteration + 1,
    'converged': improved_value < 10
}
"""
                    },
                },
                {
                    "id": "checker",
                    "type": "SwitchNode",
                    "config": {"condition_field": "converged"},
                },
                {
                    "id": "complete",
                    "type": "PythonCodeNode",
                    "config": {
                        "code": "result = {'final_value': input_data['value'], 'iterations': input_data['iteration']}"
                    },
                },
            ],
            "connections": [
                {"from": "optimizer", "to": "checker"},
                {"from": "checker", "to": "complete", "condition": "true"},
                {"from": "checker", "to": "optimizer", "condition": "false"},  # CYCLE!
            ],
        }

        # Register workflow with cycles
        workflow_id = await self.gateway.agent_ui.create_dynamic_workflow(
            session_id=self.session_id, workflow_config=cycle_config
        )

        print("✅ Created workflow with cycles")
        print("   - SDK runtime detects and handles cycles")
        print("   - Automatic loop prevention")
        print("   - Convergence checking")

        # Execute with runtime config overrides
        execution_id = await self.gateway.agent_ui.execute_workflow(
            session_id=self.session_id,
            workflow_id=workflow_id,
            inputs={"value": 1000},
            config_overrides={
                "enable_cycles": True,
                "max_iterations": 20,
                "enable_monitoring": True,
            },
        )

        print(f"✅ Executing cyclic workflow: {execution_id}")
        print("   - Runtime handles cycle detection")
        print("   - Enforces max iterations")
        print("   - Monitors performance")

    async def show_before_after_comparison(self):
        """Show how middleware execution has improved."""
        print("\n" + "=" * 60)
        print("📊 BEFORE vs AFTER: Middleware Execution")
        print("=" * 60)

        print("\n❌ BEFORE (Manual Orchestration):")
        print(
            """
# Old agent_ui.py execution
async def _execute_workflow_async(self, execution_id: str):
    # Manually track execution
    results = await asyncio.to_thread(
        self.runtime.execute, workflow, parameters=inputs
    )

    # Manual progress updates
    await self.event_stream.emit_workflow_progress(
        workflow_id=workflow.workflow_id,
        execution_id=execution_id,
        progress_percent=50.0,  # Hardcoded!
        current_node="processing"
    )
"""
        )

        print("\n✅ AFTER (SDK Runtime Delegation):")
        print(
            """
# New agent_ui.py execution
async def _execute_with_sdk_runtime(self, workflow, inputs, task_manager):
    # Create runtime with proper config
    runtime = LocalRuntime(
        enable_monitoring=True,
        enable_cycles=True,
        max_parallel_tasks=10
    , enable_async=True)

    # Delegate everything to SDK runtime!
    results, run_id = await runtime.execute(
        workflow,
        task_manager=task_manager,
        parameters=inputs
    )

    # Runtime handles EVERYTHING:
    # - Orchestration
    # - Progress tracking
    # - Error handling
    # - Resource management
    # - Event emission
"""
        )

        print("\n🎯 KEY IMPROVEMENTS:")
        print("1. No manual orchestration code")
        print("2. Automatic progress tracking via TaskManager")
        print("3. Built-in error handling and retries")
        print("4. Proper resource management")
        print("5. Native cycle handling")
        print("6. Performance monitoring included")

    async def run_complete_demo(self):
        """Run the complete demonstration."""
        print("\n" + "=" * 60)
        print("🌟 MIDDLEWARE WORKFLOW & RUNTIME INTEGRATION DEMO")
        print("=" * 60)

        try:
            await self.setup()

            # Show all improvements
            workflow_id = await self.demonstrate_workflow_builder_from_dict()
            await self.demonstrate_sdk_runtime_execution(workflow_id)
            await self.demonstrate_task_manager_integration()
            await self.demonstrate_workflow_templates()
            await self.demonstrate_runtime_features()
            await self.show_before_after_comparison()

            print("\n" + "=" * 60)
            print("✅ DEMO COMPLETE!")
            print("=" * 60)
            print("\n🎉 The middleware now properly uses:")
            print("   - WorkflowBuilder.from_dict() for dynamic workflows")
            print("   - SDK runtime for all orchestration")
            print("   - TaskManager for execution tracking")
            print("   - SDK event system integration")
            print("   - Workflow templates for common patterns")
            print("\n💡 Result: Simpler code, more features, better reliability!")

        except Exception as e:
            logger.error(f"Demo failed: {e}")
            raise


if __name__ == "__main__":
    demo = WorkflowRuntimeDemo()
    asyncio.run(demo.run_complete_demo())
