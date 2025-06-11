"""
Comprehensive Kailash Workflow Studio Examples

This file demonstrates all Studio API features:
1. Workflow management (CRUD operations)
2. Custom node creation (Python, Workflow, API types)
3. Workflow execution and monitoring
4. Database operations and queries
5. Multi-tenant isolation
6. Performance analytics

Can be run in two modes:
- Standalone: Uses direct database operations (no server required)
- API Client: Connects to running Studio API server
"""

import asyncio
import json
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

# Import data path utilities
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from sqlalchemy import func

from examples.utils.data_paths import get_output_data_path
from kailash.api.database import CustomNode as CustomNodeModel
from kailash.api.database import (
    CustomNodeRepository,
    ExecutionRepository,
)
from kailash.api.database import Workflow as WorkflowModel
from kailash.api.database import WorkflowExecution as ExecutionModel
from kailash.api.database import (
    WorkflowRepository,
    WorkflowTemplate,
    get_db_session,
    init_database,
)

# ============================================================================
# PART 1: Standalone Database Examples (No Server Required)
# ============================================================================


class StudioDatabaseExamples:
    """Direct database operations for Workflow Studio"""

    def __init__(self, db_path: str = None):
        if db_path is None:
            # Use centralized data structure for database
            db_path = str(
                get_output_data_path("studio_examples.db", subdirectory="databases")
            )
        self.SessionLocal, self.engine = init_database(db_path)
        self.db_path = db_path

    def example_workflow_management(self):
        """Demonstrate workflow CRUD operations"""
        print("\n=== Workflow Management ===")

        with get_db_session(self.SessionLocal) as session:
            repo = WorkflowRepository(session)

            # Create workflow
            workflow = repo.create(
                tenant_id="example-tenant",
                name="Data Processing Pipeline",
                description="ETL pipeline for customer data",
                definition={
                    "nodes": [
                        {
                            "id": "extract",
                            "type": "CSVReaderNode",
                            "config": {"file_path": "data.csv"},
                        },
                        {
                            "id": "transform",
                            "type": "DataTransformerNode",
                            "config": {"operations": ["clean", "normalize"]},
                        },
                        {
                            "id": "load",
                            "type": "CSVWriterNode",
                            "config": {"file_path": "output.csv"},
                        },
                    ],
                    "connections": [
                        {"from": "extract", "to": "transform"},
                        {"from": "transform", "to": "load"},
                    ],
                },
                created_by="admin@example.com",
            )
            print(f"✅ Created workflow: {workflow.name} (ID: {workflow.id})")

            # Update workflow
            updated = repo.update(
                workflow.id,
                {
                    "description": "Enhanced ETL pipeline with validation",
                    "change_message": "Added data validation step",
                },
                updated_by="admin@example.com",
            )
            print(f"✅ Updated workflow: version {updated.version}")

            # List workflows
            workflows = repo.list("example-tenant")
            print(f"✅ Found {len(workflows)} workflows")

            return workflow.id

    def example_custom_nodes(self):
        """Create different types of custom nodes"""
        print("\n=== Custom Node Creation ===")

        with get_db_session(self.SessionLocal) as session:
            repo = CustomNodeRepository(session)

            # 1. Python-based node
            python_node = repo.create(
                tenant_id="example-tenant",
                node_data={
                    "name": "DataValidator",
                    "category": "validation",
                    "description": "Validates data quality and completeness",
                    "icon": "check_circle",
                    "color": "#4CAF50",
                    "parameters": [
                        {"name": "strict_mode", "type": "bool", "default": True},
                        {
                            "name": "rules",
                            "type": "list",
                            "default": ["not_null", "unique"],
                        },
                    ],
                    "inputs": [{"name": "data", "type": "DataFrame", "required": True}],
                    "outputs": [
                        {"name": "valid_data", "type": "DataFrame"},
                        {"name": "validation_report", "type": "Dict"},
                    ],
                    "implementation_type": "python",
                    "implementation": {
                        "code": """
import pandas as pd

# Get parameters
strict_mode = parameters.get('strict_mode', True)
rules = parameters.get('rules', ['not_null'])

# Validation logic
report = {"total_rows": len(data), "errors": []}

if 'not_null' in rules:
    null_counts = data.isnull().sum()
    if null_counts.any():
        report["errors"].append({"type": "null_values", "columns": null_counts[null_counts > 0].to_dict()})

if 'unique' in rules:
    duplicate_count = data.duplicated().sum()
    if duplicate_count > 0:
        report["errors"].append({"type": "duplicates", "count": duplicate_count})

# Filter valid data
if strict_mode and report["errors"]:
    valid_data = pd.DataFrame()  # Empty if errors in strict mode
else:
    valid_data = data.dropna().drop_duplicates()

return {"valid_data": valid_data, "validation_report": report}
"""
                    },
                    "created_by": "admin@example.com",
                },
            )
            print(f"✅ Created Python node: {python_node.name}")

            # 2. API-based node
            api_node = repo.create(
                tenant_id="example-tenant",
                node_data={
                    "name": "GeoEnricher",
                    "category": "enrichment",
                    "description": "Enriches addresses with geocoding data",
                    "icon": "location_on",
                    "color": "#2196F3",
                    "parameters": [
                        {"name": "address_column", "type": "str", "required": True},
                        {
                            "name": "api_key",
                            "type": "str",
                            "required": True,
                            "sensitive": True,
                        },
                    ],
                    "inputs": [{"name": "data", "type": "DataFrame", "required": True}],
                    "outputs": [{"name": "enriched_data", "type": "DataFrame"}],
                    "implementation_type": "api",
                    "implementation": {
                        "base_url": "https://api.geocoding.service/v1",
                        "endpoints": [
                            {
                                "name": "geocode",
                                "path": "/geocode",
                                "method": "GET",
                                "params_template": {
                                    "address": "{{address}}",
                                    "key": "{{api_key}}",
                                },
                                "response_mapping": {
                                    "latitude": "$.results[0].geometry.location.lat",
                                    "longitude": "$.results[0].geometry.location.lng",
                                    "formatted_address": "$.results[0].formatted_address",
                                },
                            }
                        ],
                        "rate_limit": {"requests_per_second": 10},
                    },
                    "created_by": "admin@example.com",
                },
            )
            print(f"✅ Created API node: {api_node.name}")

            # 3. Workflow-based node
            workflow_node = repo.create(
                tenant_id="example-tenant",
                node_data={
                    "name": "DataQualityPipeline",
                    "category": "composite",
                    "description": "Complete data quality check pipeline",
                    "icon": "timeline",
                    "color": "#FF9800",
                    "parameters": [],
                    "inputs": [
                        {"name": "raw_data", "type": "DataFrame", "required": True}
                    ],
                    "outputs": [
                        {"name": "clean_data", "type": "DataFrame"},
                        {"name": "quality_report", "type": "Dict"},
                    ],
                    "implementation_type": "workflow",
                    "implementation": {
                        "workflow_definition": {
                            "nodes": [
                                {
                                    "id": "validate",
                                    "type": "DataValidator",
                                    "config": {"strict_mode": False},
                                },
                                {
                                    "id": "profile",
                                    "type": "DataProfilerNode",
                                    "config": {},
                                },
                                {
                                    "id": "report",
                                    "type": "ReportGeneratorNode",
                                    "config": {"format": "json"},
                                },
                            ],
                            "connections": [
                                {"from": "input", "to": "validate"},
                                {
                                    "from": "validate",
                                    "output": "valid_data",
                                    "to": "profile",
                                },
                                {
                                    "from": "validate",
                                    "output": "validation_report",
                                    "to": "report",
                                    "input": "validation_data",
                                },
                                {
                                    "from": "profile",
                                    "to": "report",
                                    "input": "profile_data",
                                },
                            ],
                        }
                    },
                    "created_by": "admin@example.com",
                },
            )
            print(f"✅ Created Workflow node: {workflow_node.name}")

            # List all custom nodes
            nodes = repo.list("example-tenant")
            print(f"\n📦 Total custom nodes created: {len(nodes)}")
            for node in nodes:
                print(f"   - {node.name} ({node.implementation_type})")

    def example_workflow_execution(self, workflow_id: str):
        """Execute and track workflow performance"""
        print("\n=== Workflow Execution ===")

        with get_db_session(self.SessionLocal) as session:
            exec_repo = ExecutionRepository(session)

            # Execute workflow multiple times
            execution_ids = []
            for i in range(3):
                execution = exec_repo.create(
                    workflow_id=workflow_id,
                    tenant_id="example-tenant",
                    parameters={"batch_size": 1000 * (i + 1)},
                )

                # Simulate execution with varying times
                import time

                time.sleep(0.1)  # Simulate processing

                exec_repo.update_status(
                    execution.id,
                    status="completed",
                    result={
                        "rows_processed": 1000 * (i + 1),
                        "errors": 0,
                        "warnings": i * 2,
                    },
                )
                execution_ids.append(execution.id)
                print(f"✅ Execution {i+1} completed: {execution.id}")

            # Query execution history
            executions = exec_repo.list_for_workflow(workflow_id)
            print("\n📊 Execution History for workflow:")
            for exec in executions:
                if exec.execution_time_ms:
                    print(
                        f"   - {exec.id}: {exec.status} in {exec.execution_time_ms}ms"
                    )

    def example_analytics(self):
        """Perform analytics queries"""
        print("\n=== Analytics & Insights ===")

        with get_db_session(self.SessionLocal) as session:
            # Workflow usage statistics
            usage_stats = (
                session.query(
                    WorkflowModel.name,
                    func.count(ExecutionModel.id).label("execution_count"),
                    func.avg(ExecutionModel.execution_time_ms).label("avg_time"),
                    func.min(ExecutionModel.execution_time_ms).label("min_time"),
                    func.max(ExecutionModel.execution_time_ms).label("max_time"),
                )
                .join(ExecutionModel)
                .group_by(WorkflowModel.name)
                .all()
            )

            print("📈 Workflow Performance Stats:")
            for stat in usage_stats:
                print(f"   - {stat.name}:")
                print(f"     Executions: {stat.execution_count}")
                if stat.avg_time:
                    print(f"     Avg time: {stat.avg_time:.0f}ms")
                    print(f"     Min/Max: {stat.min_time}ms / {stat.max_time}ms")

            # Custom node usage
            node_count = (
                session.query(
                    CustomNodeModel.implementation_type,
                    func.count(CustomNodeModel.id).label("count"),
                )
                .group_by(CustomNodeModel.implementation_type)
                .all()
            )

            print("\n📊 Custom Node Distribution:")
            for node_type in node_count:
                print(f"   - {node_type.implementation_type}: {node_type.count} nodes")

    def example_templates(self):
        """Create and manage workflow templates"""
        print("\n=== Workflow Templates ===")

        with get_db_session(self.SessionLocal) as session:
            # Create templates
            templates = [
                {
                    "name": "Data Quality Check",
                    "category": "quality",
                    "description": "Standard data quality validation pipeline",
                    "definition": {
                        "nodes": [
                            {"id": "input", "type": "InputNode"},
                            {"id": "validate", "type": "DataValidator"},
                            {"id": "profile", "type": "DataProfilerNode"},
                            {"id": "output", "type": "OutputNode"},
                        ],
                        "connections": [
                            {"from": "input", "to": "validate"},
                            {"from": "validate", "to": "profile"},
                            {"from": "profile", "to": "output"},
                        ],
                    },
                },
                {
                    "name": "ML Feature Engineering",
                    "category": "ml",
                    "description": "Feature extraction and transformation for ML",
                    "definition": {
                        "nodes": [
                            {"id": "input", "type": "InputNode"},
                            {"id": "clean", "type": "DataCleanerNode"},
                            {"id": "encode", "type": "EncoderNode"},
                            {"id": "scale", "type": "ScalerNode"},
                            {"id": "output", "type": "OutputNode"},
                        ],
                        "connections": [
                            {"from": "input", "to": "clean"},
                            {"from": "clean", "to": "encode"},
                            {"from": "encode", "to": "scale"},
                            {"from": "scale", "to": "output"},
                        ],
                    },
                },
            ]

            for tmpl in templates:
                template = WorkflowTemplate(
                    tenant_id="example-tenant",
                    name=tmpl["name"],
                    category=tmpl["category"],
                    description=tmpl["description"],
                    definition=tmpl["definition"],
                    is_public=True,
                    created_by="system",
                )
                session.add(template)
            session.commit()

            # Query templates
            saved_templates = (
                session.query(WorkflowTemplate)
                .filter_by(tenant_id="example-tenant")
                .all()
            )

            print(f"✅ Created {len(saved_templates)} workflow templates:")
            for tmpl in saved_templates:
                print(f"   - {tmpl.name} ({tmpl.category})")

    def cleanup(self):
        """Clean up demo database"""
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
            print("\n🧹 Cleaned up demo database")


