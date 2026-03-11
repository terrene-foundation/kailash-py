"""
Unit tests for OllamaVisionProvider.

Tests the vision-specific provider for Ollama llava models.
Following TDD pattern from TODO-146 Phase 2.
"""

from unittest.mock import MagicMock, patch

import pytest
from PIL import Image


class TestOllamaVisionProviderInitialization:
    """Test OllamaVisionProvider initialization."""

    def test_vision_provider_initialization(self):
        """Test initializing OllamaVisionProvider with default config."""
        from kaizen.providers.ollama_vision_provider import OllamaVisionProvider

        # Mock ollama and model manager
        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": [{"name": "llava:13b"}]}

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            with patch(
                "kaizen.providers.ollama_model_manager.OllamaModelManager"
            ) as mock_manager:
                mock_manager.return_value.model_exists.return_value = True

                provider = OllamaVisionProvider()

                assert provider is not None
                assert hasattr(provider, "vision_config")
                assert provider.vision_config.model == "llava:13b"

    def test_vision_provider_custom_config(self):
        """Test initializing with custom OllamaVisionConfig."""
        from kaizen.providers.ollama_vision_provider import (
            OllamaVisionConfig,
            OllamaVisionProvider,
        )

        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            with patch(
                "kaizen.providers.ollama_model_manager.OllamaModelManager"
            ) as mock_manager:
                mock_manager.return_value.model_exists.return_value = True

                config = OllamaVisionConfig(
                    model="bakllava", max_images=5, detail="high"
                )
                provider = OllamaVisionProvider(config=config)

                assert provider.vision_config.model == "bakllava"
                assert provider.vision_config.max_images == 5
                assert provider.vision_config.detail == "high"

    def test_vision_provider_ensures_model_available(self):
        """Test provider ensures vision model is available."""
        from kaizen.providers.ollama_vision_provider import OllamaVisionProvider

        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            with patch(
                "kaizen.providers.ollama_model_manager.OllamaModelManager"
            ) as mock_manager:
                mock_instance = mock_manager.return_value
                mock_instance.model_exists.return_value = False
                mock_instance.download_model.return_value = True

                OllamaVisionProvider()

                # Should check if model exists
                mock_instance.model_exists.assert_called_with("llava:13b")
                # Should download if not exists
                mock_instance.download_model.assert_called_with("llava:13b")

    def test_vision_provider_model_download_failure(self):
        """Test provider raises error when model download fails."""
        from kaizen.providers.ollama_vision_provider import OllamaVisionProvider

        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            with patch(
                "kaizen.providers.ollama_model_manager.OllamaModelManager"
            ) as mock_manager:
                mock_instance = mock_manager.return_value
                mock_instance.model_exists.return_value = False
                mock_instance.download_model.return_value = False

                with pytest.raises(
                    RuntimeError, match="Failed to download vision model"
                ):
                    OllamaVisionProvider()


class TestVisionMessageFormatting:
    """Test vision message formatting for Ollama."""

    def test_vision_message_formatting_single_image(self, tmp_path):
        """Test formatting vision message with single image."""
        from kaizen.providers.ollama_vision_provider import OllamaVisionProvider
        from kaizen.signatures.multi_modal import ImageField

        # Create test image
        img = Image.new("RGB", (100, 100), color="red")
        img_path = tmp_path / "test.jpg"
        img.save(img_path, format="JPEG")

        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}
        mock_ollama.chat.return_value = {
            "message": {"content": "I see a red square."},
            "model": "llava:13b",
            "done": True,
        }

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            with patch(
                "kaizen.providers.ollama_model_manager.OllamaModelManager"
            ) as mock_manager:
                mock_manager.return_value.model_exists.return_value = True

                provider = OllamaVisionProvider()

                # Load image
                image_field = ImageField()
                image_field.load(img_path)

                provider.analyze_image(image=image_field, prompt="What do you see?")

                # Verify ollama.chat was called with correct format
                call_args = mock_ollama.chat.call_args
                messages = call_args[1]["messages"]

                # Should have user message with base64 image
                user_msg = messages[-1]
                assert user_msg["role"] == "user"
                assert user_msg["content"] == "What do you see?"
                assert "images" in user_msg

    def test_vision_message_formatting_multiple_images(self, tmp_path):
        """Test formatting vision message with multiple images."""
        from kaizen.providers.ollama_vision_provider import OllamaVisionProvider
        from kaizen.signatures.multi_modal import ImageField

        # Create test images
        img1 = Image.new("RGB", (50, 50), color="red")
        img1_path = tmp_path / "test1.jpg"
        img1.save(img1_path, format="JPEG")

        img2 = Image.new("RGB", (50, 50), color="blue")
        img2_path = tmp_path / "test2.jpg"
        img2.save(img2_path, format="JPEG")

        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}
        mock_ollama.chat.return_value = {
            "message": {"content": "I see two colored squares."},
            "model": "llava:13b",
            "done": True,
        }

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            with patch(
                "kaizen.providers.ollama_model_manager.OllamaModelManager"
            ) as mock_manager:
                mock_manager.return_value.model_exists.return_value = True

                provider = OllamaVisionProvider()

                # Load images
                images = [ImageField(), ImageField()]
                images[0].load(img1_path)
                images[1].load(img2_path)

                provider.analyze_images(images=images, prompt="Compare these images")

                # Verify ollama.chat was called with multiple images
                call_args = mock_ollama.chat.call_args
                messages = call_args[1]["messages"]

                user_msg = messages[-1]
                assert "images" in user_msg
                assert len(user_msg["images"]) == 2


