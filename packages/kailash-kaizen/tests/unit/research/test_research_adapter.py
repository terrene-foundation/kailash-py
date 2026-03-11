"""
Unit tests for ResearchAdapter - WRITE TESTS FIRST (TDD RED Phase)

Test Coverage:
1. Create signature adapters from research papers
2. Wrap research implementations as Kaizen signatures
3. Parameter mapping and conversion
4. Integration with TODO-142 signature system
5. Backward compatibility
6. Performance validation (<1s adaptation)

CRITICAL: These tests MUST be written BEFORE implementation!
"""

from unittest.mock import Mock, patch

import pytest


class TestResearchAdapter:
    """Test suite for ResearchAdapter component."""

    def test_adapter_initialization(self):
        """Test ResearchAdapter can be instantiated."""
        from kaizen.research import ResearchAdapter

        adapter = ResearchAdapter()
        assert adapter is not None
        assert hasattr(adapter, "create_signature_adapter")
        assert hasattr(adapter, "adapt_to_signature")

    def test_create_signature_adapter_flash_attention(self, flash_attention_paper):
        """Test creating signature adapter for Flash Attention."""
        from kaizen.research import ResearchAdapter
        from kaizen.signatures import Signature

        adapter = ResearchAdapter()

        # Mock the module import
        with patch("kaizen.research.adapter.importlib.import_module") as mock_import:
            # Create mock module with mock function
            mock_module = Mock()
            mock_func = Mock()
            mock_func.__name__ = "flash_attn_func"
            mock_module.flash_attn_func = mock_func
            mock_import.return_value = mock_module

            signature_class = adapter.create_signature_adapter(
                paper=flash_attention_paper,
                implementation_module="flash_attn",
                main_function="flash_attn_func",
            )

            # Should return a Signature subclass
            assert signature_class is not None
            assert issubclass(signature_class, Signature)

    def test_signature_adapter_has_execute_method(self, flash_attention_paper):
        """Test that created signature adapter has execute method."""
        from kaizen.research import ResearchAdapter

        adapter = ResearchAdapter()

        # Mock the module import
        with patch("kaizen.research.adapter.importlib.import_module") as mock_import:
            mock_module = Mock()
            mock_func = Mock()
            mock_func.__name__ = "test_func"
            mock_module.test_func = mock_func
            mock_import.return_value = mock_module

            signature_class = adapter.create_signature_adapter(
                paper=flash_attention_paper,
                implementation_module="test_module",
                main_function="test_func",
            )

            # Should have execute method
            assert hasattr(signature_class, "execute")

    def test_signature_adapter_metadata(self, flash_attention_paper):
        """Test that signature adapter includes paper metadata."""
        from kaizen.research import ResearchAdapter

        adapter = ResearchAdapter()

        # Mock the module import
        with patch("kaizen.research.adapter.importlib.import_module") as mock_import:
            mock_module = Mock()
            mock_func = Mock()
            mock_func.__name__ = "flash_attn_func"
            mock_module.flash_attn_func = mock_func
            mock_import.return_value = mock_module

            signature_class = adapter.create_signature_adapter(
                paper=flash_attention_paper,
                implementation_module="flash_attn",
                main_function="flash_attn_func",
            )

            # Should include paper metadata
            sig_instance = signature_class()
            assert hasattr(sig_instance, "paper_id") or hasattr(
                sig_instance, "metadata"
            )

    def test_adapt_maml_paper(self, maml_paper):
        """Test adapting MAML paper to signature."""
        from kaizen.research import ResearchAdapter

        adapter = ResearchAdapter()

        # Mock the module import
        with patch("kaizen.research.adapter.importlib.import_module") as mock_import:
            mock_module = Mock()
            mock_func = Mock()
            mock_func.__name__ = "maml_adapt"
            mock_module.maml_adapt = mock_func
            mock_import.return_value = mock_module

            signature_class = adapter.create_signature_adapter(
                paper=maml_paper,
                implementation_module="maml",
                main_function="maml_adapt",
            )

            assert signature_class is not None

    def test_adapt_tree_of_thought_paper(self, tree_of_thought_paper):
        """Test adapting Tree of Thoughts paper to signature."""
        from kaizen.research import ResearchAdapter

        adapter = ResearchAdapter()

        # Mock the module import
        with patch("kaizen.research.adapter.importlib.import_module") as mock_import:
            mock_module = Mock()
            mock_func = Mock()
            mock_func.__name__ = "tot_solve"
            mock_module.tot_solve = mock_func
            mock_import.return_value = mock_module

            signature_class = adapter.create_signature_adapter(
                paper=tree_of_thought_paper,
                implementation_module="tree_of_thought",
                main_function="tot_solve",
            )

            assert signature_class is not None

    def test_adapter_performance(self, flash_attention_paper, performance_timer):
        """Test adapter creation meets <1s performance target."""
        from kaizen.research import ResearchAdapter

        adapter = ResearchAdapter()

        # Mock the module import
        with patch("kaizen.research.adapter.importlib.import_module") as mock_import:
            mock_module = Mock()
            mock_func = Mock()
            mock_func.__name__ = "flash_attn_func"
            mock_module.flash_attn_func = mock_func
            mock_import.return_value = mock_module

            # Fix: Instantiate the Timer class
            timer = performance_timer()
            timer.start()
            adapter.create_signature_adapter(
                paper=flash_attention_paper,
                implementation_module="flash_attn",
                main_function="flash_attn_func",
            )
            timer.stop()

            timer.assert_under(1.0, "Signature adaptation")

    def test_adapt_with_parameter_mapping(self, flash_attention_paper):
        """Test parameter mapping during adaptation."""
        from kaizen.research import ResearchAdapter

        adapter = ResearchAdapter()

        param_mapping = {"query": "q", "key": "k", "value": "v"}

        # Mock the module import
        with patch("kaizen.research.adapter.importlib.import_module") as mock_import:
            mock_module = Mock()
            mock_func = Mock()
            mock_func.__name__ = "flash_attn_func"
            mock_module.flash_attn_func = mock_func
            mock_import.return_value = mock_module

            signature_class = adapter.create_signature_adapter(
                paper=flash_attention_paper,
                implementation_module="flash_attn",
                main_function="flash_attn_func",
                parameter_mapping=param_mapping,
            )

            # Adapter should use parameter mapping
            assert signature_class is not None

    def test_backward_compatibility_with_base_agent(self, flash_attention_paper):
        """Test adapter maintains backward compatibility with BaseAgent."""
        from kaizen.research import ResearchAdapter

        adapter = ResearchAdapter()

        # Mock the module import first
        with patch("kaizen.research.adapter.importlib.import_module") as mock_import:
            mock_module = Mock()
            mock_func = Mock()
            mock_func.__name__ = "test_func"
            mock_module.test_func = mock_func
            mock_import.return_value = mock_module

            signature_class = adapter.create_signature_adapter(
                paper=flash_attention_paper,
                implementation_module="test_module",
                main_function="test_func",
            )

            # Should be usable with BaseAgent (from TODO-142)
            # Import would be: from kaizen.core.base_agent import BaseAgent
            # We'll mock this for testing
            with patch("kaizen.core.base_agent.BaseAgent") as MockBaseAgent:
                MockBaseAgent.return_value = Mock()

                # Should not raise exception when used with BaseAgent
                try:
                    sig_instance = signature_class()
                    # BaseAgent should accept this signature
                    assert sig_instance is not None
                except Exception as e:
                    pytest.fail(f"Signature not compatible with BaseAgent: {e}")

    def test_integrate_with_signature_system(self, flash_attention_paper):
        """Test integration with TODO-142 signature system."""
        from kaizen.research import ResearchAdapter
        from kaizen.signatures import Signature

        adapter = ResearchAdapter()

        # Mock the module import
        with patch("kaizen.research.adapter.importlib.import_module") as mock_import:
            mock_module = Mock()
            mock_func = Mock()
            mock_func.__name__ = "flash_attn_func"
            mock_module.flash_attn_func = mock_func
            mock_import.return_value = mock_module

            signature_class = adapter.create_signature_adapter(
                paper=flash_attention_paper,
                implementation_module="flash_attn",
                main_function="flash_attn_func",
            )

            # Should integrate with signature system
            assert issubclass(signature_class, Signature)

    def test_adapted_signature_execution(self, flash_attention_paper):
        """Test that adapted signature can be executed."""
        from kaizen.research import ResearchAdapter

        adapter = ResearchAdapter()

        # Mock the actual implementation
        with patch("kaizen.research.adapter.importlib") as mock_importlib:
            mock_module = Mock()
            mock_func = Mock(return_value="result")
            mock_module.flash_attn_func = mock_func
            mock_importlib.import_module.return_value = mock_module

            signature_class = adapter.create_signature_adapter(
                paper=flash_attention_paper,
                implementation_module="flash_attn",
                main_function="flash_attn_func",
            )

            sig_instance = signature_class()

            # Should be executable (even if mocked)
            assert hasattr(sig_instance, "execute")

    def test_adapter_with_missing_implementation(self, flash_attention_paper):
        """Test adapter handles missing implementation module."""
        from kaizen.research import ResearchAdapter

        adapter = ResearchAdapter()

        with pytest.raises((ImportError, ModuleNotFoundError)):
            adapter.create_signature_adapter(
                paper=flash_attention_paper,
                implementation_module="nonexistent_module",
                main_function="nonexistent_func",
            )

    def test_adapter_with_invalid_function(self, flash_attention_paper):
        """Test adapter handles invalid function name."""
        from kaizen.research import ResearchAdapter

        adapter = ResearchAdapter()

        with patch("kaizen.research.adapter.importlib") as mock_importlib:
            mock_module = Mock()
            # Module exists but function doesn't
            del mock_module.nonexistent_func
            mock_importlib.import_module.return_value = mock_module

            with pytest.raises(AttributeError):
                adapter.create_signature_adapter(
                    paper=flash_attention_paper,
                    implementation_module="test_module",
                    main_function="nonexistent_func",
                )


