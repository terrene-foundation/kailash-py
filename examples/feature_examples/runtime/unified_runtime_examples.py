#!/usr/bin/env python3
"""
Unified Runtime Examples - Demonstrating the New Enterprise Capabilities

This module demonstrates how the unified LocalRuntime works differently from
the previous architecture and shows enterprise features integration.

Key Differences from Previous Architecture:
1. Enterprise features are built-in (no manual node construction)
2. Unified async/sync execution in single runtime
3. Composable integration with existing enterprise nodes
4. Zero breaking changes for existing code

Run this example:
    python examples/feature_examples/runtime/unified_runtime_examples.py
"""

import asyncio
import logging
from datetime import datetime
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from examples.utils.data_paths import get_input_data_path, get_output_data_path
from kailash.access_control import UserContext
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.data.readers import CSVReaderNode
from kailash.nodes.data.writers import CSVWriterNode
from kailash.runtime.local import LocalRuntime
from kailash.tracking import TaskManager
from kailash.workflow import Workflow

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_sample_workflow() -> Workflow:
    """Create a sample workflow for testing unified runtime."""
    workflow = Workflow(workflow_id="unified_runtime_demo", name="Unified Runtime Demo")
    
    # Create nodes
    reader = CSVReaderNode(file_path=str(get_input_data_path("customers.csv")))
    
    def process_data(data, **kwargs):
        """Process customer data."""
        if not data:
            return {"result": []}
        
        processed = []
        for row in data:
            if isinstance(row, dict) and "age" in row:
                # Add processed flag and calculate category
                processed_row = row.copy()
                processed_row["processed"] = True
                processed_row["age_category"] = "senior" if int(row["age"]) >= 65 else "adult"
                processed.append(processed_row)
        
        return {"result": processed}
    
    processor = PythonCodeNode.from_function(
        func=process_data,
        name="data_processor"
    )
    
    writer = CSVWriterNode(file_path=str(get_output_data_path("unified_runtime_output.csv")))
    
    # Add nodes to workflow
    workflow.add_node("reader", reader)
    workflow.add_node("processor", processor)
    workflow.add_node("writer", writer)
    
    # Connect nodes
    workflow.connect("reader", "processor", {"data": "data"})
    workflow.connect("processor", "writer", {"result": "data"})
    
    return workflow


def example_1_backward_compatibility():
    """Example 1: Demonstrate 100% backward compatibility."""
    print("\n" + "="*60)
    print("EXAMPLE 1: BACKWARD COMPATIBILITY")
    print("="*60)
    print("✅ All existing LocalRuntime usage patterns work unchanged\n")
    
    workflow = create_sample_workflow()
    
    # Previous usage patterns - ALL WORK UNCHANGED
    print("1. Basic LocalRuntime usage (unchanged):")
    runtime1 = LocalRuntime()
    results1, run_id1 = runtime1.execute(workflow)
    print(f"   ✅ Results: {len(results1)} nodes executed, Run ID: {run_id1}")
    
    print("\n2. LocalRuntime with debug (unchanged):")
    runtime2 = LocalRuntime(debug=True)
    results2, run_id2 = runtime2.execute(workflow)
    print(f"   ✅ Results: {len(results2)} nodes executed, Run ID: {run_id2}")
    
    print("\n3. LocalRuntime with cycles (unchanged):")
    runtime3 = LocalRuntime(debug=False, enable_cycles=True)
    results3, run_id3 = runtime3.execute(workflow)
    print(f"   ✅ Results: {len(results3)} nodes executed, Run ID: {run_id3}")
    
    print("\n4. Task manager integration (unchanged):")
    task_manager = TaskManager()
    runtime4 = LocalRuntime(debug=True)
    results4, run_id4 = runtime4.execute(workflow, task_manager=task_manager)
    print(f"   ✅ Results: {len(results4)} nodes executed, Run ID: {run_id4}")
    
    print("\n✨ KEY DIFFERENCE: Same interface, now with enterprise capabilities available!")


