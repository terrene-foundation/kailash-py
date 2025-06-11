"""
Studio API Examples - Standalone Version with SQLAlchemy

This version demonstrates the API functionality using real database operations
without requiring a running API server.
"""

import os
import sys
from typing import Any

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

# Import data path utilities
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from examples.utils.data_paths import get_output_data_path
from kailash.api.database import (
    CustomNodeRepository,
    ExecutionRepository,
    WorkflowRepository,
    get_db_session,
    init_database,
)


class StandaloneWorkflowStudioAPI:
    """Standalone implementation of Workflow Studio API using real database"""

    def __init__(self, tenant_id: str = "default", db_path: str = None):
        self.tenant_id = tenant_id
        # Initialize database in centralized location
        if db_path is None:
            db_path = str(
                get_output_data_path("demo_studio.db", subdirectory="databases")
            )
        self.SessionLocal, self.engine = init_database(db_path)
        self.db_path = db_path  # Store for cleanup
        self._cleanup_existing_data()

    def _cleanup_existing_data(self):
        """Clean up any existing data for fresh start"""
        with get_db_session(self.SessionLocal) as session:
            # Clear existing data for this tenant
            from kailash.api.database import CustomNode as CustomNodeModel
            from kailash.api.database import Workflow as WorkflowModel

            session.query(WorkflowModel).filter_by(tenant_id=self.tenant_id).delete()
            session.query(CustomNodeModel).filter_by(tenant_id=self.tenant_id).delete()
            session.commit()

    def create_workflow(
        self, name: str, description: str, definition: dict[str, Any]
    ) -> dict[str, Any]:
        """Create a workflow"""
        with get_db_session(self.SessionLocal) as session:
            repo = WorkflowRepository(session)
            workflow = repo.create(
                tenant_id=self.tenant_id,
                name=name,
                description=description,
                definition=definition,
                created_by="demo@example.com",
            )
            return {
                "id": workflow.id,
                "tenant_id": workflow.tenant_id,
                "name": workflow.name,
                "description": workflow.description,
                "definition": workflow.definition,
                "created_at": workflow.created_at.isoformat(),
                "updated_at": workflow.updated_at.isoformat(),
            }

    def list_workflows(self) -> list[dict[str, Any]]:
        """List workflows for tenant"""
        with get_db_session(self.SessionLocal) as session:
            repo = WorkflowRepository(session)
            workflows = repo.list(self.tenant_id)
            return [
                {
                    "id": wf.id,
                    "name": wf.name,
                    "description": wf.description,
                    "created_at": wf.created_at.isoformat(),
                }
                for wf in workflows
            ]

    def create_custom_node(self, node_data: dict[str, Any]) -> dict[str, Any]:
        """Create a custom node"""
        with get_db_session(self.SessionLocal) as session:
            repo = CustomNodeRepository(session)
            node = repo.create(self.tenant_id, node_data)
            return {
                "id": node.id,
                "tenant_id": node.tenant_id,
                "name": node.name,
                "category": node.category,
                "description": node.description,
                "implementation_type": node.implementation_type,
                "parameters": node.parameters or [],
                "created_at": node.created_at.isoformat(),
            }

    def execute_workflow(
        self, workflow_id: str, parameters: dict[str, Any] = None
    ) -> dict[str, Any]:
        """Execute a workflow"""
        with get_db_session(self.SessionLocal) as session:
            execution_repo = ExecutionRepository(session)

            # Create execution record
            execution = execution_repo.create(
                workflow_id=workflow_id, tenant_id=self.tenant_id, parameters=parameters
            )

            # Simulate execution completion
            execution_repo.update_status(
                execution.id,
                status="completed",
                result={
                    "message": "Execution completed successfully",
                    "rows_processed": 100,
                },
            )

            # Retrieve updated execution
            execution = execution_repo.get(execution.id)

            return {
                "id": execution.id,
                "workflow_id": execution.workflow_id,
                "status": execution.status,
                "parameters": execution.parameters,
                "started_at": (
                    execution.started_at.isoformat() if execution.started_at else None
                ),
                "completed_at": (
                    execution.completed_at.isoformat()
                    if execution.completed_at
                    else None
                ),
                "result": execution.result,
            }


