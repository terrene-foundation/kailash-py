"""
Minimal reproduction of AgentCreateNode failure with ErrorEnhancer API mismatch.

Bug Report: DataFlow 0.9.0 - AgentCreateNode fails after UserCreateNode succeeds
Root Cause: ErrorEnhancer.enhance_missing_required_field() receives unexpected 'expected_fields' argument
Expected: 'operation' parameter (3rd positional)
Actual: 'expected_fields' parameter passed instead

File: apps/kailash-dataflow/src/dataflow/core/nodes.py:1258-1263
"""

import asyncio
import sys
from datetime import datetime

from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from dataflow import DataFlow


async def test_parameter_name_collision():
    """
    Test if Agent model with 'model_name' field causes CreateNode failure.

    Expected Result: FAILURE with ErrorEnhancer API mismatch
    """
    print("=" * 80)
    print("TESTING: AgentCreateNode with model_name Field Collision")
    print("=" * 80)

    # Step 1: Create DataFlow with SQLite
    print("\nStep 1: Creating DataFlow instances...")
    auth_db = DataFlow(
        ":memory:",
        instance_name="auth",
        auto_migrate=False,
        existing_schema_mode=True,
        skip_registry=True,
        enable_model_persistence=False,
    )

    agent_db = DataFlow(
        ":memory:",
        instance_name="agent",
        auto_migrate=False,
        existing_schema_mode=True,
        skip_registry=True,
        enable_model_persistence=False,
    )

    # Step 2: Define User model (auth_db)
    print("\nStep 2: Defining User model (auth_db)...")

    @auth_db.model
    class User:
        id: str
        user_type: str
        username: str
        email: str
        name: str
        role: str
        department: str
        location: str
        job_level: str
        created_at: datetime
        updated_at: datetime

    # Step 3: Define Agent model with model_name field (agent_db)
    print("\nStep 3: Defining Agent model with 'model_name' field (agent_db)...")

    @agent_db.model
    class Agent:
        id: str
        name: str
        description: str
        capabilities: str
        model_provider: str
        model_name: str  # ⚠️ POTENTIAL CONFLICT with DataFlow internal parameter
        system_prompt: str
        parameters: str
        status: str
        rbac_roles: str
        rbac_departments: str
        created_by: str
        metadata_json: str
        icon: str
        color: str
        created_at: datetime
        updated_at: datetime

    # Step 4: Initialize DataFlow instances
    print("\nStep 4: Initializing DataFlow instances...")
    await auth_db.initialize()
    await agent_db.initialize()

    # Step 5: Create User (should succeed)
    print("\nStep 5: Creating User (auth_db)...")
    timestamp = int(datetime.utcnow().timestamp() * 1000000)
    now = datetime.utcnow().isoformat()
    user_id = f"test_user_{timestamp}"

    workflow_user = WorkflowBuilder()
    workflow_user.add_node(
        "UserCreateNode",
        "create_user",
        {
            "db_instance": "auth",
            "model_name": "User",  # DataFlow internal parameter
            "id": user_id,
            "user_type": "coach",
            "username": f"testuser_{timestamp}",
            "email": f"test_{timestamp}@example.com",
            "name": "Test User",
            "role": "coach",
            "department": "Engineering",
            "location": "Singapore",
            "job_level": "IC3",
            "created_at": now,
            "updated_at": now,
        },
    )

    runtime = AsyncLocalRuntime()

    try:
        results_user, _ = await runtime.execute_workflow_async(
            workflow_user.build(), inputs={}
        )
        print(f"   ✅ User created successfully: {results_user['create_user']['id']}")
    except Exception as e:
        print(f"   ❌ User creation failed: {e}")
        return

    await asyncio.sleep(0.5)

    # Step 6: Create Agent (expected to fail)
    print("\nStep 6: Creating Agent (agent_db) - EXPECTING FAILURE...")
    agent_id = f"test_agent_{timestamp}"

    workflow_agent = WorkflowBuilder()
    workflow_agent.add_node(
        "AgentCreateNode",
        "create_agent",
        {
            "db_instance": "agent",
            "id": agent_id,
            "name": "Test Agent",
            "description": "Test coaching agent",
            "capabilities": '["search", "analysis"]',
            "model_provider": "azure_openai",
            "model_name": "gpt-4",  # Agent field
            "system_prompt": "You are a helpful coach.",
            "parameters": '{"temperature": 0.7}',
            "status": "active",
            "rbac_roles": '["coach"]',
            "rbac_departments": '["All"]',
            "created_by": user_id,
            "created_at": now,
            "updated_at": now,
            "metadata_json": "{}",
            "icon": "robot",
            "color": "#3B82F6",
        },
    )

    try:
        results_agent, _ = await runtime.execute_workflow_async(
            workflow_agent.build(), inputs={}
        )
        print(
            f"   ❌ BUG NOT REPRODUCED - Agent created successfully: {results_agent.get('create_agent', {}).get('id', 'UNKNOWN')}"
        )
        print("\n" + "=" * 80)
        print("STATUS: Bug may have been fixed")
        print("=" * 80)
    except Exception as e:
        error_str = str(e)
        if "unexpected keyword argument 'expected_fields'" in error_str:
            print("   ✅ BUG REPRODUCED - ErrorEnhancer API mismatch")
            print(f"\nError Type: {type(e).__name__}")
            print(f"Error Message: {error_str}")
            print("\n" + "=" * 80)
            print("ROOT CAUSE CONFIRMED")
            print("=" * 80)
            print("\nFile: apps/kailash-dataflow/src/dataflow/core/nodes.py:1258-1263")
            print("\nMethod definition expects:")
            print("  def enhance_missing_required_field(")
            print("      cls,")
            print("      node_id: str,")
            print("      field_name: str,")
            print("      operation: str,  # ← Expects this")
            print("      model_name: Optional[str] = None,")
            print("      original_error: Optional[Exception] = None,")
            print("  )")
            print("\nBut call site passes:")
            print("  raise _error_enhancer().enhance_missing_required_field(")
            print("      node_id=...,")
            print("      field_name=...,")
            print("      model_name=...,")
            print("      expected_fields=field_names,  # ← Wrong parameter!")
            print("  )")
            print("\n" + "=" * 80)
        else:
            print("   ⚠️ Different error occurred")
            print(f"\nError Type: {type(e).__name__}")
            print(f"Error Message: {error_str}")
            import traceback

            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_parameter_name_collision())
