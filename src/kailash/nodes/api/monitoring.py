"""Monitoring and health check nodes for system observability."""

import asyncio
import socket
import subprocess
import time
from datetime import UTC, datetime
from typing import Any

import requests

from kailash.nodes.base import Node, NodeParameter, register_node


@register_node()
class APIHealthCheckNode(Node):
    """
    Performs health checks on various system components and services.

    This node provides comprehensive health monitoring capabilities for
    distributed systems, replacing DataTransformer with embedded Python code
    for monitoring tasks. It supports HTTP endpoints, TCP ports, databases,
    file systems, and custom health check commands.

    Design Philosophy:
        Modern distributed systems require robust health monitoring. This node
        provides a declarative way to define health checks without writing
        custom code in DataTransformer nodes. It standardizes health check
        patterns and provides consistent output formats.

    Upstream Dependencies:
        - Configuration nodes with endpoint definitions
        - Service discovery nodes
        - Timer nodes for scheduled checks
        - Alert threshold nodes

    Downstream Consumers:
        - Alert generation nodes
        - Dashboard visualization nodes
        - Logging and metrics nodes
        - Auto-scaling decision nodes
        - Incident response workflows

    Configuration:
        - Target endpoints and services
        - Check types and parameters
        - Timeout and retry settings
        - Success/failure criteria
        - Alert thresholds

    Implementation Details:
        - Parallel execution of multiple checks
        - Proper timeout handling
        - Retry logic with exponential backoff
        - Structured output with metrics
        - Support for various check types

    Error Handling:
        - Graceful handling of network failures
        - Timeout management
        - Invalid configuration detection
        - Partial failure reporting

    Side Effects:
        - Network requests to target systems
        - File system access for disk checks
        - Process execution for custom commands
        - Minimal impact design

    Examples:
        >>> # HTTP endpoint health checks
        >>> health_check = HealthCheckNode(
        ...     targets=[
        ...         {'type': 'http', 'url': 'https://api.example.com/health'},
        ...         {'type': 'http', 'url': 'https://app.example.com/status'}
        ...     ],
        ...     timeout=30
        ... )
        >>> result = health_check.execute()
        >>> assert 'health_results' in result
        >>> assert result['summary']['total_checks'] == 2
        >>>
        >>> # Mixed health checks
        >>> health_check = HealthCheckNode(
        ...     targets=[
        ...         {'type': 'tcp', 'host': 'database.example.com', 'port': 5432},
        ...         {'type': 'disk', 'path': '/var/log', 'threshold': 80},
        ...         {'type': 'command', 'command': 'systemctl is-active nginx'}
        ...     ]
        ... )
        >>> result = health_check.execute()
        >>> assert 'health_results' in result
    """

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "targets": NodeParameter(
                name="targets",
                type=list,
                required=True,
                description="List of health check targets with type and configuration",
            ),
            "timeout": NodeParameter(
                name="timeout",
                type=int,
                required=False,
                default=30,
                description="Timeout in seconds for each health check",
            ),
            "retries": NodeParameter(
                name="retries",
                type=int,
                required=False,
                default=2,
                description="Number of retry attempts for failed checks",
            ),
            "parallel": NodeParameter(
                name="parallel",
                type=bool,
                required=False,
                default=True,
                description="Execute health checks in parallel",
            ),
            "include_metrics": NodeParameter(
                name="include_metrics",
                type=bool,
                required=False,
                default=True,
                description="Include performance metrics in results",
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        targets = kwargs["targets"]
        timeout = kwargs.get("timeout", 30)
        retries = kwargs.get("retries", 2)
        parallel = kwargs.get("parallel", True)
        include_metrics = kwargs.get("include_metrics", True)

        start_time = time.time()

        if parallel:
            # Use asyncio for parallel execution
            results = asyncio.run(
                self._run_checks_parallel(targets, timeout, retries, include_metrics)
            )
        else:
            # Sequential execution
            results = self._run_checks_sequential(
                targets, timeout, retries, include_metrics
            )

        execution_time = time.time() - start_time

        # Generate summary
        summary = self._generate_summary(results, execution_time)

        return {
            "health_results": results,
            "summary": summary,
            "check_count": len(results),
            "healthy_count": len([r for r in results if r["status"] == "healthy"]),
            "unhealthy_count": len([r for r in results if r["status"] == "unhealthy"]),
            "execution_time": execution_time,
            "timestamp": datetime.now(UTC).isoformat() + "Z",
        }

    async def _run_checks_parallel(
        self, targets: list[dict], timeout: int, retries: int, include_metrics: bool
    ) -> list[dict[str, Any]]:
        """Run health checks in parallel using asyncio."""

        async def run_single_check(target):
            return await asyncio.get_event_loop().run_in_executor(
                None,
                self._perform_health_check,
                target,
                timeout,
                retries,
                include_metrics,
            )

        tasks = [run_single_check(target) for target in targets]
        return await asyncio.gather(*tasks, return_exceptions=True)

    def _run_checks_sequential(
        self, targets: list[dict], timeout: int, retries: int, include_metrics: bool
    ) -> list[dict[str, Any]]:
        """Run health checks sequentially."""
        return [
            self._perform_health_check(target, timeout, retries, include_metrics)
            for target in targets
        ]

    def _perform_health_check(
        self, target: dict, timeout: int, retries: int, include_metrics: bool
    ) -> dict[str, Any]:
        """Perform a single health check with retry logic."""

        check_type = target.get("type", "unknown")
        check_id = target.get("id", f"{check_type}_{hash(str(target)) % 10000}")

        for attempt in range(retries + 1):
            try:
                start_time = time.time()

                if check_type == "http":
                    result = self._check_http(target, timeout)
                elif check_type == "tcp":
                    result = self._check_tcp(target, timeout)
                elif check_type == "disk":
                    result = self._check_disk(target)
                elif check_type == "command":
                    result = self._check_command(target, timeout)
                elif check_type == "database":
                    result = self._check_database(target, timeout)
                else:
                    result = {
                        "status": "unhealthy",
                        "message": f"Unknown check type: {check_type}",
                        "details": {},
                    }

                # Add timing information
                response_time = time.time() - start_time
                result["response_time"] = response_time
                result["attempt"] = attempt + 1
                result["check_id"] = check_id
                result["check_type"] = check_type
                result["target"] = target
                result["timestamp"] = datetime.now(UTC).isoformat() + "Z"

                # If successful, return immediately
                if result["status"] == "healthy":
                    return result

            except Exception as e:
                if attempt == retries:  # Last attempt
                    return {
                        "check_id": check_id,
                        "check_type": check_type,
                        "target": target,
                        "status": "unhealthy",
                        "message": f"Health check failed after {retries + 1} attempts: {str(e)}",
                        "details": {"error": str(e), "error_type": type(e).__name__},
                        "response_time": time.time() - start_time,
                        "attempt": attempt + 1,
                        "timestamp": datetime.now(UTC).isoformat() + "Z",
                    }

                # Wait before retry (exponential backoff)
                time.sleep(min(2**attempt, 10))

        return result

    def _check_http(self, target: dict, timeout: int) -> dict[str, Any]:
        """Perform HTTP health check."""
        url = target["url"]
        expected_status = target.get("expected_status", 200)
        expected_content = target.get("expected_content")
        headers = target.get("headers", {})

        response = requests.get(url, timeout=timeout, headers=headers)

        # Check status code
        if response.status_code != expected_status:
            return {
                "status": "unhealthy",
                "message": f"HTTP status {response.status_code}, expected {expected_status}",
                "details": {
                    "status_code": response.status_code,
                    "response_size": len(response.content),
                    "url": url,
                },
            }

        # Check content if specified
        if expected_content and expected_content not in response.text:
            return {
                "status": "unhealthy",
                "message": f"Expected content '{expected_content}' not found in response",
                "details": {
                    "status_code": response.status_code,
                    "response_size": len(response.content),
                    "url": url,
                },
            }

        return {
            "status": "healthy",
            "message": f"HTTP check successful: {response.status_code}",
            "details": {
                "status_code": response.status_code,
                "response_size": len(response.content),
                "url": url,
            },
        }

    def _check_tcp(self, target: dict, timeout: int) -> dict[str, Any]:
        """Perform TCP port connectivity check."""
        host = target["host"]
        port = target["port"]

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)

        try:
            result = sock.connect_ex((host, port))
            if result == 0:
                return {
                    "status": "healthy",
                    "message": f"TCP connection successful to {host}:{port}",
                    "details": {"host": host, "port": port},
                }
            else:
                return {
                    "status": "unhealthy",
                    "message": f"TCP connection failed to {host}:{port}",
                    "details": {"host": host, "port": port, "error_code": result},
                }
        finally:
            sock.close()

    def _check_disk(self, target: dict) -> dict[str, Any]:
        """Perform disk space check."""
        import shutil

        path = target["path"]
        threshold = target.get("threshold", 90)  # Default 90% threshold

        try:
            total, used, free = shutil.disk_usage(path)
            usage_percent = (used / total) * 100

            if usage_percent > threshold:
                return {
                    "status": "unhealthy",
                    "message": f"Disk usage {usage_percent:.1f}% exceeds threshold {threshold}%",
                    "details": {
                        "path": path,
                        "usage_percent": usage_percent,
                        "threshold": threshold,
                        "total_gb": total / (1024**3),
                        "used_gb": used / (1024**3),
                        "free_gb": free / (1024**3),
                    },
                }
            else:
                return {
                    "status": "healthy",
                    "message": f"Disk usage {usage_percent:.1f}% within threshold",
                    "details": {
                        "path": path,
                        "usage_percent": usage_percent,
                        "threshold": threshold,
                        "total_gb": total / (1024**3),
                        "used_gb": used / (1024**3),
                        "free_gb": free / (1024**3),
                    },
                }
        except Exception as e:
            return {
                "status": "unhealthy",
                "message": f"Disk check failed: {str(e)}",
                "details": {"path": path, "error": str(e)},
            }

    def _check_command(self, target: dict, timeout: int) -> dict[str, Any]:
        """Perform custom command health check."""
        command = target["command"]
        expected_exit_code = target.get("expected_exit_code", 0)

        try:
            result = subprocess.run(
                command,
                shell=True,
                timeout=timeout,
                capture_output=True,
                text=True,
            )

            if result.returncode == expected_exit_code:
                return {
                    "status": "healthy",
                    "message": f"Command succeeded with exit code {result.returncode}",
                    "details": {
                        "command": command,
                        "exit_code": result.returncode,
                        "stdout": result.stdout.strip(),
                        "stderr": result.stderr.strip(),
                    },
                }
            else:
                return {
                    "status": "unhealthy",
                    "message": f"Command failed with exit code {result.returncode}",
                    "details": {
                        "command": command,
                        "exit_code": result.returncode,
                        "expected_exit_code": expected_exit_code,
                        "stdout": result.stdout.strip(),
                        "stderr": result.stderr.strip(),
                    },
                }
        except subprocess.TimeoutExpired:
            return {
                "status": "unhealthy",
                "message": f"Command timed out after {timeout} seconds",
                "details": {"command": command, "timeout": timeout},
            }

    def _check_database(self, target: dict, timeout: int) -> dict[str, Any]:
        """Perform database connectivity check."""
        # This is a simplified example - in production, you'd use actual database drivers
        db_type = target.get("db_type", "postgresql")
        host = target["host"]
        port = target.get("port", 5432 if db_type == "postgresql" else 3306)

        # For now, just check TCP connectivity
        # In a real implementation, you'd use database-specific health checks
        return self._check_tcp({"host": host, "port": port}, timeout)

    def _generate_summary(
        self, results: list[dict], execution_time: float
    ) -> dict[str, Any]:
        """Generate summary statistics from health check results."""
        total_checks = len(results)
        healthy_checks = len([r for r in results if r.get("status") == "healthy"])
        unhealthy_checks = total_checks - healthy_checks

        # Calculate average response time
        response_times = [
            r.get("response_time", 0) for r in results if "response_time" in r
        ]
        avg_response_time = (
            sum(response_times) / len(response_times) if response_times else 0
        )

        # Group by check type
        check_types = {}
        for result in results:
            check_type = result.get("check_type", "unknown")
            if check_type not in check_types:
                check_types[check_type] = {"total": 0, "healthy": 0, "unhealthy": 0}

            check_types[check_type]["total"] += 1
            if result.get("status") == "healthy":
                check_types[check_type]["healthy"] += 1
            else:
                check_types[check_type]["unhealthy"] += 1

        return {
            "total_checks": total_checks,
            "healthy_checks": healthy_checks,
            "unhealthy_checks": unhealthy_checks,
            "health_percentage": (
                (healthy_checks / total_checks * 100) if total_checks > 0 else 0
            ),
            "average_response_time": avg_response_time,
            "execution_time": execution_time,
            "check_types": check_types,
            "overall_status": "healthy" if unhealthy_checks == 0 else "unhealthy",
        }
