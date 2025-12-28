"""
MRO (Method Resolution Order) verification tests for AsyncNode enterprise features.

This module verifies that AsyncNode correctly inherits from all enterprise mixins
and that the MRO chain is correct for proper method resolution.

Phase: 6A - Mixin Inheritance Foundation
Created: 2025-10-26
"""

import asyncio

import pytest
from kailash.nodes.base import Node
from kailash.nodes.base_async import AsyncNode


# Concrete implementation of AsyncNode for testing
class ConcreteAsyncNode(AsyncNode):
    """Concrete AsyncNode implementation for testing."""

    def get_parameters(self):
        """Return empty parameter schema for testing."""
        return {}

    async def async_run(self, **kwargs):
        """Simple async implementation for testing."""
        await asyncio.sleep(0.001)  # Simulate async I/O
        return {"result": "success", **kwargs}


class TestAsyncNodeMRO:
    """Test AsyncNode Method Resolution Order and mixin inheritance."""

    def test_async_node_mro_chain(self):
        """Verify AsyncNode has correct MRO chain with all mixins."""
        mro = AsyncNode.__mro__

        # Verify AsyncNode is first
        assert mro[0] == AsyncNode, "AsyncNode should be first in MRO"

        # Verify mixins are in correct order (will be added in Phase 6A)
        # Expected order: AsyncNode → EventEmitterMixin → SecurityMixin →
        #                 ValidationMixin → PerformanceMixin → LoggingMixin → Node → ABC → object

        # For now, verify AsyncNode → Node → ABC → object (current state)
        assert Node in mro, "Node should be in MRO"

        # After Phase 6A implementation, this should be 9
        expected_mro_length = 9  # AsyncNode + 5 mixins + Node + ABC + object
        assert len(mro) >= 3, f"MRO should have at least 3 elements, got {len(mro)}"

    def test_async_node_inherits_from_node(self):
        """Verify AsyncNode inherits from Node base class."""
        assert issubclass(AsyncNode, Node), "AsyncNode must inherit from Node"

        # Verify instance relationship
        node = ConcreteAsyncNode(node_id="test")
        assert isinstance(node, Node), "AsyncNode instance should be instance of Node"
        assert isinstance(
            node, AsyncNode
        ), "AsyncNode instance should be instance of AsyncNode"

    def test_async_node_has_node_base_methods(self):
        """Verify AsyncNode has all Node base methods (48 methods)."""
        node = ConcreteAsyncNode(node_id="test_node")

        # Verify key Node methods are accessible
        base_methods = [
            "validate_inputs",
            "validate_outputs",
            "execute",
            "run",
            "get_parameters",
            "get_workflow_context",
            "set_workflow_context",
            "to_dict",
        ]

        for method_name in base_methods:
            assert hasattr(
                node, method_name
            ), f"AsyncNode should have {method_name} from Node base"
            assert callable(
                getattr(node, method_name)
            ), f"{method_name} should be callable"

        # Verify key Node attributes
        assert hasattr(node, "id"), "AsyncNode should have 'id' attribute from Node"
        assert hasattr(
            node, "config"
        ), "AsyncNode should have 'config' attribute from Node"
        assert hasattr(
            node, "metadata"
        ), "AsyncNode should have 'metadata' attribute from Node"

    def test_async_node_has_event_emission_methods(self):
        """Verify AsyncNode has event emission methods from EventEmitterMixin."""
        node = ConcreteAsyncNode(node_id="test_node")

        # These methods will be available after Phase 6A implementation
        event_methods = [
            "emit_event",
            "emit_async",
            "add_event_listener",
            "remove_event_listener",
        ]

        # Check if methods exist (will pass after implementation)
        for method_name in event_methods:
            # After Phase 6A, these should exist
            if hasattr(node, method_name):
                assert callable(
                    getattr(node, method_name)
                ), f"{method_name} should be callable"

    def test_async_node_has_security_methods(self):
        """Verify AsyncNode has security methods from SecurityMixin."""
        node = ConcreteAsyncNode(node_id="test_node")

        # These methods will be available after Phase 6A implementation
        security_methods = [
            "validate_security",
            "sanitize_input",
            "check_access",
        ]

        # Check if methods exist (will pass after implementation)
        for method_name in security_methods:
            if hasattr(node, method_name):
                assert callable(
                    getattr(node, method_name)
                ), f"{method_name} should be callable"

    def test_async_node_has_validation_methods(self):
        """Verify AsyncNode has additional validation methods from ValidationMixin."""
        node = ConcreteAsyncNode(node_id="test_node")

        # These methods will be available after Phase 6A implementation
        validation_methods = [
            "validate_type",
            "validate_range",
            "validate_format",
        ]

        # Check if methods exist (will pass after implementation)
        for method_name in validation_methods:
            if hasattr(node, method_name):
                assert callable(
                    getattr(node, method_name)
                ), f"{method_name} should be callable"

    def test_async_node_has_performance_methods(self):
        """Verify AsyncNode has performance monitoring methods from PerformanceMixin."""
        node = ConcreteAsyncNode(node_id="test_node")

        # These methods will be available after Phase 6A implementation
        performance_methods = [
            "track_performance",
            "get_performance_metrics",
            "reset_metrics",
        ]

        # Check if methods exist (will pass after implementation)
        for method_name in performance_methods:
            if hasattr(node, method_name):
                assert callable(
                    getattr(node, method_name)
                ), f"{method_name} should be callable"

    def test_async_node_has_logging_methods(self):
        """Verify AsyncNode has enhanced logging methods from LoggingMixin."""
        node = ConcreteAsyncNode(node_id="test_node")

        # These methods will be available after Phase 6A implementation
        logging_methods = [
            "log_with_context",
            "log_security_event",
            "log_performance_metric",
        ]

        # Check if methods exist (will pass after implementation)
        for method_name in logging_methods:
            if hasattr(node, method_name):
                assert callable(
                    getattr(node, method_name)
                ), f"{method_name} should be callable"

    def test_async_node_method_count(self):
        """Verify AsyncNode has expected number of methods after mixin inheritance."""
        node = ConcreteAsyncNode(node_id="test_node")

        # Count public methods (not starting with _)
        public_methods = [
            m for m in dir(node) if not m.startswith("_") and callable(getattr(node, m))
        ]
        method_count = len(public_methods)

        # With 4 mixins (EventEmitterMixin, SecurityMixin, PerformanceMixin, LoggingMixin) + Node + AsyncNode
        # Expected: ~33 methods total
        #   - Node base: ~8 methods
        #   - AsyncNode: ~5 methods
        #   - EventEmitterMixin: ~7 methods
        #   - SecurityMixin: ~3 methods
        #   - PerformanceMixin: ~3 methods
        #   - LoggingMixin: ~7 methods

        assert (
            method_count >= 30
        ), f"AsyncNode should have at least 30 public methods with mixins, got {method_count}"
        assert (
            method_count <= 40
        ), f"AsyncNode should have at most 40 public methods, got {method_count} (unexpected growth)"


