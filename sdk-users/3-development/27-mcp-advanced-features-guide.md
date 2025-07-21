# MCP Advanced Features Guide

*Sophisticated MCP capabilities including structured outputs, multimodal content, and progress reporting*

## Overview

This guide covers advanced MCP features that enable sophisticated client-server interactions. These features include structured tool outputs with validation, multimodal content support, progress reporting, resource subscriptions, and request cancellation - all designed for production-ready MCP implementations.

## Prerequisites

- Completed [Enhanced MCP Server Guide](23-enhanced-mcp-server-guide.md)
- Completed [MCP Transport Layers Guide](26-mcp-transport-layers-guide.md)
- Understanding of JSON Schema
- Familiarity with async programming

## Structured Tool Outputs

Create tools with validated, schema-enforced outputs for reliable client consumption.

### Basic Structured Tools

```python
from kailash.mcp_server.advanced_features import StructuredTool
from kailash.mcp_server import MCPServer

server = MCPServer("advanced-server", enable_cache=True, enable_metrics=True)

# Tool with structured output schema
@StructuredTool(
    output_schema={
        "type": "object",
        "properties": {
            "results": {
                "type": "array",
                "items": {"type": "string"}
            },
            "count": {"type": "integer"},
            "success": {"type": "boolean"}
        },
        "required": ["results", "count", "success"]
    }
)
@server.tool()
async def search_database(query: str) -> dict:
    """Search database with structured output."""
    # Perform search
    results = await database.search(query)

    # Return structured data (automatically validated)
    return {
        "results": [str(item) for item in results],
        "count": len(results),
        "success": True
    }
```

### Advanced Schema Validation

```python
# Complex nested schema with validation
@StructuredTool(
    output_schema={
        "type": "object",
        "properties": {
            "user": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string"},
                    "email": {"type": "string", "format": "email"},
                    "roles": {
                        "type": "array",
                        "items": {"type": "string"}
                    }
                },
                "required": ["id", "name", "email"]
            },
            "permissions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "resource": {"type": "string"},
                        "actions": {
                            "type": "array",
                            "items": {"type": "string"}
                        }
                    }
                }
            },
            "metadata": {
                "type": "object",
                "additionalProperties": {"type": "string"}
            }
        },
        "required": ["user", "permissions"]
    }
)
@server.tool()
async def get_user_profile(user_id: int) -> dict:
    """Get user profile with comprehensive data."""
    user_data = await user_service.get_user(user_id)
    permissions = await permission_service.get_user_permissions(user_id)

    return {
        "user": {
            "id": user_data.id,
            "name": user_data.full_name,
            "email": user_data.email,
            "roles": user_data.roles
        },
        "permissions": [
            {
                "resource": perm.resource,
                "actions": perm.allowed_actions
            } for perm in permissions
        ],
        "metadata": {
            "last_login": user_data.last_login.isoformat(),
            "account_type": user_data.account_type
        }
    }
```

## Multimodal Content

Handle rich content including text, images, audio, and resource references.

### Basic Multimodal Content

```python
from kailash.mcp_server.advanced_features import MultiModalContent, ContentType

@server.tool()
async def generate_report(data_source: str) -> dict:
    """Generate a multimodal report with charts and data."""
    content = MultiModalContent()

    # Add text description
    content.add_text("## Data Analysis Report\n\nKey findings from the analysis:")

    # Add chart image
    chart_data = await generate_chart(data_source)
    content.add_image(
        data=chart_data,
        mime_type="image/png",
        description="Sales trend chart for Q4"
    )

    # Add data file reference
    content.add_resource(
        uri=f"data://{data_source}/export.csv",
        mime_type="text/csv",
        description="Raw data export"
    )

    # Add analysis summary
    summary = await analyze_data(data_source)
    content.add_text(f"\n**Summary**: {summary}")

    return {"content": content.to_list()}
```

### Advanced Multimodal Features

