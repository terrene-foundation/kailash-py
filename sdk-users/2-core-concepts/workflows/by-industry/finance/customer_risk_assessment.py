#!/usr/bin/env python3
"""
Customer Risk Assessment Workflow for Financial Services

This production workflow implements a comprehensive customer risk assessment
system with PII protection, compliance tracking, and enterprise security features.

Business Context:
- Processes customer financial data with risk scoring
- Implements data privacy and compliance requirements
- Provides audit trails for regulatory compliance
- Supports multi-tenant isolation for different business units

Industry: Finance
Pattern: Risk Assessment, Compliance
Enterprise Features: Security, Audit, Multi-tenancy
"""

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))
from kailash.access_control import UserContext
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.data.readers import CSVReaderNode
from kailash.runtime.local import LocalRuntime
from kailash.tracking import TaskManager
from kailash.workflow import Workflow

from examples.utils.data_paths import get_input_data_path, get_output_data_path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_enterprise_workflow() -> Workflow:
    """Create a workflow that benefits from enterprise features."""
    workflow = Workflow(
        workflow_id="enterprise_demo",
        name="Enterprise Demo Workflow",
        description="Demonstrates enterprise integration patterns",
    )

    # Data source
    reader = CSVReaderNode(file_path=str(get_input_data_path("customers.csv")))

    # Sensitive data processing
    def process_sensitive_data(data, **kwargs):
        """Process customer data (contains PII)."""
        if not data:
            return {"result": []}

        processed = []
        for row in data:
            if isinstance(row, dict):
                # Simulate sensitive data processing
                processed_row = {
                    "customer_id": row.get("id", "unknown"),
                    "age_group": "senior" if int(row.get("age", 0)) >= 65 else "adult",
                    "email_domain": (
                        row.get("email", "").split("@")[-1]
                        if "@" in row.get("email", "")
                        else "unknown"
                    ),
                    "processed_at": datetime.now().isoformat(),
                    "contains_pii": True,  # Flag for audit purposes
                }
                processed.append(processed_row)

        return {"result": processed}

    processor = PythonCodeNode.from_function(
        func=process_sensitive_data, name="sensitive_processor"
    )

    # Risk assessment
    def assess_risk(data, **kwargs):
        """Assess risk levels for customers."""
        if not data:
            return {"result": []}

        risk_assessed = []
        for row in data:
            if isinstance(row, dict):
                # Simulate risk assessment
                row_with_risk = row.copy()
                row_with_risk["risk_level"] = (
                    "high" if row.get("age_group") == "senior" else "low"
                )
                row_with_risk["requires_review"] = row_with_risk["risk_level"] == "high"
                risk_assessed.append(row_with_risk)

        return {"result": risk_assessed}

    risk_assessor = PythonCodeNode.from_function(func=assess_risk, name="risk_assessor")

    # Add nodes
    workflow.add_node("data_source", reader)
    workflow.add_node("sensitive_processor", processor)
    workflow.add_node("risk_assessor", risk_assessor)

    # Connect nodes
    workflow.connect("data_source", "sensitive_processor", {"data": "data"})
    workflow.connect("sensitive_processor", "risk_assessor", {"result": "data"})

    return workflow


