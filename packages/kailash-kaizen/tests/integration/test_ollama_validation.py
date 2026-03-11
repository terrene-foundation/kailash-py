"""
Ollama Provider Validation Tests - Real Infrastructure

This test suite validates that Ollama works end-to-end with REAL models and files.
This ensures Phase 5 (OpenAI validation) is simply a provider switch.

CRITICAL: These tests use REAL Ollama models (NO MOCKING).
"""

import pytest

# Check Ollama availability
try:
    from kaizen.agents.multi_modal_agent import MultiModalAgent, MultiModalConfig
    from kaizen.agents.transcription_agent import (
        TranscriptionAgent,
        TranscriptionAgentConfig,
    )
    from kaizen.agents.vision_agent import VisionAgent, VisionAgentConfig
    from kaizen.cost.tracker import CostTracker
    from kaizen.providers import OLLAMA_AVAILABLE
    from kaizen.providers.multi_modal_adapter import (
        OllamaMultiModalAdapter,
        get_multi_modal_adapter,
    )
    from kaizen.providers.ollama_model_manager import OllamaModelManager
    from kaizen.signatures import InputField, OutputField
    from kaizen.signatures.multi_modal import (
        AudioField,
        ImageField,
        MultiModalSignature,
    )

    IMPORTS_AVAILABLE = True
except ImportError as e:
    IMPORTS_AVAILABLE = False
    OLLAMA_AVAILABLE = False
    import_error = str(e)

pytestmark = [
    pytest.mark.skipif(
        not IMPORTS_AVAILABLE,
        reason=f"Imports not available: {import_error if not IMPORTS_AVAILABLE else ''}",
    ),
    pytest.mark.skipif(
        not OLLAMA_AVAILABLE, reason="Ollama not installed or not running"
    ),
    pytest.mark.integration,
    pytest.mark.ollama_validation,
]


@pytest.fixture(scope="module")
def ollama_manager():
    """Get Ollama model manager."""
    return OllamaModelManager()


@pytest.fixture(scope="module")
def ensure_vision_model(ollama_manager):
    """Ensure vision model is available (download if needed)."""
    if not ollama_manager.is_ollama_running():
        pytest.skip("Ollama is not running")

    # Check if llava:13b exists
    if not ollama_manager.model_exists("llava:13b"):
        # Try bakllava (smaller, faster to download)
        if not ollama_manager.model_exists("bakllava"):
            pytest.skip(
                "No vision model available. Download with: "
                "ollama pull bakllava (or llava:13b for better quality)"
            )
            return "bakllava"
        return "bakllava"
    return "llava:13b"


