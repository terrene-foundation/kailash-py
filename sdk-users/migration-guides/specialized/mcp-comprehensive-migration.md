# MCP Migration Guide

## Overview

This guide helps you migrate existing systems to use the Model Context Protocol (MCP). It covers migration strategies, common patterns, and step-by-step instructions for various scenarios.

## Table of Contents

1. [Migration Planning](#migration-planning)
2. [From REST APIs](#from-rest-apis)
3. [From Function Calling](#from-function-calling)
4. [From Plugin Systems](#from-plugin-systems)
5. [From Legacy Tool Systems](#from-legacy-tool-systems)
6. [Data Migration](#data-migration)
7. [Authentication Migration](#authentication-migration)
8. [Client Migration](#client-migration)
9. [Testing Migration](#testing-migration)
10. [Rollback Strategies](#rollback-strategies)

## Migration Planning

### Assessment Checklist

Before starting migration, assess your current system:

```python
# migration/assessment.py
from typing import Dict, List, Any
import json

class MigrationAssessment:
    """Assess system for MCP migration."""

    def __init__(self):
        self.assessment = {
            "current_system": {},
            "migration_complexity": None,
            "estimated_effort": None,
            "risks": [],
            "recommendations": []
        }

    def analyze_current_system(self, system_info: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze current system architecture."""

        # Check API type
        if system_info.get("api_type") == "rest":
            self.assessment["current_system"]["type"] = "REST API"
            self.assessment["recommendations"].append(
                "Use REST-to-MCP adapter pattern"
            )

        # Check authentication
        auth_type = system_info.get("auth_type")
        if auth_type == "api_key":
            self.assessment["current_system"]["auth"] = "API Key"
            self.assessment["recommendations"].append(
                "Migrate to JWT-based authentication"
            )

        # Check tools/endpoints
        endpoint_count = len(system_info.get("endpoints", []))
        self.assessment["current_system"]["endpoints"] = endpoint_count

        # Calculate complexity
        if endpoint_count < 10:
            self.assessment["migration_complexity"] = "Low"
            self.assessment["estimated_effort"] = "1-2 weeks"
        elif endpoint_count < 50:
            self.assessment["migration_complexity"] = "Medium"
            self.assessment["estimated_effort"] = "2-4 weeks"
        else:
            self.assessment["migration_complexity"] = "High"
            self.assessment["estimated_effort"] = "4+ weeks"

        # Identify risks
        if system_info.get("has_stateful_operations"):
            self.assessment["risks"].append(
                "Stateful operations need careful migration"
            )

        if system_info.get("custom_protocols"):
            self.assessment["risks"].append(
                "Custom protocols require adapter implementation"
            )

        return self.assessment

    def generate_migration_plan(self) -> List[Dict[str, Any]]:
        """Generate step-by-step migration plan."""

        plan = []

        # Phase 1: Setup
        plan.append({
            "phase": 1,
            "name": "Setup and Preparation",
            "tasks": [
                "Set up MCP development environment",
                "Create migration branch",
                "Set up testing infrastructure",
                "Document current API"
            ],
            "duration": "2-3 days"
        })

        # Phase 2: Tool Migration
        plan.append({
            "phase": 2,
            "name": "Tool Migration",
            "tasks": [
                "Create MCP tool definitions",
                "Implement tool adapters",
                "Migrate business logic",
                "Add validation"
            ],
            "duration": "1-2 weeks"
        })

        # Phase 3: Testing
        plan.append({
            "phase": 3,
            "name": "Testing and Validation",
            "tasks": [
                "Unit test all tools",
                "Integration testing",
                "Performance testing",
                "Security audit"
            ],
            "duration": "3-5 days"
        })

        # Phase 4: Deployment
        plan.append({
            "phase": 4,
            "name": "Deployment",
            "tasks": [
                "Deploy to staging",
                "Client migration",
                "Gradual rollout",
                "Monitor and optimize"
            ],
            "duration": "1 week"
        })

        return plan

# Usage
assessor = MigrationAssessment()
system_info = {
    "api_type": "rest",
    "auth_type": "api_key",
    "endpoints": ["search", "process", "analyze"],
    "has_stateful_operations": True
}

assessment = assessor.analyze_current_system(system_info)
plan = assessor.generate_migration_plan()

print(json.dumps(assessment, indent=2))
print("\nMigration Plan:")
for phase in plan:
    print(f"\nPhase {phase['phase']}: {phase['name']}")
    for task in phase['tasks']:
        print(f"  - {task}")
```

## From REST APIs

### REST to MCP Adapter

```python
# migration/rest_to_mcp.py
from mcp.server import FastMCP
from typing import Dict, Any, Optional
import aiohttp
from pydantic import BaseModel

class RESTEndpoint(BaseModel):
    """REST endpoint configuration."""
    method: str
    path: str
    description: str
    parameters: Dict[str, Any]
    headers: Optional[Dict[str, str]] = None

class RESTToMCPAdapter:
    """Adapter to convert REST APIs to MCP tools."""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.mcp = FastMCP("REST API Adapter")

    def add_endpoint(self, name: str, endpoint: RESTEndpoint):
        """Add REST endpoint as MCP tool."""

        # Create tool function
        async def tool_function(**kwargs):
            # Build URL
            url = f"{self.base_url}{endpoint.path}"

            # Replace path parameters
            for key, value in kwargs.items():
                if f"{{{key}}}" in url:
                    url = url.replace(f"{{{key}}}", str(value))
                    del kwargs[key]

            # Make request
            async with aiohttp.ClientSession() as session:
                method = getattr(session, endpoint.method.lower())

                # Prepare request
                request_kwargs = {
                    "headers": endpoint.headers or {}
                }

                if endpoint.method.upper() in ["POST", "PUT", "PATCH"]:
                    request_kwargs["json"] = kwargs
                else:
                    request_kwargs["params"] = kwargs

                # Execute request
                async with method(url, **request_kwargs) as response:
                    data = await response.json()

                    return {
                        "status": response.status,
                        "data": data
                    }

        # Set function attributes for FastMCP
        tool_function.__name__ = name
        tool_function.__doc__ = endpoint.description

        # Register tool
        self.mcp.tool()(tool_function)

    def migrate_openapi_spec(self, openapi_spec: Dict[str, Any]):
        """Migrate from OpenAPI specification."""

        paths = openapi_spec.get("paths", {})

        for path, methods in paths.items():
            for method, operation in methods.items():
                if method.upper() in ["GET", "POST", "PUT", "DELETE", "PATCH"]:
                    # Create tool name
                    operation_id = operation.get("operationId")
                    if not operation_id:
                        # Generate from path and method
                        operation_id = f"{method}_{path.replace('/', '_').strip('_')}"

                    # Extract parameters
                    parameters = {}
                    for param in operation.get("parameters", []):
                        param_name = param["name"]
                        parameters[param_name] = {
                            "type": param.get("schema", {}).get("type", "string"),
                            "description": param.get("description", ""),
                            "required": param.get("required", False)
                        }

                    # Add request body parameters
                    if "requestBody" in operation:
                        content = operation["requestBody"].get("content", {})
                        if "application/json" in content:
                            schema = content["application/json"].get("schema", {})
                            if "properties" in schema:
                                for prop, prop_schema in schema["properties"].items():
                                    parameters[prop] = {
                                        "type": prop_schema.get("type", "string"),
                                        "description": prop_schema.get("description", ""),
                                        "required": prop in schema.get("required", [])
                                    }

                    # Create endpoint
                    endpoint = RESTEndpoint(
                        method=method,
                        path=path,
                        description=operation.get("summary", operation_id),
                        parameters=parameters
                    )

                    self.add_endpoint(operation_id, endpoint)

# Example usage
adapter = RESTToMCPAdapter("https://api.example.com")

# Add individual endpoint
adapter.add_endpoint("get_user", RESTEndpoint(
    method="GET",
    path="/users/{user_id}",
    description="Get user by ID",
    parameters={
        "user_id": {"type": "integer", "required": True}
    }
))

# Migrate from OpenAPI spec
openapi_spec = {
    "paths": {
        "/search": {
            "get": {
                "operationId": "search",
                "summary": "Search for items",
                "parameters": [
                    {
                        "name": "q",
                        "in": "query",
                        "required": True,
                        "schema": {"type": "string"}
                    }
                ]
            }
        }
    }
}

adapter.migrate_openapi_spec(openapi_spec)
```

### Gradual Migration Strategy

```python
# migration/gradual_migration.py
from mcp.server import FastMCP
from typing import Dict, Any, Callable
import asyncio

class GradualMigration:
    """Implement gradual migration from REST to MCP."""

    def __init__(self, legacy_client, mcp_client):
        self.legacy_client = legacy_client
        self.mcp_client = mcp_client
        self.migration_flags = {}
        self.metrics = {
            "legacy_calls": 0,
            "mcp_calls": 0,
            "errors": {"legacy": 0, "mcp": 0}
        }

    def set_migration_percentage(self, tool_name: str, percentage: int):
        """Set percentage of traffic to route to MCP."""
        self.migration_flags[tool_name] = percentage

    async def execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute tool with migration logic."""

        import random

        # Check migration percentage
        mcp_percentage = self.migration_flags.get(tool_name, 0)
        use_mcp = random.randint(1, 100) <= mcp_percentage

        if use_mcp:
            try:
                # Use MCP
                result = await self.mcp_client.execute_tool(tool_name, parameters)
                self.metrics["mcp_calls"] += 1

                # Log for comparison
                await self.log_execution(tool_name, "mcp", parameters, result)

                return result

            except Exception as e:
                self.metrics["errors"]["mcp"] += 1

                # Fallback to legacy
                if mcp_percentage < 100:
                    return await self.execute_legacy(tool_name, parameters)
                raise
        else:
            return await self.execute_legacy(tool_name, parameters)

    async def execute_legacy(self, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute using legacy system."""
        try:
            result = await self.legacy_client.call(tool_name, parameters)
            self.metrics["legacy_calls"] += 1

            # Log for comparison
            await self.log_execution(tool_name, "legacy", parameters, result)

            return result

        except Exception as e:
            self.metrics["errors"]["legacy"] += 1
            raise

    async def compare_results(self, tool_name: str, parameters: Dict[str, Any]):
        """Execute both systems and compare results."""

        # Execute both in parallel
        legacy_task = asyncio.create_task(
            self.legacy_client.call(tool_name, parameters)
        )
        mcp_task = asyncio.create_task(
            self.mcp_client.execute_tool(tool_name, parameters)
        )

        try:
            legacy_result, mcp_result = await asyncio.gather(
                legacy_task, mcp_task
            )

            # Compare results
            differences = self.find_differences(legacy_result, mcp_result)

            if differences:
                await self.log_differences(tool_name, parameters, differences)

            return {
                "legacy": legacy_result,
                "mcp": mcp_result,
                "differences": differences
            }

        except Exception as e:
            return {
                "error": str(e),
                "legacy_success": not legacy_task.done() or not legacy_task.exception(),
                "mcp_success": not mcp_task.done() or not mcp_task.exception()
            }

    def find_differences(self, obj1: Any, obj2: Any, path: str = "") -> List[Dict[str, Any]]:
        """Find differences between two objects."""
        differences = []

        if type(obj1) != type(obj2):
            differences.append({
                "path": path,
                "type": "type_mismatch",
                "legacy": type(obj1).__name__,
                "mcp": type(obj2).__name__
            })
        elif isinstance(obj1, dict):
            # Compare dictionaries
            all_keys = set(obj1.keys()) | set(obj2.keys())
            for key in all_keys:
                if key not in obj1:
                    differences.append({
                        "path": f"{path}.{key}",
                        "type": "missing_in_legacy",
                        "value": obj2[key]
                    })
                elif key not in obj2:
                    differences.append({
                        "path": f"{path}.{key}",
                        "type": "missing_in_mcp",
                        "value": obj1[key]
                    })
                else:
                    differences.extend(
                        self.find_differences(
                            obj1[key],
                            obj2[key],
                            f"{path}.{key}"
                        )
                    )
        elif isinstance(obj1, list):
            # Compare lists
            if len(obj1) != len(obj2):
                differences.append({
                    "path": path,
                    "type": "length_mismatch",
                    "legacy_length": len(obj1),
                    "mcp_length": len(obj2)
                })
            else:
                for i, (item1, item2) in enumerate(zip(obj1, obj2)):
                    differences.extend(
                        self.find_differences(
                            item1,
                            item2,
                            f"{path}[{i}]"
                        )
                    )
        elif obj1 != obj2:
            differences.append({
                "path": path,
                "type": "value_mismatch",
                "legacy": obj1,
                "mcp": obj2
            })

        return differences

    def get_migration_report(self) -> Dict[str, Any]:
        """Get migration metrics and status."""
        total_calls = self.metrics["legacy_calls"] + self.metrics["mcp_calls"]

        return {
            "total_calls": total_calls,
            "legacy_calls": self.metrics["legacy_calls"],
            "mcp_calls": self.metrics["mcp_calls"],
            "mcp_percentage": (self.metrics["mcp_calls"] / total_calls * 100) if total_calls > 0 else 0,
            "errors": self.metrics["errors"],
            "migration_status": self.migration_flags
        }

# Usage example
migration = GradualMigration(legacy_client, mcp_client)

# Start with 10% MCP traffic
migration.set_migration_percentage("search", 10)

# Gradually increase
await asyncio.sleep(3600)  # After 1 hour
migration.set_migration_percentage("search", 25)

await asyncio.sleep(3600)  # After another hour
migration.set_migration_percentage("search", 50)

# Check metrics
report = migration.get_migration_report()
print(f"Migration report: {report}")
```

## From Function Calling

### OpenAI Function Calling to MCP

```python
# migration/openai_to_mcp.py
from mcp.server import FastMCP
from typing import Dict, Any, List
import json

class OpenAIFunctionMigrator:
    """Migrate OpenAI function definitions to MCP tools."""

    def __init__(self):
        self.mcp = FastMCP("OpenAI Function Migration")

    def migrate_function(self, function_def: Dict[str, Any]):
        """Migrate single OpenAI function to MCP tool."""

        name = function_def["name"]
        description = function_def.get("description", "")
        parameters = function_def.get("parameters", {})

        # Create tool function
        async def tool_function(**kwargs):
            # Here you would implement the actual function logic
            # This is a placeholder that shows the structure
            return {
                "function": name,
                "parameters": kwargs,
                "result": f"Executed {name} with {kwargs}"
            }

        # Set function metadata
        tool_function.__name__ = name
        tool_function.__doc__ = description

        # Add parameter validation based on JSON schema
        if "properties" in parameters:
            # Create Pydantic model dynamically
            from pydantic import create_model, Field

            fields = {}
            for param_name, param_schema in parameters["properties"].items():
                param_type = self._json_schema_to_python_type(param_schema)
                is_required = param_name in parameters.get("required", [])

                if is_required:
                    fields[param_name] = (param_type, Field(..., description=param_schema.get("description", "")))
                else:
                    default_value = param_schema.get("default", None)
                    fields[param_name] = (param_type, Field(default_value, description=param_schema.get("description", "")))

            # Create model
            ParamModel = create_model(f"{name}_params", **fields)

            # Wrap function with validation
            original_function = tool_function

            async def validated_function(**kwargs):
                # Validate parameters
                validated_params = ParamModel(**kwargs)
                return await original_function(**validated_params.dict())

            validated_function.__name__ = name
            validated_function.__doc__ = description

            self.mcp.tool()(validated_function)
        else:
            self.mcp.tool()(tool_function)

    def _json_schema_to_python_type(self, schema: Dict[str, Any]):
        """Convert JSON schema type to Python type."""
        type_mapping = {
            "string": str,
            "number": float,
            "integer": int,
            "boolean": bool,
            "array": List,
            "object": Dict
        }

        json_type = schema.get("type", "string")
        python_type = type_mapping.get(json_type, str)

        # Handle array items
        if json_type == "array" and "items" in schema:
            item_type = self._json_schema_to_python_type(schema["items"])
            return List[item_type]

        return python_type

    def migrate_functions_list(self, functions: List[Dict[str, Any]]):
        """Migrate list of OpenAI functions."""
        for function_def in functions:
            self.migrate_function(function_def)

    def generate_migration_code(self, function_def: Dict[str, Any]) -> str:
        """Generate MCP tool code from OpenAI function."""

        name = function_def["name"]
        description = function_def.get("description", "")
        parameters = function_def.get("parameters", {})

        # Generate parameter list
        param_list = []
        param_docs = []

        if "properties" in parameters:
            for param_name, param_schema in parameters["properties"].items():
                param_type = self._json_schema_to_python_type(param_schema)
                is_required = param_name in parameters.get("required", [])

                type_hint = param_type.__name__ if hasattr(param_type, '__name__') else str(param_type)

                if is_required:
                    param_list.append(f"{param_name}: {type_hint}")
                else:
                    default = param_schema.get("default", "None")
                    if isinstance(default, str):
                        default = f'"{default}"'
                    param_list.append(f"{param_name}: {type_hint} = {default}")

                param_desc = param_schema.get("description", "")
                param_docs.append(f"    {param_name}: {param_desc}")

        # Generate code
        code = f'''
@mcp.tool()
async def {name}({", ".join(param_list)}) -> Dict[str, Any]:
    """{description}

    Args:
{chr(10).join(param_docs)}

    Returns:
        Tool execution result
    """
    # TODO: Implement function logic

    result = {{
        "status": "success",
        "data": {{}}
    }}

    return result
'''

        return code

# Example usage
migrator = OpenAIFunctionMigrator()

# OpenAI function definition
openai_function = {
    "name": "search_web",
    "description": "Search the web for information",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query"
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results",
                "default": 10
            }
        },
        "required": ["query"]
    }
}

# Migrate function
migrator.migrate_function(openai_function)

# Generate code
code = migrator.generate_migration_code(openai_function)
print(code)
```

### Anthropic Tool Use to MCP

```python
# migration/anthropic_to_mcp.py
from mcp.server import FastMCP
from typing import Dict, Any, List

class AnthropicToolMigrator:
    """Migrate Anthropic tool definitions to MCP."""

    def __init__(self):
        self.mcp = FastMCP("Anthropic Tool Migration")

    def migrate_tool(self, tool_def: Dict[str, Any]):
        """Migrate Anthropic tool to MCP."""

        name = tool_def["name"]
        description = tool_def["description"]
        input_schema = tool_def["input_schema"]

        # Create async wrapper for tool
        async def tool_function(**kwargs):
            # Validate against schema
            self._validate_against_schema(kwargs, input_schema)

            # Execute tool (placeholder - implement actual logic)
            return {
                "tool": name,
                "input": kwargs,
                "output": f"Processed with {name}"
            }

        tool_function.__name__ = name
        tool_function.__doc__ = description

        self.mcp.tool()(tool_function)

    def _validate_against_schema(self, data: Dict[str, Any], schema: Dict[str, Any]):
        """Validate data against JSON schema."""
        # Simple validation - in production use jsonschema library
        if schema.get("type") != "object":
            raise ValueError("Schema must be object type")

        properties = schema.get("properties", {})
        required = schema.get("required", [])

        # Check required fields
        for field in required:
            if field not in data:
                raise ValueError(f"Missing required field: {field}")

        # Validate types
        for field, value in data.items():
            if field in properties:
                expected_type = properties[field].get("type")
                if not self._check_type(value, expected_type):
                    raise ValueError(f"Invalid type for {field}: expected {expected_type}")

    def _check_type(self, value: Any, expected_type: str) -> bool:
        """Check if value matches expected type."""
        type_checks = {
            "string": lambda v: isinstance(v, str),
            "number": lambda v: isinstance(v, (int, float)),
            "integer": lambda v: isinstance(v, int),
            "boolean": lambda v: isinstance(v, bool),
            "array": lambda v: isinstance(v, list),
            "object": lambda v: isinstance(v, dict)
        }

        check = type_checks.get(expected_type)
        return check(value) if check else True

    def create_compatibility_layer(self):
        """Create compatibility layer for Anthropic clients."""

        class AnthropicCompatibilityClient:
            def __init__(self, mcp_client):
                self.mcp_client = mcp_client

            async def messages_create(self, messages: List[Dict], tools: List[Dict] = None):
                """Anthropic-compatible message creation."""

                # Extract tool calls from messages
                tool_calls = []
                for message in messages:
                    if message.get("role") == "assistant" and "tool_calls" in message:
                        tool_calls.extend(message["tool_calls"])

                # Execute tool calls via MCP
                results = []
                for tool_call in tool_calls:
                    result = await self.mcp_client.execute_tool(
                        tool_call["name"],
                        tool_call["input"]
                    )
                    results.append(result)

                # Format response
                return {
                    "content": results,
                    "role": "assistant"
                }

        return AnthropicCompatibilityClient
```

## From Plugin Systems

### WordPress-style Plugins to MCP

```python
# migration/plugin_to_mcp.py
from mcp.server import FastMCP
from typing import Dict, Any, List, Callable
import inspect

class PluginSystem:
    """Legacy plugin system."""

    def __init__(self):
        self.hooks = {}
        self.filters = {}

    def add_action(self, hook: str, callback: Callable, priority: int = 10):
        if hook not in self.hooks:
            self.hooks[hook] = []
        self.hooks[hook].append((priority, callback))
        self.hooks[hook].sort(key=lambda x: x[0])

    def add_filter(self, hook: str, callback: Callable, priority: int = 10):
        if hook not in self.filters:
            self.filters[hook] = []
        self.filters[hook].append((priority, callback))
        self.filters[hook].sort(key=lambda x: x[0])

class PluginToMCPMigrator:
    """Migrate plugin system to MCP."""

    def __init__(self, plugin_system: PluginSystem):
        self.plugin_system = plugin_system
        self.mcp = FastMCP("Plugin Migration")

    def migrate_actions_to_tools(self):
        """Convert plugin actions to MCP tools."""

        for hook_name, callbacks in self.plugin_system.hooks.items():
            # Create tool for each hook
            tool_name = f"plugin_{hook_name.replace('-', '_')}"

            async def create_tool(hook_name, callbacks):
                async def tool_function(**kwargs):
                    """Execute plugin hook."""
                    results = []

                    for priority, callback in callbacks:
                        try:
                            # Handle both sync and async callbacks
                            if inspect.iscoroutinefunction(callback):
                                result = await callback(**kwargs)
                            else:
                                result = callback(**kwargs)

                            results.append({
                                "priority": priority,
                                "callback": callback.__name__,
                                "result": result
                            })
                        except Exception as e:
                            results.append({
                                "priority": priority,
                                "callback": callback.__name__,
                                "error": str(e)
                            })

                    return {
                        "hook": hook_name,
                        "results": results
                    }

                return tool_function

            # Create and register tool
            tool = asyncio.run(create_tool(hook_name, callbacks))
            tool.__name__ = tool_name
            tool.__doc__ = f"Plugin hook: {hook_name}"

            self.mcp.tool()(tool)

    def migrate_filters_to_tools(self):
        """Convert plugin filters to MCP tools."""

        for filter_name, callbacks in self.plugin_system.filters.items():
            tool_name = f"filter_{filter_name.replace('-', '_')}"

            async def create_filter_tool(filter_name, callbacks):
                async def tool_function(value: Any, **kwargs):
                    """Apply plugin filter."""

                    # Apply filters in order
                    for priority, callback in callbacks:
                        try:
                            if inspect.iscoroutinefunction(callback):
                                value = await callback(value, **kwargs)
                            else:
                                value = callback(value, **kwargs)
                        except Exception as e:
                            # Log error but continue
                            print(f"Filter error in {callback.__name__}: {e}")

                    return {
                        "filter": filter_name,
                        "filtered_value": value
                    }

                return tool_function

            # Create and register tool
            tool = asyncio.run(create_filter_tool(filter_name, callbacks))
            tool.__name__ = tool_name
            tool.__doc__ = f"Plugin filter: {filter_name}"

            self.mcp.tool()(tool)

    def create_plugin_adapter(self, plugin_class):
        """Create adapter for plugin class."""

        class MCPPluginAdapter:
            def __init__(self, plugin_instance):
                self.plugin = plugin_instance
                self.mcp = FastMCP(f"Plugin: {plugin_instance.__class__.__name__}")
                self._migrate_methods()

            def _migrate_methods(self):
                """Migrate plugin methods to MCP tools."""

                for name, method in inspect.getmembers(self.plugin, inspect.ismethod):
                    if not name.startswith('_'):  # Skip private methods
                        # Create tool from method
                        async def create_method_tool(method):
                            async def tool_function(**kwargs):
                                if inspect.iscoroutinefunction(method):
                                    return await method(**kwargs)
                                else:
                                    return method(**kwargs)

                            return tool_function

                        tool = asyncio.run(create_method_tool(method))
                        tool.__name__ = name
                        tool.__doc__ = method.__doc__ or f"Plugin method: {name}"

                        self.mcp.tool()(tool)

        return MCPPluginAdapter

# Example plugin migration
legacy_plugin_system = PluginSystem()

# Add legacy hooks
def on_user_login(user_id: str):
    print(f"User {user_id} logged in")

def send_welcome_email(user_id: str):
    print(f"Sending welcome email to {user_id}")

legacy_plugin_system.add_action("user_login", on_user_login)
legacy_plugin_system.add_action("user_login", send_welcome_email, priority=20)

# Migrate to MCP
migrator = PluginToMCPMigrator(legacy_plugin_system)
migrator.migrate_actions_to_tools()
```

## From Legacy Tool Systems

### Generic Legacy System Migration

```python
# migration/legacy_migration.py
from mcp.server import FastMCP
from typing import Dict, Any, List, Protocol
import asyncio
from abc import ABC, abstractmethod

class LegacyTool(Protocol):
    """Protocol for legacy tools."""

    def get_name(self) -> str: ...
    def get_description(self) -> str: ...
    def get_parameters(self) -> Dict[str, Any]: ...
    def execute(self, **kwargs) -> Any: ...

class LegacyToolAdapter:
    """Adapter for legacy tools to MCP."""

    def __init__(self, legacy_tool: LegacyTool):
        self.legacy_tool = legacy_tool

    async def to_mcp_tool(self):
        """Convert legacy tool to MCP tool."""

        # Create async wrapper
        async def mcp_tool(**kwargs):
            # Execute legacy tool
            try:
                # Handle both sync and async legacy tools
                result = self.legacy_tool.execute(**kwargs)

                if asyncio.iscoroutine(result):
                    result = await result

                return {
                    "status": "success",
                    "result": result
                }
            except Exception as e:
                return {
                    "status": "error",
                    "error": str(e)
                }

        # Set metadata
        mcp_tool.__name__ = self.legacy_tool.get_name()
        mcp_tool.__doc__ = self.legacy_tool.get_description()

        return mcp_tool

class LegacySystemMigrator:
    """Migrate entire legacy system to MCP."""

    def __init__(self):
        self.mcp = FastMCP("Legacy System Migration")
        self.migration_map = {}

    async def migrate_tool(self, legacy_tool: LegacyTool):
        """Migrate single legacy tool."""

        adapter = LegacyToolAdapter(legacy_tool)
        mcp_tool = await adapter.to_mcp_tool()

        # Register with MCP
        self.mcp.tool()(mcp_tool)

        # Track migration
        self.migration_map[legacy_tool.get_name()] = {
            "legacy": legacy_tool,
            "mcp": mcp_tool,
            "migrated_at": datetime.utcnow()
        }

    async def migrate_batch(self, legacy_tools: List[LegacyTool]):
        """Migrate batch of legacy tools."""

        tasks = [self.migrate_tool(tool) for tool in legacy_tools]
        await asyncio.gather(*tasks)

    def generate_migration_report(self) -> Dict[str, Any]:
        """Generate migration report."""

        return {
            "total_migrated": len(self.migration_map),
            "tools": list(self.migration_map.keys()),
            "migration_details": [
                {
                    "name": name,
                    "migrated_at": details["migrated_at"].isoformat()
                }
                for name, details in self.migration_map.items()
            ]
        }

    def create_compatibility_shim(self):
        """Create compatibility layer for legacy clients."""

        class LegacyCompatibilityLayer:
            def __init__(self, mcp_client):
                self.mcp_client = mcp_client

            def execute_tool(self, tool_name: str, **kwargs):
                """Legacy-style tool execution."""

                # Run async MCP tool in sync context
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                try:
                    result = loop.run_until_complete(
                        self.mcp_client.execute_tool(tool_name, kwargs)
                    )

                    # Extract result in legacy format
                    if result.get("status") == "success":
                        return result.get("result")
                    else:
                        raise Exception(result.get("error", "Unknown error"))
                finally:
                    loop.close()

        return LegacyCompatibilityLayer
```

## Data Migration

### State and Configuration Migration

```python
# migration/data_migration.py
from typing import Dict, Any, List
import json
import asyncio
from datetime import datetime

class DataMigrator:
    """Migrate data from legacy system to MCP."""

    def __init__(self, legacy_storage, mcp_storage):
        self.legacy_storage = legacy_storage
        self.mcp_storage = mcp_storage
        self.migration_log = []

    async def migrate_tool_configurations(self):
        """Migrate tool configurations."""

        # Get legacy configurations
        legacy_configs = await self.legacy_storage.get_all_configs()

        for tool_name, config in legacy_configs.items():
            try:
                # Transform configuration format
                mcp_config = self.transform_config(config)

                # Store in MCP format
                await self.mcp_storage.store_tool_config(tool_name, mcp_config)

                self.migration_log.append({
                    "type": "config",
                    "tool": tool_name,
                    "status": "success",
                    "timestamp": datetime.utcnow()
                })

            except Exception as e:
                self.migration_log.append({
                    "type": "config",
                    "tool": tool_name,
                    "status": "error",
                    "error": str(e),
                    "timestamp": datetime.utcnow()
                })

    def transform_config(self, legacy_config: Dict[str, Any]) -> Dict[str, Any]:
        """Transform legacy config to MCP format."""

        mcp_config = {
            "version": "1.0",
            "metadata": {
                "migrated_from": "legacy",
                "migration_date": datetime.utcnow().isoformat()
            }
        }

        # Map legacy fields to MCP fields
        field_mapping = {
            "endpoint": "url",
            "auth_token": "api_key",
            "timeout_ms": "timeout",
            "retry_count": "max_retries"
        }

        for legacy_field, mcp_field in field_mapping.items():
            if legacy_field in legacy_config:
                value = legacy_config[legacy_field]

                # Transform timeout from ms to seconds
                if legacy_field == "timeout_ms":
                    value = value / 1000

                mcp_config[mcp_field] = value

        # Copy unmapped fields
        for field, value in legacy_config.items():
            if field not in field_mapping and field not in mcp_config:
                mcp_config[f"legacy_{field}"] = value

        return mcp_config

    async def migrate_user_data(self):
        """Migrate user-specific data."""

        users = await self.legacy_storage.get_all_users()

        for user_id, user_data in users.items():
            try:
                # Transform user data
                mcp_user_data = {
                    "id": user_id,
                    "preferences": self.transform_preferences(
                        user_data.get("preferences", {})
                    ),
                    "tool_usage": self.transform_usage_data(
                        user_data.get("tool_usage", {})
                    ),
                    "migration_info": {
                        "migrated_at": datetime.utcnow().isoformat(),
                        "legacy_id": user_data.get("legacy_id")
                    }
                }

                await self.mcp_storage.store_user_data(user_id, mcp_user_data)

            except Exception as e:
                self.migration_log.append({
                    "type": "user_data",
                    "user": user_id,
                    "status": "error",
                    "error": str(e)
                })

    def transform_preferences(self, legacy_prefs: Dict[str, Any]) -> Dict[str, Any]:
        """Transform user preferences."""

        return {
            "default_timeout": legacy_prefs.get("timeout", 30),
            "preferred_tools": legacy_prefs.get("favorite_tools", []),
            "ui_theme": legacy_prefs.get("theme", "light"),
            "notifications_enabled": legacy_prefs.get("notifications", True)
        }

    def transform_usage_data(self, legacy_usage: Dict[str, Any]) -> Dict[str, Any]:
        """Transform usage data."""

        mcp_usage = {}

        for tool_name, usage_info in legacy_usage.items():
            mcp_usage[tool_name] = {
                "call_count": usage_info.get("calls", 0),
                "last_used": usage_info.get("last_call"),
                "average_duration": usage_info.get("avg_time"),
                "error_count": usage_info.get("errors", 0)
            }

        return mcp_usage

    async def verify_migration(self):
        """Verify data migration integrity."""

        verification_results = {
            "configs": {"total": 0, "verified": 0},
            "users": {"total": 0, "verified": 0}
        }

        # Verify configurations
        legacy_configs = await self.legacy_storage.get_all_configs()
        for tool_name in legacy_configs:
            verification_results["configs"]["total"] += 1

            mcp_config = await self.mcp_storage.get_tool_config(tool_name)
            if mcp_config:
                verification_results["configs"]["verified"] += 1

        # Verify user data
        legacy_users = await self.legacy_storage.get_all_users()
        for user_id in legacy_users:
            verification_results["users"]["total"] += 1

            mcp_user = await self.mcp_storage.get_user_data(user_id)
            if mcp_user:
                verification_results["users"]["verified"] += 1

        return verification_results
```

## Authentication Migration

### Migrating Authentication Systems

```python
# migration/auth_migration.py
from typing import Dict, Any, List
import jwt
import hashlib
from datetime import datetime, timedelta

class AuthMigrator:
    """Migrate authentication from legacy to MCP."""

    def __init__(self, legacy_auth, mcp_auth):
        self.legacy_auth = legacy_auth
        self.mcp_auth = mcp_auth

    async def migrate_user_credentials(self, user_id: str):
        """Migrate single user's credentials."""

        # Get legacy credentials
        legacy_creds = await self.legacy_auth.get_user_credentials(user_id)

        # Transform to MCP format
        if legacy_creds["type"] == "api_key":
            # Convert API key to JWT
            mcp_token = self.create_jwt_from_api_key(
                user_id,
                legacy_creds["api_key"]
            )

            await self.mcp_auth.store_user_token(user_id, mcp_token)

        elif legacy_creds["type"] == "basic":
            # Migrate password hash
            mcp_creds = {
                "username": legacy_creds["username"],
                "password_hash": self.upgrade_password_hash(
                    legacy_creds["password_hash"]
                )
            }

            await self.mcp_auth.store_user_credentials(user_id, mcp_creds)

    def create_jwt_from_api_key(self, user_id: str, api_key: str) -> str:
        """Create JWT token from API key."""

        payload = {
            "sub": user_id,
            "iat": datetime.utcnow(),
            "exp": datetime.utcnow() + timedelta(days=30),
            "legacy_api_key_hash": hashlib.sha256(api_key.encode()).hexdigest()[:8],
            "migration": {
                "from": "api_key",
                "date": datetime.utcnow().isoformat()
            }
        }

        return jwt.encode(payload, self.mcp_auth.secret_key, algorithm="HS256")

    def upgrade_password_hash(self, legacy_hash: str) -> str:
        """Upgrade password hash to modern algorithm."""

        # Detect legacy hash type
        if legacy_hash.startswith("$1$"):  # MD5
            # Mark for password reset on next login
            return f"UPGRADE_REQUIRED:{legacy_hash}"
        elif legacy_hash.startswith("$2a$"):  # bcrypt
            # Already secure, keep as is
            return legacy_hash
        else:
            # Unknown format, require reset
            return "RESET_REQUIRED"

    async def create_migration_tokens(self, user_ids: List[str]):
        """Create temporary migration tokens for users."""

        migration_tokens = {}

        for user_id in user_ids:
            # Create temporary migration token
            token = jwt.encode({
                "sub": user_id,
                "purpose": "migration",
                "exp": datetime.utcnow() + timedelta(hours=24)
            }, self.mcp_auth.secret_key)

            migration_tokens[user_id] = token

            # Send migration email
            await self.send_migration_email(user_id, token)

        return migration_tokens

    async def send_migration_email(self, user_id: str, token: str):
        """Send migration instructions to user."""

        # Email template
        migration_url = f"https://app.example.com/migrate?token={token}"

        email_content = f"""
        Dear User,

        We're upgrading our authentication system. Please click the link below
        to complete your account migration:

        {migration_url}

        This link will expire in 24 hours.

        Thank you,
        The Team
        """

        # Send email (implementation depends on email service)
        await self.email_service.send(user_id, "Account Migration Required", email_content)
```

## Client Migration

### JavaScript/TypeScript Client Migration

```typescript
// migration/client_migration.ts

// Legacy client interface
interface LegacyClient {
  callTool(name: string, params: any): Promise<any>;
  authenticate(apiKey: string): void;
}

// MCP client interface
interface MCPClient {
  executeTool(name: string, parameters: any): Promise<any>;
  connect(): Promise<void>;
  disconnect(): Promise<void>;
}

// Migration adapter
class ClientMigrationAdapter implements LegacyClient {
  private mcpClient: MCPClient;
  private connected: boolean = false;

  constructor(serverUrl: string) {
    this.mcpClient = new MCPClient({
      serverUrl,
      transport: 'http'
    });
  }

  async authenticate(apiKey: string): Promise<void> {
    // Convert API key to JWT token
    const response = await fetch('/auth/migrate', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ api_key: apiKey })
    });

    const { access_token } = await response.json();

    // Configure MCP client with token
    this.mcpClient.setAuthToken(access_token);

    // Connect to MCP server
    await this.mcpClient.connect();
    this.connected = true;
  }

  async callTool(name: string, params: any): Promise<any> {
    if (!this.connected) {
      throw new Error('Not authenticated');
    }

    try {
      // Map legacy tool names to MCP tool names
      const mcpToolName = this.mapToolName(name);

      // Execute via MCP
      const result = await this.mcpClient.executeTool(mcpToolName, params);

      // Transform result to legacy format
      return this.transformResult(result);

    } catch (error) {
      // Map MCP errors to legacy errors
      throw this.mapError(error);
    }
  }

  private mapToolName(legacyName: string): string {
    const mapping: Record<string, string> = {
      'search_api': 'search',
      'process_data': 'data_processor',
      'get_info': 'information_retriever'
    };

    return mapping[legacyName] || legacyName;
  }

  private transformResult(mcpResult: any): any {
    // MCP returns { status, result, ... }
    // Legacy expects just the result
    if (mcpResult.status === 'success') {
      return mcpResult.result;
    } else {
      throw new Error(mcpResult.error?.message || 'Unknown error');
    }
  }

  private mapError(error: any): Error {
    if (error.code === 'TOOL_NOT_FOUND') {
      return new Error(`Unknown tool: ${error.tool}`);
    } else if (error.code === 'VALIDATION_ERROR') {
      return new Error(`Invalid parameters: ${error.details}`);
    } else {
      return error;
    }
  }
}

// Progressive migration example
class ProgressiveClientMigration {
  private legacyClient: LegacyClient;
  private mcpAdapter: ClientMigrationAdapter;
  private migrationFlags: Map<string, boolean> = new Map();

  constructor(legacyClient: LegacyClient, serverUrl: string) {
    this.legacyClient = legacyClient;
    this.mcpAdapter = new ClientMigrationAdapter(serverUrl);
  }

  enableToolMigration(toolName: string): void {
    this.migrationFlags.set(toolName, true);
  }

  async callTool(name: string, params: any): Promise<any> {
    // Check if tool is migrated
    if (this.migrationFlags.get(name)) {
      console.log(`Using MCP for tool: ${name}`);
      return this.mcpAdapter.callTool(name, params);
    } else {
      console.log(`Using legacy for tool: ${name}`);
      return this.legacyClient.callTool(name, params);
    }
  }
}
```

## Testing Migration

### Migration Testing Framework

```python
# migration/testing.py
import asyncio
from typing import Dict, Any, List
import pytest
from deepdiff import DeepDiff

class MigrationTester:
    """Test framework for migration validation."""

    def __init__(self, legacy_client, mcp_client):
        self.legacy_client = legacy_client
        self.mcp_client = mcp_client
        self.test_results = []

    async def test_tool_parity(self, tool_name: str, test_cases: List[Dict[str, Any]]):
        """Test that tool produces same results in both systems."""

        for test_case in test_cases:
            params = test_case["params"]

            try:
                # Execute on both systems
                legacy_result = await self.legacy_client.call(tool_name, params)
                mcp_result = await self.mcp_client.execute_tool(tool_name, params)

                # Compare results
                diff = DeepDiff(legacy_result, mcp_result, ignore_order=True)

                self.test_results.append({
                    "tool": tool_name,
                    "test_case": test_case["name"],
                    "passed": len(diff) == 0,
                    "differences": diff
                })

            except Exception as e:
                self.test_results.append({
                    "tool": tool_name,
                    "test_case": test_case["name"],
                    "passed": False,
                    "error": str(e)
                })

    async def test_performance_regression(self, tool_name: str, params: Dict[str, Any]):
        """Test for performance regressions."""

        import time

        # Warm up
        await self.legacy_client.call(tool_name, params)
        await self.mcp_client.execute_tool(tool_name, params)

        # Measure legacy performance
        legacy_times = []
        for _ in range(10):
            start = time.time()
            await self.legacy_client.call(tool_name, params)
            legacy_times.append(time.time() - start)

        # Measure MCP performance
        mcp_times = []
        for _ in range(10):
            start = time.time()
            await self.mcp_client.execute_tool(tool_name, params)
            mcp_times.append(time.time() - start)

        # Calculate statistics
        legacy_avg = sum(legacy_times) / len(legacy_times)
        mcp_avg = sum(mcp_times) / len(mcp_times)

        regression = ((mcp_avg - legacy_avg) / legacy_avg) * 100

        return {
            "tool": tool_name,
            "legacy_avg_ms": legacy_avg * 1000,
            "mcp_avg_ms": mcp_avg * 1000,
            "regression_percent": regression,
            "acceptable": regression < 20  # Allow 20% regression
        }

    async def test_error_handling(self, tool_name: str):
        """Test error handling compatibility."""

        error_cases = [
            {"params": {}, "expected": "missing_required_parameter"},
            {"params": {"invalid": "data"}, "expected": "invalid_parameter"},
            {"params": {"timeout": 0.001}, "expected": "timeout"}
        ]

        for case in error_cases:
            legacy_error = None
            mcp_error = None

            try:
                await self.legacy_client.call(tool_name, case["params"])
            except Exception as e:
                legacy_error = type(e).__name__

            try:
                await self.mcp_client.execute_tool(tool_name, case["params"])
            except Exception as e:
                mcp_error = type(e).__name__

            # Verify both systems handle errors similarly
            assert legacy_error is not None, f"Legacy should error on {case['expected']}"
            assert mcp_error is not None, f"MCP should error on {case['expected']}"

    def generate_test_report(self) -> Dict[str, Any]:
        """Generate comprehensive test report."""

        passed = sum(1 for r in self.test_results if r["passed"])
        total = len(self.test_results)

        return {
            "summary": {
                "total_tests": total,
                "passed": passed,
                "failed": total - passed,
                "pass_rate": (passed / total * 100) if total > 0 else 0
            },
            "details": self.test_results
        }

# Pytest fixtures for migration testing
@pytest.fixture
async def migration_tester(legacy_client, mcp_client):
    """Provide migration tester instance."""
    return MigrationTester(legacy_client, mcp_client)

@pytest.mark.asyncio
async def test_search_tool_migration(migration_tester):
    """Test search tool migration."""

    test_cases = [
        {
            "name": "basic_search",
            "params": {"query": "test"}
        },
        {
            "name": "search_with_filters",
            "params": {"query": "test", "max_results": 5}
        }
    ]

    await migration_tester.test_tool_parity("search", test_cases)

    report = migration_tester.generate_test_report()
    assert report["summary"]["pass_rate"] == 100
```

## Rollback Strategies

### Implementing Rollback Capability

```python
# migration/rollback.py
from typing import Dict, Any
import asyncio
from datetime import datetime

class MigrationRollback:
    """Rollback capability for migrations."""

    def __init__(self):
        self.rollback_points = []
        self.rollback_procedures = {}

    def create_rollback_point(self, name: str):
        """Create a rollback point."""

        rollback_point = {
            "name": name,
            "timestamp": datetime.utcnow(),
            "state": self.capture_current_state()
        }

        self.rollback_points.append(rollback_point)

        return rollback_point

    def capture_current_state(self) -> Dict[str, Any]:
        """Capture current system state."""

        return {
            "active_tools": self.get_active_tools(),
            "configuration": self.get_configuration(),
            "routing_rules": self.get_routing_rules()
        }

    async def rollback_to_point(self, point_name: str):
        """Rollback to specific point."""

        # Find rollback point
        point = next(
            (p for p in self.rollback_points if p["name"] == point_name),
            None
        )

        if not point:
            raise ValueError(f"Rollback point '{point_name}' not found")

        # Execute rollback procedures
        state = point["state"]

        # Restore routing rules
        await self.restore_routing_rules(state["routing_rules"])

        # Restore configuration
        await self.restore_configuration(state["configuration"])

        # Restore tools
        await self.restore_tools(state["active_tools"])

        return {
            "rolled_back_to": point_name,
            "timestamp": datetime.utcnow()
        }

    def register_rollback_procedure(self, component: str, procedure: Callable):
        """Register component-specific rollback procedure."""

        self.rollback_procedures[component] = procedure

    async def emergency_rollback(self):
        """Emergency rollback to last known good state."""

        if not self.rollback_points:
            raise ValueError("No rollback points available")

        # Get last rollback point
        last_point = self.rollback_points[-1]

        await self.rollback_to_point(last_point["name"])

# Blue-green deployment for safe migration
class BlueGreenMigration:
    """Blue-green deployment strategy for migration."""

    def __init__(self, blue_env, green_env):
        self.blue_env = blue_env  # Current production
        self.green_env = green_env  # New MCP environment
        self.active_env = "blue"

    async def deploy_green(self):
        """Deploy MCP to green environment."""

        # Deploy MCP server
        await self.green_env.deploy_mcp()

        # Run health checks
        health = await self.green_env.health_check()

        if not health["healthy"]:
            raise Exception("Green environment unhealthy")

        return health

    async def switch_traffic(self, percentage: int):
        """Switch percentage of traffic to green."""

        # Update load balancer
        await self.load_balancer.update_weights({
            "blue": 100 - percentage,
            "green": percentage
        })

        # Monitor for issues
        await self.monitor_environments()

    async def complete_migration(self):
        """Complete migration to green."""

        # Switch all traffic
        await self.switch_traffic(100)

        # Wait for stability
        await asyncio.sleep(300)  # 5 minutes

        # Make green the new blue
        self.blue_env = self.green_env
        self.active_env = "green"

    async def rollback(self):
        """Rollback to blue environment."""

        # Switch all traffic back to blue
        await self.switch_traffic(0)

        # Shutdown green
        await self.green_env.shutdown()

        self.active_env = "blue"
```

## Migration Best Practices

### 1. Planning Phase
- Inventory all existing tools and APIs
- Document current authentication methods
- Identify dependencies
- Create rollback plan

### 2. Implementation Phase
- Start with read-only tools
- Implement monitoring early
- Use feature flags
- Maintain backward compatibility

### 3. Testing Phase
- Test both positive and negative cases
- Performance regression testing
- Load testing
- Security audit

### 4. Deployment Phase
- Use gradual rollout
- Monitor metrics closely
- Have rollback ready
- Communicate with users

### 5. Post-Migration
- Remove legacy code gradually
- Update documentation
- Train support team
- Gather feedback

## Common Migration Patterns

### Pattern 1: Adapter Pattern
```python
# Create adapters for legacy systems
adapter = LegacyToMCPAdapter(legacy_system)
mcp_server.register_adapter(adapter)
```

### Pattern 2: Parallel Run
```python
# Run both systems in parallel
result_legacy = await legacy_system.execute(params)
result_mcp = await mcp_system.execute(params)
compare_results(result_legacy, result_mcp)
```

### Pattern 3: Feature Flag Migration
```python
# Use feature flags for gradual migration
if feature_flags.is_enabled("use_mcp", user_id):
    return await mcp_client.execute_tool(name, params)
else:
    return await legacy_client.call(name, params)
```

## Conclusion

Successful migration to MCP requires careful planning, systematic implementation, and thorough testing. Use the patterns and tools in this guide to ensure a smooth transition while maintaining system reliability and performance. Remember to always have a rollback plan and monitor the migration closely.
