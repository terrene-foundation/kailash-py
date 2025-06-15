# Custom Node Development Guide

This guide demonstrates how to create custom nodes by:
1. Extending the base Node class
2. Implementing required methods
3. Adding custom configuration
4. Handling different data types
5. Implementing validation logic
6. Adding custom error handling
7. Creating reusable node templates

Shows best practices for extending the Kailash SDK.

## Table of Contents

1. [Basic Custom Node Structure](#basic-custom-node-structure)
2. [Node Parameter Definition](#node-parameter-definition)
3. [Data Type Handling](#data-type-handling)
4. [Validation and Error Handling](#validation-and-error-handling)
5. [Async Operations](#async-operations)
6. [Configuration Management](#configuration-management)
7. [Testing Custom Nodes](#testing-custom-nodes)
8. [Real-world Examples](#real-world-examples)

## Basic Custom Node Structure

All custom nodes must inherit from the base `Node` class and implement required methods:

```python
from typing import Dict, Any
from kailash.nodes.base import Node, NodeParameter

class CustomProcessorNode(Node):
    """Custom data processing node."""
    
    def __init__(self, name: str, processing_mode: str = "standard", **kwargs):
        # Set attributes BEFORE calling super().__init__()
        self.processing_mode = processing_mode
        super().__init__(name, **kwargs)
    
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
    
    def execute(self, **kwargs) -> Dict[str, Any]:
        """Main execution logic."""
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
        # More complex logic here
        processed = []
        for item in data:
            if self._validate_item(item):
                enhanced_item = self._enhance_item(item, config)
                processed.append(enhanced_item)
        return processed
    
    def _validate_item(self, item: Any) -> bool:
        """Validate individual items."""
        return item is not None
    
    def _enhance_item(self, item: Any, config: dict) -> Any:
        """Enhance item with additional data."""
        if isinstance(item, dict):
            item["processed_at"] = datetime.now().isoformat()
            item["enhancement_level"] = config.get("level", "basic")
        return item
```

## Node Parameter Definition

Parameters define the interface contract for your node:

```python
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
        
        # Complex validation
        "format": NodeParameter(
            name="format",
            type=str,
            required=False,
            default="json",
            validation=lambda x: x in ["json", "csv", "xml"],
            description="Output format"
        )
    }
```

## Data Type Handling

Handle different data types robustly:

```python
class DataTypeHandlerNode(Node):
    """Node that handles various data types safely."""
    
    def execute(self, **kwargs) -> Dict[str, Any]:
        data = kwargs.get("data")
        
        # Type detection and conversion
        if isinstance(data, str):
            result = self._handle_string(data)
        elif isinstance(data, (list, tuple)):
            result = self._handle_sequence(data)
        elif isinstance(data, dict):
            result = self._handle_mapping(data)
        elif hasattr(data, '__iter__'):
            result = self._handle_iterable(data)
        else:
            result = self._handle_scalar(data)
        
        return {"result": result, "input_type": type(data).__name__}
    
    def _handle_string(self, data: str) -> Any:
        """Handle string input."""
        try:
            # Try to parse as JSON
            import json
            return json.loads(data)
        except (json.JSONDecodeError, ValueError):
            # Return as processed string
            return data.strip().upper()
    
    def _handle_sequence(self, data) -> list:
        """Handle list/tuple input."""
        return [self._process_item(item) for item in data]
    
    def _handle_mapping(self, data: dict) -> dict:
        """Handle dictionary input."""
        return {k: self._process_item(v) for k, v in data.items()}
    
    def _handle_iterable(self, data) -> list:
        """Handle generic iterable."""
        return list(data)
    
    def _handle_scalar(self, data) -> Any:
        """Handle scalar values."""
        if isinstance(data, (int, float)):
            return data * 2
        return str(data)
    
    def _process_item(self, item: Any) -> Any:
        """Process individual items based on type."""
        if isinstance(item, str):
            return item.strip()
        elif isinstance(item, (int, float)):
            return item
        elif isinstance(item, dict):
            return {k: str(v) for k, v in item.items()}
        else:
            return str(item)
```

## Validation and Error Handling

Implement robust validation and error handling:

```python
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError

class ValidatedProcessorNode(Node):
    """Node with comprehensive validation and error handling."""
    
    def execute(self, **kwargs) -> Dict[str, Any]:
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

## Async Operations

Create nodes that support asynchronous operations:

```python
import asyncio
from typing import Dict, Any, Optional

class AsyncProcessorNode(Node):
    """Node that supports async operations."""
    
    def __init__(self, name: str, concurrency: int = 5, **kwargs):
        self.concurrency = concurrency
        super().__init__(name, **kwargs)
    
    async def async_execute(self, **kwargs) -> Dict[str, Any]:
        """Async execution method."""
        data = kwargs.get("data", [])
        
        # Process items concurrently
        semaphore = asyncio.Semaphore(self.concurrency)
        tasks = [
            self._process_item_async(item, semaphore) 
            for item in data
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Separate successful results from exceptions
        successful = []
        failed = []
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                failed.append({"index": i, "error": str(result)})
            else:
                successful.append(result)
        
        return {
            "result": successful,
            "success_count": len(successful),
            "failure_count": len(failed),
            "failures": failed
        }
    
    def execute(self, **kwargs) -> Dict[str, Any]:
        """Sync wrapper for async execution."""
        return asyncio.run(self.async_execute(**kwargs))
    
    async def _process_item_async(self, item: Any, semaphore: asyncio.Semaphore) -> Any:
        """Process single item asynchronously."""
        async with semaphore:
            # Simulate async processing
            await asyncio.sleep(0.1)
            
            if isinstance(item, dict):
                item["async_processed"] = True
                item["processing_time"] = 0.1
            
            return item
```

## Configuration Management

Handle complex configuration scenarios:

```python
class ConfigurableNode(Node):
    """Node with advanced configuration management."""
    
    def __init__(self, name: str, config_source: str = "default", **kwargs):
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
    
    def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute with dynamic configuration."""
        # Load configuration
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

class StandardProcessor:
    """Standard data processor."""
    
    def __init__(self, config: dict):
        self.config = config
    
    def process(self, data: list) -> list:
        """Process data with standard algorithm."""
        return [self._process_item(item) for item in data]
    
    def _process_item(self, item: Any) -> Any:
        """Process individual item."""
        return item

class AdvancedProcessor(StandardProcessor):
    """Advanced data processor with additional features."""
    
    def process(self, data: list) -> list:
        """Process data with advanced algorithm."""
        batch_size = self.config.get("batch_size", 100)
        processed = []
        
        # Process in batches
        for i in range(0, len(data), batch_size):
            batch = data[i:i + batch_size]
            batch_result = self._process_batch(batch)
            processed.extend(batch_result)
        
        return processed
    
    def _process_batch(self, batch: list) -> list:
        """Process a batch of items."""
        return [self._process_item_advanced(item) for item in batch]
    
    def _process_item_advanced(self, item: Any) -> Any:
        """Advanced item processing."""
        if isinstance(item, dict):
            item["advanced_processing"] = True
            item["batch_processed"] = True
        return item

class BatchProcessor(StandardProcessor):
    """Batch-optimized processor."""
    
    def process(self, data: list) -> list:
        """Process data optimized for large batches."""
        # Simulate batch optimization
        return [{"batch_id": i // 10, "item": item} for i, item in enumerate(data)]
```

## Testing Custom Nodes

Create comprehensive tests for your custom nodes:

```python
import pytest
from unittest.mock import Mock, patch

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
        assert hasattr(node, 'execute')
    
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
        result = node.execute(input_data=sample_data, config={})
        
        assert "result" in result
        assert "processing_mode" in result
        assert result["processing_mode"] == "standard"
        assert len(result["result"]) == len(sample_data)
    
    def test_advanced_processing(self, sample_data):
        """Test advanced processing mode."""
        node = CustomProcessorNode(name="test", processing_mode="advanced")
        result = node.execute(input_data=sample_data, config={"level": "high"})
        
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
            node.execute(input_data=None)
    
    def test_empty_data_handling(self, node):
        """Test handling of empty data."""
        result = node.execute(input_data=[], config={})
        
        assert "result" in result
        assert result["result"] == []
    
    def test_config_parameter_handling(self, node, sample_data):
        """Test configuration parameter handling."""
        config = {"custom_setting": "value", "level": "test"}
        result = node.execute(input_data=sample_data, config=config)
        
        assert "result" in result
        # Verify config was used (implementation-dependent)
    
    @pytest.mark.asyncio
    async def test_async_node(self, sample_data):
        """Test async node execution."""
        async_node = AsyncProcessorNode(name="test_async", concurrency=2)
        result = await async_node.async_execute(data=sample_data)
        
        assert "result" in result
        assert "success_count" in result
        assert result["success_count"] > 0
    
    def test_configuration_loading(self):
        """Test configuration loading."""
        with patch.dict('os.environ', {'NODE_BATCH_SIZE': '50'}):
            node = ConfigurableNode(name="test_config")
            result = node.execute(data=[1, 2, 3])
            
            assert "config_used" in result
            assert result["config_used"]["batch_size"] == 50
    
    def test_error_recovery(self, sample_data):
        """Test error recovery in processing."""
        # Add an invalid item that should cause an error
        invalid_data = sample_data + [{"id": 4, "status": "invalid"}]
        
        node = ValidatedProcessorNode(name="test_validation")
        result = node.execute(data=invalid_data)
        
        assert "result" in result
        assert "errors" in result
        assert result["error_count"] > 0
        assert result["success_count"] > 0
```

## Real-world Examples

### Custom Database Connector Node

```python
class DatabaseConnectorNode(Node):
    """Custom node for database operations."""
    
    def __init__(self, name: str, connection_string: str, **kwargs):
        self.connection_string = connection_string
        self._connection_pool = None
        super().__init__(name, **kwargs)
    
    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "query": NodeParameter(
                name="query", type=str, required=True
            ),
            "parameters": NodeParameter(
                name="parameters", type=dict, required=False, default={}
            ),
            "operation": NodeParameter(
                name="operation", 
                type=str, 
                required=False, 
                default="select",
                validation=lambda x: x in ["select", "insert", "update", "delete"]
            )
        }
    
    async def async_execute(self, **kwargs) -> Dict[str, Any]:
        """Execute database operation asynchronously."""
        query = kwargs["query"]
        parameters = kwargs.get("parameters", {})
        operation = kwargs.get("operation", "select")
        
        try:
            connection = await self._get_connection()
            
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
    
    async def _get_connection(self):
        """Get database connection from pool."""
        if not self._connection_pool:
            self._connection_pool = await self._create_connection_pool()
        return await self._connection_pool.acquire()
    
    async def _create_connection_pool(self):
        """Create connection pool."""
        # Implementation depends on database type
        pass
    
    async def _execute_select(self, connection, query: str, parameters: dict) -> list:
        """Execute SELECT query."""
        cursor = await connection.execute(query, parameters)
        return await cursor.fetchall()
    
    async def _execute_modification(self, connection, query: str, parameters: dict) -> int:
        """Execute INSERT/UPDATE/DELETE query."""
        cursor = await connection.execute(query, parameters)
        return cursor.rowcount
```

### Custom ML Model Node

```python
class MLModelNode(Node):
    """Custom node for machine learning model inference."""
    
    def __init__(self, name: str, model_path: str, model_type: str = "sklearn", **kwargs):
        self.model_path = model_path
        self.model_type = model_type
        self._model = None
        super().__init__(name, **kwargs)
    
    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "features": NodeParameter(
                name="features", type=(list, dict), required=True
            ),
            "return_probabilities": NodeParameter(
                name="return_probabilities", type=bool, required=False, default=False
            ),
            "batch_size": NodeParameter(
                name="batch_size", type=int, required=False, default=32
            )
        }
    
    def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute model inference."""
        features = kwargs["features"]
        return_probs = kwargs.get("return_probabilities", False)
        batch_size = kwargs.get("batch_size", 32)
        
        # Load model if not already loaded
        if self._model is None:
            self._model = self._load_model()
        
        # Prepare features
        X = self._prepare_features(features)
        
        # Make predictions
        if return_probs and hasattr(self._model, 'predict_proba'):
            predictions = self._model.predict_proba(X)
            result_key = "probabilities"
        else:
            predictions = self._model.predict(X)
            result_key = "predictions"
        
        return {
            result_key: predictions.tolist(),
            "feature_count": X.shape[1] if hasattr(X, 'shape') else len(X[0]),
            "prediction_count": len(predictions),
            "model_type": self.model_type
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
            return torch.load(self.model_path)
        else:
            raise ValueError(f"Unsupported model type: {self.model_type}")
    
    def _prepare_features(self, features):
        """Prepare features for model input."""
        import numpy as np
        
        if isinstance(features, dict):
            # Convert dict to array based on expected feature order
            features = [features]
        
        if isinstance(features, list):
            # Assume list of dictionaries or list of lists
            if features and isinstance(features[0], dict):
                # Convert to array (assumes consistent keys)
                feature_names = sorted(features[0].keys())
                X = np.array([[item[key] for key in feature_names] for item in features])
            else:
                X = np.array(features)
        else:
            X = np.array(features)
        
        return X
```

This guide provides a comprehensive foundation for creating custom nodes that are robust, maintainable, and follow SDK best practices. Remember to always test your custom nodes thoroughly and handle edge cases gracefully.