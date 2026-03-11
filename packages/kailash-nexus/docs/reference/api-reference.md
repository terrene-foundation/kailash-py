# API Reference

Complete API reference for Nexus's workflow-native platform, covering all endpoints, objects, methods, and integration patterns.

## Overview

Nexus automatically exposes comprehensive REST APIs, WebSocket connections, CLI interfaces, and MCP (Model Context Protocol) endpoints for every registered workflow. This reference covers all available interfaces, objects, methods, and configuration options.

## Core API Classes

### Nexus Application

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder
import asyncio
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

# Primary application class
class Nexus:
    """
    The main Nexus application class for workflow-native platform

    Args:
        config (Dict[str, Any], optional): Application configuration
        enable_api (bool): Enable REST API endpoints (default: True)
        enable_cli (bool): Enable CLI interface (default: True)
        enable_mcp (bool): Enable MCP protocol (default: True)
        channels_synced (bool): Enable cross-channel session sync (default: True)
        auto_scale (bool): Enable automatic scaling (default: True)
        monitoring (bool): Enable comprehensive monitoring (default: True)

    Example:
        app = Nexus(
            config={"environment": "production"},
            enable_api=True,
            enable_cli=True,
            enable_mcp=True,
            channels_synced=True
        )
    """

    def __init__(self,
                 config: Optional[Dict[str, Any]] = None,
                 enable_api: bool = True,
                 enable_cli: bool = True,
                 enable_mcp: bool = True,
                 channels_synced: bool = True,
                 auto_scale: bool = True,
                 monitoring: bool = True):
        pass

    def register(self, name: str, workflow: Any) -> None:
        """
        Register a workflow with the platform

        Args:
            name (str): Workflow name for registration
            workflow: Workflow object or WorkflowBuilder instance

        Returns:
            None

        Example:
            app.register("data-processor", workflow)
        """
        pass

    def run(self, host: str = "0.0.0.0", port: int = 8000, **kwargs) -> None:
        """
        Start the Nexus platform

        Args:
            host (str): Host address (default: "0.0.0.0")
            port (int): Port number (default: 8000)
            **kwargs: Additional server configuration

        Example:
            app.run(host="0.0.0.0", port=8000, workers=4)
        """
        pass

    def health_check(self) -> Dict[str, Any]:
        """
        Get comprehensive health status

        Returns:
            Dict containing system health information

        Example:
            health = app.health_check()
            print(f"Status: {health['status']}")
            print(f"Uptime: {health['uptime_seconds']}")
            print(f"Workflows: {health['workflows_registered']}")
        """
        pass

    def get_registered_workflows(self) -> List[Dict[str, Any]]:
        """
        Get list of all registered workflows

        Returns:
            List of workflow registration information

        Example:
            workflows = app.get_registered_workflows()
            for workflow in workflows:
                print(f"{workflow['name']}: {workflow['endpoints']}")
        """
        pass

    def get_session_info(self, session_id: str) -> Dict[str, Any]:
        """
        Get session information across all channels

        Args:
            session_id (str): Session identifier

        Returns:
            Dict containing session details

        Example:
            session = app.get_session_info("session_123")
            print(f"Active channels: {session['active_channels']}")
        """
        pass

# Application instance example
app = Nexus(
    config={"environment": "development"},
    enable_api=True,
    enable_cli=True,
    enable_mcp=True,
    channels_synced=True
)

