"""
Integration test for multi-modal signature system.

Tests end-to-end functionality with real images and audio files.
Demonstrates usage with Ollama vision models.
"""

import os

import pytest
from kaizen.signatures.multi_modal import AudioField, ImageField, MultiModalSignature
from PIL import Image


class TestMultiModalIntegration:
    """Integration tests for multi-modal signature system."""

    @pytest.fixture
    def test_image(self, tmp_path):
        """Create a test image file."""
        img = Image.new("RGB", (800, 600), color=(100, 150, 200))
        img_path = tmp_path / "test_image.jpg"
        img.save(img_path, format="JPEG", quality=90)
        return img_path

    @pytest.fixture
    def test_audio(self, tmp_path):
        """Create a test audio file."""
        audio_path = tmp_path / "test_audio.mp3"
        # Create dummy MP3 file
        with open(audio_path, "wb") as f:
            f.write(b"ID3\x04\x00\x00" + b"\x00" * 5000)
        return audio_path

    def test_image_field_end_to_end(self, test_image):
        """Test ImageField end-to-end workflow."""
        # Create and load image
        field = ImageField(
            description="Test image for analysis",
            max_size_mb=5.0,
            formats=["jpg", "jpeg", "png"],
        )

        # Load from file
        field.load(test_image)

        # Validate
        assert field.validate()
        assert field._format == "jpeg"
        assert field._size_bytes > 0

        # Convert to base64
        b64_str = field.to_base64()
        assert b64_str.startswith("data:image/jpeg;base64,")

        # Verify we can reconstruct
        import base64

        b64_data = b64_str.split(",", 1)[1]
        decoded = base64.b64decode(b64_data)
        assert len(decoded) == field._size_bytes

    def test_audio_field_end_to_end(self, test_audio):
        """Test AudioField end-to-end workflow."""
        # Create and load audio
        field = AudioField(
            description="Test audio for transcription",
            max_duration_sec=300.0,
            max_size_mb=10.0,
        )

        # Load from file
        field.load(test_audio)

        # Validate
        assert field.validate()
        assert field._format == "mp3"
        assert field._size_bytes > 0
        assert field._duration_sec >= 0  # Duration extracted

    def test_multi_modal_signature_ollama_format(self, test_image, test_audio):
        """Test MultiModalSignature formatting for Ollama."""

        # Create signature with mixed fields
        class VisionQASignature(MultiModalSignature):
            def __init__(self):
                self.image = ImageField(description="Image to analyze")
                self.audio = AudioField(description="Audio context")
                self.question = ""

        sig = VisionQASignature()

        # Load media
        sig.image.load(test_image)
        sig.audio.load(test_audio)

        # Format for Ollama
        result = sig.format_for_ollama(
            image=sig.image,
            question="What do you see in this image?",
            context="Analyze the visual content",
        )

        # Verify structure
        assert "content" in result
        assert "images" in result
        assert len(result["images"]) == 1
        assert "question" in result["content"]
        assert "What do you see" in result["content"]
        assert "context" in result["content"]

    def test_multiple_images_workflow(self, tmp_path):
        """Test workflow with multiple images."""
        # Create multiple test images
        img1_path = tmp_path / "img1.png"
        img1 = Image.new("RGB", (400, 300), color="red")
        img1.save(img1_path, format="PNG")

        img2_path = tmp_path / "img2.png"
        img2 = Image.new("RGB", (400, 300), color="blue")
        img2.save(img2_path, format="PNG")

        # Load images
        image1 = ImageField().load(img1_path)
        image2 = ImageField().load(img2_path)

        # Format for Ollama
        result = MultiModalSignature.format_for_ollama(
            image1=image1, image2=image2, question="Compare these two images"
        )

        # Verify multiple images
        assert "images" in result
        assert len(result["images"]) == 2
        assert all(img.startswith("data:image/") for img in result["images"])

    def test_image_auto_resize_integration(self, tmp_path):
        """Test auto-resize with real workflow."""
        import random

        from PIL import ImageDraw

        # Create a larger image
        img = Image.new("RGB", (2000, 2000))
        draw = ImageDraw.Draw(img)

        # Add random content
        for _ in range(5000):
            x, y = random.randint(0, 1999), random.randint(0, 1999)
            color = (
                random.randint(0, 255),
                random.randint(0, 255),
                random.randint(0, 255),
            )
            draw.point((x, y), fill=color)

        img_path = tmp_path / "large.jpg"
        img.save(img_path, format="JPEG", quality=95)

        # Load with auto-resize
        field = ImageField(max_size_mb=0.5, auto_resize=True)
        field.load(img_path)

        # Should be resized
        assert field._size_bytes <= 0.5 * 1024 * 1024
        assert field.validate()
        assert field._format == "jpeg"  # Converted to JPEG

    def test_error_handling_integration(self):
        """Test error handling in real scenarios."""
        # Test missing file
        field = ImageField()
        with pytest.raises(FileNotFoundError):
            field.load("/nonexistent/path/to/image.jpg")

        # Test unsupported format
        field = AudioField(formats=["mp3", "wav"])
        with pytest.raises(ValueError, match="Unsupported audio format"):
            # This will fail during format detection

            with tempfile.NamedTemporaryFile(suffix=".flac", delete=False) as f:
                f.write(b"fLaC" + b"\x00" * 1000)
                temp_path = f.name

            try:
                field.load(temp_path)
            finally:
                os.unlink(temp_path)

    def test_base64_roundtrip(self, test_image):
        """Test base64 encoding/decoding roundtrip."""
        import base64

        # Load image
        field = ImageField()
        field.load(test_image)

        # Convert to base64
        b64_str = field.to_base64()

        # Decode
        b64_data = b64_str.split(",", 1)[1]
        decoded_bytes = base64.b64decode(b64_data)

        # Create new field from decoded bytes
        field2 = ImageField()
        field2.load(decoded_bytes)

        # Should be identical
        assert field2._format == field._format
        assert field2._size_bytes == field._size_bytes
        assert field2.validate()

    def test_vision_qa_signature_example(self, test_image):
        """Example: Vision QA signature usage."""

        class VisionQASignature(MultiModalSignature):
            """Signature for vision-based question answering."""

            def __init__(self):
                self.image = ImageField(
                    description="Image to analyze",
                    max_size_mb=2.0,
                    formats=["jpg", "jpeg", "png", "webp"],
                )
                self.question = ""

            def prepare_for_ollama(self, image_path: str, question: str):
                """Prepare inputs for Ollama vision API."""
                self.image.load(image_path)
                self.question = question

                return self.format_for_ollama(image=self.image, question=question)

        # Use the signature
        sig = VisionQASignature()
        ollama_input = sig.prepare_for_ollama(
            str(test_image), "Describe what you see in this image"
        )

        # Verify output format
        assert "content" in ollama_input
        assert "images" in ollama_input
        assert "question" in ollama_input["content"]
        assert "Describe what you see" in ollama_input["content"]

    def test_audio_transcription_signature_example(self, test_audio):
        """Example: Audio transcription signature usage."""

        class TranscriptionSignature(MultiModalSignature):
            """Signature for audio transcription."""

            def __init__(self):
                self.audio = AudioField(
                    description="Audio to transcribe",
                    max_duration_sec=600.0,  # 10 minutes
                    formats=["mp3", "wav", "m4a"],
                )

            def prepare_for_processing(self, audio_path: str):
                """Prepare audio for processing."""
                self.audio.load(audio_path)

                return {
                    "audio_data": self.audio._data,
                    "format": self.audio._format,
                    "duration": self.audio._duration_sec,
                    "size_mb": self.audio._size_bytes / (1024 * 1024),
                }

        # Use the signature
        sig = TranscriptionSignature()
        audio_info = sig.prepare_for_processing(str(test_audio))

        # Verify output
        assert "audio_data" in audio_info
        assert "format" in audio_info
        assert "duration" in audio_info
        assert "size_mb" in audio_info
        assert audio_info["format"] == "mp3"
        assert audio_info["duration"] >= 0

    def test_real_world_workflow(self, test_image, test_audio):
        """Test complete real-world multi-modal workflow."""

        class MultiModalAnalysisSignature(MultiModalSignature):
            """Complete multi-modal analysis signature."""

            def __init__(self):
                self.image = ImageField(description="Visual input")
                self.audio = AudioField(description="Audio input")
                self.instructions = ""
                self.context = ""

            def validate_inputs(self):
                """Validate all inputs are ready."""
                return (
                    self.image.validate()
                    and self.audio.validate()
                    and len(self.instructions) > 0
                )

            def prepare_analysis(self):
                """Prepare complete analysis input."""
                if not self.validate_inputs():
                    raise ValueError("Invalid inputs")

                return {
                    "visual": self.image.to_base64(),
                    "audio_info": {
                        "format": self.audio._format,
                        "duration": self.audio._duration_sec,
                    },
                    "metadata": {
                        "instructions": self.instructions,
                        "context": self.context,
                    },
                }

        # Create and configure signature
        sig = MultiModalAnalysisSignature()
        sig.image.load(test_image)
        sig.audio.load(test_audio)
        sig.instructions = "Analyze the visual and audio content together"
        sig.context = "Multi-modal analysis task"

        # Prepare analysis
        analysis_input = sig.prepare_analysis()

        # Verify complete output
        assert "visual" in analysis_input
        assert "audio_info" in analysis_input
        assert "metadata" in analysis_input
        assert analysis_input["visual"].startswith("data:image/")
        assert analysis_input["audio_info"]["format"] == "mp3"
        assert analysis_input["metadata"]["instructions"] == sig.instructions


