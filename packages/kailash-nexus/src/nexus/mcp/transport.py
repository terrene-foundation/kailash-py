"""MCP Transport implementations for Nexus.

This module provides transport layer implementations for the Model Context Protocol (MCP).
It supports WebSocket-based communication for server-side MCP implementations.
"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Optional, Set

import websockets
from websockets import WebSocketServerProtocol

logger = logging.getLogger(__name__)


class MCPTransport(ABC):
    """Abstract base class for MCP transport implementations."""

    @abstractmethod
    async def start(self):
        """Start the transport layer."""
        pass

    @abstractmethod
    async def stop(self):
        """Stop the transport layer."""
        pass

    @abstractmethod
    async def send_message(self, message: Dict[str, Any]) -> None:
        """Send a message through the transport.

        Args:
            message: Message to send
        """
        pass

    @abstractmethod
    async def receive_message(self) -> Dict[str, Any]:
        """Receive a message from the transport.

        Returns:
            Received message
        """
        pass


class WebSocketServerTransport(MCPTransport):
    """WebSocket server transport for MCP.

    This transport implementation provides a WebSocket server that can handle
    multiple concurrent MCP client connections. It's designed for server-side
    MCP implementations that need to expose tools and resources to AI agents.
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 3001,
        message_handler: Optional[Callable] = None,
        max_message_size: int = 10 * 1024 * 1024,  # 10MB
    ):
        """Initialize WebSocket server transport.

        Args:
            host: Host to bind to
            port: Port to listen on
            message_handler: Async callable to handle incoming messages
            max_message_size: Maximum message size in bytes
        """
        self.host = host
        self.port = port
        self.message_handler = message_handler
        self.max_message_size = max_message_size

        self._server = None
        self._clients: Set[WebSocketServerProtocol] = set()
        self._running = False
        self._server_task = None
        self._message_queue: asyncio.Queue = asyncio.Queue()

    async def start(self):
        """Start the WebSocket server."""
        if self._running:
            logger.warning("WebSocket server already running")
            return

        logger.info(f"Starting WebSocket server on {self.host}:{self.port}")

        # Create the WebSocket server
        self._server = await websockets.serve(
            self._handle_client,
            self.host,
            self.port,
            max_size=self.max_message_size,
            ping_interval=20,
            ping_timeout=10,
        )

        self._running = True
        logger.info(f"WebSocket server listening on ws://{self.host}:{self.port}")

    async def stop(self):
        """Stop the WebSocket server."""
        if not self._running:
            return

        logger.info("Stopping WebSocket server")
        self._running = False

        # Close all client connections
        if self._clients:
            await asyncio.gather(
                *[client.close() for client in self._clients], return_exceptions=True
            )
            self._clients.clear()

        # Stop the server
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        logger.info("WebSocket server stopped")

    async def send_message(
        self, message: Dict[str, Any], client: Optional[WebSocketServerProtocol] = None
    ) -> None:
        """Send a message to a specific client or broadcast to all.

        Args:
            message: Message to send
            client: Specific client to send to (None for broadcast)
        """
        message_str = json.dumps(message)

        if client:
            # Send to specific client
            try:
                await client.send(message_str)
            except websockets.exceptions.ConnectionClosed:
                logger.warning("Failed to send message - client disconnected")
                self._clients.discard(client)
        else:
            # Broadcast to all clients
            disconnected = []
            for client in self._clients:
                try:
                    await client.send(message_str)
                except websockets.exceptions.ConnectionClosed:
                    disconnected.append(client)

            # Remove disconnected clients
            for client in disconnected:
                self._clients.discard(client)

    async def receive_message(self) -> Dict[str, Any]:
        """Receive the next message from any connected client.

        Messages are enqueued by ``_handle_client`` as they arrive over
        WebSocket connections.  This method blocks until a message is
        available.

        Returns:
            Parsed JSON message dict.
        """
        return await self._message_queue.get()

    async def _handle_client(self, websocket: WebSocketServerProtocol, path: str):
        """Handle a client connection.

        Args:
            websocket: WebSocket connection
            path: Request path
        """
        client_addr = websocket.remote_address
        logger.info(f"Client connected from {client_addr}")

        # Add client to active set
        self._clients.add(websocket)

        try:
            # Send welcome message
            await self.send_message(
                {
                    "type": "welcome",
                    "version": "1.0",
                    "capabilities": ["tools", "resources", "prompts"],
                },
                websocket,
            )

            # Handle messages from this client
            async for message in websocket:
                try:
                    # Parse the message
                    data = json.loads(message)

                    # Add client reference to the message
                    data["_client"] = websocket

                    # Enqueue for receive_message() consumers
                    await self._message_queue.put(data)

                    # Handle the message if we have a handler
                    if self.message_handler:
                        response = await self.message_handler(data)

                        # Send response if provided
                        if response:
                            await self.send_message(response, websocket)

                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON from client: {e}")
                    await self.send_message(
                        {"type": "error", "error": "Invalid JSON message"}, websocket
                    )
                except Exception as e:
                    logger.error(f"Error handling message: {e}")
                    await self.send_message(
                        {
                            "type": "error",
                            "error": f"Internal error: {type(e).__name__}",
                        },
                        websocket,
                    )

        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Client disconnected from {client_addr}")
        except Exception as e:
            logger.error(f"Error in client handler: {e}")
        finally:
            # Remove client from active set
            self._clients.discard(websocket)

    async def broadcast_notification(self, notification: Dict[str, Any]) -> None:
        """Broadcast a notification to all connected clients.

        Args:
            notification: Notification message to broadcast
        """
        notification["type"] = "notification"
        await self.send_message(notification)

    def get_connected_clients(self) -> int:
        """Get the number of connected clients.

        Returns:
            Number of active client connections
        """
        return len(self._clients)

    async def wait_for_clients(
        self, min_clients: int = 1, timeout: float = 30.0
    ) -> bool:
        """Wait for a minimum number of clients to connect.

        Args:
            min_clients: Minimum number of clients to wait for
            timeout: Maximum time to wait in seconds

        Returns:
            True if minimum clients connected, False if timeout
        """
        start_time = asyncio.get_event_loop().time()

        while self.get_connected_clients() < min_clients:
            if asyncio.get_event_loop().time() - start_time > timeout:
                return False
            await asyncio.sleep(0.1)

        return True


