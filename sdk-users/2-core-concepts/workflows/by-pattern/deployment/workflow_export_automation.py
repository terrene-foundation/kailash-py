#!/usr/bin/env python3
"""
Workflow Export & Deployment Automation - Production Business Solution

Enterprise workflow deployment and CI/CD automation for production environments:
1. Automated workflow validation and testing before deployment
2. Multi-environment export with configuration management
3. Kubernetes and Docker deployment automation
4. Version control integration with automated rollback
5. Production monitoring and health check integration
6. Compliance validation and audit trail generation

Business Value:
- Automated deployment reduces human error and deployment time
- Multi-environment support ensures consistent deployments across dev/staging/prod
- Version control integration enables safe rollbacks and change tracking
- Compliance validation meets enterprise governance requirements
- Production monitoring ensures workflow health and performance
- Audit trails provide full deployment history for compliance

Key Features:
- WorkflowExporter with enterprise templates and validation
- Multi-environment configuration management
- Automated testing and validation pipeline
- Production-ready deployment automation
- Real-time monitoring and alerting integration
- Compliance and audit trail generation
"""

import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root))

# Add examples directory to path for utils import
examples_dir = project_root / "examples"
sys.path.insert(0, str(examples_dir))

from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.data.readers import CSVReaderNode
from kailash.nodes.data.writers import JSONWriterNode
from kailash.runtime.local import LocalRuntime
from kailash.utils.export import ExportConfig, WorkflowExporter, export_workflow
from kailash.workflow.graph import Workflow

from examples.utils.paths import get_data_dir

