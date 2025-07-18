# DataFlow Custom Nodes Development

Guide to creating custom nodes for DataFlow workflows.

## Overview

While DataFlow automatically generates nodes for your models, you may need custom nodes for specialized logic, external integrations, or complex operations.

## Basic Custom Node

### Simple Node Structure

```python
from kailash.core.node import Node
from kailash.core.execution import NodeException

class DataValidationNode(Node):
    """Custom node for data validation."""

    def __init__(self, node_id: str, parameters: dict):
        # Set default parameters BEFORE super().__init__
        self.validation_rules = parameters.get("rules", {})
        self.strict_mode = parameters.get("strict", True)
        self.error_handler = parameters.get("on_error", "throw")

        # Call parent constructor
        super().__init__(node_id, parameters)

    def execute(self, input_data: dict) -> dict:
        """Execute validation logic."""
        data = input_data.get("data", {})
        errors = []

        # Apply validation rules
        for field, rules in self.validation_rules.items():
            value = data.get(field)

            # Required check
            if rules.get("required") and value is None:
                errors.append(f"{field} is required")
                continue

            # Type check
            expected_type = rules.get("type")
            if expected_type and not isinstance(value, expected_type):
                errors.append(f"{field} must be {expected_type.__name__}")

            # Custom validator
            if "validator" in rules:
                try:
                    if not rules["validator"](value):
                        errors.append(f"{field} failed validation")
                except Exception as e:
                    errors.append(f"{field} validation error: {str(e)}")

        # Handle errors
        if errors:
            if self.error_handler == "throw":
                raise NodeException(f"Validation failed: {', '.join(errors)}")
            else:
                return {
                    "valid": False,
                    "errors": errors,
                    "data": data
                }

        return {
            "valid": True,
            "data": data
        }
```

### Using Custom Node

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Register custom node
WorkflowBuilder.register_node("DataValidationNode", DataValidationNode)

# Use in workflow
workflow = WorkflowBuilder()

workflow.add_node("DataValidationNode", "validate_user", {
    "rules": {
        "email": {
            "required": True,
            "type": str,
            "validator": lambda x: "@" in x
        },
        "age": {
            "required": True,
            "type": int,
            "validator": lambda x: 0 < x < 150
        }
    },
    "strict": True
})

runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build(), {
    "data": {"email": "user@example.com", "age": 25}
})
```

## Advanced Custom Nodes

### Database Integration Node

```python
class CustomQueryNode(Node):
    """Execute custom SQL queries with DataFlow integration."""

    def __init__(self, node_id: str, parameters: dict):
        self.query = parameters.get("query")
        self.params = parameters.get("params", {})
        self.return_type = parameters.get("return_type", "dict")
        self.timeout = parameters.get("timeout", 30.0)

        super().__init__(node_id, parameters)

    def execute(self, input_data: dict) -> dict:
        """Execute custom query."""
        # Get database connection from DataFlow
        db = self.get_dataflow_instance()

        # Parameter substitution from input data
        query_params = {}
        for key, value in self.params.items():
            if isinstance(value, str) and value.startswith(":"):
                param_name = value[1:]
                query_params[key] = input_data.get(param_name)
            else:
                query_params[key] = value

        try:
            with db.connection() as conn:
                # Set timeout
                if self.timeout:
                    conn.execute(f"SET statement_timeout = {int(self.timeout * 1000)}")

                # Execute query
                result = conn.execute(self.query, query_params)

                # Format results based on return type
                if self.return_type == "scalar":
                    return {"result": result.scalar()}
                elif self.return_type == "list":
                    return {"result": [dict(row) for row in result]}
                elif self.return_type == "dataframe":
                    import pandas as pd
                    return {"result": pd.DataFrame(result.fetchall())}
                else:
                    return {"result": result.fetchall()}

        except Exception as e:
            raise NodeException(f"Query execution failed: {str(e)}")
```

### External API Integration Node

```python
import httpx
import asyncio
from typing import Optional

