# Custom Development - Build Nodes & Extensions

*Create custom nodes and extend Kailash SDK functionality*

## 🎯 **Prerequisites**
- Completed [Fundamentals](01-fundamentals.md) - Core SDK concepts
- Completed [Workflows](02-workflows.md) - Basic workflow patterns
- Understanding of Python classes and inheritance
- Familiarity with type hints

## 🏗️ **Basic Custom Node Structure**

### **Essential Rules for Custom Nodes**

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
        super().__init__(name, **kwargs)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define input/output parameters."""
        return {
            "input_data": NodeParameter(
                name="input_data",
                type=list,  # Use basic types, not List[str]
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

    def _validate_item(self, 'item_value') -> bool:
        """Validate individual items."""
        return item is not None

    def _enhance_item(self, 'item_value', config: dict) -> Any:
        """Enhance item with additional data."""
        if isinstance(item, dict):
            item["processed_at"] = datetime.now().isoformat()
            item["enhancement_level"] = config.get("level", "basic")
        return item

```

### **Common Mistakes to Avoid**

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# ❌ WRONG - Attributes set after super().__init__()
class BadNode(Node):
    def __init__(self, name, **kwargs):
        super().__init__(name=name)  # Too early!
        self.my_param = kwargs.get("my_param")  # AttributeError!

# ❌ WRONG - Using generic types
def get_parameters(self):
    return {
        "items": NodeParameter(type=List[str], ...)  # TypeError!
    }

# ❌ WRONG - Wrong method name
def execute(self, **kwargs):  # Should be 'run'
    pass

# ❌ WRONG - Returning raw values
def get_parameters(self):
    return {
        "max_tokens": self.max_tokens,  # Should be NodeParameter object
    }

```

## 📋 **Parameter Definition Patterns**

### **Comprehensive Parameter Schema**

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

def get_parameters(self) -> Dict[str, NodeParameter]:
    """Define comprehensive parameter schema."""
    return {
        # Required parameters
        "data": NodeParameter(
            name="data",
            type=list,
            required=True,
            description="Input data to process"
        ),

        # Optional parameters with defaults
        "batch_size": NodeParameter(
            name="batch_size",
            type=int,
            required=False,
            default=100,
            description="Processing batch size"
        ),

        # Configuration objects
        "options": NodeParameter(
            name="options",
            type=dict,
            required=False,
            default={"mode": "safe", "timeout": 30},
            description="Processing options"
        ),

        # Multiple allowed types
        "threshold": NodeParameter(
            name="threshold",
            type=(int, float),
            required=False,
            default=0.5,
            description="Processing threshold"
        ),

        # Any type with runtime validation
        "flexible_input": NodeParameter(
            name="flexible_input",
            type=Any,
            required=False,
            description="Accepts any type, validated at runtime"
        ),

        # Auto-mapping parameters (Session 067+)
        "auto_mapped": NodeParameter(
            name="auto_mapped",
            type=str,
            required=False,
            auto_map_primary=True,
            auto_map_from=["alt_name1", "alt_name2"],
            workflow_alias="global_param"
        )
    }

```

### **Runtime Type Validation**

```python
def run(self, **kwargs):
    """Runtime validation for flexible types."""
    flexible_input = kwargs.get("flexible_input")

    # Validate Any type at runtime
    if flexible_input is not None:
        if isinstance(flexible_input, str):
            processed = self._process_string(flexible_input)
        elif isinstance(flexible_input, (list, tuple)):
            processed = self._process_sequence(flexible_input)
        elif isinstance(flexible_input, dict):
            processed = self._process_mapping(flexible_input)
        else:
            raise ValueError(f"Unsupported type: {type(flexible_input)}")

    return {"result": processed}

```

## 🔒 **Validation & Error Handling**

### **Comprehensive Validation Pattern**

```python
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError

class ValidatedProcessorNode(Node):
    """Node with comprehensive validation and error handling."""

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute with validation and error handling."""
        try:
            # Pre-execution validation
            self._validate_inputs(kwargs)

            # Main processing
            result = self._safe_process(kwargs)

            # Post-execution validation
            self._validate_outputs(result)

            return result

        except NodeValidationError:
            # Re-raise validation errors
            raise
        except Exception as e:
            # Wrap other errors
            raise NodeExecutionError(
                f"Processing failed in {self.metadata.name}: {str(e)}"
            ) from e

    def _validate_inputs(self, inputs: Dict[str, Any]):
        """Validate input parameters."""
        data = inputs.get("data")

        if not data:
            raise NodeValidationError("Input data cannot be empty")

        if not isinstance(data, (list, tuple)):
            raise NodeValidationError("Input data must be a list or tuple")

        # Validate data structure
        for i, item in enumerate(data):
            if not isinstance(item, dict):
                raise NodeValidationError(
                    f"Item {i} must be a dictionary, got {type(item)}"
                )

            if "id" not in item:
                raise NodeValidationError(f"Item {i} missing required 'id' field")

    def _validate_outputs(self, outputs: Dict[str, Any]):
        """Validate output data."""
        if "result" not in outputs:
            raise NodeValidationError("Output must contain 'result' field")

        result = outputs["result"]
        if not isinstance(result, list):
            raise NodeValidationError("Result must be a list")

    def _safe_process(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Process data with error recovery."""
        data = inputs["data"]
        processed = []
        errors = []

        for i, item in enumerate(data):
            try:
                processed_item = self._process_single_item(item)
                processed.append(processed_item)
            except Exception as e:
                error_info = {
                    "index": i,
                    "item_id": item.get("id", "unknown"),
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                }
                errors.append(error_info)

                # Continue processing other items
                self.logger.warning(f"Failed to process item {i}: {e}")

        return {
            "result": processed,
            "success_count": len(processed),
            "error_count": len(errors),
            "errors": errors
        }

    def _process_single_item(self, item: dict) -> dict:
        """Process a single item with validation."""
        # Simulate processing that might fail
        if item.get("status") == "invalid":
            raise ValueError("Item marked as invalid")

        return {
            **item,
            "processed": True,
            "processed_at": datetime.now().isoformat()
        }

```

## ⚡ **Async Node Development**

### **Async-Compatible Node**

```python
import asyncio
from typing import Dict, Any, Optional

class AsyncProcessorNode(Node):
    """Node that supports async operations."""

    def __init__(self, 'name', concurrency: int = 5, **kwargs):
        self.concurrency = concurrency
        super().__init__(name, **kwargs)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "data": NodeParameter(
                name="data",
                type=list,
                required=True,
                description="Data to process asynchronously"
            ),
            "timeout": NodeParameter(
                name="timeout",
                type=float,
                required=False,
                default=30.0,
                description="Timeout per item in seconds"
            )
        }

    async def execute_async(self, **kwargs) -> Dict[str, Any]:
        """Async execution method for runtime integration."""
        data = kwargs.get("data", [])
        timeout = kwargs.get("timeout", 30.0)

        # Process items concurrently
        semaphore = asyncio.Semaphore(self.concurrency)
        tasks = [
            self._process_item_async(item, semaphore, timeout)
            for item in data
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Separate successful results from exceptions
        successful = []
        failed = []

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                failed.append({
                    "index": i,
                    "error": str(result),
                    "item": data[i] if i < len(data) else None
                })
            else:
                successful.append(result)

        return {
            "result": successful,
            "success_count": len(successful),
            "failure_count": len(failed),
            "failures": failed
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Sync wrapper for async execution - required for base compatibility."""
        return asyncio.run(self.execute_async(**kwargs))

    async def _process_item_async(self, 'item_value', semaphore: asyncio.Semaphore, timeout: float) -> Any:
        """Process single item asynchronously."""
        async with semaphore:
            try:
                # Use timeout for each item
                async with asyncio.timeout(timeout):
                    # Simulate async processing
                    await asyncio.sleep(0.1)

                    if isinstance(item, dict):
                        item["async_processed"] = True
                        item["processing_time"] = 0.1

                    return item
            except asyncio.TimeoutError:
                raise TimeoutError(f"Processing timeout for item: {item}")

```

### **Database Async Node**

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

class AsyncDatabaseNode(Node):
    """Async database operations node."""

    def __init__(self, "workflow_name", 'connection_string', pool_size: int = 10, **kwargs):
        self.connection_string = connection_string
        self.pool_size = pool_size
        self._pool = None
        super().__init__(name, **kwargs)

    async def execute_async(self, **kwargs) -> Dict[str, Any]:
        """Execute database operation asynchronously."""
        query = kwargs["query"]
# Parameters setup
workflow. kwargs.get("parameters", {})
        operation = kwargs.get("operation", "select")

        try:
            # Get connection from pool
            if not self._pool:
                self._pool = await self._create_pool()

            async with self._pool.acquire() as connection:
                if operation == "select":
                    result = await self._execute_select(connection, query, parameters)
                else:
                    result = await self._execute_modification(connection, query, parameters)

            return {
                "result": result,
                "operation": operation,
                "row_count": len(result) if isinstance(result, list) else result
            }

        except Exception as e:
            raise NodeExecutionError(f"Database operation failed: {e}") from e

    async def _create_pool(self):
        """Create connection pool."""
        import asyncpg
        return await asyncpg.create_pool(
            self.connection_string,
            min_size=1,
            max_size=self.pool_size
        )

    async def _execute_select(self, connection, 'query', parameters: dict) -> list:
        """Execute SELECT query."""
        rows = await connection.fetch(query, *parameters.values())
        return [dict(row) for row in rows]

    async def _execute_modification(self, connection, 'query', parameters: dict) -> int:
        """Execute INSERT/UPDATE/DELETE query."""
        result = await connection.execute(query, *parameters.values())
        return int(result.split()[-1])  # Extract row count

    def run(self, **kwargs) -> Dict[str, Any]:
        """Sync wrapper for compatibility."""
        return asyncio.run(self.execute_async(**kwargs))

    async def cleanup(self):
        """Clean up resources."""
        if self._pool:
            await self._pool.close()

```

## 🔧 **Configuration Management**

### **Advanced Configuration Patterns**

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

class ConfigurableNode(Node):
    """Node with advanced configuration management."""

    def __init__(self, "workflow_name", config_source: str = "default", **kwargs):
        self.config_source = config_source
        self._config_cache = {}
        super().__init__(name, **kwargs)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "data": NodeParameter(
                name="data", type=list, required=True
            ),
            "runtime_config": NodeParameter(
                name="runtime_config", type=dict, required=False, default={}
            )
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute with dynamic configuration."""
        # Load configuration from multiple sources
        config = self._load_config(kwargs.get("runtime_config", {}))

        # Apply configuration
        processor = self._create_processor(config)

        # Process data
        data = kwargs["data"]
        result = processor.process(data)

        return {
            "result": result,
            "config_used": config,
            "config_source": self.config_source
        }

    def _load_config(self, runtime_config: dict) -> dict:
        """Load and merge configuration from multiple sources."""
        # Base configuration
        base_config = {
            "processing_mode": "standard",
            "batch_size": 100,
            "timeout": 30,
            "retry_count": 3
        }

        # Environment-specific config
        env_config = self._load_env_config()

        # File-based config (if specified)
        file_config = self._load_file_config()

        # Merge configurations (runtime overrides everything)
        merged_config = {
            **base_config,
            **env_config,
            **file_config,
            **runtime_config
        }

        return merged_config

    def _load_env_config(self) -> dict:
        """Load configuration from environment variables."""
        import os

        env_config = {}

        if batch_size := os.getenv("NODE_BATCH_SIZE"):
            env_config["batch_size"] = int(batch_size)

        if timeout := os.getenv("NODE_TIMEOUT"):
            env_config["timeout"] = int(timeout)

        if mode := os.getenv("NODE_PROCESSING_MODE"):
            env_config["processing_mode"] = mode

        return env_config

    def _load_file_config(self) -> dict:
        """Load configuration from file."""
        if self.config_source == "default":
            return {}

        # Check cache first
        if self.config_source in self._config_cache:
            return self._config_cache[self.config_source]

        try:
            import json
            with open(self.config_source, 'r') as f:
                file_config = json.load(f)

            # Cache the configuration
            self._config_cache[self.config_source] = file_config
            return file_config

        except (FileNotFoundError, json.JSONDecodeError) as e:
            self.logger.warning(f"Could not load config from {self.config_source}: {e}")
            return {}

    def _create_processor(self, config: dict):
        """Create processor based on configuration."""
        mode = config.get("processing_mode", "standard")

        if mode == "advanced":
            return AdvancedProcessor(config)
        elif mode == "batch":
            return BatchProcessor(config)
        else:
            return StandardProcessor(config)

```

## 🤖 **ML Model Integration Node**

### **Custom ML Model Node**

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

class MLModelNode(Node):
    """Custom node for machine learning model inference."""

    def __init__(self, "workflow_name", 'model_path', model_type: str = "sklearn", **kwargs):
        self.model_path = model_path
        self.model_type = model_type
        self._model = None
        super().__init__(name, **kwargs)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "features": NodeParameter(
                name="features",
                type=(list, dict),
                required=True,
                description="Features for model prediction"
            ),
            "return_probabilities": NodeParameter(
                name="return_probabilities",
                type=bool,
                required=False,
                default=False,
                description="Return class probabilities instead of predictions"
            ),
            "batch_size": NodeParameter(
                name="batch_size",
                type=int,
                required=False,
                default=32,
                description="Batch size for inference"
            )
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute model inference."""
        features = kwargs["features"]
        return_probs = kwargs.get("return_probabilities", False)
        batch_size = kwargs.get("batch_size", 32)

        # Load model if not already loaded
        if self._model is None:
            self._model = self._load_model()

        # Prepare features
        X = self._prepare_features(features)

        # Make predictions in batches
        predictions = []
        for i in range(0, len(X), batch_size):
            batch = X[i:i + batch_size]

            if return_probs and hasattr(self._model, 'predict_proba'):
                batch_pred = self._model.predict_proba(batch)
                result_key = "probabilities"
            else:
                batch_pred = self._model.predict(batch)
                result_key = "predictions"

            predictions.extend(batch_pred.tolist())

        return {
            result_key: predictions,
            "feature_count": X.shape[1] if hasattr(X, 'shape') else len(X[0]),
            "prediction_count": len(predictions),
            "model_type": self.model_type,
            "model_path": self.model_path
        }

    def _load_model(self):
        """Load the ML model."""
        if self.model_type == "sklearn":
            import joblib
            return joblib.load(self.model_path)
        elif self.model_type == "tensorflow":
            import tensorflow as tf
            return tf.keras.models.load_model(self.model_path)
        elif self.model_type == "pytorch":
            import torch
            model = torch.load(self.model_path)
            model.eval()  # Set to evaluation mode
            return model
        else:
            raise ValueError(f"Unsupported model type: {self.model_type}")

    def _prepare_features(self, features):
        """Prepare features for model input."""
        import numpy as np

        if isinstance(features, dict):
            # Convert single dict to list
            features = [features]

        if isinstance(features, list) and features:
            if isinstance(features[0], dict):
                # Convert list of dicts to array
                feature_names = sorted(features[0].keys())
                X = np.array([[item.get(key, 0) for key in feature_names] for item in features])
            else:
                # Assume list of lists/arrays
                X = np.array(features)
        else:
            X = np.array(features)

        return X

```

## 🧪 **Testing Custom Nodes**

### **Comprehensive Test Suite**

```python
import pytest
from unittest.mock import Mock, patch
import asyncio

class TestCustomProcessorNode:
    """Test suite for CustomProcessorNode."""

    @pytest.fixture
    def node(self):
        """Create a test node instance."""
        return CustomProcessorNode(name="test_processor")

    @pytest.fixture
    def sample_data(self):
        """Sample test data."""
        return [
            {"id": 1, "name": "Item 1", "value": 100},
            {"id": 2, "name": "Item 2", "value": 200},
            {"id": 3, "name": "Item 3", "value": 300}
        ]

    def test_node_initialization(self, node):
        """Test node initialization."""
        assert node.metadata.name == "test_processor"
        assert node.processing_mode == "standard"
        assert hasattr(node, 'get_parameters')
        assert hasattr(node, 'run')

    def test_get_parameters(self, node):
        """Test parameter definition."""
        params = node.get_parameters()

        assert "input_data" in params
        assert params["input_data"].required is True
        assert params["input_data"].type == list

        assert "config" in params
        assert params["config"].required is False
        assert params["config"].default == {}

    def test_standard_processing(self, node, sample_data):
        """Test standard processing mode."""
        result = node.run(input_data=sample_data, config={})

        assert "result" in result
        assert "processing_mode" in result
        assert result["processing_mode"] == "standard"
        assert len(result["result"]) == len(sample_data)

    def test_advanced_processing(self, sample_data):
        """Test advanced processing mode."""
        node = CustomProcessorNode(name="test", processing_mode="advanced")
        result = node.run(input_data=sample_data, config={"level": "high"})

        assert result["processing_mode"] == "advanced"
        assert len(result["result"]) == len(sample_data)

        # Check that items were enhanced
        for item in result["result"]:
            if isinstance(item, dict):
                assert "processed_at" in item
                assert "enhancement_level" in item
                assert item["enhancement_level"] == "high"

    def test_validation_error_handling(self, node):
        """Test validation and error handling."""
        # Test with invalid data
        with pytest.raises((NodeValidationError, ValueError)):
            node.run(input_data=None)

    def test_empty_data_handling(self, node):
        """Test handling of empty data."""
        result = node.run(input_data=[], config={})

        assert "result" in result
        assert result["result"] == []

    @pytest.mark.asyncio
    async def test_async_node(self, sample_data):
        """Test async node execution."""
        async_node = AsyncProcessorNode(name="test_async", concurrency=2)
        result = await async_node.execute_async(data=sample_data)

        assert "result" in result
        assert "success_count" in result
        assert result["success_count"] == len(sample_data)

    def test_configuration_loading(self):
        """Test configuration loading."""
        with patch.dict('os.environ', {'NODE_BATCH_SIZE': '50'}):
            node = ConfigurableNode(name="test_config")
            result = node.run(data=[1, 2, 3])

            assert "config_used" in result
            assert result["config_used"]["batch_size"] == 50

    def test_error_recovery(self, sample_data):
        """Test error recovery in processing."""
        # Add an invalid item that should cause an error
        invalid_data = sample_data + [{"id": 4, "status": "invalid"}]

        node = ValidatedProcessorNode(name="test_validation")
        result = node.run(data=invalid_data)

        assert "result" in result
        assert "errors" in result
        assert result["error_count"] == 1
        assert result["success_count"] == 3

    def test_ml_model_node(self, sample_data):
        """Test ML model node with mock model."""
        with patch('joblib.load') as mock_load:
            # Mock sklearn model
            mock_model = Mock()
            mock_model.predict.return_value = np.array([1, 0, 1])
            mock_load.return_value = mock_model

            node = MLModelNode(name="test_ml", model_path="model.pkl")
            features = [{"feature1": 1, "feature2": 2} for _ in range(3)]

            result = node.run(features=features)

            assert "predictions" in result
            assert len(result["predictions"]) == 3
            assert result["model_type"] == "sklearn"

```

## 🚀 **Registering & Using Custom Nodes**

### **Node Registration**

```python
from kailash.nodes import register_node

# Register your custom node
register_node("CustomProcessorNode", CustomProcessorNode)

# Now use it in workflows
workflow = WorkflowBuilder()
workflow.add_node("CustomProcessorNode", "processor", {}),
    processing_mode="advanced",
    threshold=0.8
)