```python
# Multimodal content with annotations and metadata
@server.tool()
async def create_presentation(topic: str) -> dict:
    """Create an interactive presentation."""
    content = MultiModalContent()

    # Title slide
    content.add_text(f"# {topic}\n\n*Generated on {datetime.now().isoformat()}*")

    # Add slides with images and annotations
    slides = await presentation_service.create_slides(topic)

    for i, slide in enumerate(slides):
        # Slide content
        content.add_text(f"\n## Slide {i+1}: {slide.title}\n\n{slide.content}")

        # Slide image
        if slide.image:
            content.add_image(
                data=slide.image,
                mime_type="image/jpeg",
                description=f"Visual for slide {i+1}",
                metadata={
                    "slide_number": i+1,
                    "slide_title": slide.title,
                    "generated": True
                }
            )

        # Speaker notes annotation
        content.add_annotation(
            type="speaker_notes",
            content=slide.speaker_notes,
            metadata={"slide": i+1}
        )

    # Interactive elements
    content.add_annotation(
        type="interactive",
        content="Click charts for detailed data",
        metadata={"type": "tooltip"}
    )

    return {
        "content": content.to_list(),
        "slide_count": len(slides),
        "interactive": True
    }
```

## Progress Reporting

Track and report progress for long-running operations.

### Basic Progress Reporting

```python
from kailash.mcp_server.advanced_features import ProgressReporter

@server.tool()
async def process_large_dataset(dataset_id: str) -> dict:
    """Process large dataset with progress reporting."""
    dataset = await get_dataset(dataset_id)
    total_items = len(dataset.items)

    async with ProgressReporter("processing", total=total_items) as progress:
        results = []

        for i, item in enumerate(dataset.items):
            # Process item
            result = await process_item(item)
            results.append(result)

            # Update progress
            await progress.update(
                current=i + 1,
                message=f"Processed {i + 1}/{total_items} items"
            )

            # Optional: Send intermediate results
            if (i + 1) % 100 == 0:
                await progress.send_partial_result({
                    "intermediate_count": i + 1,
                    "sample_results": results[-5:]  # Last 5 results
                })

        await progress.complete("Dataset processing completed successfully")

    return {
        "total_processed": len(results),
        "results": results,
        "success": True
    }
```

### Advanced Progress Features

```python
# Multi-stage progress with detailed reporting
@server.tool()
async def complex_analysis_pipeline(input_data: dict) -> dict:
    """Run complex analysis with multi-stage progress."""
    stages = ["validation", "preprocessing", "analysis", "visualization", "reporting"]

    async with ProgressReporter("pipeline", total=100) as progress:
        stage_progress = 0

        # Stage 1: Validation (20% of total)
        await progress.update(stage_progress, "Starting data validation...")
        validation_result = await validate_data(input_data)
        stage_progress += 20
        await progress.update(stage_progress, "Data validation complete")

        # Stage 2: Preprocessing (30% of total)
        await progress.update(stage_progress, "Preprocessing data...")

        preprocessed_data = []
        for i, chunk in enumerate(chunk_data(validation_result)):
            processed_chunk = await preprocess_chunk(chunk)
            preprocessed_data.append(processed_chunk)

            # Update within stage
            chunk_progress = stage_progress + (10 * (i + 1) / len(list(chunk_data(validation_result))))
            await progress.update(
                chunk_progress,
                f"Preprocessing chunk {i + 1}",
                metadata={"stage": "preprocessing", "chunk": i + 1}
            )

        stage_progress += 30
        await progress.update(stage_progress, "Preprocessing complete")

        # Stage 3: Analysis (30% of total)
        await progress.update(stage_progress, "Running analysis algorithms...")
        analysis_results = await run_analysis(preprocessed_data)
        stage_progress += 30
        await progress.update(stage_progress, "Analysis complete")

        # Stage 4: Visualization (10% of total)
        await progress.update(stage_progress, "Generating visualizations...")
        charts = await generate_visualizations(analysis_results)
        stage_progress += 10
        await progress.update(stage_progress, "Visualizations complete")

        # Stage 5: Reporting (10% of total)
        await progress.update(stage_progress, "Generating final report...")
        report = await generate_report(analysis_results, charts)
        stage_progress += 10

        await progress.complete(
            "Analysis pipeline completed successfully",
            final_result={
                "stages_completed": len(stages),
                "total_data_points": len(preprocessed_data),
                "analysis_summary": analysis_results.summary
            }
        )

    return {
        "report": report,
        "visualizations": charts,
        "metadata": {
            "pipeline_stages": stages,
            "execution_time": time.time() - start_time
        }
    }
```