class AsyncAPINode(Node):
    """Async node for external API calls."""

    def __init__(self, node_id: str, parameters: dict):
        self.url = parameters.get("url")
        self.method = parameters.get("method", "GET")
        self.headers = parameters.get("headers", {})
        self.timeout = parameters.get("timeout", 30.0)
        self.retry_count = parameters.get("retry_count", 3)
        self.retry_delay = parameters.get("retry_delay", 1.0)

        super().__init__(node_id, parameters)

    async def execute_async(self, input_data: dict) -> dict:
        """Execute async API call."""
        # Build request parameters
        request_data = self._build_request(input_data)

        async with httpx.AsyncClient() as client:
            for attempt in range(self.retry_count):
                try:
                    response = await client.request(
                        method=self.method,
                        url=self.url,
                        headers=self.headers,
                        json=request_data.get("json"),
                        params=request_data.get("params"),
                        timeout=self.timeout
                    )

                    response.raise_for_status()

                    return {
                        "status_code": response.status_code,
                        "data": response.json(),
                        "headers": dict(response.headers)
                    }

                except httpx.HTTPError as e:
                    if attempt < self.retry_count - 1:
                        await asyncio.sleep(self.retry_delay * (attempt + 1))
                        continue
                    raise NodeException(f"API call failed: {str(e)}")

    def execute(self, input_data: dict) -> dict:
        """Synchronous wrapper for async execution."""
        return asyncio.run(self.execute_async(input_data))

    def _build_request(self, input_data: dict) -> dict:
        """Build request from input data."""
        return {
            "json": input_data.get("body"),
            "params": input_data.get("query_params")
        }
```

### Machine Learning Node

```python
import pickle
import numpy as np
from pathlib import Path

class MLPredictionNode(Node):
    """Node for ML model predictions."""

    def __init__(self, node_id: str, parameters: dict):
        self.model_path = parameters.get("model_path")
        self.feature_columns = parameters.get("features")
        self.preprocessing = parameters.get("preprocessing", {})
        self.threshold = parameters.get("threshold", 0.5)

        # Load model
        self.model = self._load_model()

        super().__init__(node_id, parameters)

    def _load_model(self):
        """Load ML model from file."""
        model_path = Path(self.model_path)
        if not model_path.exists():
            raise ValueError(f"Model not found: {self.model_path}")

        with open(model_path, 'rb') as f:
            return pickle.load(f)

    def execute(self, input_data: dict) -> dict:
        """Make predictions."""
        # Extract features
        features = self._extract_features(input_data)

        # Preprocess
        features = self._preprocess(features)

        # Predict
        predictions = self.model.predict_proba(features)

        # Format results
        results = []
        for i, pred in enumerate(predictions):
            result = {
                "probability": float(pred[1]),  # Assuming binary classification
                "prediction": int(pred[1] > self.threshold),
                "confidence": float(max(pred))
            }
            results.append(result)

        return {
            "predictions": results,
            "model_version": getattr(self.model, 'version', 'unknown')
        }

    def _extract_features(self, input_data: dict) -> np.ndarray:
        """Extract features from input data."""
        data = input_data.get("data", [])
        if not isinstance(data, list):
            data = [data]

        features = []
        for record in data:
            row = [record.get(col, 0) for col in self.feature_columns]
            features.append(row)

        return np.array(features)

    def _preprocess(self, features: np.ndarray) -> np.ndarray:
        """Apply preprocessing."""
        # Scaling
        if "scaler" in self.preprocessing:
            features = self.preprocessing["scaler"].transform(features)

        # Other transformations
        return features
