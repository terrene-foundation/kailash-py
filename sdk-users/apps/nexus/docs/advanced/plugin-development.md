# Plugin Development Guide

Extend Nexus's workflow-native platform with custom plugins for specialized functionality, third-party integrations, and domain-specific workflow nodes.

## Overview

Nexus's plugin architecture enables developers to create custom nodes, middleware components, authentication providers, and integration adapters. This guide covers plugin creation, registration, testing, and distribution through Nexus's extensible architecture.

## Plugin Architecture

### Plugin Types

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.base import BaseNode
from kailash.gateway.middleware import BaseMiddleware
from abc import ABC, abstractmethod
import time
import json
from enum import Enum
from typing import Dict, Any, List, Optional

app = Nexus()

class PluginType(Enum):
    """Available plugin types"""
    WORKFLOW_NODE = "workflow_node"
    MIDDLEWARE = "middleware"
    AUTH_PROVIDER = "auth_provider"
    DATA_CONNECTOR = "data_connector"
    INTEGRATION_ADAPTER = "integration_adapter"
    CUSTOM_EXECUTOR = "custom_executor"

class PluginManager:
    """Manage plugins within Nexus platform"""

    def __init__(self, nexus_app):
        self.app = nexus_app
        self.registered_plugins = {}
        self.plugin_configs = {}
        self.plugin_metadata = {}
        self.dependency_graph = {}
        self.plugin_health = {}

    def register_plugin(self, plugin_class, plugin_config=None):
        """Register a plugin with the Nexus platform"""

        plugin_instance = plugin_class(plugin_config or {})
        plugin_name = plugin_instance.get_plugin_name()

        # Validate plugin requirements
        if not self._validate_plugin(plugin_instance):
            raise ValueError(f"Plugin '{plugin_name}' failed validation")

        # Register plugin
        self.registered_plugins[plugin_name] = plugin_instance
        self.plugin_configs[plugin_name] = plugin_config or {}
        self.plugin_metadata[plugin_name] = plugin_instance.get_metadata()

        # Initialize plugin
        plugin_instance.initialize()

        # Update health status
        self.plugin_health[plugin_name] = {
            "status": "healthy",
            "registered_at": time.time(),
            "last_health_check": time.time()
        }

        return {
            "plugin_registered": plugin_name,
            "plugin_type": plugin_instance.get_plugin_type().value,
            "version": plugin_instance.get_version(),
            "capabilities": plugin_instance.get_capabilities()
        }

    def _validate_plugin(self, plugin_instance):
        """Validate plugin meets requirements"""

        required_methods = ["get_plugin_name", "get_plugin_type", "get_version", "initialize"]

        for method in required_methods:
            if not hasattr(plugin_instance, method):
                return False

        return True

    def get_plugin_registry(self):
        """Get registry of all registered plugins"""

        registry = {}

        for plugin_name, plugin in self.registered_plugins.items():
            registry[plugin_name] = {
                "type": plugin.get_plugin_type().value,
                "version": plugin.get_version(),
                "status": self.plugin_health.get(plugin_name, {}).get("status", "unknown"),
                "capabilities": plugin.get_capabilities(),
                "metadata": self.plugin_metadata.get(plugin_name, {})
            }

        return registry

plugin_manager = PluginManager(app)

# Example plugin registration
class SampleWorkflowPlugin:
    """Sample workflow node plugin"""

    def __init__(self, config):
        self.config = config
        self.plugin_name = "sample_workflow_plugin"
        self.version = "1.0.0"

    def get_plugin_name(self):
        return self.plugin_name

    def get_plugin_type(self):
        return PluginType.WORKFLOW_NODE

    def get_version(self):
        return self.version

    def get_capabilities(self):
        return ["data_processing", "custom_logic"]

    def get_metadata(self):
        return {
            "description": "Sample workflow plugin for demonstration",
            "author": "Nexus Team",
            "tags": ["sample", "demo"]
        }

    def initialize(self):
        """Initialize plugin resources"""
        pass

