"""
Test suite for MultiModalSignature base class.

Tests mixed text/image/audio fields and formatting for Ollama API.
"""

import base64

from kaizen.signatures.multi_modal import AudioField, ImageField, MultiModalSignature
from PIL import Image


class TestMultiModalSignatureCreation:
    """Test MultiModalSignature creation with various field combinations."""

    def test_multi_modal_signature_creation(self):
        """Test basic MultiModalSignature subclass creation."""

        class TestSignature(MultiModalSignature):
            pass

        sig = TestSignature()
        assert isinstance(sig, MultiModalSignature)

    def test_multi_modal_signature_with_image_field(self, tmp_path):
        """Test signature with image field."""
        # Create test image
        img = Image.new("RGB", (100, 100), color="red")
        img_path = tmp_path / "test.jpg"
        img.save(img_path, format="JPEG")

        # Create signature with image field
        class VisionSignature(MultiModalSignature):
            def __init__(self):
                self.image = ImageField(description="Input image")

        sig = VisionSignature()
        sig.image.load(img_path)

        assert sig.image.validate()

    def test_multi_modal_signature_with_text_field(self):
        """Test signature with text field."""

        class TextSignature(MultiModalSignature):
            def __init__(self):
                self.question = "What is this?"

        sig = TextSignature()
        assert sig.question == "What is this?"


class TestMultiModalSignatureTextOnly:
    """Test MultiModalSignature with only text fields."""

    def test_multi_modal_signature_text_only(self):
        """Test signature with only text fields."""

        class TextOnlySignature(MultiModalSignature):
            def __init__(self):
                self.question = ""
                self.context = ""

        sig = TextOnlySignature()
        sig.question = "What is the capital of France?"
        sig.context = "Geography question"

        assert sig.question == "What is the capital of France?"
        assert sig.context == "Geography question"

    def test_multi_modal_signature_format_text_only(self):
        """Test formatting signature with only text fields."""

        class TextOnlySignature(MultiModalSignature):
            pass

        result = TextOnlySignature.format_for_ollama(
            question="What is 2+2?", context="Math problem"
        )

        assert "content" in result
        assert "question" in result["content"]
        assert "context" in result["content"]
        assert "2+2" in result["content"]
        assert "images" not in result


class TestMultiModalSignatureImageOnly:
    """Test MultiModalSignature with only image fields."""

    def test_multi_modal_signature_image_only(self, tmp_path):
        """Test signature with only image fields."""
        # Create test image
        img = Image.new("RGB", (100, 100), color="blue")
        img_path = tmp_path / "test.png"
        img.save(img_path, format="PNG")

        class ImageOnlySignature(MultiModalSignature):
            def __init__(self):
                self.image = ImageField(description="Input image")

        sig = ImageOnlySignature()
        sig.image.load(img_path)

        assert sig.image.validate()
        assert sig.image._format == "png"

    def test_multi_modal_signature_format_image_only(self, tmp_path):
        """Test formatting signature with only image fields."""
        # Create test image
        img = Image.new("RGB", (50, 50), color="green")
        img_path = tmp_path / "test.jpg"
        img.save(img_path, format="JPEG")

        # Load image
        image_field = ImageField()
        image_field.load(img_path)

        # Format for Ollama
        result = MultiModalSignature.format_for_ollama(image=image_field)

        assert "images" in result
        assert len(result["images"]) == 1
        assert result["images"][0].startswith("data:image/")
        assert "base64," in result["images"][0]


class TestMultiModalSignatureMixedFields:
    """Test MultiModalSignature with mixed text/image/audio fields."""

    def test_multi_modal_signature_mixed_fields(self, tmp_path):
        """Test signature with mixed text and image fields."""
        # Create test image
        img = Image.new("RGB", (100, 100), color="red")
        img_path = tmp_path / "test.jpg"
        img.save(img_path, format="JPEG")

        class MixedSignature(MultiModalSignature):
            def __init__(self):
                self.image = ImageField(description="Input image")
                self.question = ""

        sig = MixedSignature()
        sig.image.load(img_path)
        sig.question = "What color is this?"

        assert sig.image.validate()
        assert sig.question == "What color is this?"

    def test_multi_modal_signature_text_image_audio(self, tmp_path):
        """Test signature with text, image, and audio fields."""
        # Create test image
        img = Image.new("RGB", (100, 100), color="blue")
        img_path = tmp_path / "test.jpg"
        img.save(img_path, format="JPEG")

        # Create test audio
        audio_path = tmp_path / "test.mp3"
        with open(audio_path, "wb") as f:
            f.write(b"ID3" + b"\x00" * 1000)

        class FullSignature(MultiModalSignature):
            def __init__(self):
                self.image = ImageField(description="Input image")
                self.audio = AudioField(description="Input audio")
                self.question = ""

        sig = FullSignature()
        sig.image.load(img_path)
        sig.audio.load(audio_path)
        sig.question = "Analyze this media"

        assert sig.image.validate()
        assert sig.audio.validate()
        assert sig.question == "Analyze this media"

    def test_multi_modal_signature_format_mixed(self, tmp_path):
        """Test formatting signature with mixed fields."""
        # Create test image
        img = Image.new("RGB", (50, 50), color="yellow")
        img_path = tmp_path / "test.png"
        img.save(img_path, format="PNG")

        # Load image
        image_field = ImageField()
        image_field.load(img_path)

        # Format with text and image
        result = MultiModalSignature.format_for_ollama(
            image=image_field, question="What is this?", context="Visual analysis"
        )

        assert "content" in result
        assert "images" in result
        assert "question" in result["content"]
        assert "What is this?" in result["content"]
        assert "context" in result["content"]
        assert len(result["images"]) == 1


