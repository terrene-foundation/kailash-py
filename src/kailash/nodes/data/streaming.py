"""Streaming data nodes for the Kailash system.

This module provides nodes for handling streaming data sources and sinks.
Key features include:

- Real-time data ingestion (Kafka, RabbitMQ, WebSockets)
- Stream processing and transformation
- Event-driven architectures
- Backpressure handling
- Message acknowledgment

Design Philosophy:
- Support various streaming protocols
- Handle backpressure gracefully
- Provide reliable message delivery
- Enable stream transformations
- Support both push and pull models

Common Use Cases:
- Real-time data pipelines
- Event sourcing systems
- Log aggregation
- Monitoring and alerting
- Live data feeds

Example:
    >>> # Consume from Kafka
    >>> consumer = KafkaConsumerNode()
    >>> consumer.configure({
    ...     "bootstrap_servers": "localhost:9092",
    ...     "topic": "events",
    ...     "group_id": "my-group",
    ...     "auto_offset_reset": "earliest"
    ... })
    >>> result = consumer.execute({"max_messages": 100})
    >>>
    >>> # Publish to stream
    >>> publisher = StreamPublisherNode()
    >>> publisher.configure({
    ...     "protocol": "websocket",
    ...     "url": "ws://localhost:8080/stream"
    ... })
    >>> publisher.execute({"messages": result["messages"]})
"""

import time
from typing import Any, Dict, List

from kailash.nodes.base import Node, NodeMetadata, NodeParameter, register_node
from kailash.sdk_exceptions import NodeConfigurationError, NodeExecutionError