# Register sample plugin
registration = plugin_manager.register_plugin(SampleWorkflowPlugin, {"enable_logging": True})
```

### Custom Workflow Nodes

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.base import BaseNode
from abc import ABC, abstractmethod
import requests
import time
import hashlib
from typing import Dict, Any, Optional

app = Nexus()

class EnterpriseWorkflowNode(BaseNode):
    """Base class for enterprise workflow nodes"""

    def __init__(self, node_id: str, parameters: Dict[str, Any]):
        super().__init__(node_id, parameters)
        self.execution_metrics = {
            "total_executions": 0,
            "successful_executions": 0,
            "failed_executions": 0,
            "avg_execution_time": 0.0
        }
        self.plugin_config = parameters.get("plugin_config", {})
        self.enterprise_features = {
            "audit_logging": True,
            "performance_monitoring": True,
            "error_recovery": True,
            "caching": True
        }

    def execute(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute node with enterprise features"""

        start_time = time.time()

        try:
            # Pre-execution logging
            if self.enterprise_features["audit_logging"]:
                self._log_execution_start(data)

            # Check cache
            if self.enterprise_features["caching"]:
                cached_result = self._check_cache(data)
                if cached_result:
                    return cached_result

            # Execute business logic
            result = self._execute_business_logic(data)

            # Post-execution processing
            self._update_metrics(start_time, True)

            # Cache result
            if self.enterprise_features["caching"]:
                self._cache_result(data, result)

            # Log success
            if self.enterprise_features["audit_logging"]:
                self._log_execution_success(data, result)

            return result

        except Exception as e:
            # Error handling and recovery
            self._update_metrics(start_time, False)

            if self.enterprise_features["error_recovery"]:
                recovery_result = self._attempt_error_recovery(data, e)
                if recovery_result:
                    return recovery_result

            if self.enterprise_features["audit_logging"]:
                self._log_execution_error(data, e)

            raise e

    @abstractmethod
    def _execute_business_logic(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Implement business logic in subclasses"""
        pass

    def _log_execution_start(self, data: Dict[str, Any]):
        """Log execution start"""
        pass

    def _log_execution_success(self, data: Dict[str, Any], result: Dict[str, Any]):
        """Log successful execution"""
        pass

    def _log_execution_error(self, data: Dict[str, Any], error: Exception):
        """Log execution error"""
        pass

    def _check_cache(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Check for cached result"""
        return None

    def _cache_result(self, data: Dict[str, Any], result: Dict[str, Any]):
        """Cache execution result"""
        pass

    def _attempt_error_recovery(self, data: Dict[str, Any], error: Exception) -> Optional[Dict[str, Any]]:
        """Attempt to recover from error"""
        return None

    def _update_metrics(self, start_time: float, success: bool):
        """Update execution metrics"""

        execution_time = time.time() - start_time

        self.execution_metrics["total_executions"] += 1

        if success:
            self.execution_metrics["successful_executions"] += 1
        else:
            self.execution_metrics["failed_executions"] += 1

        # Update average execution time
        total_time = (self.execution_metrics["avg_execution_time"] *
                     (self.execution_metrics["total_executions"] - 1))
        self.execution_metrics["avg_execution_time"] = (
            (total_time + execution_time) / self.execution_metrics["total_executions"]
        )

    def get_execution_metrics(self) -> Dict[str, Any]:
        """Get node execution metrics"""
        return self.execution_metrics.copy()

class CustomAPICallNode(EnterpriseWorkflowNode):
    """Custom API call node with advanced features"""

    def __init__(self, node_id: str, parameters: Dict[str, Any]):
        super().__init__(node_id, parameters)
        self.api_config = {
            "base_url": parameters.get("base_url", ""),
            "timeout": parameters.get("timeout", 30),
            "retry_attempts": parameters.get("retry_attempts", 3),
            "retry_delay": parameters.get("retry_delay", 1),
            "auth_token": parameters.get("auth_token"),
            "custom_headers": parameters.get("headers", {}),
            "rate_limit": parameters.get("rate_limit", 100)  # requests per minute
        }
        self.request_cache = {}
        self.rate_limiter = {
            "requests": [],
            "limit": self.api_config["rate_limit"]
        }

    def _execute_business_logic(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute API call with advanced features"""

        # Extract API call parameters
        endpoint = data.get("endpoint", "")
        method = data.get("method", "GET").upper()
        payload = data.get("payload", {})
        query_params = data.get("query_params", {})

        # Build request URL
        url = f"{self.api_config['base_url'].rstrip('/')}/{endpoint.lstrip('/')}"

        # Check rate limiting
        if not self._check_rate_limit():
            raise Exception("Rate limit exceeded")

        # Prepare headers
        headers = self.api_config["custom_headers"].copy()
        if self.api_config["auth_token"]:
            headers["Authorization"] = f"Bearer {self.api_config['auth_token']}"

        # Make API call with retry logic
        response = self._make_request_with_retry(
            method, url, headers, payload, query_params
        )

        # Process response
        result = {
            "status_code": response.get("status_code", 0),
            "response_data": response.get("data", {}),
            "response_headers": response.get("headers", {}),
            "execution_time": response.get("execution_time", 0),
            "api_endpoint": endpoint,
            "success": response.get("status_code", 0) < 400
        }

        return result

    def _make_request_with_retry(self, method, url, headers, payload, query_params):
        """Make HTTP request with retry logic"""

        for attempt in range(self.api_config["retry_attempts"]):
            try:
                start_time = time.time()

                # Simulate HTTP request (in real implementation, use requests library)
                response = {
                    "status_code": 200,
                    "data": {"message": "API call successful", "timestamp": time.time()},
                    "headers": {"content-type": "application/json"},
                    "execution_time": time.time() - start_time
                }

                return response

            except Exception as e:
                if attempt == self.api_config["retry_attempts"] - 1:
                    raise e

                # Wait before retry
                time.sleep(self.api_config["retry_delay"] * (attempt + 1))

        raise Exception("Max retry attempts exceeded")

    def _check_rate_limit(self) -> bool:
        """Check if request is within rate limit"""

        current_time = time.time()
        minute_ago = current_time - 60

        # Clean old requests
        self.rate_limiter["requests"] = [
            req_time for req_time in self.rate_limiter["requests"]
            if req_time > minute_ago
        ]

        # Check limit
        if len(self.rate_limiter["requests"]) >= self.rate_limiter["limit"]:
            return False

        # Add current request
        self.rate_limiter["requests"].append(current_time)
        return True

    def _check_cache(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Check for cached API response"""

        # Create cache key
        cache_key = hashlib.md5(
            json.dumps(data, sort_keys=True).encode()
        ).hexdigest()

        if cache_key in self.request_cache:
            cached_entry = self.request_cache[cache_key]
            # Check if cache is still valid (5 minutes)
            if time.time() - cached_entry["timestamp"] < 300:
                return cached_entry["result"]

        return None

    def _cache_result(self, data: Dict[str, Any], result: Dict[str, Any]):
        """Cache API response"""

        cache_key = hashlib.md5(
            json.dumps(data, sort_keys=True).encode()
        ).hexdigest()

        self.request_cache[cache_key] = {
            "result": result,
            "timestamp": time.time()
        }

        # Limit cache size
        if len(self.request_cache) > 100:
            oldest_key = min(
                self.request_cache.keys(),
                key=lambda k: self.request_cache[k]["timestamp"]
            )
            del self.request_cache[oldest_key]

# Create workflow with custom node
workflow = WorkflowBuilder()

# Add custom API call node
workflow.add_node("CustomAPICallNode", "api_processor", {
    "base_url": "https://api.example.com",
    "auth_token": "your_api_token",
    "timeout": 30,
    "retry_attempts": 3,
    "rate_limit": 50
})

# Register workflow
app.register("custom-api-workflow", workflow)

# Test custom node
custom_node = CustomAPICallNode("test_node", {
    "base_url": "https://api.example.com",
    "auth_token": "test_token"
})

test_data = {
    "endpoint": "users/profile",
    "method": "GET",
    "query_params": {"include": "permissions"}
}

result = custom_node.execute(test_data)
```

