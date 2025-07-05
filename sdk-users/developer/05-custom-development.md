# Custom Development - Build Nodes & Extensions

*Create custom nodes and extend Kailash SDK functionality*

## Prerequisites

- Completed [Fundamentals](01-fundamentals.md) - Core SDK concepts
- Completed [Workflows](02-workflows.md) - Basic workflow patterns
- Understanding of Python classes and inheritance
- Familiarity with type hints

## Basic Custom Node Structure

### Essential Rules for Custom Nodes

All custom nodes must inherit from the base `Node` class and implement required methods:

```python
from typing import Dict, Any
from kailash.nodes.base import Node, NodeParameter

class CustomProcessorNode(Node):
    """Custom data processing node."""

    def __init__(self, name, processing_mode: str = "standard", **kwargs):
        # ⚠️ CRITICAL: Set attributes BEFORE calling super().__init__()
        self.processing_mode = processing_mode
        self.threshold = kwargs.get("threshold", 0.75)

        # NOW call parent init
        super().__init__(name=name)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define input/output parameters."""
        return {
            "input_data": NodeParameter(
                name="input_data",
                type=list,
                required=True,
                description="Data to process"
            ),
            "config": NodeParameter(
                name="config",
                type=dict,
                required=False,
                default={},
                description="Processing configuration"
            )
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Main execution logic - must be named 'run' not 'execute'."""
        input_data = kwargs.get("input_data", [])
        config = kwargs.get("config", {})

        # Process data based on mode
        if self.processing_mode == "advanced":
            result = self._advanced_processing(input_data, config)
        else:
            result = self._standard_processing(input_data, config)

        return {"result": result, "processing_mode": self.processing_mode}

    def _standard_processing(self, data: list, config: dict) -> Any:
        """Standard processing implementation."""
        return [item for item in data if self._validate_item(item)]

    def _advanced_processing(self, data: list, config: dict) -> Any:
        """Advanced processing implementation."""
        processed = []
        for item in data:
            if self._validate_item(item):
                enhanced_item = self._enhance_item(item, config)
                processed.append(enhanced_item)
        return processed

    def _validate_item(self, item) -> bool:
        """Validate individual items."""
        return item is not None

    def _enhance_item(self, item, config: dict) -> Any:
        """Enhance item with additional data."""
        from datetime import datetime

        if isinstance(item, dict):
            item["processed_at"] = datetime.now().isoformat()
            item["enhancement_level"] = config.get("level", "basic")
        return item
```

### Common Mistakes to Avoid

```python
# ❌ WRONG - Setting attributes after super().__init__()
class BadNode(Node):
    def __init__(self, name, **kwargs):
        super().__init__(name=name)  # Parent validates here!
        self.my_param = kwargs.get("my_param")  # Too late!

# ✅ CORRECT - Set attributes first
class GoodNode(Node):
    def __init__(self, name, **kwargs):
        self.my_param = kwargs.get("my_param", "default")
        super().__init__(name=name)

# ❌ WRONG - Using wrong method name
def execute(self, **kwargs):  # Won't be called!
    pass

# ✅ CORRECT - Must use 'run' method
def run(self, **kwargs):
    pass

# ❌ WRONG - Not returning dict with 'result' key
def run(self, **kwargs):
    return "processed data"  # Wrong format!

# ✅ CORRECT - Return dict with result
def run(self, **kwargs):
    return {"result": "processed data"}
```

## NodeParameter Definition

### Parameter Types and Validation

```python
def get_parameters(self) -> Dict[str, NodeParameter]:
    """Define all node parameters with proper types."""
    return {
        # String parameter
        "text_input": NodeParameter(
            name="text_input",
            type=str,
            required=True,
            description="Text to process"
        ),

        # List parameter with default
        "items": NodeParameter(
            name="items",
            type=list,
            required=False,
            default=[],
            description="List of items to process"
        ),

        # Dict parameter for configuration
        "settings": NodeParameter(
            name="settings",
            type=dict,
            required=False,
            default={"mode": "standard"},
            description="Processing settings"
        ),

        # Numeric parameters
        "threshold": NodeParameter(
            name="threshold",
            type=float,
            required=False,
            default=0.75,
            description="Processing threshold"
        ),

        # Boolean flag
        "verbose": NodeParameter(
            name="verbose",
            type=bool,
            required=False,
            default=False,
            description="Enable verbose output"
        )
    }
```

### Parameter Access in run()

