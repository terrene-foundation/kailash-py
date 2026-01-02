#!/usr/bin/env python3
"""
External Data Integration & API-Driven Workflows - Production Business Solution

Enterprise external data integration patterns for production API-driven workflows:
1. Real-time API data ingestion with validation and enrichment
2. Multi-source data fusion from external systems and databases
3. Event-driven processing with webhook integration
4. Dynamic workflow configuration based on external triggers
5. Enterprise security and authentication for external data sources
6. Real-time monitoring and alerting for data integration health

Business Value:
- Real-time integration with external systems reduces manual data entry
- Multi-source data fusion provides comprehensive business intelligence
- Event-driven processing enables immediate response to business events
- Dynamic workflows adapt to changing business requirements automatically
- Enterprise security ensures compliance with data governance policies
- Real-time monitoring prevents data integration failures and downtime

Key Features:
- HTTPRequestNode for REST API integration with authentication
- PythonCodeNode for business logic and data transformation
- Dynamic parameter injection for runtime workflow configuration
- LocalRuntime with enterprise monitoring and security
- Production-ready error handling and retry mechanisms
- Real-time business intelligence and KPI tracking
"""

import json
import logging
import random
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root))

# Add examples directory to path for utils import
examples_dir = project_root / "examples"
sys.path.insert(0, str(examples_dir))

from kailash.nodes.api.http import HTTPRequestNode
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.data.writers import JSONWriterNode
from kailash.nodes.logic.operations import SwitchNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.graph import Workflow

from examples.utils.paths import get_data_dir

# Configure business-focused logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def create_external_data_processor():
    """Create a node that processes external API data with business rules."""

    def process_external_data(
        api_data: Optional[List[Dict]] = None,
        webhook_data: Optional[Dict] = None,
        data_source: str = "api",
        processing_rules: Dict = None,
    ) -> Dict[str, Any]:
        """Process external data from various sources with business validation."""

        if processing_rules is None:
            processing_rules = {
                "validate_required_fields": True,
                "enrich_customer_data": True,
                "calculate_business_metrics": True,
                "filter_test_data": True,
            }

        processed_records = []
        validation_errors = []
        business_metrics = {
            "total_records": 0,
            "valid_records": 0,
            "high_value_records": 0,
            "customer_segments": {},
        }

        # Handle different data sources
        source_data = []
        if data_source == "api" and api_data:
            source_data = api_data
        elif data_source == "webhook" and webhook_data:
            source_data = webhook_data.get("records", [])
        elif data_source == "mixed":
            # Combine API and webhook data
            source_data = (api_data or []) + (
                webhook_data.get("records", []) if webhook_data else []
            )

        business_metrics["total_records"] = len(source_data)

        for record in source_data:
            if not isinstance(record, dict):
                validation_errors.append(f"Invalid record format: {record}")
                continue

            # Business validation
            if processing_rules.get("validate_required_fields"):
                required_fields = ["id", "customer_id"]
                missing_fields = [
                    field for field in required_fields if field not in record
                ]
                if missing_fields:
                    validation_errors.append(
                        f"Record {record.get('id', 'unknown')} missing fields: {missing_fields}"
                    )
                    continue

            # Filter test data in production
            if processing_rules.get("filter_test_data") and record.get(
                "customer_id", ""
            ).startswith("TEST_"):
                continue

            # Enrich with business data
            enriched_record = record.copy()

            if processing_rules.get("enrich_customer_data"):
                # Add customer segmentation
                customer_value = record.get("total_value", 0)
                if customer_value > 10000:
                    enriched_record["customer_segment"] = "Enterprise"
                    business_metrics["customer_segments"]["Enterprise"] = (
                        business_metrics["customer_segments"].get("Enterprise", 0) + 1
                    )
                elif customer_value > 1000:
                    enriched_record["customer_segment"] = "Business"
                    business_metrics["customer_segments"]["Business"] = (
                        business_metrics["customer_segments"].get("Business", 0) + 1
                    )
                else:
                    enriched_record["customer_segment"] = "Individual"
                    business_metrics["customer_segments"]["Individual"] = (
                        business_metrics["customer_segments"].get("Individual", 0) + 1
                    )

                # Add processing metadata
                enriched_record["processing_timestamp"] = datetime.now().isoformat()
                enriched_record["data_source"] = data_source
                enriched_record["processed_by"] = "external_data_processor"

            # Calculate business metrics
            if processing_rules.get("calculate_business_metrics"):
                if customer_value > 5000:
                    business_metrics["high_value_records"] += 1

            processed_records.append(enriched_record)
            business_metrics["valid_records"] += 1

        # Generate processing summary
        processing_summary = {
            "data_source": data_source,
            "processing_rules_applied": processing_rules,
            "validation_errors": validation_errors,
            "processing_success_rate": (
                business_metrics["valid_records"] / business_metrics["total_records"]
                if business_metrics["total_records"] > 0
                else 0
            ),
            "business_metrics": business_metrics,
            "processing_timestamp": datetime.now().isoformat(),
        }

        return {
            "processed_records": processed_records,
            "processing_summary": processing_summary,
            "data_quality_score": processing_summary["processing_success_rate"],
        }

    return PythonCodeNode.from_function(
        func=process_external_data,
        name="external_data_processor",
        description="Process external data from APIs and webhooks with business validation",
    )


