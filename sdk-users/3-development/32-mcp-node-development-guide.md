# MCP Node Development Guide

*Building custom MCP servers, tools, and nodes with enterprise-grade features*

## Overview

The Model Context Protocol (MCP) enables seamless integration between AI models and external tools. This guide covers custom MCP server development, node-to-tool bridging, advanced features like authentication and monitoring, and production deployment patterns using the Kailash SDK.

## Prerequisites

- Completed [Cyclic Workflows Guide](31-cyclic-workflows-guide.md)
- Understanding of MCP protocol concepts
- Familiarity with async Python programming

## Core MCP Development Features

### MCPServerBase and MCPServer

Foundation classes for building custom MCP servers.

```python
from kailash.mcp_server.server import MCPServer, MCPServerBase
from kailash.mcp_server.auth import APIKeyAuth, PermissionManager
from kailash.mcp_server.transports import EnhancedStdioTransport

# Initialize enhanced MCP server
mcp_server = MCPServer(
    name="custom-analytics-server",
    version="1.2.0",

    # Authentication
    auth_provider=APIKeyAuth(keys={
        "admin-key": {"permissions": ["read", "write", "admin"]},
        "user-key": {"permissions": ["read", "write"]},
        "readonly-key": {"permissions": ["read"]}
    }),

    # Transport configuration
    transport=EnhancedStdioTransport(
        enable_compression=True,
        compression_threshold=1024,
        max_message_size=10485760  # 10MB
    ),

    # Caching configuration
    enable_caching=True,
    cache_config={
        "default_ttl": 300,  # 5 minutes
        "max_size": 1000,
        "cleanup_interval": 60
    },

    # Circuit breaker for resilience
    circuit_breaker_config={
        "failure_threshold": 5,
        "timeout_seconds": 30,
        "half_open_max_calls": 3
    },

    # Monitoring and metrics
    enable_metrics=True,
    metrics_config={
        "export_format": "prometheus",
        "export_port": 9090,
        "collection_interval": 30
    },

    # Rate limiting
    rate_limit_config={
        "requests_per_minute": 100,
        "burst_size": 20,
        "per_user_limits": {
            "admin-key": 1000,
            "user-key": 500,
            "readonly-key": 100
        }
    }
)

# Start the server
await mcp_server.start()
```

### Basic Tool Creation

Simple tool registration with decorators.