def example_1_no_manual_construction():
    """Example 1: No manual enterprise node construction required."""
    print("\n" + "=" * 70)
    print("EXAMPLE 1: NO MANUAL ENTERPRISE NODE CONSTRUCTION")
    print("=" * 70)
    print("🏗️  Enterprise features integrate automatically - no manual setup!\n")

    workflow = create_enterprise_workflow()
    user_context = UserContext(
        user_id="compliance_officer",
        tenant_id="financial_corp",
        email="compliance@financial.com",
        roles=["compliance_officer", "data_analyst"],
    )

    print("❌ WHAT USERS DON'T NEED TO DO ANYMORE:")
    print(
        """
    # Users DON'T need to manually create enterprise nodes:
    from kailash.nodes.security.audit_log import AuditLogNode
    from kailash.nodes.security.threat_detection import ThreatDetectionNode
    from kailash.nodes.security.credential_manager import CredentialManagerNode
    from kailash.access_control import AccessControlManager

    # Users DON'T need complex manual wiring:
    audit_node = AuditLogNode()
    threat_node = ThreatDetectionNode()
    acm = AccessControlManager()

    # Users DON'T need manual execution orchestration:
    audit_result = audit_node.execute(event_type="workflow_start", ...)
    threat_result = threat_node.execute(...)
    access_decision = acm.check_workflow_access(...)
    """
    )

    print("✅ WHAT USERS DO NOW (SIMPLE):")
    print(
        """
    # Simple parameter-based configuration:
    runtime = LocalRuntime(
        enable_audit=True,      # AuditLogNode integration automatic
        enable_security=True,   # AccessControlManager integration automatic
        enable_monitoring=True, # TaskManager integration automatic
        user_context=user_ctx   # Multi-tenant support automatic
    )

    # Everything works automatically!
    results, run_id = runtime.execute(workflow)
    """
    )

    # Demonstrate the automatic integration
    print("🔧 Demonstrating automatic enterprise integration:")

    # Create runtime with enterprise features
    runtime = LocalRuntime(
        enable_audit=True,  # Automatically uses AuditLogNode
        enable_monitoring=True,  # Automatically uses TaskManager & MetricsCollector
        enable_security=False,  # Would use AccessControlManager (disabled for demo)
        user_context=user_context,  # User context for enterprise features
    )

    print("   📋 Runtime created with enterprise features")
    print(f"   🔹 Audit logging: {runtime.enable_audit} (uses AuditLogNode)")
    print(f"   🔹 Monitoring: {runtime.enable_monitoring} (uses TaskManager)")
    print(f"   🔹 Security: {runtime.enable_security} (uses AccessControlManager)")
    print(f"   🔹 User context: {runtime.user_context.user_id}")

    # Execute workflow - enterprise features activate automatically
    task_manager = TaskManager()
    results, run_id = runtime.execute(workflow, task_manager=task_manager)

    print("\n   ✅ Workflow executed with automatic enterprise integration")
    print(f"   📊 Nodes: {len(results)}, Run ID: {run_id}")
    print("   📝 Audit events logged automatically")
    print("   📈 Performance metrics collected automatically")
    print("   👤 User context tracked automatically")

    print("\n✨ ENTERPRISE NODES USED UNDER THE HOOD:")
    print("   🔹 AuditLogNode: Automatic audit event logging")
    print("   🔹 TaskManager: Automatic performance tracking")
    print("   🔹 MetricsCollector: Automatic performance metrics")
    print("   🔹 All without manual construction or wiring!")


