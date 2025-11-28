"""Example of DataFlow models with edge computing integration.

This example demonstrates how to configure DataFlow models with edge
requirements for compliance, performance, and geo-distribution.
"""

from dataflow import DataFlow

from kailash.integrations.dataflow_edge import (
    DataFlowEdgeIntegration,
    enhance_dataflow_node_generator,
)
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

# Enable edge support in DataFlow
enhance_dataflow_node_generator()

# Initialize DataFlow
db = DataFlow()


# Example 1: GDPR-compliant user data with edge requirements
@db.model
class EUUserData:
    """User data that must remain in EU for GDPR compliance."""

    user_id: int
    email: str
    name: str
    preferences: dict
    consent_given: bool = False

    __dataflow__ = {
        "multi_tenant": True,
        "soft_delete": True,  # GDPR right to be forgotten
        "audit_log": True,  # Track all data access
        # Edge configuration for GDPR compliance
        "edge_config": {
            "compliance_classification": "eu_personal",
            "required_compliance": ["GDPR"],
            "preferred_regions": ["eu-west-1", "eu-central-1"],
            "edge_locations": ["eu-west-1", "eu-central-1"],
            "replication_strategy": "eu-only",
            "encryption_required": True,
            "data_residency": "EU",  # Data must not leave EU
            "edge_operations": ["create", "read", "update", "delete"],
        },
    }


# Example 2: Healthcare data with HIPAA requirements
@db.model
class HealthRecord:
    """Healthcare data requiring HIPAA compliance."""

    patient_id: int
    diagnosis: str
    treatment_plan: str
    medications: list
    provider_notes: str

    __dataflow__ = {
        "versioned": True,  # Track all changes
        "audit_log": True,  # Full audit trail
        "encryption": True,  # Encrypt at rest
        # Edge configuration for HIPAA compliance
        "edge_config": {
            "compliance_classification": "phi",
            "required_compliance": ["HIPAA"],
            "preferred_regions": ["us-east-1", "us-west-2"],
            "edge_locations": ["us-east-1", "us-west-2"],
            "consistency_model": "strong",  # Strong consistency for medical data
            "encryption_required": True,
            "audit_retention_days": 2555,  # 7 years for HIPAA
            "access_control": "strict",
            "edge_operations": ["create", "read", "update"],  # No edge delete
        },
    }


# Example 3: Global e-commerce with performance optimization
@db.model
class ProductCatalog:
    """Globally distributed product catalog."""

    product_id: int
    name: str
    description: str
    price: float
    inventory_count: int
    images: list

    __dataflow__ = {
        "indexes": [
            {"fields": ["name"], "type": "text"},
            {"fields": ["price", "inventory_count"]},
        ],
        # Edge configuration for global distribution
        "edge_config": {
            "compliance_classification": "public",
            "geo_distributed": True,
            "low_latency_required": True,
            "preferred_regions": ["us-east-1", "eu-west-1", "asia-east-1"],
            "edge_locations": ["us-east-1", "eu-west-1", "asia-east-1", "us-west-2"],
            "replication_strategy": "global",
            "replication_factor": 4,
            "consistency_model": "eventual",  # Eventual consistency is OK
            "cache_enabled": True,
            "cache_ttl": 300,  # 5 minute cache
            "edge_operations": ["read", "list"],  # Only reads at edge
            "selection_strategy": "latency",  # Choose nearest edge
        },
    }


# Example 4: Financial transactions with mixed requirements
@db.model
class FinancialTransaction:
    """Financial data with complex compliance needs."""

    transaction_id: str
    account_id: int
    amount: float
    currency: str
    transaction_type: str
    metadata: dict

    __dataflow__ = {
        "audit_log": True,
        "versioned": True,
        "soft_delete": False,  # Hard delete after retention period
        # Edge configuration for financial compliance
        "edge_config": {
            "compliance_classification": "financial",
            "required_compliance": ["PCI_DSS", "SOX"],
            "preferred_regions": ["us-east-1", "us-west-2"],
            "consistency_model": "strong",  # ACID compliance
            "encryption_required": True,
            "replication_strategy": "multi-region",
            "replication_factor": 3,
            "backup_retention_days": 2555,  # 7 years
            "edge_operations": ["create", "read"],
            "transaction_support": True,  # Enable distributed transactions
            "selection_strategy": "compliance",  # Compliance-first selection
        },
    }