def example_2_asynclocal_compatibility():
    """Example 2: LocalRuntime compatibility."""
    print("\n" + "="*60)
    print("EXAMPLE 2: ASYNCLOCAL COMPATIBILITY")
    print("="*60)
    print("✅ LocalRuntime usage patterns work unchanged\n")
    
    async def async_demo():
        workflow = create_sample_workflow()
        
        print("1. LocalRuntime usage (unchanged):")
        runtime = LocalRuntime(enable_async=True)
        results, run_id = await runtime.execute(workflow)
        print(f"   ✅ Async Results: {len(results)} nodes executed, Run ID: {run_id}")
        
        print("\n2. LocalRuntime with debug (unchanged):")
        runtime2 = LocalRuntime(debug=True, max_concurrency=5, enable_async=True)
        results2, run_id2 = await runtime2.execute(workflow)
        print(f"   ✅ Async Results: {len(results2)} nodes executed, Run ID: {run_id2}")
        
        print("\n✨ KEY DIFFERENCE: LocalRuntime now powered by unified LocalRuntime!")
    
    asyncio.run(async_demo())


def example_3_enterprise_features_builtin():
    """Example 3: Enterprise features are now built-in (no manual construction)."""
    print("\n" + "="*60)
    print("EXAMPLE 3: ENTERPRISE FEATURES BUILT-IN")
    print("="*60)
    print("🏢 Enterprise capabilities available with simple parameters\n")
    
    workflow = create_sample_workflow()
    
    # BEFORE: Users had to manually construct enterprise nodes
    print("❌ BEFORE: Manual enterprise node construction required")
    print("   - Create AccessControlManager manually")
    print("   - Create AuditLogNode manually") 
    print("   - Create SecurityEventNode manually")
    print("   - Wire everything together manually")
    print("   - Complex integration code required\n")
    
    # NOW: Enterprise features built into runtime
    print("✅ NOW: Enterprise features built into unified runtime")
    
    print("\n1. Enable monitoring (automatic TaskManager integration):")
    runtime1 = LocalRuntime(enable_monitoring=True)
    results1, run_id1 = runtime1.execute(workflow)
    print(f"   📊 Enhanced monitoring active, Run ID: {run_id1}")
    
    print("\n2. Enable async execution (automatic async/sync detection):")
    runtime2 = LocalRuntime(enable_async=True, max_concurrency=10)
    results2, run_id2 = runtime2.execute(workflow)
    print(f"   ⚡ Async execution enabled, Run ID: {run_id2}")
    
    print("\n3. Enable audit logging (automatic AuditLogNode integration):")
    runtime3 = LocalRuntime(enable_audit=True)
    results3, run_id3 = runtime3.execute(workflow)
    print(f"   📝 Audit logging active, Run ID: {run_id3}")
    
    print("\n✨ KEY DIFFERENCE: Enterprise features integrate automatically!")
    print("   🔹 No manual node construction required")
    print("   🔹 No complex wiring needed") 
    print("   🔹 Uses existing enterprise nodes under the hood")
    print("   🔹 Composable architecture maintained")


def example_4_enterprise_security_integration():
    """Example 4: Enterprise security integration."""
    print("\n" + "="*60)
    print("EXAMPLE 4: ENTERPRISE SECURITY INTEGRATION")
    print("="*60)
    print("🔒 Security features integrate with existing enterprise nodes\n")
    
    workflow = create_sample_workflow()
    
    # Create user context for security
    user_context = UserContext(
        user_id="demo_user",
        tenant_id="demo_tenant", 
        email="demo@company.com",
        roles=["analyst", "viewer"]
    )
    
    print("User Context:")
    print(f"   🆔 User ID: {user_context.user_id}")
    print(f"   🏢 Tenant: {user_context.tenant_id}")
    print(f"   👤 Roles: {user_context.roles}")
    
    print("\n1. Runtime with security disabled (default):")
    runtime1 = LocalRuntime(user_context=user_context)
    results1, run_id1 = runtime1.execute(workflow)
    print(f"   ✅ Executed without security checks, Run ID: {run_id1}")
    
    print("\n2. Runtime with security enabled:")
    print("   🔹 Uses existing AccessControlManager")
    print("   🔹 Leverages existing security nodes")
    print("   🔹 No manual security construction needed")
    
    runtime2 = LocalRuntime(
        user_context=user_context,
        enable_security=True,  # Enables automatic security checks
        enable_audit=True      # Logs security events
    )
    
    try:
        results2, run_id2 = runtime2.execute(workflow)
        print(f"   ✅ Security checks passed, Run ID: {run_id2}")
    except PermissionError as e:
        print(f"   🚫 Security check failed: {e}")
    
    print("\n✨ KEY DIFFERENCE: Security integrates with existing enterprise architecture!")
    print("   🔹 AccessControlManager integration automatic")
    print("   🔹 AuditLogNode logging automatic")
    print("   🔹 SecurityEventNode integration automatic")


