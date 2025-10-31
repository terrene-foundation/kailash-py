"""
Unit tests for the AsyncTypedNode base class.

Tests async version of Task 3.2: Node Migration Framework
- AsyncTypedNode base class functionality
- Async port to parameter conversion
- Async enhanced validation
- Async execution with type-safe ports
- Backward compatibility and migration
"""

import asyncio
from typing import Any, Dict, List, Optional, Union
from unittest.mock import AsyncMock, Mock

import pytest
from kailash.nodes.base import AsyncTypedNode, NodeParameter
from kailash.nodes.ports import InputPort, IntPort, OutputPort, StringPort
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError


class TestAsyncTypedNodeBasics:
    """Test basic AsyncTypedNode functionality."""

    def test_simple_async_typed_node_creation(self):
        """Test creating a simple async typed node."""

        class SimpleAsyncTypedNode(AsyncTypedNode):
            text_input = InputPort[str]("text_input", description="Text input")
            result_output = OutputPort[str](
                "result_output", description="Result output"
            )

            async def async_run(self, **kwargs):
                text = self.text_input.get()
                await asyncio.sleep(0.01)  # Simulate async I/O
                return {"result_output": text.upper()}

        node = SimpleAsyncTypedNode()

        assert hasattr(node, "text_input")
        assert hasattr(node, "result_output")
        assert hasattr(node, "_port_registry")
        assert hasattr(node, "execute_async")
        assert hasattr(node, "async_run")

        # Check port registry
        assert len(node._port_registry.input_ports) == 1
        assert len(node._port_registry.output_ports) == 1
        assert "text_input" in node._port_registry.input_ports
        assert "result_output" in node._port_registry.output_ports

    def test_async_typed_node_with_config(self):
        """Test async typed node initialization with config values."""

        class ConfigAsyncTypedNode(AsyncTypedNode):
            count = InputPort[int]("count", default=5, description="Count value")
            name = InputPort[str]("name", description="Name value")

            async def async_run(self, **kwargs):
                await asyncio.sleep(0.01)
                return {"count": self.count.get(), "name": self.name.get()}

        # Test with config values
        node = ConfigAsyncTypedNode(count=10, name="test")

        # Config should be stored
        assert node.config["count"] == 10
        # Note: 'name' goes to metadata, not config due to Node base class handling
        assert node.metadata.name == "test"

    def test_parameter_generation_same_as_typed_node(self):
        """Test that parameter generation works same as TypedNode."""

        class ParameterTestAsyncNode(AsyncTypedNode):
            required_text = InputPort[str]("required_text", description="Required text")
            optional_count = InputPort[int](
                "optional_count",
                default=1,
                required=False,
                description="Optional count",
            )
            data_list = InputPort[List[str]]("data_list", description="List of strings")

            async def async_run(self, **kwargs):
                return {}

        node = ParameterTestAsyncNode()
        params = node.get_parameters()

        # Check all ports are converted to parameters
        assert len(params) == 3
        assert "required_text" in params
        assert "optional_count" in params
        assert "data_list" in params

        # Check parameter properties
        required_param = params["required_text"]
        assert required_param.name == "required_text"
        assert required_param.type == str
        assert required_param.required is True
        assert required_param.description == "Required text"