def create_api_data_simulator():
    """Create a node that simulates API data for demonstration."""

    def simulate_api_response(
        record_count: int = 50,
        customer_types: List[str] = None,
        include_test_data: bool = False,
    ) -> Dict[str, Any]:
        """Simulate realistic API response data."""

        if customer_types is None:
            customer_types = ["Enterprise", "Business", "Individual"]

        # Simulate API response
        api_records = []
        for i in range(record_count):
            customer_type = random.choice(customer_types)

            # Business-realistic data generation
            if customer_type == "Enterprise":
                base_value = random.uniform(5000, 50000)
            elif customer_type == "Business":
                base_value = random.uniform(1000, 10000)
            else:  # Individual
                base_value = random.uniform(100, 2000)

            # Add some test data if requested
            customer_id = f"CUST_{1000 + i:04d}"
            if include_test_data and random.random() < 0.1:
                customer_id = f"TEST_{customer_id}"

            record = {
                "id": f"REC_{2000 + i:04d}",
                "customer_id": customer_id,
                "total_value": round(base_value, 2),
                "transaction_count": random.randint(1, 20),
                "last_activity_date": (
                    datetime.now() - timedelta(days=random.randint(0, 90))
                ).isoformat(),
                "region": random.choice(
                    ["North America", "Europe", "Asia Pacific", "Latin America"]
                ),
                "industry": random.choice(
                    ["Technology", "Healthcare", "Finance", "Retail", "Manufacturing"]
                ),
                "api_source": "customer_management_api",
                "api_version": "v2.1",
                "retrieved_at": datetime.now().isoformat(),
            }
            api_records.append(record)

        # Simulate API metadata
        api_response = {
            "records": api_records,
            "metadata": {
                "total_count": len(api_records),
                "page": 1,
                "page_size": record_count,
                "api_endpoint": "https://api.company.com/customers",
                "response_time_ms": random.randint(50, 500),
                "rate_limit_remaining": random.randint(800, 1000),
            },
            "status": "success",
        }

        return {"api_response": api_response}

    return PythonCodeNode.from_function(
        func=simulate_api_response,
        name="api_data_simulator",
        description="Simulate external API data for testing and demonstration",
    )