def example_2_composable_integration_patterns():
    """Example 2: Show how runtime composes with existing enterprise nodes."""
    print("\n" + "=" * 70)
    print("EXAMPLE 2: COMPOSABLE INTEGRATION PATTERNS")
    print("=" * 70)
    print("🧩 Runtime composes with existing enterprise nodes (no duplication)\n")

    workflow = create_enterprise_workflow()

    # Show enterprise nodes that exist in the SDK
    print("📦 EXISTING ENTERPRISE NODES IN SDK (67+ nodes):")
    print(
        """
    Security Nodes:
    🔹 AuditLogNode - Compliance audit logging
    🔹 SecurityEventNode - Security incident tracking
    🔹 ThreatDetectionNode - AI-powered threat detection
    🔹 CredentialManagerNode - Secure credential management
    🔹 RotatingCredentialNode - Automatic credential rotation
    🔹 ABACPermissionEvaluatorNode - Attribute-based access control

    Auth Nodes:
    🔹 SSOAuthenticationNode - Single sign-on integration
    🔹 MultiFactorAuthNode - MFA verification
    🔹 SessionManagementNode - Session lifecycle management
    🔹 EnterpriseAuthProviderNode - Enterprise auth integration

    Admin Nodes:
    🔹 UserManagementNode - User lifecycle management
    🔹 RoleManagementNode - Role assignment and hierarchy
    🔹 PermissionCheckNode - Real-time permission evaluation

    Monitoring Nodes:
    🔹 PerformanceBenchmarkNode - Performance analysis
    🔹 DataLineageNode - Data lineage tracking
    🔹 BatchProcessorNode - Optimized batch processing
    """
    )

    print("🏗️  HOW UNIFIED RUNTIME COMPOSES WITH THESE NODES:")
    print(
        """
    Runtime Integration Pattern:

    1. enable_audit=True → Uses AuditLogNode automatically
       ├── runtime._log_audit_event_async()
       └── AuditLogNode.async_run(event_type, event_data, user_context)

    2. enable_security=True → Uses AccessControlManager + security nodes
       ├── runtime._check_workflow_access()
       ├── AccessControlManager.check_workflow_access()
       └── Various security nodes for enforcement

    3. enable_monitoring=True → Uses TaskManager + MetricsCollector
       ├── TaskManager.create_run() / create_task()
       ├── MetricsCollector.collect()
       └── Performance nodes for analysis

    4. user_context → Passed to all enterprise nodes automatically
       ├── Multi-tenant isolation
       ├── Security context
       └── Audit trail attribution
    """
    )

    # Demonstrate composition in action
    print("🔧 DEMONSTRATING COMPOSITION:")

    user_context = UserContext(
        user_id="enterprise_admin",
        tenant_id="enterprise_corp",
        roles=["admin", "security_officer"],
        attributes={"department": "security", "clearance": "high"},
    )

    # Runtime composes with enterprise nodes
    runtime = LocalRuntime(
        enable_audit=True,  # Composes with AuditLogNode
        enable_monitoring=True,  # Composes with TaskManager/MetricsCollector
        enable_async=True,  # Composes with AsyncNode patterns
        user_context=user_context,  # Shared context across all enterprise nodes
    )

    print("   🏗️  Runtime configured for enterprise composition")
    print("   📝 Audit: Composes with AuditLogNode")
    print("   📊 Monitoring: Composes with TaskManager + MetricsCollector")
    print("   ⚡ Async: Composes with AsyncNode execution patterns")
    print("   👤 Context: Shared across all enterprise nodes")

    # Execute and show composition
    task_manager = TaskManager()
    results, run_id = runtime.execute(workflow, task_manager=task_manager)

    print("\n   ✅ Execution completed with enterprise composition")
    print("   🔗 Enterprise nodes composed automatically")
    print("   📋 No manual wiring required")
    print("   🎯 Single runtime interface for everything")

    print("\n✨ COMPOSITION BENEFITS:")
    print("   🔹 No code duplication - leverages existing nodes")
    print("   🔹 Consistent interfaces across all enterprise features")
    print("   🔹 Automatic integration - no manual wiring")
    print("   🔹 Composable architecture maintained")
    print("   🔹 Enterprise nodes can be used independently too")


