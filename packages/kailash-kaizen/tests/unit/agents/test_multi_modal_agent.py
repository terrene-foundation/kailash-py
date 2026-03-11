"""
Unit tests for MultiModalAgent - combines vision, audio, and text processing.

Following TDD methodology: Write tests FIRST, then implement.
"""

from unittest.mock import Mock, patch

import pytest

# Test infrastructure
try:
    from kaizen.agents.multi_modal import MultiModalAgent, MultiModalConfig
    from kaizen.providers.multi_modal_adapter import (
        MultiModalAdapter,
        OllamaMultiModalAdapter,
    )
    from kaizen.signatures import (
        AudioField,
        ImageField,
        InputField,
        OutputField,
        Signature,
    )
    from kaizen.signatures.multi_modal import MultiModalSignature as MultiModalMixin

    IMPORTS_AVAILABLE = True
except ImportError:
    IMPORTS_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not IMPORTS_AVAILABLE, reason="MultiModalAgent not yet implemented"
)


# Test signature for multi-modal inputs
class DocumentUnderstandingSignature(MultiModalMixin, Signature):
    """Test signature combining image and text."""

    image: ImageField = InputField(description="Document image to analyze")
    question: str = InputField(description="Question about the document")
    answer: str = OutputField(description="Answer based on image analysis")
    confidence: float = OutputField(description="Confidence score")


class VideoAnalysisSignature(MultiModalMixin, Signature):
    """Test signature combining image, audio, and text."""

    video_frame: ImageField = InputField(description="Video frame to analyze")
    audio_clip: AudioField = InputField(description="Audio from video")
    query: str = InputField(description="Analysis query")
    analysis: str = OutputField(description="Combined video analysis")


@pytest.fixture
def mock_ollama_adapter():
    """Mock Ollama multi-modal adapter."""
    adapter = Mock(spec=OllamaMultiModalAdapter)
    adapter.is_available.return_value = True
    adapter.supports_vision.return_value = True
    adapter.supports_audio.return_value = True
    adapter.process_multi_modal.return_value = {
        "answer": "Test answer based on image analysis",
        "confidence": 0.92,
    }
    return adapter


@pytest.fixture
def test_image_path(tmp_path):
    """Create a test image file."""
    image_path = tmp_path / "test_document.png"
    # Create a simple test image
    from PIL import Image

    img = Image.new("RGB", (800, 600), color="white")
    img.save(image_path)
    return str(image_path)


