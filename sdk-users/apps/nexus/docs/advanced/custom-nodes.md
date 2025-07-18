# Custom Nodes Development Guide

Create specialized workflow nodes for Nexus's workflow-native platform with advanced features, enterprise capabilities, and production-ready implementations.

## Overview

Nexus's custom node architecture enables developers to create domain-specific workflow components with built-in enterprise features like caching, monitoring, error recovery, and performance optimization. This guide covers node development patterns, advanced implementations, and best practices.

## Node Development Fundamentals

### Base Node Architecture

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.base import BaseNode
from abc import ABC, abstractmethod
import time
import json
import hashlib
from typing import Dict, Any, Optional, List
from enum import Enum
import threading
from concurrent.futures import ThreadPoolExecutor

app = Nexus()

class NodeCategory(Enum):
    """Node categories for organization"""
    DATA_PROCESSING = "data_processing"
    AI_ML = "ai_ml"
    INTEGRATION = "integration"
    UTILITY = "utility"
    SECURITY = "security"
    MONITORING = "monitoring"

class ExecutionMode(Enum):
    """Node execution modes"""
    SYNCHRONOUS = "sync"
    ASYNCHRONOUS = "async"
    BATCH = "batch"
    STREAMING = "streaming"

class NodeMetadata:
    """Comprehensive node metadata"""

    def __init__(self, name: str, category: NodeCategory, version: str = "1.0.0"):
        self.name = name
        self.category = category
        self.version = version
        self.description = ""
        self.author = ""
        self.tags = []
        self.input_schema = {}
        self.output_schema = {}
        self.configuration_schema = {}
        self.supported_execution_modes = [ExecutionMode.SYNCHRONOUS]
        self.resource_requirements = {
            "min_memory_mb": 64,
            "max_memory_mb": 512,
            "cpu_cores": 1,
            "io_intensive": False,
            "network_required": False
        }
        self.enterprise_features = {
            "caching": True,
            "monitoring": True,
            "error_recovery": True,
            "audit_logging": True,
            "rate_limiting": False,
            "load_balancing": False
        }