## Resource Templates and Subscriptions

Dynamic resources with change notifications and subscriptions.

### Resource Templates

```python
from kailash.mcp_server.advanced_features import ResourceTemplate

# Dynamic file system resource
file_template = ResourceTemplate(
    uri_template="files://{path}",
    name="File System Access",
    description="Access files and directories",
    supports_subscription=True
)

@server.resource(file_template)
async def file_resource(path: str) -> dict:
    """Dynamic file resource."""
    file_path = Path(path)

    if not file_path.exists():
        return {"error": "File not found", "path": path}

    if file_path.is_file():
        # File content
        content = file_path.read_text()
        return {
            "type": "file",
            "path": path,
            "content": content,
            "size": file_path.stat().st_size,
            "modified": file_path.stat().st_mtime
        }
    else:
        # Directory listing
        items = [item.name for item in file_path.iterdir()]
        return {
            "type": "directory",
            "path": path,
            "items": items,
            "count": len(items)
        }

# Database resource template
db_template = ResourceTemplate(
    uri_template="db://{table}/{id?}",
    name="Database Access",
    description="Access database tables and records"
)

@server.resource(db_template)
async def database_resource(table: str, id: Optional[str] = None) -> dict:
    """Dynamic database resource."""
    if id:
        # Single record
        record = await db.get_record(table, id)
        return {"record": record, "table": table, "id": id}
    else:
        # Table schema and stats
        schema = await db.get_table_schema(table)
        count = await db.get_record_count(table)
        return {"schema": schema, "record_count": count, "table": table}
```

### Resource Subscriptions

```python
# Resource change monitoring
@server.resource_subscription_handler
async def handle_resource_subscription(uri: str, callback: Callable):
    """Handle resource change subscriptions."""
    if uri.startswith("files://"):
        # File system monitoring
        path = uri[8:]  # Remove "files://" prefix

        async def file_watcher():
            last_modified = {}
            while True:
                try:
                    file_path = Path(path)
                    if file_path.exists():
                        current_modified = file_path.stat().st_mtime
                        if path not in last_modified:
                            last_modified[path] = current_modified
                        elif current_modified > last_modified[path]:
                            # File changed
                            await callback({
                                "type": "updated",
                                "uri": uri,
                                "timestamp": current_modified,
                                "size": file_path.stat().st_size
                            })
                            last_modified[path] = current_modified
                except Exception as e:
                    await callback({
                        "type": "error",
                        "uri": uri,
                        "error": str(e)
                    })

                await asyncio.sleep(1)  # Check every second

        # Start monitoring task
        task = asyncio.create_task(file_watcher())
        return task

    elif uri.startswith("db://"):
        # Database change monitoring
        table = uri.split("/")[2]

        async def db_watcher():
            last_count = await db.get_record_count(table)
            while True:
                try:
                    current_count = await db.get_record_count(table)
                    if current_count != last_count:
                        change_type = "created" if current_count > last_count else "deleted"
                        await callback({
                            "type": change_type,
                            "uri": uri,
                            "table": table,
                            "count_change": current_count - last_count
                        })
                        last_count = current_count
                except Exception as e:
                    await callback({
                        "type": "error",
                        "uri": uri,
                        "error": str(e)
                    })

                await asyncio.sleep(5)  # Check every 5 seconds

        task = asyncio.create_task(db_watcher())
        return task
```

## Request Cancellation

Handle cancellation of long-running operations gracefully.

### Cancellation Context