# Example 1: Basic Workflow Creation and Execution
def example_basic_workflow():
    """Create and execute a simple workflow"""
    print("=== Example 1: Basic Workflow ===")

    api = StandaloneWorkflowStudioAPI(tenant_id="demo")

    # Create workflow
    workflow = api.create_workflow(
        name="Data Processing Pipeline",
        description="Process CSV data through multiple stages",
        definition={
            "nodes": [
                {
                    "id": "reader",
                    "type": "CSVReaderNode",
                    "config": {"file_path": "input.csv"},
                },
                {
                    "id": "filter",
                    "type": "FilterNode",
                    "config": {"expression": "age > 25"},
                },
                {
                    "id": "writer",
                    "type": "CSVWriterNode",
                    "config": {"file_path": "output.csv"},
                },
            ],
            "connections": [
                {"from": "reader", "to": "filter"},
                {"from": "filter", "to": "writer"},
            ],
        },
    )
    print(f"Created workflow: {workflow['name']} (ID: {workflow['id']})")

    # Execute workflow
    execution = api.execute_workflow(workflow["id"], parameters={"debug": True})
    print(f"Execution completed: {execution['status']}")
    print(f"Result: {execution['result']}")


# Example 2: Custom Node Creation
def example_custom_nodes():
    """Create different types of custom nodes"""
    print("\n=== Example 2: Custom Nodes ===")

    api = StandaloneWorkflowStudioAPI(tenant_id="demo")

    # Python-based node
    python_node = api.create_custom_node(
        {
            "name": "DataValidator",
            "category": "validation",
            "description": "Validates data quality",
            "implementation_type": "python",
            "parameters": [{"name": "strict_mode", "type": "bool", "default": False}],
            "inputs": [{"name": "data", "type": "DataFrame"}],
            "outputs": [{"name": "valid_data", "type": "DataFrame"}],
            "implementation": {"code": "# Validation logic here\nreturn data"},
        }
    )
    print(f"Created Python node: {python_node['name']}")

    # API-based node
    api_node = api.create_custom_node(
        {
            "name": "WeatherAPI",
            "category": "enrichment",
            "description": "Fetch weather data",
            "implementation_type": "api",
            "parameters": [{"name": "api_key", "type": "str", "required": True}],
            "implementation": {
                "base_url": "https://api.weather.com",
                "method": "GET",
                "headers": {"Authorization": "Bearer {{api_key}}"},
            },
        }
    )
    print(f"Created API node: {api_node['name']}")

    # Workflow-based node
    workflow_node = api.create_custom_node(
        {
            "name": "DataPipeline",
            "category": "composite",
            "description": "Composite data processing node",
            "implementation_type": "workflow",
            "implementation": {
                "workflow_definition": {
                    "nodes": [{"id": "n1", "type": "Node1"}],
                    "connections": [],
                }
            },
        }
    )
    print(f"Created Workflow node: {workflow_node['name']}")


# Example 3: Multi-Tenant Isolation
def example_multi_tenant():
    """Demonstrate multi-tenant data isolation"""
    print("\n=== Example 3: Multi-Tenant Isolation ===")

    # Create workflows for different tenants
    tenants = ["company-a", "company-b", "company-c"]

    for tenant in tenants:
        api = StandaloneWorkflowStudioAPI(tenant_id=tenant)

        # Create tenant-specific workflows
        for i in range(2):
            api.create_workflow(
                name=f"{tenant} Workflow {i+1}",
                description=f"Private workflow for {tenant}",
                definition={"nodes": [], "connections": []},
            )

    # Verify isolation
    for tenant in tenants:
        api = StandaloneWorkflowStudioAPI(tenant_id=tenant)
        workflows = api.list_workflows()
        print(f"\n{tenant}: {len(workflows)} workflows")
        for wf in workflows:
            print(f"  - {wf['name']}")