```python
# Simple function-based tool
@mcp_server.tool(
    description="Search for information in a knowledge base",
    cache_key="search",  # Enable caching
    cache_ttl=600,       # 10 minutes
    rate_limit=50        # Max 50 calls per minute
)
def search_knowledge_base(query: str, max_results: int = 10) -> dict:
    """
    Search the knowledge base for relevant information.

    Args:
        query: Search query string
        max_results: Maximum number of results to return

    Returns:
        Dictionary with search results and metadata
    """
    # Implement search logic
    results = knowledge_base.search(query, limit=max_results)

    return {
        "query": query,
        "results": [
            {
                "title": result.title,
                "content": result.content,
                "relevance_score": result.score,
                "source": result.source,
                "timestamp": result.timestamp.isoformat()
            }
            for result in results
        ],
        "total_found": len(results),
        "search_time_ms": results.search_time
    }

# Tool with structured input validation
@mcp_server.tool(
    description="Analyze data and generate insights",
    input_schema={
        "type": "object",
        "properties": {
            "data": {
                "type": "array",
                "items": {"type": "number"},
                "description": "Numerical data to analyze"
            },
            "analysis_type": {
                "type": "string",
                "enum": ["statistical", "trend", "correlation"],
                "description": "Type of analysis to perform"
            },
            "confidence_level": {
                "type": "number",
                "minimum": 0.8,
                "maximum": 0.99,
                "default": 0.95,
                "description": "Statistical confidence level"
            }
        },
        "required": ["data", "analysis_type"]
    }
)
async def analyze_data(data: list, analysis_type: str, confidence_level: float = 0.95) -> dict:
    """
    Perform statistical analysis on numerical data.
    """
    import numpy as np
    from scipy import stats

    data_array = np.array(data)

    if analysis_type == "statistical":
        return {
            "analysis_type": "statistical",
            "summary": {
                "mean": float(np.mean(data_array)),
                "median": float(np.median(data_array)),
                "std_dev": float(np.std(data_array)),
                "min": float(np.min(data_array)),
                "max": float(np.max(data_array)),
                "count": len(data_array)
            },
            "confidence_interval": {
                "level": confidence_level,
                "lower": float(stats.t.interval(confidence_level, len(data_array)-1,
                                               loc=np.mean(data_array),
                                               scale=stats.sem(data_array))[0]),
                "upper": float(stats.t.interval(confidence_level, len(data_array)-1,
                                               loc=np.mean(data_array),
                                               scale=stats.sem(data_array))[1])
            }
        }

    elif analysis_type == "trend":
        # Simple linear trend analysis
        x = np.arange(len(data_array))
        slope, intercept, r_value, p_value, std_err = stats.linregress(x, data_array)

        return {
            "analysis_type": "trend",
            "trend": {
                "slope": float(slope),
                "intercept": float(intercept),
                "correlation": float(r_value),
                "p_value": float(p_value),
                "standard_error": float(std_err)
            },
            "interpretation": {
                "direction": "increasing" if slope > 0 else "decreasing" if slope < 0 else "stable",
                "strength": "strong" if abs(r_value) > 0.7 else "moderate" if abs(r_value) > 0.3 else "weak",
                "significant": p_value < (1 - confidence_level)
            }
        }

    elif analysis_type == "correlation":
        # Auto-correlation analysis
        correlation = np.correlate(data_array, data_array, mode='full')
        correlation = correlation[correlation.size // 2:]
        correlation = correlation / correlation[0]  # Normalize

        return {
            "analysis_type": "correlation",
            "autocorrelation": correlation[:min(10, len(correlation))].tolist(),
            "periodicity_detected": bool(np.any(correlation[1:] > 0.5)),
            "dominant_period": int(np.argmax(correlation[1:]) + 1) if np.any(correlation[1:] > 0.5) else None
        }
```

## Node-to-MCP Tool Bridging

Convert Kailash nodes into MCP tools seamlessly.

### Single Node Tools

```python
from kailash.nodes.data.csv_reader import CSVReaderNode
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.ai.llm_agent import LLMAgentNode

# Register a CSVReaderNode as an MCP tool
@mcp_server.node_tool(
    node_class=CSVReaderNode,
    tool_name="read_csv_file",
    description="Read and parse CSV files with advanced options",
    cache_ttl=300
)
async def csv_reader_tool(file_path: str, delimiter: str = ",", encoding: str = "utf-8") -> dict:
    """
    Read a CSV file and return its contents as structured data.

    Args:
        file_path: Path to the CSV file
        delimiter: Field delimiter (default: comma)
        encoding: File encoding (default: utf-8)
    """
    # The node will be automatically instantiated and executed
    # Parameters are mapped to node configuration
    return {
        "node_config": {
            "file_path": file_path,
            "delimiter": delimiter,
            "encoding": encoding,
            "include_headers": True,
            "skip_empty_rows": True
        }
    }

# Register a PythonCodeNode for dynamic code execution
@mcp_server.node_tool(
    node_class=PythonCodeNode,
    tool_name="execute_python_code",
    description="Execute Python code dynamically with access to data context",
    cache_ttl=0,  # Don't cache code execution
    rate_limit=20  # Limit to 20 executions per minute
)
async def python_executor_tool(code: str, context_data: dict = None) -> dict:
    """
    Execute Python code with optional context data.

    Args:
        code: Python code to execute
        context_data: Optional data context for the code
    """
    return {
        "node_config": {
            "code": code,
            "context": context_data or {},
            "timeout": 30,
            "memory_limit": 256
        }
    }

# Register an LLM agent as an MCP tool
@mcp_server.node_tool(
    node_class=LLMAgentNode,
    tool_name="ai_assistant",
    description="Intelligent AI assistant for various tasks",
    cache_key="llm_response",
    cache_ttl=1800  # 30 minutes for LLM responses
)
async def ai_assistant_tool(
    prompt: str,
    task_type: str = "general",
    model: str = "ollama:llama3.2:3b",
    max_tokens: int = 1000
) -> dict:
    """
    Get AI assistance for various tasks.

    Args:
        prompt: The prompt or question for the AI
        task_type: Type of task (general, analysis, coding, writing)
        model: AI model to use
        max_tokens: Maximum tokens in response
    """
    return {
        "node_config": {
            "prompt": prompt,
            "model": model,
            "max_tokens": max_tokens,
            "temperature": 0.7,
            "system_prompt": f"You are an AI assistant specialized in {task_type} tasks."
        }
    }
```

