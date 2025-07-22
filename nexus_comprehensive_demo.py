#!/usr/bin/env python3
"""
NEXUS COMPREHENSIVE DEMO: Zero FastAPI Coding Required
=====================================================

This example demonstrates that Nexus requires ZERO FastAPI coding and provides
complete high-level workflow-to-API automation through SDK integration.

Key Findings:
- Single workflow registration → API + CLI + MCP exposure automatically
- Zero-config setup with enterprise defaults 
- Uses SDK's enterprise gateway (no custom FastAPI needed)
- Production-ready features enabled by default
- Progressive enhancement for complex scenarios

Run: python nexus_comprehensive_demo.py
Then test:
- API: curl http://localhost:8000/workflows/data-processor/execute -X POST -H "Content-Type: application/json" -d '{"data": [1,2,3,4,5]}'
- MCP: AI agents can call the workflow directly
- CLI: nexus run data-processor --data '[1,2,3,4,5]'
"""

from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
import json

# ==============================================================================
# EXAMPLE 1: ZERO-CONFIG DATA PROCESSING WORKFLOW
# ==============================================================================

def create_data_processing_workflow():
    """Create a data processing workflow with multiple nodes."""
    workflow = WorkflowBuilder()
    
    # Input validation node
    validation_code = """
def validate_input(data):
    if not isinstance(data, list):
        raise ValueError("Data must be a list")
    if len(data) == 0:
        raise ValueError("Data cannot be empty")
    if not all(isinstance(x, (int, float)) for x in data):
        raise ValueError("All data items must be numbers")
    return {"validated_data": data}
"""
    workflow.add_node("PythonCodeNode", "validator", {
        "code": validation_code.strip()
    })
    
    # Data processing node
    processing_code = """
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
"""
    workflow.add_node("PythonCodeNode", "processor", {
        "code": processing_code.strip()
    })
    
    # Results formatting node
    formatting_code = """
def format_results(result):
    data_result = result
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
"""
    workflow.add_node("PythonCodeNode", "formatter", {
        "code": formatting_code.strip()
    })
    
    # Connect the workflow pipeline
    workflow.add_connection("validator", "validated_data", "processor", "validated_data")
    workflow.add_connection("processor", "result", "formatter", "result")
    
    return workflow.build()

# ==============================================================================
# EXAMPLE 2: AI-POWERED DOCUMENT ANALYSIS WORKFLOW  
# ==============================================================================

def create_ai_document_workflow():
    """Create an AI-powered document analysis workflow."""
    workflow = WorkflowBuilder()
    
    # Document preprocessing
    preprocess_code = """
def preprocess_document(text, max_length=1000):
    if not text or not text.strip():
        raise ValueError("Document text cannot be empty")
    
    # Clean and truncate text
    cleaned = text.strip()
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length] + "..."
    
    return {
        "processed_text": cleaned,
        "original_length": len(text),
        "processed_length": len(cleaned),
        "truncated": len(text) > max_length
    }
"""
    workflow.add_node("PythonCodeNode", "preprocessor", {
        "code": preprocess_code.strip()
    })
    
    # AI Analysis using LLM
    workflow.add_node("LLMAgentNode", "analyzer", {
        "model": "gpt-4",
        "system_prompt": """You are a document analysis expert. Analyze the given text and provide:
        1. Summary (max 2 sentences)
        2. Key topics (max 5 topics)
        3. Sentiment (positive/negative/neutral)
        4. Readability level (easy/medium/hard)
        5. Word count estimate""",
        "use_real_mcp": True  # Real AI execution by default
    })
    
    # Results compilation
    compile_code = """
def compile_analysis(processed_text, analysis_result):
    # Extract AI analysis from LLM response
    ai_analysis = analysis_result.get("response", "Analysis not available")
    
    return {
        "document_info": {
            "original_length": processed_text["original_length"],
            "processed_length": processed_text["processed_length"],
            "truncated": processed_text["truncated"]
        },
        "ai_analysis": ai_analysis,
        "processed_text_preview": processed_text["processed_text"][:200] + "..." if len(processed_text["processed_text"]) > 200 else processed_text["processed_text"]
    }
"""
    workflow.add_node("PythonCodeNode", "compiler", {
        "code": compile_code.strip()
    })
    
    # Connect the AI workflow
    workflow.add_connection("preprocessor", "processed_text", "analyzer", "message")
    workflow.add_connection("preprocessor", "processed_text", "compiler", "processed_text") 
    workflow.add_connection("analyzer", "analysis_result", "compiler", "analysis_result")
    
    return workflow.build()