class TestMultiModalPerformance:
    """Performance tests for multi-modal operations."""

    def test_image_loading_performance(self, tmp_path):
        """Test image loading performance."""
        import time

        # Create test image
        img = Image.new("RGB", (1000, 1000), color="red")
        img_path = tmp_path / "perf_test.jpg"
        img.save(img_path, format="JPEG")

        # Measure loading time
        field = ImageField()
        start = time.time()
        field.load(img_path)
        duration = time.time() - start

        # Should be fast (<100ms for 1000x1000 image)
        assert duration < 0.1
        assert field.validate()

    def test_base64_conversion_performance(self, tmp_path):
        """Test base64 conversion performance."""
        import time

        # Create test image
        img = Image.new("RGB", (800, 600), color="blue")
        img_path = tmp_path / "b64_test.jpg"
        img.save(img_path, format="JPEG")

        # Load image
        field = ImageField()
        field.load(img_path)

        # Measure base64 conversion
        start = time.time()
        b64_str = field.to_base64()
        duration = time.time() - start

        # Should be fast (<50ms)
        assert duration < 0.05
        assert len(b64_str) > 0

    def test_multiple_images_performance(self, tmp_path):
        """Test performance with multiple images."""
        import time

        # Create 5 test images
        images = []
        for i in range(5):
            img = Image.new("RGB", (500, 500), color=(i * 50, 100, 200))
            img_path = tmp_path / f"img_{i}.jpg"
            img.save(img_path, format="JPEG")
            images.append(img_path)

        # Measure batch loading
        start = time.time()
        fields = [ImageField().load(img) for img in images]
        duration = time.time() - start

        # Should be reasonable (<500ms for 5 images)
        assert duration < 0.5
        assert all(f.validate() for f in fields)