# Health check example
health_status = app.health_check()
print(f"Application health: {health_status['status']}")
```

### Workflow Builder Integration

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Workflow construction with Nexus integration
class NexusWorkflowIntegration:
    """Integration patterns for Nexus workflows"""

    @staticmethod
    def create_data_processing_workflow() -> WorkflowBuilder:
        """Create a data processing workflow for Nexus"""

        workflow = WorkflowBuilder()

        # Add data input node
        workflow.add_node("CSVReaderNode", "csv_reader", {
            "file_path": "/data/input.csv",
            "delimiter": ",",
            "encoding": "utf-8"
        })

        # Add transformation node
        workflow.add_node("PythonCodeNode", "transformer", {
            "script": """
def process_data(data):
    # Transform data
    processed = []
    for row in data.get('rows', []):
        transformed_row = {k.lower(): v for k, v in row.items()}
        processed.append(transformed_row)
    return {'processed_data': processed, 'count': len(processed)}
            """
        })

        # Add output node
        workflow.add_node("JSONWriterNode", "json_writer", {
            "output_path": "/data/output.json",
            "indent": 2
        })

        # Connect nodes
        workflow.add_connection("csv_reader", "transformer", "output", "data")
        workflow.add_connection("transformer", "json_writer", "output", "data")

        return workflow

    @staticmethod
    def create_api_workflow() -> WorkflowBuilder:
        """Create a workflow optimized for API endpoints"""

        workflow = WorkflowBuilder()

        # Add HTTP request processing
        workflow.add_node("HTTPRequestNode", "api_processor", {
            "method": "POST",
            "timeout": 30,
            "retry_count": 3
        })

        # Add business logic
        workflow.add_node("PythonCodeNode", "business_logic", {
            "script": """
def execute_business_logic(data):
    request_data = data.get('request_data', {})

    # Business processing
    result = {
        'processed_at': data.get('timestamp'),
        'input_size': len(str(request_data)),
        'status': 'success',
        'data': request_data
    }

    return {'api_response': result}
            """
        })

        # Add response formatting
        workflow.add_node("JSONWriterNode", "response_formatter", {
            "format_response": True,
            "include_metadata": True
        })

        # Connect workflow
        workflow.add_connection("api_processor", "business_logic", "output", "data")
        workflow.add_connection("business_logic", "response_formatter", "output", "data")

        return workflow

# Example workflow registration
data_workflow = NexusWorkflowIntegration.create_data_processing_workflow()
api_workflow = NexusWorkflowIntegration.create_api_workflow()

# Register workflows with Nexus
data_registration = app.register(data_workflow, "data-processor", "1.0.0")
api_registration = app.register(api_workflow, "api-handler", "1.0.0")

print(f"Data workflow API: {data_registration['api_endpoint']}")
print(f"API workflow CLI: {api_registration['cli_command']}")
```

## REST API Endpoints

### Workflow Execution Endpoints

```python
import requests
import asyncio
import aiohttp
from typing import Dict, Any

class NexusAPIClient:
    """Client for Nexus REST API"""

    def __init__(self, base_url: str = "http://localhost:8000", timeout: int = 30):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.session = requests.Session()

    def execute_workflow(self, workflow_name: str, input_data: Dict[str, Any],
                        session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Execute a registered workflow via REST API

        Args:
            workflow_name (str): Name of registered workflow
            input_data (Dict): Input data for workflow execution
            session_id (str, optional): Session ID for tracking

        Returns:
            Dict containing execution results

        Example:
            client = NexusAPIClient()
            result = client.execute_workflow("data-processor", {
                "input_file": "/data/sample.csv",
                "options": {"format": "json"}
            })
        """

        endpoint = f"{self.base_url}/workflows/{workflow_name}/execute"

        payload = {
            "input_data": input_data,
            "session_id": session_id or f"api_session_{int(time.time())}"
        }

        response = self.session.post(
            endpoint,
            json=payload,
            timeout=self.timeout
        )

        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"API Error {response.status_code}: {response.text}")

    def get_execution_status(self, execution_id: str) -> Dict[str, Any]:
        """
        Get status of workflow execution

        Args:
            execution_id (str): Execution identifier

        Returns:
            Dict containing execution status

        Example:
            status = client.get_execution_status("exec_123456")
            print(f"Status: {status['status']}")
            print(f"Progress: {status['progress']}%")
        """

        endpoint = f"{self.base_url}/executions/{execution_id}/status"
        response = self.session.get(endpoint, timeout=self.timeout)

        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Status Error {response.status_code}: {response.text}")

    def list_workflows(self) -> List[Dict[str, Any]]:
        """
        List all registered workflows

        Returns:
            List of workflow information

        Example:
            workflows = client.list_workflows()
            for workflow in workflows:
                print(f"{workflow['name']} v{workflow['version']}")
        """

        endpoint = f"{self.base_url}/workflows"
        response = self.session.get(endpoint, timeout=self.timeout)

        if response.status_code == 200:
            return response.json()['workflows']
        else:
            raise Exception(f"List Error {response.status_code}: {response.text}")

    def get_workflow_info(self, workflow_name: str) -> Dict[str, Any]:
        """
        Get detailed workflow information

        Args:
            workflow_name (str): Name of workflow

        Returns:
            Dict containing workflow details

        Example:
            info = client.get_workflow_info("data-processor")
            print(f"Description: {info['description']}")
            print(f"Input schema: {info['input_schema']}")
        """

        endpoint = f"{self.base_url}/workflows/{workflow_name}"
        response = self.session.get(endpoint, timeout=self.timeout)

        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Info Error {response.status_code}: {response.text}")

# API client usage examples
api_client = NexusAPIClient(base_url="http://localhost:8000")

# List available workflows
available_workflows = api_client.list_workflows()
print(f"Available workflows: {[w['name'] for w in available_workflows]}")

# Execute workflow
execution_result = api_client.execute_workflow("data-processor", {
    "input_file": "/tmp/test_data.csv",
    "output_format": "json",
    "validate_data": True
})

print(f"Execution ID: {execution_result['execution_id']}")
print(f"Status: {execution_result['status']}")
```

