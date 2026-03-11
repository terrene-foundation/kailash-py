"""
Unit Tests for APIESA (REST API Enterprise System Agent).

Tests cover:
- Capability discovery (with and without OpenAPI spec)
- HTTP method operations (GET, POST, PUT, DELETE, PATCH)
- Rate limiting enforcement
- Request/response logging
- Error handling
- Connection validation
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kaizen.trust.chain import CapabilityType
from kaizen.trust.esa.api import APIESA, ESAResult, RateLimitConfig, RateLimitTracker
from kaizen.trust.esa.base import SystemConnectionInfo, SystemMetadata
from kaizen.trust.esa.exceptions import ESAConnectionError, ESAOperationError


@pytest.fixture
def mock_trust_ops():
    """Mock TrustOperations instance."""
    trust_ops = MagicMock()
    trust_ops.establish = AsyncMock(return_value=MagicMock())
    trust_ops.verify = AsyncMock(return_value=MagicMock(valid=True))
    trust_ops.audit = AsyncMock(return_value=MagicMock(id="audit-001"))
    return trust_ops


@pytest.fixture
def basic_esa(mock_trust_ops):
    """Create basic APIESA instance without OpenAPI spec."""
    return APIESA(
        system_id="api-test-001",
        base_url="https://api.test.com",
        trust_ops=mock_trust_ops,
        authority_id="org-test",
    )


@pytest.fixture
def openapi_spec():
    """Sample OpenAPI spec."""
    return {
        "openapi": "3.0.0",
        "paths": {
            "/users": {
                "get": {
                    "summary": "List users",
                    "parameters": [
                        {
                            "name": "limit",
                            "in": "query",
                            "schema": {"type": "integer"},
                            "description": "Max users to return",
                            "required": False,
                        }
                    ],
                    "responses": {"200": {"description": "List of users"}},
                },
                "post": {
                    "summary": "Create user",
                    "responses": {"201": {"description": "User created"}},
                },
            },
            "/users/{id}": {
                "get": {
                    "summary": "Get user by ID",
                    "responses": {"200": {"description": "User details"}},
                },
                "put": {
                    "summary": "Update user",
                    "responses": {"200": {"description": "User updated"}},
                },
                "delete": {
                    "summary": "Delete user",
                    "responses": {"204": {"description": "User deleted"}},
                },
            },
        },
    }


@pytest.fixture
def esa_with_spec(mock_trust_ops, openapi_spec):
    """Create APIESA with OpenAPI spec."""
    return APIESA(
        system_id="api-test-001",
        base_url="https://api.test.com",
        trust_ops=mock_trust_ops,
        authority_id="org-test",
        openapi_spec=openapi_spec,
    )


class TestAPIESAInitialization:
    """Tests for APIESA initialization."""

    def test_basic_initialization(self, mock_trust_ops):
        """Test basic APIESA initialization."""
        esa = APIESA(
            system_id="api-test-001",
            base_url="https://api.test.com",
            trust_ops=mock_trust_ops,
            authority_id="org-test",
        )

        assert esa.system_id == "api-test-001"
        assert esa.base_url == "https://api.test.com"
        assert esa.authority_id == "org-test"
        assert esa.openapi_spec == {}
        assert esa.auth_headers == {}

    def test_initialization_with_trailing_slash(self, mock_trust_ops):
        """Test base URL normalization (trailing slash removal)."""
        esa = APIESA(
            system_id="api-test-001",
            base_url="https://api.test.com/",
            trust_ops=mock_trust_ops,
            authority_id="org-test",
        )

        assert esa.base_url == "https://api.test.com"

    def test_initialization_with_auth_headers(self, mock_trust_ops):
        """Test initialization with authentication headers."""
        auth_headers = {"Authorization": "Bearer token123"}

        esa = APIESA(
            system_id="api-test-001",
            base_url="https://api.test.com",
            trust_ops=mock_trust_ops,
            authority_id="org-test",
            auth_headers=auth_headers,
        )

        assert esa.auth_headers == auth_headers

    def test_initialization_with_rate_limit_config(self, mock_trust_ops):
        """Test initialization with rate limit configuration."""
        rate_config = RateLimitConfig(
            requests_per_second=10,
            requests_per_minute=100,
            requests_per_hour=1000,
        )

        esa = APIESA(
            system_id="api-test-001",
            base_url="https://api.test.com",
            trust_ops=mock_trust_ops,
            authority_id="org-test",
            rate_limit_config=rate_config,
        )

        assert esa.rate_limit_config.requests_per_second == 10
        assert esa.rate_limit_config.requests_per_minute == 100
        assert esa.rate_limit_config.requests_per_hour == 1000


class TestCapabilityDiscovery:
    """Tests for capability discovery."""

    @pytest.mark.asyncio
    async def test_discover_capabilities_without_spec(self, basic_esa):
        """Test capability discovery without OpenAPI spec (generic capabilities)."""
        capabilities = await basic_esa.discover_capabilities()

        # Should discover generic HTTP method capabilities
        assert "get_request" in capabilities
        assert "post_request" in capabilities
        assert "put_request" in capabilities
        assert "delete_request" in capabilities
        assert "patch_request" in capabilities

        # Check capability metadata
        get_meta = basic_esa.get_capability_metadata("get_request")
        assert get_meta is not None
        assert get_meta.capability == "get_request"
        assert get_meta.capability_type == CapabilityType.ACTION

    @pytest.mark.asyncio
    async def test_discover_capabilities_with_spec(self, esa_with_spec):
        """Test capability discovery with OpenAPI spec."""
        capabilities = await esa_with_spec.discover_capabilities()

        # Should discover capabilities from spec
        # Note: Path "/users/{id}" becomes "users_id_" due to bracket replacement
        assert "get_users" in capabilities
        assert "post_users" in capabilities
        assert "get_users_id_" in capabilities  # Trailing _ from {id} -> id_
        assert "put_users_id_" in capabilities
        assert "delete_users_id_" in capabilities

        # Check capability metadata
        get_users_meta = esa_with_spec.get_capability_metadata("get_users")
        assert get_users_meta is not None
        assert get_users_meta.capability == "get_users"
        assert get_users_meta.description == "List users"
        assert "limit" in get_users_meta.parameters

    @pytest.mark.asyncio
    async def test_capability_metadata_from_spec(self, esa_with_spec):
        """Test that capability metadata is correctly extracted from OpenAPI spec."""
        await esa_with_spec.discover_capabilities()

        # Check POST capability
        post_meta = esa_with_spec.get_capability_metadata("post_users")
        assert post_meta is not None
        assert post_meta.description == "Create user"
        assert post_meta.capability_type == CapabilityType.ACTION


class TestConnectionValidation:
    """Tests for connection validation."""

    @pytest.mark.asyncio
    async def test_validate_connection_success(self, basic_esa):
        """Test successful connection validation."""
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            result = await basic_esa.validate_connection()
            assert result is True

    @pytest.mark.asyncio
    async def test_validate_connection_404_acceptable(self, basic_esa):
        """Test that 404 is acceptable for connection validation."""
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_get.return_value = mock_response

            result = await basic_esa.validate_connection()
            assert result is True

    @pytest.mark.asyncio
    async def test_validate_connection_server_error(self, basic_esa):
        """Test connection validation with server error."""
        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_get.return_value = mock_response

            result = await basic_esa.validate_connection()
            assert result is False

    @pytest.mark.asyncio
    async def test_validate_connection_exception(self, basic_esa):
        """Test connection validation with exception."""
        with patch("httpx.AsyncClient.get", side_effect=Exception("Connection failed")):
            result = await basic_esa.validate_connection()
            assert result is False


class TestHTTPMethods:
    """Tests for HTTP method helpers."""

    @pytest.mark.asyncio
    async def test_get_method(self, basic_esa):
        """Test GET request method."""
        with patch.object(
            basic_esa, "call_endpoint", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = ESAResult(success=True, status_code=200)

            result = await basic_esa.get("/users", params={"limit": 10})

            mock_call.assert_called_once_with(
                method="GET",
                path="/users",
                params={"limit": 10},
                headers={},
            )
            assert result.success is True

    @pytest.mark.asyncio
    async def test_post_method(self, basic_esa):
        """Test POST request method."""
        with patch.object(
            basic_esa, "call_endpoint", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = ESAResult(success=True, status_code=201)

            data = {"name": "John", "email": "john@example.com"}
            result = await basic_esa.post("/users", data=data)

            mock_call.assert_called_once_with(
                method="POST",
                path="/users",
                params={},
                data=data,
                headers={},
            )
            assert result.status_code == 201

    @pytest.mark.asyncio
    async def test_put_method(self, basic_esa):
        """Test PUT request method."""
        with patch.object(
            basic_esa, "call_endpoint", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = ESAResult(success=True, status_code=200)

            data = {"name": "John Updated"}
            result = await basic_esa.put("/users/123", data=data)

            mock_call.assert_called_once_with(
                method="PUT",
                path="/users/123",
                params={},
                data=data,
                headers={},
            )

    @pytest.mark.asyncio
    async def test_delete_method(self, basic_esa):
        """Test DELETE request method."""
        with patch.object(
            basic_esa, "call_endpoint", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = ESAResult(success=True, status_code=204)

            result = await basic_esa.delete("/users/123")

            mock_call.assert_called_once_with(
                method="DELETE",
                path="/users/123",
                params={},
                headers={},
            )

    @pytest.mark.asyncio
    async def test_patch_method(self, basic_esa):
        """Test PATCH request method."""
        with patch.object(
            basic_esa, "call_endpoint", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = ESAResult(success=True, status_code=200)

            data = {"email": "newemail@example.com"}
            result = await basic_esa.patch("/users/123", data=data)

            mock_call.assert_called_once_with(
                method="PATCH",
                path="/users/123",
                params={},
                data=data,
                headers={},
            )


class TestRateLimiting:
    """Tests for rate limiting."""

    @pytest.mark.asyncio
    async def test_rate_limit_enforcement_per_second(self, mock_trust_ops):
        """Test per-second rate limiting."""
        esa = APIESA(
            system_id="api-test-001",
            base_url="https://api.test.com",
            trust_ops=mock_trust_ops,
            authority_id="org-test",
            rate_limit_config=RateLimitConfig(requests_per_second=2),
        )

        # Mock HTTP client
        with patch("httpx.AsyncClient.request") as mock_request:
            mock_response = MagicMock()
            mock_response.is_success = True
            mock_response.status_code = 200
            mock_response.json.return_value = {"status": "ok"}
            mock_response.text = "OK"
            mock_response.headers = {}
            mock_request.return_value = mock_response

            # Make 3 requests - third should be delayed
            start = datetime.now(timezone.utc)
            await esa.call_endpoint("GET", "/test")
            await esa.call_endpoint("GET", "/test")
            await esa.call_endpoint("GET", "/test")
            duration = (datetime.now(timezone.utc) - start).total_seconds()

            # Should take at least 1 second due to rate limiting
            assert duration >= 1.0

    @pytest.mark.asyncio
    async def test_rate_limit_status(self, mock_trust_ops):
        """Test rate limit status reporting."""
        esa = APIESA(
            system_id="api-test-001",
            base_url="https://api.test.com",
            trust_ops=mock_trust_ops,
            authority_id="org-test",
            rate_limit_config=RateLimitConfig(
                requests_per_second=10,
                requests_per_minute=100,
                requests_per_hour=1000,
            ),
        )

        # Mock HTTP client
        with patch("httpx.AsyncClient.request") as mock_request:
            mock_response = MagicMock()
            mock_response.is_success = True
            mock_response.status_code = 200
            mock_response.json.return_value = {}
            mock_response.text = ""
            mock_response.headers = {}
            mock_request.return_value = mock_response

            # Make some requests
            await esa.call_endpoint("GET", "/test")
            await esa.call_endpoint("GET", "/test")

            status = esa.get_rate_limit_status()

            assert status["per_second"]["current"] == 2
            assert status["per_second"]["limit"] == 10
            assert status["per_minute"]["current"] == 2
            assert status["per_minute"]["limit"] == 100

    def test_rate_limiter_cleanup(self):
        """Test rate limiter cleanup of old timestamps."""
        tracker = RateLimitTracker()

        # Add old and new timestamps
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(seconds=5)

        tracker.second_requests.append(old_time)
        tracker.second_requests.append(now)

        # Clean should remove old timestamp
        esa = APIESA(
            system_id="test",
            base_url="https://test.com",
            trust_ops=MagicMock(),
            authority_id="test",
        )
        esa._rate_limiter = tracker
        esa._clean_rate_limiter(now)

        assert len(tracker.second_requests) == 1
        assert tracker.second_requests[0] == now


class TestRequestLogging:
    """Tests for request/response logging."""

    @pytest.mark.asyncio
    async def test_request_logging(self, basic_esa):
        """Test that requests are logged."""
        with patch("httpx.AsyncClient.request") as mock_request:
            mock_response = MagicMock()
            mock_response.is_success = True
            mock_response.status_code = 200
            mock_response.json.return_value = {"data": "test"}
            mock_response.text = "OK"
            mock_response.headers = {}
            mock_request.return_value = mock_response

            await basic_esa.call_endpoint("GET", "/users")

            # Check log
            log = basic_esa.get_request_log(limit=10)
            assert len(log) == 1
            assert log[0]["method"] == "GET"
            assert log[0]["path"] == "/users"
            assert log[0]["status_code"] == 200

    @pytest.mark.asyncio
    async def test_request_statistics(self, basic_esa):
        """Test request statistics calculation."""
        with patch("httpx.AsyncClient.request") as mock_request:
            # Success response
            mock_response = MagicMock()
            mock_response.is_success = True
            mock_response.status_code = 200
            mock_response.json.return_value = {}
            mock_response.text = ""
            mock_response.headers = {}
            mock_request.return_value = mock_response

            # Make successful requests
            await basic_esa.call_endpoint("GET", "/users")
            await basic_esa.call_endpoint("POST", "/users")

            # Make failed request
            mock_response.is_success = False
            mock_response.status_code = 500
            try:
                await basic_esa.call_endpoint("GET", "/error")
            except ESAOperationError:
                pass

            # Check statistics
            stats = basic_esa.get_request_statistics()
            assert stats["total_requests"] == 3
            assert stats["successful_requests"] == 2
            assert stats["failed_requests"] == 1
            assert stats["success_rate"] == 2 / 3
            assert "GET" in stats["methods"]
            assert "POST" in stats["methods"]

    def test_request_log_limit(self, basic_esa):
        """Test request log size limit via _log_request method.

        The limit is enforced by the _log_request() method, not by direct append.
        """
        # Use internal _log_request method which enforces the limit
        for i in range(1100):
            basic_esa._log_request(
                method="GET",
                path=f"/test{i}",
                params=None,
                data=None,
                status_code=200,
                duration_ms=10,
                error=None,
            )

        # Should keep only last 1000 entries
        assert len(basic_esa._request_log) == 1000
        # Verify we have the most recent entries (1000-1099)
        assert basic_esa._request_log[0]["path"] == "/test100"
        assert basic_esa._request_log[-1]["path"] == "/test1099"


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_execute_operation_missing_path(self, basic_esa):
        """Test execute_operation with missing path parameter."""
        with pytest.raises(ESAOperationError) as exc_info:
            await basic_esa.execute_operation(
                operation="get_users", parameters={}  # Missing 'path'
            )

        assert "Missing required parameter: 'path'" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_call_endpoint_timeout(self, basic_esa):
        """Test timeout handling in call_endpoint."""
        import httpx

        with patch(
            "httpx.AsyncClient.request", side_effect=httpx.TimeoutException("Timeout")
        ):
            with pytest.raises(ESAOperationError) as exc_info:
                await basic_esa.call_endpoint("GET", "/slow")

            assert "timeout" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_call_endpoint_request_error(self, basic_esa):
        """Test request error handling."""
        import httpx

        with patch(
            "httpx.AsyncClient.request",
            side_effect=httpx.RequestError("Connection failed"),
        ):
            with pytest.raises(ESAOperationError) as exc_info:
                await basic_esa.call_endpoint("GET", "/error")

            assert "HTTP request failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_call_endpoint_unexpected_error(self, basic_esa):
        """Test unexpected error handling."""
        with patch("httpx.AsyncClient.request", side_effect=ValueError("Unexpected")):
            with pytest.raises(ESAOperationError) as exc_info:
                await basic_esa.call_endpoint("GET", "/error")

            assert "Unexpected error" in str(exc_info.value)


class TestCleanup:
    """Tests for resource cleanup."""

    @pytest.mark.asyncio
    async def test_cleanup_closes_client(self, basic_esa):
        """Test that cleanup closes HTTP client."""
        # Create client
        await basic_esa._get_client()
        assert basic_esa._client is not None

        # Cleanup
        await basic_esa.cleanup()
        assert basic_esa._client is None

    @pytest.mark.asyncio
    async def test_cleanup_idempotent(self, basic_esa):
        """Test that cleanup can be called multiple times."""
        await basic_esa.cleanup()
        await basic_esa.cleanup()  # Should not raise


class TestESAResult:
    """Tests for ESAResult dataclass."""

    def test_esa_result_creation(self):
        """Test ESAResult creation."""
        result = ESAResult(
            success=True,
            status_code=200,
            data={"id": 1, "name": "Test"},
            headers={"Content-Type": "application/json"},
            duration_ms=150,
        )

        assert result.success is True
        assert result.status_code == 200
        assert result.data["id"] == 1
        assert result.headers["Content-Type"] == "application/json"
        assert result.duration_ms == 150
        assert result.error is None

    def test_esa_result_with_error(self):
        """Test ESAResult with error."""
        result = ESAResult(
            success=False,
            status_code=500,
            error="Internal server error",
        )

        assert result.success is False
        assert result.error == "Internal server error"
        assert result.data is None


class TestRateLimitConfig:
    """Tests for RateLimitConfig."""

    def test_rate_limit_config_defaults(self):
        """Test RateLimitConfig default values."""
        config = RateLimitConfig()

        assert config.requests_per_second is None
        assert config.requests_per_minute is None
        assert config.requests_per_hour is None
        assert config.burst_size == 10

    def test_rate_limit_config_custom(self):
        """Test RateLimitConfig with custom values."""
        config = RateLimitConfig(
            requests_per_second=5,
            requests_per_minute=100,
            requests_per_hour=1000,
            burst_size=20,
        )

        assert config.requests_per_second == 5
        assert config.requests_per_minute == 100
        assert config.requests_per_hour == 1000
        assert config.burst_size == 20