```python
def run(self, **kwargs) -> Dict[str, Any]:
    """Access parameters safely with defaults."""
    # Get required parameters
    text_input = kwargs["text_input"]  # Will raise KeyError if missing

    # Get optional parameters with defaults
    items = kwargs.get("items", [])
    settings = kwargs.get("settings", {})
    threshold = kwargs.get("threshold", self.threshold)  # Use instance default
    verbose = kwargs.get("verbose", False)

    # Process based on parameters
    if verbose:
        print(f"Processing {len(items)} items with threshold {threshold}")

    # Your processing logic here
    result = self._process(text_input, items, settings, threshold)

    return {
        "result": result,
        "items_processed": len(items),
        "threshold_used": threshold
    }
```

## Error Handling in Custom Nodes

### Comprehensive Error Management

```python
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class RobustProcessorNode(Node):
    """Node with comprehensive error handling."""

    def __init__(self, name, error_mode: str = "catch", **kwargs):
        self.error_mode = error_mode  # "catch", "raise", or "partial"
        self.max_errors = kwargs.get("max_errors", 10)
        super().__init__(name=name)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "data": NodeParameter(
                name="data",
                type=list,
                required=True,
                description="Data to process"
            )
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Process with error handling."""
        try:
            data = kwargs.get("data", [])

            # Input validation
            if not isinstance(data, list):
                raise TypeError(f"Expected list, got {type(data).__name__}")

            if not data:
                raise ValueError("No data provided")

            # Process with individual error handling
            results = []
            errors = []

            for i, item in enumerate(data):
                try:
                    result = self._process_item(item, i)
                    results.append(result)

                except Exception as e:
                    error_msg = f"Item {i}: {str(e)}"
                    errors.append(error_msg)
                    logger.warning(error_msg)

                    if len(errors) >= self.max_errors:
                        logger.error(f"Max errors ({self.max_errors}) reached")
                        if self.error_mode == "raise":
                            raise RuntimeError(f"Too many errors: {len(errors)}")
                        break

                    if self.error_mode == "raise":
                        raise

            # Return comprehensive result
            return {
                "result": results,
                "success_count": len(results),
                "error_count": len(errors),
                "errors": errors[:10],  # Limit error list size
                "status": self._determine_status(results, errors)
            }

        except Exception as e:
            logger.error(f"Processing failed: {e}", exc_info=True)

            if self.error_mode == "raise":
                raise

            return {
                "result": [],
                "error": str(e),
                "status": "error"
            }

    def _process_item(self, item: Any, index: int) -> Any:
        """Process individual item with validation."""
        if item is None:
            raise ValueError("Item is None")

        # Your processing logic here
        return {"original": item, "processed": True, "index": index}

    def _determine_status(self, results: list, errors: list) -> str:
        """Determine overall processing status."""
        if not errors:
            return "success"
        elif not results:
            return "error"
        else:
            return "partial"
```

## Async Custom Nodes

### Basic Async Node

```python
import asyncio
from typing import Dict, Any

class AsyncDataFetcherNode(Node):
    """Async node for concurrent data fetching."""

    def __init__(self, name, timeout: float = 30.0, **kwargs):
        self.timeout = timeout
        self.max_concurrent = kwargs.get("max_concurrent", 5)
        super().__init__(name=name)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "urls": NodeParameter(
                name="urls",
                type=list,
                required=True,
                description="URLs to fetch"
            )
        }

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Async execution method."""
        urls = kwargs.get("urls", [])

        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(self.max_concurrent)

        # Fetch all URLs concurrently
        tasks = [self._fetch_with_limit(url, semaphore) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        successful = []
        failed = []

        for url, result in zip(urls, results):
            if isinstance(result, Exception):
                failed.append({"url": url, "error": str(result)})
            else:
                successful.append({"url": url, "data": result})

        return {
            "result": successful,
            "failed": failed,
            "success_rate": len(successful) / len(urls) if urls else 0
        }

    async def _fetch_with_limit(self, url: str, semaphore: asyncio.Semaphore) -> Any:
        """Fetch URL with concurrency limit."""
        async with semaphore:
            return await self._fetch_url(url)

    async def _fetch_url(self, url: str) -> Any:
        """Simulate async URL fetching."""
        # In real implementation, use aiohttp or similar
        await asyncio.sleep(0.1)  # Simulate network delay
        return f"Data from {url}"

    def run(self, **kwargs) -> Dict[str, Any]:
        """Sync wrapper for async execution."""
        # Get or create event loop
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # Run async method
        return loop.run_until_complete(self.async_run(**kwargs))
```

