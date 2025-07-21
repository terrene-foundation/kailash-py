# MCP Tool Execution Guide

*Advanced patterns for MCP tool implementation and execution*

## Overview

This guide covers advanced MCP (Model Context Protocol) tool execution patterns, including complex tool implementations, execution strategies, and integration with AI agents.

## Prerequisites

- Completed [MCP Development Guide](17-mcp-development-guide.md)
- Understanding of async programming
- Familiarity with AI agent concepts

## Advanced Tool Implementation

### Stateful Tools

```python
from kailash.mcp_server import MCPServer, MCPTool

class SessionManager:
    """Manage user sessions across tool calls."""
    def __init__(self):
        self.sessions = {}

    def get_session(self, session_id: str) -> dict:
        if session_id not in self.sessions:
            self.sessions[session_id] = {
                "created_at": datetime.now(),
                "data": {},
                "history": []
            }
        return self.sessions[session_id]

# Create server with session manager
server = MCPServer("stateful_tools")
session_manager = SessionManager()

@server.tool()
async def start_analysis(session_id: str, data: list) -> dict:
    """Start a multi-step analysis process."""
    session = session_manager.get_session(session_id)

    # Store data in session
    session["data"]["raw_data"] = data
    session["data"]["analysis_id"] = str(uuid.uuid4())
    session["history"].append({
        "action": "start_analysis",
        "timestamp": datetime.now().isoformat()
    })

    # Begin analysis
    initial_stats = {
        "count": len(data),
        "min": min(data) if data else None,
        "max": max(data) if data else None
    }

    session["data"]["initial_stats"] = initial_stats

    return {
        "session_id": session_id,
        "analysis_id": session["data"]["analysis_id"],
        "status": "started",
        "initial_stats": initial_stats
    }

@server.tool()
async def continue_analysis(
    session_id: str,
    analysis_type: str = "statistical"
) -> dict:
    """Continue analysis with specific type."""
    session = session_manager.get_session(session_id)

    if "raw_data" not in session["data"]:
        return {"error": "No analysis started for this session"}

    data = session["data"]["raw_data"]

    if analysis_type == "statistical":
        import statistics
        results = {
            "mean": statistics.mean(data),
            "median": statistics.median(data),
            "stdev": statistics.stdev(data) if len(data) > 1 else 0
        }
    elif analysis_type == "distribution":
        results = {
            "quartiles": [
                min(data),
                statistics.quantiles(data, n=4)[0],
                statistics.quantiles(data, n=4)[2],
                max(data)
            ]
        }
    else:
        return {"error": f"Unknown analysis type: {analysis_type}"}

    session["data"][f"{analysis_type}_results"] = results
    session["history"].append({
        "action": f"continue_analysis_{analysis_type}",
        "timestamp": datetime.now().isoformat()
    })

    return {
        "session_id": session_id,
        "analysis_type": analysis_type,
        "results": results
    }
```

### Streaming Tools

```python
@server.tool(streaming=True)
async def process_large_dataset(
    file_path: str,
    chunk_size: int = 1000
) -> AsyncGenerator[dict, None]:
    """Process large dataset in chunks."""
    total_processed = 0

    async with aiofiles.open(file_path, 'r') as file:
        while True:
            # Read chunk
            lines = []
            for _ in range(chunk_size):
                line = await file.readline()
                if not line:
                    break
                lines.append(line.strip())

            if not lines:
                break

            # Process chunk
            processed_chunk = process_lines(lines)
            total_processed += len(lines)

            # Yield progress update
            yield {
                "type": "progress",
                "processed": len(lines),
                "total_processed": total_processed,
                "chunk_results": processed_chunk
            }

    # Final result
    yield {
        "type": "complete",
        "total_processed": total_processed,
        "status": "success"
    }
```

### Composite Tools

```python
@server.tool()
async def analyze_and_visualize(
    data: list,
    visualization_type: str = "histogram",
    output_format: str = "png"
) -> dict:
    """Composite tool that analyzes data and creates visualization."""

    # Step 1: Analyze data
    analysis_result = await analyze_data_internal(data)

    # Step 2: Create visualization
    viz_result = await create_visualization_internal(
        data,
        analysis_result,
        visualization_type
    )

    # Step 3: Export in requested format
    export_result = await export_visualization_internal(
        viz_result,
        output_format
    )

    return {
        "analysis": analysis_result,
        "visualization": {
            "type": visualization_type,
            "format": output_format,
            "url": export_result["url"],
            "size": export_result["size"]
        },
        "composite_execution_time": sum([
            analysis_result["execution_time"],
            viz_result["execution_time"],
            export_result["execution_time"]
        ])
    }
```