def example_3_progressive_enterprise_enablement():
    """Example 3: Progressive enablement of enterprise features."""
    print("\n" + "=" * 70)
    print("EXAMPLE 3: PROGRESSIVE ENTERPRISE ENABLEMENT")
    print("=" * 70)
    print("📈 Enable enterprise features progressively as needs grow\n")

    workflow = create_enterprise_workflow()
    user_context = UserContext(
        user_id="developer", tenant_id="startup", roles=["developer"]
    )

    print("🚀 ENTERPRISE ADOPTION JOURNEY:")

    # Stage 1: Basic usage
    print("\n1️⃣  STAGE 1: Basic Development (No Enterprise)")
    runtime_basic = LocalRuntime()
    results1, run_id1 = runtime_basic.execute(workflow)
    print(f"   📊 Basic execution: {len(results1)} nodes, Run ID: {run_id1}")
    print("   🔹 No enterprise overhead")
    print("   🔹 Fast development iteration")

    # Stage 2: Add monitoring
    print("\n2️⃣  STAGE 2: Add Performance Monitoring")
    runtime_monitoring = LocalRuntime(enable_monitoring=True)
    task_manager = TaskManager()
    results2, run_id2 = runtime_monitoring.execute(workflow, task_manager=task_manager)
    print(f"   📈 With monitoring: {len(results2)} nodes, Run ID: {run_id2}")
    print("   🔹 TaskManager integration automatic")
    print("   🔹 MetricsCollector tracking automatic")
    print("   🔹 Performance insights available")

    # Stage 3: Add audit logging
    print("\n3️⃣  STAGE 3: Add Compliance Auditing")
    runtime_audit = LocalRuntime(
        enable_monitoring=True, enable_audit=True, user_context=user_context
    )
    results3, run_id3 = runtime_audit.execute(workflow, task_manager=task_manager)
    print(f"   📝 With auditing: {len(results3)} nodes, Run ID: {run_id3}")
    print("   🔹 AuditLogNode integration automatic")
    print("   🔹 Compliance events logged automatically")
    print("   🔹 User attribution tracked")

    # Stage 4: Add async performance
    print("\n4️⃣  STAGE 4: Add Async Performance")
    runtime_async = LocalRuntime(
        enable_monitoring=True,
        enable_audit=True,
        enable_async=True,
        max_concurrency=10,
        user_context=user_context,
    )
    results4, run_id4 = runtime_async.execute(workflow, task_manager=task_manager)
    print(f"   ⚡ With async: {len(results4)} nodes, Run ID: {run_id4}")
    print("   🔹 AsyncNode execution automatic")
    print("   🔹 Concurrent node processing")
    print("   🔹 Better resource utilization")

    # Stage 5: Full enterprise
    print("\n5️⃣  STAGE 5: Full Enterprise Security")
    enterprise_user = UserContext(
        user_id="enterprise_admin",
        tenant_id="enterprise_corp",
        roles=["admin", "security_officer", "compliance_officer"],
        attributes={"department": "security", "clearance": "high"},
    )

    runtime_enterprise = LocalRuntime(
        enable_monitoring=True,
        enable_audit=True,
        enable_async=True,
        enable_security=False,  # Would enable AccessControlManager (disabled for demo)
        max_concurrency=20,
        user_context=enterprise_user,
        resource_limits={"memory_mb": 8192, "cpu_cores": 8},
    )
    results5, run_id5 = runtime_enterprise.execute(workflow, task_manager=task_manager)
    print(f"   🏢 Full enterprise: {len(results5)} nodes, Run ID: {run_id5}")
    print("   🔹 AccessControlManager integration (when enabled)")
    print("   🔹 Multi-tenant isolation")
    print("   🔹 Resource limits enforcement")
    print("   🔹 Complete enterprise stack")

    print("\n✨ PROGRESSIVE ENABLEMENT BENEFITS:")
    print("   🔹 Start simple, add features as needed")
    print("   🔹 No upfront complexity")
    print("   🔹 Each stage adds value incrementally")
    print("   🔹 No breaking changes between stages")
    print("   🔹 Enterprise features opt-in")