# Or use the registered name
workflow.add_node("processor", "CustomProcessorNode",
    processing_mode="advanced",
    threshold=0.8
)

```

### **Integration Example**

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Create workflow with custom nodes
workflow = WorkflowBuilder()

# Add custom ML node
workflow.add_node("MLModelNode", "model", {}))

# Add custom async processor
workflow.add_node("AsyncProcessorNode", "processor", {}))

# Connect nodes
workflow.add_connection("processor", "model", "result", "features")

# Execute
runtime = LocalRuntime(enable_async=True)
results, run_id = runtime.execute(workflow, parameters={
    "processor": {"data": input_data}
})

```

## 📚 **Best Practices**

### **Node Development Guidelines**

1. **Always set attributes before super().__init__()**
2. **Use basic types in NodeParameter (list, dict, not List[T])**
3. **Implement both get_parameters() and run() methods**
4. **Handle optional parameters with proper defaults**
5. **Add comprehensive validation and error handling**
6. **Support both sync and async operations when appropriate**
7. **Cache expensive operations (model loading, connections)**
8. **Clean up resources properly (connection pools, file handles)**
9. **Write comprehensive tests for all node functionality**
10. **Document parameters and behavior thoroughly**

### **Performance Considerations**

1. **Lazy Loading**: Load models/resources only when first needed
2. **Connection Pooling**: Reuse database/API connections
3. **Batch Processing**: Process data in chunks for large datasets
4. **Async Operations**: Use async for I/O-bound operations
5. **Resource Limits**: Implement timeouts and memory limits
6. **Caching**: Cache configuration and computed values appropriately

## 🔗 **Next Steps**

- Review [Examples](../../examples/) for more custom node implementations
- Check [Tests](../../tests/) for testing patterns
- Explore [Enterprise Nodes](../nodes/comprehensive-node-catalog.md#enterprise-nodes) for advanced patterns

---

**Custom node development enables you to extend Kailash SDK with domain-specific functionality while maintaining consistency and reliability!**