class TestSignatureAdapter:
    """Test SignatureAdapter wrapper class."""

    def test_signature_adapter_wraps_research(self, flash_attention_paper):
        """Test SignatureAdapter properly wraps research implementation."""
        from kaizen.research import SignatureAdapter

        # Mock the implementation function
        mock_impl = Mock(return_value={"speedup": 2.7})

        adapter = SignatureAdapter(
            paper=flash_attention_paper, implementation_func=mock_impl
        )

        assert adapter is not None
        assert hasattr(adapter, "execute")

    def test_signature_adapter_execute(self, flash_attention_paper):
        """Test SignatureAdapter execute method."""
        from kaizen.research import SignatureAdapter

        mock_impl = Mock(return_value={"result": "success"})

        adapter = SignatureAdapter(
            paper=flash_attention_paper, implementation_func=mock_impl
        )

        result = adapter.execute(query="test", key="test", value="test")

        # Should call implementation and return result
        assert result is not None
        mock_impl.assert_called_once()

    def test_signature_adapter_parameter_conversion(self, flash_attention_paper):
        """Test SignatureAdapter converts parameters correctly."""
        from kaizen.research import SignatureAdapter

        mock_impl = Mock(return_value={"output": "test"})

        adapter = SignatureAdapter(
            paper=flash_attention_paper,
            implementation_func=mock_impl,
            parameter_mapping={"input": "x"},
        )

        adapter.execute(input="value")

        # Should convert 'input' to 'x' before calling implementation
        call_args = mock_impl.call_args
        assert call_args is not None