### Plugin Middleware

```python
from nexus import Nexus
from kailash.gateway.middleware import BaseMiddleware
from fastapi import Request, Response
import time
import json
import hashlib
from typing import Callable, Dict, Any
from enum import Enum

app = Nexus()

class MiddlewareType(Enum):
    """Middleware execution types"""
    REQUEST = "request"
    RESPONSE = "response"
    ERROR = "error"
    WORKFLOW = "workflow"

class AdvancedLoggingMiddleware(BaseMiddleware):
    """Advanced logging middleware with structured logging"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.log_config = {
            "log_level": config.get("log_level", "INFO"),
            "include_request_body": config.get("include_request_body", False),
            "include_response_body": config.get("include_response_body", False),
            "log_sensitive_data": config.get("log_sensitive_data", False),
            "structured_format": config.get("structured_format", True),
            "performance_logging": config.get("performance_logging", True)
        }
        self.request_log = []
        self.sensitive_fields = {"password", "token", "secret", "key", "auth"}

    async def process_request(self, request: Request, call_next: Callable):
        """Process incoming request with advanced logging"""

        start_time = time.time()
        request_id = self._generate_request_id()

        # Log request
        request_log = {
            "request_id": request_id,
            "timestamp": start_time,
            "method": request.method,
            "url": str(request.url),
            "headers": dict(request.headers),
            "client_ip": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent"),
            "content_length": request.headers.get("content-length")
        }

        # Include request body if configured
        if self.log_config["include_request_body"]:
            body = await self._get_request_body(request)
            request_log["request_body"] = self._sanitize_sensitive_data(body)

        # Process request
        try:
            response = await call_next(request)

            # Calculate response time
            response_time = (time.time() - start_time) * 1000  # ms

            # Log response
            response_log = {
                "request_id": request_id,
                "status_code": response.status_code,
                "response_time_ms": response_time,
                "response_headers": dict(response.headers),
                "success": response.status_code < 400
            }

            # Include response body if configured
            if self.log_config["include_response_body"]:
                response_body = await self._get_response_body(response)
                response_log["response_body"] = self._sanitize_sensitive_data(response_body)

            # Store complete log entry
            complete_log = {**request_log, **response_log}
            self.request_log.append(complete_log)

            # Maintain log size
            if len(self.request_log) > 1000:
                self.request_log = self.request_log[-1000:]

            return response

        except Exception as e:
            # Log error
            error_log = {
                "request_id": request_id,
                "error": str(e),
                "error_type": type(e).__name__,
                "response_time_ms": (time.time() - start_time) * 1000
            }

            complete_log = {**request_log, **error_log}
            self.request_log.append(complete_log)

            raise e

    def _generate_request_id(self) -> str:
        """Generate unique request ID"""
        return hashlib.sha256(f"{time.time()}_{id(self)}".encode()).hexdigest()[:16]

    async def _get_request_body(self, request: Request) -> str:
        """Get request body safely"""
        try:
            body = await request.body()
            return body.decode("utf-8")
        except Exception:
            return ""

    async def _get_response_body(self, response: Response) -> str:
        """Get response body safely"""
        # This is simplified - in practice, you'd need to handle streaming responses
        return ""

    def _sanitize_sensitive_data(self, data: str) -> str:
        """Remove sensitive data from logs"""

        if not self.log_config["log_sensitive_data"]:
            try:
                parsed_data = json.loads(data)
                return self._recursive_sanitize(parsed_data)
            except json.JSONDecodeError:
                return data

        return data

    def _recursive_sanitize(self, obj):
        """Recursively sanitize sensitive fields"""

        if isinstance(obj, dict):
            sanitized = {}
            for key, value in obj.items():
                if any(sensitive in key.lower() for sensitive in self.sensitive_fields):
                    sanitized[key] = "[REDACTED]"
                else:
                    sanitized[key] = self._recursive_sanitize(value)
            return sanitized
        elif isinstance(obj, list):
            return [self._recursive_sanitize(item) for item in obj]
        else:
            return obj

    def get_request_analytics(self) -> Dict[str, Any]:
        """Get request analytics"""

        if not self.request_log:
            return {"total_requests": 0}

        total_requests = len(self.request_log)
        successful_requests = len([log for log in self.request_log if log.get("success", False)])

        response_times = [log.get("response_time_ms", 0) for log in self.request_log if "response_time_ms" in log]
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0

        return {
            "total_requests": total_requests,
            "successful_requests": successful_requests,
            "success_rate": (successful_requests / total_requests * 100) if total_requests > 0 else 0,
            "average_response_time_ms": avg_response_time,
            "error_rate": ((total_requests - successful_requests) / total_requests * 100) if total_requests > 0 else 0
        }

class CachingMiddleware(BaseMiddleware):
    """Intelligent caching middleware"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.cache_config = {
            "ttl_seconds": config.get("ttl_seconds", 300),  # 5 minutes
            "max_cache_size": config.get("max_cache_size", 1000),
            "cache_post_requests": config.get("cache_post_requests", False),
            "vary_headers": config.get("vary_headers", ["authorization", "user-agent"]),
            "cache_control_header": config.get("cache_control_header", True)
        }
        self.cache_storage = {}
        self.cache_stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0
        }

    async def process_request(self, request: Request, call_next: Callable):
        """Process request with intelligent caching"""

        # Check if request is cacheable
        if not self._is_cacheable(request):
            return await call_next(request)

        # Generate cache key
        cache_key = self._generate_cache_key(request)

        # Check cache
        cached_response = self._get_cached_response(cache_key)
        if cached_response:
            self.cache_stats["hits"] += 1
            return self._create_response_from_cache(cached_response)

        # Execute request
        response = await call_next(request)

        # Cache response if appropriate
        if self._should_cache_response(response):
            self._cache_response(cache_key, response)

        self.cache_stats["misses"] += 1
        return response

    def _is_cacheable(self, request: Request) -> bool:
        """Check if request is cacheable"""

        # Only cache GET requests by default
        if request.method != "GET" and not self.cache_config["cache_post_requests"]:
            return False

        # Don't cache requests with authorization unless specifically configured
        if "authorization" in request.headers and "authorization" not in self.cache_config["vary_headers"]:
            return False

        return True

    def _generate_cache_key(self, request: Request) -> str:
        """Generate cache key for request"""

        key_components = [
            request.method,
            str(request.url)
        ]

        # Include vary headers in cache key
        for header in self.cache_config["vary_headers"]:
            header_value = request.headers.get(header, "")
            key_components.append(f"{header}:{header_value}")

        cache_key = "|".join(key_components)
        return hashlib.md5(cache_key.encode()).hexdigest()

    def _get_cached_response(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get response from cache"""

        if cache_key in self.cache_storage:
            cached_entry = self.cache_storage[cache_key]

            # Check if cache entry is still valid
            if time.time() - cached_entry["timestamp"] < self.cache_config["ttl_seconds"]:
                return cached_entry
            else:
                # Remove expired entry
                del self.cache_storage[cache_key]

        return None

    def _should_cache_response(self, response: Response) -> bool:
        """Check if response should be cached"""

        # Only cache successful responses
        if response.status_code >= 400:
            return False

        # Check cache-control headers
        cache_control = response.headers.get("cache-control", "")
        if "no-cache" in cache_control or "no-store" in cache_control:
            return False

        return True

    def _cache_response(self, cache_key: str, response: Response):
        """Cache response"""

        # Evict old entries if cache is full
        if len(self.cache_storage) >= self.cache_config["max_cache_size"]:
            self._evict_oldest_entry()

        cached_entry = {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "timestamp": time.time(),
            "cache_key": cache_key
        }

        self.cache_storage[cache_key] = cached_entry

    def _evict_oldest_entry(self):
        """Evict oldest cache entry"""

        if self.cache_storage:
            oldest_key = min(
                self.cache_storage.keys(),
                key=lambda k: self.cache_storage[k]["timestamp"]
            )
            del self.cache_storage[oldest_key]
            self.cache_stats["evictions"] += 1

    def _create_response_from_cache(self, cached_entry: Dict[str, Any]):
        """Create response object from cached entry"""

        # This is simplified - in practice, you'd create a proper Response object
        return {
            "status_code": cached_entry["status_code"],
            "headers": cached_entry["headers"],
            "cached": True,
            "cache_age": time.time() - cached_entry["timestamp"]
        }

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""

        total_requests = self.cache_stats["hits"] + self.cache_stats["misses"]
        hit_rate = (self.cache_stats["hits"] / total_requests * 100) if total_requests > 0 else 0

        return {
            "cache_hits": self.cache_stats["hits"],
            "cache_misses": self.cache_stats["misses"],
            "cache_evictions": self.cache_stats["evictions"],
            "hit_rate_percent": hit_rate,
            "cached_entries": len(self.cache_storage),
            "cache_size_limit": self.cache_config["max_cache_size"]
        }

# Create middleware instances
logging_middleware = AdvancedLoggingMiddleware({
    "log_level": "INFO",
    "include_request_body": True,
    "performance_logging": True,
    "structured_format": True
})

caching_middleware = CachingMiddleware({
    "ttl_seconds": 600,  # 10 minutes
    "max_cache_size": 500,
    "cache_post_requests": False
})

# Get middleware analytics
logging_analytics = logging_middleware.get_request_analytics()
cache_stats = caching_middleware.get_cache_stats()
```