### Async API Client

```python
import aiohttp
import asyncio
from typing import Dict, Any, List, Optional

class AsyncNexusAPIClient:
    """Async client for high-performance Nexus API access"""

    def __init__(self, base_url: str = "http://localhost:8000", timeout: int = 30):
        self.base_url = base_url.rstrip('/')
        self.timeout = aiohttp.ClientTimeout(total=timeout)

    async def execute_workflow_async(self, workflow_name: str, input_data: Dict[str, Any],
                                   session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Execute workflow asynchronously

        Args:
            workflow_name (str): Name of registered workflow
            input_data (Dict): Input data for workflow execution
            session_id (str, optional): Session ID for tracking

        Returns:
            Dict containing execution results

        Example:
            async_client = AsyncNexusAPIClient()
            result = await async_client.execute_workflow_async("data-processor", {
                "batch_size": 1000,
                "parallel_processing": True
            })
        """

        endpoint = f"{self.base_url}/workflows/{workflow_name}/execute"

        payload = {
            "input_data": input_data,
            "session_id": session_id or f"async_session_{int(time.time())}"
        }

        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.post(endpoint, json=payload) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    raise Exception(f"Async API Error {response.status}: {await response.text()}")

    async def batch_execute_workflows(self, executions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Execute multiple workflows concurrently

        Args:
            executions: List of execution specifications

        Returns:
            List of execution results

        Example:
            executions = [
                {"workflow": "processor-1", "data": {"type": "csv"}},
                {"workflow": "processor-2", "data": {"type": "json"}},
                {"workflow": "processor-3", "data": {"type": "xml"}}
            ]
            results = await async_client.batch_execute_workflows(executions)
        """

        tasks = []
        for execution in executions:
            task = self.execute_workflow_async(
                execution["workflow"],
                execution["data"],
                execution.get("session_id")
            )
            tasks.append(task)

        return await asyncio.gather(*tasks, return_exceptions=True)

    async def stream_execution_updates(self, execution_id: str):
        """
        Stream real-time execution updates via WebSocket

        Args:
            execution_id (str): Execution identifier

        Yields:
            Dict updates about execution progress

        Example:
            async for update in async_client.stream_execution_updates("exec_123"):
                print(f"Progress: {update['progress']}%")
        """

        ws_url = f"{self.base_url.replace('http', 'ws')}/executions/{execution_id}/stream"

        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(ws_url) as ws:
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        yield json.loads(msg.data)
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        break

# Async usage examples
async def demonstrate_async_api():
    """Demonstrate async API capabilities"""

    async_client = AsyncNexusAPIClient()

    # Single async execution
    single_result = await async_client.execute_workflow_async("data-processor", {
        "input_data": {"file": "large_dataset.csv"},
        "processing_mode": "optimized"
    })

    print(f"Single execution: {single_result['execution_id']}")

    # Batch async executions
    batch_executions = [
        {"workflow": "data-processor", "data": {"file": f"batch_{i}.csv"}}
        for i in range(5)
    ]

    batch_results = await async_client.batch_execute_workflows(batch_executions)
    print(f"Batch completed: {len(batch_results)} executions")

    # Stream updates
    execution_id = single_result['execution_id']
    async for update in async_client.stream_execution_updates(execution_id):
        print(f"Stream update: {update}")
        if update.get('status') == 'completed':
            break

# Run async demonstration
# asyncio.run(demonstrate_async_api())
```

