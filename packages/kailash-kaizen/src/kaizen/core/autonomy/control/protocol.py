"""
Control Protocol Implementation

Implements the bidirectional communication protocol for autonomous agent capabilities.

Design Principles (from ADR-011):
- Use anyio.Event for request/response synchronization
- Use anyio.create_task_group for background tasks
- Use anyio.fail_after for timeout handling
- Thread-safe request tracking with dict[request_id, Event]
- Clean shutdown with proper task cancellation
- Explicit error handling (no silent failures)

Architecture:
    1. Transport Layer: Abstract bidirectional communication (Transport ABC)
    2. Protocol Layer: Request/response pairing and lifecycle (ControlProtocol)
    3. Message Layer: Type-safe request/response structures (ControlRequest/Response)

Example:
    transport = CLITransport()
    protocol = ControlProtocol(transport=transport)

    async with anyio.create_task_group() as tg:
        await protocol.start(tg)

        # Send request and wait for response
        request = ControlRequest.create("question", {"q": "Proceed?"})
        response = await protocol.send_request(request, timeout=60.0)

        if response.is_error:
            print(f"Error: {response.error}")
        else:
            print(f"Answer: {response.data}")

        await protocol.stop()

See Also:
    - kaizen.core.autonomy.control.transport.Transport
    - kaizen.core.autonomy.control.types.ControlRequest
    - kaizen.core.autonomy.control.types.ControlResponse
    - tests/unit/core/autonomy/control/test_protocol.py
"""

import json
import logging

import anyio
from anyio.abc import TaskGroup
from kaizen.core.autonomy.control.transport import Transport, TransportProtocol
from kaizen.core.autonomy.control.types import ControlRequest, ControlResponse

logger = logging.getLogger(__name__)


