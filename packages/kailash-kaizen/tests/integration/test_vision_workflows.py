"""
Integration tests for vision workflows.

End-to-end vision workflows with real Ollama (when available).
Following TDD pattern from TODO-146 Phase 2.
"""

import pytest
from PIL import Image

# Skip tests if Ollama is not available
try:
    import ollama

    OLLAMA_AVAILABLE = True
    try:
        ollama.list()
    except Exception:
        OLLAMA_AVAILABLE = False
except ImportError:
    OLLAMA_AVAILABLE = False


@pytest.mark.skipif(not OLLAMA_AVAILABLE, reason="Ollama not available")
class TestE2EImageDescription:
    """Test end-to-end image description workflow."""

    def test_e2e_image_description(self, tmp_path):
        """Test complete image description workflow with real Ollama."""
        from kaizen.agents.vision_agent import VisionAgent, VisionAgentConfig

        # Create test image
        img = Image.new("RGB", (200, 200), color="red")
        img_path = tmp_path / "red_square.jpg"
        img.save(img_path, format="JPEG")

        # Create vision agent
        config = VisionAgentConfig(
            llm_provider="ollama", model="llava:13b", temperature=0.7
        )
        agent = VisionAgent(config)

        # Generate description
        description = agent.describe(image=str(img_path), detail="auto")

        # Verify description is generated
        assert description is not None
        assert isinstance(description, str)
        assert len(description) > 0

    def test_e2e_image_description_detailed(self, tmp_path):
        """Test detailed image description."""
        from kaizen.agents.vision_agent import VisionAgent, VisionAgentConfig

        # Create more complex test image
        img = Image.new("RGB", (400, 300), color="blue")
        img_path = tmp_path / "blue_rectangle.jpg"
        img.save(img_path, format="JPEG")

        config = VisionAgentConfig(model="llava:13b")
        agent = VisionAgent(config)

        description = agent.describe(image=str(img_path), detail="detailed")

        assert description is not None
        assert len(description) > 20  # Detailed description should be longer


@pytest.mark.skipif(not OLLAMA_AVAILABLE, reason="Ollama not available")
class TestE2EVisualQA:
    """Test end-to-end visual question answering."""

    def test_e2e_visual_qa(self, tmp_path):
        """Test complete visual Q&A workflow."""
        from kaizen.agents.vision_agent import VisionAgent, VisionAgentConfig

        # Create test image
        img = Image.new("RGB", (150, 150), color="green")
        img_path = tmp_path / "green_square.jpg"
        img.save(img_path, format="JPEG")

        config = VisionAgentConfig(model="llava:13b")
        agent = VisionAgent(config)

        result = agent.analyze(
            image=str(img_path), question="What is the dominant color in this image?"
        )

        # Verify response structure
        assert "answer" in result
        assert "confidence" in result
        assert "model" in result
        assert isinstance(result["answer"], str)
        assert isinstance(result["confidence"], float)

    def test_e2e_visual_qa_multiple_questions(self, tmp_path):
        """Test multiple questions about same image."""
        from kaizen.agents.vision_agent import VisionAgent, VisionAgentConfig

        # Create test image
        img = Image.new("RGB", (200, 100), color="yellow")
        img_path = tmp_path / "yellow_rect.jpg"
        img.save(img_path, format="JPEG")

        config = VisionAgentConfig(model="llava:13b")
        agent = VisionAgent(config)

        questions = [
            "What is the shape of this image?",
            "What is the primary color?",
            "Is this image wider than it is tall?",
        ]

        results = []
        for question in questions:
            result = agent.run(image=str(img_path), question=question)
            results.append(result)

        # Verify all questions were answered
        assert len(results) == 3
        assert all("answer" in r for r in results)


