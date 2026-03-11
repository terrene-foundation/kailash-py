#!/usr/bin/env python3
"""
NEXUS COMPREHENSIVE DEMO: Zero FastAPI Coding Required (v1.3.0)
===============================================================

This example demonstrates that Nexus requires ZERO FastAPI coding and provides
complete high-level workflow-to-API automation through SDK integration.

Key Findings:
- Single workflow registration -> API + CLI + MCP exposure automatically
- Zero-config setup with enterprise defaults
- Handler pattern for simple workflows (bypasses PythonCodeNode sandbox)
- Enterprise auth via NexusAuthPlugin (not app.auth.*)
- Uses SDK's enterprise gateway (no custom FastAPI needed)
- Production-ready features enabled by default
- Progressive enhancement for complex scenarios

Usage:
    cd packages/kailash-nexus
    python examples/comprehensive_demo.py

Then test:
- API: curl http://localhost:8000/workflows/data-processor/execute -X POST -H "Content-Type: application/json" -d '{"data": [1,2,3,4,5]}'
- MCP: AI agents can call the workflow directly
- CLI: nexus run data-processor --data '[1,2,3,4,5]'
"""

import os
import sys

# Add src to Python path so we can import nexus
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import json

from nexus import Nexus

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

# ==============================================================================
# EXAMPLE 1: ZERO-CONFIG DATA PROCESSING WORKFLOW (WorkflowBuilder)
# ==============================================================================


def create_data_processing_workflow():
    """Create a data processing workflow with multiple nodes."""
    workflow = WorkflowBuilder()

    # Input validation node -- uses try/except for API parameter access
    validation_code = """
try:
    data = data
except NameError:
    data = []

def validate_input(data):
    if not isinstance(data, list):
        raise ValueError("Data must be a list")
    if len(data) == 0:
        raise ValueError("Data cannot be empty")
    if not all(isinstance(x, (int, float)) for x in data):
        raise ValueError("All data items must be numbers")
    return {"validated_data": data}

result = validate_input(data)
"""
    workflow.add_node("PythonCodeNode", "validator", {"code": validation_code.strip()})

    # Data processing node
    processing_code = """
try:
    validated_data = validated_data
except NameError:
    validated_data = []

def process_data(validated_data):
    data = validated_data
    result = {
        "original": data,
        "count": len(data),
        "sum": sum(data),
        "average": sum(data) / len(data),
        "min": min(data),
        "max": max(data),
        "processed": [x * 2 for x in data]  # Double each value
    }
    return {"result": result}

result = process_data(validated_data)
"""
    workflow.add_node("PythonCodeNode", "processor", {"code": processing_code.strip()})

    # Results formatting node
    formatting_code = """
try:
    data_result = result
except NameError:
    data_result = {}

def format_results(data_result):
    formatted = {
        "status": "success",
        "summary": f"Processed {data_result['count']} numbers",
        "statistics": {
            "sum": data_result["sum"],
            "average": round(data_result["average"], 2),
            "range": f"{data_result['min']} - {data_result['max']}"
        },
        "original_data": data_result["original"],
        "processed_data": data_result["processed"]
    }
    return {"formatted_result": formatted}

result = format_results(data_result)
"""
    workflow.add_node("PythonCodeNode", "formatter", {"code": formatting_code.strip()})

    # Connect the workflow pipeline
    workflow.add_connection(
        "validator", "validated_data", "processor", "validated_data"
    )
    workflow.add_connection("processor", "result", "formatter", "result")

    return workflow


# ==============================================================================
# EXAMPLE 2: HANDLER PATTERN (recommended for v1.2.0+)
# ==============================================================================
# Handlers bypass PythonCodeNode sandbox restrictions, support any import,
# and derive parameters automatically from function signatures.
# See register_handlers() below for usage.


# ==============================================================================
# EXAMPLE 3: DATABASE SIMULATION WORKFLOW (WorkflowBuilder)
# ==============================================================================