class TestAsyncTypedNodeExecution:
    """Test async execution with port system integration."""

    @pytest.mark.asyncio
    async def test_async_execution_flow(self):
        """Test complete async execution flow with ports."""

        class AsyncExecutionTestNode(AsyncTypedNode):
            text_input = InputPort[str]("text_input", description="Input text")
            multiplier = InputPort[int](
                "multiplier", default=2, description="Multiplier"
            )
            result = OutputPort[str]("result", description="Result")
            length = OutputPort[int]("length", description="Result length")

            async def async_run(self, **kwargs):
                # Access inputs through ports
                text = self.text_input.get()
                mult = self.multiplier.get()

                # Simulate async processing
                await asyncio.sleep(0.01)
                result_text = text * mult

                # Set outputs through ports (optional, can also return dict)
                self.result.set(result_text)
                self.length.set(len(result_text))

                # Return traditional dict format
                return {"result": result_text, "length": len(result_text)}

        node = AsyncExecutionTestNode()

        # Execute with valid inputs using execute_async
        result = await node.execute_async(text_input="hello", multiplier=3)

        assert result["result"] == "hellohellohello"
        assert result["length"] == 15

        # Test with default multiplier
        result = await node.execute_async(text_input="hi")
        assert result["result"] == "hihi"
        assert result["length"] == 4

    @pytest.mark.asyncio
    async def test_async_port_access_during_execution(self):
        """Test accessing port values during async execution."""

        class AsyncPortAccessNode(AsyncTypedNode):
            data = InputPort[str]("data", description="Data input")
            flag = InputPort[bool]("flag", default=True, description="Flag input")
            result = OutputPort[str]("result", description="Result")

            async def async_run(self, **kwargs):
                # Direct port access should work in async context
                data_value = self.data.get()
                flag_value = self.flag.get()

                # Simulate async processing
                await asyncio.sleep(0.01)

                if flag_value:
                    result_value = data_value.upper()
                else:
                    result_value = data_value.lower()

                return {"result": result_value}

        node = AsyncPortAccessNode()

        # Test with flag=True
        result = await node.execute_async(data="Hello World", flag=True)
        assert result["result"] == "HELLO WORLD"

        # Test with flag=False
        result = await node.execute_async(data="Hello World", flag=False)
        assert result["result"] == "hello world"

        # Test with default flag
        result = await node.execute_async(data="Hello World")
        assert result["result"] == "HELLO WORLD"

    def test_sync_execution_compatibility(self):
        """Test that sync execute() method works for backward compatibility."""

        class SyncCompatAsyncNode(AsyncTypedNode):
            text_input = InputPort[str]("text_input", description="Input text")
            result = OutputPort[str]("result", description="Result")

            async def async_run(self, **kwargs):
                text = self.text_input.get()
                await asyncio.sleep(0.01)  # Simulate async I/O
                return {"result": text.upper()}

        node = SyncCompatAsyncNode()

        # Should be able to call execute() (sync) on async node
        result = node.execute(text_input="hello")
        assert result["result"] == "HELLO"


class TestAsyncTypedNodeValidation:
    """Test async validation features."""

    @pytest.mark.asyncio
    async def test_async_input_validation_with_ports(self):
        """Test enhanced input validation in async context."""

        class AsyncValidationTestNode(AsyncTypedNode):
            text_input = InputPort[str]("text_input", description="Text input")
            number_input = InputPort[int]("number_input", description="Number input")
            optional_input = InputPort[str](
                "optional_input", required=False, description="Optional"
            )

            async def async_run(self, **kwargs):
                await asyncio.sleep(0.01)
                return {}

        node = AsyncValidationTestNode()

        # Valid inputs
        result = await node.execute_async(text_input="hello", number_input=42)
        assert result == {}

        # Test missing required parameter
        with pytest.raises(
            NodeValidationError, match="Required parameter 'text_input' not provided"
        ):
            await node.execute_async(number_input=42)

    @pytest.mark.asyncio
    async def test_async_output_validation_with_ports(self):
        """Test enhanced output validation in async context."""

        class AsyncOutputValidationNode(AsyncTypedNode):
            input_data = InputPort[str]("input_data")
            result = OutputPort[str]("result", description="String result")
            count = OutputPort[int]("count", description="Integer count")

            async def async_run(self, **kwargs):
                await asyncio.sleep(0.01)
                # Return outputs that need validation
                return {
                    "result": "hello",
                    "count": "42",
                }  # count will be converted to int

        node = AsyncOutputValidationNode()

        # Valid execution with type conversion
        result = await node.execute_async(input_data="test")
        assert result["result"] == "hello"
        assert result["count"] == 42  # Should be converted to int

    @pytest.mark.asyncio
    async def test_async_constraint_validation(self):
        """Test port constraint validation in async context."""

        class AsyncConstraintTestNode(AsyncTypedNode):
            text_input = InputPort[str](
                "text_input",
                constraints={"min_length": 3, "max_length": 10},
                description="Text with length constraints",
            )
            number_input = InputPort[int](
                "number_input",
                constraints={"min_value": 0, "max_value": 100},
                description="Number with range constraints",
            )

            async def async_run(self, **kwargs):
                await asyncio.sleep(0.01)
                return {}

        node = AsyncConstraintTestNode()

        # Valid inputs within constraints
        await node.execute_async(text_input="hello", number_input=50)

        # Text too short
        with pytest.raises(NodeValidationError):
            await node.execute_async(text_input="hi", number_input=50)

        # Number too large
        with pytest.raises(NodeValidationError):
            await node.execute_async(text_input="hello", number_input=101)