class WebSocketClientTransport(MCPTransport):
    """WebSocket client transport for MCP.

    This transport implementation provides a WebSocket client for connecting
    to MCP servers. It's designed for client-side implementations that need
    to consume tools and resources from MCP servers.
    """

    def __init__(
        self,
        uri: str,
        message_handler: Optional[Callable] = None,
        max_message_size: int = 10 * 1024 * 1024,  # 10MB
    ):
        """Initialize WebSocket client transport.

        Args:
            uri: WebSocket URI to connect to (e.g., "ws://localhost:3001")
            message_handler: Async callable to handle incoming messages
            max_message_size: Maximum message size in bytes
        """
        self.uri = uri
        self.message_handler = message_handler
        self.max_message_size = max_message_size

        self._websocket = None
        self._running = False
        self._receive_task = None

    async def start(self):
        """Connect to the WebSocket server."""
        if self._running:
            logger.warning("WebSocket client already connected")
            return

        logger.info(f"Connecting to WebSocket server at {self.uri}")

        try:
            self._websocket = await websockets.connect(
                self.uri,
                max_size=self.max_message_size,
                ping_interval=20,
                ping_timeout=10,
            )

            self._running = True

            # Start receiving messages
            if self.message_handler:
                self._receive_task = asyncio.create_task(self._receive_loop())

            logger.info(f"Connected to WebSocket server at {self.uri}")

        except Exception as e:
            logger.error(f"Failed to connect to WebSocket server: {e}")
            raise

    async def stop(self):
        """Disconnect from the WebSocket server."""
        if not self._running:
            return

        logger.info("Disconnecting from WebSocket server")
        self._running = False

        # Cancel receive task
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

        # Close WebSocket connection
        if self._websocket:
            await self._websocket.close()
            self._websocket = None

        logger.info("Disconnected from WebSocket server")

    async def send_message(self, message: Dict[str, Any]) -> None:
        """Send a message to the server.

        Args:
            message: Message to send
        """
        if not self._websocket:
            raise RuntimeError("Not connected to WebSocket server")

        try:
            message_str = json.dumps(message)
            await self._websocket.send(message_str)
        except websockets.exceptions.ConnectionClosed:
            logger.error("Connection lost while sending message")
            self._running = False
            raise

    async def receive_message(self) -> Dict[str, Any]:
        """Receive a message from the server.

        Returns:
            Received message
        """
        if not self._websocket:
            raise RuntimeError("Not connected to WebSocket server")

        try:
            message = await self._websocket.recv()
            return json.loads(message)
        except websockets.exceptions.ConnectionClosed:
            logger.error("Connection lost while receiving message")
            self._running = False
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON received: {e}")
            raise

    async def _receive_loop(self):
        """Background task to receive and handle messages."""
        while self._running:
            try:
                message = await self.receive_message()

                if self.message_handler:
                    await self.message_handler(message)

            except websockets.exceptions.ConnectionClosed:
                logger.info("Connection closed by server")
                break
            except Exception as e:
                logger.error(f"Error in receive loop: {e}")
                if self._running:
                    await asyncio.sleep(1)  # Brief pause before retry

    def is_connected(self) -> bool:
        """Check if the client is connected.

        Returns:
            True if connected, False otherwise
        """
        return self._running and self._websocket and not self._websocket.closed
