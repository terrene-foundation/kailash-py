"""
Unit tests for KaizenMemory base class.

Test Strategy:
- Tier 1 (Unit): Abstract base class validation
- Tests abstract methods are defined
- Tests inheritance and concrete implementation
- Tests NotImplementedError behavior
"""

from typing import Any, Dict

import pytest


class TestMemoryBaseAbstractInterface:
    """Test that KaizenMemory enforces abstract interface."""

    def test_kaizen_memory_is_abstract(self):
        """Test that KaizenMemory cannot be instantiated directly."""
        from kaizen.memory.conversation_base import KaizenMemory

        # Should raise TypeError when trying to instantiate abstract class
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            KaizenMemory()

    def test_kaizen_memory_has_load_context_abstract_method(self):
        """Test that load_context is defined as abstract method."""
        from kaizen.memory.conversation_base import KaizenMemory

        assert hasattr(KaizenMemory, "load_context")
        assert getattr(KaizenMemory.load_context, "__isabstractmethod__", False)

    def test_kaizen_memory_has_save_turn_abstract_method(self):
        """Test that save_turn is defined as abstract method."""
        from kaizen.memory.conversation_base import KaizenMemory

        assert hasattr(KaizenMemory, "save_turn")
        assert getattr(KaizenMemory.save_turn, "__isabstractmethod__", False)

    def test_kaizen_memory_has_clear_abstract_method(self):
        """Test that clear is defined as abstract method."""
        from kaizen.memory.conversation_base import KaizenMemory

        assert hasattr(KaizenMemory, "clear")
        assert getattr(KaizenMemory.clear, "__isabstractmethod__", False)

    def test_concrete_implementation_can_be_instantiated(self):
        """Test that concrete subclass implementing all methods can be instantiated."""
        from kaizen.memory.conversation_base import KaizenMemory

        class ConcreteMemory(KaizenMemory):
            def load_context(self, session_id: str) -> Dict[str, Any]:
                return {}

            def save_turn(self, session_id: str, turn: Dict[str, Any]) -> None:
                pass

            def clear(self, session_id: str) -> None:
                pass

        # Should instantiate without error
        memory = ConcreteMemory()
        assert isinstance(memory, KaizenMemory)

    def test_partial_implementation_raises_error(self):
        """Test that partial implementation cannot be instantiated."""
        from kaizen.memory.conversation_base import KaizenMemory

        class PartialMemory(KaizenMemory):
            def load_context(self, session_id: str) -> Dict[str, Any]:
                return {}

            # Missing save_turn and clear

        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            PartialMemory()

    def test_load_context_signature(self):
        """Test load_context has correct signature."""
        import inspect

        from kaizen.memory.conversation_base import KaizenMemory

        sig = inspect.signature(KaizenMemory.load_context)
        params = list(sig.parameters.keys())

        assert "session_id" in params
        # Check return annotation
        assert sig.return_annotation != inspect.Parameter.empty

    def test_save_turn_signature(self):
        """Test save_turn has correct signature."""
        import inspect

        from kaizen.memory.conversation_base import KaizenMemory

        sig = inspect.signature(KaizenMemory.save_turn)
        params = list(sig.parameters.keys())

        assert "session_id" in params
        assert "turn" in params

    def test_clear_signature(self):
        """Test clear has correct signature."""
        import inspect

        from kaizen.memory.conversation_base import KaizenMemory

        sig = inspect.signature(KaizenMemory.clear)
        params = list(sig.parameters.keys())

        assert "session_id" in params

    def test_concrete_implementation_methods_work(self):
        """Test that concrete implementation methods can be called."""
        from kaizen.memory.conversation_base import KaizenMemory

        class ConcreteMemory(KaizenMemory):
            def __init__(self):
                self.data = {}

            def load_context(self, session_id: str) -> Dict[str, Any]:
                return self.data.get(session_id, {})

            def save_turn(self, session_id: str, turn: Dict[str, Any]) -> None:
                if session_id not in self.data:
                    self.data[session_id] = []
                self.data[session_id].append(turn)

            def clear(self, session_id: str) -> None:
                if session_id in self.data:
                    del self.data[session_id]

        memory = ConcreteMemory()

        # Test save_turn
        memory.save_turn("session1", {"user": "hello", "agent": "hi"})

        # Test load_context
        context = memory.load_context("session1")
        assert isinstance(context, list)
        assert len(context) == 1

        # Test clear
        memory.clear("session1")
        context = memory.load_context("session1")
        assert context == {}