@register_node()
class KafkaConsumerNode(Node):
    """Consumes messages from Apache Kafka topics.

    This node provides a high-level interface for consuming messages from
    Kafka topics with support for consumer groups, offset management, and
    error handling.

    Design Pattern:
    - Observer pattern for message consumption
    - Iterator pattern for message streaming
    - Template method for processing

    Features:
    - Consumer group support
    - Automatic offset management
    - Message deserialization
    - Error recovery
    - Batch consumption
    - SSL/SASL authentication

    Common Usage Patterns:
    - Event stream processing
    - Log aggregation
    - Real-time analytics
    - Microservice communication
    - Data synchronization

    Upstream Dependencies:
    - Configuration nodes
    - Schema registry nodes
    - Authentication nodes

    Downstream Consumers:
    - Processing nodes
    - Storage nodes
    - Analytics nodes
    - Notification nodes

    Configuration:
        bootstrap_servers (str): Kafka broker addresses
        topic (str): Topic to consume from
        group_id (str): Consumer group ID
        auto_offset_reset (str): Where to start reading
        max_poll_records (int): Max messages per poll
        enable_auto_commit (bool): Auto commit offsets
        security_protocol (str): Security protocol
        sasl_mechanism (str): SASL mechanism
        sasl_username (str): SASL username
        sasl_password (str): SASL password

    Inputs:
        max_messages (int): Maximum messages to consume
        timeout_ms (int): Poll timeout in milliseconds

    Outputs:
        messages (List[Dict]): Consumed messages
        metadata (Dict): Consumer metadata

    Error Handling:
    - Connection failures with retry
    - Deserialization errors
    - Offset management errors
    - Authentication failures

    Example:
        >>> consumer = KafkaConsumerNode()
        >>> consumer.configure({
        ...     "bootstrap_servers": "localhost:9092",
        ...     "topic": "user-events",
        ...     "group_id": "analytics-group",
        ...     "auto_offset_reset": "latest",
        ...     "max_poll_records": 500
        ... })
        >>> result = consumer.execute({
        ...     "max_messages": 1000,
        ...     "timeout_ms": 5000
        ... })
        >>> print(f"Consumed {len(result['messages'])} messages")
    """

    metadata = NodeMetadata(
        name="KafkaConsumerNode",
        description="Consumes messages from Kafka",
        version="1.0.0",
        tags={"streaming", "kafka", "consumer"},
    )

    def __init__(self):
        """Initialize the Kafka consumer node.

        Sets up the node and prepares for consumer initialization.
        The actual consumer is created during configuration.
        """
        super().__init__()
        self._consumer = None
        self._topic = None

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define parameters for the Kafka consumer node."""
        return {
            "bootstrap_servers": NodeParameter(
                name="bootstrap_servers",
                type=str,
                description="Kafka broker addresses",
                required=True,
            ),
            "topic": NodeParameter(
                name="topic",
                type=str,
                description="Topic to consume from",
                required=True,
            ),
            "group_id": NodeParameter(
                name="group_id",
                type=str,
                description="Consumer group ID",
                required=True,
            ),
            "auto_offset_reset": NodeParameter(
                name="auto_offset_reset",
                type=str,
                description="Where to start reading",
                required=False,
                default="latest",
            ),
            "max_poll_records": NodeParameter(
                name="max_poll_records",
                type=int,
                description="Max messages per poll",
                required=False,
                default=500,
            ),
            "enable_auto_commit": NodeParameter(
                name="enable_auto_commit",
                type=bool,
                description="Auto commit offsets",
                required=False,
                default=True,
            ),
            "security_protocol": NodeParameter(
                name="security_protocol",
                type=str,
                description="Security protocol",
                required=False,
                default="PLAINTEXT",
            ),
            "value_deserializer": NodeParameter(
                name="value_deserializer",
                type=str,
                description="Message deserializer",
                required=False,
                default="json",
            ),
        }

    def configure(self, config: Dict[str, Any]) -> None:
        """Configure the Kafka consumer.

        Creates and configures the Kafka consumer with the specified
        settings including security, serialization, and consumer group.

        Args:
            config: Configuration dictionary

        Raises:
            NodeConfigurationError: If configuration fails
        """
        super().configure(config)

        required_fields = ["bootstrap_servers", "topic", "group_id"]
        for field in required_fields:
            if not self.config.get(field):
                raise NodeConfigurationError(f"{field} is required")

        try:
            # Placeholder for actual consumer creation
            self._create_consumer()
        except Exception as e:
            raise NodeConfigurationError(f"Failed to create consumer: {str(e)}")

    def _create_consumer(self) -> None:
        """Create the Kafka consumer instance.

        Initializes the consumer with all configured settings.
        This is a placeholder for actual consumer creation.
        """
        # Placeholder for actual consumer creation
        self._consumer = f"kafka_consumer_{self.config['group_id']}"
        self._topic = self.config["topic"]

    def run(self, **kwargs) -> Dict[str, Any]:
        """Consume messages from Kafka.

        Implementation of the abstract run method from the base Node class.

        Args:
            **kwargs: Keyword arguments for consumption

        Returns:
            Consumed messages and metadata
        """
        return self.execute(kwargs)

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Consume messages from Kafka.

        Polls for messages up to the specified limit or timeout.

        Args:
            inputs: Execution parameters

        Returns:
            Consumed messages and metadata

        Raises:
            NodeExecutionError: If consumption fails
        """
        try:
            max_messages = inputs.get("max_messages", 100)
            timeout_ms = inputs.get("timeout_ms", 1000)

            messages = self._consume_messages(max_messages, timeout_ms)

            return {
                "messages": messages,
                "metadata": {
                    "topic": self._topic,
                    "group_id": self.config["group_id"],
                    "message_count": len(messages),
                    "timestamp": time.time(),
                },
            }
        except Exception as e:
            raise NodeExecutionError(f"Failed to consume messages: {str(e)}")

    def _consume_messages(self, max_messages: int, timeout_ms: int) -> List[Dict]:
        """Consume messages from Kafka.

        This is a placeholder for actual message consumption logic.

        Args:
            max_messages: Maximum messages to consume
            timeout_ms: Poll timeout

        Returns:
            List of consumed messages
        """
        # Placeholder implementation
        messages = []
        for i in range(min(max_messages, 10)):  # Simulate consuming up to 10 messages
            messages.append(
                {
                    "key": f"key_{i}",
                    "value": {"event": f"event_{i}", "timestamp": time.time()},
                    "partition": i % 3,
                    "offset": i,
                    "timestamp": time.time(),
                }
            )
        return messages

    def cleanup(self) -> None:
        """Clean up consumer resources.

        Closes the consumer connection and releases resources.
        """
        if self._consumer:
            # Placeholder for actual cleanup
            self._consumer = None
        super().cleanup()


