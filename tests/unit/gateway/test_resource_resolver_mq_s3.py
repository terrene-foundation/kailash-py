"""
Unit tests for ResourceResolver message queue and S3 client resolution.

Tests:
- RabbitMQ resolution with factory + registry pattern
- Kafka resolution with factory + registry pattern
- S3 client resolution with factory + registry pattern
- Credential merging for all resource types
- Missing dependency error handling
- Resource reuse via registry caching
"""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kailash.gateway.resource_resolver import ResourceReference, ResourceResolver
from kailash.resources.registry import ResourceRegistry


@pytest.fixture
def resource_registry():
    """Create a ResourceRegistry for testing."""
    return ResourceRegistry(enable_metrics=False)


@pytest.fixture
def secret_manager():
    """Create a mock SecretManager."""
    manager = AsyncMock()
    manager.get_secret = AsyncMock(return_value=None)
    return manager


@pytest.fixture
def resolver(resource_registry, secret_manager):
    """Create a ResourceResolver with mocked dependencies."""
    return ResourceResolver(resource_registry, secret_manager)


@pytest.fixture
def mock_aio_pika():
    """Install a mock aio_pika module into sys.modules."""
    mock_module = MagicMock()
    mock_connection = AsyncMock()
    mock_module.connect_robust = AsyncMock(return_value=mock_connection)
    original = sys.modules.get("aio_pika")
    sys.modules["aio_pika"] = mock_module
    yield mock_module, mock_connection
    if original is not None:
        sys.modules["aio_pika"] = original
    else:
        sys.modules.pop("aio_pika", None)


@pytest.fixture
def mock_aiokafka():
    """Install a mock aiokafka module into sys.modules."""
    mock_module = MagicMock()
    mock_producer = AsyncMock()
    mock_consumer = AsyncMock()
    mock_module.AIOKafkaProducer = MagicMock(return_value=mock_producer)
    mock_module.AIOKafkaConsumer = MagicMock(return_value=mock_consumer)
    original = sys.modules.get("aiokafka")
    sys.modules["aiokafka"] = mock_module
    yield mock_module, mock_producer, mock_consumer
    if original is not None:
        sys.modules["aiokafka"] = original
    else:
        sys.modules.pop("aiokafka", None)


@pytest.fixture
def mock_aioboto3():
    """Install a mock aioboto3 module into sys.modules."""
    mock_module = MagicMock()
    mock_client = AsyncMock()
    mock_context_manager = AsyncMock()
    mock_context_manager.__aenter__ = AsyncMock(return_value=mock_client)
    mock_context_manager.__aexit__ = AsyncMock(return_value=False)
    mock_session = MagicMock()
    mock_session.client = MagicMock(return_value=mock_context_manager)
    mock_module.Session = MagicMock(return_value=mock_session)
    original = sys.modules.get("aioboto3")
    sys.modules["aioboto3"] = mock_module
    yield mock_module, mock_session, mock_client
    if original is not None:
        sys.modules["aioboto3"] = original
    else:
        sys.modules.pop("aioboto3", None)