## CLI Integration

### Command Line Interface

```python
import subprocess
import json
from typing import Dict, Any, List

class NexusCLIInterface:
    """Interface for Nexus CLI operations"""

    def __init__(self, nexus_binary: str = "nexus"):
        self.nexus_binary = nexus_binary

    def execute_workflow_cli(self, workflow_name: str, input_data: Dict[str, Any],
                           session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Execute workflow via CLI

        Args:
            workflow_name (str): Name of workflow
            input_data (Dict): Input parameters
            session_id (str, optional): Session identifier

        Returns:
            Dict containing execution results

        Example:
            cli = NexusCLIInterface()
            result = cli.execute_workflow_cli("data-processor", {
                "input_file": "./data.csv",
                "output_format": "json"
            })
        """

        # Prepare CLI command
        cmd = [
            self.nexus_binary, "execute",
            "--workflow", workflow_name,
            "--input", json.dumps(input_data)
        ]

        if session_id:
            cmd.extend(["--session", session_id])

        # Execute command
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300
        )

        if result.returncode == 0:
            return json.loads(result.stdout)
        else:
            raise Exception(f"CLI Error: {result.stderr}")

    def list_workflows_cli(self) -> List[Dict[str, Any]]:
        """
        List workflows via CLI

        Returns:
            List of available workflows

        Example:
            workflows = cli.list_workflows_cli()
            for workflow in workflows:
                print(f"{workflow['name']}: {workflow['description']}")
        """

        cmd = [self.nexus_binary, "list", "--format", "json"]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            return json.loads(result.stdout)['workflows']
        else:
            raise Exception(f"CLI List Error: {result.stderr}")

    def get_workflow_status_cli(self, execution_id: str) -> Dict[str, Any]:
        """
        Get execution status via CLI

        Args:
            execution_id (str): Execution identifier

        Returns:
            Dict containing status information

        Example:
            status = cli.get_workflow_status_cli("exec_123456")
            print(f"Status: {status['status']}")
        """

        cmd = [
            self.nexus_binary, "status",
            "--execution-id", execution_id,
            "--format", "json"
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            return json.loads(result.stdout)
        else:
            raise Exception(f"CLI Status Error: {result.stderr}")

# CLI usage examples
cli_interface = NexusCLIInterface()

# List available workflows
cli_workflows = cli_interface.list_workflows_cli()
print(f"CLI workflows available: {len(cli_workflows)}")

# Execute workflow via CLI
cli_execution = cli_interface.execute_workflow_cli("data-processor", {
    "input_source": "cli_input.csv",
    "output_destination": "cli_output.json",
    "processing_options": {
        "validate": True,
        "format": "normalized"
    }
})

print(f"CLI execution ID: {cli_execution['execution_id']}")
```

## WebSocket API

### Real-time Communication