# ============================================================================
# PART 2: API Client Examples (Requires Running Server)
# ============================================================================


async def api_client_examples():
    """Examples using the REST API (requires server running)"""

    try:
        import httpx
        import websockets
    except ImportError:
        print("\n⚠️  API client examples require: pip install httpx websockets")
        return

    print("\n" + "=" * 60)
    print("API CLIENT EXAMPLES")
    print("=" * 60)

    base_url = "http://localhost:8000"

    async with httpx.AsyncClient() as client:
        # Check if server is running
        try:
            response = await client.get(f"{base_url}/health")
            print(f"✅ Connected to Studio API: {response.json()}")
        except Exception:
            print("❌ Studio API server not running.")
            print("   Start it with: python -m kailash.api.studio")
            return

        # Create workflow via API
        print("\n=== Creating Workflow via API ===")
        workflow_data = {
            "name": "API Test Workflow",
            "description": "Created via REST API",
            "definition": {
                "nodes": [
                    {"id": "input", "type": "InputNode"},
                    {"id": "process", "type": "DataProcessorNode"},
                    {"id": "output", "type": "OutputNode"},
                ],
                "connections": [
                    {"from": "input", "to": "process"},
                    {"from": "process", "to": "output"},
                ],
            },
        }

        response = await client.post(f"{base_url}/api/workflows", json=workflow_data)
        if response.status_code == 200:
            workflow = response.json()
            print(f"✅ Created workflow: {workflow['name']} (ID: {workflow['id']})")

            # Execute workflow
            print("\n=== Executing Workflow ===")
            exec_response = await client.post(
                f"{base_url}/api/workflows/{workflow['id']}/execute",
                json={"parameters": {"test_mode": True}},
            )

            if exec_response.status_code == 200:
                execution = exec_response.json()
                print(f"✅ Started execution: {execution['id']}")

                # Monitor via WebSocket
                print("\n=== Monitoring Execution via WebSocket ===")
                try:
                    async with websockets.connect(
                        f"ws://localhost:8000/ws/executions/{execution['id']}"
                    ) as ws:
                        while True:
                            message = await asyncio.wait_for(ws.recv(), timeout=5.0)
                            status = json.loads(message)
                            print(f"📡 Status: {status['status']}")
                            if status["status"] in ["completed", "failed"]:
                                break
                except TimeoutError:
                    print("⏱️  WebSocket monitoring timed out")