### Plugin Testing Framework

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder
import unittest
import time
import json
from typing import Dict, Any, List
from unittest.mock import Mock, patch

app = Nexus()

class PluginTestFramework:
    """Comprehensive testing framework for Nexus plugins"""

    def __init__(self, nexus_app):
        self.app = nexus_app
        self.test_results = []
        self.test_config = {
            "timeout_seconds": 30,
            "max_memory_mb": 512,
            "enable_performance_tests": True,
            "enable_stress_tests": True,
            "parallel_test_workers": 4
        }

    def test_plugin_functionality(self, plugin_class, test_cases: List[Dict[str, Any]]):
        """Test plugin functionality with multiple test cases"""

        test_results = {
            "plugin_name": plugin_class.__name__,
            "test_timestamp": time.time(),
            "test_cases": [],
            "overall_success": True,
            "performance_metrics": {}
        }

        for i, test_case in enumerate(test_cases):
            case_result = self._run_test_case(plugin_class, test_case, f"test_case_{i}")
            test_results["test_cases"].append(case_result)

            if not case_result["success"]:
                test_results["overall_success"] = False

        # Run performance tests
        if self.test_config["enable_performance_tests"]:
            perf_results = self._run_performance_tests(plugin_class, test_cases)
            test_results["performance_metrics"] = perf_results

        self.test_results.append(test_results)
        return test_results

    def _run_test_case(self, plugin_class, test_case: Dict[str, Any], case_name: str):
        """Run individual test case"""

        start_time = time.time()

        try:
            # Create plugin instance
            plugin_config = test_case.get("plugin_config", {})
            plugin_instance = plugin_class(plugin_config)

            # Initialize plugin
            plugin_instance.initialize()

            # Run test input
            test_input = test_case.get("input", {})
            expected_output = test_case.get("expected_output", {})

            # Execute plugin logic
            if hasattr(plugin_instance, "execute"):
                actual_output = plugin_instance.execute(test_input)
            else:
                actual_output = plugin_instance.process(test_input)

            # Validate output
            validation_result = self._validate_output(actual_output, expected_output)

            execution_time = time.time() - start_time

            return {
                "case_name": case_name,
                "success": validation_result["valid"],
                "execution_time": execution_time,
                "validation_details": validation_result,
                "actual_output": actual_output,
                "error": None
            }

        except Exception as e:
            execution_time = time.time() - start_time

            return {
                "case_name": case_name,
                "success": False,
                "execution_time": execution_time,
                "validation_details": {"valid": False, "errors": []},
                "actual_output": None,
                "error": str(e)
            }

    def _validate_output(self, actual: Any, expected: Any) -> Dict[str, Any]:
        """Validate plugin output against expected results"""

        validation_result = {
            "valid": True,
            "errors": [],
            "warnings": []
        }

        # Type validation
        if type(actual) != type(expected):
            validation_result["valid"] = False
            validation_result["errors"].append(
                f"Type mismatch: expected {type(expected)}, got {type(actual)}"
            )
            return validation_result

        # Dictionary validation
        if isinstance(expected, dict):
            for key, expected_value in expected.items():
                if key not in actual:
                    validation_result["valid"] = False
                    validation_result["errors"].append(f"Missing key: {key}")
                else:
                    nested_validation = self._validate_output(actual[key], expected_value)
                    if not nested_validation["valid"]:
                        validation_result["valid"] = False
                        validation_result["errors"].extend(nested_validation["errors"])

        # List validation
        elif isinstance(expected, list):
            if len(actual) != len(expected):
                validation_result["valid"] = False
                validation_result["errors"].append(
                    f"List length mismatch: expected {len(expected)}, got {len(actual)}"
                )
            else:
                for i, (actual_item, expected_item) in enumerate(zip(actual, expected)):
                    nested_validation = self._validate_output(actual_item, expected_item)
                    if not nested_validation["valid"]:
                        validation_result["valid"] = False
                        validation_result["errors"].extend(
                            [f"Index {i}: {error}" for error in nested_validation["errors"]]
                        )

        # Value validation
        else:
            if actual != expected:
                validation_result["valid"] = False
                validation_result["errors"].append(
                    f"Value mismatch: expected {expected}, got {actual}"
                )

        return validation_result

    def _run_performance_tests(self, plugin_class, test_cases: List[Dict[str, Any]]):
        """Run performance tests on plugin"""

        performance_metrics = {
            "avg_execution_time": 0.0,
            "min_execution_time": float("inf"),
            "max_execution_time": 0.0,
            "memory_usage": 0,
            "throughput_per_second": 0
        }

        if not test_cases:
            return performance_metrics

        execution_times = []

        # Run performance test iterations
        iterations = 100
        for i in range(iterations):
            test_case = test_cases[i % len(test_cases)]

            start_time = time.time()

            try:
                plugin_instance = plugin_class(test_case.get("plugin_config", {}))
                plugin_instance.initialize()

                if hasattr(plugin_instance, "execute"):
                    plugin_instance.execute(test_case.get("input", {}))
                else:
                    plugin_instance.process(test_case.get("input", {}))

                execution_time = time.time() - start_time
                execution_times.append(execution_time)

            except Exception:
                # Skip failed executions in performance test
                continue

        if execution_times:
            performance_metrics["avg_execution_time"] = sum(execution_times) / len(execution_times)
            performance_metrics["min_execution_time"] = min(execution_times)
            performance_metrics["max_execution_time"] = max(execution_times)
            performance_metrics["throughput_per_second"] = 1.0 / performance_metrics["avg_execution_time"]

        return performance_metrics

    def generate_test_report(self) -> Dict[str, Any]:
        """Generate comprehensive test report"""

        if not self.test_results:
            return {"error": "No test results available"}

        total_tests = len(self.test_results)
        successful_tests = len([r for r in self.test_results if r["overall_success"]])

        all_case_results = []
        for test_result in self.test_results:
            all_case_results.extend(test_result["test_cases"])

        total_cases = len(all_case_results)
        successful_cases = len([c for c in all_case_results if c["success"]])

        avg_execution_time = (
            sum(c["execution_time"] for c in all_case_results) / total_cases
            if total_cases > 0 else 0
        )

        report = {
            "test_summary": {
                "total_plugins_tested": total_tests,
                "successful_plugins": successful_tests,
                "plugin_success_rate": (successful_tests / total_tests * 100) if total_tests > 0 else 0,
                "total_test_cases": total_cases,
                "successful_test_cases": successful_cases,
                "case_success_rate": (successful_cases / total_cases * 100) if total_cases > 0 else 0,
                "average_execution_time": avg_execution_time
            },
            "detailed_results": self.test_results,
            "generated_at": time.time()
        }

        return report