@register_node()
class StreamPublisherNode(Node):
    """Publishes messages to various streaming platforms.

    This node provides a unified interface for publishing messages to
    different streaming platforms including Kafka, RabbitMQ, WebSockets,
    and server-sent events (SSE).

    Design Pattern:
    - Adapter pattern for different protocols
    - Producer pattern for message publishing
    - Strategy pattern for serialization

    Features:
    - Multi-protocol support
    - Message batching
    - Retry logic
    - Async publishing
    - Compression support
    - Dead letter queues

    Common Usage Patterns:
    - Event publishing
    - Real-time notifications
    - Data distribution
    - Log forwarding
    - Metric emission

    Upstream Dependencies:
    - Processing nodes
    - Transformation nodes
    - Aggregation nodes

    Downstream Consumers:
    - Other streaming systems
    - Analytics platforms
    - Storage systems
    - Monitoring tools

    Configuration:
        protocol (str): Streaming protocol to use
        endpoint (str): Server endpoint/URL
        topic (str): Topic/channel to publish to
        auth_type (str): Authentication type
        batch_size (int): Message batch size
        compression (str): Compression algorithm
        retry_count (int): Number of retries

    Inputs:
        messages (List[Dict]): Messages to publish
        headers (Dict): Optional message headers

    Outputs:
        published_count (int): Number of messages published
        failed_messages (List[Dict]): Failed messages
        metadata (Dict): Publishing metadata

    Error Handling:
    - Connection failures
    - Serialization errors
    - Rate limiting
    - Authentication errors

    Example:
        >>> publisher = StreamPublisherNode()
        >>> publisher.configure({
        ...     "protocol": "kafka",
        ...     "endpoint": "localhost:9092",
        ...     "topic": "processed-events",
        ...     "batch_size": 100,
        ...     "compression": "gzip"
        ... })
        >>> result = publisher.execute({
        ...     "messages": [
        ...         {"id": 1, "event": "user_login"},
        ...         {"id": 2, "event": "page_view"}
        ...     ]
        ... })
        >>> print(f"Published {result['published_count']} messages")
    """

    metadata = NodeMetadata(
        name="StreamPublisherNode",
        description="Publishes to streaming platforms",
        version="1.0.0",
        tags={"streaming", "publisher", "messaging"},
    )

    def __init__(self):
        """Initialize the stream publisher node.

        Sets up the node and prepares for publisher initialization.
        """
        super().__init__()
        self._publisher = None
        self._protocol = None

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define parameters for the stream publisher node."""
        return {
            "protocol": NodeParameter(
                name="protocol",
                type=str,
                description="Streaming protocol",
                required=True,
            ),
            "endpoint": NodeParameter(
                name="endpoint", type=str, description="Server endpoint", required=True
            ),
            "topic": NodeParameter(
                name="topic", type=str, description="Topic/channel name", required=True
            ),
            "auth_type": NodeParameter(
                name="auth_type",
                type=str,
                description="Authentication type",
                required=False,
                default="none",
            ),
            "batch_size": NodeParameter(
                name="batch_size",
                type=int,
                description="Message batch size",
                required=False,
                default=100,
            ),
            "compression": NodeParameter(
                name="compression",
                type=str,
                description="Compression algorithm",
                required=False,
                default="none",
            ),
            "retry_count": NodeParameter(
                name="retry_count",
                type=int,
                description="Number of retries",
                required=False,
                default=3,
            ),
        }

    def configure(self, config: Dict[str, Any]) -> None:
        """Configure the stream publisher.

        Creates the appropriate publisher based on the protocol.

        Args:
            config: Configuration dictionary

        Raises:
            NodeConfigurationError: If configuration fails
        """
        super().configure(config)

        required_fields = ["protocol", "endpoint", "topic"]
        for field in required_fields:
            if not self.config.get(field):
                raise NodeConfigurationError(f"{field} is required")

        self._protocol = self.config["protocol"]

        try:
            # Placeholder for actual publisher creation
            self._create_publisher()
        except Exception as e:
            raise NodeConfigurationError(f"Failed to create publisher: {str(e)}")

    def _create_publisher(self) -> None:
        """Create the appropriate publisher instance.

        This is a placeholder for actual publisher creation.
        """
        # Placeholder for actual publisher creation
        self._publisher = f"{self._protocol}_publisher"

    def run(self, **kwargs) -> Dict[str, Any]:
        """Publish messages to the streaming platform.

        Implementation of the abstract run method from the base Node class.

        Args:
            **kwargs: Messages and optional headers

        Returns:
            Publishing results
        """
        return self.execute(kwargs)

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Publish messages to the streaming platform.

        Args:
            inputs: Messages and optional headers

        Returns:
            Publishing results

        Raises:
            NodeExecutionError: If publishing fails
        """
        try:
            messages = inputs.get("messages", [])
            headers = inputs.get("headers", {})

            if not messages:
                return {
                    "published_count": 0,
                    "failed_messages": [],
                    "metadata": {"protocol": self._protocol},
                }

            results = self._publish_messages(messages, headers)

            return results
        except Exception as e:
            raise NodeExecutionError(f"Failed to publish messages: {str(e)}")

    def _publish_messages(self, messages: List[Dict], headers: Dict) -> Dict[str, Any]:
        """Publish messages to the stream.

        This is a placeholder for actual publishing logic.

        Args:
            messages: Messages to publish
            headers: Optional headers

        Returns:
            Publishing results
        """
        # Placeholder implementation
        batch_size = self.config.get("batch_size", 100)
        published_count = 0
        failed_messages = []

        for i in range(0, len(messages), batch_size):
            batch = messages[i : i + batch_size]
            # Simulate publishing with 95% success rate
            for msg in batch:
                if hash(str(msg)) % 100 < 95:  # Simulate 95% success
                    published_count += 1
                else:
                    failed_messages.append(msg)

        return {
            "published_count": published_count,
            "failed_messages": failed_messages,
            "metadata": {
                "protocol": self._protocol,
                "topic": self.config["topic"],
                "batch_size": batch_size,
                "timestamp": time.time(),
            },
        }