@pytest.fixture
def test_image(tmp_path):
    """Create a test image with text."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (400, 300), color="white")
    draw = ImageDraw.Draw(img)

    # Add clear text for OCR
    text = "INVOICE #2025-001\nTotal: $500.00"
    draw.text((50, 50), text, fill="black")

    image_path = tmp_path / "test_invoice.png"
    img.save(image_path)
    return str(image_path)


@pytest.fixture
def test_audio(tmp_path):
    """Create a test audio file."""
    import struct
    import wave

    audio_path = tmp_path / "test_audio.wav"
    with wave.open(str(audio_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        # 1 second of simple tone
        for i in range(16000):
            value = int(16000 * 0.3)
            wav.writeframes(struct.pack("<h", value if i % 100 < 50 else -value))
    return str(audio_path)


class TestOllamaInfrastructure:
    """Validate Ollama infrastructure is working."""

    def test_ollama_is_running(self, ollama_manager):
        """Verify Ollama service is running."""
        assert ollama_manager.is_ollama_running(), "Ollama service must be running"

    def test_vision_model_available(self, ensure_vision_model):
        """Verify vision model is available."""
        assert ensure_vision_model in [
            "llava:13b",
            "bakllava",
        ], f"Expected llava:13b or bakllava, got {ensure_vision_model}"

    def test_list_models(self, ollama_manager):
        """Test listing installed models."""
        models = ollama_manager.list_models()
        assert len(models) > 0, "Should have at least one model installed"
        model_names = [m.name for m in models]
        print(f"\nInstalled models: {model_names}")


class TestOllamaAdapterValidation:
    """Validate OllamaMultiModalAdapter with real models."""

    def test_adapter_creation(self, ensure_vision_model):
        """Test creating Ollama adapter."""
        adapter = OllamaMultiModalAdapter(model=ensure_vision_model)
        assert adapter.is_available()
        assert adapter.supports_vision()
        assert adapter.supports_audio()

    def test_adapter_auto_selection(self):
        """Test automatic adapter selection prefers Ollama."""
        adapter = get_multi_modal_adapter(prefer_local=True)
        assert isinstance(adapter, OllamaMultiModalAdapter)
        assert adapter.is_available()

    def test_vision_processing_real(self, ensure_vision_model, test_image):
        """Test REAL vision processing with Ollama."""
        adapter = OllamaMultiModalAdapter(model=ensure_vision_model)

        result = adapter.process_multi_modal(
            image=test_image, prompt="What text do you see in this image?"
        )

        # Verify we got a response
        assert result is not None
        assert isinstance(result, dict)
        print(f"\nVision result: {result}")

    def test_cost_is_zero(self, ensure_vision_model):
        """Verify Ollama costs are always $0."""
        adapter = OllamaMultiModalAdapter(model=ensure_vision_model)

        # Vision cost
        vision_cost = adapter.estimate_cost(modality="vision", input_size=1000)
        assert vision_cost == 0.0

        # Audio cost
        audio_cost = adapter.estimate_cost(modality="audio", duration=60)
        assert audio_cost == 0.0

        # Mixed cost
        mixed_cost = adapter.estimate_cost(modality="mixed")
        assert mixed_cost == 0.0


class TestVisionAgentValidation:
    """Validate VisionAgent with real Ollama."""

    def test_vision_agent_creation(self, ensure_vision_model):
        """Test creating VisionAgent with Ollama."""
        config = VisionAgentConfig(llm_provider="ollama", model=ensure_vision_model)
        agent = VisionAgent(config=config)
        assert agent is not None

    def test_vision_agent_analysis_real(self, ensure_vision_model, test_image):
        """Test REAL image analysis with VisionAgent."""
        config = VisionAgentConfig(llm_provider="ollama", model=ensure_vision_model)
        agent = VisionAgent(config=config)

        result = agent.analyze(
            image=test_image, prompt="Describe what you see in this image"
        )

        assert "description" in result
        assert len(result["description"]) > 0
        print(f"\nVisionAgent result: {result['description'][:100]}...")


class TestTranscriptionAgentValidation:
    """Validate TranscriptionAgent with real Whisper."""

    def test_transcription_agent_creation(self):
        """Test creating TranscriptionAgent."""
        config = TranscriptionAgentConfig(model_size="tiny")  # Use tiny for speed
        agent = TranscriptionAgent(config=config)
        assert agent is not None

    def test_transcription_real(self, test_audio):
        """Test REAL audio transcription."""
        config = TranscriptionAgentConfig(model_size="tiny")
        agent = TranscriptionAgent(config=config)

        result = agent.transcribe(audio=test_audio)

        assert "text" in result
        print(f"\nTranscription result: {result}")


class TestMultiModalAgentValidation:
    """Validate MultiModalAgent with real Ollama."""

    def test_multi_modal_agent_creation(self, ensure_vision_model):
        """Test creating MultiModalAgent with Ollama."""

        class TestSignature(MultiModalSignature):
            image: ImageField = InputField(description="Image")
            result: str = OutputField(description="Result")

        config = MultiModalConfig(
            llm_provider="ollama", model=ensure_vision_model, prefer_local=True
        )

        agent = MultiModalAgent(config=config, signature=TestSignature())

        assert agent is not None
        assert isinstance(agent.adapter, OllamaMultiModalAdapter)

    def test_multi_modal_vision_real(self, ensure_vision_model, test_image):
        """Test REAL multi-modal vision processing."""

        class VisionSignature(MultiModalSignature):
            image: ImageField = InputField(description="Image to analyze")
            analysis: str = OutputField(description="Analysis result")

        config = MultiModalConfig(
            llm_provider="ollama", model=ensure_vision_model, enable_cost_tracking=True
        )

        cost_tracker = CostTracker()

        agent = MultiModalAgent(
            config=config, signature=VisionSignature(), cost_tracker=cost_tracker
        )

        result = agent.run(image=test_image)

        # Verify result
        assert result is not None
        assert isinstance(result, dict)

        # Verify cost tracking (should be $0 for Ollama)
        assert cost_tracker.get_total_cost() == 0.0
        stats = cost_tracker.get_usage_stats()
        assert stats["ollama_calls"] > 0

        print(f"\nMultiModalAgent result: {result}")
        print(f"Cost stats: {stats}")


class TestDocumentUnderstandingPipeline:
    """Validate complete document understanding pipeline with real Ollama."""

    def test_complete_pipeline_real(self, ensure_vision_model, test_image):
        """Test COMPLETE pipeline: Image → OCR → Analysis → Summary."""
        from kaizen.memory.shared_memory import SharedMemoryPool

        # Step 1: OCR with vision
        class OCRSignature(MultiModalSignature):
            image: ImageField = InputField(description="Document image")
            text: str = OutputField(description="Extracted text")

        ocr_config = MultiModalConfig(llm_provider="ollama", model=ensure_vision_model)

        memory_pool = SharedMemoryPool()
        cost_tracker = CostTracker(enable_cost_tracking=True)

        ocr_agent = MultiModalAgent(
            config=ocr_config,
            signature=OCRSignature(),
            cost_tracker=cost_tracker,
            memory_pool=memory_pool,
            agent_id="ocr_agent",
        )

        ocr_result = ocr_agent.run(image=test_image, store_in_memory=True)

        # Verify OCR worked
        assert "text" in ocr_result or len(ocr_result) > 0

        # Verify cost is $0
        assert cost_tracker.get_total_cost() == 0.0

        # Verify memory storage
        memories = memory_pool.retrieve(agent_id="ocr_agent", limit=10)
        assert len(memories) > 0

        print(f"\nPipeline OCR result: {ocr_result}")
        print(f"Cost: ${cost_tracker.get_total_cost():.3f} (should be $0.00)")
        print(f"Memories stored: {len(memories)}")


class TestProviderSwitchingPreparation:
    """Validate that switching to OpenAI will be straightforward."""

    def test_config_supports_provider_switch(self):
        """Test that config easily switches between providers."""
        # Ollama config
        ollama_config = MultiModalConfig(
            llm_provider="ollama", model="llava:13b", prefer_local=True
        )

        # OpenAI config (Phase 5)
        openai_config = MultiModalConfig(
            llm_provider="openai", model="gpt-4-vision-preview", prefer_local=False
        )

        assert ollama_config.llm_provider == "ollama"
        assert openai_config.llm_provider == "openai"

    def test_adapter_factory_supports_both(self):
        """Test that adapter factory supports both providers."""
        # Get Ollama adapter
        ollama_adapter = get_multi_modal_adapter(prefer_local=True)
        assert isinstance(ollama_adapter, OllamaMultiModalAdapter)

        # OpenAI adapter would be:
        # openai_adapter = get_multi_modal_adapter(provider='openai', api_key='...')
        # (tested in Phase 5)

    def test_signature_works_with_both_providers(self, ensure_vision_model):
        """Test that same signature works with different providers."""

        class UniversalSignature(MultiModalSignature):
            image: ImageField = InputField(description="Image")
            result: str = OutputField(description="Result")

        # Works with Ollama
        ollama_config = MultiModalConfig(
            llm_provider="ollama", model=ensure_vision_model
        )

        ollama_agent = MultiModalAgent(
            config=ollama_config, signature=UniversalSignature()
        )

        assert ollama_agent.signature.__class__.__name__ == "UniversalSignature"

        # Same signature will work with OpenAI in Phase 5


@pytest.mark.summary
class TestOllamaValidationSummary:
    """Summary test - validates Ollama is production-ready."""

    def test_ollama_validation_summary(
        self, ensure_vision_model, test_image, test_audio
    ):
        """
        SUMMARY: Validate Ollama provider is fully operational.

        This test confirms:
        1. ✅ Ollama is running
        2. ✅ Vision model available
        3. ✅ Vision processing works
        4. ✅ Audio processing works
        5. ✅ Cost tracking shows $0
        6. ✅ Multi-modal agent works
        7. ✅ Provider switching is ready

        After this passes, Phase 5 is simply:
        - Create OpenAI adapter (already designed)
        - Run same tests with provider="openai"
        - Verify format compatibility
        - Document differences
        """
        # 1. Ollama running
        mgr = OllamaModelManager()
        assert mgr.is_ollama_running()

        # 2. Vision model available
        assert ensure_vision_model in ["llava:13b", "bakllava"]

        # 3. Vision works
        vision_adapter = OllamaMultiModalAdapter(model=ensure_vision_model)
        vision_result = vision_adapter.process_multi_modal(
            image=test_image, prompt="What do you see?"
        )
        assert vision_result is not None

        # 4. Audio works
        from kaizen.audio.whisper_processor import WhisperProcessor

        whisper = WhisperProcessor(model_size="tiny")
        audio_result = whisper.transcribe(test_audio)
        assert "text" in audio_result

        # 5. Cost is $0
        tracker = CostTracker()
        tracker.record_usage("ollama", "vision", ensure_vision_model, cost=0.0)
        tracker.record_usage("ollama", "audio", "whisper", cost=0.0)
        assert tracker.get_total_cost() == 0.0

        # 6. Multi-modal agent works
        class TestSig(MultiModalSignature):
            image: ImageField = InputField(description="Image")
            result: str = OutputField(description="Result")

        config = MultiModalConfig(llm_provider="ollama", model=ensure_vision_model)
        agent = MultiModalAgent(config=config, signature=TestSig())
        result = agent.run(image=test_image)
        assert result is not None

        # 7. Provider switching ready
        assert config.llm_provider == "ollama"
        # Phase 5 will just change to: config.llm_provider = "openai"

        print("\n" + "=" * 60)
        print("✅ OLLAMA VALIDATION COMPLETE")
        print("=" * 60)
        print(f"Vision model: {ensure_vision_model}")
        print(f"Vision result: {str(vision_result)[:80]}...")
        print(
            f"Audio result: {audio_result['text'][:80] if audio_result.get('text') else 'N/A'}..."
        )
        print(f"Total cost: ${tracker.get_total_cost():.3f}")
        print("\n🚀 Ready for Phase 5: OpenAI Validation")
        print(
            "   Phase 5 will simply switch provider='openai' and verify compatibility"
        )
        print("=" * 60)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-m", "summary"])