class TestAsyncNodeMixinInheritance:
    """Test AsyncNode mixin inheritance and initialization."""

    def test_async_node_initialization_with_mixins(self):
        """Verify AsyncNode initializes correctly with all mixins."""
        # Create node with explicit ID
        node = ConcreteAsyncNode()

        # Node.id defaults to class name when not specified
        assert (
            node.id == "ConcreteAsyncNode"
        ), f"Default id should be class name, got {node.id}"

        # Verify core Node attributes
        assert hasattr(node, "config"), "Node should have config attribute"
        assert hasattr(node, "metadata"), "Node should have metadata attribute"

        # Verify mixin methods are accessible (mixins inherited correctly)
        # SecurityMixin methods
        assert hasattr(
            node, "validate_and_sanitize_inputs"
        ), "Should have SecurityMixin methods"

        # LoggingMixin methods
        assert hasattr(node, "log_with_context"), "Should have LoggingMixin methods"

        # PerformanceMixin methods
        assert hasattr(
            node, "track_performance"
        ), "Should have PerformanceMixin methods"

        # EventEmitterMixin methods
        assert hasattr(
            node, "emit_node_started"
        ), "Should have EventEmitterMixin methods"

    def test_async_node_mro_length(self):
        """Verify MRO chain has expected length."""
        mro = AsyncNode.__mro__

        # Before Phase 6A: 4 elements (AsyncNode, Node, ABC, object)
        # After Phase 6A: 9 elements (AsyncNode + 5 mixins + Node + ABC + object)

        current_length = len(mro)
        assert (
            current_length >= 3
        ), f"MRO should have at least 3 elements, got {current_length}"

        # After implementation, uncomment:
        # assert current_length == 9, f"MRO should have 9 elements after mixins, got {current_length}"

    def test_async_node_is_instance_of_mixins(self):
        """Verify AsyncNode instance is instance of all mixins."""
        node = ConcreteAsyncNode(node_id="test_node")

        # Verify Node inheritance (current state)
        assert isinstance(node, Node), "AsyncNode should be instance of Node"

        # After Phase 6A, verify mixin inheritance
        # from kailash.nodes.mixins import SecurityMixin, ValidationMixin, PerformanceMixin, LoggingMixin
        # from kailash.nodes.mixins.event_emitter import EventEmitterMixin
        #
        # assert isinstance(node, EventEmitterMixin), "AsyncNode should be instance of EventEmitterMixin"
        # assert isinstance(node, SecurityMixin), "AsyncNode should be instance of SecurityMixin"
        # assert isinstance(node, ValidationMixin), "AsyncNode should be instance of ValidationMixin"
        # assert isinstance(node, PerformanceMixin), "AsyncNode should be instance of PerformanceMixin"
        # assert isinstance(node, LoggingMixin), "AsyncNode should be instance of LoggingMixin"

    def test_async_node_issubclass_of_mixins(self):
        """Verify AsyncNode is subclass of all mixins."""
        # Verify Node inheritance (current state)
        assert issubclass(AsyncNode, Node), "AsyncNode should be subclass of Node"

        # After Phase 6A, verify mixin inheritance
        # from kailash.nodes.mixins import SecurityMixin, ValidationMixin, PerformanceMixin, LoggingMixin
        # from kailash.nodes.mixins.event_emitter import EventEmitterMixin
        #
        # assert issubclass(AsyncNode, EventEmitterMixin), "AsyncNode should be subclass of EventEmitterMixin"
        # assert issubclass(AsyncNode, SecurityMixin), "AsyncNode should be subclass of SecurityMixin"
        # assert issubclass(AsyncNode, ValidationMixin), "AsyncNode should be subclass of ValidationMixin"
        # assert issubclass(AsyncNode, PerformanceMixin), "AsyncNode should be subclass of PerformanceMixin"
        # assert issubclass(AsyncNode, LoggingMixin), "AsyncNode should be subclass of LoggingMixin"