## Tool Execution Strategies

### Parallel Tool Execution

```python
from kailash.mcp_server import MCPExecutor

class ParallelExecutor(MCPExecutor):
    """Execute multiple tools in parallel."""

    async def execute_parallel(
        self,
        tool_calls: list[dict]
    ) -> list[dict]:
        """Execute multiple tool calls in parallel."""
        tasks = []

        for call in tool_calls:
            task = self.execute_tool(
                call["tool_name"],
                call["parameters"]
            )
            tasks.append(task)

        # Execute all in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                final_results.append({
                    "tool": tool_calls[i]["tool_name"],
                    "error": str(result),
                    "success": False
                })
            else:
                final_results.append({
                    "tool": tool_calls[i]["tool_name"],
                    "result": result,
                    "success": True
                })

        return final_results

# Usage
executor = ParallelExecutor(server)

results = await executor.execute_parallel([
    {"tool_name": "fetch_user_data", "parameters": {"user_id": "123"}},
    {"tool_name": "fetch_orders", "parameters": {"user_id": "123"}},
    {"tool_name": "calculate_statistics", "parameters": {"user_id": "123"}}
])
```

### Conditional Tool Execution

```python
@server.tool()
async def smart_data_processor(
    data: dict,
    processing_mode: str = "auto"
) -> dict:
    """Process data with conditional tool execution."""

    # Analyze data characteristics
    data_profile = await profile_data(data)

    # Determine processing strategy
    if processing_mode == "auto":
        if data_profile["size"] > 1000000:
            processing_mode = "distributed"
        elif data_profile["complexity"] > 0.8:
            processing_mode = "advanced"
        else:
            processing_mode = "simple"

    # Execute appropriate tools
    if processing_mode == "distributed":
        # Use distributed processing tools
        result = await execute_tool("distributed_processor", {
            "data": data,
            "partitions": 10
        })
    elif processing_mode == "advanced":
        # Chain multiple analysis tools
        cleaned = await execute_tool("data_cleaner", {"data": data})
        analyzed = await execute_tool("advanced_analyzer", {"data": cleaned})
        result = await execute_tool("result_formatter", {"analysis": analyzed})
    else:
        # Simple processing
        result = await execute_tool("simple_processor", {"data": data})

    return {
        "mode": processing_mode,
        "profile": data_profile,
        "result": result
    }
```

### Tool Orchestration

```python
class ToolOrchestrator:
    """Orchestrate complex tool workflows."""

    def __init__(self, server: MCPServer):
        self.server = server
        self.workflows = {}

    def define_workflow(self, name: str, steps: list):
        """Define a tool workflow."""
        self.workflows[name] = steps

    async def execute_workflow(
        self,
        workflow_name: str,
        initial_params: dict
    ) -> dict:
        """Execute a defined workflow."""
        if workflow_name not in self.workflows:
            raise ValueError(f"Unknown workflow: {workflow_name}")

        steps = self.workflows[workflow_name]
        context = {"params": initial_params, "results": {}}

        for step in steps:
            # Resolve parameters from context
            params = self._resolve_params(step["params"], context)

            # Execute tool
            result = await self.server.execute_tool(
                step["tool"],
                params
            )

            # Store result in context
            context["results"][step["name"]] = result

            # Check conditions
            if "condition" in step:
                if not self._evaluate_condition(step["condition"], context):
                    continue

        return context["results"]

# Define workflow
orchestrator = ToolOrchestrator(server)

orchestrator.define_workflow("user_analysis", [
    {
        "name": "fetch_user",
        "tool": "get_user_data",
        "params": {"user_id": "{params.user_id}"}
    },
    {
        "name": "fetch_activity",
        "tool": "get_user_activity",
        "params": {"user_id": "{params.user_id}", "days": 30}
    },
    {
        "name": "analyze",
        "tool": "analyze_user_behavior",
        "params": {
            "user_data": "{results.fetch_user}",
            "activity_data": "{results.fetch_activity}"
        }
    },
    {
        "name": "generate_report",
        "tool": "create_report",
        "params": {"analysis": "{results.analyze}"},
        "condition": "results.analyze.score > 0.5"
    }
])

# Execute workflow
results = await orchestrator.execute_workflow(
    "user_analysis",
    {"user_id": "12345"}
)
```

## Integration with AI Agents

### Tool Selection Strategy