# Example plugin for testing
class SampleTestPlugin:
    """Sample plugin for testing framework demonstration"""

    def __init__(self, config):
        self.config = config
        self.multiplier = config.get("multiplier", 2)

    def initialize(self):
        """Initialize plugin"""
        pass

    def execute(self, data):
        """Execute plugin logic"""

        input_value = data.get("value", 0)
        result = input_value * self.multiplier

        return {
            "result": result,
            "input_value": input_value,
            "multiplier": self.multiplier,
            "operation": "multiply"
        }

# Create test framework
test_framework = PluginTestFramework(app)

# Define test cases
test_cases = [
    {
        "plugin_config": {"multiplier": 2},
        "input": {"value": 5},
        "expected_output": {
            "result": 10,
            "input_value": 5,
            "multiplier": 2,
            "operation": "multiply"
        }
    },
    {
        "plugin_config": {"multiplier": 3},
        "input": {"value": 7},
        "expected_output": {
            "result": 21,
            "input_value": 7,
            "multiplier": 3,
            "operation": "multiply"
        }
    }
]

# Run plugin tests
test_results = test_framework.test_plugin_functionality(SampleTestPlugin, test_cases)

# Generate test report
test_report = test_framework.generate_test_report()
```

## Plugin Distribution

### Plugin Package Structure

```python
from nexus import Nexus
from pathlib import Path
import json
import tarfile
import zipfile
import hashlib
import time
from typing import Dict, Any, List

