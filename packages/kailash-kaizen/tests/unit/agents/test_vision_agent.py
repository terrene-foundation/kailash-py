"""
Unit tests for VisionAgent.

Tests the vision processing agent using BaseAgent + ImageField.
Following TDD pattern from TODO-146 Phase 2.
"""

from unittest.mock import MagicMock, patch

import pytest
from PIL import Image


class TestVisionAgentCreation:
    """Test VisionAgent creation and initialization."""

    def test_vision_agent_creation(self):
        """Test creating VisionAgent with signature."""
        from kaizen.agents.multi_modal.vision_agent import (
            VisionAgent,
            VisionAgentConfig,
        )

        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            with patch(
                "kaizen.providers.ollama_model_manager.OllamaModelManager"
            ) as mock_manager:
                mock_manager.return_value.model_exists.return_value = True

                config = VisionAgentConfig()
                agent = VisionAgent(config)

                assert agent is not None
                assert hasattr(agent, "vision_provider")
                assert hasattr(agent, "config")

    def test_vision_agent_custom_config(self):
        """Test VisionAgent with custom configuration."""
        from kaizen.agents.multi_modal.vision_agent import (
            VisionAgent,
            VisionAgentConfig,
        )

        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            with patch(
                "kaizen.providers.ollama_model_manager.OllamaModelManager"
            ) as mock_manager:
                mock_manager.return_value.model_exists.return_value = True

                config = VisionAgentConfig(
                    llm_provider="ollama",
                    model="bakllava",
                    temperature=0.9,
                    max_images=3,
                )
                agent = VisionAgent(config)

                assert agent.config.model == "bakllava"
                assert agent.config.temperature == 0.9
                assert agent.config.max_images == 3

    def test_vision_agent_has_signature(self):
        """Test VisionAgent has vision signature."""
        from kaizen.agents.multi_modal.vision_agent import (
            VisionAgent,
            VisionAgentConfig,
        )

        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            with patch(
                "kaizen.providers.ollama_model_manager.OllamaModelManager"
            ) as mock_manager:
                mock_manager.return_value.model_exists.return_value = True

                config = VisionAgentConfig()
                agent = VisionAgent(config)

                # Should have signature attribute from BaseAgent
                assert hasattr(agent, "signature")


class TestVisionAgentAnalyzeImage:
    """Test VisionAgent image analysis."""

    def test_vision_agent_analyze_image(self, tmp_path):
        """Test analyzing single image."""
        from kaizen.agents.multi_modal.vision_agent import (
            VisionAgent,
            VisionAgentConfig,
        )

        # Create test image
        img = Image.new("RGB", (100, 100), color="red")
        img_path = tmp_path / "test.jpg"
        img.save(img_path, format="JPEG")

        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}
        mock_ollama.chat.return_value = {
            "message": {"content": "This is a red square."},
            "model": "llava:13b",
        }

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            with patch(
                "kaizen.providers.ollama_model_manager.OllamaModelManager"
            ) as mock_manager:
                mock_manager.return_value.model_exists.return_value = True

                config = VisionAgentConfig()
                agent = VisionAgent(config)

                result = agent.run(image=str(img_path), question="What do you see?")

                assert "answer" in result
                assert "confidence" in result
                assert "model" in result
                assert result["answer"] == "This is a red square."

    def test_vision_agent_answer_question(self, tmp_path):
        """Test visual question answering."""
        from kaizen.agents.multi_modal.vision_agent import (
            VisionAgent,
            VisionAgentConfig,
        )

        # Create test image
        img = Image.new("RGB", (100, 100), color="blue")
        img_path = tmp_path / "test.jpg"
        img.save(img_path, format="JPEG")

        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}
        mock_ollama.chat.return_value = {
            "message": {"content": "The color is blue."},
            "model": "llava:13b",
        }

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            with patch(
                "kaizen.providers.ollama_model_manager.OllamaModelManager"
            ) as mock_manager:
                mock_manager.return_value.model_exists.return_value = True

                config = VisionAgentConfig()
                agent = VisionAgent(config)

                result = agent.analyze(
                    image=str(img_path), question="What color is this?"
                )

                assert result["answer"] == "The color is blue."
                assert isinstance(result["confidence"], float)

    def test_vision_agent_describe_image(self, tmp_path):
        """Test generating image description."""
        from kaizen.agents.multi_modal.vision_agent import (
            VisionAgent,
            VisionAgentConfig,
        )

        # Create test image
        img = Image.new("RGB", (100, 100), color="green")
        img_path = tmp_path / "test.jpg"
        img.save(img_path, format="JPEG")

        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}
        mock_ollama.chat.return_value = {
            "message": {"content": "A vibrant green square."},
            "model": "llava:13b",
        }

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            with patch(
                "kaizen.providers.ollama_model_manager.OllamaModelManager"
            ) as mock_manager:
                mock_manager.return_value.model_exists.return_value = True

                config = VisionAgentConfig()
                agent = VisionAgent(config)

                description = agent.describe(image=str(img_path), detail="detailed")

                assert description == "A vibrant green square."
                assert isinstance(description, str)


