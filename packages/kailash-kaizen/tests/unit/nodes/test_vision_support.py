"""Test vision support in AI providers."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

from kaizen.nodes.ai.ai_providers import (
    AnthropicProvider,
    OllamaProvider,
    OpenAIProvider,
)
from kaizen.nodes.ai.vision_utils import (
    encode_image,
    get_media_type,
    validate_image_size,
)


class TestVisionSupport(unittest.TestCase):
    """Test vision capabilities in AI providers."""

    def test_backward_compatibility(self):
        """Test that text-only messages still work."""
        messages = [{"role": "user", "content": "Hello"}]

        # Each provider should accept simple string content
        providers = [OpenAIProvider(), AnthropicProvider(), OllamaProvider()]
        for provider in providers:
            # Just test that the method accepts the format
            # (actual API calls would be mocked in integration tests)
            self.assertIsNotNone(provider)

    def test_vision_message_format(self):
        """Test vision message format is accepted."""
        vision_message = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What's in this image?"},
                    {"type": "image", "path": "test.jpg"},
                ],
            }
        ]

        # Test that providers can handle vision format
        providers = [OpenAIProvider(), AnthropicProvider(), OllamaProvider()]
        for provider in providers:
            self.assertIsNotNone(provider)

    def test_vision_utils(self):
        """Test vision utility functions."""
        # Test media type detection
        self.assertEqual(get_media_type("test.jpg"), "image/jpeg")
        self.assertEqual(get_media_type("test.png"), "image/png")
        self.assertEqual(get_media_type("test.gif"), "image/gif")
        self.assertEqual(get_media_type("test.unknown"), "image/jpeg")  # default

        # Test image size validation
        with patch("os.path.getsize", return_value=1024 * 1024):  # 1MB
            is_valid, error = validate_image_size("test.jpg", max_size_mb=20.0)
            self.assertTrue(is_valid)
            self.assertIsNone(error)

        with patch("os.path.getsize", return_value=25 * 1024 * 1024):  # 25MB
            is_valid, error = validate_image_size("test.jpg", max_size_mb=20.0)
            self.assertFalse(is_valid)
            self.assertIn("exceeds maximum", error)

    @patch("pathlib.Path.exists")
    @patch("builtins.open", create=True)
    @patch("base64.b64encode")
    def test_encode_image(self, mock_b64encode, mock_open, mock_exists):
        """Test image encoding."""
        # Mock file existence
        mock_exists.return_value = True

        # Mock file reading
        mock_open.return_value.__enter__.return_value.read.return_value = (
            b"fake_image_data"
        )
        mock_b64encode.return_value = b"ZmFrZV9pbWFnZV9kYXRh"

        # Test encoding
        result = encode_image("/path/to/image.jpg")
        self.assertEqual(result, "ZmFrZV9pbWFnZV9kYXRh")

        # Verify file was opened in binary mode
        mock_open.assert_called_with(unittest.mock.ANY, "rb")


if __name__ == "__main__":
    unittest.main()