@register_node()
class WebSocketNode(Node):
    """Handles WebSocket connections for bidirectional streaming.

    This node provides WebSocket client functionality for real-time
    bidirectional communication with servers, supporting both sending
    and receiving messages.

    Design Pattern:
    - Observer pattern for message events
    - State pattern for connection states
    - Command pattern for message handling

    Features:
    - Auto-reconnection
    - Message queuing
    - Event callbacks
    - Heartbeat/ping-pong
    - SSL/TLS support
    - Custom headers

    Common Usage Patterns:
    - Real-time chat systems
    - Live data feeds
    - Collaborative applications
    - Gaming backends
    - IoT communication

    Upstream Dependencies:
    - Authentication nodes
    - Message formatting nodes
    - Configuration nodes

    Downstream Consumers:
    - UI update nodes
    - Storage nodes
    - Processing nodes
    - Analytics nodes

    Configuration:
        url (str): WebSocket URL
        headers (Dict): Connection headers
        reconnect (bool): Auto-reconnect on disconnect
        ping_interval (int): Heartbeat interval
        ssl_verify (bool): Verify SSL certificates

    Inputs:
        action (str): Action to perform ("connect", "send", "receive", "disconnect")
        message (Any): Message to send (for "send" action)
        timeout (float): Receive timeout (for "receive" action)

    Outputs:
        status (str): Connection status
        messages (List[Any]): Received messages
        metadata (Dict): Connection metadata

    Error Handling:
    - Connection failures
    - Message serialization
    - Timeout handling
    - SSL errors

    Example:
        >>> ws_node = WebSocketNode()
        >>> ws_node.configure({
        ...     "url": "wss://example.com/socket",
        ...     "headers": {"Authorization": "Bearer token"},
        ...     "reconnect": True,
        ...     "ping_interval": 30
        ... })
        >>>
        >>> # Connect
        >>> ws_node.execute({"action": "connect"})
        >>>
        >>> # Send message
        >>> ws_node.execute({
        ...     "action": "send",
        ...     "message": {"type": "subscribe", "channel": "updates"}
        ... })
        >>>
        >>> # Receive messages
        >>> result = ws_node.execute({
        ...     "action": "receive",
        ...     "timeout": 5.0
        ... })
    """

    metadata = NodeMetadata(
        name="WebSocketNode",
        description="WebSocket client for streaming",
        version="1.0.0",
        tags={"streaming", "websocket", "data"},
    )

    def __init__(self):
        """Initialize the WebSocket node.

        Sets up the node and prepares for WebSocket connection.
        """
        super().__init__()
        self._ws = None
        self._connected = False
        self._message_queue = []

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Get the parameters for this node.

        Returns:
            Parameter definitions for configuration and execution
        """
        return {
            "url": NodeParameter(
                name="url", type=str, description="WebSocket URL", required=True
            ),
            "headers": NodeParameter(
                name="headers",
                type=dict,
                description="Connection headers",
                required=False,
                default={},
            ),
            "reconnect": NodeParameter(
                name="reconnect",
                type=bool,
                description="Auto-reconnect on disconnect",
                required=False,
                default=True,
            ),
            "ping_interval": NodeParameter(
                name="ping_interval",
                type=int,
                description="Heartbeat interval in seconds",
                required=False,
                default=30,
            ),
            "ssl_verify": NodeParameter(
                name="ssl_verify",
                type=bool,
                description="Verify SSL certificates",
                required=False,
                default=True,
            ),
            "max_reconnect_attempts": NodeParameter(
                name="max_reconnect_attempts",
                type=int,
                description="Maximum reconnection attempts",
                required=False,
                default=5,
            ),
            "action": NodeParameter(
                name="action",
                type=str,
                description="Action to perform (connect, send, receive, disconnect)",
                required=False,
                default="receive",
            ),
            "message": NodeParameter(
                name="message",
                type=Any,
                description="Message to send (for send action)",
                required=False,
            ),
            "timeout": NodeParameter(
                name="timeout",
                type=float,
                description="Receive timeout (for receive action)",
                required=False,
                default=1.0,
            ),
        }

    def configure(self, config: Dict[str, Any]) -> None:
        """Configure the WebSocket connection.

        Validates the URL and prepares connection parameters.

        Args:
            config: Configuration dictionary

        Raises:
            NodeConfigurationError: If configuration is invalid
        """
        super().configure(config)

        if not self.config.get("url"):
            raise NodeConfigurationError("WebSocket URL is required")

        url = self.config["url"]
        if not url.startswith(("ws://", "wss://")):
            raise NodeConfigurationError("URL must start with ws:// or wss://")

    def run(self, **kwargs) -> Dict[str, Any]:
        """Run the WebSocket node.

        This method fulfills the abstract run method requirement from the base Node class.

        Args:
            **kwargs: Input parameters

        Returns:
            Operation results

        Raises:
            NodeExecutionError: If execution fails
        """
        return self.execute(kwargs)

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Execute WebSocket operations.

        Performs the requested action (connect, send, receive, disconnect).

        Args:
            inputs: Action and parameters

        Returns:
            Operation results

        Raises:
            NodeExecutionError: If operation fails
        """
        try:
            action = inputs.get("action", "receive")

            if action == "connect":
                return self._connect()
            elif action == "send":
                return self._send_message(inputs.get("message"))
            elif action == "receive":
                return self._receive_messages(inputs.get("timeout", 1.0))
            elif action == "disconnect":
                return self._disconnect()
            else:
                raise ValueError(f"Unknown action: {action}")
        except Exception as e:
            raise NodeExecutionError(f"WebSocket operation failed: {str(e)}")

    def _connect(self) -> Dict[str, Any]:
        """Connect to the WebSocket server.

        Returns:
            Connection status
        """
        # Placeholder for actual connection
        self._ws = f"websocket_to_{self.config['url']}"
        self._connected = True

        return {
            "status": "connected",
            "url": self.config["url"],
            "metadata": {"timestamp": time.time()},
        }

    def _send_message(self, message: Any) -> Dict[str, Any]:
        """Send a message through the WebSocket.

        Args:
            message: Message to send

        Returns:
            Send status
        """
        if not self._connected:
            raise ValueError("Not connected to WebSocket")

        # Placeholder for actual send
        return {
            "status": "sent",
            "message": message,
            "metadata": {"timestamp": time.time()},
        }

    def _receive_messages(self, timeout: float) -> Dict[str, Any]:
        """Receive messages from the WebSocket.

        Args:
            timeout: Receive timeout

        Returns:
            Received messages
        """
        if not self._connected:
            raise ValueError("Not connected to WebSocket")

        # Placeholder for actual receive
        messages = []
        # Simulate receiving 1-3 messages
        for i in range(hash(str(time.time())) % 3 + 1):
            messages.append(
                {"type": "update", "data": f"message_{i}", "timestamp": time.time()}
            )

        return {
            "status": "received",
            "messages": messages,
            "metadata": {"count": len(messages), "timeout": timeout},
        }

    def _disconnect(self) -> Dict[str, Any]:
        """Disconnect from the WebSocket server.

        Returns:
            Disconnection status
        """
        # Placeholder for actual disconnect
        self._connected = False
        self._ws = None

        return {"status": "disconnected", "metadata": {"timestamp": time.time()}}

    def cleanup(self) -> None:
        """Clean up WebSocket resources.

        Ensures the connection is closed and resources are released.
        """
        if self._connected:
            self._disconnect()
        super().cleanup()