class EnterpriseBaseNode(BaseNode):
    """Enhanced base node with enterprise features"""

    def __init__(self, node_id: str, parameters: Dict[str, Any]):
        super().__init__(node_id, parameters)
        self.metadata = self._initialize_metadata()
        self.execution_stats = {
            "total_executions": 0,
            "successful_executions": 0,
            "failed_executions": 0,
            "avg_execution_time": 0.0,
            "last_execution": None,
            "peak_memory_usage": 0,
            "cache_hits": 0,
            "cache_misses": 0
        }

        # Enterprise capabilities
        self.cache_manager = self._initialize_cache()
        self.monitoring_enabled = parameters.get("enable_monitoring", True)
        self.error_recovery_enabled = parameters.get("enable_error_recovery", True)
        self.audit_enabled = parameters.get("enable_audit", True)

        # Performance optimization
        self.execution_lock = threading.Lock()
        self.thread_pool = ThreadPoolExecutor(max_workers=parameters.get("max_workers", 4))

        # Configuration validation
        self._validate_configuration(parameters)

    @abstractmethod
    def _initialize_metadata(self) -> NodeMetadata:
        """Initialize node metadata - must be implemented by subclasses"""
        pass

    @abstractmethod
    def _execute_core_logic(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute core business logic - must be implemented by subclasses"""
        pass

    def execute(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute node with enterprise features"""

        execution_id = self._generate_execution_id()
        start_time = time.time()

        try:
            # Pre-execution logging
            if self.audit_enabled:
                self._log_execution_start(execution_id, data)

            # Input validation
            self._validate_input(data)

            # Check cache
            if self.metadata.enterprise_features["caching"]:
                cached_result = self._check_cache(data)
                if cached_result:
                    self.execution_stats["cache_hits"] += 1
                    return self._prepare_output(cached_result, execution_id, start_time, True)
                self.execution_stats["cache_misses"] += 1

            # Execute core logic
            result = self._execute_core_logic(data)

            # Post-processing
            processed_result = self._post_process_result(result, data)

            # Cache result
            if self.metadata.enterprise_features["caching"]:
                self._cache_result(data, processed_result)

            # Update statistics
            self._update_execution_stats(start_time, True)

            # Audit logging
            if self.audit_enabled:
                self._log_execution_success(execution_id, data, processed_result)

            return self._prepare_output(processed_result, execution_id, start_time, False)

        except Exception as e:
            # Error handling
            self._update_execution_stats(start_time, False)

            # Attempt recovery
            if self.error_recovery_enabled:
                recovery_result = self._attempt_error_recovery(data, e, execution_id)
                if recovery_result:
                    return self._prepare_output(recovery_result, execution_id, start_time, False)

            # Error logging
            if self.audit_enabled:
                self._log_execution_error(execution_id, data, e)

            raise self._wrap_error(e, execution_id)

    def _initialize_cache(self):
        """Initialize caching system"""
        return {
            "data": {},
            "max_size": self.parameters.get("cache_max_size", 1000),
            "ttl_seconds": self.parameters.get("cache_ttl", 300),
            "hit_rate": 0.0
        }

    def _validate_configuration(self, parameters: Dict[str, Any]):
        """Validate node configuration"""
        schema = self.metadata.configuration_schema

        if not schema:
            return  # No validation schema defined

        for required_param in schema.get("required", []):
            if required_param not in parameters:
                raise ValueError(f"Required parameter '{required_param}' missing")

        for param_name, param_config in schema.get("properties", {}).items():
            if param_name in parameters:
                self._validate_parameter(param_name, parameters[param_name], param_config)

    def _validate_parameter(self, name: str, value: Any, config: Dict[str, Any]):
        """Validate individual parameter"""
        param_type = config.get("type")

        if param_type == "integer" and not isinstance(value, int):
            raise ValueError(f"Parameter '{name}' must be an integer")
        elif param_type == "string" and not isinstance(value, str):
            raise ValueError(f"Parameter '{name}' must be a string")
        elif param_type == "boolean" and not isinstance(value, bool):
            raise ValueError(f"Parameter '{name}' must be a boolean")

        # Range validation
        if "minimum" in config and value < config["minimum"]:
            raise ValueError(f"Parameter '{name}' must be >= {config['minimum']}")
        if "maximum" in config and value > config["maximum"]:
            raise ValueError(f"Parameter '{name}' must be <= {config['maximum']}")

    def _validate_input(self, data: Dict[str, Any]):
        """Validate input data against schema"""
        schema = self.metadata.input_schema

        if not schema:
            return

        for required_field in schema.get("required", []):
            if required_field not in data:
                raise ValueError(f"Required input field '{required_field}' missing")

    def _check_cache(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Check for cached result"""
        cache_key = self._generate_cache_key(data)

        if cache_key in self.cache_manager["data"]:
            cached_entry = self.cache_manager["data"][cache_key]

            # Check TTL
            if time.time() - cached_entry["timestamp"] < self.cache_manager["ttl_seconds"]:
                return cached_entry["result"]
            else:
                # Remove expired entry
                del self.cache_manager["data"][cache_key]

        return None

    def _cache_result(self, data: Dict[str, Any], result: Dict[str, Any]):
        """Cache execution result"""
        cache_key = self._generate_cache_key(data)

        # Evict old entries if cache is full
        if len(self.cache_manager["data"]) >= self.cache_manager["max_size"]:
            self._evict_oldest_cache_entry()

        self.cache_manager["data"][cache_key] = {
            "result": result,
            "timestamp": time.time()
        }

    def _generate_cache_key(self, data: Dict[str, Any]) -> str:
        """Generate cache key for input data"""
        # Create deterministic hash of input data
        data_str = json.dumps(data, sort_keys=True)
        return hashlib.md5(data_str.encode()).hexdigest()

    def _evict_oldest_cache_entry(self):
        """Remove oldest cache entry"""
        if self.cache_manager["data"]:
            oldest_key = min(
                self.cache_manager["data"].keys(),
                key=lambda k: self.cache_manager["data"][k]["timestamp"]
            )
            del self.cache_manager["data"][oldest_key]

    def _generate_execution_id(self) -> str:
        """Generate unique execution ID"""
        return f"{self.node_id}_{int(time.time())}_{id(self)}"

    def _update_execution_stats(self, start_time: float, success: bool):
        """Update execution statistics"""
        execution_time = time.time() - start_time

        with self.execution_lock:
            self.execution_stats["total_executions"] += 1
            self.execution_stats["last_execution"] = time.time()

            if success:
                self.execution_stats["successful_executions"] += 1
            else:
                self.execution_stats["failed_executions"] += 1

            # Update average execution time
            total_time = (self.execution_stats["avg_execution_time"] *
                         (self.execution_stats["total_executions"] - 1))
            self.execution_stats["avg_execution_time"] = (
                (total_time + execution_time) / self.execution_stats["total_executions"]
            )

    def _post_process_result(self, result: Dict[str, Any], input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Post-process execution result"""
        # Add metadata to result
        result["_node_metadata"] = {
            "node_id": self.node_id,
            "node_name": self.metadata.name,
            "execution_time": time.time(),
            "version": self.metadata.version
        }

        return result

    def _prepare_output(self, result: Dict[str, Any], execution_id: str, start_time: float, from_cache: bool) -> Dict[str, Any]:
        """Prepare final output with execution metadata"""
        execution_time = time.time() - start_time

        output = result.copy() if isinstance(result, dict) else {"result": result}

        output["_execution_info"] = {
            "execution_id": execution_id,
            "execution_time_ms": execution_time * 1000,
            "from_cache": from_cache,
            "node_id": self.node_id,
            "timestamp": time.time()
        }

        return output

    def _attempt_error_recovery(self, data: Dict[str, Any], error: Exception, execution_id: str) -> Optional[Dict[str, Any]]:
        """Attempt to recover from execution error"""
        # Default recovery strategies
        recovery_strategies = [
            self._retry_with_backoff,
            self._fallback_execution,
            self._partial_result_recovery
        ]

        for strategy in recovery_strategies:
            try:
                recovery_result = strategy(data, error, execution_id)
                if recovery_result:
                    return recovery_result
            except Exception:
                continue  # Try next strategy

        return None

    def _retry_with_backoff(self, data: Dict[str, Any], error: Exception, execution_id: str) -> Optional[Dict[str, Any]]:
        """Retry execution with exponential backoff"""
        max_retries = self.parameters.get("max_retries", 3)
        base_delay = self.parameters.get("retry_base_delay", 1.0)

        for attempt in range(max_retries):
            try:
                delay = base_delay * (2 ** attempt)
                time.sleep(delay)
                return self._execute_core_logic(data)
            except Exception:
                if attempt == max_retries - 1:
                    break

        return None

    def _fallback_execution(self, data: Dict[str, Any], error: Exception, execution_id: str) -> Optional[Dict[str, Any]]:
        """Execute fallback logic if available"""
        # Override in subclasses to provide fallback behavior
        return None

    def _partial_result_recovery(self, data: Dict[str, Any], error: Exception, execution_id: str) -> Optional[Dict[str, Any]]:
        """Attempt to return partial results"""
        # Override in subclasses to provide partial result logic
        return None

    def _wrap_error(self, error: Exception, execution_id: str) -> Exception:
        """Wrap error with additional context"""
        error_message = f"Node '{self.node_id}' execution failed (ID: {execution_id}): {str(error)}"
        return type(error)(error_message) from error

    def _log_execution_start(self, execution_id: str, data: Dict[str, Any]):
        """Log execution start"""
        # Implement logging logic
        pass

    def _log_execution_success(self, execution_id: str, data: Dict[str, Any], result: Dict[str, Any]):
        """Log successful execution"""
        # Implement logging logic
        pass

    def _log_execution_error(self, execution_id: str, data: Dict[str, Any], error: Exception):
        """Log execution error"""
        # Implement logging logic
        pass

    def get_node_info(self) -> Dict[str, Any]:
        """Get comprehensive node information"""
        return {
            "metadata": {
                "name": self.metadata.name,
                "category": self.metadata.category.value,
                "version": self.metadata.version,
                "description": self.metadata.description,
                "tags": self.metadata.tags
            },
            "execution_stats": self.execution_stats.copy(),
            "cache_stats": {
                "size": len(self.cache_manager["data"]),
                "max_size": self.cache_manager["max_size"],
                "hit_rate": (self.execution_stats["cache_hits"] /
                           (self.execution_stats["cache_hits"] + self.execution_stats["cache_misses"])
                           if (self.execution_stats["cache_hits"] + self.execution_stats["cache_misses"]) > 0 else 0)
            },
            "configuration": self.parameters,
            "resource_requirements": self.metadata.resource_requirements,
            "enterprise_features": self.metadata.enterprise_features
        }

# Example implementation
class DataTransformationNode(EnterpriseBaseNode):
    """Advanced data transformation node"""

    def _initialize_metadata(self) -> NodeMetadata:
        metadata = NodeMetadata("DataTransformationNode", NodeCategory.DATA_PROCESSING, "1.2.0")
        metadata.description = "Advanced data transformation with multiple formats and validation"
        metadata.author = "Nexus Data Team"
        metadata.tags = ["data", "transformation", "validation", "formatting"]

        metadata.input_schema = {
            "type": "object",
            "required": ["data", "transformation_type"],
            "properties": {
                "data": {"type": "object"},
                "transformation_type": {"type": "string", "enum": ["normalize", "aggregate", "filter", "enrich"]},
                "options": {"type": "object"}
            }
        }

        metadata.output_schema = {
            "type": "object",
            "properties": {
                "transformed_data": {"type": "object"},
                "metadata": {"type": "object"},
                "statistics": {"type": "object"}
            }
        }

        metadata.configuration_schema = {
            "type": "object",
            "properties": {
                "enable_validation": {"type": "boolean", "default": True},
                "max_batch_size": {"type": "integer", "minimum": 1, "maximum": 10000, "default": 1000},
                "transformation_timeout": {"type": "integer", "minimum": 1, "maximum": 300, "default": 30}
            }
        }

        return metadata

    def _execute_core_logic(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute data transformation logic"""

        input_data = data["data"]
        transformation_type = data["transformation_type"]
        options = data.get("options", {})

        # Perform transformation based on type
        if transformation_type == "normalize":
            transformed_data = self._normalize_data(input_data, options)
        elif transformation_type == "aggregate":
            transformed_data = self._aggregate_data(input_data, options)
        elif transformation_type == "filter":
            transformed_data = self._filter_data(input_data, options)
        elif transformation_type == "enrich":
            transformed_data = self._enrich_data(input_data, options)
        else:
            raise ValueError(f"Unsupported transformation type: {transformation_type}")

        # Generate statistics
        statistics = self._generate_statistics(input_data, transformed_data)

        return {
            "transformed_data": transformed_data,
            "transformation_type": transformation_type,
            "input_size": len(input_data) if isinstance(input_data, (list, dict)) else 1,
            "output_size": len(transformed_data) if isinstance(transformed_data, (list, dict)) else 1,
            "statistics": statistics,
            "success": True
        }

    def _normalize_data(self, data: Any, options: Dict[str, Any]) -> Any:
        """Normalize data format"""
        if isinstance(data, dict):
            normalized = {}
            for key, value in data.items():
                # Convert keys to lowercase
                normalized_key = key.lower().replace(" ", "_")

                # Normalize values
                if isinstance(value, str):
                    normalized[normalized_key] = value.strip().lower()
                elif isinstance(value, (int, float)):
                    normalized[normalized_key] = value
                else:
                    normalized[normalized_key] = str(value)

            return normalized
        elif isinstance(data, list):
            return [self._normalize_data(item, options) for item in data]
        else:
            return data

    def _aggregate_data(self, data: Any, options: Dict[str, Any]) -> Any:
        """Aggregate data"""
        if isinstance(data, list) and all(isinstance(item, dict) for item in data):
            # Aggregate list of dictionaries
            aggregated = {}
            group_by = options.get("group_by", "category")

            for item in data:
                key = item.get(group_by, "unknown")
                if key not in aggregated:
                    aggregated[key] = {"count": 0, "items": []}

                aggregated[key]["count"] += 1
                aggregated[key]["items"].append(item)

            return aggregated
        else:
            return {"total_count": len(data) if isinstance(data, (list, dict)) else 1}

    def _filter_data(self, data: Any, options: Dict[str, Any]) -> Any:
        """Filter data based on criteria"""
        filter_criteria = options.get("criteria", {})

        if isinstance(data, list):
            filtered = []
            for item in data:
                if self._matches_criteria(item, filter_criteria):
                    filtered.append(item)
            return filtered
        elif isinstance(data, dict):
            if self._matches_criteria(data, filter_criteria):
                return data
            else:
                return {}
        else:
            return data

    def _enrich_data(self, data: Any, options: Dict[str, Any]) -> Any:
        """Enrich data with additional information"""
        enrichment_config = options.get("enrichment", {})

        if isinstance(data, dict):
            enriched = data.copy()
            enriched["_enrichment"] = {
                "timestamp": time.time(),
                "node_id": self.node_id,
                "version": self.metadata.version,
                "enrichment_level": enrichment_config.get("level", "basic")
            }
            return enriched
        elif isinstance(data, list):
            return [self._enrich_data(item, options) for item in data]
        else:
            return data

    def _matches_criteria(self, item: Any, criteria: Dict[str, Any]) -> bool:
        """Check if item matches filter criteria"""
        if not isinstance(item, dict):
            return True

        for key, expected_value in criteria.items():
            if key not in item:
                return False

            actual_value = item[key]

            if isinstance(expected_value, dict):
                # Handle range criteria
                if "min" in expected_value and actual_value < expected_value["min"]:
                    return False
                if "max" in expected_value and actual_value > expected_value["max"]:
                    return False
            else:
                # Exact match
                if actual_value != expected_value:
                    return False

        return True

    def _generate_statistics(self, input_data: Any, output_data: Any) -> Dict[str, Any]:
        """Generate transformation statistics"""
        return {
            "input_type": type(input_data).__name__,
            "output_type": type(output_data).__name__,
            "transformation_timestamp": time.time(),
            "data_reduction": self._calculate_data_reduction(input_data, output_data)
        }

    def _calculate_data_reduction(self, input_data: Any, output_data: Any) -> float:
        """Calculate data reduction percentage"""
        input_size = len(str(input_data))
        output_size = len(str(output_data))

        if input_size == 0:
            return 0.0

        reduction = (input_size - output_size) / input_size * 100
        return max(0.0, reduction)

# Test the custom node
transformation_node = DataTransformationNode("transform_001", {
    "enable_validation": True,
    "max_batch_size": 500,
    "transformation_timeout": 60,
    "enable_monitoring": True,
    "cache_max_size": 100
})

# Test data transformation
test_data = {
    "data": [
        {"Name": "John Doe", "Age": 30, "Category": "Employee"},
        {"Name": "Jane Smith", "Age": 25, "Category": "Manager"},
        {"Name": "Bob Johnson", "Age": 35, "Category": "Employee"}
    ],
    "transformation_type": "normalize"
}

result = transformation_node.execute(test_data)
node_info = transformation_node.get_node_info()
```

### AI/ML Integration Nodes

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder
import time
import json
import base64
from typing import Dict, Any, List, Optional, Union
from enum import Enum
import threading

app = Nexus()

class ModelType(Enum):
    """Supported ML model types"""
    CLASSIFICATION = "classification"
    REGRESSION = "regression"
    CLUSTERING = "clustering"
    NLP = "nlp"
    COMPUTER_VISION = "computer_vision"
    TIME_SERIES = "time_series"

class ModelFramework(Enum):
    """Supported ML frameworks"""
    SCIKIT_LEARN = "scikit_learn"
    TENSORFLOW = "tensorflow"
    PYTORCH = "pytorch"
    HUGGINGFACE = "huggingface"
    ONNX = "onnx"
    CUSTOM = "custom"

class MLInferenceNode(EnterpriseBaseNode):
    """Advanced ML model inference node"""

    def _initialize_metadata(self) -> NodeMetadata:
        metadata = NodeMetadata("MLInferenceNode", NodeCategory.AI_ML, "2.0.0")
        metadata.description = "High-performance ML model inference with multiple framework support"
        metadata.author = "Nexus AI Team"
        metadata.tags = ["ml", "ai", "inference", "prediction", "model"]

        metadata.input_schema = {
            "type": "object",
            "required": ["input_data", "model_config"],
            "properties": {
                "input_data": {"type": ["object", "array"]},
                "model_config": {
                    "type": "object",
                    "required": ["model_id", "model_type"],
                    "properties": {
                        "model_id": {"type": "string"},
                        "model_type": {"type": "string"},
                        "framework": {"type": "string"},
                        "version": {"type": "string"}
                    }
                },
                "inference_options": {"type": "object"}
            }
        }

        metadata.configuration_schema = {
            "type": "object",
            "properties": {
                "model_cache_size": {"type": "integer", "minimum": 1, "maximum": 100, "default": 10},
                "batch_size": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 32},
                "inference_timeout": {"type": "integer", "minimum": 1, "maximum": 300, "default": 30},
                "enable_gpu": {"type": "boolean", "default": False},
                "model_registry_url": {"type": "string"}
            }
        }

        metadata.resource_requirements = {
            "min_memory_mb": 512,
            "max_memory_mb": 4096,
            "cpu_cores": 2,
            "io_intensive": True,
            "network_required": True
        }

        return metadata

    def __init__(self, node_id: str, parameters: Dict[str, Any]):
        super().__init__(node_id, parameters)
        self.model_cache = {}
        self.model_registry = self._initialize_model_registry()
        self.inference_stats = {
            "total_inferences": 0,
            "successful_inferences": 0,
            "failed_inferences": 0,
            "avg_inference_time": 0.0,
            "batch_inferences": 0,
            "model_cache_hits": 0
        }
        self.inference_lock = threading.Lock()

    def _initialize_model_registry(self) -> Dict[str, Any]:
        """Initialize model registry with available models"""
        return {
            "text_classifier": {
                "model_type": ModelType.NLP,
                "framework": ModelFramework.HUGGINGFACE,
                "version": "1.0.0",
                "input_format": "text",
                "output_format": "classification",
                "model_path": "/models/text_classifier",
                "loaded": False,
                "load_time": 0
            },
            "image_classifier": {
                "model_type": ModelType.COMPUTER_VISION,
                "framework": ModelFramework.TENSORFLOW,
                "version": "2.1.0",
                "input_format": "image",
                "output_format": "classification",
                "model_path": "/models/image_classifier",
                "loaded": False,
                "load_time": 0
            },
            "regression_model": {
                "model_type": ModelType.REGRESSION,
                "framework": ModelFramework.SCIKIT_LEARN,
                "version": "1.3.0",
                "input_format": "tabular",
                "output_format": "regression",
                "model_path": "/models/regression_model",
                "loaded": False,
                "load_time": 0
            }
        }

    def _execute_core_logic(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute ML inference"""

        input_data = data["input_data"]
        model_config = data["model_config"]
        inference_options = data.get("inference_options", {})

        # Load model if needed
        model = self._load_model(model_config["model_id"])

        # Prepare input data
        processed_input = self._preprocess_input(input_data, model)

        # Perform inference
        start_time = time.time()

        if isinstance(processed_input, list) and len(processed_input) > 1:
            # Batch inference
            predictions = self._batch_inference(processed_input, model, inference_options)
            self.inference_stats["batch_inferences"] += 1
        else:
            # Single inference
            predictions = self._single_inference(processed_input, model, inference_options)

        inference_time = time.time() - start_time

        # Post-process results
        results = self._postprocess_output(predictions, model, inference_options)

        # Update statistics
        self._update_inference_stats(inference_time, True)

        return {
            "predictions": results,
            "model_info": {
                "model_id": model_config["model_id"],
                "model_type": model["model_type"].value,
                "framework": model["framework"].value,
                "version": model["version"]
            },
            "inference_metadata": {
                "inference_time_ms": inference_time * 1000,
                "input_size": len(processed_input) if isinstance(processed_input, list) else 1,
                "batch_processing": isinstance(processed_input, list) and len(processed_input) > 1,
                "preprocessing_applied": True,
                "confidence_scores": self._extract_confidence_scores(results)
            },
            "success": True
        }

    def _load_model(self, model_id: str) -> Dict[str, Any]:
        """Load ML model with caching"""

        if model_id in self.model_cache:
            self.inference_stats["model_cache_hits"] += 1
            return self.model_cache[model_id]

        if model_id not in self.model_registry:
            raise ValueError(f"Model '{model_id}' not found in registry")

        model_info = self.model_registry[model_id].copy()

        # Simulate model loading
        load_start = time.time()

        # Load model based on framework
        if model_info["framework"] == ModelFramework.HUGGINGFACE:
            model_info["model"] = self._load_huggingface_model(model_info)
        elif model_info["framework"] == ModelFramework.TENSORFLOW:
            model_info["model"] = self._load_tensorflow_model(model_info)
        elif model_info["framework"] == ModelFramework.SCIKIT_LEARN:
            model_info["model"] = self._load_sklearn_model(model_info)
        else:
            raise ValueError(f"Unsupported framework: {model_info['framework']}")

        model_info["load_time"] = time.time() - load_start
        model_info["loaded"] = True

        # Cache model
        self._cache_model(model_id, model_info)

        return model_info

    def _load_huggingface_model(self, model_info: Dict[str, Any]) -> Dict[str, Any]:
        """Load HuggingFace model (simulated)"""
        return {
            "type": "huggingface",
            "tokenizer": "mock_tokenizer",
            "model": "mock_model",
            "max_length": 512
        }

    def _load_tensorflow_model(self, model_info: Dict[str, Any]) -> Dict[str, Any]:
        """Load TensorFlow model (simulated)"""
        return {
            "type": "tensorflow",
            "model": "mock_tf_model",
            "input_shape": [224, 224, 3],
            "output_classes": 1000
        }

    def _load_sklearn_model(self, model_info: Dict[str, Any]) -> Dict[str, Any]:
        """Load scikit-learn model (simulated)"""
        return {
            "type": "sklearn",
            "model": "mock_sklearn_model",
            "feature_count": 10,
            "scaler": "mock_scaler"
        }

    def _cache_model(self, model_id: str, model_info: Dict[str, Any]):
        """Cache loaded model"""
        max_cache_size = self.parameters.get("model_cache_size", 10)

        # Evict oldest models if cache is full
        if len(self.model_cache) >= max_cache_size:
            oldest_model = min(
                self.model_cache.keys(),
                key=lambda k: self.model_cache[k]["load_time"]
            )
            del self.model_cache[oldest_model]

        self.model_cache[model_id] = model_info

    def _preprocess_input(self, input_data: Any, model: Dict[str, Any]) -> Any:
        """Preprocess input data for model"""

        model_type = model["model_type"]
        framework = model["framework"]

        if model_type == ModelType.NLP:
            # Text preprocessing
            if isinstance(input_data, str):
                return [{"text": input_data}]
            elif isinstance(input_data, list):
                return [{"text": text} for text in input_data]
            else:
                return [{"text": str(input_data)}]

        elif model_type == ModelType.COMPUTER_VISION:
            # Image preprocessing
            if isinstance(input_data, str):
                # Assume base64 encoded image
                return [{"image": input_data, "format": "base64"}]
            elif isinstance(input_data, list):
                return [{"image": img, "format": "base64"} for img in input_data]

        elif model_type == ModelType.REGRESSION:
            # Tabular data preprocessing
            if isinstance(input_data, dict):
                return [input_data]
            elif isinstance(input_data, list):
                return input_data

        return input_data

    def _single_inference(self, input_data: Any, model: Dict[str, Any], options: Dict[str, Any]) -> Any:
        """Perform single inference"""

        # Simulate inference based on model type
        model_type = model["model_type"]

        if model_type == ModelType.NLP:
            return {
                "label": "positive",
                "confidence": 0.85,
                "scores": {"positive": 0.85, "negative": 0.15}
            }

        elif model_type == ModelType.COMPUTER_VISION:
            return {
                "class": "cat",
                "confidence": 0.92,
                "top_5": [
                    {"class": "cat", "confidence": 0.92},
                    {"class": "dog", "confidence": 0.05},
                    {"class": "bird", "confidence": 0.02},
                    {"class": "fish", "confidence": 0.01},
                    {"class": "other", "confidence": 0.00}
                ]
            }

        elif model_type == ModelType.REGRESSION:
            return {
                "prediction": 42.5,
                "confidence_interval": [40.2, 44.8],
                "feature_importance": {"feature_1": 0.3, "feature_2": 0.7}
            }

        return {"prediction": "mock_result"}

    def _batch_inference(self, input_batch: List[Any], model: Dict[str, Any], options: Dict[str, Any]) -> List[Any]:
        """Perform batch inference"""

        batch_size = self.parameters.get("batch_size", 32)
        results = []

        # Process in batches
        for i in range(0, len(input_batch), batch_size):
            batch = input_batch[i:i + batch_size]
            batch_results = []

            for item in batch:
                result = self._single_inference(item, model, options)
                batch_results.append(result)

            results.extend(batch_results)

        return results

    def _postprocess_output(self, predictions: Any, model: Dict[str, Any], options: Dict[str, Any]) -> Any:
        """Post-process model output"""

        if isinstance(predictions, list):
            # Batch results
            processed_results = []
            for pred in predictions:
                processed_pred = self._apply_postprocessing(pred, options)
                processed_results.append(processed_pred)
            return processed_results
        else:
            # Single result
            return self._apply_postprocessing(predictions, options)

    def _apply_postprocessing(self, prediction: Any, options: Dict[str, Any]) -> Any:
        """Apply post-processing to individual prediction"""

        # Add metadata
        if isinstance(prediction, dict):
            prediction["_postprocessing"] = {
                "timestamp": time.time(),
                "node_id": self.node_id,
                "applied_filters": options.get("filters", [])
            }

        return prediction

    def _extract_confidence_scores(self, results: Any) -> List[float]:
        """Extract confidence scores from results"""

        confidence_scores = []

        if isinstance(results, list):
            for result in results:
                if isinstance(result, dict) and "confidence" in result:
                    confidence_scores.append(result["confidence"])
        elif isinstance(results, dict) and "confidence" in results:
            confidence_scores.append(results["confidence"])

        return confidence_scores

    def _update_inference_stats(self, inference_time: float, success: bool):
        """Update inference statistics"""

        with self.inference_lock:
            self.inference_stats["total_inferences"] += 1

            if success:
                self.inference_stats["successful_inferences"] += 1
            else:
                self.inference_stats["failed_inferences"] += 1

            # Update average inference time
            total_time = (self.inference_stats["avg_inference_time"] *
                         (self.inference_stats["total_inferences"] - 1))
            self.inference_stats["avg_inference_time"] = (
                (total_time + inference_time) / self.inference_stats["total_inferences"]
            )

    def get_model_registry(self) -> Dict[str, Any]:
        """Get available models in registry"""
        return {
            model_id: {
                "model_type": info["model_type"].value,
                "framework": info["framework"].value,
                "version": info["version"],
                "input_format": info["input_format"],
                "output_format": info["output_format"],
                "loaded": info["loaded"]
            }
            for model_id, info in self.model_registry.items()
        }

    def get_inference_stats(self) -> Dict[str, Any]:
        """Get inference statistics"""
        return self.inference_stats.copy()

# Test ML inference node
ml_node = MLInferenceNode("ml_inference_001", {
    "model_cache_size": 5,
    "batch_size": 16,
    "inference_timeout": 30,
    "enable_gpu": False
})

# Test text classification
text_classification_data = {
    "input_data": "This is a great product! I love it.",
    "model_config": {
        "model_id": "text_classifier",
        "model_type": "nlp",
        "framework": "huggingface",
        "version": "1.0.0"
    },
    "inference_options": {
        "confidence_threshold": 0.7
    }
}

text_result = ml_node.execute(text_classification_data)

# Test batch image classification
image_classification_data = {
    "input_data": [
        "base64_encoded_image_1",
        "base64_encoded_image_2",
        "base64_encoded_image_3"
    ],
    "model_config": {
        "model_id": "image_classifier",
        "model_type": "computer_vision",
        "framework": "tensorflow",
        "version": "2.1.0"
    },
    "inference_options": {
        "top_k": 5
    }
}

image_result = ml_node.execute(image_classification_data)

# Get model registry and stats
model_registry = ml_node.get_model_registry()
inference_stats = ml_node.get_inference_stats()
```

### Real-time Processing Nodes

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder
import time
import threading
from collections import deque
from typing import Dict, Any, List, Optional, Callable
from enum import Enum
import asyncio
from concurrent.futures import ThreadPoolExecutor

app = Nexus()

class StreamingMode(Enum):
    """Streaming processing modes"""
    WINDOWED = "windowed"
    CONTINUOUS = "continuous"
    BATCHED = "batched"
    EVENT_DRIVEN = "event_driven"

class WindowType(Enum):
    """Time window types"""
    TUMBLING = "tumbling"
    SLIDING = "sliding"
    SESSION = "session"
    COUNT_BASED = "count_based"

class RealTimeStreamProcessor(EnterpriseBaseNode):
    """Real-time stream processing node with windowing and aggregation"""

    def _initialize_metadata(self) -> NodeMetadata:
        metadata = NodeMetadata("RealTimeStreamProcessor", NodeCategory.DATA_PROCESSING, "1.5.0")
        metadata.description = "High-performance real-time stream processing with windowing and aggregation"
        metadata.author = "Nexus Streaming Team"
        metadata.tags = ["streaming", "realtime", "windowing", "aggregation", "events"]

        metadata.input_schema = {
            "type": "object",
            "required": ["stream_data", "processing_config"],
            "properties": {
                "stream_data": {"type": "array"},
                "processing_config": {
                    "type": "object",
                    "required": ["window_type", "window_size"],
                    "properties": {
                        "window_type": {"type": "string"},
                        "window_size": {"type": "integer"},
                        "aggregation_functions": {"type": "array"},
                        "trigger_conditions": {"type": "object"}
                    }
                },
                "stream_metadata": {"type": "object"}
            }
        }

        metadata.configuration_schema = {
            "type": "object",
            "properties": {
                "max_buffer_size": {"type": "integer", "minimum": 100, "maximum": 100000, "default": 10000},
                "processing_threads": {"type": "integer", "minimum": 1, "maximum": 16, "default": 4},
                "checkpoint_interval": {"type": "integer", "minimum": 1, "maximum": 3600, "default": 60},
                "enable_backpressure": {"type": "boolean", "default": True},
                "watermark_delay_ms": {"type": "integer", "minimum": 0, "maximum": 60000, "default": 1000}
            }
        }

        metadata.supported_execution_modes = [ExecutionMode.STREAMING, ExecutionMode.ASYNCHRONOUS]
        metadata.resource_requirements = {
            "min_memory_mb": 256,
            "max_memory_mb": 2048,
            "cpu_cores": 2,
            "io_intensive": True,
            "network_required": False
        }

        return metadata

    def __init__(self, node_id: str, parameters: Dict[str, Any]):
        super().__init__(node_id, parameters)

        # Stream processing state
        self.stream_buffer = deque(maxlen=parameters.get("max_buffer_size", 10000))
        self.windows = {}
        self.processing_state = {
            "last_checkpoint": time.time(),
            "processed_events": 0,
            "watermark": 0,
            "active_windows": 0
        }

        # Threading and async setup
        self.processing_threads = parameters.get("processing_threads", 4)
        self.executor = ThreadPoolExecutor(max_workers=self.processing_threads)
        self.processing_lock = threading.Lock()
        self.window_lock = threading.Lock()

        # Stream metrics
        self.stream_metrics = {
            "events_processed": 0,
            "events_per_second": 0.0,
            "avg_latency_ms": 0.0,
            "windows_created": 0,
            "windows_closed": 0,
            "backpressure_events": 0,
            "out_of_order_events": 0
        }

        # Processing functions
        self.aggregation_functions = {
            "sum": self._sum_aggregation,
            "count": self._count_aggregation,
            "average": self._average_aggregation,
            "min": self._min_aggregation,
            "max": self._max_aggregation,
            "distinct_count": self._distinct_count_aggregation,
            "percentile": self._percentile_aggregation
        }

    def _execute_core_logic(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute real-time stream processing"""

        stream_data = data["stream_data"]
        processing_config = data["processing_config"]
        stream_metadata = data.get("stream_metadata", {})

        # Initialize processing session
        session_id = f"session_{int(time.time())}_{id(self)}"
        processing_start = time.time()

        # Process stream data
        if processing_config.get("streaming_mode", "windowed") == "windowed":
            results = self._process_windowed_stream(stream_data, processing_config, session_id)
        else:
            results = self._process_continuous_stream(stream_data, processing_config, session_id)

        processing_time = time.time() - processing_start

        # Update metrics
        self._update_stream_metrics(len(stream_data), processing_time)

        return {
            "processed_results": results,
            "session_info": {
                "session_id": session_id,
                "events_processed": len(stream_data),
                "processing_time_ms": processing_time * 1000,
                "windows_created": len(results.get("windows", [])),
                "throughput_eps": len(stream_data) / processing_time if processing_time > 0 else 0
            },
            "stream_metadata": stream_metadata,
            "processing_config": processing_config,
            "performance_metrics": self._get_performance_snapshot(),
            "success": True
        }

    def _process_windowed_stream(self, stream_data: List[Dict[str, Any]], config: Dict[str, Any], session_id: str) -> Dict[str, Any]:
        """Process stream with windowing"""

        window_type = WindowType(config["window_type"])
        window_size = config["window_size"]
        aggregation_functions = config.get("aggregation_functions", ["count"])

        # Create windows based on type
        windows = self._create_windows(stream_data, window_type, window_size, session_id)

        # Process each window
        window_results = []

        for window_id, window_data in windows.items():
            window_result = self._process_window(window_data, aggregation_functions, config)
            window_result["window_id"] = window_id
            window_result["window_type"] = window_type.value
            window_results.append(window_result)

        return {
            "windows": window_results,
            "total_windows": len(window_results),
            "window_type": window_type.value,
            "window_size": window_size,
            "session_id": session_id
        }

    def _process_continuous_stream(self, stream_data: List[Dict[str, Any]], config: Dict[str, Any], session_id: str) -> Dict[str, Any]:
        """Process stream continuously without windowing"""

        aggregation_functions = config.get("aggregation_functions", ["count"])

        # Process all data as single stream
        continuous_result = self._process_window(
            {"events": stream_data, "start_time": time.time(), "end_time": time.time()},
            aggregation_functions,
            config
        )

        return {
            "continuous_result": continuous_result,
            "events_processed": len(stream_data),
            "session_id": session_id
        }

    def _create_windows(self, stream_data: List[Dict[str, Any]], window_type: WindowType, window_size: int, session_id: str) -> Dict[str, Dict[str, Any]]:
        """Create windows based on type and size"""

        windows = {}

        if window_type == WindowType.TUMBLING:
            windows = self._create_tumbling_windows(stream_data, window_size, session_id)
        elif window_type == WindowType.SLIDING:
            windows = self._create_sliding_windows(stream_data, window_size, session_id)
        elif window_type == WindowType.COUNT_BASED:
            windows = self._create_count_based_windows(stream_data, window_size, session_id)
        else:
            # Default to tumbling windows
            windows = self._create_tumbling_windows(stream_data, window_size, session_id)

        # Update window metrics
        with self.window_lock:
            self.stream_metrics["windows_created"] += len(windows)
            self.processing_state["active_windows"] = len(windows)

        return windows

    def _create_tumbling_windows(self, stream_data: List[Dict[str, Any]], window_size: int, session_id: str) -> Dict[str, Dict[str, Any]]:
        """Create non-overlapping tumbling windows"""

        windows = {}
        current_time = time.time()

        # Group events by time windows
        for event in stream_data:
            event_time = event.get("timestamp", current_time)
            window_start = int(event_time // window_size) * window_size
            window_end = window_start + window_size

            window_id = f"{session_id}_tumbling_{window_start}_{window_end}"

            if window_id not in windows:
                windows[window_id] = {
                    "events": [],
                    "start_time": window_start,
                    "end_time": window_end,
                    "window_type": "tumbling"
                }

            windows[window_id]["events"].append(event)

        return windows

    def _create_sliding_windows(self, stream_data: List[Dict[str, Any]], window_size: int, session_id: str) -> Dict[str, Dict[str, Any]]:
        """Create overlapping sliding windows"""

        windows = {}
        current_time = time.time()
        slide_interval = window_size // 2  # 50% overlap

        # Create sliding windows
        for event in stream_data:
            event_time = event.get("timestamp", current_time)

            # Find all windows this event belongs to
            window_start = int(event_time // slide_interval) * slide_interval

            for offset in range(0, window_size, slide_interval):
                win_start = window_start - offset
                win_end = win_start + window_size

                if win_start <= event_time < win_end:
                    window_id = f"{session_id}_sliding_{win_start}_{win_end}"

                    if window_id not in windows:
                        windows[window_id] = {
                            "events": [],
                            "start_time": win_start,
                            "end_time": win_end,
                            "window_type": "sliding"
                        }

                    windows[window_id]["events"].append(event)

        return windows

    def _create_count_based_windows(self, stream_data: List[Dict[str, Any]], window_size: int, session_id: str) -> Dict[str, Dict[str, Any]]:
        """Create count-based windows"""

        windows = {}

        for i in range(0, len(stream_data), window_size):
            window_events = stream_data[i:i + window_size]
            window_id = f"{session_id}_count_{i}_{i + len(window_events)}"

            windows[window_id] = {
                "events": window_events,
                "start_time": time.time(),
                "end_time": time.time(),
                "window_type": "count_based",
                "event_count": len(window_events)
            }

        return windows

    def _process_window(self, window_data: Dict[str, Any], aggregation_functions: List[str], config: Dict[str, Any]) -> Dict[str, Any]:
        """Process individual window with aggregations"""

        events = window_data["events"]
        window_result = {
            "start_time": window_data["start_time"],
            "end_time": window_data["end_time"],
            "event_count": len(events),
            "aggregations": {}
        }

        # Apply aggregation functions
        for func_name in aggregation_functions:
            if func_name in self.aggregation_functions:
                aggregation_result = self.aggregation_functions[func_name](events, config)
                window_result["aggregations"][func_name] = aggregation_result

        return window_result

    def _sum_aggregation(self, events: List[Dict[str, Any]], config: Dict[str, Any]) -> Dict[str, Any]:
        """Sum aggregation function"""
        field = config.get("aggregation_field", "value")
        total = sum(event.get(field, 0) for event in events)
        return {"sum": total, "field": field}

    def _count_aggregation(self, events: List[Dict[str, Any]], config: Dict[str, Any]) -> Dict[str, Any]:
        """Count aggregation function"""
        return {"count": len(events)}

    def _average_aggregation(self, events: List[Dict[str, Any]], config: Dict[str, Any]) -> Dict[str, Any]:
        """Average aggregation function"""
        field = config.get("aggregation_field", "value")
        values = [event.get(field, 0) for event in events if field in event]
        average = sum(values) / len(values) if values else 0
        return {"average": average, "field": field, "sample_count": len(values)}

    def _min_aggregation(self, events: List[Dict[str, Any]], config: Dict[str, Any]) -> Dict[str, Any]:
        """Minimum aggregation function"""
        field = config.get("aggregation_field", "value")
        values = [event.get(field, 0) for event in events if field in event]
        minimum = min(values) if values else 0
        return {"min": minimum, "field": field}

    def _max_aggregation(self, events: List[Dict[str, Any]], config: Dict[str, Any]) -> Dict[str, Any]:
        """Maximum aggregation function"""
        field = config.get("aggregation_field", "value")
        values = [event.get(field, 0) for event in events if field in event]
        maximum = max(values) if values else 0
        return {"max": maximum, "field": field}

    def _distinct_count_aggregation(self, events: List[Dict[str, Any]], config: Dict[str, Any]) -> Dict[str, Any]:
        """Distinct count aggregation function"""
        field = config.get("aggregation_field", "value")
        distinct_values = set(event.get(field) for event in events if field in event)
        return {"distinct_count": len(distinct_values), "field": field}

    def _percentile_aggregation(self, events: List[Dict[str, Any]], config: Dict[str, Any]) -> Dict[str, Any]:
        """Percentile aggregation function"""
        field = config.get("aggregation_field", "value")
        percentile = config.get("percentile", 50)

        values = sorted([event.get(field, 0) for event in events if field in event])
        if not values:
            return {"percentile": 0, "field": field, "percentile_level": percentile}

        index = int((percentile / 100.0) * (len(values) - 1))
        percentile_value = values[index]

        return {"percentile": percentile_value, "field": field, "percentile_level": percentile}

    def _update_stream_metrics(self, events_processed: int, processing_time: float):
        """Update stream processing metrics"""

        with self.processing_lock:
            self.stream_metrics["events_processed"] += events_processed

            # Calculate events per second
            if processing_time > 0:
                current_eps = events_processed / processing_time
                # Exponential moving average
                alpha = 0.1
                self.stream_metrics["events_per_second"] = (
                    alpha * current_eps + (1 - alpha) * self.stream_metrics["events_per_second"]
                )

            # Update average latency
            latency_ms = processing_time * 1000
            alpha = 0.1
            self.stream_metrics["avg_latency_ms"] = (
                alpha * latency_ms + (1 - alpha) * self.stream_metrics["avg_latency_ms"]
            )

    def _get_performance_snapshot(self) -> Dict[str, Any]:
        """Get current performance metrics snapshot"""
        return {
            "events_per_second": self.stream_metrics["events_per_second"],
            "avg_latency_ms": self.stream_metrics["avg_latency_ms"],
            "active_windows": self.processing_state["active_windows"],
            "buffer_utilization": len(self.stream_buffer) / self.stream_buffer.maxlen,
            "processing_threads": self.processing_threads
        }

    def get_stream_metrics(self) -> Dict[str, Any]:
        """Get comprehensive stream metrics"""
        return self.stream_metrics.copy()

# Test real-time stream processor
stream_processor = RealTimeStreamProcessor("stream_proc_001", {
    "max_buffer_size": 5000,
    "processing_threads": 2,
    "checkpoint_interval": 30,
    "enable_backpressure": True
})

# Generate sample stream data
import random

sample_stream_data = []
current_time = time.time()

for i in range(100):
    event = {
        "id": f"event_{i}",
        "timestamp": current_time + i,
        "value": random.randint(1, 100),
        "category": random.choice(["A", "B", "C"]),
        "user_id": f"user_{random.randint(1, 10)}"
    }
    sample_stream_data.append(event)

# Test windowed processing
windowed_processing_data = {
    "stream_data": sample_stream_data,
    "processing_config": {
        "window_type": "tumbling",
        "window_size": 10,  # 10 second windows
        "aggregation_functions": ["count", "sum", "average"],
        "aggregation_field": "value"
    },
    "stream_metadata": {
        "source": "test_stream",
        "schema_version": "1.0"
    }
}

windowed_result = stream_processor.execute(windowed_processing_data)

# Test continuous processing
continuous_processing_data = {
    "stream_data": sample_stream_data[:50],
    "processing_config": {
        "streaming_mode": "continuous",
        "aggregation_functions": ["count", "distinct_count"],
        "aggregation_field": "category"
    }
}

continuous_result = stream_processor.execute(continuous_processing_data)

# Get stream metrics
stream_metrics = stream_processor.get_stream_metrics()
node_info = stream_processor.get_node_info()
```

This comprehensive custom nodes development guide demonstrates:

1. **Enterprise Base Node** - Foundation with caching, monitoring, and error recovery
2. **Data Transformation Node** - Advanced data processing with validation and statistics
3. **ML Inference Node** - AI/ML model integration with multiple framework support
4. **Real-time Stream Processor** - High-performance streaming with windowing and aggregation

Each node includes production-ready features like performance monitoring, caching, error handling, and comprehensive configuration validation.