app = Nexus()

class PluginPackager:
    """Package plugins for distribution"""

    def __init__(self, nexus_app):
        self.app = nexus_app
        self.package_config = {
            "manifest_version": "1.0",
            "compression": "gzip",
            "include_tests": True,
            "include_docs": True,
            "verify_checksums": True
        }

    def create_plugin_package(self, plugin_info: Dict[str, Any], output_path: str):
        """Create distributable plugin package"""

        package_manifest = {
            "manifest_version": self.package_config["manifest_version"],
            "plugin": {
                "name": plugin_info["name"],
                "version": plugin_info["version"],
                "description": plugin_info.get("description", ""),
                "author": plugin_info.get("author", ""),
                "license": plugin_info.get("license", "MIT"),
                "homepage": plugin_info.get("homepage", ""),
                "repository": plugin_info.get("repository", ""),
                "keywords": plugin_info.get("keywords", []),
                "category": plugin_info.get("category", "general")
            },
            "requirements": {
                "nexus_version": plugin_info.get("min_nexus_version", "0.1.0"),
                "python_version": plugin_info.get("min_python_version", "3.8"),
                "dependencies": plugin_info.get("dependencies", []),
                "system_requirements": plugin_info.get("system_requirements", {})
            },
            "entry_points": {
                "main": plugin_info.get("main_module", ""),
                "nodes": plugin_info.get("node_classes", []),
                "middleware": plugin_info.get("middleware_classes", []),
                "auth_providers": plugin_info.get("auth_provider_classes", [])
            },
            "assets": {
                "source_files": plugin_info.get("source_files", []),
                "config_files": plugin_info.get("config_files", []),
                "test_files": plugin_info.get("test_files", []),
                "documentation": plugin_info.get("documentation_files", [])
            },
            "package_info": {
                "created_at": time.time(),
                "package_format": "nexus-plugin",
                "checksum": "",
                "file_count": 0,
                "package_size": 0
            }
        }

        # Create package
        package_path = self._create_package_archive(package_manifest, plugin_info, output_path)

        return {
            "package_created": True,
            "package_path": package_path,
            "manifest": package_manifest,
            "package_size": Path(package_path).stat().st_size if Path(package_path).exists() else 0
        }

    def _create_package_archive(self, manifest: Dict[str, Any], plugin_info: Dict[str, Any], output_path: str):
        """Create archive file with plugin contents"""

        # For demonstration, create a simple structure
        package_structure = {
            "manifest.json": json.dumps(manifest, indent=2),
            "README.md": f"# {plugin_info['name']}\\n\\n{plugin_info.get('description', '')}",
            "setup.py": self._generate_setup_py(plugin_info),
            "src/": {
                f"{plugin_info['name']}.py": "# Plugin source code",
                "__init__.py": ""
            },
            "tests/": {
                "test_plugin.py": "# Plugin tests",
                "__init__.py": ""
            },
            "docs/": {
                "usage.md": "# Usage Documentation",
                "api.md": "# API Reference"
            }
        }

        # Update manifest with file info
        manifest["package_info"]["file_count"] = self._count_files(package_structure)
        manifest["package_info"]["checksum"] = self._calculate_checksum(package_structure)

        return output_path

    def _generate_setup_py(self, plugin_info: Dict[str, Any]) -> str:
        """Generate setup.py for plugin installation"""

        setup_content = f'''
from setuptools import setup, find_packages

setup(
    name="{plugin_info['name']}",
    version="{plugin_info['version']}",
    description="{plugin_info.get('description', '')}",
    author="{plugin_info.get('author', '')}",
    packages=find_packages(),
    install_requires={plugin_info.get('dependencies', [])},
    python_requires=">={plugin_info.get('min_python_version', '3.8')}",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
    ],
)
'''
        return setup_content.strip()

    def _count_files(self, structure, count=0):
        """Count files in package structure"""

        for key, value in structure.items():
            if isinstance(value, dict):
                count = self._count_files(value, count)
            else:
                count += 1

        return count

    def _calculate_checksum(self, structure) -> str:
        """Calculate checksum for package contents"""

        content_hash = hashlib.sha256()

        def add_to_hash(obj):
            if isinstance(obj, dict):
                for key in sorted(obj.keys()):
                    content_hash.update(key.encode())
                    add_to_hash(obj[key])
            else:
                content_hash.update(str(obj).encode())

        add_to_hash(structure)
        return content_hash.hexdigest()