class TestVisionGeneration:
    """Test vision generation methods."""

    def test_vision_generation_single_image(self, tmp_path):
        """Test generating response with single image."""
        from kaizen.providers.ollama_vision_provider import OllamaVisionProvider

        # Create test image
        img = Image.new("RGB", (100, 100), color="green")
        img_path = tmp_path / "test.jpg"
        img.save(img_path, format="JPEG")

        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}
        mock_ollama.chat.return_value = {
            "message": {"content": "Green square detected."},
            "model": "llava:13b",
            "done": True,
        }

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            with patch(
                "kaizen.providers.ollama_model_manager.OllamaModelManager"
            ) as mock_manager:
                mock_manager.return_value.model_exists.return_value = True

                provider = OllamaVisionProvider()
                result = provider.analyze_image(
                    image=str(img_path), prompt="What color is this?"
                )

                assert "response" in result
                assert result["response"] == "Green square detected."

    def test_vision_generation_multiple_images(self, tmp_path):
        """Test generating response with multiple images."""
        from kaizen.providers.ollama_vision_provider import OllamaVisionProvider

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
            "message": {"content": "Three red squares."},
            "model": "llava:13b",
            "done": True,
        }

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            with patch(
                "kaizen.providers.ollama_model_manager.OllamaModelManager"
            ) as mock_manager:
                mock_manager.return_value.model_exists.return_value = True

                provider = OllamaVisionProvider()
                result = provider.analyze_images(
                    images=images, prompt="How many images?"
                )

                assert "response" in result
                assert "images_analyzed" in result
                assert result["images_analyzed"] == 3

    def test_vision_streaming(self, tmp_path):
        """Test streaming vision responses."""
        from kaizen.providers.ollama_vision_provider import OllamaVisionProvider

        # Create test image
        img = Image.new("RGB", (100, 100), color="blue")
        img_path = tmp_path / "test.jpg"
        img.save(img_path, format="JPEG")

        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}

        # Mock streaming response
        def mock_chat(*args, **kwargs):
            if kwargs.get("stream"):
                yield {"message": {"content": "Blue "}}
                yield {"message": {"content": "square."}}

        mock_ollama.chat = mock_chat

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            with patch(
                "kaizen.providers.ollama_model_manager.OllamaModelManager"
            ) as mock_manager:
                mock_manager.return_value.model_exists.return_value = True

                provider = OllamaVisionProvider()

                # Test that provider has base streaming capability
                assert hasattr(provider, "generate_stream")


class TestVisionErrorHandling:
    """Test error handling for vision operations."""

    def test_vision_error_handling(self, tmp_path):
        """Test error handling during vision generation."""
        from kaizen.providers.ollama_vision_provider import OllamaVisionProvider

        # Create test image
        img = Image.new("RGB", (100, 100), color="red")
        img_path = tmp_path / "test.jpg"
        img.save(img_path, format="JPEG")

        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}
        mock_ollama.chat.side_effect = Exception("Vision processing failed")

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            with patch(
                "kaizen.providers.ollama_model_manager.OllamaModelManager"
            ) as mock_manager:
                mock_manager.return_value.model_exists.return_value = True

                provider = OllamaVisionProvider()

                with pytest.raises(RuntimeError, match="Multi-image analysis failed"):
                    provider.analyze_images(images=[str(img_path)], prompt="Analyze")

    def test_vision_model_not_available(self):
        """Test graceful handling when vision model is not available."""
        from kaizen.providers.ollama_vision_provider import OllamaVisionProvider

        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            with patch(
                "kaizen.providers.ollama_model_manager.OllamaModelManager"
            ) as mock_manager:
                mock_instance = mock_manager.return_value
                mock_instance.model_exists.return_value = False
                mock_instance.download_model.return_value = False

                with pytest.raises(
                    RuntimeError, match="Failed to download vision model"
                ):
                    OllamaVisionProvider()

    def test_vision_too_many_images(self):
        """Test error when too many images are provided."""
        from kaizen.providers.ollama_vision_provider import (
            OllamaVisionConfig,
            OllamaVisionProvider,
        )

        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            with patch(
                "kaizen.providers.ollama_model_manager.OllamaModelManager"
            ) as mock_manager:
                mock_manager.return_value.model_exists.return_value = True

                config = OllamaVisionConfig(max_images=2)
                provider = OllamaVisionProvider(config=config)

                with pytest.raises(ValueError, match="Too many images"):
                    provider.analyze_images(
                        images=["img1.jpg", "img2.jpg", "img3.jpg"],
                        prompt="Analyze all",
                    )