@register_node()
class EventStreamNode(Node):
    """Handles server-sent events (SSE) for unidirectional streaming.

    This node provides SSE client functionality for receiving real-time
    events from servers using the EventSource protocol.

    Design Pattern:
    - Observer pattern for event handling
    - Iterator pattern for event streaming
    - Decorator pattern for event processing

    Features:
    - Auto-reconnection
    - Event type filtering
    - Custom event handlers
    - Last-Event-ID tracking
    - Connection timeout

    Common Usage Patterns:
    - Live updates/notifications
    - Stock price feeds
    - News streams
    - Progress monitoring
    - Log streaming

    Upstream Dependencies:
    - Authentication nodes
    - Configuration nodes

    Downstream Consumers:
    - Event processing nodes
    - Storage nodes
    - UI update nodes
    - Analytics nodes

    Configuration:
        url (str): SSE endpoint URL
        headers (Dict): Request headers
        event_types (List[str]): Event types to listen for
        reconnect_time (int): Reconnection delay
        timeout (int): Connection timeout

    Inputs:
        action (str): Action to perform ("start", "stop", "receive")
        max_events (int): Maximum events to receive

    Outputs:
        events (List[Dict]): Received events
        status (str): Stream status
        metadata (Dict): Stream metadata

    Error Handling:
    - Connection failures
    - Timeout handling
    - Invalid event data
    - Authentication errors

    Example:
        >>> sse_node = EventStreamNode()
        >>> sse_node.configure({
        ...     "url": "https://api.example.com/events",
        ...     "headers": {"Authorization": "Bearer token"},
        ...     "event_types": ["update", "notification"],
        ...     "reconnect_time": 3000
        ... })
        >>>
        >>> # Start listening
        >>> sse_node.execute({"action": "start"})
        >>>
        >>> # Receive events
        >>> result = sse_node.execute({
        ...     "action": "receive",
        ...     "max_events": 10
        ... })
        >>> print(f"Received {len(result['events'])} events")
    """

    metadata = NodeMetadata(
        name="EventStreamNode",
        description="Server-sent events client",
        version="1.0.0",
        tags={"streaming", "sse", "data"},
    )

    def __init__(self):
        """Initialize the EventStream node.

        Sets up the node and prepares for SSE connection.
        """
        super().__init__()
        self._stream = None
        self._connected = False
        self._last_event_id = None

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Get the parameters for this node.

        Returns:
            Parameter definitions for configuration and execution
        """
        return {
            "url": NodeParameter(
                name="url", type=str, description="SSE endpoint URL", required=True
            ),
            "headers": NodeParameter(
                name="headers",
                type=dict,
                description="Request headers",
                required=False,
                default={},
            ),
            "event_types": NodeParameter(
                name="event_types",
                type=list,
                description="Event types to listen for",
                required=False,
                default=[],
            ),
            "reconnect_time": NodeParameter(
                name="reconnect_time",
                type=int,
                description="Reconnection delay in ms",
                required=False,
                default=3000,
            ),
            "timeout": NodeParameter(
                name="timeout",
                type=int,
                description="Connection timeout in seconds",
                required=False,
                default=60,
            ),
            "action": NodeParameter(
                name="action",
                type=str,
                description="Action to perform (start, stop, receive)",
                required=False,
                default="receive",
            ),
            "max_events": NodeParameter(
                name="max_events",
                type=int,
                description="Maximum events to receive",
                required=False,
                default=10,
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Run the EventStream node.

        This method fulfills the abstract run method requirement from the base Node class.

        Args:
            **kwargs: Input parameters

        Returns:
            Operation results

        Raises:
            NodeExecutionError: If execution fails
        """
        return self.execute(kwargs)

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Execute EventStream operations.

        Args:
            inputs: Action and parameters

        Returns:
            Operation results

        Raises:
            NodeExecutionError: If operation fails
        """
        try:
            action = inputs.get("action", "receive")

            if action == "start":
                return self._start_stream()
            elif action == "stop":
                return self._stop_stream()
            elif action == "receive":
                return self._receive_events(inputs.get("max_events", 10))
            else:
                raise ValueError(f"Unknown action: {action}")
        except Exception as e:
            raise NodeExecutionError(f"EventStream operation failed: {str(e)}")

    def _start_stream(self) -> Dict[str, Any]:
        """Start the event stream connection.

        Returns:
            Connection status
        """
        # Placeholder for actual connection
        self._stream = f"sse_stream_{self.config['url']}"
        self._connected = True

        return {
            "status": "streaming",
            "url": self.config["url"],
            "metadata": {"timestamp": time.time()},
        }

    def _stop_stream(self) -> Dict[str, Any]:
        """Stop the event stream connection.

        Returns:
            Disconnection status
        """
        # Placeholder for actual disconnection
        self._connected = False
        self._stream = None

        return {
            "status": "stopped",
            "metadata": {
                "timestamp": time.time(),
                "last_event_id": self._last_event_id,
            },
        }

    def _receive_events(self, max_events: int) -> Dict[str, Any]:
        """Receive events from the stream.

        Args:
            max_events: Maximum events to receive

        Returns:
            Received events
        """
        if not self._connected:
            raise ValueError("Not connected to event stream")

        # Placeholder for actual event reception
        events = []
        event_types = self.config.get("event_types", [])

        # Simulate receiving events
        for i in range(min(max_events, 5)):
            event_type = event_types[i % len(event_types)] if event_types else "message"
            event = {
                "id": f"event_{time.time()}_{i}",
                "type": event_type,
                "data": {"content": f"Event data {i}"},
                "timestamp": time.time(),
            }
            events.append(event)
            self._last_event_id = event["id"]

        return {
            "status": "received",
            "events": events,
            "metadata": {"count": len(events), "last_event_id": self._last_event_id},
        }

    def cleanup(self) -> None:
        """Clean up EventStream resources.

        Ensures the stream is closed and resources are released.
        """
        if self._connected:
            self._stop_stream()
        super().cleanup()