```python
import asyncio
import websockets
import json
from typing import Dict, Any, AsyncGenerator

class NexusWebSocketClient:
    """WebSocket client for real-time Nexus communication"""

    def __init__(self, ws_url: str = "ws://localhost:8000/ws"):
        self.ws_url = ws_url

    async def connect_and_execute(self, workflow_name: str, input_data: Dict[str, Any],
                                session_id: Optional[str] = None) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Execute workflow with real-time updates via WebSocket

        Args:
            workflow_name (str): Name of workflow
            input_data (Dict): Input data
            session_id (str, optional): Session identifier

        Yields:
            Dict updates during execution

        Example:
            ws_client = NexusWebSocketClient()
            async for update in ws_client.connect_and_execute("data-processor", data):
                print(f"Progress: {update['progress']}%")
        """

        async with websockets.connect(self.ws_url) as websocket:
            # Send execution request
            request = {
                "action": "execute_workflow",
                "workflow_name": workflow_name,
                "input_data": input_data,
                "session_id": session_id or f"ws_session_{int(time.time())}"
            }

            await websocket.send(json.dumps(request))

            # Receive real-time updates
            async for message in websocket:
                update = json.loads(message)
                yield update

                # Break on completion
                if update.get('status') in ['completed', 'failed', 'cancelled']:
                    break

    async def subscribe_to_session(self, session_id: str) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Subscribe to session updates across all channels

        Args:
            session_id (str): Session identifier

        Yields:
            Dict session updates

        Example:
            async for update in ws_client.subscribe_to_session("session_123"):
                print(f"Channel {update['channel']}: {update['event']}")
        """

        session_ws_url = f"{self.ws_url}/sessions/{session_id}"

        async with websockets.connect(session_ws_url) as websocket:
            # Send subscription request
            subscribe_request = {
                "action": "subscribe_session",
                "session_id": session_id
            }

            await websocket.send(json.dumps(subscribe_request))

            # Receive session updates
            async for message in websocket:
                update = json.loads(message)
                yield update

# WebSocket usage examples
async def demonstrate_websocket_api():
    """Demonstrate WebSocket API capabilities"""

    ws_client = NexusWebSocketClient()

    # Real-time workflow execution
    execution_data = {
        "input_file": "realtime_data.csv",
        "processing_mode": "streaming",
        "notify_progress": True
    }

    print("Starting real-time workflow execution...")
    async for update in ws_client.connect_and_execute("data-processor", execution_data):
        print(f"WebSocket update: {update}")

        if update.get('status') == 'completed':
            print(f"Workflow completed: {update['result']}")
            break

    # Session monitoring
    session_id = "demo_session_123"
    print(f"Monitoring session: {session_id}")

    async for session_update in ws_client.subscribe_to_session(session_id):
        print(f"Session update: {session_update}")

        # Break after a few updates for demo
        if session_update.get('event_count', 0) > 5:
            break

# Run WebSocket demonstration
# asyncio.run(demonstrate_websocket_api())
```

## Response Formats

### Standard API Responses

```python
from typing import Dict, Any, List, Optional
from datetime import datetime
import uuid

class NexusResponseFormats:
    """Standard response formats for Nexus API"""

    @staticmethod
    def execution_response(execution_id: str, status: str, result: Any = None,
                         error: str = None) -> Dict[str, Any]:
        """
        Standard execution response format

        Returns:
            Dict containing standardized execution response

        Example:
            response = NexusResponseFormats.execution_response(
                execution_id="exec_123",
                status="completed",
                result={"processed_records": 1000}
            )
        """

        response = {
            "execution_id": execution_id,
            "status": status,
            "timestamp": datetime.utcnow().isoformat(),
            "api_version": "1.0.0"
        }

        if result is not None:
            response["result"] = result

        if error:
            response["error"] = error

        return response

    @staticmethod
    def workflow_info_response(workflow_name: str, version: str,
                             endpoints: Dict[str, str]) -> Dict[str, Any]:
        """
        Standard workflow information response

        Returns:
            Dict containing workflow details

        Example:
            info = NexusResponseFormats.workflow_info_response(
                workflow_name="data-processor",
                version="1.0.0",
                endpoints={
                    "api": "/workflows/data-processor/execute",
                    "cli": "nexus execute --workflow data-processor",
                    "mcp": "process_data"
                }
            )
        """

        return {
            "workflow_name": workflow_name,
            "version": version,
            "endpoints": endpoints,
            "registration_time": datetime.utcnow().isoformat(),
            "status": "active",
            "api_version": "1.0.0"
        }

    @staticmethod
    def health_response(status: str, uptime: float, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """
        Standard health check response

        Returns:
            Dict containing health information

        Example:
            health = NexusResponseFormats.health_response(
                status="healthy",
                uptime=3600.5,
                metrics={"workflows": 5, "executions": 100}
            )
        """

        return {
            "status": status,
            "uptime_seconds": uptime,
            "timestamp": datetime.utcnow().isoformat(),
            "metrics": metrics,
            "api_version": "1.0.0"
        }

# Example response formatting
execution_response = NexusResponseFormats.execution_response(
    execution_id=str(uuid.uuid4()),
    status="completed",
    result={
        "processed_records": 1500,
        "output_file": "/data/processed_output.json",
        "execution_time_ms": 2450.5
    }
)

workflow_info = NexusResponseFormats.workflow_info_response(
    workflow_name="advanced-analytics",
    version="2.1.0",
    endpoints={
        "api": "/workflows/advanced-analytics/execute",
        "cli": "nexus execute --workflow advanced-analytics",
        "mcp": "analyze_data",
        "websocket": "ws://localhost:8000/workflows/advanced-analytics/stream"
    }
)

health_status = NexusResponseFormats.health_response(
    status="healthy",
    uptime=7200.0,
    metrics={
        "workflows_registered": 8,
        "active_executions": 3,
        "total_executions": 856,
        "success_rate": 99.8,
        "avg_response_time_ms": 145.2
    }
)

print(f"Execution response: {execution_response}")
print(f"Workflow info: {workflow_info}")
print(f"Health status: {health_status}")
```