```python
class IntelligentToolSelector:
    """AI-driven tool selection."""

    def __init__(self, tools: list[MCPTool]):
        self.tools = tools
        self.tool_embeddings = self._compute_embeddings()

    async def select_tools(
        self,
        query: str,
        max_tools: int = 3
    ) -> list[str]:
        """Select most relevant tools for query."""
        # Get query embedding
        query_embedding = await self._get_embedding(query)

        # Calculate similarities
        similarities = []
        for tool_name, embedding in self.tool_embeddings.items():
            similarity = self._cosine_similarity(query_embedding, embedding)
            similarities.append((tool_name, similarity))

        # Sort by relevance
        similarities.sort(key=lambda x: x[1], reverse=True)

        # Return top tools
        return [name for name, _ in similarities[:max_tools]]

    def _compute_embeddings(self) -> dict:
        """Pre-compute tool embeddings from descriptions."""
        embeddings = {}
        for tool in self.tools:
            # Combine name and description
            text = f"{tool.name}: {tool.description}"
            embeddings[tool.name] = self._get_embedding(text)
        return embeddings
```

### Execution Monitoring

```python
class ToolExecutionMonitor:
    """Monitor and analyze tool execution."""

    def __init__(self):
        self.executions = []
        self.metrics = defaultdict(lambda: {
            "count": 0,
            "total_time": 0,
            "errors": 0,
            "success_rate": 0
        })

    async def monitor_execution(
        self,
        tool_name: str,
        parameters: dict,
        executor: callable
    ) -> dict:
        """Monitor tool execution."""
        start_time = time.time()
        execution_id = str(uuid.uuid4())

        try:
            # Execute tool
            result = await executor(tool_name, parameters)

            # Record success
            execution_time = time.time() - start_time
            self._record_execution(
                execution_id,
                tool_name,
                parameters,
                result,
                execution_time,
                success=True
            )

            return result

        except Exception as e:
            # Record failure
            execution_time = time.time() - start_time
            self._record_execution(
                execution_id,
                tool_name,
                parameters,
                str(e),
                execution_time,
                success=False
            )
            raise

    def get_tool_metrics(self, tool_name: str) -> dict:
        """Get metrics for specific tool."""
        return self.metrics[tool_name]

    def get_recommendations(self) -> list[dict]:
        """Get optimization recommendations."""
        recommendations = []

        for tool, metrics in self.metrics.items():
            # High error rate
            if metrics["success_rate"] < 0.9:
                recommendations.append({
                    "tool": tool,
                    "issue": "high_error_rate",
                    "suggestion": "Review error logs and add retry logic"
                })

            # Slow execution
            avg_time = metrics["total_time"] / max(metrics["count"], 1)
            if avg_time > 5.0:
                recommendations.append({
                    "tool": tool,
                    "issue": "slow_execution",
                    "suggestion": "Consider caching or optimization"
                })

        return recommendations
```

## Best Practices

### 1. Tool Versioning

```python
@server.tool(version="2.0")
async def process_data_v2(
    data: list,
    options: dict = None
) -> dict:
    """Enhanced data processor with backward compatibility."""
    # Check if old version parameters
    if options is None and isinstance(data, dict):
        # Handle v1 parameters
        return await process_data_v1(data)

    # New version logic
    return await enhanced_processing(data, options)
```

### 2. Input Validation

```python
from pydantic import BaseModel, validator

class DataProcessingParams(BaseModel):
    data: list
    threshold: float = 0.5

    @validator('threshold')
    def threshold_range(cls, v):
        if not 0 <= v <= 1:
            raise ValueError('Threshold must be between 0 and 1')
        return v

@server.tool()
async def validated_processor(params: DataProcessingParams) -> dict:
    """Process with validated parameters."""
    # Parameters are guaranteed valid
    return await process_data(params.data, params.threshold)
```

### 3. Error Context

```python
@server.tool()
async def robust_tool(data: dict) -> dict:
    """Tool with rich error context."""
    try:
        result = await process_complex_data(data)
        return {"success": True, "result": result}
    except ValidationError as e:
        return {
            "success": False,
            "error": "validation_error",
            "details": str(e),
            "suggestion": "Check data format matches schema"
        }
    except ResourceError as e:
        return {
            "success": False,
            "error": "resource_error",
            "details": str(e),
            "suggestion": "Retry after resource becomes available"
        }
```

## Related Guides

**Prerequisites:**
- [MCP Development Guide](17-mcp-development-guide.md) - MCP basics

**Advanced Topics:**
- [AI Agent Integration](../ai/) - Agent patterns
- [Performance Optimization](../performance/) - Tool optimization

---

**Build sophisticated MCP tools with advanced execution patterns and AI integration!**