# ==============================================================================
# EXAMPLE 3: DATABASE WORKFLOW WITH DATAFLOW INTEGRATION
# ==============================================================================

def create_database_workflow():
    """Create a database workflow using DataFlow integration."""
    workflow = WorkflowBuilder()
    
    # User data preparation
    prep_code = """
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
"""
    workflow.add_node("PythonCodeNode", "data_prep", {
        "code": prep_code.strip()
    })
    
    # Simulate database operation (in real scenario, use AsyncSQLDatabaseNode)
    db_code = """
def simulate_database_insert(user_data):
    # In production, this would be AsyncSQLDatabaseNode with real database
    user = user_data
    
    # Simulate database insertion
    user["user_id"] = f"user_{hash(user['email']) % 10000}"
    
    return {
        "operation": "user_created",
        "user": user,
        "database": "users_db",
        "table": "users"
    }
"""
    workflow.add_node("PythonCodeNode", "database", {
        "code": db_code.strip()
    })
    
    # Response formatting
    response_code = """
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
"""
    workflow.add_node("PythonCodeNode", "formatter", {
        "code": response_code.strip()
    })
    
    # Connect database workflow
    workflow.add_connection("data_prep", "user_data", "database", "user_data")
    workflow.add_connection("database", "operation", "formatter", "operation")
    workflow.add_connection("database", "user", "formatter", "user")
    workflow.add_connection("database", "database", "formatter", "database")
    workflow.add_connection("database", "table", "formatter", "table")
    
    return workflow.build()

# ==============================================================================
# MAIN NEXUS APPLICATION - ZERO FASTAPI CODING REQUIRED!
# ==============================================================================