class PluginRegistry:
    """Plugin registry for discovery and installation"""

    def __init__(self, nexus_app):
        self.app = nexus_app
        self.registry_config = {
            "registry_url": "https://plugins.nexus.ai/registry",
            "cache_timeout": 3600,  # 1 hour
            "verify_signatures": True,
            "auto_update_check": True
        }
        self.plugin_cache = {}
        self.installed_plugins = {}

    def search_plugins(self, query: str, category: str = None) -> List[Dict[str, Any]]:
        """Search for plugins in registry"""

        # Simulate plugin search results
        sample_plugins = [
            {
                "name": "advanced-auth-plugin",
                "version": "1.2.0",
                "description": "Advanced authentication and authorization plugin",
                "author": "Nexus Security Team",
                "category": "security",
                "downloads": 15420,
                "rating": 4.8,
                "last_updated": time.time() - 86400 * 7,  # 1 week ago
                "tags": ["auth", "security", "oauth", "saml"],
                "nexus_compatibility": ">=0.6.0"
            },
            {
                "name": "data-pipeline-plugin",
                "version": "2.1.3",
                "description": "High-performance data pipeline processing nodes",
                "author": "DataFlow Solutions",
                "category": "data",
                "downloads": 8950,
                "rating": 4.6,
                "last_updated": time.time() - 86400 * 3,  # 3 days ago
                "tags": ["data", "pipeline", "etl", "streaming"],
                "nexus_compatibility": ">=0.5.0"
            },
            {
                "name": "ml-inference-plugin",
                "version": "1.0.8",
                "description": "Machine learning model inference and deployment",
                "author": "AI Labs",
                "category": "ml",
                "downloads": 12300,
                "rating": 4.9,
                "last_updated": time.time() - 86400 * 2,  # 2 days ago
                "tags": ["ml", "ai", "inference", "models"],
                "nexus_compatibility": ">=0.6.5"
            }
        ]

        # Filter by query and category
        results = []
        for plugin in sample_plugins:
            if query.lower() in plugin["name"].lower() or query.lower() in plugin["description"].lower():
                if category is None or plugin["category"] == category:
                    results.append(plugin)

        return results

    def install_plugin(self, plugin_name: str, version: str = "latest") -> Dict[str, Any]:
        """Install plugin from registry"""

        installation_result = {
            "plugin_name": plugin_name,
            "version": version,
            "installation_status": "success",
            "installed_at": time.time(),
            "dependencies_installed": [],
            "installation_log": []
        }

        # Simulate installation process
        installation_steps = [
            "Downloading plugin package",
            "Verifying package integrity",
            "Checking dependencies",
            "Installing plugin files",
            "Registering plugin with Nexus",
            "Running post-installation tests"
        ]

        for step in installation_steps:
            installation_result["installation_log"].append({
                "step": step,
                "status": "completed",
                "timestamp": time.time()
            })

        # Add to installed plugins
        self.installed_plugins[plugin_name] = {
            "version": version,
            "installed_at": time.time(),
            "status": "active"
        }

        return installation_result

    def list_installed_plugins(self) -> Dict[str, Any]:
        """List all installed plugins"""

        return {
            "installed_plugins": self.installed_plugins,
            "total_count": len(self.installed_plugins),
            "registry_info": {
                "last_updated": time.time(),
                "registry_url": self.registry_config["registry_url"]
            }
        }