class TestAsyncTypedNodeAdvancedFeatures:
    """Test advanced async features."""

    @pytest.mark.asyncio
    async def test_complex_async_operations(self):
        """Test complex async operations with multiple I/O."""

        class ComplexAsyncNode(AsyncTypedNode):
            urls = InputPort[List[str]]("urls", description="List of URLs to process")
            timeout = InputPort[float](
                "timeout", default=1.0, description="Request timeout"
            )
            results = OutputPort[Dict[str, Any]](
                "results", description="Processing results"
            )

            async def async_run(self, **kwargs):
                urls = self.urls.get()
                timeout = self.timeout.get()

                # Simulate multiple async I/O operations
                results = {}
                for i, url in enumerate(urls):
                    await asyncio.sleep(0.01)  # Simulate HTTP request
                    results[url] = {"status": "ok", "length": len(url) * 10, "index": i}

                return {"results": results}

        node = ComplexAsyncNode()

        urls = ["http://example.com", "http://test.com"]
        result = await node.execute_async(urls=urls, timeout=2.0)

        assert "results" in result
        assert len(result["results"]) == 2
        assert "http://example.com" in result["results"]
        assert result["results"]["http://example.com"]["status"] == "ok"

    @pytest.mark.asyncio
    async def test_async_error_handling(self):
        """Test error handling in async context."""

        class AsyncErrorTestNode(AsyncTypedNode):
            should_fail = InputPort[bool](
                "should_fail", default=False, description="Whether to fail"
            )

            async def async_run(self, **kwargs):
                should_fail = self.should_fail.get()

                if should_fail:
                    await asyncio.sleep(0.01)
                    raise ValueError("Simulated async error")

                return {"result": "success"}

        node = AsyncErrorTestNode()

        # Should succeed when should_fail=False
        result = await node.execute_async(should_fail=False)
        assert result["result"] == "success"

        # Should fail when should_fail=True
        with pytest.raises(NodeExecutionError, match="Simulated async error"):
            await node.execute_async(should_fail=True)

    @pytest.mark.asyncio
    async def test_convenience_port_types_async(self):
        """Test convenience port types in async context."""

        class AsyncConvenienceNode(AsyncTypedNode):
            text = StringPort("text", description="String input")
            count = IntPort("count", default=1, description="Integer input")

            async def async_run(self, **kwargs):
                await asyncio.sleep(0.01)
                return {"text": self.text.get(), "count": self.count.get()}

        node = AsyncConvenienceNode()

        result = await node.execute_async(text="hello", count=5)
        assert result["text"] == "hello"
        assert result["count"] == 5

        # Test type validation
        result = await node.execute_async(
            text="hello", count="5"
        )  # Should convert string to int
        assert result["count"] == 5


class TestAsyncTypedNodeBackwardCompatibility:
    """Test backward compatibility and migration features."""

    @pytest.mark.asyncio
    async def test_traditional_parameter_access_async(self):
        """Test that traditional parameter access still works in async context."""

        class AsyncHybridNode(AsyncTypedNode):
            port_input = InputPort[str]("port_input", description="Port-based input")

            def get_parameters(self):
                # Override to add traditional parameters alongside ports
                port_params = super().get_parameters()
                port_params.update(
                    {
                        "traditional_param": NodeParameter(
                            name="traditional_param",
                            type=str,
                            required=True,
                            description="Traditional parameter",
                        )
                    }
                )
                return port_params

            async def async_run(self, **kwargs):
                # Should be able to access both port and traditional params
                port_value = self.port_input.get()
                traditional_value = kwargs.get("traditional_param")

                await asyncio.sleep(0.01)

                return {
                    "port_result": port_value,
                    "traditional_result": traditional_value,
                }

        node = AsyncHybridNode()

        result = await node.execute_async(
            port_input="port_data", traditional_param="traditional_data"
        )

        assert result["port_result"] == "port_data"
        assert result["traditional_result"] == "traditional_data"

    def test_run_method_override_error(self):
        """Test that run() method properly raises error."""

        class AsyncTestNode(AsyncTypedNode):
            async def async_run(self, **kwargs):
                return {}

        node = AsyncTestNode()

        # run() should raise NotImplementedError
        with pytest.raises(NotImplementedError, match="should implement async_run"):
            node.run()

    def test_async_run_not_implemented_error(self):
        """Test that missing async_run() implementation raises error."""

        class IncompleteAsyncNode(AsyncTypedNode):
            pass  # No async_run implementation

        node = IncompleteAsyncNode()

        # Should raise NotImplementedError when async_run is not implemented
        with pytest.raises(NotImplementedError, match="must implement async_run"):
            asyncio.run(node.async_run())