def main():
    """
    Main application demonstrating Nexus capabilities.
    
    This is the ENTIRE setup required - NO FastAPI coding needed!
    """
    
    print("🚀 Starting Nexus Comprehensive Demo")
    print("=" * 50)
    
    # STEP 1: Initialize Nexus with zero configuration
    # This automatically sets up:
    # - Enterprise FastAPI server via create_gateway()
    # - WebSocket MCP server for AI agents
    # - CLI interface preparation
    # - Health monitoring and durability
    app = Nexus()
    
    print("✅ Nexus initialized with zero configuration")
    
    # STEP 2: Register workflows - Single call exposes on ALL channels
    print("\n📝 Registering workflows...")
    
    # Data processing workflow
    data_workflow = create_data_processing_workflow()
    app.register("data-processor", data_workflow)
    print("  ✅ data-processor: Registered → API + CLI + MCP")
    
    # AI document analysis workflow  
    ai_workflow = create_ai_document_workflow()
    app.register("document-analyzer", ai_workflow)
    print("  ✅ document-analyzer: Registered → API + CLI + MCP")
    
    # Database workflow
    db_workflow = create_database_workflow()
    app.register("user-manager", db_workflow)
    print("  ✅ user-manager: Registered → API + CLI + MCP")
    
    # STEP 3: Optional enterprise features (progressive enhancement)
    print("\n🔒 Enabling enterprise features...")
    app.auth.strategy = "rbac"  # Role-based access control
    app.monitoring.interval = 30  # Performance monitoring
    app.api.cors_enabled = True  # CORS for web clients
    
    # Enable features (optional - works fine without these)
    try:
        app.enable_monitoring()
        print("  ✅ Performance monitoring enabled")
    except Exception as e:
        print(f"  ⚠️ Monitoring setup: {e}")
    
    try:
        app.enable_auth()
        print("  ✅ Authentication system enabled")
    except Exception as e:
        print(f"  ⚠️ Auth setup: {e}")
    
    # STEP 4: Start all channels with single command
    print("\n🌐 Starting multi-channel platform...")
    print("This single command starts:")
    print("  • REST API server (enterprise-grade)")
    print("  • WebSocket MCP server (for AI agents)")  
    print("  • CLI interface (for command-line use)")
    print("  • Health monitoring and metrics")
    print("  • Auto-discovery and hot-reload")
    
    try:
        app.start()
        
        print("\n" + "=" * 60)
        print("🎉 NEXUS PLATFORM RUNNING - ZERO FASTAPI CODING REQUIRED!")
        print("=" * 60)
        
        print("\n📡 Available Interfaces:")
        print("  🌐 REST API: http://localhost:8000")
        print("    • POST /workflows/data-processor/execute")
        print("    • POST /workflows/document-analyzer/execute") 
        print("    • POST /workflows/user-manager/execute")
        print("    • GET  /workflows (list all workflows)")
        print("    • GET  /health (health check)")
        
        print("\n  🤖 MCP Interface: ws://localhost:3001")
        print("    • AI agents can call workflows directly")
        print("    • Real-time WebSocket communication")
        print("    • Tool discovery and execution")
        
        print("\n  ⌨️  CLI Interface: nexus run <workflow>")
        print("    • nexus run data-processor --data '[1,2,3,4,5]'")
        print("    • nexus run document-analyzer --text 'Hello world'")
        print("    • nexus run user-manager --name 'John' --email 'john@example.com'")
        
        print("\n🧪 Test Commands:")
        print("  # Test data processor")
        print('  curl -X POST http://localhost:8000/workflows/data-processor/execute \\')
        print('    -H "Content-Type: application/json" \\')
        print('    -d \'{"data": [1, 2, 3, 4, 5]}\'')
        
        print("\n  # Test document analyzer")
        print('  curl -X POST http://localhost:8000/workflows/document-analyzer/execute \\')
        print('    -H "Content-Type: application/json" \\')
        print('    -d \'{"text": "This is a sample document for analysis."}\'')
        
        print("\n  # Test user manager")
        print('  curl -X POST http://localhost:8000/workflows/user-manager/execute \\')
        print('    -H "Content-Type: application/json" \\')
        print('    -d \'{"name": "Alice", "email": "alice@example.com", "age": 30}\'')
        
        print("\n" + "=" * 60)
        print("💡 KEY INSIGHT: This entire multi-channel platform required:")
        print("   ❌ ZERO FastAPI route definitions")
        print("   ❌ ZERO custom middleware setup") 
        print("   ❌ ZERO API endpoint coding")
        print("   ❌ ZERO WebSocket handling")
        print("   ❌ ZERO CLI command setup")
        print("   ✅ ONLY workflow definitions + app.register() calls!")
        print("=" * 60)
        
        print("\n⏹️  Press Ctrl+C to stop the platform...")
        
        # Keep running until interrupted
        import signal
        import time
        
        def signal_handler(sig, frame):
            print("\n\n🛑 Shutting down Nexus platform...")
            app.stop()
            print("✅ Platform stopped gracefully")
            exit(0)
            
        signal.signal(signal.SIGINT, signal_handler)
        
        while True:
            time.sleep(1)
            
    except Exception as e:
        print(f"❌ Error starting platform: {e}")
        print("\n🔍 This might be due to:")
        print("  • Ports 8000 or 3001 already in use") 
        print("  • Missing dependencies (ensure 'pip install kailash[nexus]')")
        print("  • Configuration issues")
        return False
    
    return True

if __name__ == "__main__":
    success = main()
    if not success:
        exit(1)