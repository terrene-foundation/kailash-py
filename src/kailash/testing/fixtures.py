"""Common test fixtures for async workflows."""

import asyncio
import json
import logging
import os
import shutil
import tempfile
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

# Optional dependencies
try:
    import aiofiles

    HAS_AIOFILES = True
except ImportError:
    HAS_AIOFILES = False
    logger.warning("aiofiles not available for async file operations")

# Check if Docker is available
try:
    import docker

    # Verify it's the correct docker-py client
    if hasattr(docker, "from_env"):
        HAS_DOCKER = True
    else:
        HAS_DOCKER = False
        docker = None
        logger.warning("docker module found but not docker-py client")
except ImportError:
    HAS_DOCKER = False
    docker = None
    logger.warning("Docker not available for test fixtures")


@dataclass
class DatabaseFixture:
    """Test database fixture."""

    container: Any  # Docker container
    connection_string: str
    host: str
    port: int
    database: str
    user: str
    password: str

    async def cleanup(self):
        """Clean up database."""
        if self.container and HAS_DOCKER:
            try:
                self.container.stop()
                self.container.remove()
            except Exception as e:
                logger.error(f"Failed to cleanup database container: {e}")


@dataclass
class TestHttpServer:
    """Test HTTP server fixture."""

    host: str
    port: int
    url: str
    process: Any

    async def cleanup(self):
        """Stop server."""
        if self.process:
            try:
                self.process.terminate()
                await self.process.wait()
            except Exception as e:
                logger.error(f"Failed to cleanup HTTP server: {e}")


class AsyncWorkflowFixtures:
    """Common test fixtures for async workflows."""

    @staticmethod
    @asynccontextmanager
    async def temp_directory():
        """Create temporary directory for test."""
        temp_dir = tempfile.mkdtemp()
        try:
            yield temp_dir
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    @staticmethod
    async def create_test_database(
        engine: str = "postgresql",
        tag: str = "13",
        database: str = "test",
        user: str = "test",
        password: str = "test",
        port: int = None,
    ) -> DatabaseFixture:
        """Create test database with Docker."""
        if not HAS_DOCKER:
            raise RuntimeError("Docker not available for test database")

        client = docker.from_env()

        if engine == "postgresql":
            # Start PostgreSQL container
            container = client.containers.execute(
                f"postgres:{tag}",
                environment={
                    "POSTGRES_DB": database,
                    "POSTGRES_USER": user,
                    "POSTGRES_PASSWORD": password,
                },
                ports={"5432/tcp": port} if port else {"5432/tcp": None},
                detach=True,
                remove=False,
            )

            # Get assigned port
            container.reload()
            actual_port = int(container.ports["5432/tcp"][0]["HostPort"])

            # Wait for database to be ready
            try:
                import asyncpg
            except ImportError:
                container.stop()
                container.remove()
                raise RuntimeError("asyncpg required for PostgreSQL testing")

            conn_string = (
                f"postgresql://{user}:{password}@localhost:{actual_port}/{database}"
            )

            # Wait up to 30 seconds for database to be ready
            for i in range(30):
                try:
                    conn = await asyncpg.connect(conn_string)
                    await conn.close()
                    break
                except Exception:
                    if i == 29:  # Last attempt
                        container.stop()
                        container.remove()
                        raise TimeoutError("Database did not start in time")
                    await asyncio.sleep(1)

            return DatabaseFixture(
                container=container,
                connection_string=conn_string,
                host="localhost",
                port=actual_port,
                database=database,
                user=user,
                password=password,
            )

        elif engine == "mysql":
            # Start MySQL container
            container = client.containers.execute(
                f"mysql:{tag}",
                environment={
                    "MYSQL_ROOT_PASSWORD": password,
                    "MYSQL_DATABASE": database,
                    "MYSQL_USER": user,
                    "MYSQL_PASSWORD": password,
                },
                ports={"3306/tcp": port} if port else {"3306/tcp": None},
                detach=True,
                remove=False,
            )

            # Get assigned port
            container.reload()
            actual_port = int(container.ports["3306/tcp"][0]["HostPort"])

            conn_string = (
                f"mysql://{user}:{password}@localhost:{actual_port}/{database}"
            )

            # Wait for MySQL to be ready (takes longer than PostgreSQL)
            await asyncio.sleep(10)

            return DatabaseFixture(
                container=container,
                connection_string=conn_string,
                host="localhost",
                port=actual_port,
                database=database,
                user=user,
                password=password,
            )

        else:
            raise ValueError(f"Unsupported database engine: {engine}")

    @staticmethod
    async def create_test_files(directory: str, files: Dict[str, Union[str, Dict]]):
        """Create test files in directory."""
        for path, content in files.items():
            full_path = os.path.join(directory, path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)

            if HAS_AIOFILES:
                async with aiofiles.open(full_path, "w") as f:
                    if isinstance(content, dict):
                        await f.write(json.dumps(content, indent=2))
                    else:
                        await f.write(content)
            else:
                # Fallback to sync file operations
                with open(full_path, "w") as f:
                    if isinstance(content, dict):
                        f.write(json.dumps(content, indent=2))
                    else:
                        f.write(content)

    @staticmethod
    def create_mock_http_client() -> "MockHttpClient":
        """Create mock HTTP client for testing."""
        return MockHttpClient()

    @staticmethod
    async def create_test_cache() -> "MockCache":
        """Create mock cache for testing."""
        return MockCache()

    @staticmethod
    @asynccontextmanager
    async def mock_time(start_time: float = None, speed: float = 1.0):
        """Mock time for testing time-dependent code."""
        import time as time_module

        if start_time is None:
            start_time = time_module.time()

        real_time = time_module.time
        mock_start = start_time
        real_start = real_time()

        def mock_time():
            elapsed = (real_time() - real_start) * speed
            return mock_start + elapsed

        # Store original
        original_time = time_module.time
        original_loop_time = asyncio.get_event_loop().time

        # Patch time
        time_module.time = mock_time
        # Note: Patching event loop time is tricky and may not work in all cases

        try:
            yield mock_time
        finally:
            # Restore
            time_module.time = original_time