### Workflow-Based Tools

```python
from kailash.workflow.builder import WorkflowBuilder

# Create a complex workflow as an MCP tool
@mcp_server.workflow_tool(
    tool_name="data_analysis_pipeline",
    description="Complete data analysis pipeline from CSV to insights",
    cache_ttl=600
)
async def data_analysis_workflow() -> WorkflowBuilder:
    """
    Build a comprehensive data analysis # Workflow setup goes here
    """
    workflow = WorkflowBuilder()

    # Data ingestion
    workflow.add_node("CSVReaderNode", "data_reader", {
        "include_headers": True,
        "skip_empty_rows": True,
        "data_types_inference": True
    })

    # Data cleaning
    workflow.add_node("PythonCodeNode", "data_cleaner", {
        "code": """
        import pandas as pd
        import numpy as np

        df = pd.DataFrame(data)

        # Remove duplicates
        df = df.drop_duplicates()

        # Handle missing values
        numeric_columns = df.select_dtypes(include=[np.number]).columns
        df[numeric_columns] = df[numeric_columns].fillna(df[numeric_columns].mean())

        categorical_columns = df.select_dtypes(include=['object']).columns
        df[categorical_columns] = df[categorical_columns].fillna(df[categorical_columns].mode().iloc[0])

        result = {
            'cleaned_data': df.to_dict('records'),
            'cleaning_summary': {
                'original_rows': len(data),
                'cleaned_rows': len(df),
                'duplicates_removed': len(data) - len(df),
                'columns_processed': len(df.columns)
            }
        }
        """
    })

    # Statistical analysis
    workflow.add_node("PythonCodeNode", "statistical_analyzer", {
        "code": """
        import pandas as pd
        import numpy as np
        from scipy import stats

        df = pd.DataFrame(cleaned_data)
        numeric_columns = df.select_dtypes(include=[np.number]).columns

        statistics = {}
        for col in numeric_columns:
            statistics[col] = {
                'mean': float(df[col].mean()),
                'median': float(df[col].median()),
                'std': float(df[col].std()),
                'min': float(df[col].min()),
                'max': float(df[col].max()),
                'skewness': float(stats.skew(df[col])),
                'kurtosis': float(stats.kurtosis(df[col]))
            }

        result = {
            'statistics': statistics,
            'data_shape': df.shape,
            'numeric_columns': list(numeric_columns),
            'categorical_columns': list(df.select_dtypes(include=['object']).columns)
        }
        """
    })

    # Correlation analysis
    workflow.add_node("PythonCodeNode", "correlation_analyzer", {
        "code": """
        import pandas as pd
        import numpy as np

        df = pd.DataFrame(cleaned_data)
        numeric_df = df.select_dtypes(include=[np.number])

        if len(numeric_df.columns) > 1:
            correlation_matrix = numeric_df.corr()

            # Find strong correlations
            strong_correlations = []
            for i in range(len(correlation_matrix.columns)):
                for j in range(i+1, len(correlation_matrix.columns)):
                    corr_value = correlation_matrix.iloc[i, j]
                    if abs(corr_value) > 0.7:
                        strong_correlations.append({
                            'var1': correlation_matrix.columns[i],
                            'var2': correlation_matrix.columns[j],
                            'correlation': float(corr_value)
                        })

            result = {
                'correlation_matrix': correlation_matrix.to_dict(),
                'strong_correlations': strong_correlations,
                'correlation_summary': {
                    'total_pairs': len(correlation_matrix.columns) * (len(correlation_matrix.columns) - 1) // 2,
                    'strong_correlations_count': len(strong_correlations)
                }
            }
        else:
            result = {
                'correlation_matrix': {},
                'strong_correlations': [],
                'message': 'Insufficient numeric columns for correlation analysis'
            }
        """
    })

    # Generate insights
    workflow.add_node("LLMAgentNode", "insight_generator", {
        "model": "ollama:llama3.2:3b",
        "temperature": 0.3,
        "max_tokens": 1000,
        "system_prompt": """
        You are a data analyst AI. Analyze the provided statistical and correlation data
        to generate meaningful insights and recommendations. Focus on:
        1. Key statistical findings
        2. Notable correlations and their business implications
        3. Data quality observations
        4. Actionable recommendations

        Present your analysis in a clear, structured format.
        """
    })

    # Connect workflow nodes
    workflow.add_connection("data_reader", "data_cleaner", "data", "data")
    workflow.add_connection("data_cleaner", "statistical_analyzer", "result.cleaned_data", "cleaned_data")
    workflow.add_connection("data_cleaner", "correlation_analyzer", "result.cleaned_data", "cleaned_data")
    workflow.add_connection("statistical_analyzer", "insight_generator", "result", "statistics")
    workflow.add_connection("correlation_analyzer", "insight_generator", "result", "correlations")

    return workflow

# Use the workflow tool
async def execute_data_analysis(file_path: str) -> dict:
    """Execute the data analysis pipeline on a CSV file."""

    # Get the workflow
    workflow = await data_analysis_workflow()

    # Execute with input data
    result = await runtime.execute(workflow.build(), {
        "data_reader": {"file_path": file_path}
    })

    return {
        "analysis_complete": True,
        "file_analyzed": file_path,
        "cleaning_summary": result["data_cleaner"]["result"]["cleaning_summary"],
        "statistics": result["statistical_analyzer"]["result"]["statistics"],
        "correlations": result["correlation_analyzer"]["result"]["correlation_summary"],
        "insights": result["insight_generator"]["response"],
        "execution_time": result["metadata"]["execution_time"]
    }
```