```python
from kailash.mcp_server.advanced_features import CancellationContext

@server.tool()
async def long_running_operation(data: dict) -> dict:
    """Cancellable long-running operation."""
    async with CancellationContext() as cancel_ctx:
        results = []
        total_items = len(data.get("items", []))

        for i, item in enumerate(data.get("items", [])):
            # Check for cancellation
            if cancel_ctx.is_cancelled():
                return {
                    "cancelled": True,
                    "partial_results": results,
                    "processed_count": len(results),
                    "total_count": total_items,
                    "cancellation_reason": cancel_ctx.cancellation_reason
                }

            # Process item (potentially slow operation)
            try:
                result = await process_item_with_timeout(item, timeout=10)
                results.append(result)
            except asyncio.TimeoutError:
                if cancel_ctx.is_cancelled():
                    break
                # Continue with timeout, but check cancellation
                continue

            # Periodic cancellation check
            if i % 10 == 0 and cancel_ctx.is_cancelled():
                break

        return {
            "cancelled": False,
            "results": results,
            "processed_count": len(results),
            "total_count": total_items,
            "success": True
        }

# Cancellation with cleanup
@server.tool()
async def complex_operation_with_cleanup(config: dict) -> dict:
    """Operation with proper resource cleanup on cancellation."""
    resources = []

    async with CancellationContext() as cancel_ctx:
        try:
            # Allocate resources
            db_connection = await allocate_database_connection()
            resources.append(("db", db_connection))

            temp_files = await create_temp_files(config)
            resources.append(("files", temp_files))

            # Long-running work
            results = []
            for task in generate_tasks(config):
                if cancel_ctx.is_cancelled():
                    break

                result = await execute_task(task, db_connection)
                results.append(result)

            return {"results": results, "success": True}

        finally:
            # Always cleanup resources
            for resource_type, resource in resources:
                try:
                    if resource_type == "db":
                        await resource.close()
                    elif resource_type == "files":
                        for file in resource:
                            file.unlink(missing_ok=True)
                except Exception as e:
                    logger.error(f"Cleanup error for {resource_type}: {e}")
```

## Streaming Support

Handle large responses with streaming for optimal performance.

### Streaming Handlers

```python
from kailash.mcp_server.advanced_features import StreamingHandler

@server.tool(streaming=True)
async def stream_large_dataset(query: dict) -> AsyncGenerator[dict, None]:
    """Stream large dataset results."""
    async with StreamingHandler("dataset_stream") as stream:
        # Send metadata first
        yield {
            "type": "metadata",
            "query": query,
            "timestamp": time.time()
        }

        # Stream data in chunks
        async for chunk in database.stream_query_results(query):
            yield {
                "type": "data_chunk",
                "data": chunk,
                "chunk_size": len(chunk)
            }

            # Optional: Add stream control
            if stream.should_pause():
                await stream.wait_for_resume()

        # Send completion
        yield {
            "type": "complete",
            "total_chunks": stream.chunks_sent,
            "total_bytes": stream.bytes_sent
        }

# Streaming with progress
@server.tool(streaming=True)
async def export_data_with_progress(export_config: dict) -> AsyncGenerator[dict, None]:
    """Export data with streaming progress."""
    total_records = await get_export_record_count(export_config)
    processed = 0

    async with StreamingHandler("data_export") as stream:
        # Initial response
        yield {
            "type": "export_started",
            "total_records": total_records,
            "format": export_config.get("format", "json")
        }

        # Stream data with progress updates
        async for batch in export_data_in_batches(export_config):
            # Send data batch
            yield {
                "type": "data_batch",
                "records": batch,
                "batch_size": len(batch)
            }

            processed += len(batch)

            # Send progress update
            yield {
                "type": "progress",
                "processed": processed,
                "total": total_records,
                "percentage": (processed / total_records) * 100
            }

        # Final summary
        yield {
            "type": "export_complete",
            "total_processed": processed,
            "export_size_bytes": stream.bytes_sent
        }
```

## Tool Annotations and Metadata

