"""End-to-end tests for MCP resource subscription flow with real client."""

import asyncio
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

import pytest

from tests.utils.docker_manager import DockerTestManager
from tests.utils.test_helpers import wait_for_condition


@pytest.fixture(scope="module")
def docker_manager():
    """Create Docker test manager for real services."""
    manager = DockerTestManager()
    manager.start_services(["redis", "postgres"])
    yield manager
    manager.stop_services()


@pytest.fixture
def test_resources():
    """Create test resource directory with files."""
    temp_dir = tempfile.mkdtemp()

    # Create various test files
    files = {
        "config.json": {"database": "postgres", "port": 5432},
        "settings.yaml": "debug: true\nport: 8080",
        "data/users.json": [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}],
        "data/products.json": [{"id": 1, "name": "Widget", "price": 9.99}],
        "docs/readme.md": "# Test Project\n\nThis is a test.",
        "docs/api.md": "# API Documentation\n\n## Endpoints",
    }

    for filepath, content in files.items():
        path = Path(temp_dir) / filepath
        path.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(content, dict) or isinstance(content, list):
            path.write_text(json.dumps(content, indent=2))
        else:
            path.write_text(content)

    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
async def mcp_server_process(docker_manager, test_resources):
    """Start real MCP server process."""
    # Create server script
    server_script = Path(test_resources) / "test_server.py"
    server_script.write_text(
        f"""
import asyncio
import sys
from pathlib import Path

from kailash.mcp_server import MCPServer
from kailash.mcp_server.auth import APIKeyAuth
from kailash.middleware.gateway.event_store import EventStore
import redis.asyncio as redis

async def main():
    # Initialize Redis
    redis_client = await redis.from_url("{docker_manager.get_service_url('redis')}")

    # Create event store
    event_store = EventStore(redis_client=redis_client)
    await event_store.initialize()

    # Create auth
    auth = APIKeyAuth(keys={{
        "test-api-key": {{"permissions": ["read", "subscribe", "admin"]}}
    }})

    # Create server
    server = MCPServer(
        name="e2e-test-server",
        auth_provider=auth,
        enable_subscriptions=True,
        event_store=event_store,
        transport="stdio"
    )

    # Register all resources from directory
    resource_dir = Path("{test_resources}")
    for file_path in resource_dir.rglob("*"):
        if file_path.is_file():
            rel_path = file_path.relative_to(resource_dir)
            uri = f"file:///{rel_path}"

            @server.resource(uri)
            async def read_resource(path=file_path):
                return {{
                    "uri": f"file:///{path.relative_to(resource_dir)}",
                    "mimeType": "text/plain",
                    "text": path.read_text()
                }}

    # Run server
    await server.run()

if __name__ == "__main__":
    asyncio.run(main())
"""
    )

    # Start server process
    process = subprocess.Popen(
        [sys.executable, str(server_script)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    # Wait for server to start
    time.sleep(2)

    yield process

    # Cleanup
    process.terminate()
    process.wait(timeout=5)


class MCPClient:
    """Simple MCP client for testing."""

    def __init__(self, process):
        self.process = process
        self.request_id = 0
        self.subscriptions = {}
        self.notifications = []
        self._reader_task = None
        self._running = True

    async def start(self):
        """Start reading from server."""
        self._reader_task = asyncio.create_task(self._read_loop())

    async def stop(self):
        """Stop the client."""
        self._running = False
        if self._reader_task:
            await self._reader_task

    async def _read_loop(self):
        """Read messages from server."""
        while self._running:
            try:
                line = await asyncio.get_event_loop().run_in_executor(
                    None, self.process.stdout.readline
                )
                if not line:
                    break

                message = json.loads(line)

                # Handle notifications
                if "method" in message:
                    self.notifications.append(message)

            except json.JSONDecodeError:
                continue
            except Exception:
                break

    async def send_request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Send request and wait for response."""
        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params,
        }

        # Send request
        self.process.stdin.write(json.dumps(request) + "\n")
        self.process.stdin.flush()

        # Wait for response
        start_time = time.time()
        while time.time() - start_time < 5:
            line = self.process.stdout.readline()
            if line:
                response = json.loads(line)
                if response.get("id") == self.request_id:
                    if "error" in response:
                        raise Exception(response["error"])
                    return response.get("result", {})
            await asyncio.sleep(0.1)

        raise TimeoutError("No response received")

    async def initialize(self):
        """Initialize connection."""
        return await self.send_request(
            "initialize",
            {
                "protocolVersion": "0.1.0",
                "clientInfo": {"name": "test-client", "version": "1.0"},
                "capabilities": {},
            },
        )

    async def subscribe(self, uri_pattern: str, cursor: str = None):
        """Subscribe to resources."""
        params = {"uri": uri_pattern}
        if cursor:
            params["cursor"] = cursor

        result = await self.send_request("resources/subscribe", params)
        sub_id = result["subscriptionId"]
        self.subscriptions[sub_id] = uri_pattern
        return sub_id

    async def unsubscribe(self, subscription_id: str):
        """Unsubscribe from resources."""
        await self.send_request(
            "resources/unsubscribe", {"subscriptionId": subscription_id}
        )
        del self.subscriptions[subscription_id]

    async def list_resources(self, cursor: str = None, limit: int = None):
        """List resources with pagination."""
        params = {}
        if cursor:
            params["cursor"] = cursor
        if limit:
            params["limit"] = limit

        return await self.send_request("resources/list", params)

    async def read_resource(self, uri: str):
        """Read a specific resource."""
        return await self.send_request("resources/read", {"uri": uri})

    def get_notifications(self, method: str = None) -> List[Dict[str, Any]]:
        """Get received notifications."""
        if method:
            return [n for n in self.notifications if n.get("method") == method]
        return self.notifications


class TestMCPResourceE2E:
    """End-to-end tests for complete MCP resource flows."""

    @pytest.mark.asyncio
    async def test_complete_subscription_flow(self, mcp_server_process, test_resources):
        """Test complete subscription flow from client perspective."""
        client = MCPClient(mcp_server_process)
        await client.start()

        try:
            # Initialize connection
            init_response = await client.initialize()

            # Verify subscription capability
            assert init_response["capabilities"]["resources"]["subscribe"] is True
            assert init_response["capabilities"]["resources"]["listChanged"] is True

            # Subscribe to JSON files
            sub_id = await client.subscribe("file:///**/*.json")
            assert sub_id is not None

            # Modify a resource
            config_path = Path(test_resources) / "config.json"
            original = config_path.read_text()
            config_path.write_text('{"database": "mysql", "port": 3306}')

            # Read the resource to trigger change detection
            await client.read_resource("file:///config.json")

            # Wait for notification
            await wait_for_condition(
                lambda: len(client.get_notifications("notifications/resources/updated"))
                > 0,
                timeout=3,
            )

            # Verify notification
            notifications = client.get_notifications("notifications/resources/updated")
            assert len(notifications) == 1
            assert notifications[0]["params"]["uri"] == "file:///config.json"
            assert notifications[0]["params"]["type"] == "updated"

            # Unsubscribe
            await client.unsubscribe(sub_id)

            # Modify again - should not get notification
            config_path.write_text('{"database": "sqlite"}')
            await client.read_resource("file:///config.json")
            await asyncio.sleep(1)

            # Verify no new notifications
            assert len(client.get_notifications("notifications/resources/updated")) == 1

            # Restore original
            config_path.write_text(original)

        finally:
            await client.stop()

    @pytest.mark.asyncio
    async def test_pagination_flow(self, mcp_server_process):
        """Test cursor-based pagination with real client."""
        client = MCPClient(mcp_server_process)
        await client.start()

        try:
            await client.initialize()

            # Get first page
            page1 = await client.list_resources(limit=3)
            assert len(page1["resources"]) == 3
            assert "nextCursor" in page1

            # Get second page
            page2 = await client.list_resources(cursor=page1["nextCursor"], limit=3)
            assert len(page2["resources"]) >= 1

            # Verify no duplicates
            uris1 = {r["uri"] for r in page1["resources"]}
            uris2 = {r["uri"] for r in page2["resources"]}
            assert len(uris1.intersection(uris2)) == 0

            # Get all resources at once
            all_resources = await client.list_resources()
            all_uris = {r["uri"] for r in all_resources["resources"]}

            # Verify pagination covered all resources
            assert uris1.union(uris2).issubset(all_uris)

        finally:
            await client.stop()

    @pytest.mark.asyncio
    async def test_multiple_pattern_subscriptions(
        self, mcp_server_process, test_resources
    ):
        """Test subscribing to multiple patterns."""
        client = MCPClient(mcp_server_process)
        await client.start()

        try:
            await client.initialize()

            # Subscribe to different patterns
            json_sub = await client.subscribe("file:///**/*.json")
            md_sub = await client.subscribe("file:///**/docs/*.md")

            # Clear any existing notifications
            client.notifications.clear()

            # Modify files
            changes = [
                (
                    Path(test_resources) / "data" / "users.json",
                    '[{"id": 3, "name": "Charlie"}]',
                ),
                (Path(test_resources) / "docs" / "readme.md", "# Updated README"),
                (
                    Path(test_resources) / "settings.yaml",
                    "debug: false",
                ),  # Should not notify
            ]

            for path, content in changes:
                path.write_text(content)
                await client.read_resource(
                    f"file:///{path.relative_to(test_resources)}"
                )

            # Wait for notifications
            await wait_for_condition(
                lambda: len(client.get_notifications("notifications/resources/updated"))
                >= 2,
                timeout=3,
            )

            # Verify correct notifications
            notifications = client.get_notifications("notifications/resources/updated")
            notified_uris = {n["params"]["uri"] for n in notifications}

            assert "file:///data/users.json" in notified_uris
            assert "file:///docs/readme.md" in notified_uris
            assert "file:///settings.yaml" not in notified_uris

        finally:
            await client.stop()

    @pytest.mark.asyncio
    async def test_high_frequency_changes(self, mcp_server_process, test_resources):
        """Test handling rapid resource changes."""
        client = MCPClient(mcp_server_process)
        await client.start()

        try:
            await client.initialize()

            # Subscribe to all JSON files
            await client.subscribe("file:///**/*.json")

            # Clear notifications
            client.notifications.clear()

            # Make rapid changes
            config_path = Path(test_resources) / "config.json"
            for i in range(10):
                config_path.write_text(json.dumps({"version": i}))
                await client.read_resource("file:///config.json")
                await asyncio.sleep(0.1)  # Small delay between changes

            # Wait for notifications (may be batched)
            await wait_for_condition(
                lambda: len(client.get_notifications("notifications/resources/updated"))
                > 0,
                timeout=5,
            )

            # Verify at least some notifications received
            notifications = client.get_notifications("notifications/resources/updated")
            assert len(notifications) >= 1  # May be batched

            # All should be for the same resource
            uris = {n["params"]["uri"] for n in notifications}
            assert uris == {"file:///config.json"}

        finally:
            await client.stop()

    @pytest.mark.asyncio
    async def test_connection_recovery(self, mcp_server_process, test_resources):
        """Test subscription behavior after connection issues."""
        client1 = MCPClient(mcp_server_process)
        await client1.start()

        try:
            await client1.initialize()

            # Create subscription
            sub_id = await client1.subscribe("file:///**/*.json")

            # Simulate connection drop by creating new client
            await client1.stop()

            # Create new client (simulating reconnection)
            client2 = MCPClient(mcp_server_process)
            await client2.start()
            await client2.initialize()

            # Old subscription should not exist
            # Try to use old subscription ID (should fail or create new)
            with pytest.raises(Exception):
                await client2.unsubscribe(sub_id)

            # Create new subscription
            new_sub_id = await client2.subscribe("file:///**/*.json")
            assert new_sub_id != sub_id  # Should be different

            await client2.stop()

        finally:
            pass

    @pytest.mark.asyncio
    async def test_performance_under_load(self, mcp_server_process, test_resources):
        """Test performance with many subscriptions and resources."""
        clients = []

        try:
            # Create multiple clients
            for i in range(10):
                client = MCPClient(mcp_server_process)
                await client.start()
                await client.initialize()
                clients.append(client)

            # Each client creates multiple subscriptions
            for client in clients:
                await client.subscribe("file:///**/*.json")
                await client.subscribe("file:///**/*.md")
                await client.subscribe("file:///**/*.yaml")

            # Measure notification latency
            start_time = time.time()

            # Trigger a change
            config_path = Path(test_resources) / "config.json"
            config_path.write_text('{"performance": "test"}')

            # All clients read to trigger change detection
            read_tasks = [
                client.read_resource("file:///config.json") for client in clients
            ]
            await asyncio.gather(*read_tasks)

            # Wait for all clients to receive notification
            async def all_notified():
                for client in clients:
                    if (
                        len(client.get_notifications("notifications/resources/updated"))
                        == 0
                    ):
                        return False
                return True

            await wait_for_condition(all_notified, timeout=5)

            # Calculate latency
            latency = time.time() - start_time
            assert latency < 2  # Should notify all within 2 seconds

            # Verify all clients got notification
            for client in clients:
                notifications = client.get_notifications(
                    "notifications/resources/updated"
                )
                assert len(notifications) >= 1
                assert notifications[0]["params"]["uri"] == "file:///config.json"

        finally:
            # Cleanup all clients
            for client in clients:
                await client.stop()

    @pytest.mark.asyncio
    async def test_auth_enforcement(self, docker_manager, test_resources):
        """Test authentication and authorization for subscriptions."""
        # Create server with different auth keys
        server_script = Path(test_resources) / "auth_test_server.py"
        server_script.write_text(
            """
import asyncio
from kailash.mcp_server import MCPServer
from kailash.mcp_server.auth import APIKeyAuth

async def main():
    auth = APIKeyAuth(keys={
        "read-only-key": {"permissions": ["read"]},
        "subscribe-key": {"permissions": ["read", "subscribe"]},
    })

    server = MCPServer(
        name="auth-test-server",
        auth_provider=auth,
        enable_subscriptions=True,
        transport="stdio"
    )

    @server.resource("file:///test.json")
    async def test_resource():
        return {"uri": "file:///test.json", "text": "{}"}

    await server.run()

asyncio.run(main())
"""
        )

        # Start server with auth
        process = subprocess.Popen(
            [sys.executable, str(server_script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={**os.environ, "MCP_AUTH_KEY": "read-only-key"},
        )

        try:
            client = MCPClient(process)
            await client.start()
            await client.initialize()

            # Try to subscribe with read-only key (should fail)
            with pytest.raises(Exception, match="permission"):
                await client.subscribe("file:///*.json")

            await client.stop()

        finally:
            process.terminate()
            process.wait(timeout=5)