class TestMessageQueueResolution:
    """Test _resolve_message_queue implementation."""

    @pytest.mark.asyncio
    async def test_rabbitmq_resolution_registers_factory(self, resolver, mock_aio_pika):
        """Test that RabbitMQ resolution registers a factory and creates resource."""
        _, mock_connection = mock_aio_pika

        config = {"type": "rabbitmq", "host": "localhost", "port": 5672}
        result = await resolver._resolve_message_queue(config, None)

        assert result is mock_connection

    @pytest.mark.asyncio
    async def test_rabbitmq_with_credentials(self, resolver, mock_aio_pika):
        """Test RabbitMQ resolution merges credentials."""
        mock_module, mock_connection = mock_aio_pika

        config = {"type": "rabbitmq", "host": "mq.example.com"}
        credentials = {
            "username": "admin",
            "password": "secret",
            "port": 5673,
        }
        result = await resolver._resolve_message_queue(config, credentials)

        assert result is mock_connection
        call_args = mock_module.connect_robust.call_args
        url = call_args[0][0]
        assert "admin" in url
        assert "secret" in url
        assert "5673" in url

    @pytest.mark.asyncio
    async def test_kafka_resolution_registers_factory(self, resolver, mock_aiokafka):
        """Test that Kafka resolution registers a factory and creates resource."""
        _, mock_producer, mock_consumer = mock_aiokafka

        config = {"type": "kafka", "host": "localhost", "port": 9092}
        result = await resolver._resolve_message_queue(config, None)

        assert result is not None
        assert hasattr(result, "producer")
        assert hasattr(result, "consumer")

    @pytest.mark.asyncio
    async def test_mq_reuses_existing_resource(self, resolver, mock_aio_pika):
        """Test that calling resolve twice returns the cached resource."""
        mock_module, _ = mock_aio_pika

        config = {"type": "rabbitmq", "host": "localhost"}
        result1 = await resolver._resolve_message_queue(config.copy(), None)
        result2 = await resolver._resolve_message_queue(config.copy(), None)

        assert result1 is result2
        assert mock_module.connect_robust.call_count == 1

    @pytest.mark.asyncio
    async def test_mq_unique_key_generation(self, resolver, mock_aio_pika):
        """Test that different configs produce different registry keys."""
        mock_module, _ = mock_aio_pika
        mock_conn1 = AsyncMock()
        mock_conn2 = AsyncMock()
        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return mock_conn1 if call_count == 1 else mock_conn2

        mock_module.connect_robust = AsyncMock(side_effect=side_effect)

        config1 = {"type": "rabbitmq", "host": "host1"}
        config2 = {"type": "rabbitmq", "host": "host2"}
        result1 = await resolver._resolve_message_queue(config1, None)
        result2 = await resolver._resolve_message_queue(config2, None)

        assert result1 is not result2

    @pytest.mark.asyncio
    async def test_mq_missing_aio_pika_raises_import_error(self, resolver):
        """Test helpful error when aio-pika is not installed."""
        original = sys.modules.pop("aio_pika", None)
        try:
            with patch.dict("sys.modules", {"aio_pika": None}):
                config = {"type": "rabbitmq", "host": "localhost"}
                with pytest.raises(ImportError, match="aio-pika is required"):
                    await resolver._resolve_message_queue(config, None)
        finally:
            if original is not None:
                sys.modules["aio_pika"] = original

    @pytest.mark.asyncio
    async def test_mq_missing_aiokafka_raises_import_error(self, resolver):
        """Test helpful error when aiokafka is not installed."""
        original = sys.modules.pop("aiokafka", None)
        try:
            with patch.dict("sys.modules", {"aiokafka": None}):
                config = {"type": "kafka", "host": "localhost"}
                with pytest.raises(ImportError, match="aiokafka is required"):
                    await resolver._resolve_message_queue(config, None)
        finally:
            if original is not None:
                sys.modules["aiokafka"] = original


