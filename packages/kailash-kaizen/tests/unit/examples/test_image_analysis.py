"""
Tests for examples/8-multi-modal/image-analysis example.

Tests the vision processing example using standardized fixtures.
"""

from pathlib import Path

import pytest

# Import helper
from example_import_helper import import_example_module


@pytest.fixture
def image_analysis_example():
    """Load image-analysis example."""
    return import_example_module("examples/8-multi-modal/image-analysis")


class TestImageAnalysisExample:
    """Test image analysis example workflow."""

    def test_example_imports(self, image_analysis_example):
        """Test that example imports successfully."""
        assert image_analysis_example is not None
        assert hasattr(image_analysis_example, "create_sample_images")

    def test_sample_image_creation(self, image_analysis_example, tmp_path):
        """Test sample image creation."""
        # Temporarily change directory for test
        import os

        original_cwd = os.getcwd()

        try:
            os.chdir(tmp_path)

            # Create sample images
            create_sample_images = image_analysis_example.create_sample_images
            images_dir = create_sample_images()

            # Verify images created
            assert images_dir.exists()
            assert (images_dir / "red_square.jpg").exists()
            assert (images_dir / "blue_square.jpg").exists()
            assert (images_dir / "green_square.jpg").exists()
            assert (images_dir / "landscape.jpg").exists()
        finally:
            os.chdir(original_cwd)

    @pytest.mark.skipif(
        not pytest.importorskip("ollama", reason="Ollama not available"),
        reason="Requires Ollama",
    )
    def test_vision_agent_initialization(self, image_analysis_example):
        """Test VisionAgent initialization from example."""
        from kaizen.agents.multi_modal.vision_agent import VisionAgentConfig

        config = VisionAgentConfig(model="llama3.2-vision", temperature=0.7)

        # Verify config creation works
        assert config.model == "llama3.2-vision"
        assert config.temperature == 0.7


class TestImageAnalysisPatterns:
    """Test patterns used in image analysis example."""

    def test_uses_vision_agent(self, image_analysis_example):
        """Verify example uses VisionAgent."""
        source = Path(image_analysis_example.__file__).read_text()
        assert "VisionAgent" in source
        assert "VisionAgentConfig" in source

    def test_sample_generation_pattern(self, image_analysis_example):
        """Verify sample generation pattern."""
        source = Path(image_analysis_example.__file__).read_text()
        assert "create_sample_images" in source
        assert "PIL" in source or "Image" in source