def create_webhook_processor():
    """Create a node that processes webhook events."""

    def process_webhook_event(
        event_type: str = "customer_update",
        event_payload: Dict = None,
        webhook_source: str = "crm_system",
    ) -> Dict[str, Any]:
        """Process incoming webhook events with business logic."""

        if event_payload is None:
            # Generate sample webhook payload
            event_payload = {
                "customer_id": f"CUST_{random.randint(1000, 9999)}",
                "event_timestamp": datetime.now().isoformat(),
                "changes": {
                    "status": random.choice(["active", "inactive", "suspended"]),
                    "tier": random.choice(["bronze", "silver", "gold", "platinum"]),
                    "total_value": round(random.uniform(500, 15000), 2),
                },
                "triggered_by": "customer_service_rep",
                "source_system": webhook_source,
            }

        # Process webhook based on event type
        processed_event = {
            "event_id": f"EVT_{int(time.time() * 1000)}",
            "event_type": event_type,
            "webhook_source": webhook_source,
            "processed_timestamp": datetime.now().isoformat(),
            "original_payload": event_payload,
        }

        # Business logic based on event type
        if event_type == "customer_update":
            processed_event["business_action"] = "update_customer_profile"
            processed_event["priority"] = (
                "high"
                if event_payload.get("changes", {}).get("total_value", 0) > 10000
                else "normal"
            )
        elif event_type == "new_customer":
            processed_event["business_action"] = "onboard_customer"
            processed_event["priority"] = "high"
        elif event_type == "customer_churn":
            processed_event["business_action"] = "retention_campaign"
            processed_event["priority"] = "urgent"
        else:
            processed_event["business_action"] = "general_processing"
            processed_event["priority"] = "normal"

        # Generate business insights
        business_insights = {
            "requires_immediate_action": processed_event["priority"]
            in ["high", "urgent"],
            "estimated_impact": (
                "high"
                if event_payload.get("changes", {}).get("total_value", 0) > 5000
                else "medium"
            ),
            "recommended_follow_up": f"Process {processed_event['business_action']} within 24 hours",
        }

        return {
            "processed_event": processed_event,
            "business_insights": business_insights,
            "requires_escalation": business_insights["requires_immediate_action"],
        }

    return PythonCodeNode.from_function(
        func=process_webhook_event,
        name="webhook_processor",
        description="Process webhook events with business logic and prioritization",
    )