def example_4_enterprise_nodes_still_usable_independently():
    """Example 4: Enterprise nodes can still be used independently."""
    print("\n" + "=" * 70)
    print("EXAMPLE 4: ENTERPRISE NODES STILL USABLE INDEPENDENTLY")
    print("=" * 70)
    print("🔧 Enterprise nodes remain available for direct use when needed\n")

    print("💡 FLEXIBILITY: Choose your integration level")
    print(
        """
    Option 1: Use unified runtime (recommended for most cases)
    ├── runtime = LocalRuntime(enable_audit=True)
    └── Automatic enterprise node integration

    Option 2: Manual enterprise node usage (for custom workflows)
    ├── audit_node = AuditLogNode()
    ├── result = audit_node.execute(...)
    └── Direct node control and custom integration
    """
    )

    # Demonstrate manual enterprise node usage
    print("🔧 DEMONSTRATING MANUAL ENTERPRISE NODE USAGE:")

    try:
        # Manual AuditLogNode usage
        print("\n1. Manual AuditLogNode usage:")
        from kailash.nodes.security.audit_log import AuditLogNode

        audit_node = AuditLogNode()
        audit_result = audit_node.execute(
            event_type="manual_audit_test",
            event_data={"test": "manual audit logging"},
            user_context=UserContext(user_id="manual_user", tenant_id="test"),
            timestamp=datetime.now(),
        )
        print(f"   ✅ Manual audit result: {type(audit_result)}")
        print("   🔹 Direct node control")
        print("   🔹 Custom audit event structure")

    except ImportError:
        print("   ℹ️  AuditLogNode not available (for demo)")

    try:
        # Manual TaskManager usage
        print("\n2. Manual TaskManager usage:")
        task_manager = TaskManager()
        run_id = task_manager.create_run("manual_test_workflow")
        print(f"   ✅ Manual task manager run ID: {run_id}")
        print("   🔹 Direct task tracking control")
        print("   🔹 Custom metadata and tracking")

    except Exception as e:
        print(f"   ℹ️  TaskManager demo: {e}")

    try:
        # Manual AccessControlManager usage
        print("\n3. Manual AccessControlManager usage:")
        from kailash.access_control import (
            WorkflowPermission,
            get_access_control_manager,
        )

        acm = get_access_control_manager()
        user_context = UserContext(
            user_id="test_user", tenant_id="test", roles=["user"]
        )

        # This would work with proper access control setup
        print(f"   ✅ AccessControlManager available: {acm is not None}")
        print("   🔹 Direct access control decisions")
        print("   🔹 Custom permission evaluation")

    except ImportError:
        print("   ℹ️  AccessControlManager not available (for demo)")

    print("\n🔄 COMPARISON: Unified vs Manual")
    print(
        """
    Unified Runtime (Recommended):
    ✅ Simple parameter-based configuration
    ✅ Automatic integration and orchestration
    ✅ Consistent enterprise feature behavior
    ✅ No manual wiring required
    ✅ Production-ready defaults

    Manual Node Usage (Advanced):
    ✅ Maximum control and customization
    ✅ Custom integration patterns
    ✅ Specialized use cases
    ✅ Educational/debugging purposes
    ✅ Legacy integration support
    """
    )

    print("\n✨ ARCHITECTURAL FLEXIBILITY:")
    print("   🔹 Unified runtime for 90% of use cases")
    print("   🔹 Manual nodes for advanced customization")
    print("   🔹 Mix and match as needed")
    print("   🔹 Enterprise nodes composable at any level")
    print("   🔹 No vendor lock-in to runtime approach")