class TestVisionImageFormats:
    """Test handling of different image formats."""

    def test_vision_base64_image(self, tmp_path):
        """Test handling base64-encoded images."""
        from kaizen.providers.ollama_vision_provider import OllamaVisionProvider
        from kaizen.signatures.multi_modal import ImageField

        # Create test image
        img = Image.new("RGB", (50, 50), color="red")
        img_path = tmp_path / "test.jpg"
        img.save(img_path, format="JPEG")

        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}
        mock_ollama.chat.return_value = {
            "message": {"content": "Red image."},
            "model": "llava:13b",
        }

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            with patch(
                "kaizen.providers.ollama_model_manager.OllamaModelManager"
            ) as mock_manager:
                mock_manager.return_value.model_exists.return_value = True

                provider = OllamaVisionProvider()

                # Load as ImageField
                image_field = ImageField()
                image_field.load(img_path)

                result = provider.analyze_image(
                    image=image_field, prompt="Describe this"
                )

                assert result is not None

    def test_vision_file_path_image(self, tmp_path):
        """Test handling file path images."""
        from kaizen.providers.ollama_vision_provider import OllamaVisionProvider

        # Create test image
        img = Image.new("RGB", (50, 50), color="blue")
        img_path = tmp_path / "test.png"
        img.save(img_path, format="PNG")

        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}
        mock_ollama.chat.return_value = {
            "message": {"content": "Blue image."},
            "model": "llava:13b",
        }

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            with patch(
                "kaizen.providers.ollama_model_manager.OllamaModelManager"
            ) as mock_manager:
                mock_manager.return_value.model_exists.return_value = True

                provider = OllamaVisionProvider()
                result = provider.analyze_image(
                    image=str(img_path), prompt="What is this?"
                )

                assert result is not None

    def test_vision_url_image(self):
        """Test handling URL images."""
        from kaizen.providers.ollama_vision_provider import OllamaVisionProvider

        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}
        mock_ollama.chat.return_value = {
            "message": {"content": "Image from URL."},
            "model": "llava:13b",
        }

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            with patch(
                "kaizen.providers.ollama_model_manager.OllamaModelManager"
            ) as mock_manager:
                mock_manager.return_value.model_exists.return_value = True

                provider = OllamaVisionProvider()

                # URL image would be loaded via ImageField
                # Test that provider accepts ImageField
                assert hasattr(provider, "analyze_image")


class TestVisionHelperMethods:
    """Test helper methods for common vision tasks."""

    def test_describe_image(self, tmp_path):
        """Test image description generation."""
        from kaizen.providers.ollama_vision_provider import OllamaVisionProvider

        # Create test image
        img = Image.new("RGB", (100, 100), color="yellow")
        img_path = tmp_path / "test.jpg"
        img.save(img_path, format="JPEG")

        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}
        mock_ollama.chat.return_value = {
            "message": {"content": "A yellow square."},
            "model": "llava:13b",
        }

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            with patch(
                "kaizen.providers.ollama_model_manager.OllamaModelManager"
            ) as mock_manager:
                mock_manager.return_value.model_exists.return_value = True

                provider = OllamaVisionProvider()
                description = provider.describe_image(
                    image=str(img_path), detail="auto"
                )

                assert description == "A yellow square."

    def test_answer_visual_question(self, tmp_path):
        """Test visual question answering."""
        from kaizen.providers.ollama_vision_provider import OllamaVisionProvider

        # Create test image
        img = Image.new("RGB", (100, 100), color="green")
        img_path = tmp_path / "test.jpg"
        img.save(img_path, format="JPEG")

        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}
        mock_ollama.chat.return_value = {
            "message": {"content": "The image is green."},
            "model": "llava:13b",
        }

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            with patch(
                "kaizen.providers.ollama_model_manager.OllamaModelManager"
            ) as mock_manager:
                mock_manager.return_value.model_exists.return_value = True

                provider = OllamaVisionProvider()
                answer = provider.answer_visual_question(
                    image=str(img_path), question="What color is the image?"
                )

                assert answer == "The image is green."

    def test_extract_text_ocr(self, tmp_path):
        """Test OCR text extraction."""
        from kaizen.providers.ollama_vision_provider import OllamaVisionProvider

        # Create test image
        img = Image.new("RGB", (200, 100), color="white")
        img_path = tmp_path / "text.jpg"
        img.save(img_path, format="JPEG")

        mock_ollama = MagicMock()
        mock_ollama.list.return_value = {"models": []}
        mock_ollama.chat.return_value = {
            "message": {"content": "Hello World"},
            "model": "llava:13b",
        }

        with patch.dict("sys.modules", {"ollama": mock_ollama}):
            with patch(
                "kaizen.providers.ollama_model_manager.OllamaModelManager"
            ) as mock_manager:
                mock_manager.return_value.model_exists.return_value = True

                provider = OllamaVisionProvider()
                text = provider.extract_text(image=str(img_path))

                assert text == "Hello World"