Enhance tools with rich metadata and annotations for better client integration.

### Tool Annotations

```python
from kailash.mcp_server.advanced_features import ToolAnnotation

@server.tool()
@ToolAnnotation(
    category="data_processing",
    tags=["analytics", "reporting", "batch"],
    complexity="high",
    estimated_duration="5-30 minutes",
    resource_requirements={
        "memory": "2GB",
        "cpu": "2 cores",
        "disk": "1GB temp space"
    },
    security_level="restricted",
    rate_limit={"calls_per_hour": 10}
)
async def generate_analytics_report(parameters: dict) -> dict:
    """Generate comprehensive analytics report with annotations."""
    return await analytics_service.generate_report(parameters)

# Interactive tool with user input
@server.tool()
@ToolAnnotation(
    category="interactive",
    requires_user_input=True,
    input_prompts=[
        {"name": "confirmation", "type": "boolean", "prompt": "Proceed with deletion?"},
        {"name": "backup_location", "type": "string", "prompt": "Backup location:"}
    ]
)
async def delete_with_confirmation(resource_id: str) -> dict:
    """Delete resource with interactive confirmation."""
    # Tool can request user input through the annotation system
    confirmation = await request_user_input("confirmation")
    if not confirmation:
        return {"cancelled": True, "reason": "User cancelled"}

    backup_location = await request_user_input("backup_location")

    # Perform deletion with backup
    await backup_resource(resource_id, backup_location)
    await delete_resource(resource_id)

    return {
        "deleted": True,
        "resource_id": resource_id,
        "backup_location": backup_location
    }
```

## Best Practices

### 1. Schema Design

```python
# Use comprehensive schemas for reliability
COMPREHENSIVE_SCHEMA = {
    "type": "object",
    "properties": {
        "data": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "pattern": "^[a-zA-Z0-9-]+$"},
                "timestamp": {"type": "string", "format": "date-time"},
                "values": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 1,
                    "maxItems": 1000
                }
            },
            "required": ["id", "timestamp", "values"]
        },
        "metadata": {
            "type": "object",
            "additionalProperties": {"type": "string"}
        },
        "status": {
            "type": "string",
            "enum": ["success", "partial", "error"]
        }
    },
    "required": ["data", "status"],
    "additionalProperties": False
}
```

### 2. Progress Reporting

```python
# Always provide meaningful progress updates
async def progress_best_practices():
    async with ProgressReporter("operation", total=100) as progress:
        # Start with clear message
        await progress.update(0, "Initializing operation...")

        # Regular updates with context
        for i in range(100):
            await process_item(i)

            # Informative progress messages
            if i % 10 == 0:
                await progress.update(
                    i + 1,
                    f"Processing item {i + 1}/100 - {(i+1)/100*100:.1f}% complete",
                    metadata={
                        "current_item": i + 1,
                        "items_per_second": calculate_rate(i + 1)
                    }
                )

        # Clear completion message
        await progress.complete("Operation completed successfully")
```

### 3. Resource Management

```python
# Proper resource cleanup in all scenarios
async def resource_management_example():
    resources = []
    try:
        # Allocate resources
        conn = await get_connection()
        resources.append(conn)

        file_handle = await open_temp_file()
        resources.append(file_handle)

        # Use resources...

    finally:
        # Always cleanup
        for resource in reversed(resources):
            try:
                await resource.cleanup()
            except Exception as e:
                logger.error(f"Resource cleanup failed: {e}")
```

## Related Guides

**Prerequisites:**
- [Enhanced MCP Server Guide](23-enhanced-mcp-server-guide.md) - Server basics
- [MCP Transport Layers Guide](26-mcp-transport-layers-guide.md) - Transport configuration

**Next Steps:**
- [MCP Service Discovery Guide](24-mcp-service-discovery-guide.md) - Service discovery
- [MCP Transport Layers Guide](26-mcp-transport-layers-guide.md) - Transport configuration

---

**Implement sophisticated MCP features for production-ready client-server interactions!**