# ============================================================================
# MAIN EXECUTION
# ============================================================================


def main():
    """Run all examples"""
    print("=== Kailash Workflow Studio Comprehensive Examples ===")
    print("\nThis demo shows all Studio features using real database operations.")

    # Part 1: Database examples (always works)
    print("\n" + "=" * 60)
    print("STANDALONE DATABASE EXAMPLES")
    print("=" * 60)

    db_examples = StudioDatabaseExamples()

    # Run all database examples
    workflow_id = db_examples.example_workflow_management()
    db_examples.example_custom_nodes()
    db_examples.example_workflow_execution(workflow_id)
    db_examples.example_analytics()
    db_examples.example_templates()

    # Part 2: API client examples (optional)
    print("\n" + "=" * 60)
    print("API CLIENT EXAMPLES (Optional)")
    print("=" * 60)

    # Try to run API examples
    try:
        asyncio.run(api_client_examples())
    except Exception as e:
        print(f"\n⚠️  Could not run API examples: {e}")

    # Cleanup
    db_examples.cleanup()

    print("\n✅ All examples completed!")
    print("\n📚 Next steps:")
    print("1. Start the Studio API: python -m kailash.api.studio")
    print("2. Access the API at: http://localhost:8000/docs")
    print("3. Build your frontend using the REST API endpoints")


if __name__ == "__main__":
    main()