## Advanced MCP Features

### Authentication and Authorization

```python
from kailash.mcp_server.auth import JWTAuth, OAuth2Client, PermissionManager

# JWT Authentication
jwt_auth = JWTAuth(
    secret_key="your-secret-key",
    algorithm="HS256",
    token_expiry_hours=24,

    # Token validation
    validate_issuer=True,
    validate_audience=True,
    issuer="analytics-server",
    audience="mcp-clients",

    # User information extraction
    user_id_claim="sub",
    permissions_claim="permissions",
    roles_claim="roles"
)

# OAuth 2.1 Client
oauth_client = OAuth2Client(
    client_id="your-client-id",
    client_secret="your-client-secret",
    authorization_url="https://auth.example.com/oauth/authorize",
    token_url="https://auth.example.com/oauth/token",

    # Scopes
    scopes=["read", "write", "admin"],

    # PKCE support
    use_pkce=True,
    code_challenge_method="S256",

    # Token management
    token_storage="memory",  # or "redis", "database"
    refresh_token_enabled=True
)

# Permission management
permission_manager = PermissionManager(
    roles={
        "admin": ["read", "write", "execute", "manage"],
        "analyst": ["read", "write", "execute"],
        "viewer": ["read"]
    },

    # Resource-based permissions
    resource_permissions={
        "datasets": {
            "admin": ["create", "read", "update", "delete"],
            "analyst": ["read", "update"],
            "viewer": ["read"]
        },
        "models": {
            "admin": ["create", "read", "update", "delete", "deploy"],
            "analyst": ["create", "read", "update"],
            "viewer": ["read"]
        }
    },

    # Dynamic permission checking
    permission_validators={
        "data_access": lambda user, resource: user.clearance_level >= resource.sensitivity_level,
        "model_deploy": lambda user, resource: user.department == "ml_ops"
    }
)

# Protected tool with fine-grained permissions
@mcp_server.tool(
    description="Execute sensitive data operations",
    requires_auth=True,
    required_permissions=["execute"],
    required_roles=["analyst", "admin"],
    resource_permission="datasets:update"
)
async def sensitive_data_operation(
    operation: str,
    dataset_id: str,
    parameters: dict,
    user_context=None  # Automatically injected by auth system
) -> dict:
    """
    Execute sensitive data operations with proper authorization.
    """
    # Additional authorization checks
    if operation == "delete" and user_context.role != "admin":
        raise PermissionError("Delete operations require admin role")

    # Check resource-specific permissions
    dataset = await get_dataset(dataset_id)
    if not permission_manager.check_resource_permission(
        user_context, "datasets", operation, dataset
    ):
        raise PermissionError(f"Insufficient permissions for {operation} on dataset {dataset_id}")

    # Execute operation
    result = await execute_data_operation(operation, dataset, parameters)

    # Audit log
    await audit_logger.log_operation(
        user_id=user_context.user_id,
        operation=operation,
        resource_type="dataset",
        resource_id=dataset_id,
        success=True,
        details=parameters
    )

    return result
```