```

## Batch Processing Node

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
import math

class BatchProcessorNode(Node):
    """Process data in batches with parallel execution."""

    def __init__(self, node_id: str, parameters: dict):
        self.batch_size = parameters.get("batch_size", 100)
        self.parallel_workers = parameters.get("workers", 4)
        self.processor_node = parameters.get("processor_node")
        self.error_handling = parameters.get("error_handling", "fail_fast")

        super().__init__(node_id, parameters)

    def execute(self, input_data: dict) -> dict:
        """Execute batch processing."""
        items = input_data.get("items", [])
        total_items = len(items)

        # Split into batches
        batches = self._create_batches(items)

        # Process batches in parallel
        results = []
        errors = []

        with ThreadPoolExecutor(max_workers=self.parallel_workers) as executor:
            # Submit batch processing tasks
            future_to_batch = {
                executor.submit(self._process_batch, batch, idx): (batch, idx)
                for idx, batch in enumerate(batches)
            }

            # Collect results
            for future in as_completed(future_to_batch):
                batch, idx = future_to_batch[future]
                try:
                    batch_result = future.result()
                    results.extend(batch_result["items"])
                except Exception as e:
                    error_info = {
                        "batch_index": idx,
                        "batch_size": len(batch),
                        "error": str(e)
                    }
                    errors.append(error_info)

                    if self.error_handling == "fail_fast":
                        # Cancel remaining tasks
                        for f in future_to_batch:
                            f.cancel()
                        raise NodeException(f"Batch {idx} failed: {str(e)}")

        return {
            "total_items": total_items,
            "processed_items": len(results),
            "results": results,
            "errors": errors,
            "success_rate": len(results) / total_items if total_items > 0 else 0
        }

    def _create_batches(self, items: list) -> list:
        """Split items into batches."""
        num_batches = math.ceil(len(items) / self.batch_size)
        return [
            items[i * self.batch_size:(i + 1) * self.batch_size]
            for i in range(num_batches)
        ]

    def _process_batch(self, batch: list, batch_idx: int) -> dict:
        """Process a single batch."""
        # Create workflow for batch processing
        workflow = WorkflowBuilder()
        workflow.add_node(self.processor_node, "process", {
            "items": batch,
            "batch_index": batch_idx
        })

        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())

        return results["process"]
```

## State Management Node

```python
import json
from typing import Any

class StatefulNode(Node):
    """Node with persistent state management."""

    def __init__(self, node_id: str, parameters: dict):
        self.state_key = parameters.get("state_key", node_id)
        self.initial_state = parameters.get("initial_state", {})
        self.state_backend = parameters.get("backend", "redis")
        self.ttl = parameters.get("ttl", 3600)  # 1 hour default

        super().__init__(node_id, parameters)

    def execute(self, input_data: dict) -> dict:
        """Execute with state management."""
        # Load current state
        current_state = self._load_state()

        # Process with state
        action = input_data.get("action", "update")

        if action == "get":
            return {"state": current_state}

        elif action == "update":
            updates = input_data.get("updates", {})
            new_state = {**current_state, **updates}
            self._save_state(new_state)
            return {"state": new_state, "previous": current_state}

        elif action == "increment":
            field = input_data.get("field")
            amount = input_data.get("amount", 1)
            current_value = current_state.get(field, 0)
            new_value = current_value + amount
            current_state[field] = new_value
            self._save_state(current_state)
            return {"field": field, "new_value": new_value, "increment": amount}

        elif action == "reset":
            self._save_state(self.initial_state)
            return {"state": self.initial_state, "reset": True}

        else:
            raise ValueError(f"Unknown action: {action}")

    def _load_state(self) -> dict:
        """Load state from backend."""
        if self.state_backend == "redis":
            redis_client = self.get_redis_client()
            state_data = redis_client.get(self.state_key)
            if state_data:
                return json.loads(state_data)
        elif self.state_backend == "database":
            db = self.get_dataflow_instance()
            with db.connection() as conn:
                result = conn.execute(
                    "SELECT state_data FROM node_states WHERE state_key = %s",
                    (self.state_key,)
                ).fetchone()
                if result:
                    return result['state_data']

        return self.initial_state.copy()

    def _save_state(self, state: dict) -> None:
        """Save state to backend."""
        if self.state_backend == "redis":
            redis_client = self.get_redis_client()
            redis_client.setex(
                self.state_key,
                self.ttl,
                json.dumps(state)
            )
        elif self.state_backend == "database":
            db = self.get_dataflow_instance()
            with db.connection() as conn:
                conn.execute("""
                    INSERT INTO node_states (state_key, state_data, expires_at)
                    VALUES (%s, %s, NOW() + INTERVAL '%s seconds')
                    ON CONFLICT (state_key) DO UPDATE
                    SET state_data = EXCLUDED.state_data,
                        expires_at = EXCLUDED.expires_at
                """, (self.state_key, json.dumps(state), self.ttl))
```