class TestMultiModalSignatureOllamaFormat:
    """Test formatting messages for Ollama vision API."""

    def test_multi_modal_signature_ollama_format_basic(self, tmp_path):
        """Test basic Ollama formatting with text and image."""
        # Create test image
        img = Image.new("RGB", (100, 100), color="red")
        img_path = tmp_path / "test.jpg"
        img.save(img_path, format="JPEG")

        # Load image
        image_field = ImageField()
        image_field.load(img_path)

        # Format for Ollama
        result = MultiModalSignature.format_for_ollama(
            image=image_field, question="Describe this image"
        )

        assert isinstance(result, dict)
        assert "content" in result
        assert "images" in result
        assert isinstance(result["images"], list)
        assert len(result["images"]) == 1

    def test_multi_modal_signature_ollama_format_multiple_images(self, tmp_path):
        """Test Ollama formatting with multiple images."""
        # Create test images
        img1 = Image.new("RGB", (50, 50), color="red")
        img1_path = tmp_path / "test1.jpg"
        img1.save(img1_path, format="JPEG")

        img2 = Image.new("RGB", (50, 50), color="blue")
        img2_path = tmp_path / "test2.jpg"
        img2.save(img2_path, format="JPEG")

        # Load images
        image1 = ImageField()
        image1.load(img1_path)

        image2 = ImageField()
        image2.load(img2_path)

        # Format for Ollama
        result = MultiModalSignature.format_for_ollama(
            image1=image1, image2=image2, question="Compare these images"
        )

        assert "images" in result
        assert len(result["images"]) == 2
        assert all(img.startswith("data:image/") for img in result["images"])

    def test_multi_modal_signature_ollama_format_content_structure(self, tmp_path):
        """Test content structure in Ollama format."""
        # Create test image
        img = Image.new("RGB", (50, 50), color="green")
        img_path = tmp_path / "test.jpg"
        img.save(img_path, format="JPEG")

        # Load image
        image_field = ImageField()
        image_field.load(img_path)

        # Format with multiple text fields
        result = MultiModalSignature.format_for_ollama(
            image=image_field,
            question="What is this?",
            context="Object identification",
            instructions="Be specific",
        )

        content = result["content"]

        # Check all text fields are in content
        assert "question" in content
        assert "What is this?" in content
        assert "context" in content
        assert "Object identification" in content
        assert "instructions" in content
        assert "Be specific" in content

    def test_multi_modal_signature_ollama_format_no_images(self):
        """Test Ollama format with no images (text only)."""
        result = MultiModalSignature.format_for_ollama(
            question="What is 2+2?", context="Math problem"
        )

        assert "content" in result
        assert "images" not in result  # No images key when no images
        assert "question" in result["content"]
        assert "context" in result["content"]


class TestMultiModalSignatureValidation:
    """Test validation of multi-modal signatures."""

    def test_multi_modal_signature_validation_all_valid(self, tmp_path):
        """Test validation passes when all fields are valid."""
        # Create test image
        img = Image.new("RGB", (100, 100), color="red")
        img_path = tmp_path / "test.jpg"
        img.save(img_path, format="JPEG")

        class ValidSignature(MultiModalSignature):
            def __init__(self):
                self.image = ImageField(description="Input image")
                self.question = ""

            def validate(self):
                return self.image.validate() and len(self.question) > 0

        sig = ValidSignature()
        sig.image.load(img_path)
        sig.question = "What is this?"

        assert sig.validate()

    def test_multi_modal_signature_validation_invalid_image(self, tmp_path):
        """Test validation fails with invalid image."""

        class ValidSignature(MultiModalSignature):
            def __init__(self):
                self.image = ImageField(description="Input image")

            def validate(self):
                return self.image.validate()

        sig = ValidSignature()
        # Don't load image

        assert not sig.validate()

    def test_multi_modal_signature_validation_mixed_validity(self, tmp_path):
        """Test validation with some valid and some invalid fields."""
        # Create test image
        img = Image.new("RGB", (100, 100), color="blue")
        img_path = tmp_path / "test.jpg"
        img.save(img_path, format="JPEG")

        class MixedSignature(MultiModalSignature):
            def __init__(self):
                self.image = ImageField(description="Input image")
                self.audio = AudioField(description="Input audio")

            def validate(self):
                return self.image.validate() and self.audio.validate()

        sig = MixedSignature()
        sig.image.load(img_path)  # Valid
        # Don't load audio - invalid

        assert not sig.validate()


class TestMultiModalSignatureEdgeCases:
    """Test edge cases and error handling."""

    def test_multi_modal_signature_empty_inputs(self):
        """Test formatting with empty inputs."""
        result = MultiModalSignature.format_for_ollama()

        assert "content" in result
        assert result["content"] == ""
        assert "images" not in result

    def test_multi_modal_signature_none_values(self):
        """Test handling of None values in inputs."""
        result = MultiModalSignature.format_for_ollama(question=None, image=None)

        assert "content" in result
        # None values should be handled gracefully

    def test_multi_modal_signature_base64_image_in_format(self, tmp_path):
        """Test that base64 images are properly formatted."""
        # Create small test image
        img = Image.new("RGB", (10, 10), color="red")
        img_path = tmp_path / "tiny.jpg"
        img.save(img_path, format="JPEG")

        # Load and format
        image_field = ImageField()
        image_field.load(img_path)

        result = MultiModalSignature.format_for_ollama(image=image_field)

        # Verify base64 image format
        b64_image = result["images"][0]
        assert b64_image.startswith("data:image/jpeg;base64,")

        # Verify we can decode it
        b64_data = b64_image.split(",", 1)[1]
        decoded = base64.b64decode(b64_data)
        assert len(decoded) > 0