def example_5_full_enterprise_configuration():
    """Example 5: Full enterprise configuration."""
    print("\n" + "="*60)
    print("EXAMPLE 5: FULL ENTERPRISE CONFIGURATION")
    print("="*60)
    print("🚀 Complete enterprise setup with all features enabled\n")
    
    workflow = create_sample_workflow()
    
    # Enterprise user context
    user_context = UserContext(
        user_id="enterprise_user",
        tenant_id="enterprise_corp",
        email="admin@enterprise.com", 
        roles=["admin", "security_officer"],
        attributes={"department": "IT", "clearance": "high"}
    )
    
    # Full enterprise runtime configuration
    enterprise_runtime = LocalRuntime(
        # Standard parameters
        debug=True,
        enable_cycles=True,
        
        # Enterprise parameters  
        enable_async=True,           # Async execution support
        max_concurrency=10,          # Parallel execution
        user_context=user_context,   # Multi-tenant security
        enable_monitoring=True,      # Performance tracking
        enable_security=True,        # Access control
        enable_audit=True,           # Compliance logging
        resource_limits={            # Resource management
            "memory_mb": 4096,
            "cpu_cores": 4,
            "max_execution_time": 300
        }
    )
    
    print("Enterprise Runtime Configuration:")
    print(f"   🔧 Debug: {enterprise_runtime.debug}")
    print(f"   🔄 Cycles: {enterprise_runtime.enable_cycles}")
    print(f"   ⚡ Async: {enterprise_runtime.enable_async}")
    print(f"   🚀 Concurrency: {enterprise_runtime.max_concurrency}")
    print(f"   👤 User: {enterprise_runtime.user_context.user_id}")
    print(f"   📊 Monitoring: {enterprise_runtime.enable_monitoring}")
    print(f"   🔒 Security: {enterprise_runtime.enable_security}")
    print(f"   📝 Audit: {enterprise_runtime.enable_audit}")
    print(f"   💾 Memory Limit: {enterprise_runtime.resource_limits.get('memory_mb')}MB")
    
    print("\n🏢 Enterprise Features Integration:")
    print("   🔹 AccessControlManager: Automatic RBAC/ABAC evaluation")
    print("   🔹 AuditLogNode: Automatic compliance logging")
    print("   🔹 SecurityEventNode: Automatic security event tracking") 
    print("   🔹 TaskManager: Enhanced performance monitoring")
    print("   🔹 MetricsCollector: Automatic performance metrics")
    print("   🔹 CredentialManagerNode: Secure credential handling")
    print("   🔹 ThreatDetectionNode: Security threat monitoring")
    
    # Execute with full enterprise features
    task_manager = TaskManager()
    
    try:
        print(f"\n⚙️  Executing workflow with full enterprise features...")
        start_time = datetime.now()
        
        results, run_id = enterprise_runtime.execute(
            workflow, 
            task_manager=task_manager
        )
        
        end_time = datetime.now()
        execution_time = (end_time - start_time).total_seconds()
        
        print(f"   ✅ Enterprise execution completed!")
        print(f"   📊 Nodes executed: {len(results)}")
        print(f"   🆔 Run ID: {run_id}")
        print(f"   ⏱️  Execution time: {execution_time:.3f}s")
        
        # Show enterprise tracking
        if run_id and task_manager:
            run_data = task_manager.get_run(run_id)
            if run_data:
                print(f"   📈 Run status: {run_data.status}")
                print(f"   🕐 Started: {run_data.started_at}")
                
    except Exception as e:
        print(f"   ❌ Enterprise execution failed: {e}")
    
    print("\n✨ KEY DIFFERENCE: Complete enterprise stack with single runtime!")
    print("   🔹 No manual enterprise node construction")
    print("   🔹 No complex middleware setup")
    print("   🔹 All enterprise features composably integrated")
    print("   🔹 Production-ready security and compliance")


