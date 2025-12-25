"""Health check node for monitoring service availability.

This module provides comprehensive health checking capabilities for various
services including HTTP endpoints, databases, and custom health checks.
"""

import asyncio
import time
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import aiohttp
import asyncpg
from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode
from kailash.sdk_exceptions import NodeExecutionError


class HealthStatus(Enum):
    """Health check status values."""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


class ServiceType(Enum):
    """Types of services that can be health checked."""

    HTTP = "http"
    DATABASE = "database"
    REDIS = "redis"
    CUSTOM = "custom"


@register_node()
class HealthCheckNode(AsyncNode):
    """Node for performing health checks on various services.

    This node provides comprehensive health checking capabilities including:
    - HTTP endpoint health checks with configurable methods and status codes
    - Database connectivity verification with query execution
    - Redis connection and operation verification
    - Custom health check function execution
    - Configurable timeouts and retries
    - Health status aggregation for multiple services
    - Detailed latency measurements

    Design Purpose:
    - Monitor service availability and performance
    - Enable proactive issue detection
    - Support various service types and protocols
    - Provide detailed health metrics for observability

    Examples:
        >>> # HTTP health check
        >>> health_checker = HealthCheckNode()
        >>> result = await health_checker.execute(
        ...     services=[{
        ...         "name": "api",
        ...         "type": "http",
        ...         "url": "https://api.example.com/health",
        ...         "method": "GET",
        ...         "expected_status": [200, 204]
        ...     }]
        ... )

        >>> # Database health check
        >>> result = await health_checker.execute(
        ...     services=[{
        ...         "name": "postgres",
        ...         "type": "database",
        ...         "connection_string": "postgresql://user:pass@localhost/db",
        ...         "test_query": "SELECT 1"
        ...     }]
        ... )
    """

    def __init__(self, **kwargs):
        """Initialize the health check node."""
        super().__init__(**kwargs)
        self.logger.info(f"Initialized HealthCheckNode: {self.id}")

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define the parameters this node accepts."""
        return {
            "services": NodeParameter(
                name="services",
                type=list,
                required=True,
                description="List of services to health check",
            ),
            "timeout": NodeParameter(
                name="timeout",
                type=float,
                required=False,
                default=30.0,
                description="Timeout in seconds for each health check",
            ),
            "parallel": NodeParameter(
                name="parallel",
                type=bool,
                required=False,
                default=True,
                description="Whether to run health checks in parallel",
            ),
            "fail_fast": NodeParameter(
                name="fail_fast",
                type=bool,
                required=False,
                default=False,
                description="Stop checking on first failure",
            ),
            "retries": NodeParameter(
                name="retries",
                type=int,
                required=False,
                default=3,
                description="Number of retries for failed checks",
            ),
            "retry_delay": NodeParameter(
                name="retry_delay",
                type=float,
                required=False,
                default=1.0,
                description="Delay between retries in seconds",
            ),
        }

    def get_output_schema(self) -> Dict[str, NodeParameter]:
        """Define the output schema for this node."""
        return {
            "overall_status": NodeParameter(
                name="overall_status",
                type=str,
                description="Overall health status (healthy/unhealthy/degraded)",
            ),
            "services": NodeParameter(
                name="services",
                type=dict,
                description="Health status for each service",
            ),
            "healthy_count": NodeParameter(
                name="healthy_count",
                type=int,
                description="Number of healthy services",
            ),
            "unhealthy_count": NodeParameter(
                name="unhealthy_count",
                type=int,
                description="Number of unhealthy services",
            ),
            "total_latency": NodeParameter(
                name="total_latency",
                type=float,
                description="Total time taken for all health checks",
            ),
            "timestamp": NodeParameter(
                name="timestamp",
                type=str,
                description="ISO timestamp of health check execution",
            ),
        }

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Execute health checks on configured services."""
        services = kwargs["services"]
        timeout = kwargs.get("timeout", 30.0)
        parallel = kwargs.get("parallel", True)
        fail_fast = kwargs.get("fail_fast", False)
        retries = kwargs.get("retries", 3)
        retry_delay = kwargs.get("retry_delay", 1.0)

        start_time = time.time()
        results = {}

        try:
            if parallel:
                # Run health checks in parallel
                tasks = []
                for service in services:
                    task = self._check_service_with_retry(
                        service, timeout, retries, retry_delay
                    )
                    tasks.append(task)

                # Use gather with return_exceptions to handle failures
                check_results = await asyncio.gather(*tasks, return_exceptions=True)

                # Process results
                for service, result in zip(services, check_results):
                    if isinstance(result, Exception):
                        results[service["name"]] = {
                            "status": HealthStatus.UNHEALTHY.value,
                            "error": str(result),
                            "latency": None,
                        }
                    else:
                        results[service["name"]] = result
            else:
                # Run health checks sequentially
                for service in services:
                    try:
                        result = await self._check_service_with_retry(
                            service, timeout, retries, retry_delay
                        )
                        results[service["name"]] = result

                        if (
                            fail_fast
                            and result["status"] == HealthStatus.UNHEALTHY.value
                        ):
                            break
                    except Exception as e:
                        results[service["name"]] = {
                            "status": HealthStatus.UNHEALTHY.value,
                            "error": str(e),
                            "latency": None,
                        }
                        if fail_fast:
                            break

            # Calculate overall status
            healthy_count = sum(
                1 for r in results.values() if r["status"] == HealthStatus.HEALTHY.value
            )
            unhealthy_count = sum(
                1
                for r in results.values()
                if r["status"] == HealthStatus.UNHEALTHY.value
            )

            if unhealthy_count == 0:
                overall_status = HealthStatus.HEALTHY.value
            elif healthy_count == 0:
                overall_status = HealthStatus.UNHEALTHY.value
            else:
                overall_status = HealthStatus.DEGRADED.value

            total_latency = time.time() - start_time

            return {
                "overall_status": overall_status,
                "services": results,
                "healthy_count": healthy_count,
                "unhealthy_count": unhealthy_count,
                "total_latency": total_latency,
                "timestamp": datetime.now(UTC).isoformat(),
            }

        except Exception as e:
            self.logger.error(f"Health check failed: {str(e)}")
            raise NodeExecutionError(f"Health check execution failed: {str(e)}")

    async def _check_service_with_retry(
        self, service: Dict[str, Any], timeout: float, retries: int, retry_delay: float
    ) -> Dict[str, Any]:
        """Check a service with retry logic."""
        last_error = None

        for attempt in range(retries):
            try:
                return await self._check_service(service, timeout)
            except Exception as e:
                last_error = e
                if attempt < retries - 1:
                    await asyncio.sleep(retry_delay)
                    self.logger.debug(
                        f"Retrying health check for {service['name']} "
                        f"(attempt {attempt + 2}/{retries})"
                    )

        # All retries failed
        return {
            "status": HealthStatus.UNHEALTHY.value,
            "error": str(last_error),
            "latency": None,
            "retries": retries,
        }

    async def _check_service(
        self, service: Dict[str, Any], timeout: float
    ) -> Dict[str, Any]:
        """Check a single service health."""
        service_type = ServiceType(service.get("type", "http"))
        start_time = time.time()

        try:
            if service_type == ServiceType.HTTP:
                result = await self._check_http_service(service, timeout)
            elif service_type == ServiceType.DATABASE:
                result = await self._check_database_service(service, timeout)
            elif service_type == ServiceType.REDIS:
                result = await self._check_redis_service(service, timeout)
            elif service_type == ServiceType.CUSTOM:
                result = await self._check_custom_service(service, timeout)
            else:
                raise ValueError(f"Unsupported service type: {service_type}")

            latency = time.time() - start_time
            result["latency"] = latency
            return result

        except asyncio.TimeoutError:
            return {
                "status": HealthStatus.UNHEALTHY.value,
                "error": f"Health check timed out after {timeout}s",
                "latency": timeout,
            }
        except Exception as e:
            return {
                "status": HealthStatus.UNHEALTHY.value,
                "error": str(e),
                "latency": time.time() - start_time,
            }

    async def _check_http_service(
        self, service: Dict[str, Any], timeout: float
    ) -> Dict[str, Any]:
        """Check HTTP endpoint health."""
        url = service["url"]
        method = service.get("method", "GET").upper()
        expected_status = service.get("expected_status", [200])
        headers = service.get("headers", {})

        if isinstance(expected_status, int):
            expected_status = [expected_status]

        async with aiohttp.ClientSession() as session:
            async with session.request(
                method=method,
                url=url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as response:
                if response.status in expected_status:
                    return {
                        "status": HealthStatus.HEALTHY.value,
                        "status_code": response.status,
                        "response_time": response.headers.get("X-Response-Time"),
                    }
                else:
                    return {
                        "status": HealthStatus.UNHEALTHY.value,
                        "status_code": response.status,
                        "error": f"Unexpected status code: {response.status}",
                    }

    async def _check_database_service(
        self, service: Dict[str, Any], timeout: float
    ) -> Dict[str, Any]:
        """Check database health."""
        connection_string = service["connection_string"]
        test_query = service.get("test_query", "SELECT 1")

        try:
            conn = await asyncio.wait_for(
                asyncpg.connect(connection_string), timeout=timeout
            )

            try:
                # Execute test query
                result = await asyncio.wait_for(
                    conn.fetchval(test_query), timeout=timeout
                )

                return {
                    "status": HealthStatus.HEALTHY.value,
                    "query_result": result,
                }
            finally:
                await conn.close()

        except Exception as e:
            return {
                "status": HealthStatus.UNHEALTHY.value,
                "error": f"Database check failed: {str(e)}",
            }

    async def _check_redis_service(
        self, service: Dict[str, Any], timeout: float
    ) -> Dict[str, Any]:
        """Check Redis health."""
        try:
            import redis.asyncio as redis

            redis_url = service.get("url", "redis://localhost:6379")

            client = redis.from_url(
                redis_url, socket_connect_timeout=timeout, socket_timeout=timeout
            )

            try:
                # Ping Redis
                pong = await client.ping()

                if pong:
                    return {"status": HealthStatus.HEALTHY.value}
                else:
                    return {
                        "status": HealthStatus.UNHEALTHY.value,
                        "error": "Redis ping failed",
                    }
            finally:
                await client.close()

        except ImportError:
            return {
                "status": HealthStatus.UNHEALTHY.value,
                "error": "Redis client not installed (pip install redis)",
            }
        except Exception as e:
            return {
                "status": HealthStatus.UNHEALTHY.value,
                "error": f"Redis check failed: {str(e)}",
            }

    async def _check_custom_service(
        self, service: Dict[str, Any], timeout: float
    ) -> Dict[str, Any]:
        """Check custom service using provided function."""
        check_function = service.get("check_function")

        if not check_function or not callable(check_function):
            return {
                "status": HealthStatus.UNHEALTHY.value,
                "error": "No valid check_function provided",
            }

        try:
            # Run custom check function with timeout
            if asyncio.iscoroutinefunction(check_function):
                result = await asyncio.wait_for(check_function(), timeout=timeout)
            else:
                # Run sync function in executor
                loop = asyncio.get_event_loop()
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, check_function), timeout=timeout
                )

            # Custom function should return dict with status
            if isinstance(result, dict) and "status" in result:
                return result
            elif result:
                return {"status": HealthStatus.HEALTHY.value, "result": result}
            else:
                return {"status": HealthStatus.UNHEALTHY.value, "result": result}

        except Exception as e:
            return {
                "status": HealthStatus.UNHEALTHY.value,
                "error": f"Custom check failed: {str(e)}",
            }
