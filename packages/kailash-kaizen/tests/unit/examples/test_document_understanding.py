"""
Tests for examples/8-multi-modal/document-understanding example.

Tests the complete multi-modal pipeline example using standardized fixtures.
"""

from pathlib import Path

import pytest

# Import helper
from example_import_helper import import_example_module


@pytest.fixture
def document_understanding_example():
    """Load document-understanding example."""
    return import_example_module("examples/8-multi-modal/document-understanding")


class TestDocumentUnderstandingExample:
    """Test document understanding example workflow."""

    def test_example_imports(self, document_understanding_example):
        """Test that example imports successfully."""
        assert document_understanding_example is not None

    def test_workflow_class_exists(self, document_understanding_example):
        """Test DocumentUnderstandingWorkflow class exists."""
        assert hasattr(document_understanding_example, "DocumentUnderstandingWorkflow")

        workflow_class = document_understanding_example.DocumentUnderstandingWorkflow
        assert workflow_class is not None

    def test_config_class_exists(self, document_understanding_example):
        """Test DocumentUnderstandingConfig exists."""
        assert hasattr(document_understanding_example, "DocumentUnderstandingConfig")

        config_class = document_understanding_example.DocumentUnderstandingConfig
        config = config_class()

        # Verify default config values
        assert config.llm_provider == "ollama"
        assert config.budget_limit == 5.0
        assert config.enable_cost_tracking == True

    def test_signature_classes_exist(self, document_understanding_example):
        """Test signature classes exist."""
        assert hasattr(document_understanding_example, "DocumentOCRSignature")
        assert hasattr(document_understanding_example, "DocumentAnalysisSignature")
        assert hasattr(document_understanding_example, "DocumentSummarySignature")

    def test_multi_agent_pipeline(self, document_understanding_example):
        """Verify multi-agent pipeline structure."""
        workflow_class = document_understanding_example.DocumentUnderstandingWorkflow
        config_class = document_understanding_example.DocumentUnderstandingConfig

        # Create workflow
        config = config_class()
        workflow = workflow_class(config)

        # Verify agents created
        assert hasattr(workflow, "ocr_agent")
        assert hasattr(workflow, "analysis_agent")
        assert hasattr(workflow, "summary_agent")

        # Verify shared resources
        assert hasattr(workflow, "memory_pool")
        assert hasattr(workflow, "cost_tracker")

    def test_provider_selection(self, document_understanding_example):
        """Test provider selection patterns."""
        source = Path(document_understanding_example.__file__).read_text()

        # Verify provider selection pattern
        assert "llm_provider" in source
        assert "ollama" in source.lower() or "openai" in source.lower()


class TestDocumentUnderstandingPatterns:
    """Test patterns used in document understanding example."""

    def test_uses_multi_modal_agent(self, document_understanding_example):
        """Verify example uses MultiModalAgent."""
        source = Path(document_understanding_example.__file__).read_text()
        assert "MultiModalAgent" in source
        assert "MultiModalConfig" in source

    def test_uses_cost_tracking(self, document_understanding_example):
        """Verify example uses cost tracking."""
        source = Path(document_understanding_example.__file__).read_text()
        assert "CostTracker" in source
        assert "budget_limit" in source

    def test_uses_shared_memory(self, document_understanding_example):
        """Verify example uses shared memory."""
        source = Path(document_understanding_example.__file__).read_text()
        assert "SharedMemoryPool" in source
        assert "memory_pool" in source

    def test_pipeline_structure(self, document_understanding_example):
        """Verify 3-step pipeline structure."""
        source = Path(document_understanding_example.__file__).read_text()

        # Verify OCR → Analysis → Summary pipeline
        assert "OCR" in source or "ocr" in source
        assert "analysis" in source.lower()
        assert "summary" in source.lower()