def create_user_management_workflow():
    """Create a user management workflow with database simulation."""
    workflow = WorkflowBuilder()

    # User data preparation -- uses try/except for API parameter access
    prep_code = """
try:
    name = name
except NameError:
    name = ''
try:
    email = email
except NameError:
    email = ''
try:
    age = age
except NameError:
    age = None

def prepare_user_data(name, email, age=None):
    if not name or not name.strip():
        raise ValueError("Name is required")
    if not email or "@" not in email:
        raise ValueError("Valid email is required")

    user_data = {
        "name": name.strip(),
        "email": email.strip().lower(),
        "age": int(age) if age else None,
        "created_at": "2025-01-15T10:00:00Z"  # Simulated timestamp
    }

    return {"user_data": user_data}

result = prepare_user_data(name, email, age)
"""
    workflow.add_node("PythonCodeNode", "data_prep", {"code": prep_code.strip()})

    # Simulate database operation
    db_code = """
try:
    user_data = user_data
except NameError:
    user_data = {}

def simulate_database_insert(user_data):
    # In production, use DataFlow for real database operations
    user = user_data

    # Simulate database insertion
    user["user_id"] = f"user_{hash(user['email']) % 10000}"

    return {
        "operation": "user_created",
        "user": user,
        "database": "users_db",
        "table": "users"
    }

result = simulate_database_insert(user_data)
"""
    workflow.add_node("PythonCodeNode", "database", {"code": db_code.strip()})

    # Response formatting
    response_code = """
try:
    operation = operation
except NameError:
    operation = ''
try:
    user = user
except NameError:
    user = {}
try:
    database = database
except NameError:
    database = ''
try:
    table = table
except NameError:
    table = ''

def format_response(operation, user, database, table):
    return {
        "status": "success",
        "operation": operation,
        "user_created": {
            "user_id": user["user_id"],
            "name": user["name"],
            "email": user["email"],
            "age": user["age"]
        },
        "database_info": {
            "database": database,
            "table": table,
            "timestamp": user["created_at"]
        }
    }

result = format_response(operation, user, database, table)
"""
    workflow.add_node("PythonCodeNode", "formatter", {"code": response_code.strip()})

    # Connect database workflow
    workflow.add_connection("data_prep", "user_data", "database", "user_data")
    workflow.add_connection("database", "operation", "formatter", "operation")
    workflow.add_connection("database", "user", "formatter", "user")
    workflow.add_connection("database", "database", "formatter", "database")
    workflow.add_connection("database", "table", "formatter", "table")

    return workflow


# ==============================================================================
# MAIN NEXUS APPLICATION - ZERO FASTAPI CODING REQUIRED!
# ==============================================================================


def register_handlers(app: Nexus):
    """Register handler-based workflows (recommended for v1.2.0+).

    Handlers are simpler than WorkflowBuilder for straightforward logic.
    They bypass PythonCodeNode sandbox restrictions and support any import.
    """

    @app.handler("greeting", description="Simple greeting handler", tags=["utility"])
    async def greeting(name: str = "World", message: str = "Hello") -> dict:
        """Greeting handler available on API, CLI, and MCP simultaneously."""
        return {"greeting": f"{message}, {name}!", "name": name, "message": message}

    @app.handler("health-detail", description="Detailed health info")
    async def health_detail() -> dict:
        """Return detailed platform info."""
        return {
            "status": "healthy",
            "version": "1.3.0",
            "channels": ["api", "cli", "mcp"],
        }


