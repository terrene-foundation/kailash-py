"""
Integration tests for complete multi-modal workflows.

Following TDD methodology: Write tests FIRST, then implement.
Tests use real infrastructure (Ollama, real files) - NO MOCKING.
"""

import pytest

# Test infrastructure
try:
    from kaizen.agents.multi_modal import (
        MultiModalAgent,
        MultiModalConfig,
        TranscriptionAgent,
        TranscriptionAgentConfig,
        VisionAgent,
        VisionAgentConfig,
    )
    from kaizen.cost.tracker import CostTracker
    from kaizen.memory import SharedMemoryPool
    from kaizen.providers import OLLAMA_AVAILABLE
    from kaizen.providers.multi_modal_adapter import get_multi_modal_adapter
    from kaizen.signatures import (
        AudioField,
        ImageField,
        InputField,
        MultiModalSignature,
        OutputField,
    )

    IMPORTS_AVAILABLE = True
except ImportError:
    IMPORTS_AVAILABLE = False
    OLLAMA_AVAILABLE = False  # Define fallback

pytestmark = [
    pytest.mark.skipif(
        not IMPORTS_AVAILABLE, reason="Multi-modal components not yet implemented"
    ),
    pytest.mark.integration,
]


@pytest.fixture
def test_image(tmp_path):
    """Create a test image with text for OCR testing."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (800, 600), color="white")
    draw = ImageDraw.Draw(img)

    # Add text for OCR
    text = "INVOICE #12345\nDate: 2025-01-15\nTotal: $1,234.56"
    draw.text((50, 50), text, fill="black")

    image_path = tmp_path / "invoice.png"
    img.save(image_path)
    return str(image_path)


@pytest.fixture
def test_audio(tmp_path):
    """Create a test audio file."""
    import struct
    import wave

    audio_path = tmp_path / "test_speech.wav"
    with wave.open(str(audio_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        # Write 2 seconds of simple tone (440 Hz)
        for i in range(32000):
            value = int(16000 * 0.5)  # Simple tone
            wav.writeframes(struct.pack("<h", value if i % 100 < 50 else -value))
    return str(audio_path)


@pytest.fixture
def cost_tracker():
    """Create a cost tracker for monitoring usage."""
    return CostTracker(budget_limit=5.0, warn_on_openai_usage=True)


@pytest.fixture
def memory_pool():
    """Create a shared memory pool."""
    return SharedMemoryPool()


class TestDocumentUnderstandingWorkflow:
    """Test complete document understanding workflow."""

    @pytest.mark.skipif(not OLLAMA_AVAILABLE, reason="Ollama not available")
    def test_image_to_text_extraction(self, test_image, cost_tracker):
        """Test extracting text from document image."""

        class DocumentSignature(MultiModalSignature):
            image: ImageField = InputField(description="Document image")
            query: str = InputField(description="What to extract")
            extracted_text: str = OutputField(description="Extracted text")

        config = MultiModalConfig(
            llm_provider="ollama", model="llava:13b", enable_cost_tracking=True
        )

        agent = MultiModalAgent(
            config=config, signature=DocumentSignature(), cost_tracker=cost_tracker
        )

        result = agent.analyze(
            image=test_image, query="Extract all text from this invoice"
        )

        # Verify result
        assert "extracted_text" in result
        assert len(result["extracted_text"]) > 0

        # Verify cost tracking (should be $0 for Ollama)
        assert cost_tracker.get_total_cost() == 0.0
        stats = cost_tracker.get_usage_stats()
        assert stats["ollama_calls"] > 0

    @pytest.mark.skipif(not OLLAMA_AVAILABLE, reason="Ollama not available")
    def test_multi_step_document_analysis(self, test_image, memory_pool):
        """Test multi-step workflow: OCR → Analysis → Summary."""

        # Step 1: OCR
        class OCRSignature(MultiModalSignature):
            image: ImageField = InputField(description="Document to OCR")
            text: str = OutputField(description="Extracted text")

        ocr_config = MultiModalConfig(llm_provider="ollama", model="llava:13b")
        ocr_agent = MultiModalAgent(
            config=ocr_config, signature=OCRSignature(), memory_pool=memory_pool
        )

        ocr_result = ocr_agent.run(image=test_image, store_in_memory=True)

        # Step 2: Analyze extracted text
        class AnalysisSignature(MultiModalSignature):
            text: str = InputField(description="Text to analyze")
            analysis: str = OutputField(description="Document analysis")

        analysis_config = MultiModalConfig(llm_provider="ollama")
        analysis_agent = MultiModalAgent(
            config=analysis_config,
            signature=AnalysisSignature(),
            memory_pool=memory_pool,
        )

        analysis_result = analysis_agent.analyze(
            text=ocr_result["text"], store_in_memory=True
        )

        # Verify workflow
        assert "text" in ocr_result
        assert "analysis" in analysis_result

        # Verify memory integration
        memories = memory_pool.retrieve(agent_id=ocr_agent.agent_id, limit=10)
        assert len(memories) > 0

    @pytest.mark.skipif(not OLLAMA_AVAILABLE, reason="Ollama not available")
    def test_batch_document_processing(self, tmp_path, cost_tracker):
        """Test batch processing of multiple documents."""
        # Create multiple test images
        from PIL import Image, ImageDraw

        images = []
        for i in range(3):
            img = Image.new("RGB", (400, 300), color="white")
            draw = ImageDraw.Draw(img)
            draw.text((50, 50), f"Document {i+1}", fill="black")
            img_path = tmp_path / f"doc_{i}.png"
            img.save(img_path)
            images.append(str(img_path))

        class BatchSignature(MultiModalSignature):
            image: ImageField = InputField(description="Document")
            summary: str = OutputField(description="Document summary")

        config = MultiModalConfig(
            llm_provider="ollama", model="llava:13b", enable_cost_tracking=True
        )

        agent = MultiModalAgent(
            config=config, signature=BatchSignature(), cost_tracker=cost_tracker
        )

        results = agent.batch_analyze(images=images)

        # Verify batch processing
        assert len(results) == 3
        assert all("summary" in r for r in results)

        # Verify cost (should be $0 for Ollama)
        assert cost_tracker.get_total_cost() == 0.0


class TestAudioTranscriptionWorkflow:
    """Test audio transcription workflows."""

    @pytest.mark.skipif(not OLLAMA_AVAILABLE, reason="Ollama not available")
    def test_audio_transcription(self, test_audio, cost_tracker):
        """Test basic audio transcription."""

        class TranscriptSignature(MultiModalSignature):
            audio: AudioField = InputField(description="Audio to transcribe")
            transcript: str = OutputField(description="Transcription")
            language: str = OutputField(description="Detected language")

        config = MultiModalConfig(llm_provider="ollama", enable_cost_tracking=True)

        agent = MultiModalAgent(
            config=config, signature=TranscriptSignature(), cost_tracker=cost_tracker
        )

        result = agent.analyze(audio=test_audio)

        # Verify transcription
        assert "transcript" in result
        assert "language" in result

        # Verify cost (should be $0 for local Whisper)
        assert cost_tracker.get_total_cost() == 0.0

    @pytest.mark.skipif(not OLLAMA_AVAILABLE, reason="Ollama not available")
    def test_transcription_with_timestamps(self, test_audio):
        """Test transcription with word-level timestamps."""
        transcription_config = TranscriptionAgentConfig(
            model_size="base", word_timestamps=True
        )

        agent = TranscriptionAgent(config=transcription_config)

        result = agent.transcribe(audio=test_audio)

        # Verify timestamps
        assert "text" in result
        assert "segments" in result
        if result["segments"]:
            assert "start" in result["segments"][0]
            assert "end" in result["segments"][0]


class TestMultiModalIntegration:
    """Test integration of vision + audio + text."""

    @pytest.mark.skipif(not OLLAMA_AVAILABLE, reason="Ollama not available")
    def test_video_analysis_simulation(self, test_image, test_audio, cost_tracker):
        """Test simulated video analysis (frame + audio)."""

        class VideoSignature(MultiModalSignature):
            frame: ImageField = InputField(description="Video frame")
            audio: AudioField = InputField(description="Audio track")
            query: str = InputField(description="Analysis query")
            analysis: str = OutputField(description="Video analysis")

        config = MultiModalConfig(
            llm_provider="ollama", model="llava:13b", enable_cost_tracking=True
        )

        agent = MultiModalAgent(
            config=config, signature=VideoSignature(), cost_tracker=cost_tracker
        )

        result = agent.analyze(
            frame=test_image,
            audio=test_audio,
            query="Describe what's happening in this video",
        )

        # Verify combined analysis
        assert "analysis" in result

        # Verify cost (should be $0 for Ollama + local Whisper)
        assert cost_tracker.get_total_cost() == 0.0

    @pytest.mark.skipif(not OLLAMA_AVAILABLE, reason="Ollama not available")
    def test_cross_modal_workflow(self, test_image, test_audio, memory_pool):
        """Test cross-modal workflow with memory."""
        # Step 1: Vision analysis
        vision_config = VisionAgentConfig(llm_provider="ollama", model="llava:13b")
        vision_agent = VisionAgent(config=vision_config, memory_pool=memory_pool)

        vision_result = vision_agent.analyze(
            image=test_image, prompt="What do you see?", store_in_memory=True
        )

        # Step 2: Audio transcription
        audio_config = TranscriptionAgentConfig(model_size="base")
        audio_agent = TranscriptionAgent(config=audio_config, memory_pool=memory_pool)

        audio_result = audio_agent.transcribe(audio=test_audio, store_in_memory=True)

        # Step 3: Combine insights
        class CombineSignature(MultiModalSignature):
            visual_info: str = InputField(description="Visual information")
            audio_info: str = InputField(description="Audio information")
            summary: str = OutputField(description="Combined summary")

        combine_config = MultiModalConfig(llm_provider="ollama")
        combine_agent = MultiModalAgent(
            config=combine_config, signature=CombineSignature(), memory_pool=memory_pool
        )

        combined_result = combine_agent.analyze(
            visual_info=vision_result["description"],
            audio_info=audio_result["text"],
            store_in_memory=True,
        )

        # Verify workflow
        assert "description" in vision_result
        assert "text" in audio_result
        assert "summary" in combined_result

        # Verify memory contains all steps
        all_memories = memory_pool.retrieve(limit=100)
        assert len(all_memories) >= 3  # At least 3 memories stored


class TestProviderAbstraction:
    """Test provider abstraction and switching."""

    @pytest.mark.skipif(not OLLAMA_AVAILABLE, reason="Ollama not available")
    def test_ollama_provider_selection(self, test_image):
        """Test automatic Ollama provider selection."""
        MultiModalConfig(prefer_local=True)

        adapter = get_multi_modal_adapter(prefer_local=True)
        assert adapter.is_available()
        assert adapter.supports_vision()

    def test_provider_cost_comparison(self, cost_tracker):
        """Test cost comparison between providers."""
        # Compare costs for same workload
        comparison = cost_tracker.compare_providers(
            modality="vision", input_size=1000, providers=["ollama", "openai"]
        )

        assert comparison["ollama"] == 0.0
        assert comparison["openai"] > 0.0
        assert "savings" in comparison

    @pytest.mark.skipif(not OLLAMA_AVAILABLE, reason="Ollama not available")
    def test_adapter_auto_selection_fallback(self):
        """Test adapter selection with fallback."""
        # Try to get adapter with preference for local
        adapter = get_multi_modal_adapter(prefer_local=True)

        # Should get Ollama if available
        if OLLAMA_AVAILABLE:
            from kaizen.providers.multi_modal_adapter import OllamaMultiModalAdapter

            assert isinstance(adapter, OllamaMultiModalAdapter)


class TestCostTrackingIntegration:
    """Test cost tracking in real workflows."""

    @pytest.mark.skipif(not OLLAMA_AVAILABLE, reason="Ollama not available")
    def test_track_ollama_usage(self, test_image):
        """Test tracking Ollama usage (should be $0)."""
        tracker = CostTracker(enable_cost_tracking=True)

        config = MultiModalConfig(
            llm_provider="ollama", model="llava:13b", enable_cost_tracking=True
        )

        class SimpleSignature(MultiModalSignature):
            image: ImageField = InputField(description="Image")
            result: str = OutputField(description="Result")

        agent = MultiModalAgent(
            config=config, signature=SimpleSignature(), cost_tracker=tracker
        )

        agent.run(image=test_image)

        # Verify tracking
        assert tracker.get_total_cost() == 0.0
        stats = tracker.get_usage_stats()
        assert stats["ollama_calls"] > 0

        # Estimate OpenAI equivalent cost
        equivalent = tracker.estimate_openai_equivalent_cost()
        assert equivalent > 0  # Would cost something with OpenAI

    @pytest.mark.skipif(not OLLAMA_AVAILABLE, reason="Ollama not available")
    def test_cost_tracking_batch_operations(self, tmp_path):
        """Test cost tracking for batch operations."""
        tracker = CostTracker(budget_limit=10.0)

        # Create batch of images
        from PIL import Image

        images = []
        for i in range(5):
            img = Image.new("RGB", (200, 200), color="white")
            img_path = tmp_path / f"img_{i}.png"
            img.save(img_path)
            images.append(str(img_path))

        config = MultiModalConfig(llm_provider="ollama", enable_cost_tracking=True)

        class BatchSignature(MultiModalSignature):
            image: ImageField = InputField(description="Image")
            caption: str = OutputField(description="Caption")

        agent = MultiModalAgent(
            config=config, signature=BatchSignature(), cost_tracker=tracker
        )

        results = agent.batch_analyze(images=images)

        # Verify batch tracking
        assert len(results) == 5
        assert tracker.get_total_cost() == 0.0
        stats = tracker.get_usage_stats()
        assert stats["total_calls"] == 5

    def test_budget_limit_enforcement(self):
        """Test budget limit enforcement."""
        tracker = CostTracker(budget_limit=0.05)

        # Record usage approaching limit
        tracker.record_usage("openai", "vision", "gpt-4v", cost=0.03)
        assert not tracker.is_over_budget()
        assert tracker.get_budget_remaining() == 0.02

        # Exceed budget
        tracker.record_usage("openai", "vision", "gpt-4v", cost=0.03)
        assert tracker.is_over_budget()

        # Get alert
        with pytest.raises(Exception, match="Budget exceeded"):
            tracker.check_budget_or_raise()


class TestMemoryIntegration:
    """Test multi-modal memory integration."""

    @pytest.mark.skipif(not OLLAMA_AVAILABLE, reason="Ollama not available")
    def test_store_multimodal_memories(self, test_image, test_audio, memory_pool):
        """Test storing multi-modal data in memory."""

        class MultiSignature(MultiModalSignature):
            image: ImageField = InputField(description="Image")
            audio: AudioField = InputField(description="Audio")
            analysis: str = OutputField(description="Analysis")

        config = MultiModalConfig(llm_provider="ollama")
        agent = MultiModalAgent(
            config=config, signature=MultiSignature(), memory_pool=memory_pool
        )

        agent.run(image=test_image, audio=test_audio, store_in_memory=True)

        # Verify memory storage
        memories = memory_pool.retrieve(agent_id=agent.agent_id, limit=10)
        assert len(memories) > 0

        # Verify multi-modal data in memory
        memory = memories[0]
        assert "image" in memory.content or "audio" in memory.content


class TestPerformance:
    """Test performance characteristics."""

    @pytest.mark.skipif(not OLLAMA_AVAILABLE, reason="Ollama not available")
    def test_vision_processing_performance(self, test_image):
        """Test vision processing meets performance targets."""
        import time

        config = VisionAgentConfig(llm_provider="ollama", model="llava:13b")
        agent = VisionAgent(config=config)

        start = time.time()
        result = agent.run(image=test_image, prompt="Describe this")
        duration = time.time() - start

        # Target: <5s for image analysis
        assert duration < 5.0
        assert "description" in result

    @pytest.mark.skipif(not OLLAMA_AVAILABLE, reason="Ollama not available")
    def test_audio_processing_performance(self, test_audio):
        """Test audio processing meets performance targets."""
        import time

        config = TranscriptionAgentConfig(model_size="base")
        agent = TranscriptionAgent(config=config)

        start = time.time()
        result = agent.transcribe(audio=test_audio)
        duration = time.time() - start

        # Target: <10s for 1 minute of audio
        assert duration < 10.0
        assert "text" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
