"""Integration tests for vision support in AI providers."""

import base64
import os
import sys
from pathlib import Path

import pytest

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.ai.ai_providers import get_provider


@pytest.fixture
def test_image_path():
    """Create a test image for vision tests."""
    # Create a simple test image
    image_path = Path(__file__).parent / "test_image.png"
    if not image_path.exists():
        # Create a proper PNG image (10x10 red square)
        try:
            from PIL import Image

            img = Image.new("RGB", (10, 10), color="red")
            img.save(image_path, "PNG")
        except ImportError:
            # Fallback to a minimal but valid PNG
            # This is a 2x2 red PNG created with PIL and verified
            image_path.write_bytes(
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x02\x00\x00\x00\x02"
                b"\x08\x02\x00\x00\x00\xfd\xd4\x9as\x00\x00\x00\x01sRGB\x00\xae\xce\x1c\xe9"
                b"\x00\x00\x00\x04gAMA\x00\x00\xb1\x8f\x0b\xfca\x05\x00\x00\x00\tpHYs\x00"
                b"\x00\x0e\xc3\x00\x00\x0e\xc3\x01\xc7o\xa8d\x00\x00\x00\x0eIDATx\xdac\xf8"
                b"\xcf\xc0\x00\x00\x03\x01\x01\x00\x18\xdd\x8d\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
            )
    yield image_path
    # Cleanup
    if image_path.exists():
        image_path.unlink()


@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key not set")
def test_openai_vision(test_image_path):
    """Test OpenAI vision capabilities with real API."""
    result = LLMAgentNode().run(
        provider="openai",
        model="o4-mini",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "What color is this 1x1 pixel image? Just say the color name.",
                    },
                    {"type": "image", "path": str(test_image_path)},
                ],
            }
        ],
        generation_config={"max_completion_tokens": 100},
    )

    if not result["success"]:
        pytest.fail(f"OpenAI vision failed: {result.get('error', 'Unknown error')}")

    assert "response" in result
    content = result["response"]["content"].lower()
    print(f"OpenAI response: {content}")


@pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"), reason="Anthropic API key not set"
)
def test_anthropic_vision(test_image_path):
    """Test Anthropic vision capabilities with real API."""
    result = LLMAgentNode().run(
        provider="anthropic",
        model="claude-sonnet-4-20250514",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "What color is this 1x1 pixel image? Just say the color name.",
                    },
                    {"type": "image", "path": str(test_image_path)},
                ],
            }
        ],
        generation_config={"max_tokens": 10, "temperature": 0},
    )

    if not result["success"]:
        pytest.fail(f"Anthropic vision failed: {result.get('error', 'Unknown error')}")

    assert "response" in result
    content = result["response"]["content"].lower()
    print(f"Anthropic response: {content}")


# TODO: Implement Ollama vision tests when available
@pytest.mark.skipif(not os.getenv("OLLAMA_AVAIL"), reason="Ollama not available")
def test_ollama_vision_if_available(test_image_path):
    """Test Ollama vision if available and model is pulled."""
    provider = get_provider("ollama")
    if not provider.is_available():
        pytest.skip("Ollama not available")

    # Try with a vision model if available
    vision_models = ["llama3.2-vision"]

    for model in vision_models:
        try:
            result = LLMAgentNode().run(
                provider="ollama",
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "What color is this image?"},
                            {"type": "image", "path": str(test_image_path)},
                        ],
                    }
                ],
                generation_config={"max_tokens": 10, "temperature": 0},
            )

            if result["success"]:
                print(f"Ollama {model} response: {result['response']['content']}")
                return  # Test passed with this model

        except Exception as e:
            print(f"Model {model} not available: {e}")
            continue

    pytest.skip("No Ollama vision models available")


def test_base64_image_support(test_image_path):
    """Test base64 encoded image support."""
    # Read and encode the test image
    image_data = test_image_path.read_bytes()
    base64_image = base64.b64encode(image_data).decode("utf-8")

    # Test with mock provider (always available)
    result = LLMAgentNode().run(
        provider="mock",
        model="mock-vision",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Analyze this base64 image"},
                    {
                        "type": "image",
                        "base64": base64_image,
                        "media_type": "image/png",
                    },
                ],
            }
        ],
    )

    if not result["success"]:
        pytest.fail(f"Base64 image test failed: {result.get('error', 'Unknown error')}")

    assert result["success"]
    print(
        f"Mock provider handled base64 image: {result['response']['content'][:50]}..."
    )


def test_multiple_images(test_image_path):
    """Test multiple image support."""
    # Create a second test image (blue pixel)
    test_image_2 = Path(__file__).parent / "test_image_2.png"
    test_image_2.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\x00\x18\x05"
        b"\x00\x00\x03\x00\x01\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    try:
        # Test with mock provider
        result = LLMAgentNode().run(
            provider="mock",
            model="mock-vision",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Compare these two images"},
                        {"type": "image", "path": str(test_image_path)},
                        {"type": "image", "path": str(test_image_2)},
                    ],
                }
            ],
        )

        if not result["success"]:
            pytest.fail(
                f"Multiple images test failed: {result.get('error', 'Unknown error')}"
            )

        assert result["success"]
        print(f"Multi-image test passed: {result['response']['content'][:50]}...")

    finally:
        if test_image_2.exists():
            test_image_2.unlink()


def test_backward_compatibility():
    """Test that text-only messages still work."""
    # Test with simple string content
    result = LLMAgentNode().run(
        provider="mock",
        model="mock-model",
        messages=[{"role": "user", "content": "Hello, how are you?"}],
    )

    assert result["success"]
    assert "response" in result
    print(
        f"Backward compatibility test passed: {result['response']['content'][:50]}..."
    )