class TestS3ClientResolution:
    """Test _resolve_s3_client implementation."""

    @pytest.mark.asyncio
    async def test_s3_resolution_registers_factory(self, resolver, mock_aioboto3):
        """Test that S3 resolution registers a factory and creates resource."""
        _, _, mock_client = mock_aioboto3

        config = {"region": "us-west-2"}
        result = await resolver._resolve_s3_client(config, None)

        assert result is mock_client

    @pytest.mark.asyncio
    async def test_s3_with_credentials(self, resolver, mock_aioboto3):
        """Test S3 resolution merges credentials from secret manager."""
        _, mock_session, mock_client = mock_aioboto3

        config = {"region": "eu-west-1"}
        credentials = {
            "access_key": "AKIAIOSFODNN7EXAMPLE",
            "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        }
        result = await resolver._resolve_s3_client(config, credentials)

        assert result is mock_client
        _, kwargs = mock_session.client.call_args
        assert kwargs.get("aws_access_key_id") == "AKIAIOSFODNN7EXAMPLE"
        assert (
            kwargs.get("aws_secret_access_key")
            == "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        )

    @pytest.mark.asyncio
    async def test_s3_reuses_existing_resource(self, resolver, mock_aioboto3):
        """Test that calling resolve twice returns the cached resource."""
        mock_module, _, _ = mock_aioboto3

        config = {"region": "us-east-1"}
        result1 = await resolver._resolve_s3_client(config.copy(), None)
        result2 = await resolver._resolve_s3_client(config.copy(), None)

        assert result1 is result2
        assert mock_module.Session.call_count == 1

    @pytest.mark.asyncio
    async def test_s3_unique_key_by_region(self, resolver):
        """Test that different regions produce different registry keys."""
        mock_client1 = AsyncMock()
        mock_client2 = AsyncMock()

        mock_cm1 = AsyncMock()
        mock_cm1.__aenter__ = AsyncMock(return_value=mock_client1)
        mock_cm1.__aexit__ = AsyncMock(return_value=False)

        mock_cm2 = AsyncMock()
        mock_cm2.__aenter__ = AsyncMock(return_value=mock_client2)
        mock_cm2.__aexit__ = AsyncMock(return_value=False)

        cm_count = 0

        def make_cm(*args, **kwargs):
            nonlocal cm_count
            cm_count += 1
            return mock_cm1 if cm_count == 1 else mock_cm2

        mock_session = MagicMock()
        mock_session.client = MagicMock(side_effect=make_cm)

        mock_module = MagicMock()
        mock_module.Session = MagicMock(return_value=mock_session)

        original = sys.modules.get("aioboto3")
        sys.modules["aioboto3"] = mock_module
        try:
            config1 = {"region": "us-east-1"}
            config2 = {"region": "eu-west-1"}
            result1 = await resolver._resolve_s3_client(config1, None)
            result2 = await resolver._resolve_s3_client(config2, None)

            assert result1 is not result2
        finally:
            if original is not None:
                sys.modules["aioboto3"] = original
            else:
                sys.modules.pop("aioboto3", None)

    @pytest.mark.asyncio
    async def test_s3_missing_aioboto3_raises_import_error(self, resolver):
        """Test helpful error when aioboto3 is not installed."""
        original = sys.modules.pop("aioboto3", None)
        try:
            with patch.dict("sys.modules", {"aioboto3": None}):
                config = {"region": "us-east-1"}
                with pytest.raises(ImportError, match="aioboto3 is required"):
                    await resolver._resolve_s3_client(config, None)
        finally:
            if original is not None:
                sys.modules["aioboto3"] = original

    @pytest.mark.asyncio
    async def test_s3_credential_region_override(self, resolver, mock_aioboto3):
        """Test that credentials can override the config region."""
        _, mock_session, mock_client = mock_aioboto3

        config = {"region": "us-east-1"}
        credentials = {"region": "ap-southeast-1"}
        result = await resolver._resolve_s3_client(config, credentials)

        assert result is mock_client
        _, kwargs = mock_session.client.call_args
        assert kwargs["region_name"] == "ap-southeast-1"

    @pytest.mark.asyncio
    async def test_s3_endpoint_url_from_credentials(self, resolver, mock_aioboto3):
        """Test that endpoint_url can come from credentials (e.g. MinIO)."""
        _, mock_session, mock_client = mock_aioboto3

        config = {"region": "us-east-1"}
        credentials = {"endpoint_url": "http://localhost:9000"}
        result = await resolver._resolve_s3_client(config, credentials)

        assert result is mock_client
        _, kwargs = mock_session.client.call_args
        assert kwargs["endpoint_url"] == "http://localhost:9000"


class TestResolverIntegration:
    """Test resolve() dispatching to message_queue and s3."""

    @pytest.mark.asyncio
    async def test_resolve_dispatches_to_message_queue(self, resolver, mock_aio_pika):
        """Test that resolve() routes message_queue type correctly."""
        _, mock_connection = mock_aio_pika

        ref = ResourceReference(
            type="message_queue",
            config={"type": "rabbitmq", "host": "localhost"},
        )
        result = await resolver.resolve(ref)
        assert result is mock_connection

    @pytest.mark.asyncio
    async def test_resolve_dispatches_to_s3(self, resolver, mock_aioboto3):
        """Test that resolve() routes s3 type correctly."""
        _, _, mock_client = mock_aioboto3

        ref = ResourceReference(
            type="s3",
            config={"region": "us-east-1"},
        )
        result = await resolver.resolve(ref)
        assert result is mock_client

    @pytest.mark.asyncio
    async def test_resolve_with_credentials_ref(
        self, resolver, secret_manager, mock_aio_pika
    ):
        """Test that resolve() fetches credentials and passes them."""
        secret_manager.get_secret = AsyncMock(
            return_value={"username": "mquser", "password": "mqpass"}
        )
        mock_module, _ = mock_aio_pika

        ref = ResourceReference(
            type="message_queue",
            config={"type": "rabbitmq", "host": "localhost"},
            credentials_ref="mq-creds",
        )
        result = await resolver.resolve(ref)

        secret_manager.get_secret.assert_awaited_once_with("mq-creds")
        url = mock_module.connect_robust.call_args[0][0]
        assert "mquser" in url
        assert "mqpass" in url