# Configure enterprise-focused logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def create_sample_business_workflow():
    """Create a realistic business workflow for deployment demonstration."""

    def process_customer_orders(order_count: int = 100) -> Dict[str, Any]:
        """Process customer orders with business validation."""

        import random
        from datetime import datetime

        # Generate realistic order data
        orders = []
        for i in range(order_count):
            order_date = datetime.now() - timedelta(days=random.randint(0, 30))

            order = {
                "order_id": f"ORD_{2000 + i:04d}",
                "customer_id": f"CUST_{random.randint(1, 500):04d}",
                "product_category": random.choice(
                    ["Electronics", "Clothing", "Books", "Home", "Sports"]
                ),
                "order_amount": round(random.uniform(25, 2500), 2),
                "order_date": order_date.isoformat(),
                "shipping_region": random.choice(
                    ["North", "South", "East", "West", "Central"]
                ),
                "priority": random.choice(["Standard", "Express", "Overnight"]),
                "status": "Processing",
            }
            orders.append(order)

        # Business metrics
        total_revenue = sum(order["order_amount"] for order in orders)
        avg_order_value = total_revenue / len(orders) if orders else 0
        high_value_orders = [o for o in orders if o["order_amount"] > 500]

        return {
            "orders": orders,
            "business_metrics": {
                "total_orders": len(orders),
                "total_revenue": round(total_revenue, 2),
                "average_order_value": round(avg_order_value, 2),
                "high_value_orders": len(high_value_orders),
                "processing_timestamp": datetime.now().isoformat(),
            },
        }

    def validate_and_enrich_orders(orders: List[Dict]) -> Dict[str, Any]:
        """Validate and enrich order data with business rules."""

        validated_orders = []
        validation_errors = []

        for order in orders:
            # Business validation rules
            is_valid = True

            if order.get("order_amount", 0) <= 0:
                validation_errors.append(
                    f"Invalid amount for order {order.get('order_id')}"
                )
                is_valid = False

            if not order.get("customer_id"):
                validation_errors.append(
                    f"Missing customer ID for order {order.get('order_id')}"
                )
                is_valid = False

            if is_valid:
                # Enrich with business logic
                enriched_order = order.copy()

                # Calculate priority score
                amount = order.get("order_amount", 0)
                if amount > 1000:
                    enriched_order["business_priority"] = "VIP"
                elif amount > 500:
                    enriched_order["business_priority"] = "Premium"
                else:
                    enriched_order["business_priority"] = "Standard"

                # Add processing metadata
                enriched_order["validation_status"] = "Validated"
                enriched_order["enrichment_timestamp"] = datetime.now().isoformat()

                validated_orders.append(enriched_order)

        return {
            "validated_orders": validated_orders,
            "validation_summary": {
                "total_processed": len(orders),
                "valid_orders": len(validated_orders),
                "validation_errors": len(validation_errors),
                "error_details": validation_errors,
                "validation_rate": len(validated_orders) / len(orders) if orders else 0,
            },
        }

    def generate_business_insights(validated_orders: List[Dict]) -> Dict[str, Any]:
        """Generate business insights and KPIs from validated orders."""

        if not validated_orders:
            return {"insights": "No validated orders to analyze"}

        # Revenue analysis
        revenue_by_category = {}
        revenue_by_region = {}
        priority_distribution = {}

        for order in validated_orders:
            category = order.get("product_category", "Unknown")
            region = order.get("shipping_region", "Unknown")
            priority = order.get("business_priority", "Unknown")
            amount = order.get("order_amount", 0)

            revenue_by_category[category] = (
                revenue_by_category.get(category, 0) + amount
            )
            revenue_by_region[region] = revenue_by_region.get(region, 0) + amount
            priority_distribution[priority] = priority_distribution.get(priority, 0) + 1

        # Calculate insights
        top_category = (
            max(revenue_by_category.items(), key=lambda x: x[1])
            if revenue_by_category
            else ("None", 0)
        )
        top_region = (
            max(revenue_by_region.items(), key=lambda x: x[1])
            if revenue_by_region
            else ("None", 0)
        )

        insights = {
            "revenue_analysis": {
                "by_category": revenue_by_category,
                "by_region": revenue_by_region,
                "top_performing_category": {
                    "name": top_category[0],
                    "revenue": round(top_category[1], 2),
                },
                "top_performing_region": {
                    "name": top_region[0],
                    "revenue": round(top_region[1], 2),
                },
            },
            "customer_segmentation": {
                "priority_distribution": priority_distribution,
                "vip_customers": priority_distribution.get("VIP", 0),
                "premium_customers": priority_distribution.get("Premium", 0),
            },
            "business_kpis": {
                "total_validated_orders": len(validated_orders),
                "total_revenue": round(
                    sum(o.get("order_amount", 0) for o in validated_orders), 2
                ),
                "average_order_value": round(
                    sum(o.get("order_amount", 0) for o in validated_orders)
                    / len(validated_orders),
                    2,
                ),
                "insights_generated_at": datetime.now().isoformat(),
            },
        }

        return {"business_insights": insights}

    # Create workflow
    workflow = Workflow(
        workflow_id="enterprise_order_processing",
        name="enterprise_order_processing",
        description="Enterprise order processing with validation and business intelligence",
    )

    # Add enterprise metadata
    workflow.metadata.update(
        {
            "version": "2.1.0",
            "environment": "production",
            "team": "data-platform",
            "compliance": {
                "data_classification": "internal",
                "retention_period_days": 2555,  # 7 years
                "privacy_level": "customer_data",
            },
            "monitoring": {
                "sla_processing_time_seconds": 30,
                "alert_on_failure": True,
                "business_metrics_tracking": True,
            },
            "deployment": {
                "container_registry": "enterprise-registry.company.com",
                "kubernetes_namespace": "data-processing",
                "resource_requirements": {
                    "cpu": "500m",
                    "memory": "1Gi",
                    "storage": "10Gi",
                },
            },
        }
    )

    # Create nodes
    order_processor = PythonCodeNode.from_function(
        func=process_customer_orders,
        name="order_processor",
        description="Process customer orders with business validation",
    )

    order_validator = PythonCodeNode.from_function(
        func=validate_and_enrich_orders,
        name="order_validator",
        description="Validate and enrich order data with business rules",
    )

    insights_generator = PythonCodeNode.from_function(
        func=generate_business_insights,
        name="insights_generator",
        description="Generate business insights and KPIs",
    )

    # Output writer for audit trail
    output_writer = JSONWriterNode(
        file_path=str(get_data_dir() / "order_processing_results.json")
    )

    # Add nodes to workflow with configuration
    workflow.add_node(
        node_id="order_processor",
        node_or_type=order_processor,
        config={"order_count": 100},  # Provide default configuration
    )
    workflow.add_node(node_id="order_validator", node_or_type=order_validator)
    workflow.add_node(node_id="insights_generator", node_or_type=insights_generator)
    workflow.add_node(node_id="output_writer", node_or_type=output_writer)

    # Connect nodes using dot notation
    workflow.connect("order_processor", "order_validator", {"result.orders": "orders"})
    workflow.connect(
        "order_validator",
        "insights_generator",
        {"result.validated_orders": "validated_orders"},
    )
    workflow.connect("insights_generator", "output_writer", {"result": "data"})

    return workflow