### Streaming and Large Data Handling

```python
from kailash.mcp_server.advanced_features import StreamingHandler

# Streaming tool for large datasets
@mcp_server.streaming_tool(
    description="Stream large dataset processing results",
    chunk_size=1000,
    compression=True
)
async def stream_dataset_processing(
    dataset_path: str,
    processing_type: str,
    batch_size: int = 1000
) -> AsyncGenerator[dict, None]:
    """
    Stream processing results for large datasets.
    """
    async with StreamingHandler("dataset_processing") as stream:
        # Send metadata first
        yield {
            "type": "metadata",
            "dataset_path": dataset_path,
            "processing_type": processing_type,
            "timestamp": time.time()
        }

        # Process data in batches
        total_processed = 0
        async for batch in process_dataset_in_batches(dataset_path, batch_size):
            # Process the batch
            processed_batch = await process_batch(batch, processing_type)

            # Yield batch results
            yield {
                "type": "batch_result",
                "batch_number": total_processed // batch_size + 1,
                "batch_size": len(processed_batch),
                "results": processed_batch,
                "progress": {
                    "processed": total_processed + len(processed_batch),
                    "percentage": ((total_processed + len(processed_batch)) / get_dataset_size(dataset_path)) * 100
                }
            }

            total_processed += len(processed_batch)

            # Stream control
            if stream.should_pause():
                await stream.wait_for_resume()

        # Send completion message
        yield {
            "type": "completion",
            "total_processed": total_processed,
            "processing_complete": True,
            "summary": await generate_processing_summary(total_processed)
        }

# Binary resource handler
@mcp_server.resource(
    uri_pattern="binary://{resource_type}/{resource_id}",
    description="Handle binary resources like images, models, datasets"
)
async def binary_resource_handler(resource_type: str, resource_id: str) -> dict:
    """
    Handle binary resources with proper encoding and metadata.
    """
    resource_path = await get_resource_path(resource_type, resource_id)

    if not resource_path.exists():
        raise FileNotFoundError(f"Resource {resource_type}/{resource_id} not found")

    # Get resource metadata
    metadata = await get_resource_metadata(resource_path)

    # Handle different resource types
    if resource_type == "image":
        return {
            "uri": f"binary://image/{resource_id}",
            "mimeType": metadata.mime_type,
            "blob": resource_path.read_bytes(),
            "metadata": {
                "width": metadata.width,
                "height": metadata.height,
                "format": metadata.format,
                "size_bytes": metadata.size
            }
        }

    elif resource_type == "model":
        return {
            "uri": f"binary://model/{resource_id}",
            "mimeType": "application/octet-stream",
            "blob": resource_path.read_bytes(),
            "metadata": {
                "model_type": metadata.model_type,
                "framework": metadata.framework,
                "version": metadata.version,
                "size_bytes": metadata.size,
                "parameters": metadata.parameter_count
            }
        }

    elif resource_type == "dataset":
        # For large datasets, provide streaming access
        return {
            "uri": f"binary://dataset/{resource_id}",
            "mimeType": "application/octet-stream",
            "streaming": True,
            "metadata": {
                "format": metadata.format,
                "rows": metadata.row_count,
                "columns": metadata.column_count,
                "size_bytes": metadata.size,
                "schema": metadata.schema
            }
        }
```