class TestAsyncTypedNodeIntegration:
    """Test integration with async runtime and workflows."""

    @pytest.mark.asyncio
    async def test_multiple_async_nodes_execution(self):
        """Test multiple async nodes working together."""

        class AsyncProducerNode(AsyncTypedNode):
            count = InputPort[int]("count", default=3, description="Number of items")
            items = OutputPort[List[str]]("items", description="Generated items")

            async def async_run(self, **kwargs):
                count = self.count.get()
                items = []

                for i in range(count):
                    await asyncio.sleep(0.01)  # Simulate async generation
                    items.append(f"item_{i}")

                return {"items": items}

        class AsyncConsumerNode(AsyncTypedNode):
            items = InputPort[List[str]]("items", description="Items to process")
            result = OutputPort[str]("result", description="Processed result")

            async def async_run(self, **kwargs):
                items = self.items.get()

                # Simulate async processing
                await asyncio.sleep(0.01)
                result = ",".join(items).upper()

                return {"result": result}

        # Test the nodes work independently
        producer = AsyncProducerNode()
        consumer = AsyncConsumerNode()

        # Producer generates items
        producer_result = await producer.execute_async(count=2)
        assert producer_result["items"] == ["item_0", "item_1"]

        # Consumer processes items
        consumer_result = await consumer.execute_async(items=producer_result["items"])
        assert consumer_result["result"] == "ITEM_0,ITEM_1"

    def test_async_node_serialization(self):
        """Test that async nodes serialize properly."""

        class SerializableAsyncNode(AsyncTypedNode):
            input_param = InputPort[str]("input_param", description="Input parameter")
            output_param = OutputPort[int](
                "output_param", description="Output parameter"
            )

            async def async_run(self, **kwargs):
                return {"output_param": 42}

        node = SerializableAsyncNode(
            name="TestAsyncNode", description="Test async node"
        )
        node_dict = node.to_dict()

        # Check base serialization
        assert node_dict["id"] == "SerializableAsyncNode"
        assert node_dict["type"] == "SerializableAsyncNode"
        assert node_dict["metadata"]["name"] == "TestAsyncNode"

        # Check port schema is included
        assert "port_schema" in node_dict
        assert "input_ports" in node_dict["port_schema"]
        assert "output_ports" in node_dict["port_schema"]
        assert "input_param" in node_dict["port_schema"]["input_ports"]
        assert "output_param" in node_dict["port_schema"]["output_ports"]


class TestEventLoopHandling:
    """Test event loop handling in different contexts."""

    def test_nested_event_loop_handling(self):
        """Test that sync execute() works even with nested event loops."""

        class NestedLoopTestNode(AsyncTypedNode):
            text = InputPort[str]("text", description="Text input")

            async def async_run(self, **kwargs):
                text = self.text.get()
                await asyncio.sleep(0.01)
                return {"result": text.upper()}

        async def async_caller():
            """Simulate calling from an async context."""
            node = NestedLoopTestNode()
            # This should work even though we're already in an async context
            result = node.execute(text="hello")
            return result

        # This tests the _execute_in_thread mechanism
        result = asyncio.run(async_caller())
        assert result["result"] == "HELLO"

    @pytest.mark.asyncio
    async def test_direct_async_execution_in_async_context(self):
        """Test direct async execution in an async context."""

        class DirectAsyncNode(AsyncTypedNode):
            value = InputPort[int]("value", description="Value input")

            async def async_run(self, **kwargs):
                value = self.value.get()
                await asyncio.sleep(0.01)
                return {"doubled": value * 2}

        node = DirectAsyncNode()

        # Direct async execution should work perfectly in async context
        result = await node.execute_async(value=21)
        assert result["doubled"] == 42