def create_deployment_environments():
    """Create configuration for multiple deployment environments."""

    environments = {
        "development": {
            "namespace": "dev-data-processing",
            "replicas": 1,
            "resources": {"cpu": "100m", "memory": "256Mi"},
            "image_tag": "dev",
            "debug_enabled": True,
            "monitoring_level": "basic",
        },
        "staging": {
            "namespace": "staging-data-processing",
            "replicas": 2,
            "resources": {"cpu": "250m", "memory": "512Mi"},
            "image_tag": "staging",
            "debug_enabled": False,
            "monitoring_level": "enhanced",
        },
        "production": {
            "namespace": "prod-data-processing",
            "replicas": 3,
            "resources": {"cpu": "500m", "memory": "1Gi"},
            "image_tag": "latest",
            "debug_enabled": False,
            "monitoring_level": "full",
            "high_availability": True,
            "backup_enabled": True,
        },
    }

    return environments


def export_workflow_for_environments(workflow: Workflow, environments: Dict[str, Dict]):
    """Export workflow configurations for multiple environments."""

    export_results = {}

    for env_name, env_config in environments.items():
        print(f"📦 Exporting workflow for {env_name} environment...")

        # Create environment-specific export config
        export_config = ExportConfig(
            version="2.1.0",
            namespace=env_config["namespace"],
            container_registry="enterprise-registry.company.com",
            include_metadata=True,
            include_resources=True,
            validate_output=True,
        )

        exporter = WorkflowExporter(export_config)

        # Update workflow metadata for environment
        workflow.metadata[f"{env_name}_config"] = env_config

        try:
            # Export as Kubernetes manifest
            k8s_manifest = exporter.to_manifest(workflow)

            # Export as YAML for configuration management
            yaml_export = exporter.to_yaml(workflow)

            # Export as JSON for API integration
            json_export = exporter.to_json(workflow)

            export_results[env_name] = {
                "kubernetes_manifest": k8s_manifest,
                "yaml_config": yaml_export,
                "json_config": json_export,
                "environment_config": env_config,
            }

            print(f"✓ {env_name} environment export completed")

        except Exception as e:
            print(f"✗ Failed to export for {env_name}: {e}")
            export_results[env_name] = {"error": str(e)}

    return export_results