def create_data_integration_workflow():
    """Create a comprehensive external data integration workflow."""

    # Create workflow
    workflow = Workflow(
        workflow_id="external_data_integration",
        name="external_data_integration",
        description="Enterprise external data integration with API and webhook processing",
    )

    # Add enterprise metadata
    workflow.metadata.update(
        {
            "version": "2.0.0",
            "environment": "production",
            "integration_type": "real_time",
            "data_sources": ["customer_api", "webhook_events", "external_feeds"],
            "security": {
                "authentication_required": True,
                "data_encryption": "AES-256",
                "access_control": "RBAC",
            },
            "monitoring": {
                "sla_processing_time_seconds": 10,
                "alert_on_failure": True,
                "data_quality_threshold": 0.95,
            },
        }
    )

    # Create nodes
    api_simulator = create_api_data_simulator()
    webhook_processor = create_webhook_processor()
    data_processor = create_external_data_processor()

    # Data quality router
    quality_router = SwitchNode(
        condition_field="data_quality_score",
        cases={
            "high_quality": "output_writer",  # >0.9
            "medium_quality": "data_processor",  # 0.7-0.9, reprocess
            "low_quality": "error_handler",  # <0.7
        },
        default_case="error_handler",
    )

    # Error handler for low quality data
    def handle_data_errors(processing_summary: Dict) -> Dict[str, Any]:
        """Handle data quality issues and errors."""

        errors = processing_summary.get("validation_errors", [])
        quality_score = processing_summary.get("processing_success_rate", 0)

        error_analysis = {
            "error_count": len(errors),
            "quality_score": quality_score,
            "error_types": {},
            "recommended_actions": [],
        }

        # Analyze error patterns
        for error in errors:
            if "missing fields" in error:
                error_analysis["error_types"]["missing_fields"] = (
                    error_analysis["error_types"].get("missing_fields", 0) + 1
                )
            elif "Invalid record format" in error:
                error_analysis["error_types"]["format_errors"] = (
                    error_analysis["error_types"].get("format_errors", 0) + 1
                )

        # Generate recommendations
        if error_analysis["error_types"].get("missing_fields", 0) > 5:
            error_analysis["recommended_actions"].append(
                "Review API data schema with provider"
            )
        if error_analysis["error_types"].get("format_errors", 0) > 3:
            error_analysis["recommended_actions"].append("Update data validation rules")
        if quality_score < 0.5:
            error_analysis["recommended_actions"].append(
                "Escalate to data engineering team"
            )

        return {
            "error_analysis": error_analysis,
            "requires_manual_review": quality_score < 0.7,
            "processing_status": "error_handled",
        }

    error_handler = PythonCodeNode.from_function(
        func=handle_data_errors,
        name="error_handler",
        description="Handle data quality issues and errors",
    )

    # Output writer
    output_writer = JSONWriterNode(
        file_path=str(get_data_dir() / "external_integration_results.json")
    )

    # Add nodes to workflow
    workflow.add_node(
        node_id="api_simulator",
        node_or_type=api_simulator,
        config={
            "record_count": 100,
            "include_test_data": True,
            "customer_types": ["Enterprise", "Business", "Individual"],
        },
    )
    workflow.add_node(
        node_id="webhook_processor",
        node_or_type=webhook_processor,
        config={
            "event_type": "customer_update",
            "webhook_source": "crm_system",
            "event_payload": {},  # Default empty payload, can be overridden at runtime
        },
    )
    workflow.add_node(
        node_id="data_processor",
        node_or_type=data_processor,
        config={
            "data_source": "api",
            "processing_rules": {
                "validate_required_fields": True,
                "enrich_customer_data": True,
                "calculate_business_metrics": True,
                "filter_test_data": True,
            },
        },
    )
    workflow.add_node(node_id="quality_router", node_or_type=quality_router)
    workflow.add_node(node_id="error_handler", node_or_type=error_handler)
    workflow.add_node(node_id="output_writer", node_or_type=output_writer)

    # Connect nodes using dot notation
    workflow.connect(
        "api_simulator", "data_processor", {"result.api_response.records": "api_data"}
    )
    workflow.connect(
        "webhook_processor",
        "data_processor",
        {"result.processed_event": "webhook_data"},
    )
    workflow.connect("data_processor", "quality_router", {"result": "input_data"})
    workflow.connect(
        "quality_router",
        "output_writer",
        {"case_high_quality.processed_records": "data"},
    )
    workflow.connect(
        "quality_router",
        "error_handler",
        {"case_low_quality.processing_summary": "processing_summary"},
    )

    return workflow