## Testing Custom Nodes

### Unit Testing

```python
import pytest
from unittest.mock import Mock, patch

class TestDataValidationNode:
    """Test custom validation node."""

    def test_valid_data(self):
        """Test validation with valid data."""
        node = DataValidationNode("test_validator", {
            "rules": {
                "email": {"required": True, "type": str},
                "age": {"required": True, "type": int}
            }
        })

        result = node.execute({
            "data": {"email": "test@example.com", "age": 25}
        })

        assert result["valid"] is True
        assert "errors" not in result

    def test_missing_required_field(self):
        """Test validation with missing field."""
        node = DataValidationNode("test_validator", {
            "rules": {"email": {"required": True}},
            "on_error": "return"
        })

        result = node.execute({"data": {}})

        assert result["valid"] is False
        assert "email is required" in result["errors"]

    @patch('kailash.core.node.Node.get_dataflow_instance')
    def test_database_integration(self, mock_db):
        """Test node with database access."""
        # Mock database
        mock_conn = Mock()
        mock_db.return_value.connection.return_value.__enter__ = Mock(
            return_value=mock_conn
        )
        mock_db.return_value.connection.return_value.__exit__ = Mock()

        # Test node execution
        node = CustomQueryNode("test_query", {
            "query": "SELECT * FROM users WHERE id = :user_id",
            "params": {"user_id": ":id"}
        })

        mock_conn.execute.return_value.fetchall.return_value = [
            {"id": 1, "name": "Test User"}
        ]

        result = node.execute({"id": 1})

        assert len(result["result"]) == 1
        assert result["result"][0]["name"] == "Test User"
```

### Integration Testing

```python
def test_custom_node_in_workflow():
    """Test custom node in complete workflow."""
    # Register custom node
    WorkflowBuilder.register_node("DataValidationNode", DataValidationNode)

    # Build workflow
    workflow = WorkflowBuilder()

    # Add validation
    workflow.add_node("DataValidationNode", "validate", {
        "rules": {
            "name": {"required": True, "type": str},
            "email": {"required": True, "type": str}
        }
    })

    # Add database operation after validation
    workflow.add_node("UserCreateNode", "create_user", {
        "name": ":name",
        "email": ":email"
    })

    # Connect nodes
    workflow.add_connection("validate", "create_user", "data", "")

    # Execute
    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build(), {
        "data": {"name": "Test User", "email": "test@example.com"}
    })

    assert results["validate"]["valid"] is True
    assert results["create_user"]["success"] is True
```

## Best Practices

1. **Initialize Parameters First**: Always set parameters before calling `super().__init__()`
2. **Handle Errors Gracefully**: Use NodeException for clear error messages
3. **Document Parameters**: Include docstrings with parameter descriptions
4. **Test Thoroughly**: Unit test nodes in isolation and integration
5. **Follow Naming Convention**: Node classes must end with "Node"
6. **Implement Async When Needed**: Use async for I/O-bound operations
7. **Manage Resources**: Clean up connections, files, etc. in finally blocks

## Next Steps

- **Node Catalog**: [Node Index](../../sdk-users/nodes/node-index.md)
- **Workflow Patterns**: [Workflow Guide](../workflows/README.md)
- **Testing**: [Testing Guide](../testing/README.md)

Custom nodes extend DataFlow's capabilities. Build them when you need specialized logic beyond the auto-generated CRUD nodes.