## Advanced Custom Node Patterns

### Stateful Node with Context

```python
class StatefulProcessorNode(Node):
    """Node that maintains state across executions."""

    def __init__(self, name, **kwargs):
        self.state = {}
        self.max_history = kwargs.get("max_history", 100)
        self.processing_history = []
        super().__init__(name=name)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "data": NodeParameter(
                name="data",
                type=dict,
                required=True
            ),
            "operation": NodeParameter(
                name="operation",
                type=str,
                required=True,
                description="Operation: 'add', 'update', 'remove', 'get'"
            ),
            "key": NodeParameter(
                name="key",
                type=str,
                required=False
            )
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute stateful operation."""
        data = kwargs.get("data", {})
        operation = kwargs.get("operation", "get")
        key = kwargs.get("key")

        # Track operation
        self._add_to_history(operation, key)

        # Execute operation
        if operation == "add":
            result = self._add_to_state(key, data)
        elif operation == "update":
            result = self._update_state(key, data)
        elif operation == "remove":
            result = self._remove_from_state(key)
        elif operation == "get":
            result = self._get_from_state(key)
        else:
            raise ValueError(f"Unknown operation: {operation}")

        return {
            "result": result,
            "state_size": len(self.state),
            "operation": operation
        }

    def _add_to_state(self, key: str, data: dict) -> Any:
        """Add data to state."""
        if key in self.state:
            raise KeyError(f"Key '{key}' already exists")
        self.state[key] = data
        return data

    def _update_state(self, key: str, data: dict) -> Any:
        """Update existing state."""
        if key not in self.state:
            raise KeyError(f"Key '{key}' not found")
        self.state[key].update(data)
        return self.state[key]

    def _remove_from_state(self, key: str) -> Any:
        """Remove from state."""
        if key not in self.state:
            raise KeyError(f"Key '{key}' not found")
        return self.state.pop(key)

    def _get_from_state(self, key: Optional[str]) -> Any:
        """Get from state."""
        if key:
            return self.state.get(key)
        return dict(self.state)  # Return copy of full state

    def _add_to_history(self, operation: str, key: Optional[str]):
        """Track operation history."""
        from datetime import datetime

        self.processing_history.append({
            "timestamp": datetime.now().isoformat(),
            "operation": operation,
            "key": key
        })

        # Limit history size
        if len(self.processing_history) > self.max_history:
            self.processing_history.pop(0)
```

### Configurable Processing Pipeline Node

```python
class PipelineNode(Node):
    """Node with configurable processing pipeline."""

    def __init__(self, name, pipeline_config: list = None, **kwargs):
        self.pipeline_config = pipeline_config or ["validate", "transform", "enrich"]
        self.skip_on_error = kwargs.get("skip_on_error", False)
        super().__init__(name=name)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "data": NodeParameter(
                name="data",
                type=list,
                required=True
            ),
            "pipeline_overrides": NodeParameter(
                name="pipeline_overrides",
                type=list,
                required=False,
                description="Override pipeline steps for this execution"
            )
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute configurable pipeline."""
        data = kwargs.get("data", [])
        pipeline = kwargs.get("pipeline_overrides", self.pipeline_config)

        # Available pipeline steps
        steps = {
            "validate": self._validate_data,
            "transform": self._transform_data,
            "enrich": self._enrich_data,
            "filter": self._filter_data,
            "aggregate": self._aggregate_data
        }

        # Execute pipeline
        current_data = data
        pipeline_results = {}

        for step_name in pipeline:
            if step_name not in steps:
                raise ValueError(f"Unknown pipeline step: {step_name}")

            try:
                step_func = steps[step_name]
                current_data = step_func(current_data)
                pipeline_results[step_name] = "success"

            except Exception as e:
                pipeline_results[step_name] = f"error: {str(e)}"

                if not self.skip_on_error:
                    raise

                logger.warning(f"Pipeline step '{step_name}' failed: {e}")

        return {
            "result": current_data,
            "pipeline_executed": pipeline,
            "pipeline_results": pipeline_results
        }

    def _validate_data(self, data: list) -> list:
        """Validate data items."""
        validated = []
        for item in data:
            if self._is_valid(item):
                validated.append(item)
        return validated

    def _transform_data(self, data: list) -> list:
        """Transform data items."""
        return [self._transform_item(item) for item in data]

    def _enrich_data(self, data: list) -> list:
        """Enrich data with additional information."""
        from datetime import datetime

        enriched = []
        for item in data:
            if isinstance(item, dict):
                item["enriched_at"] = datetime.now().isoformat()
                item["source"] = "PipelineNode"
            enriched.append(item)
        return enriched

    def _filter_data(self, data: list) -> list:
        """Filter data based on criteria."""
        return [item for item in data if self._meets_criteria(item)]

    def _aggregate_data(self, data: list) -> list:
        """Aggregate data."""
        # Simple aggregation example
        if not data:
            return []

        return [{
            "count": len(data),
            "items": data[:10],  # First 10 items
            "summary": "Aggregated data"
        }]

    def _is_valid(self, item) -> bool:
        """Check if item is valid."""
        return item is not None

    def _transform_item(self, item):
        """Transform individual item."""
        if isinstance(item, dict):
            return {k: v for k, v in item.items() if v is not None}
        return item

    def _meets_criteria(self, item) -> bool:
        """Check if item meets filter criteria."""
        if isinstance(item, dict):
            return item.get("active", True)
        return True
```