def demonstrate_edge_workflows():
    """Demonstrate workflows using edge-enabled DataFlow models."""

    # Example 1: GDPR-compliant user creation
    print("=== GDPR-Compliant User Creation ===")

    # Extract edge config for workflow
    eu_edge_config = DataFlowEdgeIntegration.create_edge_workflow_config(
        "EUUserData", EUUserData.__dataflow__["edge_config"]
    )

    # Create workflow with edge configuration
    workflow = WorkflowBuilder(edge_config=eu_edge_config)

    # Add GDPR-compliant user creation
    workflow.add_node(
        "EUUserDataCreateNode",
        "create_eu_user",
        {
            "user_id": 12345,
            "email": "user@example.eu",
            "name": "European User",
            "preferences": {"language": "en", "notifications": True},
            "consent_given": True,
        },
    )

    # Add compliant data read
    workflow.add_node("EUUserDataReadNode", "read_eu_user", {"user_id": 12345})

    workflow.add_connection("create_eu_user", "read_eu_user")

    print(
        f"Workflow uses EU edge locations: {eu_edge_config['discovery']['locations']}"
    )
    print("Compliance requirements: GDPR")

    # Example 2: Global product catalog with caching
    print("\n=== Global Product Catalog ===")

    product_edge_config = DataFlowEdgeIntegration.create_edge_workflow_config(
        "ProductCatalog", ProductCatalog.__dataflow__["edge_config"]
    )

    catalog_workflow = WorkflowBuilder(edge_config=product_edge_config)

    # Read products from nearest edge
    catalog_workflow.add_node(
        "ProductCatalogListNode",
        "list_products",
        {
            "filter": {"inventory_count": {"$gt": 0}},
            "sort": [{"price": 1}],
            "limit": 100,
            "use_cache": True,  # Use edge cache
        },
    )

    print(
        f"Product catalog distributed to: {product_edge_config['discovery']['locations']}"
    )
    print("Using latency-based edge selection for optimal performance")

    # Example 3: Healthcare workflow with strong consistency
    print("\n=== HIPAA-Compliant Healthcare Workflow ===")

    health_edge_config = DataFlowEdgeIntegration.create_edge_workflow_config(
        "HealthRecord", HealthRecord.__dataflow__["edge_config"]
    )

    health_workflow = WorkflowBuilder(edge_config=health_edge_config)

    # Create health record with HIPAA compliance
    health_workflow.add_node(
        "HealthRecordCreateNode",
        "create_record",
        {
            "patient_id": 98765,
            "diagnosis": "Hypertension",
            "treatment_plan": "Medication and lifestyle changes",
            "medications": ["Lisinopril 10mg"],
            "provider_notes": "Follow up in 3 months",
        },
    )

    # Audit log automatically tracks access
    health_workflow.add_node(
        "HealthRecordAuditNode",
        "audit_access",
        {
            "record_id": 98765,
            "action": "view",
            "user": "dr_smith",
            "reason": "routine_checkup",
        },
    )

    print("Healthcare data uses strong consistency for data integrity")
    print("All operations logged for HIPAA compliance")

    # Example 4: Complex multi-region financial workflow
    print("\n=== Financial Transaction with Distributed Consensus ===")

    financial_edge_config = DataFlowEdgeIntegration.create_edge_workflow_config(
        "FinancialTransaction", FinancialTransaction.__dataflow__["edge_config"]
    )

    financial_workflow = WorkflowBuilder(edge_config=financial_edge_config)

    # Use distributed transaction for multi-region consistency
    financial_workflow.add_node(
        "TransactionManagerNode",
        "start_transaction",
        {"transaction_type": "two_phase_commit", "timeout": 30},
    )

    financial_workflow.add_node(
        "FinancialTransactionCreateNode",
        "record_transaction",
        {
            "transaction_id": "TXN-2025-001",
            "account_id": 54321,
            "amount": 1000.00,
            "currency": "USD",
            "transaction_type": "wire_transfer",
            "metadata": {"destination": "account_98765", "reference": "INV-2025-001"},
        },
    )

    financial_workflow.add_node("TransactionCommitNode", "commit_transaction", {})

    financial_workflow.add_connection("start_transaction", "record_transaction")
    financial_workflow.add_connection("record_transaction", "commit_transaction")

    print("Financial transactions use 2PC for consistency across regions")
    print(
        f"Replicating to {financial_edge_config['performance']['connection_pool_size']} regions"
    )

    return workflow, catalog_workflow, health_workflow, financial_workflow


if __name__ == "__main__":
    # Demonstrate the edge-enabled workflows
    workflows = demonstrate_edge_workflows()

    print("\n=== Summary ===")
    print(
        "DataFlow models can now specify edge requirements in __dataflow__['edge_config']"
    )
    print("Generated nodes automatically inherit edge capabilities")
    print("WorkflowBuilder detects and configures edge infrastructure")
    print("Compliance, performance, and distribution handled transparently")

    # Show example execution (would work with actual runtime)
    print("\nTo execute these workflows:")
    print("runtime = LocalRuntime()")
    print("results, run_id = runtime.execute(workflow.build())")