@pytest.fixture
def test_audio_path(tmp_path):
    """Create a test audio file."""
    audio_path = tmp_path / "test_audio.wav"
    # Create a simple test audio file
    import struct
    import wave

    with wave.open(str(audio_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        # Write 1 second of silence
        for _ in range(16000):
            wav.writeframes(struct.pack("<h", 0))
    return str(audio_path)


class TestMultiModalConfig:
    """Test MultiModalConfig configuration."""

    def test_config_creation(self):
        """Test basic config creation."""
        config = MultiModalConfig(
            llm_provider="ollama", model="llava:13b", temperature=0.7
        )
        assert config.llm_provider == "ollama"
        assert config.model == "llava:13b"
        assert config.temperature == 0.7

    def test_config_with_cost_tracking(self):
        """Test config with cost tracking enabled."""
        config = MultiModalConfig(
            llm_provider="ollama", enable_cost_tracking=True, warn_on_openai_usage=True
        )
        assert config.enable_cost_tracking is True
        assert config.warn_on_openai_usage is True

    def test_config_provider_selection(self):
        """Test automatic provider selection."""
        # Ollama preferred
        config = MultiModalConfig(prefer_local=True)
        assert config.prefer_local is True

        # OpenAI for validation
        config = MultiModalConfig(llm_provider="openai", prefer_local=False)
        assert config.llm_provider == "openai"


class TestMultiModalAgent:
    """Test MultiModalAgent functionality."""

    def test_agent_creation(self, mock_ollama_adapter):
        """Test basic agent creation."""
        config = MultiModalConfig(llm_provider="ollama", model="llava:13b")
        agent = MultiModalAgent(
            config=config,
            signature=DocumentUnderstandingSignature(),
            adapter=mock_ollama_adapter,
        )
        assert agent is not None
        assert agent.config.llm_provider == "ollama"
        assert isinstance(agent.signature, DocumentUnderstandingSignature)

    def test_agent_extends_base_agent(self, mock_ollama_adapter):
        """Test that MultiModalAgent extends BaseAgent."""
        from kaizen.core.base_agent import BaseAgent

        config = MultiModalConfig(llm_provider="ollama")
        agent = MultiModalAgent(
            config=config,
            signature=DocumentUnderstandingSignature(),
            adapter=mock_ollama_adapter,
        )
        assert isinstance(agent, BaseAgent)

    def test_vision_only_processing(self, mock_ollama_adapter, test_image_path):
        """Test processing with vision only (image + text)."""
        config = MultiModalConfig(llm_provider="ollama", model="llava:13b")
        agent = MultiModalAgent(
            config=config,
            signature=DocumentUnderstandingSignature(),
            adapter=mock_ollama_adapter,
        )

        result = agent.analyze(
            image=test_image_path, question="What is in this document?"
        )

        assert "answer" in result
        assert "confidence" in result
        mock_ollama_adapter.process_multi_modal.assert_called_once()

    def test_audio_only_processing(self, mock_ollama_adapter, test_audio_path):
        """Test processing with audio only."""

        class TranscriptionSignature(MultiModalMixin, Signature):
            audio: AudioField = InputField(description="Audio to transcribe")
            transcript: str = OutputField(description="Transcription")

        mock_ollama_adapter.process_multi_modal.return_value = {
            "transcript": "Test transcription"
        }

        config = MultiModalConfig(llm_provider="ollama")
        agent = MultiModalAgent(
            config=config,
            signature=TranscriptionSignature(),
            adapter=mock_ollama_adapter,
        )

        result = agent.analyze(audio=test_audio_path)
        assert "transcript" in result

    def test_mixed_modal_processing(
        self, mock_ollama_adapter, test_image_path, test_audio_path
    ):
        """Test processing with image + audio + text."""
        mock_ollama_adapter.process_multi_modal.return_value = {
            "analysis": "Combined video analysis result"
        }

        config = MultiModalConfig(llm_provider="ollama")
        agent = MultiModalAgent(
            config=config,
            signature=VideoAnalysisSignature(),
            adapter=mock_ollama_adapter,
        )

        result = agent.analyze(
            video_frame=test_image_path,
            audio_clip=test_audio_path,
            query="What is happening in this video?",
        )

        assert "analysis" in result
        # Verify adapter was called with all modalities
        call_args = mock_ollama_adapter.process_multi_modal.call_args
        assert call_args is not None

    def test_cross_modal_workflow(self, mock_ollama_adapter, test_image_path):
        """Test cross-modal workflow: image → description → summary."""
        # Step 1: Image description
        mock_ollama_adapter.process_multi_modal.return_value = {
            "answer": "This is a business document with charts and graphs"
        }

        config = MultiModalConfig(llm_provider="ollama")
        agent = MultiModalAgent(
            config=config,
            signature=DocumentUnderstandingSignature(),
            adapter=mock_ollama_adapter,
        )

        # Get description
        description_result = agent.analyze(
            image=test_image_path, question="Describe this document"
        )

        # Step 2: Summarize description (text-only)
        class SummarySignature(MultiModalMixin, Signature):
            text: str = InputField(description="Text to summarize")
            summary: str = OutputField(description="Summary")

        mock_ollama_adapter.process_multi_modal.return_value = {
            "summary": "Business document summary"
        }

        summary_agent = MultiModalAgent(
            config=config, signature=SummarySignature(), adapter=mock_ollama_adapter
        )

        summary_result = summary_agent.analyze(text=description_result["answer"])

        assert "summary" in summary_result

    def test_provider_auto_selection(self):
        """Test automatic provider selection based on availability."""
        with patch("kaizen.providers.OLLAMA_AVAILABLE", True):
            config = MultiModalConfig(prefer_local=True)
            agent = MultiModalAgent(
                config=config, signature=DocumentUnderstandingSignature()
            )
            # Should select Ollama adapter automatically
            assert agent.adapter is not None

    def test_cost_tracking_integration(self, mock_ollama_adapter, test_image_path):
        """Test cost tracking during multi-modal processing."""
        config = MultiModalConfig(llm_provider="ollama", enable_cost_tracking=True)
        agent = MultiModalAgent(
            config=config,
            signature=DocumentUnderstandingSignature(),
            adapter=mock_ollama_adapter,
        )

        agent.run(image=test_image_path, question="Test question")

        # Cost tracker should record usage
        assert hasattr(agent, "cost_tracker")
        # Ollama usage should be free
        if agent.cost_tracker:
            usage = agent.cost_tracker.get_usage_stats()
            assert usage["total_cost"] == 0.0  # Ollama is free

    def test_memory_integration(self, mock_ollama_adapter, test_image_path):
        """Test shared memory integration with multi-modal data."""
        from kaizen.memory.shared_memory import SharedMemoryPool

        memory_pool = SharedMemoryPool()
        config = MultiModalConfig(llm_provider="ollama")
        agent = MultiModalAgent(
            config=config,
            signature=DocumentUnderstandingSignature(),
            adapter=mock_ollama_adapter,
            shared_memory=memory_pool,
        )

        agent.analyze(
            image=test_image_path, question="What is this?", store_in_memory=True
        )

        # Should store both input and output in memory
        memories = memory_pool.read_all()
        assert len(memories) > 0

    def test_batch_processing(self, mock_ollama_adapter, test_image_path):
        """Test batch processing of multiple images."""
        config = MultiModalConfig(llm_provider="ollama")
        agent = MultiModalAgent(
            config=config,
            signature=DocumentUnderstandingSignature(),
            adapter=mock_ollama_adapter,
        )

        images = [test_image_path] * 3
        questions = ["Q1", "Q2", "Q3"]

        results = agent.batch_analyze(images=images, questions=questions)

        assert len(results) == 3
        assert all("answer" in r for r in results)


class TestMultiModalWorkflows:
    """Test complete multi-modal workflows."""

    def test_document_understanding_workflow(
        self, mock_ollama_adapter, test_image_path
    ):
        """Test complete document understanding workflow."""
        config = MultiModalConfig(llm_provider="ollama", model="llava:13b")
        agent = MultiModalAgent(
            config=config,
            signature=DocumentUnderstandingSignature(),
            adapter=mock_ollama_adapter,
        )

        # Step 1: OCR/Description
        mock_ollama_adapter.process_multi_modal.return_value = {
            "answer": "Invoice for $1,234.56 dated 2025-01-15",
            "confidence": 0.95,
        }

        result = agent.analyze(
            image=test_image_path, question="Extract key information from this document"
        )

        assert result["answer"].startswith("Invoice")
        assert result["confidence"] > 0.9

    def test_multi_step_analysis(self, mock_ollama_adapter, test_image_path):
        """Test multi-step analysis pipeline."""
        config = MultiModalConfig(llm_provider="ollama")
        agent = MultiModalAgent(
            config=config,
            signature=DocumentUnderstandingSignature(),
            adapter=mock_ollama_adapter,
        )

        # Step 1: Identify document type
        mock_ollama_adapter.process_multi_modal.return_value = {
            "answer": "This is an invoice",
            "confidence": 0.95,
        }
        step1 = agent.analyze(
            image=test_image_path, question="What type of document is this?"
        )

        # Step 2: Extract details based on type
        mock_ollama_adapter.process_multi_modal.return_value = {
            "answer": "Total: $1,234.56, Date: 2025-01-15",
            "confidence": 0.93,
        }
        step2 = agent.analyze(
            image=test_image_path,
            question=f"Extract key details from this {step1['answer']}",
        )

        assert "Total" in step2["answer"]
        assert "Date" in step2["answer"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