## Using Custom Nodes in Workflows

### Registering and Using Custom Nodes

```python
from kailash.workflow.builder import WorkflowBuilder

# Create custom node instance
custom_processor = CustomProcessorNode(
    name="data_processor",
    processing_mode="advanced",
    threshold=0.9
)

# Method 1: Direct usage (if supported)
workflow = WorkflowBuilder()

# Add custom node to workflow
# Note: WorkflowBuilder typically uses string node names
# Check your SDK version for custom node support

# Method 2: Using PythonCodeNode wrapper
def custom_processing(data, config):
    """Wrapper function for custom logic."""
    processor = CustomProcessorNode(name="processor")
    result = processor.run(input_data=data, config=config)
    return result

from kailash.nodes.code import PythonCodeNode

workflow.add_node("PythonCodeNode", "custom_processor", {
    "code": """
# Use the custom processor
processor = CustomProcessorNode(name="processor", processing_mode="advanced")
result = processor.run(input_data=data, config=config)
"""
})
```

## Testing Custom Nodes

### Unit Testing Pattern

```python
import pytest
from unittest.mock import Mock, patch

class TestCustomProcessorNode:
    """Test suite for CustomProcessorNode."""

    def test_initialization(self):
        """Test node initialization."""
        node = CustomProcessorNode(
            name="test_node",
            processing_mode="advanced",
            threshold=0.8
        )

        assert node.name == "test_node"
        assert node.processing_mode == "advanced"
        assert node.threshold == 0.8

    def test_standard_processing(self):
        """Test standard processing mode."""
        node = CustomProcessorNode(name="test", processing_mode="standard")

        result = node.run(
            input_data=[1, 2, None, 3],
            config={}
        )

        assert "result" in result
        assert len(result["result"]) == 3  # None filtered out

    def test_error_handling(self):
        """Test error handling."""
        node = RobustProcessorNode(name="test", error_mode="catch")

        result = node.run(data=[1, None, 3])

        assert result["status"] == "partial"
        assert result["success_count"] == 2
        assert result["error_count"] == 1

    @pytest.mark.asyncio
    async def test_async_node(self):
        """Test async node execution."""
        node = AsyncDataFetcherNode(name="test", max_concurrent=2)

        result = await node.async_run(
            urls=["http://example1.com", "http://example2.com"]
        )

        assert "result" in result
        assert len(result["result"]) == 2
        assert result["success_rate"] == 1.0
```

## Best Practices

1. **Always set attributes before super().__init__()**
2. **Use descriptive parameter names and documentation**
3. **Handle errors gracefully with informative messages**
4. **Return consistent result structure**
5. **Add logging for debugging**
6. **Write comprehensive tests**
7. **Document expected inputs and outputs**
8. **Consider async implementation for I/O operations**
9. **Validate inputs early in the run() method**
10. **Keep nodes focused on a single responsibility**

## Related Guides

**Prerequisites:**
- [Fundamentals](01-fundamentals.md) - Core concepts
- [Workflows](02-workflows.md) - Using nodes in workflows

**Next Steps:**
- [Advanced Features](03-advanced-features.md) - Enterprise patterns
- [Production](04-production.md) - Deploying custom nodes
- [RAG Guide](07-comprehensive-rag-guide.md) - Specialized nodes

---

**Build powerful custom nodes to extend Kailash SDK capabilities for your specific needs!**