## Production MCP Deployment

### Complete Production Server

```python
async def create_production_mcp_server():
    """Create a production-ready MCP server with all features."""

    # Authentication setup
    auth_provider = JWTAuth(
        secret_key=os.getenv("JWT_SECRET_KEY"),
        algorithm="HS256",
        token_expiry_hours=24
    )

    # Permission management
    permission_manager = PermissionManager(
        roles={
            "admin": ["read", "write", "execute", "manage", "deploy"],
            "data_scientist": ["read", "write", "execute"],
            "analyst": ["read", "write"],
            "viewer": ["read"]
        }
    )

    # Circuit breaker for resilience
    circuit_breaker_config = {
        "failure_threshold": 10,
        "timeout_seconds": 60,
        "half_open_max_calls": 5
    }

    # Comprehensive monitoring
    monitoring_config = {
        "enable_metrics": True,
        "metrics_export_format": "prometheus",
        "metrics_export_port": 9090,
        "enable_health_checks": True,
        "health_check_interval": 30,
        "enable_distributed_tracing": True,
        "tracing_sample_rate": 0.1
    }

    # Initialize server
    server = MCPServer(
        name="production-analytics-server",
        version="2.0.0",
        description="Production analytics server with enterprise features",

        auth_provider=auth_provider,
        permission_manager=permission_manager,

        # Transport with security
        transport=EnhancedStdioTransport(
            enable_compression=True,
            enable_encryption=True,
            max_message_size=50 * 1024 * 1024  # 50MB
        ),

        # Caching strategy
        enable_caching=True,
        cache_config={
            "backend": "redis",
            "redis_url": os.getenv("REDIS_URL", "redis://localhost:6379"),
            "default_ttl": 300,
            "max_size": 10000
        },

        # Rate limiting
        rate_limit_config={
            "global_requests_per_minute": 1000,
            "per_user_requests_per_minute": 100,
            "burst_size": 50
        },

        # Circuit breaker
        circuit_breaker_config=circuit_breaker_config,

        # Monitoring
        **monitoring_config
    )

    # Register production tools
    await register_production_tools(server)

    return server

async def register_production_tools(server: MCPServer):
    """Register all production tools with proper configuration."""

    # Data analysis tools
    server.register_node_tool(
        CSVReaderNode, "read_csv",
        description="Read and parse CSV files",
        required_permissions=["read"],
        cache_ttl=300
    )

    server.register_node_tool(
        PythonCodeNode, "execute_python",
        description="Execute Python code safely",
        required_permissions=["execute"],
        required_roles=["data_scientist", "admin"],
        rate_limit=10  # Limited for security
    )

    # AI/ML tools
    server.register_node_tool(
        LLMAgentNode, "ai_assistant",
        description="AI-powered analysis and insights",
        required_permissions=["write"],
        cache_ttl=1800
    )

    # Workflow tools
    server.register_workflow_tool(
        "data_pipeline", await create_data_analysis_pipeline(),
        description="Complete data analysis pipeline",
        required_permissions=["execute"],
        required_roles=["data_scientist", "admin"],
        cache_ttl=600
    )

    # System tools
    @server.tool(
        description="Get server health and status",
        required_permissions=["read"]
    )
    async def health_check() -> dict:
        return {
            "status": "healthy",
            "version": server.version,
            "uptime": time.time() - server.start_time,
            "tools_registered": len(server.tools),
            "active_connections": server.connection_count,
            "metrics": await server.get_metrics()
        }

# Deploy production server
async def deploy_production_server():
    """Deploy the production MCP server."""

    server = await create_production_mcp_server()

    try:
        print("Starting production MCP server...")
        await server.start()

        print(f"Server started: {server.name} v{server.version}")
        print(f"Available tools: {len(server.tools)}")
        print("Server ready for connections")

        # Keep server running
        await server.wait_for_shutdown()

    except Exception as e:
        print(f"Server error: {e}")
        raise

    finally:
        await server.cleanup()

# Run the production server
if __name__ == "__main__":
    import asyncio
    asyncio.run(deploy_production_server())
```