@pytest.mark.skipif(not OLLAMA_AVAILABLE, reason="Ollama not available")
class TestE2EDocumentAnalysis:
    """Test end-to-end document analysis."""

    def test_e2e_document_analysis(self, tmp_path):
        """Test analyzing document image with OCR."""
        from kaizen.agents.vision_agent import VisionAgent, VisionAgentConfig

        # Create document-like image (white background)
        img = Image.new("RGB", (800, 600), color="white")
        img_path = tmp_path / "document.jpg"
        img.save(img_path, format="JPEG")

        config = VisionAgentConfig(model="llava:13b")
        agent = VisionAgent(config)

        # Extract text
        text = agent.extract_text(image=str(img_path))

        # Verify text extraction works
        assert text is not None
        assert isinstance(text, str)

    def test_e2e_document_analysis_with_question(self, tmp_path):
        """Test document analysis with specific question."""
        from kaizen.agents.vision_agent import VisionAgent, VisionAgentConfig

        # Create document image
        img = Image.new("RGB", (600, 400), color="white")
        img_path = tmp_path / "form.jpg"
        img.save(img_path, format="JPEG")

        config = VisionAgentConfig(model="llava:13b")
        agent = VisionAgent(config)

        result = agent.analyze(
            image=str(img_path), question="What type of document is this?"
        )

        assert "answer" in result
        assert len(result["answer"]) > 0


@pytest.mark.skipif(not OLLAMA_AVAILABLE, reason="Ollama not available")
class TestE2EMultiImageComparison:
    """Test end-to-end multi-image comparison."""

    def test_e2e_multi_image_comparison(self, tmp_path):
        """Test comparing multiple images."""
        from kaizen.agents.vision_agent import VisionAgent, VisionAgentConfig

        # Create test images with different colors
        colors = ["red", "blue", "green"]
        images = []

        for i, color in enumerate(colors):
            img = Image.new("RGB", (100, 100), color=color)
            img_path = tmp_path / f"{color}_square.jpg"
            img.save(img_path, format="JPEG")
            images.append(str(img_path))

        config = VisionAgentConfig(model="llava:13b")
        agent = VisionAgent(config)

        # Batch analyze
        results = agent.batch_analyze(
            images=images, question="What is the primary color of this image?"
        )

        # Verify all images were analyzed
        assert len(results) == 3
        assert all("answer" in r for r in results)
        assert all("confidence" in r for r in results)

    def test_e2e_multi_image_similarity(self, tmp_path):
        """Test analyzing similarity between images."""
        from kaizen.providers.ollama_vision_provider import OllamaVisionProvider

        # Create similar images
        img1 = Image.new("RGB", (100, 100), color="red")
        img1_path = tmp_path / "img1.jpg"
        img1.save(img1_path, format="JPEG")

        img2 = Image.new("RGB", (100, 100), color="red")
        img2_path = tmp_path / "img2.jpg"
        img2.save(img2_path, format="JPEG")

        # Use provider directly for multi-image analysis
        provider = OllamaVisionProvider()

        result = provider.analyze_images(
            images=[str(img1_path), str(img2_path)], prompt="Are these images similar?"
        )

        assert "response" in result
        assert "images_analyzed" in result
        assert result["images_analyzed"] == 2


@pytest.mark.skipif(not OLLAMA_AVAILABLE, reason="Ollama not available")
class TestE2EVisionPerformance:
    """Test vision workflow performance benchmarks."""

    def test_e2e_vision_performance(self, tmp_path):
        """Test performance benchmarks for vision workflows."""
        import time

        from kaizen.agents.vision_agent import VisionAgent, VisionAgentConfig

        # Create test image
        img = Image.new("RGB", (300, 300), color="purple")
        img_path = tmp_path / "test.jpg"
        img.save(img_path, format="JPEG")

        config = VisionAgentConfig(model="llava:13b")
        agent = VisionAgent(config)

        # Measure analysis time
        start_time = time.time()
        result = agent.run(image=str(img_path), question="Describe this image")
        elapsed_time = time.time() - start_time

        # Verify performance is reasonable (< 30 seconds for local Ollama)
        assert elapsed_time < 30.0
        assert "answer" in result

    def test_e2e_vision_batch_performance(self, tmp_path):
        """Test batch analysis performance."""
        import time

        from kaizen.agents.vision_agent import VisionAgent, VisionAgentConfig

        # Create multiple test images
        images = []
        for i in range(3):
            img = Image.new("RGB", (100, 100), color="blue")
            img_path = tmp_path / f"test{i}.jpg"
            img.save(img_path, format="JPEG")
            images.append(str(img_path))

        config = VisionAgentConfig(model="llava:13b")
        agent = VisionAgent(config)

        # Measure batch analysis time
        start_time = time.time()
        results = agent.batch_analyze(images=images, question="What is this?")
        elapsed_time = time.time() - start_time

        # Verify all images were processed
        assert len(results) == 3
        # Performance should be reasonable (< 60 seconds for 3 images)
        assert elapsed_time < 60.0