async def example_5_async_enterprise_integration():
    """Example 5: Async enterprise integration patterns."""
    print("\n" + "=" * 70)
    print("EXAMPLE 5: ASYNC ENTERPRISE INTEGRATION")
    print("=" * 70)
    print("⚡ Enterprise features work seamlessly with async execution\n")

    workflow = create_enterprise_workflow()
    user_context = UserContext(
        user_id="async_user",
        tenant_id="async_corp",
        roles=["async_developer"],
        attributes={"async_enabled": True},
    )

    print("🔧 Async Enterprise Runtime Configuration:")

    # Create async-optimized enterprise runtime
    runtime = LocalRuntime(
        enable_async=True,  # Async execution enabled
        enable_audit=True,  # Async audit logging
        enable_monitoring=True,  # Async performance tracking
        max_concurrency=15,  # High concurrency
        user_context=user_context,
    )

    print(f"   ⚡ Async execution: {runtime.enable_async}")
    print(f"   📝 Async audit logging: {runtime.enable_audit}")
    print(f"   📊 Async monitoring: {runtime.enable_monitoring}")
    print(f"   🚀 Concurrency: {runtime.max_concurrency}")

    print("\n🏗️  Enterprise Async Integration Patterns:")
    print(
        """
    1. Async Audit Logging:
       ├── runtime._log_audit_event_async()
       ├── AuditLogNode.async_run() if available
       └── Fallback to sync AuditLogNode.execute()

    2. Async Node Execution:
       ├── Check: hasattr(node, 'async_run')
       ├── Use: await node.async_run(**inputs)
       └── Fallback: node.execute(**inputs)

    3. Async Task Management:
       ├── TaskManager integration (sync)
       ├── MetricsCollector (sync)
       └── Performance tracking concurrent
    """
    )

    # Execute with async enterprise features
    print("⚙️  Executing async workflow with enterprise features...")

    start_time = datetime.now()

    # Use the async interface
    results, run_id = await runtime.execute_async(workflow)

    end_time = datetime.now()
    execution_time = (end_time - start_time).total_seconds()

    print("\n   ✅ Async enterprise execution completed!")
    print(f"   📊 Nodes: {len(results)}, Run ID: {run_id}")
    print(f"   ⏱️  Execution time: {execution_time:.3f}s")
    print("   📝 Audit events logged asynchronously")
    print("   📈 Performance tracked during async execution")
    print("   🔄 Enterprise features work seamlessly with async")

    print("\n✨ ASYNC ENTERPRISE BENEFITS:")
    print("   🔹 Better resource utilization")
    print("   🔹 Concurrent enterprise operations")
    print("   🔹 Non-blocking audit logging")
    print("   🔹 Scalable performance monitoring")
    print("   🔹 Enterprise-grade async patterns")


def main():
    """Run all enterprise integration examples."""
    print("🏢 ENTERPRISE INTEGRATION EXAMPLES")
    print("=" * 80)
    print("Deep dive into how unified runtime integrates with enterprise nodes")
    print("=" * 80)

    try:
        # Run all examples
        example_1_no_manual_construction()
        example_2_composable_integration_patterns()
        example_3_progressive_enterprise_enablement()
        example_4_enterprise_nodes_still_usable_independently()

        # Run async example
        asyncio.run(example_5_async_enterprise_integration())

        print("\n" + "=" * 80)
        print("🎉 ALL ENTERPRISE INTEGRATION EXAMPLES COMPLETED!")
        print("=" * 80)
        print("\n📋 KEY TAKEAWAYS:")
        print("   ✅ No manual enterprise node construction required")
        print("   ✅ Runtime composes with existing 67+ enterprise nodes")
        print("   ✅ Progressive enterprise feature enablement")
        print("   ✅ Enterprise nodes still usable independently")
        print("   ✅ Async enterprise integration seamless")

        print("\n🏗️  ARCHITECTURE HIGHLIGHTS:")
        print("   🔹 Composable integration (no duplication)")
        print("   🔹 Automatic orchestration (no manual wiring)")
        print("   🔹 Progressive adoption (start simple, scale up)")
        print("   🔹 Flexible usage (unified runtime OR manual nodes)")
        print("   🔹 Enterprise-ready (security, compliance, monitoring)")

        print("\n💡 FOR USERS:")
        print("   👨‍💻 Developers: Start with basic LocalRuntime")
        print("   📈 Scale: Add enable_monitoring=True")
        print("   🔒 Secure: Add enable_security=True")
        print("   📝 Comply: Add enable_audit=True")
        print("   🏢 Enterprise: All features with simple parameters")

    except Exception as e:
        print(f"\n❌ Example failed: {e}")
        import traceback

        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