# Example 4: Workflow Templates
def example_templates():
    """Create reusable workflow templates"""
    print("\n=== Example 4: Workflow Templates ===")

    templates = [
        {
            "name": "ETL Template",
            "category": "data_processing",
            "definition": {
                "nodes": [
                    {"id": "extract", "type": "DataExtractorNode"},
                    {"id": "transform", "type": "DataTransformerNode"},
                    {"id": "load", "type": "DataLoaderNode"},
                ],
                "connections": [
                    {"from": "extract", "to": "transform"},
                    {"from": "transform", "to": "load"},
                ],
            },
        },
        {
            "name": "ML Pipeline Template",
            "category": "machine_learning",
            "definition": {
                "nodes": [
                    {"id": "preprocess", "type": "DataPreprocessorNode"},
                    {"id": "train", "type": "ModelTrainerNode"},
                    {"id": "evaluate", "type": "ModelEvaluatorNode"},
                ],
                "connections": [
                    {"from": "preprocess", "to": "train"},
                    {"from": "train", "to": "evaluate"},
                ],
            },
        },
    ]

    api = StandaloneWorkflowStudioAPI(tenant_id="templates")

    for template in templates:
        workflow = api.create_workflow(
            name=template["name"],
            description=f"Template for {template['category']}",
            definition=template["definition"],
        )
        print(f"Created template: {workflow['name']}")


# Example 5: Advanced Features
def example_advanced_features():
    """Demonstrate advanced Studio features"""
    print("\n=== Example 5: Advanced Features ===")

    api = StandaloneWorkflowStudioAPI(tenant_id="advanced")

    # Create a complex workflow with conditional logic
    workflow = api.create_workflow(
        name="Conditional Processing Pipeline",
        description="Workflow with conditional branching",
        definition={
            "nodes": [
                {"id": "input", "type": "InputNode"},
                {
                    "id": "condition",
                    "type": "SwitchNode",
                    "config": {"expression": "data.type"},
                },
                {"id": "process_a", "type": "ProcessorA"},
                {"id": "process_b", "type": "ProcessorB"},
                {"id": "merge", "type": "MergeNode"},
                {"id": "output", "type": "OutputNode"},
            ],
            "connections": [
                {"from": "input", "to": "condition"},
                {"from": "condition", "to": "process_a", "condition": "type_a"},
                {"from": "condition", "to": "process_b", "condition": "type_b"},
                {"from": "process_a", "to": "merge"},
                {"from": "process_b", "to": "merge"},
                {"from": "merge", "to": "output"},
            ],
        },
    )
    print(f"Created conditional workflow: {workflow['name']}")

    # Create a custom node with validation
    validator_node = api.create_custom_node(
        {
            "name": "EmailValidator",
            "category": "validation",
            "description": "Validates email addresses",
            "implementation_type": "python",
            "parameters": [
                {
                    "name": "email_column",
                    "type": "str",
                    "required": True,
                    "validation": {"pattern": "^[a-zA-Z0-9_]+$"},
                },
                {
                    "name": "strict",
                    "type": "bool",
                    "default": True,
                    "description": "Use strict validation rules",
                },
            ],
            "implementation": {
                "code": """
import re
pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$'
if parameters.get('strict', True):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.(com|org|edu|gov)$'
# Validation logic continues...
"""
            },
        }
    )
    print(
        f"Created validator node with parameters: {[p['name'] for p in validator_node['parameters']]}"
    )


def main():
    """Run all examples"""
    print("=== Kailash Workflow Studio API Examples ===\n")

    example_basic_workflow()
    example_custom_nodes()
    example_multi_tenant()
    example_templates()
    example_advanced_features()

    # Get summary from database
    api = StandaloneWorkflowStudioAPI(tenant_id="summary")
    with get_db_session(api.SessionLocal) as session:
        from kailash.api.database import CustomNode as CustomNodeModel
        from kailash.api.database import Workflow as WorkflowModel
        from kailash.api.database import WorkflowExecution as ExecutionModel

        workflow_count = session.query(WorkflowModel).count()
        node_count = session.query(CustomNodeModel).count()
        execution_count = session.query(ExecutionModel).count()

    print("\n=== Summary ===")
    print(f"Total workflows created: {workflow_count}")
    print(f"Total custom nodes created: {node_count}")
    print(f"Total executions: {execution_count}")

    print("\n✅ All examples completed successfully!")
    print("\nThese examples use real SQLAlchemy database operations.")
    print("\nFor API server usage:")
    print("1. Start the API server: python -m kailash.api.studio")
    print("2. Use httpx/requests to interact with REST endpoints")
    print("3. Use websockets for real-time execution monitoring")

    # Cleanup using stored path
    if hasattr(api, "db_path") and os.path.exists(api.db_path):
        os.remove(api.db_path)
        print("\n🧹 Cleaned up demo database")


if __name__ == "__main__":
    main()