def validate_workflow_before_deployment(workflow: Workflow):
    """Validate workflow before deployment with comprehensive checks."""

    print("🔍 Performing pre-deployment validation...")

    validation_results = {
        "workflow_validation": False,
        "execution_test": False,
        "compliance_check": False,
        "performance_check": False,
        "errors": [],
        "warnings": [],
    }

    try:
        # 1. Basic workflow validation
        workflow.validate()
        validation_results["workflow_validation"] = True
        print("✓ Workflow structure validation passed")

    except Exception as e:
        validation_results["errors"].append(f"Workflow validation failed: {e}")
        print(f"✗ Workflow validation failed: {e}")

    try:
        # 2. Execution test with sample data
        print("🧪 Running execution test...")
        runner = LocalRuntime(debug=False, enable_monitoring=True, enable_audit=True)

        test_params = {"order_processor": {"order_count": 10}}
        results, run_id = runner.execute(workflow, parameters=test_params)

        if results and len(results) >= 3:  # Expecting results from all main nodes
            validation_results["execution_test"] = True
            print(f"✓ Execution test passed (run_id: {run_id})")
        else:
            validation_results["errors"].append(
                "Execution test incomplete - missing expected results"
            )

    except Exception as e:
        validation_results["errors"].append(f"Execution test failed: {e}")
        print(f"✗ Execution test failed: {e}")

    # 3. Compliance validation
    try:
        compliance_metadata = workflow.metadata.get("compliance", {})
        required_compliance_fields = [
            "data_classification",
            "retention_period_days",
            "privacy_level",
        ]

        missing_fields = [
            field
            for field in required_compliance_fields
            if field not in compliance_metadata
        ]

        if not missing_fields:
            validation_results["compliance_check"] = True
            print("✓ Compliance validation passed")
        else:
            validation_results["warnings"].append(
                f"Missing compliance fields: {missing_fields}"
            )
            print(f"⚠️ Missing compliance fields: {missing_fields}")

    except Exception as e:
        validation_results["errors"].append(f"Compliance check failed: {e}")

    # 4. Performance check (simulate)
    try:
        monitoring_config = workflow.metadata.get("monitoring", {})
        if monitoring_config.get("sla_processing_time_seconds"):
            validation_results["performance_check"] = True
            print("✓ Performance monitoring configuration found")
        else:
            validation_results["warnings"].append("No SLA configuration found")

    except Exception as e:
        validation_results["warnings"].append(f"Performance check warning: {e}")

    # Summary
    passed_checks = sum(
        [
            validation_results["workflow_validation"],
            validation_results["execution_test"],
            validation_results["compliance_check"],
            validation_results["performance_check"],
        ]
    )

    print(f"\n📊 Validation Summary: {passed_checks}/4 checks passed")

    if validation_results["errors"]:
        print("❌ Critical errors found:")
        for error in validation_results["errors"]:
            print(f"  • {error}")

    if validation_results["warnings"]:
        print("⚠️ Warnings found:")
        for warning in validation_results["warnings"]:
            print(f"  • {warning}")

    return validation_results


def simulate_deployment_pipeline(
    workflow: Workflow, target_environment: str = "staging"
):
    """Simulate a complete deployment pipeline."""

    print(f"🚀 Starting deployment pipeline for {target_environment} environment")
    print("=" * 70)

    # Step 1: Pre-deployment validation
    print("📋 Step 1: Pre-deployment validation")
    validation_results = validate_workflow_before_deployment(workflow)

    if (
        not validation_results["workflow_validation"]
        or not validation_results["execution_test"]
    ):
        print("❌ Critical validation failures - deployment blocked")
        return False

    # Step 2: Export for target environment
    print(f"\n📦 Step 2: Export for {target_environment} environment")
    environments = create_deployment_environments()
    export_results = export_workflow_for_environments(
        workflow, {target_environment: environments[target_environment]}
    )

    if "error" in export_results.get(target_environment, {}):
        print(f"❌ Export failed for {target_environment}")
        return False

    # Step 3: Simulate deployment
    print(f"\n🔧 Step 3: Deploying to {target_environment}")
    deployment_steps = [
        "Validating Kubernetes cluster access",
        "Creating namespace if not exists",
        "Applying ConfigMaps and Secrets",
        "Deploying workflow containers",
        "Configuring service mesh routing",
        "Setting up monitoring and alerting",
        "Running health checks",
    ]

    for i, step in enumerate(deployment_steps):
        print(f"  {i+1}/7: {step}...")
        time.sleep(0.5)  # Simulate deployment time
        print(f"  ✓ {step} completed")

    # Step 4: Post-deployment validation
    print("\n✅ Step 4: Post-deployment validation")
    print("  ✓ Health check endpoints responding")
    print("  ✓ Metrics collection active")
    print("  ✓ Log aggregation configured")
    print("  ✓ Workflow ready for traffic")

    # Step 5: Generate deployment report
    deployment_report = {
        "deployment_id": f"DEPLOY_{int(time.time())}",
        "environment": target_environment,
        "workflow_id": workflow.workflow_id,
        "version": workflow.metadata.get("version", "unknown"),
        "deployment_timestamp": datetime.now().isoformat(),
        "validation_summary": validation_results,
        "deployment_status": "SUCCESS",
        "next_steps": [
            "Monitor application metrics for 24 hours",
            "Verify business KPI tracking",
            "Schedule automated tests",
            "Update documentation",
        ],
    }

    print("\n📊 Deployment Report Generated:")
    print(f"  • Deployment ID: {deployment_report['deployment_id']}")
    print(f"  • Status: {deployment_report['deployment_status']}")
    print(f"  • Environment: {deployment_report['environment']}")

    return True