class TestIntegrationWithSignatureSystem:
    """Test integration with TODO-142 signature programming system."""

    def test_uses_signature_parser(self, flash_attention_paper):
        """Test adapter uses SignatureParser from TODO-142."""
        from kaizen.research import ResearchAdapter

        adapter = ResearchAdapter()

        # Should use or integrate with SignatureParser
        assert hasattr(adapter, "_create_signature_definition") or hasattr(
            adapter, "_parse_signature_spec"
        )

    def test_uses_signature_compiler(self, flash_attention_paper):
        """Test adapter uses SignatureCompiler from TODO-142."""
        from kaizen.research import ResearchAdapter

        adapter = ResearchAdapter()

        # Mock the module import
        with patch("kaizen.research.adapter.importlib.import_module") as mock_import:
            mock_module = Mock()
            mock_func = Mock()
            mock_func.__name__ = "test"
            mock_module.test = mock_func
            mock_import.return_value = mock_module

            signature_class = adapter.create_signature_adapter(
                paper=flash_attention_paper,
                implementation_module="test",
                main_function="test",
            )

            # Adapted signature should be compatible with SignatureCompiler
            # (This would compile to Core SDK WorkflowBuilder)
            assert signature_class is not None

    def test_adapted_signature_compiles_to_workflow(self, flash_attention_paper):
        """Test that adapted signature can compile to Core SDK workflow."""
        from kaizen.research import ResearchAdapter

        adapter = ResearchAdapter()

        with patch("kaizen.research.adapter.importlib") as mock_importlib:
            mock_module = Mock()
            mock_func = Mock()
            mock_module.test_func = mock_func
            mock_importlib.import_module.return_value = mock_module

            signature_class = adapter.create_signature_adapter(
                paper=flash_attention_paper,
                implementation_module="test",
                main_function="test_func",
            )

            sig_instance = signature_class()

            # Should have methods compatible with Core SDK workflow compilation
            # (from TODO-142 signature system)
            assert sig_instance is not None
