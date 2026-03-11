"""End-to-end tests for AI agent workflows with Nexus MCP.

Tests complete user scenarios from AI agent connection through
workflow execution and result processing, using the full MCP protocol.
"""

import asyncio
import json
import socket
import time
from contextlib import closing
from typing import Any, Dict, List

import pytest
import pytest_asyncio
import websockets
from kailash.workflow.builder import WorkflowBuilder
from nexus import Nexus

# Test Component 3: E2E Tests for AI Agent Workflows


def find_free_port(start_port: int = 8000) -> int:
    """Find a free port starting from start_port."""
    for port in range(start_port, start_port + 100):
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
            try:
                s.bind(("", port))
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                return port
            except OSError:
                continue
    raise RuntimeError(f"Could not find free port starting from {start_port}")


class TestAIAgentScenarios:
    """Test complete AI agent interaction scenarios."""

    @pytest_asyncio.fixture
    async def production_nexus(self):
        """Create a production-like Nexus instance."""
        # Find free ports dynamically to avoid conflicts
        api_port = find_free_port(8890)
        mcp_port = find_free_port(api_port + 100)

        app = Nexus(
            api_port=api_port,
            mcp_port=mcp_port,
            enable_auth=False,  # TODO: Test with auth in separate scenario
            enable_monitoring=True,
            enable_http_transport=False,  # Use simple MCP server for WebSocket-only mode
            enable_sse_transport=False,
            enable_discovery=False,
            rate_limit_config={"default": 100, "burst": 200},
        )

        # Register production-like workflows
        self._register_production_workflows(app)

        # Start server
        import threading

        server_thread = threading.Thread(target=app.start, daemon=True)
        server_thread.start()

        # Wait for full initialization
        await asyncio.sleep(3)

        yield app

        # Cleanup
        app.stop()

    def _register_production_workflows(self, app: Nexus):
        """Register realistic production workflows."""

        # 1. Document Processing Workflow
        doc_workflow = WorkflowBuilder()
        doc_workflow.add_node(
            "PythonCodeNode",
            "processor",
            {
                "code": """
import re
import json
from datetime import datetime

document = parameters.get('document', '')
task = parameters.get('task', 'analyze')

if task == 'analyze':
    # Document analysis
    words = document.split()
    sentences = re.split(r'[.!?]+', document)

    # Extract key information
    emails = re.findall(r'\\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Z|a-z]{2,}\\b', document)
    urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', document)

    result = {
        'analysis': {
            'word_count': len(words),
            'sentence_count': len([s for s in sentences if s.strip()]),
            'emails_found': emails,
            'urls_found': urls,
            'timestamp': datetime.now().isoformat()
        }
    }

elif task == 'summarize':
    # Simple extractive summarization
    sentences = re.split(r'[.!?]+', document)
    sentences = [s.strip() for s in sentences if s.strip()]

    # Take first and last sentences as summary
    summary = []
    if sentences:
        summary.append(sentences[0])
        if len(sentences) > 2:
            summary.append(sentences[-1])

    result = {
        'summary': ' '.join(summary),
        'original_length': len(document),
        'summary_length': len(' '.join(summary))
    }

elif task == 'extract_data':
    # Extract structured data
    lines = document.split('\\n')
    data_points = []

    for line in lines:
        # Look for key-value pairs
        if ':' in line:
            parts = line.split(':', 1)
            if len(parts) == 2:
                data_points.append({
                    'key': parts[0].strip(),
                    'value': parts[1].strip()
                })

    result = {
        'extracted_data': data_points,
        'data_count': len(data_points)
    }

else:
    result = {'error': f'Unknown task: {task}'}
"""
            },
        )
        doc_workflow.metadata = {
            "description": "Process documents for analysis, summarization, or data extraction",
            "version": "1.0.0",
            "parameters": {
                "document": {"type": "string", "required": True},
                "task": {
                    "type": "string",
                    "enum": ["analyze", "summarize", "extract_data"],
                },
            },
        }
        app.register("document_processor", doc_workflow.build())

        # 2. Data Pipeline Workflow
        pipeline_workflow = WorkflowBuilder()
        pipeline_workflow.add_node(
            "PythonCodeNode",
            "pipeline",
            {
                "code": """
import json
import statistics

data = parameters.get('data', [])
operations = parameters.get('operations', ['clean', 'transform', 'aggregate'])

results = {'stages': {}}

# Stage 1: Clean
if 'clean' in operations:
    cleaned_data = []
    for item in data:
        if item is not None and isinstance(item, (int, float)):
            if not (isinstance(item, float) and (item != item)):  # Skip NaN
                cleaned_data.append(item)

    results['stages']['clean'] = {
        'input_count': len(data),
        'output_count': len(cleaned_data),
        'removed': len(data) - len(cleaned_data)
    }
    data = cleaned_data

# Stage 2: Transform
if 'transform' in operations and data:
    transform_type = parameters.get('transform_type', 'normalize')

    if transform_type == 'normalize':
        min_val = min(data)
        max_val = max(data)
        range_val = max_val - min_val

        if range_val > 0:
            transformed = [(x - min_val) / range_val for x in data]
        else:
            transformed = data

        results['stages']['transform'] = {
            'type': 'normalize',
            'min': min_val,
            'max': max_val,
            'sample': transformed[:5] if transformed else []
        }
        data = transformed

    elif transform_type == 'scale':
        factor = parameters.get('scale_factor', 100)
        transformed = [x * factor for x in data]
        results['stages']['transform'] = {
            'type': 'scale',
            'factor': factor,
            'sample': transformed[:5] if transformed else []
        }
        data = transformed

# Stage 3: Aggregate
if 'aggregate' in operations and data:
    aggregations = {
        'count': len(data),
        'sum': sum(data),
        'mean': statistics.mean(data),
        'median': statistics.median(data),
        'min': min(data),
        'max': max(data)
    }

    if len(data) > 1:
        aggregations['std_dev'] = statistics.stdev(data)

    results['stages']['aggregate'] = aggregations

results['final_data'] = data[:10] if len(data) > 10 else data
results['success'] = True

result = results
"""
            },
        )
        app.register("data_pipeline", pipeline_workflow.build())

        # 3. Integration Workflow (simulates API calls)
        integration_workflow = WorkflowBuilder()
        integration_workflow.add_node(
            "PythonCodeNode",
            "integrator",
            {
                "code": """
import json
import time
from datetime import datetime

action = parameters.get('action', 'fetch')
endpoint = parameters.get('endpoint', 'users')
data = parameters.get('data', {})

# Simulate API operations
if action == 'fetch':
    # Simulate fetching data
    if endpoint == 'users':
        result = {
            'data': [
                {'id': 1, 'name': 'Alice', 'email': 'alice@example.com'},
                {'id': 2, 'name': 'Bob', 'email': 'bob@example.com'}
            ],
            'total': 2,
            'timestamp': datetime.now().isoformat()
        }
    elif endpoint == 'products':
        result = {
            'data': [
                {'id': 101, 'name': 'Widget', 'price': 19.99},
                {'id': 102, 'name': 'Gadget', 'price': 29.99}
            ],
            'total': 2,
            'timestamp': datetime.now().isoformat()
        }
    else:
        result = {'error': f'Unknown endpoint: {endpoint}'}

elif action == 'create':
    # Simulate creating resource
    new_id = int(time.time() * 1000) % 10000
    result = {
        'created': {
            'id': new_id,
            **data
        },
        'status': 'success',
        'timestamp': datetime.now().isoformat()
    }

elif action == 'update':
    # Simulate updating resource
    resource_id = parameters.get('id', 0)
    result = {
        'updated': {
            'id': resource_id,
            **data
        },
        'status': 'success',
        'timestamp': datetime.now().isoformat()
    }

else:
    result = {'error': f'Unknown action: {action}'}
"""
            },
        )
        app.register("api_integration", integration_workflow.build())

    @pytest.mark.asyncio
    async def test_ai_agent_discovery_and_exploration(self, production_nexus):
        """Test AI agent discovering and exploring available capabilities."""
        uri = f"ws://localhost:{production_nexus._mcp_port}"

        async with websockets.connect(uri) as websocket:
            # Step 1: Discover available tools
            discovery_request = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
            await websocket.send(json.dumps(discovery_request))

            response = await websocket.recv()
            tools_data = json.loads(response)

            assert "result" in tools_data
            tools = tools_data["result"]["tools"]
            assert len(tools) >= 3  # Our production workflows

            # Verify all workflows are discoverable
            tool_names = [t["name"] for t in tools]
            assert "document_processor" in tool_names
            assert "data_pipeline" in tool_names
            assert "api_integration" in tool_names

            # Step 2: Discover resources
            resources_request = {"jsonrpc": "2.0", "id": 2, "method": "resources/list"}
            await websocket.send(json.dumps(resources_request))

            response = await websocket.recv()
            resources_data = json.loads(response)

            resources = resources_data["result"]["resources"]

            # Check for different resource types
            workflow_resources = [
                r for r in resources if r["uri"].startswith("workflow://")
            ]
            assert len(workflow_resources) >= 3

            # Step 3: Read workflow definition for understanding
            workflow_request = {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "resources/read",
                "params": {"uri": "workflow://document_processor"},
            }
            await websocket.send(json.dumps(workflow_request))

            response = await websocket.recv()
            workflow_data = json.loads(response)

            # Verify workflow definition is available
            workflow_def = json.loads(workflow_data["result"]["contents"][0]["text"])
            assert workflow_def["name"] == "document_processor"
            assert workflow_def["type"] == "workflow"
            assert "nodes" in workflow_def
            assert "schema" in workflow_def

    @pytest.mark.asyncio
    async def test_document_processing_scenario(self, production_nexus):
        """Test complete document processing scenario."""
        uri = f"ws://localhost:{production_nexus._mcp_port}"

        async with websockets.connect(uri) as websocket:
            # Sample document
            test_document = """
            Subject: Quarterly Report Analysis

            Dear Team,

            Our Q4 results show significant growth. Revenue increased by 25% compared to last year.
            Please review the attached report at https://example.com/reports/q4-2024.

            Key metrics:
            Revenue: $2.5M
            Customers: 1,250
            Growth Rate: 25%

            For questions, contact me at manager@example.com.

            Best regards,
            The Management Team
            """

            # Step 1: Analyze the document
            analyze_request = {
                "jsonrpc": "2.0",
                "id": 10,
                "method": "tools/call",
                "params": {
                    "name": "document_processor",
                    "arguments": {"document": test_document, "task": "analyze"},
                },
            }
            await websocket.send(json.dumps(analyze_request))

            response = await websocket.recv()
            analyze_result = json.loads(response)

            # Extract analysis
            content = analyze_result["result"]["content"]
            if isinstance(content, list):
                analysis = json.loads(content[0]["text"])["analysis"]

                assert analysis["word_count"] > 40  # Test document has ~47 words
                assert analysis["sentence_count"] > 5
                assert "manager@example.com" in analysis["emails_found"]
                assert any(
                    "example.com/reports" in url for url in analysis["urls_found"]
                )

            # Step 2: Summarize the document
            summarize_request = {
                "jsonrpc": "2.0",
                "id": 11,
                "method": "tools/call",
                "params": {
                    "name": "document_processor",
                    "arguments": {"document": test_document, "task": "summarize"},
                },
            }
            await websocket.send(json.dumps(summarize_request))

            response = await websocket.recv()
            summary_result = json.loads(response)

            # Check summary
            content = summary_result["result"]["content"]
            if isinstance(content, list):
                summary_data = json.loads(content[0]["text"])
                assert len(summary_data["summary"]) < len(test_document)
                assert summary_data["summary_length"] < summary_data["original_length"]

            # Step 3: Extract structured data
            extract_request = {
                "jsonrpc": "2.0",
                "id": 12,
                "method": "tools/call",
                "params": {
                    "name": "document_processor",
                    "arguments": {"document": test_document, "task": "extract_data"},
                },
            }
            await websocket.send(json.dumps(extract_request))

            response = await websocket.recv()
            extract_result = json.loads(response)

            # Verify extracted data
            content = extract_result["result"]["content"]
            if isinstance(content, list):
                extracted = json.loads(content[0]["text"])
                data_points = extracted["extracted_data"]

                # Should extract key-value pairs
                assert len(data_points) >= 3
                keys = [dp["key"] for dp in data_points]
                assert "Revenue" in keys
                assert "Customers" in keys

    @pytest.mark.asyncio
    async def test_data_pipeline_scenario(self, production_nexus):
        """Test complete data pipeline processing."""
        uri = f"ws://localhost:{production_nexus._mcp_port}"

        async with websockets.connect(uri) as websocket:
            # Test data with some noise
            test_data = [10, 20, None, 30, 40, float("nan"), 50, 60, 70, 80, 90, 100]

            # Run full pipeline
            pipeline_request = {
                "jsonrpc": "2.0",
                "id": 20,
                "method": "tools/call",
                "params": {
                    "name": "data_pipeline",
                    "arguments": {
                        "data": test_data,
                        "operations": ["clean", "transform", "aggregate"],
                        "transform_type": "normalize",
                    },
                },
            }
            await websocket.send(json.dumps(pipeline_request))

            response = await websocket.recv()
            pipeline_result = json.loads(response)

            # Verify pipeline stages
            content = pipeline_result["result"]["content"]
            if isinstance(content, list):
                results = json.loads(content[0]["text"])

                # Check cleaning stage
                assert results["stages"]["clean"]["removed"] == 2  # None and NaN
                assert results["stages"]["clean"]["output_count"] == 10

                # Check transform stage
                assert results["stages"]["transform"]["type"] == "normalize"
                assert results["stages"]["transform"]["min"] == 10
                assert results["stages"]["transform"]["max"] == 100

                # Check aggregation stage
                agg = results["stages"]["aggregate"]
                assert agg["count"] == 10
                assert agg["mean"] == pytest.approx(0.5, rel=0.1)  # Normalized mean
                assert "std_dev" in agg

    @pytest.mark.asyncio
    async def test_multi_step_integration_scenario(self, production_nexus):
        """Test multi-step integration scenario with API operations."""
        uri = f"ws://localhost:{production_nexus._mcp_port}"

        async with websockets.connect(uri) as websocket:
            # Step 1: Fetch users
            fetch_request = {
                "jsonrpc": "2.0",
                "id": 30,
                "method": "tools/call",
                "params": {
                    "name": "api_integration",
                    "arguments": {"action": "fetch", "endpoint": "users"},
                },
            }
            await websocket.send(json.dumps(fetch_request))

            response = await websocket.recv()
            fetch_result = json.loads(response)

            # Extract users
            content = fetch_result["result"]["content"]
            if isinstance(content, list):
                users_data = json.loads(content[0]["text"])
                assert len(users_data["data"]) == 2
                assert users_data["data"][0]["name"] == "Alice"

            # Step 2: Create new resource
            create_request = {
                "jsonrpc": "2.0",
                "id": 31,
                "method": "tools/call",
                "params": {
                    "name": "api_integration",
                    "arguments": {
                        "action": "create",
                        "endpoint": "users",
                        "data": {
                            "name": "Charlie",
                            "email": "charlie@example.com",
                            "role": "developer",
                        },
                    },
                },
            }
            await websocket.send(json.dumps(create_request))

            response = await websocket.recv()
            create_result = json.loads(response)

            # Verify creation
            content = create_result["result"]["content"]
            if isinstance(content, list):
                created = json.loads(content[0]["text"])
                assert created["status"] == "success"
                assert created["created"]["name"] == "Charlie"
                assert "id" in created["created"]

                created_id = created["created"]["id"]

            # Step 3: Update the resource
            update_request = {
                "jsonrpc": "2.0",
                "id": 32,
                "method": "tools/call",
                "params": {
                    "name": "api_integration",
                    "arguments": {
                        "action": "update",
                        "id": created_id,
                        "data": {
                            "role": "senior developer",
                            "department": "engineering",
                        },
                    },
                },
            }
            await websocket.send(json.dumps(update_request))

            response = await websocket.recv()
            update_result = json.loads(response)

            # Verify update
            content = update_result["result"]["content"]
            if isinstance(content, list):
                updated = json.loads(content[0]["text"])
                assert updated["status"] == "success"
                assert updated["updated"]["role"] == "senior developer"
                assert updated["updated"]["department"] == "engineering"

    @pytest.mark.asyncio
    async def test_resource_navigation_scenario(self, production_nexus):
        """Test AI agent navigating through resources for learning."""
        uri = f"ws://localhost:{production_nexus._mcp_port}"

        async with websockets.connect(uri) as websocket:
            # Step 1: Read platform information
            platform_request = {
                "jsonrpc": "2.0",
                "id": 40,
                "method": "resources/read",
                "params": {"uri": "system://nexus/info"},
            }
            await websocket.send(json.dumps(platform_request))

            response = await websocket.recv()
            platform_data = json.loads(response)

            # Learn about the platform
            info = json.loads(platform_data["result"]["contents"][0]["text"])
            available_workflows = info["workflows"]

            # Step 2: Read help for getting started
            help_request = {
                "jsonrpc": "2.0",
                "id": 41,
                "method": "resources/read",
                "params": {"uri": "help://getting-started"},
            }
            await websocket.send(json.dumps(help_request))

            response = await websocket.recv()
            help_data = json.loads(response)

            help_text = help_data["result"]["contents"][0]["text"]
            assert "Getting Started" in help_text

            # Step 3: Read documentation
            docs_request = {
                "jsonrpc": "2.0",
                "id": 42,
                "method": "resources/read",
                "params": {"uri": "docs://quickstart"},
            }
            await websocket.send(json.dumps(docs_request))

            response = await websocket.recv()
            docs_data = json.loads(response)

            docs_text = docs_data["result"]["contents"][0]["text"]
            assert "Quick Start Guide" in docs_text  # Updated to match actual docs

            # Step 4: Check configuration
            config_request = {
                "jsonrpc": "2.0",
                "id": 43,
                "method": "resources/read",
                "params": {"uri": "config://platform"},
            }
            await websocket.send(json.dumps(config_request))

            response = await websocket.recv()
            config_data = json.loads(response)

            config = json.loads(config_data["result"]["contents"][0]["text"])
            # Verify platform configuration is readable
            assert "name" in config
            assert "api_port" in config
            assert "mcp_port" in config

    @pytest.mark.asyncio
    async def test_error_recovery_scenario(self, production_nexus):
        """Test AI agent handling and recovering from errors."""
        uri = f"ws://localhost:{production_nexus._mcp_port}"

        async with websockets.connect(uri) as websocket:
            # Step 1: Try invalid operation
            invalid_request = {
                "jsonrpc": "2.0",
                "id": 50,
                "method": "tools/call",
                "params": {
                    "name": "document_processor",
                    "arguments": {"document": "test", "task": "invalid_task"},
                },
            }
            await websocket.send(json.dumps(invalid_request))

            response = await websocket.recv()
            error_result = json.loads(response)

            # Should get error in result
            content = error_result["result"]["content"]
            if isinstance(content, list):
                result = json.loads(content[0]["text"])
                assert "error" in result
                assert "Unknown task" in result["error"]

            # Step 2: Recover by reading help
            help_request = {
                "jsonrpc": "2.0",
                "id": 51,
                "method": "resources/read",
                "params": {"uri": "workflow://document_processor"},
            }
            await websocket.send(json.dumps(help_request))

            response = await websocket.recv()
            workflow_info = json.loads(response)

            # Verify workflow definition is readable
            workflow_def = json.loads(workflow_info["result"]["contents"][0]["text"])
            assert workflow_def["name"] == "document_processor"
            assert "nodes" in workflow_def

            # Step 3: Retry with valid operation (use known valid task)
            valid_request = {
                "jsonrpc": "2.0",
                "id": 52,
                "method": "tools/call",
                "params": {
                    "name": "document_processor",
                    "arguments": {
                        "document": "This is a test document for recovery.",
                        "task": "analyze",  # Use known valid task
                    },
                },
            }
            await websocket.send(json.dumps(valid_request))

            response = await websocket.recv()
            success_result = json.loads(response)

            # Should succeed now
            assert "error" not in success_result
            assert "result" in success_result

    @pytest.mark.asyncio
    async def test_performance_under_load(self, production_nexus):
        """Test MCP server performance with multiple concurrent requests."""
        uri = f"ws://localhost:{production_nexus._mcp_port}"

        async with websockets.connect(uri) as websocket:
            start_time = time.time()

            # Send 20 concurrent requests
            tasks = []
            for i in range(20):
                request = {
                    "jsonrpc": "2.0",
                    "id": 100 + i,
                    "method": "tools/call",
                    "params": {
                        "name": "data_pipeline",
                        "arguments": {
                            "data": list(range(i, i + 10)),
                            "operations": ["aggregate"],
                        },
                    },
                }
                tasks.append(websocket.send(json.dumps(request)))

            # Send all requests
            await asyncio.gather(*tasks)

            # Collect all responses
            responses = []
            for _ in range(20):
                response = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                responses.append(json.loads(response))

            end_time = time.time()
            duration = end_time - start_time

            # Verify all succeeded
            assert len(responses) == 20
            for resp in responses:
                assert "result" in resp

            # Check performance
            assert duration < 5.0  # Should handle 20 requests in under 5 seconds
            avg_time = duration / 20
            assert avg_time < 0.5  # Average response time under 500ms


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
