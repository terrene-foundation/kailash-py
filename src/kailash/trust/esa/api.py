# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
REST API Enterprise System Agent Implementation.

Provides ESA integration for REST APIs with features:
- OpenAPI/Swagger spec parsing for capability discovery
- HTTP method support (GET, POST, PUT, DELETE, PATCH)
- Rate limiting enforcement
- Request/response logging for audit
- Authentication support (API keys, OAuth tokens, etc.)
"""

import asyncio
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

try:
    import httpx
except ImportError:
    raise ImportError("httpx is required for APIESA. Install with: pip install httpx")

from kailash.trust.chain import CapabilityType
from kailash.trust.esa.base import (
    CapabilityMetadata,
    EnterpriseSystemAgent,
    ESAConfig,
    SystemConnectionInfo,
    SystemMetadata,
)
from kailash.trust.esa.exceptions import ESAConnectionError, ESAOperationError
from kailash.trust.operations import TrustOperations


@dataclass
class RateLimitConfig:
    """
    Configuration for rate limiting.

    Attributes:
        requests_per_second: Maximum requests per second
        requests_per_minute: Maximum requests per minute
        requests_per_hour: Maximum requests per hour
        burst_size: Maximum burst size (allows temporary spikes)
    """

    requests_per_second: Optional[int] = None
    requests_per_minute: Optional[int] = None
    requests_per_hour: Optional[int] = None
    burst_size: int = 10


@dataclass
class RateLimitTracker:
    """Tracks request counts for rate limiting."""

    second_requests: deque = field(default_factory=lambda: deque(maxlen=1000))
    minute_requests: deque = field(default_factory=lambda: deque(maxlen=10000))
    hour_requests: deque = field(default_factory=lambda: deque(maxlen=100000))


@dataclass
class ESAResult:
    """
    Result from an ESA API operation.

    Attributes:
        success: Whether the operation succeeded
        status_code: HTTP status code
        data: Response data (parsed JSON or raw text)
        headers: Response headers
        error: Error message if failed
        duration_ms: Request duration in milliseconds
        metadata: Additional metadata
    """

    success: bool
    status_code: int
    data: Optional[Any] = None
    headers: Optional[Dict[str, str]] = None
    error: Optional[str] = None
    duration_ms: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class APIESA(EnterpriseSystemAgent):
    """
    REST API Enterprise System Agent.

    Provides trust-aware proxy access to REST APIs with:
    - OpenAPI spec parsing for automatic capability discovery
    - HTTP method support (GET, POST, PUT, DELETE, PATCH)
    - Rate limiting enforcement
    - Request/response audit logging
    - Authentication support

    Example:
        >>> esa = APIESA(
        ...     system_id="api-crm-001",
        ...     base_url="https://api.crm.example.com",
        ...     trust_operations=trust_ops,
        ...     authority_id="org-acme",
        ...     openapi_spec={
        ...         "paths": {
        ...             "/users": {"get": {...}, "post": {...}},
        ...             "/users/{id}": {"get": {...}, "put": {...}, "delete": {...}}
        ...         }
        ...     }
        ... )
        >>> await esa.establish_trust("org-acme")
        >>> result = await esa.get("/users", params={"limit": 10})
        >>> result = await esa.post("/users", data={"name": "John Doe"})
    """

    def __init__(
        self,
        system_id: str,
        base_url: str,
        trust_ops: TrustOperations,
        authority_id: str,
        openapi_spec: Optional[Dict[str, Any]] = None,
        auth_headers: Optional[Dict[str, str]] = None,
        rate_limit_config: Optional[RateLimitConfig] = None,
        metadata: Optional[SystemMetadata] = None,
        config: Optional[ESAConfig] = None,
        timeout_seconds: int = 30,
    ):
        """
        Initialize REST API ESA.

        Args:
            system_id: Unique identifier for the API system
            base_url: Base URL for the API (e.g., "https://api.example.com")
            trust_ops: TrustOperations instance for trust management
            authority_id: Authority ID for trust establishment
            openapi_spec: Optional OpenAPI/Swagger spec for capability discovery
            auth_headers: Optional authentication headers (e.g., {"Authorization": "Bearer ..."})
            rate_limit_config: Optional rate limiting configuration
            metadata: System metadata (optional)
            config: ESA configuration (optional)
            timeout_seconds: Request timeout in seconds
        """
        # Normalize base URL (remove trailing slash)
        self.base_url = base_url.rstrip("/")

        # Store connection info for parent class
        connection_info = SystemConnectionInfo(
            endpoint=self.base_url,
            credentials={"auth_headers": auth_headers} if auth_headers else None,  # type: ignore[arg-type]
            timeout_seconds=timeout_seconds,
        )

        # Initialize parent
        system_name = f"REST API: {system_id}"
        if metadata is None:
            metadata = SystemMetadata(
                system_type="rest_api",
                description=f"REST API at {self.base_url}",
            )

        super().__init__(
            system_id=system_id,
            system_name=system_name,
            trust_ops=trust_ops,
            connection_info=connection_info,
            metadata=metadata,
            config=config or ESAConfig(),
        )

        # API-specific configuration
        self.authority_id = authority_id
        self.openapi_spec = openapi_spec or {}
        self.auth_headers = auth_headers or {}
        self.rate_limit_config = rate_limit_config or RateLimitConfig()
        self.timeout_seconds = timeout_seconds

        # Rate limiting tracking
        self._rate_limiter = RateLimitTracker()
        self._rate_limiter_lock = asyncio.Lock()

        # HTTP client (created on first use)
        self._client: Optional[httpx.AsyncClient] = None

        # Request/response audit log (bounded to prevent OOM)
        self._request_log: deque = deque(maxlen=10000)  # type: ignore[assignment]

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout_seconds,
                follow_redirects=True,
            )
        return self._client

    async def _close_client(self) -> None:
        """Close HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # =========================================================================
    # EnterpriseSystemAgent Abstract Methods
    # =========================================================================

    async def discover_capabilities(self) -> List[str]:
        """
        Discover capabilities from OpenAPI spec.

        Parses the OpenAPI spec to create capability names based on:
        - Path (e.g., "/users", "/users/{id}")
        - HTTP method (GET, POST, PUT, DELETE, PATCH)

        Capability naming convention:
        - GET /users -> "get_users"
        - POST /users -> "post_users"
        - GET /users/{id} -> "get_users_id"
        - DELETE /users/{id} -> "delete_users_id"

        Returns:
            List of capability names

        Note:
            Also populates self._capability_metadata with CapabilityMetadata
            for each discovered capability.
        """
        capabilities = []

        if not self.openapi_spec or "paths" not in self.openapi_spec:
            # No spec provided - create generic capabilities
            capabilities = [
                "get_request",
                "post_request",
                "put_request",
                "delete_request",
                "patch_request",
            ]

            # Add generic capability metadata
            for method in ["get", "post", "put", "delete", "patch"]:
                self._capability_metadata[f"{method}_request"] = CapabilityMetadata(
                    capability=f"{method}_request",
                    description=f"Generic {method.upper()} request to any endpoint",
                    capability_type=CapabilityType.ACTION,
                    parameters={
                        "path": {
                            "type": "string",
                            "description": "API endpoint path",
                            "required": True,
                        },
                        "params": {
                            "type": "dict",
                            "description": "Query parameters",
                            "required": False,
                        },
                        "data": {
                            "type": "dict",
                            "description": "Request body data",
                            "required": False,
                        },
                    },
                    constraints=["rate_limited"],
                )

            return capabilities

        # Parse OpenAPI spec
        paths = self.openapi_spec.get("paths", {})

        for path, path_spec in paths.items():
            # Convert path to capability name
            # e.g., "/users/{id}" -> "users_id"
            path_name = (
                path.strip("/")
                .replace("/", "_")
                .replace("{", "")
                .replace("}", "_")
                .replace("-", "_")
            )
            if not path_name:
                path_name = "root"

            # Check each HTTP method
            for method in ["get", "post", "put", "delete", "patch"]:
                if method in path_spec:
                    method_spec = path_spec[method]

                    # Create capability name
                    capability = f"{method}_{path_name}"
                    capabilities.append(capability)

                    # Extract parameters from spec
                    parameters = {}
                    if "parameters" in method_spec:
                        for param in method_spec["parameters"]:
                            param_name = param.get("name", "")
                            parameters[param_name] = {
                                "type": param.get("schema", {}).get("type", "string"),
                                "description": param.get("description", ""),
                                "required": param.get("required", False),
                            }

                    # Create capability metadata
                    self._capability_metadata[capability] = CapabilityMetadata(
                        capability=capability,
                        description=method_spec.get(
                            "summary", f"{method.upper()} {path}"
                        ),
                        capability_type=CapabilityType.ACTION,
                        parameters=parameters,
                        return_type=method_spec.get("responses", {})
                        .get("200", {})
                        .get("description", ""),
                        constraints=["rate_limited"],
                        examples=[
                            {
                                "path": path,
                                "method": method.upper(),
                                "description": method_spec.get("description", ""),
                            }
                        ],
                    )

        return capabilities

    async def execute_operation(
        self,
        operation: str,
        parameters: Dict[str, Any],
    ) -> ESAResult:
        """
        Execute an HTTP API operation.

        This method is called by the parent class's execute() method after
        trust verification has passed. It performs the actual HTTP request.

        Args:
            operation: Operation name (e.g., "get_users", "post_users")
            parameters: Operation parameters including:
                - path: API endpoint path (required)
                - params: Query parameters (optional)
                - data: Request body data (optional)
                - headers: Additional headers (optional)

        Returns:
            ESAResult with response data

        Raises:
            ESAOperationError: If HTTP request fails
        """
        # Extract parameters
        path = parameters.get("path")
        params = parameters.get("params", {})
        data = parameters.get("data")
        headers = parameters.get("headers", {})

        if not path:
            raise ESAOperationError(
                operation=operation,
                system_id=self.system_id,
                reason="Missing required parameter: 'path'",
            )

        # Determine HTTP method from operation name
        method = operation.split("_")[0].upper()
        if method not in ["GET", "POST", "PUT", "DELETE", "PATCH"]:
            method = "GET"  # Default fallback

        # Call endpoint
        return await self.call_endpoint(
            method=method,
            path=path,
            params=params,
            data=data,
            headers=headers,
        )

    async def validate_connection(self) -> bool:
        """
        Validate API connection.

        Performs a lightweight health check by attempting to connect
        to the base URL.

        Returns:
            True if connection is valid, False otherwise
        """
        try:
            client = await self._get_client()
            response = await client.get(self.base_url, headers=self.auth_headers)

            # Accept any 2xx or 3xx status code, or 404 (endpoint may not have root)
            return response.status_code < 500

        except Exception as e:
            # Log connection error but don't raise
            print(f"Connection validation failed: {e}")
            return False

    # =========================================================================
    # HTTP Method Helpers
    # =========================================================================

    async def get(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> ESAResult:
        """
        Execute GET request.

        Args:
            path: API endpoint path (relative to base_url)
            params: Query parameters
            headers: Additional headers

        Returns:
            ESAResult with response data

        Raises:
            ESAOperationError: If request fails
        """
        return await self.call_endpoint(
            method="GET",
            path=path,
            params=params or {},
            headers=headers or {},
        )

    async def post(
        self,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> ESAResult:
        """
        Execute POST request.

        Args:
            path: API endpoint path (relative to base_url)
            data: Request body data
            params: Query parameters
            headers: Additional headers

        Returns:
            ESAResult with response data

        Raises:
            ESAOperationError: If request fails
        """
        return await self.call_endpoint(
            method="POST",
            path=path,
            params=params or {},
            data=data,
            headers=headers or {},
        )

    async def put(
        self,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> ESAResult:
        """
        Execute PUT request.

        Args:
            path: API endpoint path (relative to base_url)
            data: Request body data
            params: Query parameters
            headers: Additional headers

        Returns:
            ESAResult with response data

        Raises:
            ESAOperationError: If request fails
        """
        return await self.call_endpoint(
            method="PUT",
            path=path,
            params=params or {},
            data=data,
            headers=headers or {},
        )

    async def delete(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> ESAResult:
        """
        Execute DELETE request.

        Args:
            path: API endpoint path (relative to base_url)
            params: Query parameters
            headers: Additional headers

        Returns:
            ESAResult with response data

        Raises:
            ESAOperationError: If request fails
        """
        return await self.call_endpoint(
            method="DELETE",
            path=path,
            params=params or {},
            headers=headers or {},
        )

    async def patch(
        self,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> ESAResult:
        """
        Execute PATCH request.

        Args:
            path: API endpoint path (relative to base_url)
            data: Request body data
            params: Query parameters
            headers: Additional headers

        Returns:
            ESAResult with response data

        Raises:
            ESAOperationError: If request fails
        """
        return await self.call_endpoint(
            method="PATCH",
            path=path,
            params=params or {},
            data=data,
            headers=headers or {},
        )

    async def call_endpoint(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> ESAResult:
        """
        Execute HTTP request to API endpoint.

        This is the core HTTP request method that:
        1. Enforces rate limiting
        2. Makes the HTTP request
        3. Logs request/response for audit

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, PATCH)
            path: API endpoint path (relative to base_url)
            params: Query parameters
            data: Request body data
            headers: Additional headers

        Returns:
            ESAResult with response data

        Raises:
            ESAOperationError: If request fails
        """
        start_time = datetime.now(timezone.utc)

        # Enforce rate limiting
        await self._enforce_rate_limit()

        # Build full URL
        full_url = f"{self.base_url}/{path.lstrip('/')}"

        # Merge headers
        request_headers = {**self.auth_headers, **(headers or {})}

        # Get HTTP client
        client = await self._get_client()

        # Execute request
        try:
            response = await client.request(
                method=method,
                url=full_url,
                params=params or {},
                json=data if data is not None else None,
                headers=request_headers,
            )

            # Calculate duration
            duration_ms = int(
                (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            )

            # Parse response
            response_data = None
            try:
                response_data = response.json()
            except Exception:
                # Not JSON - use text
                response_data = response.text

            # Create result
            result = ESAResult(
                success=response.is_success,
                status_code=response.status_code,
                data=response_data,
                headers=dict(response.headers),
                error=(
                    None
                    if response.is_success
                    else f"HTTP {response.status_code}: {response.text}"
                ),
                duration_ms=duration_ms,
                metadata={
                    "method": method,
                    "path": path,
                    "full_url": full_url,
                },
            )

            # Log request/response
            self._log_request(
                method=method,
                path=path,
                params=params,
                data=data,
                status_code=response.status_code,
                duration_ms=duration_ms,
            )

            return result

        except httpx.TimeoutException as e:
            duration_ms = int(
                (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            )
            self._log_request(
                method=method,
                path=path,
                params=params,
                data=data,
                status_code=0,
                duration_ms=duration_ms,
                error="Timeout",
            )
            raise ESAOperationError(
                operation=f"{method} {path}",
                system_id=self.system_id,
                reason=f"Request timeout after {self.timeout_seconds}s",
                original_error=e,
            )

        except httpx.RequestError as e:
            duration_ms = int(
                (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            )
            self._log_request(
                method=method,
                path=path,
                params=params,
                data=data,
                status_code=0,
                duration_ms=duration_ms,
                error=str(e),
            )
            raise ESAOperationError(
                operation=f"{method} {path}",
                system_id=self.system_id,
                reason=f"HTTP request failed: {str(e)}",
                original_error=e,
            )

        except Exception as e:
            duration_ms = int(
                (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            )
            self._log_request(
                method=method,
                path=path,
                params=params,
                data=data,
                status_code=0,
                duration_ms=duration_ms,
                error=str(e),
            )
            raise ESAOperationError(
                operation=f"{method} {path}",
                system_id=self.system_id,
                reason=f"Unexpected error: {str(e)}",
                original_error=e,
            )

    # =========================================================================
    # Rate Limiting
    # =========================================================================

    async def _enforce_rate_limit(self) -> None:
        """
        Enforce rate limiting before making request.

        Checks configured rate limits and waits if necessary.
        Uses a sliding window algorithm.

        Raises:
            ESAOperationError: If rate limit exceeded and wait time too long
        """
        if not any(
            [
                self.rate_limit_config.requests_per_second,
                self.rate_limit_config.requests_per_minute,
                self.rate_limit_config.requests_per_hour,
            ]
        ):
            # No rate limits configured
            return

        async with self._rate_limiter_lock:
            now = datetime.now(timezone.utc)

            # Clean old requests
            self._clean_rate_limiter(now)

            # Check per-second limit
            if self.rate_limit_config.requests_per_second:
                if (
                    len(self._rate_limiter.second_requests)
                    >= self.rate_limit_config.requests_per_second
                ):
                    # Calculate wait time
                    oldest = self._rate_limiter.second_requests[0]
                    wait_seconds = 1.0 - (now - oldest).total_seconds()
                    if wait_seconds > 0:
                        await asyncio.sleep(wait_seconds)
                        now = datetime.now(timezone.utc)
                        self._clean_rate_limiter(now)

            # Check per-minute limit
            if self.rate_limit_config.requests_per_minute:
                if (
                    len(self._rate_limiter.minute_requests)
                    >= self.rate_limit_config.requests_per_minute
                ):
                    oldest = self._rate_limiter.minute_requests[0]
                    wait_seconds = 60.0 - (now - oldest).total_seconds()
                    if wait_seconds > 0:
                        await asyncio.sleep(wait_seconds)
                        now = datetime.now(timezone.utc)
                        self._clean_rate_limiter(now)

            # Check per-hour limit
            if self.rate_limit_config.requests_per_hour:
                if (
                    len(self._rate_limiter.hour_requests)
                    >= self.rate_limit_config.requests_per_hour
                ):
                    oldest = self._rate_limiter.hour_requests[0]
                    wait_seconds = 3600.0 - (now - oldest).total_seconds()
                    if wait_seconds > 60:
                        raise ESAOperationError(
                            operation="rate_limit_check",
                            system_id=self.system_id,
                            reason=f"Hourly rate limit exceeded. Wait time: {int(wait_seconds)}s",
                        )
                    if wait_seconds > 0:
                        await asyncio.sleep(wait_seconds)
                        now = datetime.now(timezone.utc)
                        self._clean_rate_limiter(now)

            # Record this request
            self._rate_limiter.second_requests.append(now)
            self._rate_limiter.minute_requests.append(now)
            self._rate_limiter.hour_requests.append(now)

    def _clean_rate_limiter(self, now: datetime) -> None:
        """
        Remove expired request timestamps from rate limiter.

        Args:
            now: Current timestamp
        """
        # Remove requests older than 1 second
        cutoff_second = now - timedelta(seconds=1)
        while (
            self._rate_limiter.second_requests
            and self._rate_limiter.second_requests[0] <= cutoff_second
        ):
            self._rate_limiter.second_requests.popleft()

        # Remove requests older than 1 minute
        cutoff_minute = now - timedelta(minutes=1)
        while (
            self._rate_limiter.minute_requests
            and self._rate_limiter.minute_requests[0] <= cutoff_minute
        ):
            self._rate_limiter.minute_requests.popleft()

        # Remove requests older than 1 hour
        cutoff_hour = now - timedelta(hours=1)
        while (
            self._rate_limiter.hour_requests
            and self._rate_limiter.hour_requests[0] <= cutoff_hour
        ):
            self._rate_limiter.hour_requests.popleft()

    def get_rate_limit_status(self) -> Dict[str, Any]:
        """
        Get current rate limit status.

        Returns:
            Dictionary with current request counts and limits
        """
        now = datetime.now(timezone.utc)
        self._clean_rate_limiter(now)

        return {
            "per_second": {
                "current": len(self._rate_limiter.second_requests),
                "limit": self.rate_limit_config.requests_per_second,
            },
            "per_minute": {
                "current": len(self._rate_limiter.minute_requests),
                "limit": self.rate_limit_config.requests_per_minute,
            },
            "per_hour": {
                "current": len(self._rate_limiter.hour_requests),
                "limit": self.rate_limit_config.requests_per_hour,
            },
        }

    # =========================================================================
    # Request Logging
    # =========================================================================

    def _log_request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]],
        data: Optional[Any],
        status_code: int,
        duration_ms: int,
        error: Optional[str] = None,
    ) -> None:
        """
        Log request/response for audit.

        Args:
            method: HTTP method
            path: API endpoint path
            params: Query parameters
            data: Request body data
            status_code: HTTP status code
            duration_ms: Request duration
            error: Error message if failed
        """
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "method": method,
            "path": path,
            "params": params,
            "data": data,
            "status_code": status_code,
            "duration_ms": duration_ms,
            "error": error,
        }

        self._request_log.append(log_entry)

    def get_request_log(
        self,
        limit: int = 100,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get request log entries.

        Args:
            limit: Maximum number of entries to return
            start_time: Optional start time filter
            end_time: Optional end time filter

        Returns:
            List of log entries
        """
        filtered_log = self._request_log

        # Apply time filters
        if start_time or end_time:
            filtered_log = []
            for entry in self._request_log:
                entry_time = datetime.fromisoformat(entry["timestamp"])
                if start_time and entry_time < start_time:
                    continue
                if end_time and entry_time > end_time:
                    continue
                filtered_log.append(entry)

        # Return most recent entries
        return list(filtered_log)[-limit:]

    def get_request_statistics(self) -> Dict[str, Any]:
        """
        Get request statistics.

        Returns:
            Dictionary with request statistics
        """
        if not self._request_log:
            return {
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "average_duration_ms": 0,
                "methods": {},
                "status_codes": {},
            }

        total = len(self._request_log)
        successful = sum(
            1 for entry in self._request_log if 200 <= entry["status_code"] < 300
        )
        failed = total - successful

        # Average duration
        total_duration = sum(entry["duration_ms"] for entry in self._request_log)
        avg_duration = total_duration / total if total > 0 else 0

        # Method counts
        methods = defaultdict(int)
        for entry in self._request_log:
            methods[entry["method"]] += 1

        # Status code counts
        status_codes = defaultdict(int)
        for entry in self._request_log:
            status_codes[str(entry["status_code"])] += 1

        return {
            "total_requests": total,
            "successful_requests": successful,
            "failed_requests": failed,
            "success_rate": successful / total if total > 0 else 0,
            "average_duration_ms": int(avg_duration),
            "methods": dict(methods),
            "status_codes": dict(status_codes),
        }

    # =========================================================================
    # Cleanup
    # =========================================================================

    async def cleanup(self) -> None:
        """Clean up resources."""
        await self._close_client()