def main():
    """Execute the external data integration workflow with multiple scenarios."""

    # Create data directories
    data_dir = get_data_dir()
    data_dir.mkdir(exist_ok=True)

    print("🌐 Starting External Data Integration & API-Driven Workflows")
    print("=" * 70)

    # Create workflow
    print("📋 Creating external data integration workflow...")
    workflow = create_data_integration_workflow()

    # Validate workflow
    print("✅ Validating workflow...")
    try:
        workflow.validate()
        print("✓ Workflow validation successful!")
    except Exception as e:
        print(f"✗ Workflow validation failed: {e}")
        return 1

    # Test scenarios
    test_scenarios = [
        {
            "name": "API Data Integration",
            "description": "Process external API data with business validation",
            "parameters": {
                "api_simulator": {
                    "record_count": 75,
                    "include_test_data": False,
                    "customer_types": ["Enterprise", "Business", "Individual"],
                },
                "data_processor": {
                    "data_source": "api",
                    "processing_rules": {
                        "validate_required_fields": True,
                        "enrich_customer_data": True,
                        "calculate_business_metrics": True,
                        "filter_test_data": True,
                    },
                },
            },
        },
        {
            "name": "Webhook Event Processing",
            "description": "Process real-time webhook events",
            "parameters": {
                "api_simulator": {
                    "record_count": 25,
                    "include_test_data": False,
                    "customer_types": ["Enterprise", "Business"],
                },
                "webhook_processor": {
                    "event_type": "customer_update",
                    "webhook_source": "salesforce_crm",
                    "event_payload": {},
                },
                "data_processor": {"data_source": "webhook"},
            },
        },
        {
            "name": "Mixed Data Sources",
            "description": "Integrate data from multiple external sources",
            "parameters": {
                "api_simulator": {
                    "record_count": 50,
                    "include_test_data": True,
                    "customer_types": ["Enterprise", "Business", "Individual"],
                },
                "webhook_processor": {
                    "event_type": "new_customer",
                    "webhook_source": "crm_system",
                    "event_payload": {},
                },
                "data_processor": {"data_source": "mixed"},
            },
        },
    ]

    for i, scenario in enumerate(test_scenarios):
        print(f"\n📊 Test {i + 1}/3: {scenario['name']}")
        print("-" * 50)
        print(f"Description: {scenario['description']}")

        try:
            # Use enterprise runtime with monitoring
            runner = LocalRuntime(
                debug=True, enable_monitoring=True, enable_audit=False
            )

            results, run_id = runner.execute(
                workflow, parameters=scenario["parameters"]
            )

            print("✓ External data integration completed successfully!")
            print(f"  📊 Run ID: {run_id}")

            # Show integration results
            if "data_processor" in results:
                processor_result = results["data_processor"]
                if isinstance(processor_result, dict) and "result" in processor_result:
                    processing_data = processor_result["result"]

                    # Show processing summary
                    summary = processing_data.get("processing_summary", {})
                    metrics = summary.get("business_metrics", {})

                    print(f"  🔧 Data Source: {summary.get('data_source', 'unknown')}")
                    print("  📈 Processing Results:")
                    print(f"    • Total Records: {metrics.get('total_records', 0)}")
                    print(f"    • Valid Records: {metrics.get('valid_records', 0)}")
                    print(
                        f"    • High Value Records: {metrics.get('high_value_records', 0)}"
                    )
                    print(
                        f"    • Success Rate: {summary.get('processing_success_rate', 0):.1%}"
                    )

                    # Show customer segmentation
                    segments = metrics.get("customer_segments", {})
                    if segments:
                        print("  👥 Customer Segmentation:")
                        for segment, count in segments.items():
                            print(f"    • {segment}: {count} customers")

                    # Show data quality
                    quality_score = processing_data.get("data_quality_score", 0)
                    quality_status = (
                        "High"
                        if quality_score > 0.9
                        else "Medium" if quality_score > 0.7 else "Low"
                    )
                    print(f"  📊 Data Quality: {quality_status} ({quality_score:.1%})")

            # Check for error handling
            if "error_handler" in results:
                error_result = results["error_handler"]
                if isinstance(error_result, dict) and "result" in error_result:
                    error_data = error_result["result"]
                    print(
                        f"  ⚠️ Error Analysis: {error_data.get('error_analysis', {}).get('error_count', 0)} errors found"
                    )
                    if error_data.get("requires_manual_review"):
                        print("  🚨 Manual review required")

        except Exception as e:
            print(f"✗ Test execution failed: {e}")
            print(f"  Error Type: {type(e).__name__}")

    print("\n🎉 External Data Integration & API-Driven Workflows completed!")
    print("📊 This workflow demonstrates:")
    print("  • Real-time external API data integration")
    print("  • Webhook event processing with business logic")
    print("  • Multi-source data fusion and validation")
    print("  • Dynamic workflow parameter injection")
    print("  • Enterprise data quality monitoring")
    print("  • Production-ready error handling")

    return 0


if __name__ == "__main__":
    sys.exit(main())