## Error Handling

### Error Response Patterns

```python
from typing import Dict, Any, Optional
from enum import Enum

class NexusErrorCode(Enum):
    """Standard error codes for Nexus API"""
    WORKFLOW_NOT_FOUND = "WORKFLOW_NOT_FOUND"
    INVALID_INPUT = "INVALID_INPUT"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    TIMEOUT = "TIMEOUT"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    INTERNAL_ERROR = "INTERNAL_ERROR"

class NexusErrorHandler:
    """Comprehensive error handling for Nexus API"""

    @staticmethod
    def format_error_response(error_code: NexusErrorCode, message: str,
                            details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Format standardized error response

        Args:
            error_code: Error classification
            message: Human-readable error message
            details: Additional error context

        Returns:
            Dict containing formatted error response

        Example:
            error = NexusErrorHandler.format_error_response(
                NexusErrorCode.WORKFLOW_NOT_FOUND,
                "Workflow 'missing-workflow' not found",
                {"available_workflows": ["processor-1", "processor-2"]}
            )
        """

        error_response = {
            "error": {
                "code": error_code.value,
                "message": message,
                "timestamp": datetime.utcnow().isoformat(),
                "api_version": "1.0.0"
            }
        }

        if details:
            error_response["error"]["details"] = details

        return error_response

    @staticmethod
    def handle_workflow_not_found(workflow_name: str, available_workflows: List[str]) -> Dict[str, Any]:
        """Handle workflow not found error"""

        return NexusErrorHandler.format_error_response(
            NexusErrorCode.WORKFLOW_NOT_FOUND,
            f"Workflow '{workflow_name}' not found",
            {
                "requested_workflow": workflow_name,
                "available_workflows": available_workflows,
                "suggestion": "Check workflow name spelling or register the workflow"
            }
        )

    @staticmethod
    def handle_validation_error(field: str, value: Any, expected: str) -> Dict[str, Any]:
        """Handle input validation error"""

        return NexusErrorHandler.format_error_response(
            NexusErrorCode.INVALID_INPUT,
            f"Invalid value for field '{field}'",
            {
                "field": field,
                "provided_value": str(value),
                "expected": expected,
                "suggestion": f"Provide a valid {expected} for field '{field}'"
            }
        )

    @staticmethod
    def handle_execution_timeout(execution_id: str, timeout_seconds: int) -> Dict[str, Any]:
        """Handle execution timeout error"""

        return NexusErrorHandler.format_error_response(
            NexusErrorCode.TIMEOUT,
            f"Execution '{execution_id}' timed out after {timeout_seconds} seconds",
            {
                "execution_id": execution_id,
                "timeout_seconds": timeout_seconds,
                "suggestion": "Increase timeout value or optimize workflow performance"
            }
        )

# Error handling examples
workflow_not_found_error = NexusErrorHandler.handle_workflow_not_found(
    "non-existent-workflow",
    ["data-processor", "api-handler", "analytics-engine"]
)

validation_error = NexusErrorHandler.handle_validation_error(
    "input_file",
    123,
    "string file path"
)

timeout_error = NexusErrorHandler.handle_execution_timeout(
    "exec_789456",
    300
)

print(f"Workflow not found: {workflow_not_found_error}")
print(f"Validation error: {validation_error}")
print(f"Timeout error: {timeout_error}")
```

This API reference provides comprehensive coverage of Nexus's workflow-native platform APIs, including REST endpoints, WebSocket communication, CLI integration, and standardized response formats. All examples are designed to work with real Nexus infrastructure and demonstrate production-ready patterns.
