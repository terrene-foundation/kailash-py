#!/usr/bin/env python3
"""
Web Interactive Agent with Server-Sent Events (SSE)

Demonstrates HTTPTransport for bidirectional agent ↔ user communication via web browser.

This example shows:
1. Agent asking questions to user via web UI
2. Real-time progress updates via Server-Sent Events (SSE)
3. Request approval workflow
4. Bidirectional communication over HTTP

Architecture:
- Agent runs as HTTP server with two endpoints:
  - POST /control: Receives user responses
  - GET /stream: Sends agent requests via SSE
- Web UI (web_ui.html) displays questions and sends responses
- ControlProtocol manages request/response pairing

Usage:
    # Terminal 1: Start agent server
    python examples/autonomy/web_interactive_agent.py

    # Terminal 2: Open web UI
    open examples/autonomy/web_ui.html

    # Or visit: http://localhost:8765/ui

See Also:
    - examples/autonomy/cli_interactive_agent.py - CLI version
    - docs/architecture/adr/011-control-protocol-architecture.md
"""

import asyncio
import sys
from pathlib import Path
from typing import Any

# Add src to path for examples
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from aiohttp import web
from kaizen.core.autonomy.control.types import ControlRequest, ControlResponse


class WebInteractiveAgent:
    """
    Interactive agent that communicates with users via web interface.

    Uses HTTPTransport-style endpoints:
    - POST /control: Receive user responses
    - GET /stream: Send agent questions via SSE
    - GET /ui: Serve web interface
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        """
        Initialize web interactive agent.

        Args:
            host: Server host address
            port: Server port number
        """
        self.host = host
        self.port = port
        self.app = web.Application()
        self.runner = None

        # Message queues for bidirectional communication
        self.request_queue: asyncio.Queue = asyncio.Queue()
        self.response_queues: dict[str, asyncio.Queue] = {}

        # Active SSE connections
        self.sse_clients: list[asyncio.Queue] = []

        # Setup routes
        self.app.router.add_post("/control", self._handle_control)
        self.app.router.add_get("/stream", self._handle_stream)
        self.app.router.add_get("/ui", self._serve_ui)
        self.app.router.add_get("/health", self._handle_health)

    async def start(self):
        """Start web server."""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, self.host, self.port)
        await site.start()
        print(f"🌐 Web agent server running at http://{self.host}:{self.port}")
        print(f"📊 Open web UI at http://{self.host}:{self.port}/ui")
        print(f"🔌 SSE stream at http://{self.host}:{self.port}/stream")
        print()

    async def stop(self):
        """Stop web server."""
        if self.runner:
            await self.runner.cleanup()

    async def _handle_control(self, request: web.Request) -> web.Response:
        """
        Handle POST /control - Receive user responses.

        Endpoint for web UI to send user responses back to agent.
        """
        try:
            data = await request.json()
            response = ControlResponse(
                request_id=data.get("request_id"),
                data=data.get("data"),
                error=data.get("error"),
            )

            # Store response for waiting request
            request_id = response.request_id
            if request_id in self.response_queues:
                await self.response_queues[request_id].put(response)

            return web.json_response({"status": "received"})

        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def _handle_stream(self, request: web.Request) -> web.StreamResponse:
        """
        Handle GET /stream - Send agent questions via SSE.

        Server-Sent Events endpoint for real-time agent → user communication.
        """
        response = web.StreamResponse()
        response.headers["Content-Type"] = "text/event-stream"
        response.headers["Cache-Control"] = "no-cache"
        response.headers["Connection"] = "keep-alive"

        await response.prepare(request)

        # Create queue for this client
        client_queue: asyncio.Queue = asyncio.Queue()
        self.sse_clients.append(client_queue)

        try:
            # Send keep-alive and messages
            while True:
                try:
                    # Wait for message or timeout
                    message = await asyncio.wait_for(client_queue.get(), timeout=5.0)

                    # Send SSE formatted message
                    await response.write(f"data: {message}\n\n".encode())
                    await response.drain()

                except asyncio.TimeoutError:
                    # Send keep-alive comment
                    await response.write(b": keepalive\n\n")
                    await response.drain()

        except (ConnectionResetError, asyncio.CancelledError):
            pass
        finally:
            # Remove client on disconnect
            if client_queue in self.sse_clients:
                self.sse_clients.remove(client_queue)

        return response

    async def _serve_ui(self, request: web.Request) -> web.Response:
        """
        Handle GET /ui - Serve web interface.

        Returns the HTML web UI for interacting with the agent.
        """
        ui_path = Path(__file__).parent / "web_ui.html"

        if not ui_path.exists():
            return web.Response(
                text="Web UI not found. Please create web_ui.html", status=404
            )

        html_content = ui_path.read_text()
        return web.Response(text=html_content, content_type="text/html")

    async def _handle_health(self, request: web.Request) -> web.Response:
        """Handle GET /health - Health check."""
        return web.json_response(
            {"status": "healthy", "active_sse_clients": len(self.sse_clients)}
        )

    async def send_request(
        self, request_type: str, data: dict[str, Any], timeout: float = 60.0
    ) -> ControlResponse:
        """
        Send request to user and wait for response.

        Args:
            request_type: Type of request (question, approval, progress)
            data: Request data
            timeout: Response timeout in seconds

        Returns:
            ControlResponse from user

        Raises:
            TimeoutError: If user doesn't respond within timeout
        """
        # Create request
        request = ControlRequest.create(request_type, data)

        # Create response queue
        response_queue: asyncio.Queue = asyncio.Queue()
        self.response_queues[request.request_id] = response_queue

        try:
            # Broadcast to all SSE clients
            message = request.to_json()
            for client_queue in self.sse_clients:
                try:
                    client_queue.put_nowait(message)
                except asyncio.QueueFull:
                    pass

            # Wait for response with timeout
            try:
                response = await asyncio.wait_for(response_queue.get(), timeout=timeout)
                return response
            except asyncio.TimeoutError:
                raise TimeoutError(
                    f"Request timeout: {request_type} "
                    f"(request_id={request.request_id}, timeout={timeout}s)"
                )
        finally:
            # Cleanup
            self.response_queues.pop(request.request_id, None)

    async def ask_question(
        self, question: str, options: list[str] | None = None, timeout: float = 60.0
    ) -> str:
        """
        Ask user a question via web UI.

        Args:
            question: Question to ask
            options: Optional list of answer choices
            timeout: Response timeout

        Returns:
            User's answer as string
        """
        data = {"question": question}
        if options:
            data["options"] = options

        response = await self.send_request("question", data, timeout)

        if response.is_error:
            raise RuntimeError(f"Question error: {response.error}")

        return response.data.get("answer", "")

    async def request_approval(
        self, action: str, details: dict[str, Any] | None = None, timeout: float = 60.0
    ) -> bool:
        """
        Request user approval for an action.

        Args:
            action: Description of action needing approval
            details: Additional context
            timeout: Response timeout

        Returns:
            True if approved, False if denied
        """
        data = {"action": action}
        if details:
            data["details"] = details

        response = await self.send_request("approval", data, timeout)

        if response.is_error:
            raise RuntimeError(f"Approval error: {response.error}")

        return response.data.get("approved", False)

    async def send_progress(self, message: str, percent: float):
        """
        Send progress update to web UI.

        Args:
            message: Progress message
            percent: Completion percentage (0-100)
        """
        request = ControlRequest.create(
            "progress", {"message": message, "percent": percent}
        )

        # Broadcast to all SSE clients
        message_json = request.to_json()
        for client_queue in self.sse_clients:
            try:
                client_queue.put_nowait(message_json)
            except asyncio.QueueFull:
                pass


async def agent_workflow(agent: WebInteractiveAgent):
    """
    Example agent workflow demonstrating interactive capabilities.

    Shows:
    - Asking questions
    - Requesting approval
    - Progress updates
    """
    print("🤖 Agent workflow starting...")
    print("📊 Waiting for web UI connection...")

    # Wait for at least one SSE client
    while len(agent.sse_clients) == 0:
        await asyncio.sleep(0.5)

    print("✅ Web UI connected!")
    print()

    try:
        # Step 1: Ask user's name
        await agent.send_progress("Starting workflow...", 0)

        name = await agent.ask_question("What is your name?", timeout=120.0)
        print(f"👤 User name: {name}")

        # Step 2: Ask favorite color
        await agent.send_progress(f"Hello {name}! Getting preferences...", 25)

        color = await agent.ask_question(
            "What is your favorite color?",
            options=["Red", "Blue", "Green", "Yellow"],
            timeout=120.0,
        )
        print(f"🎨 Favorite color: {color}")

        # Step 3: Request approval for action
        await agent.send_progress("Requesting approval...", 50)

        approved = await agent.request_approval(
            f"Create a file named '{name}_{color}.txt'",
            details={
                "filename": f"{name}_{color}.txt",
                "content": f"Hello {name}! Your favorite color is {color}.",
            },
            timeout=120.0,
        )

        if approved:
            print("✅ Action approved!")
            await agent.send_progress("Creating file...", 75)

            # Simulate work
            await asyncio.sleep(1)

            print(f"📄 File created: {name}_{color}.txt")
            await agent.send_progress("Workflow complete!", 100)
        else:
            print("❌ Action denied by user")
            await agent.send_progress("Workflow cancelled by user", 100)

        print()
        print("🎉 Agent workflow complete!")

    except TimeoutError as e:
        print(f"⏱️  Timeout: {e}")
        await agent.send_progress("Workflow timed out", 100)
    except Exception as e:
        print(f"❌ Error: {e}")
        await agent.send_progress(f"Error: {e}", 100)


async def main():
    """Main entry point."""
    print("=" * 70)
    print("Web Interactive Agent with Server-Sent Events (SSE)")
    print("=" * 70)
    print()

    # Create and start agent
    agent = WebInteractiveAgent(host="127.0.0.1", port=8765)

    try:
        await agent.start()

        # Run workflow
        await agent_workflow(agent)

        # Keep server running
        print()
        print("Press Ctrl+C to stop the agent...")
        while True:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        print("\n🛑 Shutting down agent...")
    finally:
        await agent.stop()
        print("👋 Agent stopped")


if __name__ == "__main__":
    asyncio.run(main())