class ControlProtocol:
    """
    Control protocol for bidirectional agent-client communication.

    Manages request/response pairing, background message reading, and protocol
    lifecycle. Uses anyio for async operations and event-based synchronization.

    The protocol:
    1. Starts background message reader on start()
    2. Pairs responses with requests using request_id
    3. Handles timeouts using anyio.fail_after
    4. Cleans up gracefully on stop()

    Thread Safety:
        All operations are async and use anyio primitives for synchronization.
        The _pending_requests dict is protected by the async nature of operations.

    Attributes:
        _transport: Transport instance for bidirectional communication
        _pending_requests: Maps request_id -> (Event, ControlResponse placeholder)
        _reader_task: Background task reading messages from transport
        _started: Whether protocol has been started

    Example:
        transport = MockTransport()
        await transport.connect()

        protocol = ControlProtocol(transport=transport)

        async with anyio.create_task_group() as tg:
            await protocol.start(tg)

            request = ControlRequest.create("question", {"q": "Continue?"})
            response = await protocol.send_request(request, timeout=60.0)

            print(f"Response: {response.data}")

            await protocol.stop()
    """

    def __init__(self, transport: Transport):
        """
        Initialize control protocol with transport.

        Args:
            transport: Transport instance for communication

        Raises:
            TypeError: If transport is not a Transport instance

        Example:
            transport = CLITransport()
            protocol = ControlProtocol(transport=transport)
        """
        # Validate transport
        if not isinstance(transport, (Transport, TransportProtocol)):
            raise TypeError(
                f"transport must be a Transport instance, got {type(transport).__name__}. "
                f"Provide a valid Transport implementation (CLITransport, HTTPTransport, etc.)"
            )

        self._transport = transport

        # Request tracking: request_id -> (Event, response_container)
        # Using list as mutable container for response since Event can't hold data
        self._pending_requests: dict[
            str, tuple[anyio.Event, list[ControlResponse | None]]
        ] = {}

        # Background reader task (start_soon doesn't return handle, so use boolean)
        self._reader_task: bool = False  # True when background reader is running

        # Protocol state
        self._started = False

        logger.debug(
            f"ControlProtocol initialized with transport: {type(transport).__name__}"
        )

    async def start(self, task_group: TaskGroup) -> None:
        """
        Start the control protocol.

        Connects transport and launches background message reader in the provided
        task group. Must be called before send_request().

        Args:
            task_group: anyio TaskGroup to run background reader in

        Raises:
            RuntimeError: If already started
            ConnectionError: If transport connection fails

        Example:
            async with anyio.create_task_group() as tg:
                await protocol.start(tg)
                # ... send requests ...
                await protocol.stop()
        """
        if self._started:
            raise RuntimeError(
                "Protocol already started. " "Call stop() before starting again."
            )

        logger.info("Starting ControlProtocol")

        # Connect transport if not already connected
        if not self._transport.is_ready():
            try:
                await self._transport.connect()
                logger.debug("Transport connected successfully")
            except Exception as e:
                raise ConnectionError(f"Failed to connect transport: {e}") from e

        # Launch background message reader
        task_group.start_soon(self._read_messages)
        self._reader_task = True  # Mark reader as running
        self._started = True

        logger.info("ControlProtocol started successfully")

    async def stop(self) -> None:
        """
        Stop the control protocol gracefully.

        Closes transport, cancels pending requests, and cleans up resources.
        Idempotent - safe to call multiple times.

        Example:
            await protocol.stop()
            await protocol.stop()  # Safe to call again
        """
        if not self._started:
            logger.debug("Protocol not started, nothing to stop")
            return  # Already stopped, idempotent

        logger.info("Stopping ControlProtocol")

        # Close transport
        try:
            await self._transport.close()
            logger.debug("Transport closed successfully")
        except Exception as e:
            logger.warning(f"Error closing transport: {e}")

        # Clear pending requests (background reader will be cancelled by task group)
        num_pending = len(self._pending_requests)
        if num_pending > 0:
            logger.warning(f"Clearing {num_pending} pending requests during shutdown")

        self._pending_requests.clear()
        self._reader_task = False  # Mark reader as not running
        self._started = False

        logger.info("ControlProtocol stopped successfully")

    async def send_request(
        self, request: ControlRequest, timeout: float = 60.0
    ) -> ControlResponse:
        """
        Send request and wait for response with timeout.

        Writes request to transport, waits for matching response by request_id,
        and returns the response. Uses anyio.fail_after for timeout handling.

        Args:
            request: ControlRequest to send
            timeout: Maximum seconds to wait for response (default: 60.0)

        Returns:
            ControlResponse from client

        Raises:
            RuntimeError: If protocol not started
            TimeoutError: If no response received within timeout
            ConnectionError: If transport write fails

        Example:
            request = ControlRequest.create("approval", {"action": "delete"})
            response = await protocol.send_request(request, timeout=30.0)

            if response.is_error:
                raise RuntimeError(f"Request failed: {response.error}")

            print(f"Approved: {response.data['approved']}")
        """
        if not self._started:
            raise RuntimeError(
                "Protocol not started. " "Call start() before sending requests."
            )

        request_id = request.request_id
        logger.debug(f"Sending request: {request_id}")

        # Create event and response container for this request
        event = anyio.Event()
        response_container: list[ControlResponse | None] = [None]

        # Register pending request
        self._pending_requests[request_id] = (event, response_container)

        try:
            # Write request to transport
            try:
                request_json = request.to_json()
                await self._transport.write(request_json)
                logger.debug(f"Request written to transport: {request_id}")
            except Exception as e:
                # Clean up on write failure
                del self._pending_requests[request_id]
                raise ConnectionError(
                    f"Failed to write request to transport: {e}"
                ) from e

            # Wait for response with timeout
            try:
                with anyio.fail_after(timeout):
                    await event.wait()
                    logger.debug(f"Response received for request: {request_id}")
            except TimeoutError:
                logger.warning(f"Request timed out after {timeout}s: {request_id}")
                # Clean up timed out request
                del self._pending_requests[request_id]
                raise TimeoutError(
                    f"No response received for request '{request_id}' within {timeout} seconds. "
                    f"Check that client is responding to requests."
                )

            # Extract response from container
            response = response_container[0]
            if response is None:
                # Should never happen if event was set correctly
                raise RuntimeError(
                    f"Response container empty for request '{request_id}'. "
                    f"This indicates a protocol implementation bug."
                )

            return response

        finally:
            # Always clean up pending request
            self._pending_requests.pop(request_id, None)

    async def _read_messages(self) -> None:
        """
        Background task to read messages from transport and pair with requests.

        Runs continuously, reading messages from transport.read_messages() and
        matching responses to pending requests by request_id.

        Handles:
        - Valid responses: Sets event to wake up waiting request
        - Invalid JSON: Logs warning and continues
        - Unsolicited responses: Logs warning and ignores
        - Transport errors: Logs error and exits gracefully

        This method runs in the background task group and is cancelled on stop().
        """
        logger.info("Background message reader started")

        try:
            async for message in self._transport.read_messages():
                try:
                    # Parse response
                    try:
                        response_data = json.loads(message)
                        response = ControlResponse.from_dict(response_data)
                    except json.JSONDecodeError as e:
                        logger.warning(f"Received invalid JSON message: {e}")
                        continue  # Skip malformed messages
                    except (KeyError, ValueError) as e:
                        logger.warning(f"Received malformed response: {e}")
                        continue  # Skip invalid responses

                    request_id = response.request_id

                    # Check if we're waiting for this response
                    if request_id not in self._pending_requests:
                        logger.warning(
                            f"Received unsolicited response for request_id: {request_id}. "
                            f"No pending request found."
                        )
                        continue  # Ignore unsolicited responses

                    # Get event and response container
                    event, response_container = self._pending_requests[request_id]

                    # Check for duplicate response
                    if response_container[0] is not None:
                        logger.warning(
                            f"Received duplicate response for request_id: {request_id}. "
                            f"Ignoring duplicate."
                        )
                        continue  # Ignore duplicates

                    # Store response and signal event
                    response_container[0] = response
                    event.set()

                    logger.debug(f"Paired response with request: {request_id}")

                except Exception as e:
                    # Log unexpected errors but continue reading
                    logger.error(f"Error processing message: {e}", exc_info=True)

        except anyio.get_cancelled_exc_class():
            logger.info("Background message reader cancelled (protocol stopped)")
            raise  # Re-raise to properly cancel task

        except Exception as e:
            logger.error(f"Background message reader error: {e}", exc_info=True)

        finally:
            logger.info("Background message reader exited")


__all__ = ["ControlProtocol"]