class TestVisionAgentAdvancedTasks:
    """Test advanced vision tasks."""

    def test_vision_agent_detect_objects(self, tmp_path):
        """Test object detection task."""
        from kaizen.agents.multi_modal.vision_agent import (
            VisionAgent,
            VisionAgentConfig,
        )

        # Create test image
        img = Image.new("RGB", (200, 200), color="white")
        img_path = tmp_path / "objects.jpg"
        img.save(img_path, format="JPEG")

        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}
        mock_ollama.chat.return_value = {
            "message": {"content": "I can see 3 cars and 2 people."},
            "model": "llava:13b",
        }

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            with patch(
                "kaizen.providers.ollama_model_manager.OllamaModelManager"
            ) as mock_manager:
                mock_manager.return_value.model_exists.return_value = True

                config = VisionAgentConfig()
                agent = VisionAgent(config)

                result = agent.analyze(
                    image=str(img_path),
                    question="What objects can you detect in this image?",
                )

                assert "answer" in result
                assert "cars" in result["answer"] or "people" in result["answer"]

    def test_vision_agent_ocr(self, tmp_path):
        """Test text extraction (OCR) from image."""
        from kaizen.agents.multi_modal.vision_agent import (
            VisionAgent,
            VisionAgentConfig,
        )

        # Create test image
        img = Image.new("RGB", (300, 100), color="white")
        img_path = tmp_path / "text.jpg"
        img.save(img_path, format="JPEG")

        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}
        mock_ollama.chat.return_value = {
            "message": {"content": "HELLO WORLD"},
            "model": "llava:13b",
        }

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            with patch(
                "kaizen.providers.ollama_model_manager.OllamaModelManager"
            ) as mock_manager:
                mock_manager.return_value.model_exists.return_value = True

                config = VisionAgentConfig()
                agent = VisionAgent(config)

                text = agent.extract_text(image=str(img_path))

                assert text == "HELLO WORLD"
                assert isinstance(text, str)

    def test_vision_agent_batch_analysis(self, tmp_path):
        """Test analyzing multiple images in batch."""
        from kaizen.agents.multi_modal.vision_agent import (
            VisionAgent,
            VisionAgentConfig,
        )

        # Create test images
        images = []
        for i in range(3):
            img = Image.new("RGB", (50, 50), color="red")
            img_path = tmp_path / f"test{i}.jpg"
            img.save(img_path, format="JPEG")
            images.append(str(img_path))

        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}
        mock_ollama.chat.return_value = {
            "message": {"content": "A red square."},
            "model": "llava:13b",
        }

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            with patch(
                "kaizen.providers.ollama_model_manager.OllamaModelManager"
            ) as mock_manager:
                mock_manager.return_value.model_exists.return_value = True

                config = VisionAgentConfig()
                agent = VisionAgent(config)

                results = agent.batch_analyze(images=images, question="What is this?")

                assert len(results) == 3
                assert all("answer" in r for r in results)
                assert all("confidence" in r for r in results)


class TestVisionAgentMemoryIntegration:
    """Test VisionAgent memory integration."""

    def test_vision_agent_memory_integration(self, tmp_path):
        """Test storing vision results in agent memory."""
        from kaizen.agents.multi_modal.vision_agent import (
            VisionAgent,
            VisionAgentConfig,
        )

        # Create test image
        img = Image.new("RGB", (100, 100), color="purple")
        img_path = tmp_path / "test.jpg"
        img.save(img_path, format="JPEG")

        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}
        mock_ollama.chat.return_value = {
            "message": {"content": "Purple square."},
            "model": "llava:13b",
        }

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            with patch(
                "kaizen.providers.ollama_model_manager.OllamaModelManager"
            ) as mock_manager:
                mock_manager.return_value.model_exists.return_value = True

                config = VisionAgentConfig()
                agent = VisionAgent(config)

                # Mock write_to_memory if it exists
                with patch.object(
                    agent, "write_to_memory", return_value=None
                ) as mock_memory:
                    agent.analyze(
                        image=str(img_path),
                        question="What is this?",
                        store_in_memory=True,
                    )

                    # Verify memory was written
                    if hasattr(agent, "write_to_memory"):
                        mock_memory.assert_called_once()

    def test_vision_agent_memory_disabled(self, tmp_path):
        """Test vision analysis without storing in memory."""
        from kaizen.agents.multi_modal.vision_agent import (
            VisionAgent,
            VisionAgentConfig,
        )

        # Create test image
        img = Image.new("RGB", (100, 100), color="orange")
        img_path = tmp_path / "test.jpg"
        img.save(img_path, format="JPEG")

        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}
        mock_ollama.chat.return_value = {
            "message": {"content": "Orange square."},
            "model": "llava:13b",
        }

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            with patch(
                "kaizen.providers.ollama_model_manager.OllamaModelManager"
            ) as mock_manager:
                mock_manager.return_value.model_exists.return_value = True

                config = VisionAgentConfig()
                agent = VisionAgent(config)

                # Mock write_to_memory if it exists
                with patch.object(
                    agent, "write_to_memory", return_value=None
                ) as mock_memory:
                    agent.analyze(
                        image=str(img_path),
                        question="What is this?",
                        store_in_memory=False,
                    )

                    # Verify memory was NOT written
                    mock_memory.assert_not_called()


class TestVisionAgentErrorRecovery:
    """Test VisionAgent error handling and recovery."""

    def test_vision_agent_error_recovery(self, tmp_path):
        """Test handling invalid images."""
        from kaizen.agents.multi_modal.vision_agent import (
            VisionAgent,
            VisionAgentConfig,
        )

        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}
        mock_ollama.chat.side_effect = Exception("Invalid image format")

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            with patch(
                "kaizen.providers.ollama_model_manager.OllamaModelManager"
            ) as mock_manager:
                mock_manager.return_value.model_exists.return_value = True

                config = VisionAgentConfig()
                agent = VisionAgent(config)

                # Should handle error gracefully
                with pytest.raises(Exception):
                    agent.run(image="invalid.jpg", question="What is this?")
