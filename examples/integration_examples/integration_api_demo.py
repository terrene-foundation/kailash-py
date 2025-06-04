#!/usr/bin/env python3
"""
Comprehensive API Integration Demo for Kailash SDK

This example demonstrates all API integration capabilities:
1. Workflow API Wrapper - Expose any workflow as REST API
2. API Testing - Direct execution vs API execution
3. Real Examples - Filter workflow and RAG workflow
4. Deployment Options - Development, production, Docker

Run with --help to see all options.
"""

import argparse
import asyncio

from kailash.api.workflow_api import WorkflowAPI, create_workflow_api
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder
from kailash.workflow.graph import Workflow


class APIDemo:
    """Main demo class for API integration examples."""

    def __init__(self):
        """Initialize the demo."""
        self.runtime = LocalRuntime()

    def create_filter_workflow(self) -> Workflow:
        """Create a simple filter workflow for demonstration."""
        workflow = Workflow(
            workflow_id="filter_demo",
            name="Filter Demo",
            version="1.0.0",
            description="Simple workflow that filters data",
        )

        # Add filter node
        workflow.add_node("filter_data", "Filter")

        return workflow

    def create_rag_workflow(self) -> WorkflowBuilder:
        """Create a hierarchical RAG workflow."""
        builder = WorkflowBuilder()

        # Add nodes using builder pattern
        builder.add_node("DocumentSourceNode", "doc_source")
        builder.add_node("QuerySourceNode", "query_source")
        builder.add_node(
            "HierarchicalChunkerNode", "chunker", {"chunk_size": 200, "overlap": 50}
        )
        builder.add_node("ChunkTextExtractorNode", "chunk_extractor")
        builder.add_node("QueryTextWrapperNode", "query_wrapper")
        builder.add_node(
            "EmbeddingGeneratorNode",
            "chunk_embedder",
            {"provider": "mock", "model": "text-embedding-ada-002"},
        )
        builder.add_node(
            "EmbeddingGeneratorNode",
            "query_embedder",
            {"provider": "mock", "model": "text-embedding-ada-002"},
        )
        builder.add_node(
            "RelevanceScorerNode", "scorer", {"top_k": 3, "similarity_method": "cosine"}
        )
        builder.add_node("ContextFormatterNode", "formatter")
        builder.add_node("LLMAgentNode", "llm", {"provider": "mock", "model": "gpt-4"})

        # Add connections
        builder.add_connection("doc_source", "chunker")
        builder.add_connection("chunker", "chunk_extractor")
        builder.add_connection("chunk_extractor", "chunk_embedder")
        builder.add_connection("query_source", "query_wrapper")
        builder.add_connection("query_wrapper", "query_embedder")
        builder.add_connection("chunk_embedder", "scorer", {"embeddings": "chunk_embeddings"})
        builder.add_connection("query_embedder", "scorer", {"embedding": "query_embedding"})
        builder.add_connection("scorer", "formatter", {"scores": "relevant_chunks"})
        builder.add_connection("query_source", "formatter", {"text": "query"})
        builder.add_connection("formatter", "llm")

        # Set metadata
        builder.set_metadata(
            {
                "workflow_id": "rag_demo",
                "name": "RAG Demo",
                "version": "1.0.0",
                "description": "Hierarchical RAG workflow",
            }
        )

        return builder

    def demo_simple_workflow(self):
        """Demonstrate simple workflow execution and API wrapping."""
        print("\n=== Simple Workflow Demo (Filter) ===")

        workflow = self.create_filter_workflow()

        # Test data
        test_data = {
            "filter_data": {
                "data": [1, 5, 10, 3, 8, 2, 7, 9, 4, 6],
                "operator": ">",
                "value": 5,
            }
        }

        # 1. Direct execution
        print("\n1. Direct Execution:")
        print(f"   Input: {test_data['filter_data']['data']}")
        print("   Filter: > 5")

        try:
            result = self.runtime.execute(workflow, parameters=test_data)
            if isinstance(result, tuple):
                result = result[0]
            filtered = result.get("filter_data", {}).get("filtered_data", [])
            print(f"   Result: {filtered}")
        except Exception as e:
            print(f"   Error: {e}")

        # 2. API wrapper
        print("\n2. API Wrapper:")
        api = WorkflowAPI(workflow, app_name="Filter API")
        print(f"   Created API for workflow: {api.workflow_id}")
        print("   Endpoints: /execute, /workflow/info, /health")

        # 3. Example usage
        print("\n3. Example API Usage:")
        print("   ```bash")
        print("   # Start server")
        print("   python integration_api_demo.py --serve simple")
        print()
        print("   # Execute workflow")
        print("   curl -X POST http://localhost:8000/execute \\")
        print("     -H 'Content-Type: application/json' \\")
        print("     -d '{")
        print('       "inputs": {')
        print('         "filter_data": {')
        print('           "data": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],')
        print('           "operator": ">=",')
        print('           "value": 5')
        print("         }")
        print("       }")
        print("     }'")
        print("   ```")

        return api

    def demo_complex_workflow(self):
        """Demonstrate complex RAG workflow with API wrapper."""
        print("\n=== Complex Workflow Demo (RAG) ===")

        builder = self.create_rag_workflow()

        # Create specialized RAG API
        api = create_workflow_api(
            builder,
            api_type="rag",
            app_name="RAG API",
            description="Hierarchical RAG workflow API",
        )

        print("\n1. Created specialized RAG API")
        print("   Additional endpoints: /documents, /query")

        print("\n2. Example RAG Query:")
        print("   ```bash")
        print("   curl -X POST http://localhost:8001/query \\")
        print("     -H 'Content-Type: application/json' \\")
        print("     -d '{")
        print('       "query": "What is machine learning?",')
        print('       "top_k": 3,')
        print('       "temperature": 0.7')
        print("     }'")
        print("   ```")

        print("\n3. Deployment Options:")
        print("   Development:  api.run(reload=True)")
        print("   Production:   api.run(workers=4)")
        print("   Docker:       See Dockerfile example")

        return api

    def demo_api_patterns(self):
        """Demonstrate various API patterns and configurations."""
        print("\n=== API Patterns & Best Practices ===")

        print("\n1. Minimal Deployment (3 lines):")
        print("   ```python")
        print("   workflow = create_your_workflow()")
        print("   api = WorkflowAPI(workflow)")
        print("   api.run()")
        print("   ```")

        print("\n2. Custom Endpoints:")
        print("   ```python")
        print("   @api.app.get('/status')")
        print("   async def custom_status():")
        print("       return {'custom': 'endpoint'}")
        print("   ```")

        print("\n3. Authentication:")
        print("   ```python")
        print("   from fastapi.security import HTTPBearer")
        print("   security = HTTPBearer()")
        print("   # Add to endpoints with Depends(security)")
        print("   ```")

        print("\n4. CORS Configuration:")
        print("   ```python")
        print("   from fastapi.middleware.cors import CORSMiddleware")
        print("   api.app.add_middleware(CORSMiddleware, allow_origins=['*'])")
        print("   ```")

        print("\n5. Production Deployment:")
        print("   - Use environment variables for configuration")
        print("   - Enable HTTPS with SSL certificates")
        print("   - Set up reverse proxy (nginx/traefik)")
        print("   - Use process manager (supervisor/systemd)")
        print("   - Monitor with APM tools")

    async def test_api_execution(self, api: WorkflowAPI):
        """Test API execution programmatically."""
        print("\n=== Testing API Execution ===")

        from kailash.api.workflow_api import WorkflowRequest

        # Create test request
        request = WorkflowRequest(
            inputs={
                "filter_data": {
                    "data": ["apple", "banana", "apricot", "cherry"],
                    "operator": "contains",
                    "value": "a",
                }
            },
            mode="sync",
        )

        try:
            result = await api._execute_sync(request)
            print("✓ API execution successful!")
            print(f"  Execution time: {result.execution_time:.3f}s")
        except Exception as e:
            print(f"✗ API execution failed: {e}")

    def run_interactive(self):
        """Run interactive demo menu."""
        while True:
            print("\n=== Kailash API Integration Demo ===")
            print("1. Simple Workflow Demo (Filter)")
            print("2. Complex Workflow Demo (RAG)")
            print("3. API Patterns & Best Practices")
            print("4. Test API Execution")
            print("5. Exit")

            choice = input("\nSelect demo (1-5): ")

            if choice == "1":
                self.demo_simple_workflow()
            elif choice == "2":
                self.demo_complex_workflow()
            elif choice == "3":
                self.demo_api_patterns()
            elif choice == "4":
                api = self.demo_simple_workflow()
                asyncio.run(self.test_api_execution(api))
            elif choice == "5":
                print("Goodbye!")
                break
            else:
                print("Invalid choice. Please try again.")

            input("\nPress Enter to continue...")