@dataclass
class HttpCall:
    """Record of HTTP call."""

    method: str
    url: str
    kwargs: dict


class MockResponse:
    """Mock HTTP response."""

    def __init__(self, data: Any, status: int = 200, headers: Dict = None):
        self._data = data
        self.status = status
        self.headers = headers or {}

    async def json(self):
        """Get JSON response."""
        if isinstance(self._data, str):
            return json.loads(self._data)
        return self._data

    async def text(self):
        """Get text response."""
        if isinstance(self._data, str):
            return self._data
        return json.dumps(self._data)

    def raise_for_status(self):
        """Raise if error status."""
        if self.status >= 400:
            raise Exception(f"HTTP {self.status}")


class MockHttpClient:
    """Mock HTTP client for testing."""

    def __init__(self):
        self._responses: Dict[str, Any] = {}
        self._calls: List[HttpCall] = []
        self._default_status = 404
        self._default_response = {"error": "Not found"}

    def add_response(
        self,
        method: str,
        url: str,
        response: Any,
        status: int = 200,
        headers: Dict[str, str] = None,
    ):
        """Add a mock response."""
        key = f"{method.upper()}:{url}"
        self._responses[key] = {
            "response": response,
            "status": status,
            "headers": headers or {},
        }

    def add_responses(self, responses: Dict[str, Any]):
        """Add multiple responses."""
        for key, value in responses.items():
            if ":" in key:
                method, url = key.split(":", 1)
                self.add_response(method, url, value)
            else:
                # Default to GET
                self.add_response("GET", key, value)

    def set_default_response(self, response: Any, status: int = 200):
        """Set default response for unmatched requests."""
        self._default_response = response
        self._default_status = status

    async def request(self, method: str, url: str, **kwargs) -> MockResponse:
        """Make mock request."""
        # Record call
        call = HttpCall(method.upper(), url, kwargs)
        self._calls.append(call)

        # Find response
        key = f"{method.upper()}:{url}"
        if key in self._responses:
            resp_data = self._responses[key]
            return MockResponse(
                resp_data["response"], resp_data["status"], resp_data["headers"]
            )

        # Default response
        return MockResponse(self._default_response, self._default_status)

    # Convenience methods
    async def get(self, url: str, **kwargs):
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs):
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs):
        return await self.request("PUT", url, **kwargs)

    async def delete(self, url: str, **kwargs):
        return await self.request("DELETE", url, **kwargs)

    def get_calls(self, method: str = None, url: str = None) -> List[HttpCall]:
        """Get recorded calls."""
        calls = self._calls
        if method:
            calls = [c for c in calls if c.method == method.upper()]
        if url:
            calls = [c for c in calls if c.url == url]
        return calls

    def assert_called(self, method: str, url: str, times: int = None):
        """Assert endpoint was called."""
        calls = self.get_calls(method, url)
        if times is not None:
            assert (
                len(calls) == times
            ), f"{method} {url} called {len(calls)} times, expected {times}"
        else:
            assert len(calls) > 0, f"{method} {url} was not called"

    def reset(self):
        """Reset recorded calls."""
        self._calls.clear()


class MockCache:
    """Mock cache for testing."""

    def __init__(self):
        self._data: Dict[str, Any] = {}
        self._expiry: Dict[str, float] = {}
        self._calls: List[tuple[str, tuple, dict]] = []

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        self._calls.append(("get", (key,), {}))

        # Check expiry
        if key in self._expiry:
            if asyncio.get_event_loop().time() > self._expiry[key]:
                del self._data[key]
                del self._expiry[key]
                return None

        return self._data.get(key)

    async def set(self, key: str, value: Any, ttl: int = None):
        """Set value in cache."""
        self._calls.append(("set", (key, value), {"ttl": ttl}))
        self._data[key] = value
        if ttl:
            self._expiry[key] = asyncio.get_event_loop().time() + ttl

    async def setex(self, key: str, ttl: int, value: Any):
        """Set with expiration (Redis style)."""
        await self.set(key, value, ttl)

    async def delete(self, key: str):
        """Delete from cache."""
        self._calls.append(("delete", (key,), {}))
        self._data.pop(key, None)
        self._expiry.pop(key, None)

    async def expire(self, key: str, ttl: int):
        """Set expiration on existing key."""
        self._calls.append(("expire", (key, ttl), {}))
        if key in self._data:
            self._expiry[key] = asyncio.get_event_loop().time() + ttl

    async def clear(self):
        """Clear cache."""
        self._calls.append(("clear", (), {}))
        self._data.clear()
        self._expiry.clear()

    def get_calls(self, method: str = None) -> List[tuple[str, tuple, dict]]:
        """Get recorded calls."""
        if method:
            return [c for c in self._calls if c[0] == method]
        return self._calls.copy()

    def assert_called(self, method: str, times: int = None):
        """Assert method was called."""
        calls = self.get_calls(method)
        if times is not None:
            assert (
                len(calls) == times
            ), f"Cache.{method} called {len(calls)} times, expected {times}"
        else:
            assert len(calls) > 0, f"Cache.{method} was not called"