def main():
    """
    Main application demonstrating Nexus capabilities.

    This is the ENTIRE setup required - NO FastAPI coding needed!
    """

    print("Starting Nexus Comprehensive Demo (v1.3.0)")
    print("=" * 50)

    # STEP 1: Initialize Nexus with zero configuration
    # This automatically sets up:
    # - Enterprise FastAPI server via create_gateway()
    # - WebSocket MCP server for AI agents
    # - CLI interface preparation
    # - Health monitoring and durability
    app = Nexus()

    print("Nexus initialized with zero configuration")

    # STEP 2: Register workflows - Single call exposes on ALL channels
    print("\nRegistering workflows...")

    # Data processing workflow (WorkflowBuilder pattern)
    data_workflow = create_data_processing_workflow()
    app.register("data-processor", data_workflow)
    print("  data-processor: Registered -> API + CLI + MCP")

    # Database simulation workflow (WorkflowBuilder pattern)
    db_workflow = create_user_management_workflow()
    app.register("user-manager", db_workflow)
    print("  user-manager: Registered -> API + CLI + MCP")

    # Handler-based workflows (recommended for simple logic)
    register_handlers(app)
    print("  greeting: Registered -> API + CLI + MCP (handler)")
    print("  health-detail: Registered -> API + CLI + MCP (handler)")

    # STEP 3: Optional enterprise auth via NexusAuthPlugin (v1.3.0)
    #
    # IMPORTANT: There is NO app.auth.strategy attribute.
    # Authentication is configured entirely through the plugin system:
    #
    # from nexus.auth.plugin import NexusAuthPlugin
    # from nexus.auth import JWTConfig
    #
    # auth = NexusAuthPlugin.basic_auth(
    #     jwt=JWTConfig(secret=os.environ["JWT_SECRET"]),
    # )
    # app.add_plugin(auth)
    #
    # CORS is configured via the constructor:
    # app = Nexus(cors_origins=["http://localhost:3000"])

    print("\n  Enterprise auth: available via NexusAuthPlugin (see code comments)")

    # STEP 4: Start all channels with single command
    print("\nStarting multi-channel platform...")
    print("This single command starts:")
    print("  - REST API server (enterprise-grade)")
    print("  - WebSocket MCP server (for AI agents)")
    print("  - CLI interface (for command-line use)")
    print("  - Health monitoring and metrics")

    try:
        app.start()

        print("\n" + "=" * 60)
        print("NEXUS PLATFORM RUNNING - ZERO FASTAPI CODING REQUIRED!")
        print("=" * 60)

        # Check platform health
        health = app.health_check()
        print(f"\nPlatform Status: {health.get('status', 'unknown')}")

        print("\nAvailable Interfaces:")
        print("  REST API: http://localhost:8000")
        print("    POST /workflows/data-processor/execute")
        print("    POST /workflows/greeting/execute")
        print("    POST /workflows/user-manager/execute")
        print("    POST /workflows/health-detail/execute")
        print("    GET  /workflows (list all workflows)")
        print("    GET  /health (health check)")

        print("\n  MCP Interface: ws://localhost:3001")
        print("    AI agents can call workflows directly")
        print("    Real-time WebSocket communication")
        print("    Tool discovery and execution")

        print("\n  CLI Interface: nexus run <workflow>")
        print("    nexus run data-processor --data '[1,2,3,4,5]'")
        print("    nexus run greeting --name 'Alice'")
        print("    nexus run user-manager --name 'John' --email 'john@example.com'")

        print("\nTest Commands:")
        print("  # Test data processor")
        print(
            "  curl -X POST http://localhost:8000/workflows/data-processor/execute \\"
        )
        print('    -H "Content-Type: application/json" \\')
        print("    -d '{\"data\": [1, 2, 3, 4, 5]}'")

        print("\n  # Test greeting handler")
        print("  curl -X POST http://localhost:8000/workflows/greeting/execute \\")
        print('    -H "Content-Type: application/json" \\')
        print('    -d \'{"name": "Alice", "message": "Welcome"}\'')

        print("\n  # Test user manager")
        print("  curl -X POST http://localhost:8000/workflows/user-manager/execute \\")
        print('    -H "Content-Type: application/json" \\')
        print('    -d \'{"name": "Alice", "email": "alice@example.com", "age": 30}\'')

        print("\n" + "=" * 60)
        print("KEY INSIGHT: This entire multi-channel platform required:")
        print("   NO FastAPI route definitions")
        print("   NO custom middleware setup")
        print("   NO API endpoint coding")
        print("   NO WebSocket handling")
        print("   NO CLI command setup")
        print("   ONLY workflow definitions + app.register() / @app.handler() calls!")
        print("=" * 60)

        print("\nPress Ctrl+C to stop the platform...")

        # Keep running until interrupted
        import signal
        import time

        def signal_handler(sig, frame):
            print("\n\nShutting down Nexus platform...")
            try:
                app.stop()
                print("Platform stopped gracefully")
            except Exception as e:
                print(f"Shutdown warning: {e}")
            exit(0)

        signal.signal(signal.SIGINT, signal_handler)

        while True:
            time.sleep(1)

    except Exception as e:
        print(f"Error starting platform: {e}")
        print(f"   Error type: {type(e).__name__}")
        print("\nThis might be due to:")
        print("  - Ports 8000 or 3001 already in use")
        print("  - Missing dependencies")
        print("  - Configuration issues")

        # Let's try to get more specific error info
        import traceback

        print("\nFull error traceback:")
        traceback.print_exc()

        return False

    return True


if __name__ == "__main__":
    success = main()
    if not success:
        exit(1)