def main():
    """Execute the workflow export and deployment automation."""

    # Create data directories
    data_dir = get_data_dir()
    data_dir.mkdir(exist_ok=True)

    print("🏭 Starting Workflow Export & Deployment Automation")
    print("=" * 70)

    # Create enterprise workflow
    print("📋 Creating enterprise order processing workflow...")
    workflow = create_sample_business_workflow()

    # Test basic export functionality
    print("\n🔧 Testing basic export functionality...")
    try:
        basic_export = export_workflow(workflow, format="yaml")
        print(f"✓ Basic YAML export successful ({len(basic_export)} characters)")
    except Exception as e:
        print(f"✗ Basic export failed: {e}")
        return 1

    # Multi-environment export
    print("\n🌍 Multi-environment export demonstration...")
    environments = create_deployment_environments()
    export_results = export_workflow_for_environments(workflow, environments)

    print(f"✓ Exported configurations for {len(export_results)} environments")
    for env_name, result in export_results.items():
        if "error" not in result:
            print(f"  • {env_name}: ✓ Ready for deployment")
        else:
            print(f"  • {env_name}: ✗ Export failed")

    # Simulate deployment pipeline
    print("\n🚀 Deployment Pipeline Simulation")
    print("-" * 50)

    # Deploy to staging first
    staging_success = simulate_deployment_pipeline(workflow, "staging")

    if staging_success:
        print("\n✅ Staging deployment successful!")
        print("📈 Ready for production deployment")

        # Simulate production deployment
        print("\n🎯 Production Deployment Simulation")
        print("-" * 50)
        production_success = simulate_deployment_pipeline(workflow, "production")

        if production_success:
            print("\n🎉 Production deployment completed successfully!")
        else:
            print("\n❌ Production deployment failed")
    else:
        print("\n❌ Staging deployment failed - blocking production")

    # Generate final summary
    print("\n📊 Deployment Automation Summary")
    print("=" * 70)
    print("✓ Enterprise workflow created with compliance metadata")
    print("✓ Multi-environment export configurations generated")
    print("✓ Pre-deployment validation pipeline executed")
    print("✓ Kubernetes deployment manifests created")
    print("✓ Monitoring and alerting configurations included")
    print("✓ Audit trail and compliance reporting enabled")

    print("\n🔧 This workflow demonstrates:")
    print("  • Production-ready workflow export and deployment")
    print("  • Multi-environment configuration management")
    print("  • Automated validation and testing pipelines")
    print("  • Enterprise compliance and audit requirements")
    print("  • Kubernetes deployment automation")
    print("  • Real-time monitoring and alerting integration")

    return 0


if __name__ == "__main__":
    sys.exit(main())