# Create plugin tools
packager = PluginPackager(app)
registry = PluginRegistry(app)

# Example plugin packaging
plugin_info = {
    "name": "sample-workflow-plugin",
    "version": "1.0.0",
    "description": "Sample workflow plugin for demonstration",
    "author": "Nexus Team",
    "license": "MIT",
    "dependencies": ["requests>=2.25.0"],
    "source_files": ["src/sample_plugin.py"],
    "test_files": ["tests/test_sample.py"]
}

package_result = packager.create_plugin_package(plugin_info, "/tmp/sample-plugin.nxp")

# Example plugin search and installation
search_results = registry.search_plugins("auth", "security")
installation_result = registry.install_plugin("advanced-auth-plugin", "1.2.0")
installed_plugins = registry.list_installed_plugins()
```

This comprehensive plugin development guide provides:

1. **Plugin Architecture** - Core plugin system with type management and registry
2. **Custom Workflow Nodes** - Enterprise-grade custom nodes with advanced features
3. **Plugin Middleware** - Request/response middleware with logging and caching
4. **Testing Framework** - Comprehensive testing tools for plugin validation
5. **Plugin Distribution** - Packaging and registry system for plugin distribution

All examples demonstrate real plugin development patterns with production-ready features like error handling, performance monitoring, caching, and comprehensive testing.
