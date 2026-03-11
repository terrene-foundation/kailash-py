"""
Multi-Modal Agent - Unified agent for vision, audio, document, and text processing.

Combines:
- Vision processing (Ollama llava, OpenAI GPT-4V)
- Audio processing (Local Whisper, OpenAI Whisper)
- Document processing (Landing AI, OpenAI Vision, Ollama)
- Text processing (existing LLM providers)

Extends BaseAgent with multi-modal capabilities.
Uses .run() method for standardized execution interface.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

if TYPE_CHECKING:
    from kaizen.agents.multi_modal.document_extraction_agent import (
        DocumentExtractionAgent,
    )

from kailash.nodes.base import NodeMetadata
from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.cost.tracker import CostTracker
from kaizen.memory.shared_memory import SharedMemoryPool
from kaizen.providers.multi_modal_adapter import (
    MultiModalAdapter,
    get_multi_modal_adapter,
)
from kaizen.signatures.multi_modal import AudioField, ImageField, MultiModalSignature


@dataclass
class MultiModalConfig(BaseAgentConfig):
    """Configuration for MultiModalAgent with document extraction support."""

    # Provider settings
    prefer_local: bool = True  # Prefer Ollama over OpenAI
    auto_download_models: bool = True  # Auto-download Ollama models

    # Cost tracking
    enable_cost_tracking: bool = True
    warn_on_openai_usage: bool = True
    budget_limit: Optional[float] = None

    # Multi-modal specific
    vision_model: Optional[str] = None  # e.g., "llava:13b"
    audio_model: Optional[str] = None  # e.g., "base" for Whisper

    # Document extraction settings (NEW - opt-in)
    enable_document_extraction: bool = False
    landing_ai_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    document_chunk_size: int = 512


class MultiModalAgent(BaseAgent):
    """
    Multi-modal agent combining vision, audio, document, and text processing.

    Extends BaseAgent to support:
    - ImageField inputs (auto-processed)
    - AudioField inputs (auto-processed)
    - Document inputs (auto-processed via DocumentExtractionAgent)
    - Mixed modality workflows
    - Cost tracking
    - Provider abstraction (Ollama/OpenAI/Landing AI)

    Example (vision + audio):
        >>> config = MultiModalConfig(prefer_local=True)
        >>> agent = MultiModalAgent(config, signature)
        >>>
        >>> # Use .run() method (standard interface)
        >>> result = agent.run(
        ...     image="photo.jpg",
        ...     question="What is in this image?"
        ... )

    Example (document extraction - opt-in):
        >>> config = MultiModalConfig(
        ...     enable_document_extraction=True,
        ...     landing_ai_api_key=os.getenv('LANDING_AI_API_KEY')
        ... )
        >>> agent = MultiModalAgent(config, signature)
        >>>
        >>> # Automatically detects document input
        >>> result = agent.run(
        ...     document="report.pdf",
        ...     prompt="Summarize this document"
        ... )
        >>> print(result['text'])  # Extracted text
        >>> print(result['llm_answer'])  # LLM-generated summary
    """

    # Node metadata for Studio discovery
    metadata = NodeMetadata(
        name="MultiModalAgent",
        description="Unified multi-modal agent for vision, audio, document, and text processing with cost tracking",
        version="1.1.0",
        tags={
            "ai",
            "kaizen",
            "multi-modal",
            "vision",
            "audio",
            "document",
            "unified",
            "cost-tracking",
        },
    )

    def __init__(
        self,
        config: MultiModalConfig,
        signature: MultiModalSignature,
        adapter: Optional[MultiModalAdapter] = None,
        cost_tracker: Optional[CostTracker] = None,
        shared_memory: Optional[SharedMemoryPool] = None,
        agent_id: Optional[str] = None,
        **kwargs,
    ):
        """
        Initialize multi-modal agent.

        Args:
            config: MultiModalConfig
            signature: MultiModalSignature defining inputs/outputs
            adapter: Optional MultiModalAdapter (auto-selected if None)
            cost_tracker: Optional CostTracker
            shared_memory: Optional SharedMemoryPool
            agent_id: Optional agent ID
        """
        # Initialize base agent
        super().__init__(
            config=config,
            signature=signature,
            shared_memory=shared_memory,
            agent_id=agent_id,
            **kwargs,
        )

        self.config: MultiModalConfig = config

        # Get or create adapter
        if adapter is None:
            try:
                self.adapter = get_multi_modal_adapter(
                    prefer_local=config.prefer_local,
                    model=config.vision_model or "llava:13b",
                    whisper_model=config.audio_model or "base",
                    auto_download=config.auto_download_models,
                )
            except ValueError as e:
                raise ValueError(f"No multi-modal adapter available: {e}")
        else:
            self.adapter = adapter

        # Verify adapter supports required modalities
        self._verify_adapter_compatibility()

        # Cost tracking
        self.cost_tracker = cost_tracker
        if self.cost_tracker is None and config.enable_cost_tracking:
            self.cost_tracker = CostTracker(
                budget_limit=config.budget_limit,
                warn_on_openai_usage=config.warn_on_openai_usage,
            )

        # Lazy initialization for document extraction (NEW)
        self._document_agent: Optional["DocumentExtractionAgent"] = None

    def _verify_adapter_compatibility(self):
        """Verify adapter supports signature's modalities."""
        # Check which modalities are in signature
        has_image = any(
            isinstance(getattr(self.signature, field, None), ImageField)
            for field in dir(self.signature)
        )
        has_audio = any(
            isinstance(getattr(self.signature, field, None), AudioField)
            for field in dir(self.signature)
        )

        # Verify support
        if has_image and not self.adapter.supports_vision():
            raise ValueError("Adapter does not support vision processing")

        if has_audio and not self.adapter.supports_audio():
            raise ValueError("Adapter does not support audio processing")

    @property
    def document_agent(self):
        """
        Lazy initialization of document extraction agent.

        Raises:
            RuntimeError: If document extraction not enabled in config
        """
        if not self.config.enable_document_extraction:
            raise RuntimeError(
                "Document extraction not enabled. "
                "Set enable_document_extraction=True in MultiModalConfig"
            )

        if self._document_agent is None:
            # Import here to avoid circular dependency
            from kaizen.agents.multi_modal.document_extraction_agent import (
                DocumentExtractionAgent,
                DocumentExtractionConfig,
            )

            doc_config = DocumentExtractionConfig(
                llm_provider=self.config.llm_provider,
                model=self.config.model,
                provider="auto",
                landing_ai_key=self.config.landing_ai_api_key,
                openai_key=self.config.openai_api_key,
                chunk_for_rag=False,
                chunk_size=self.config.document_chunk_size,
            )

            self._document_agent = DocumentExtractionAgent(
                config=doc_config,
                shared_memory=self.shared_memory,
                agent_id=f"{self.agent_id}_doc_extraction" if self.agent_id else None,
            )

        return self._document_agent

    def run(self, **kwargs) -> Dict[str, Any]:
        """
        Execute multi-modal analysis with .run() interface.

        This is the standardized entry point for all BaseAgent subclasses.
        Analyzes vision, audio, document, and text inputs.

        Args:
            **kwargs: Multi-modal inputs matching signature (image, audio, document, text, prompt, etc.)

        Returns:
            Dict with analysis results

        Example:
            >>> # Vision analysis
            >>> result = agent.run(image="photo.jpg", question="What is this?")
            >>>
            >>> # Document extraction
            >>> result = agent.run(document="report.pdf", prompt="Summarize")
            >>>
            >>> # Audio transcription
            >>> result = agent.run(audio="meeting.mp3")

        Raises:
            ValueError: If no valid inputs provided
        """
        store_in_memory = kwargs.pop("store_in_memory", False)
        inputs = kwargs
        # Extract modalities from inputs
        image_input = None
        audio_input = None
        document_input = None  # NEW
        text_input = None
        prompt = None

        for key, value in inputs.items():
            if isinstance(value, (ImageField, Path)) or (
                isinstance(value, str)
                and any(
                    value.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp"]
                )
            ):
                image_input = value
            elif isinstance(value, (AudioField, Path)) or (
                isinstance(value, str)
                and any(value.endswith(ext) for ext in [".wav", ".mp3", ".m4a", ".ogg"])
            ):
                audio_input = value
            # NEW: Document detection
            elif isinstance(value, str) and any(
                value.endswith(ext) for ext in [".pdf", ".docx", ".txt", ".md"]
            ):
                document_input = value
            elif isinstance(value, str):
                # Could be text or prompt
                if key in ["prompt", "query", "question"]:
                    prompt = value
                else:
                    text_input = value

        # NEW: If document input detected, use document agent
        if document_input:
            return self._process_with_document(document_input, prompt, store_in_memory)

        # Estimate cost if tracking enabled
        if self.cost_tracker:
            provider = "ollama" if self.config.prefer_local else "openai"
            modality = (
                "mixed"
                if (image_input and audio_input)
                else ("vision" if image_input else "audio" if audio_input else "text")
            )
            estimated_cost = self.cost_tracker.estimate_cost(
                provider=provider, modality=modality
            )
            self.cost_tracker.check_before_call(provider, estimated_cost)

        # Process with adapter
        result = self.adapter.process_multi_modal(
            image=image_input, audio=audio_input, text=text_input, prompt=prompt
        )

        # Record usage
        if self.cost_tracker:
            provider = "ollama" if self.config.prefer_local else "openai"
            self.cost_tracker.record_usage(
                provider=provider,
                modality=modality,
                model=self.config.model,
                cost=estimated_cost if provider == "openai" else 0.0,
            )

        # Store in memory if requested
        if store_in_memory and self.shared_memory:
            self.write_to_memory(
                content={
                    "inputs": {k: str(v) for k, v in inputs.items()},
                    "result": result,
                },
                tags=["multi_modal", modality],
                importance=0.8,
            )

        return result

    def _process_with_document(
        self,
        document_path: str,
        prompt: Optional[str],
        store_in_memory: bool,
    ) -> Dict[str, Any]:
        """
        Process document input with optional prompt-based question answering.

        Args:
            document_path: Path to document file
            prompt: Optional question/instruction about document
            store_in_memory: Store result in memory

        Returns:
            Dict with document extraction results and optional LLM answer

        Note:
            This is an internal method called by analyze() when document input detected.
            Delegates to DocumentExtractionAgent for extraction.
        """
        # Extract document content using document agent
        result = self.document_agent.extract(
            file_path=document_path,
            extract_tables=True,
            chunk_for_rag=False,
        )

        # If prompt provided, use LLM to answer question about document
        if prompt:
            # Truncate text to avoid token limits (use first 2000 chars)
            truncated_text = result["text"][:2000]
            if len(result["text"]) > 2000:
                truncated_text += "...\n[Document truncated for processing]"

            combined_prompt = f"""Document content:
{truncated_text}

Question: {prompt}

Please answer the question based on the document content above."""

            # Use base agent's LLM to answer question
            llm_result = self.run(prompt=combined_prompt)
            result["llm_answer"] = llm_result
            result["question"] = prompt

        # Track cost if cost tracking enabled
        if self.cost_tracker:
            self.cost_tracker.record_usage(
                provider=result["provider"],
                modality="document",
                model=self.config.model,
                cost=result["cost"],
            )

        # Store in memory if requested
        if store_in_memory and self.shared_memory:
            self.write_to_memory(
                content={
                    "document_path": document_path,
                    "provider": result["provider"],
                    "cost": result["cost"],
                    "text_length": len(result["text"]),
                    "has_prompt": prompt is not None,
                },
                tags=["multi_modal", "document"],
                importance=0.8,
            )

        return result

    def analyze(self, **kwargs) -> Dict[str, Any]:
        """
        Convenience method for multi-modal analysis.

        Alias for run() - provided for API clarity.

        Args:
            **kwargs: Same arguments as run() - image, audio, text, prompt, etc.

        Returns:
            Dict containing analysis results

        Example:
            >>> agent = MultiModalAgent()
            >>> result = agent.analyze(image="photo.jpg", prompt="What's in this image?")
            >>> print(result)
        """
        return self.run(**kwargs)

    def batch_analyze(
        self,
        images: Optional[List[Union[str, Path, ImageField]]] = None,
        audios: Optional[List[Union[str, Path, AudioField]]] = None,
        texts: Optional[List[str]] = None,
        questions: Optional[List[str]] = None,
        store_in_memory: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Batch process multiple inputs.

        Args:
            images: List of images
            audios: List of audio files
            texts: List of text inputs
            questions: List of questions/prompts
            store_in_memory: Store results in memory

        Returns:
            List of results
        """
        results = []

        # Determine batch size
        batch_size = max(
            len(images) if images else 0,
            len(audios) if audios else 0,
            len(texts) if texts else 0,
            len(questions) if questions else 0,
        )

        for i in range(batch_size):
            inputs = {}

            if images and i < len(images):
                inputs["image"] = images[i]
            if audios and i < len(audios):
                inputs["audio"] = audios[i]
            if texts and i < len(texts):
                inputs["text"] = texts[i]
            if questions and i < len(questions):
                inputs["question"] = questions[i]

            result = self.analyze(store_in_memory=store_in_memory, **inputs)
            results.append(result)

        return results

    def get_cost_summary(self) -> Dict[str, Any]:
        """Get cost tracking summary."""
        if not self.cost_tracker:
            return {"enabled": False}

        return {
            "enabled": True,
            "stats": self.cost_tracker.get_usage_stats(),
            "by_provider": self.cost_tracker.get_usage_by_provider(),
            "by_modality": self.cost_tracker.get_usage_by_modality(),
            "budget": {
                "limit": self.cost_tracker.budget_limit,
                "used": self.cost_tracker.get_total_cost(),
                "remaining": self.cost_tracker.get_budget_remaining(),
                "percentage": self.cost_tracker.get_budget_percentage(),
            },
            "savings": {
                "actual_cost": self.cost_tracker.get_total_cost(),
                "openai_equivalent": self.cost_tracker.estimate_openai_equivalent_cost(),
                "saved": self.cost_tracker.estimate_openai_equivalent_cost()
                - self.cost_tracker.get_total_cost(),
            },
        }