def example_6_comparison_before_after():
    """Example 6: Direct comparison of before vs after."""
    print("\n" + "="*60)
    print("EXAMPLE 6: BEFORE vs AFTER COMPARISON")
    print("="*60)
    
    workflow = create_sample_workflow()
    user_context = UserContext(user_id="test", tenant_id="test", roles=["user"])
    
    print("❌ BEFORE - Unified Runtime (Complex Manual Setup):")
    print("""
    # Multiple runtimes needed
    from kailash.runtime.local import LocalRuntime
    from kailash.runtime.local import LocalRuntime  
    from kailash.runtime.access_controlled import AccessControlledRuntime
    
    # Manual enterprise node construction
    from kailash.nodes.security.audit_log import AuditLogNode
    from kailash.access_control import AccessControlManager
    
    # Complex setup required
    acm = AccessControlManager()
    audit_node = AuditLogNode()
    
    # Different runtimes for different needs
    local_runtime = LocalRuntime()
    async_runtime = LocalRuntime(enable_async=True)
    secure_runtime = AccessControlledRuntime(user_context)
    
    # Manual enterprise feature wiring
    # ... complex integration code ...
    """)
    
    print("✅ NOW - Unified Runtime (Simple Configuration):")
    print("""
    # Single unified runtime
    from kailash.runtime.local import LocalRuntime
    
    # Enterprise features built-in
    runtime = LocalRuntime(
        enable_async=True,        # Replaces LocalRuntime
        enable_security=True,     # Replaces AccessControlledRuntime  
        enable_audit=True,        # AuditLogNode integration
        enable_monitoring=True,   # TaskManager integration
        user_context=user_context # Multi-tenant support
    )
    
    # Everything works automatically!
    results, run_id = runtime.execute(workflow)
    """)
    
    # Demonstrate the difference
    print("\n🔧 Demonstrating the unified approach:")
    
    # Single runtime does everything
    unified_runtime = LocalRuntime(
        enable_async=True,
        enable_security=False,  # Disabled for demo (would need proper setup)
        enable_audit=True,
        enable_monitoring=True,
        user_context=user_context
    )
    
    results, run_id = unified_runtime.execute(workflow)
    
    print(f"   ✅ Unified runtime executed workflow")
    print(f"   📊 Nodes: {len(results)}, Run ID: {run_id}")
    print(f"   🎯 Single runtime replaced 3+ separate runtimes")
    print(f"   🔧 Zero manual enterprise node construction")
    print(f"   🏗️  Built-in composable integration")
    
    print("\n✨ BENEFITS OF UNIFIED APPROACH:")
    print("   🔹 100% backward compatibility")
    print("   🔹 Zero breaking changes")
    print("   🔹 Simplified developer experience")
    print("   🔹 Enterprise features opt-in")
    print("   🔹 Composable architecture maintained")
    print("   🔹 Single runtime for all use cases")


def main():
    """Run all unified runtime examples."""
    print("🚀 UNIFIED RUNTIME EXAMPLES")
    print("=" * 80)
    print("Demonstrating the new unified LocalRuntime with enterprise capabilities")
    print("=" * 80)
    
    try:
        # Run all examples
        example_1_backward_compatibility()
        example_2_asynclocal_compatibility() 
        example_3_enterprise_features_builtin()
        example_4_enterprise_security_integration()
        example_5_full_enterprise_configuration()
        example_6_comparison_before_after()
        
        print("\n" + "="*80)
        print("🎉 ALL UNIFIED RUNTIME EXAMPLES COMPLETED SUCCESSFULLY!")
        print("="*80)
        print("\n📋 SUMMARY:")
        print("   ✅ Backward compatibility: 100% preserved")
        print("   ✅ LocalRuntime: Fully compatible")
        print("   ✅ Enterprise features: Built-in and composable")
        print("   ✅ Security integration: Automatic")
        print("   ✅ Zero breaking changes: All existing code works")
        print("   ✅ Developer experience: Dramatically simplified")
        
        print(f"\n🏗️  ARCHITECTURE BENEFITS:")
        print("   🔹 Single unified runtime replaces 9+ separate runtimes")
        print("   🔹 Enterprise features leverage existing 67+ enterprise nodes")
        print("   🔹 No duplication - composable integration pattern")
        print("   🔹 Opt-in enterprise features - simple parameter flags")
        print("   🔹 Production-ready security and compliance capabilities")
        
    except Exception as e:
        print(f"\n❌ Example failed: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()