## Best Practices

### 1. Tool Design Patterns

```python
# Follow these patterns for robust tool design
class ToolDesignPatterns:

    @staticmethod
    def input_validation_pattern():
        """Always validate and sanitize inputs."""
        return {
            "use_pydantic_models": True,
            "validate_file_paths": True,
            "sanitize_code_inputs": True,
            "check_resource_limits": True,
            "validate_permissions": True
        }

    @staticmethod
    def error_handling_pattern():
        """Comprehensive error handling."""
        return {
            "use_structured_errors": True,
            "provide_error_context": True,
            "log_errors_appropriately": True,
            "return_actionable_messages": True,
            "implement_graceful_degradation": True
        }

    @staticmethod
    def performance_pattern():
        """Optimize for performance."""
        return {
            "use_caching_strategically": True,
            "implement_streaming_for_large_data": True,
            "use_connection_pooling": True,
            "monitor_resource_usage": True,
            "implement_circuit_breakers": True
        }
```

### 2. Security Best Practices

```python
# Security-focused tool implementation
@mcp_server.tool(
    description="Secure file operations",
    requires_auth=True,
    required_permissions=["file_access"],
    audit_logging=True
)
async def secure_file_operation(file_path: str, operation: str, user_context=None) -> dict:
    """
    Secure file operations with comprehensive validation.
    """
    # 1. Path validation
    safe_path = validate_and_sanitize_path(file_path)
    if not safe_path:
        raise ValueError("Invalid file path")

    # 2. Permission checking
    if not check_file_permissions(user_context, safe_path, operation):
        raise PermissionError("Insufficient file permissions")

    # 3. Resource limits
    if operation == "read":
        file_size = safe_path.stat().st_size
        if file_size > user_context.max_file_size:
            raise ValueError("File too large for user tier")

    # 4. Audit logging
    await audit_logger.log_file_access(
        user_id=user_context.user_id,
        file_path=str(safe_path),
        operation=operation,
        timestamp=time.time()
    )

    # 5. Execute operation
    result = await execute_file_operation(safe_path, operation)

    return result
```

### 3. Monitoring and Observability

```python
# Comprehensive monitoring setup
async def setup_monitoring(server: MCPServer):
    """Setup comprehensive monitoring for MCP server."""

    # Metrics collection
    server.enable_metrics_collection({
        "tool_execution_time": "histogram",
        "tool_success_rate": "counter",
        "concurrent_requests": "gauge",
        "cache_hit_rate": "gauge",
        "error_rate": "counter"
    })

    # Health checks
    server.register_health_checks({
        "database_connectivity": check_database_health,
        "external_api_connectivity": check_external_apis,
        "cache_connectivity": check_cache_health,
        "disk_space": check_disk_space,
        "memory_usage": check_memory_usage
    })

    # Distributed tracing
    server.enable_distributed_tracing({
        "service_name": "mcp-analytics-server",
        "trace_sampling_rate": 0.1,
        "export_endpoint": "http://jaeger:14268/api/traces"
    })

    # Alerting rules
    server.configure_alerting({
        "high_error_rate": {
            "condition": "error_rate > 0.05",
            "duration": "5m",
            "action": "send_alert"
        },
        "high_latency": {
            "condition": "avg_response_time > 5s",
            "duration": "2m",
            "action": "send_alert"
        }
    })
```

## Related Guides

**Prerequisites:**
- [Cyclic Workflows Guide](31-cyclic-workflows-guide.md) - Workflow cycles
- [Edge Computing Guide](30-edge-computing-guide.md) - Edge deployment

**Next Steps:**
- [Database Integration Guide](33-database-integration-guide.md) - Database patterns
- [Monitoring and Observability Guide](34-monitoring-observability-guide.md) - Production monitoring

---

**Build powerful MCP servers with enterprise-grade features and seamless node integration!**