def main():
    """Main entry point with argument parsing."""
    parser = argparse.ArgumentParser(
        description="Kailash API Integration Demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run interactive demo
  python integration_api_demo.py

  # Run specific demo
  python integration_api_demo.py --demo simple
  python integration_api_demo.py --demo complex

  # Start API server
  python integration_api_demo.py --serve simple --port 8000
  python integration_api_demo.py --serve rag --port 8001

  # Run all demos
  python integration_api_demo.py --all
        """,
    )

    parser.add_argument(
        "--demo",
        choices=["simple", "complex", "patterns", "test"],
        help="Run specific demo",
    )

    parser.add_argument(
        "--serve", choices=["simple", "rag"], help="Start API server for workflow"
    )

    parser.add_argument(
        "--port", type=int, default=8000, help="Port for API server (default: 8000)"
    )

    parser.add_argument("--all", action="store_true", help="Run all demos")

    args = parser.parse_args()

    demo = APIDemo()

    if args.serve:
        # Start API server
        if args.serve == "simple":
            api = demo.demo_simple_workflow()
        else:  # rag
            api = demo.demo_complex_workflow()

        print(f"\n=== Starting {args.serve.upper()} API Server ===")
        print(f"Server: http://localhost:{args.port}")
        print(f"Docs: http://localhost:{args.port}/docs")
        print("Press Ctrl+C to stop")

        api.run(port=args.port)

    elif args.demo:
        # Run specific demo
        if args.demo == "simple":
            demo.demo_simple_workflow()
        elif args.demo == "complex":
            demo.demo_complex_workflow()
        elif args.demo == "patterns":
            demo.demo_api_patterns()
        elif args.demo == "test":
            api = demo.demo_simple_workflow()
            asyncio.run(demo.test_api_execution(api))

    elif args.all:
        # Run all demos
        demo.demo_simple_workflow()
        input("\nPress Enter to continue...")

        demo.demo_complex_workflow()
        input("\nPress Enter to continue...")

        demo.demo_api_patterns()
        input("\nPress Enter to continue...")

        api = demo.demo_simple_workflow()
        asyncio.run(demo.test_api_execution(api))

    else:
        # Interactive mode
        demo.run_interactive()


if __name__ == "__main__":
    main()
