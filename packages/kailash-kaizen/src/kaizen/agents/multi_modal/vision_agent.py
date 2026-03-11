"""
Vision processing agent for Kaizen.

Provides vision capabilities including image classification, description,
visual question answering, OCR, and multi-image analysis. Optionally supports
document extraction with RAG chunking.

Uses .run() method for standardized execution interface.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from kailash.nodes.base import NodeMetadata
from kaizen.core.base_agent import BaseAgent

if TYPE_CHECKING:
    from kaizen.agents.multi_modal.document_extraction_agent import (
        DocumentExtractionAgent,
    )

from kaizen.providers.ollama_vision_provider import (
    OllamaVisionConfig,
    OllamaVisionProvider,
)
from kaizen.signatures import InputField, OutputField, Signature
from kaizen.signatures.multi_modal import ImageField, MultiModalSignature


class VisionQASignature(MultiModalSignature, Signature):
    """Signature for visual question answering."""

    image: ImageField = InputField(description="Image to analyze")
    question: str = InputField(description="Question about the image")
    answer: str = OutputField(description="Answer based on image analysis")
    confidence: float = OutputField(description="Confidence score (0-1)", default=0.0)


class ImageDescriptionSignature(MultiModalSignature, Signature):
    """Signature for image description generation."""

    image: ImageField = InputField(description="Image to describe")
    description: str = OutputField(description="Detailed image description")


@dataclass
class VisionAgentConfig:
    """Configuration for VisionAgent with optional document extraction."""

    # Vision settings (existing - unchanged)
    llm_provider: str = "ollama"
    model: str = "llava:13b"
    temperature: float = 0.7
    max_images: int = 5
    auto_resize: bool = True

    # Document extraction settings (NEW - opt-in)
    enable_document_extraction: bool = False
    landing_ai_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    ollama_base_url: str = "http://localhost:11434"
    default_chunk_size: int = 512
    default_chunk_overlap: int = 100


class VisionAgent(BaseAgent):
    """
    Vision processing agent with optional document extraction.

    Capabilities:
    - Image classification and description
    - Visual question answering
    - Object detection and counting
    - Text extraction (OCR)
    - Multi-image analysis
    - Document extraction with RAG chunking (opt-in)

    Uses llava:13b or bakllava via Ollama for vision tasks.
    Optionally uses DocumentExtractionAgent for document processing.

    Example (vision analysis):
        config = VisionAgentConfig()
        agent = VisionAgent(config)

        # Use .run() method (standard interface)
        result = agent.run(
            image="photo.jpg",
            question="What objects are in this image?"
        )
        print(result["answer"])

    Example (with document extraction):
        config = VisionAgentConfig(
            enable_document_extraction=True,
            landing_ai_api_key=os.getenv('LANDING_AI_API_KEY')
        )
        agent = VisionAgent(config)

        # Vision analysis (existing)
        vision_result = agent.analyze(image="photo.jpg", question="What is this?")

        # Document extraction (new)
        doc_result = agent.extract_document("invoice.pdf", chunk_for_rag=True)
    """

    # Node metadata for Studio discovery
    metadata = NodeMetadata(
        name="VisionAgent",
        description="Multi-modal vision agent for image analysis, OCR, and visual Q&A",
        version="1.0.0",
        tags={"ai", "kaizen", "vision", "multi-modal", "image", "ocr"},
    )

    def __init__(self, config: VisionAgentConfig, **kwargs):
        """Initialize vision agent."""
        # Convert to BaseAgentConfig
        base_config = type(
            "BaseAgentConfig",
            (),
            {
                "llm_provider": config.llm_provider,
                "model": config.model,
                "temperature": config.temperature,
            },
        )()

        # Initialize with vision signature
        super().__init__(config=base_config, signature=VisionQASignature(), **kwargs)

        # Create vision provider
        self.vision_provider = OllamaVisionProvider(
            config=OllamaVisionConfig(
                model=config.model,
                temperature=config.temperature,
                max_images=config.max_images,
            )
        )

        self.config = config

        # Lazy initialization for document extraction (NEW)
        self._document_agent: Optional["DocumentExtractionAgent"] = None

    def run(self, **kwargs) -> Dict[str, Any]:
        """
        Execute vision analysis with .run() interface.

        This is the standardized entry point for all BaseAgent subclasses.
        Analyzes images and answers questions using vision models.

        Args:
            **kwargs: Vision inputs matching signature (image, question)

        Returns:
            Dict with 'answer', 'confidence', 'model', and 'question' keys

        Example:
            >>> result = agent.run(
            ...     image="photo.jpg",
            ...     question="What objects are in this image?"
            ... )
            >>> print(result["answer"])

        Raises:
            ValueError: If required inputs are missing
        """
        # Extract parameters from kwargs
        image = kwargs.get("image")
        question = kwargs.get("question")
        store_in_memory = kwargs.get("store_in_memory", True)

        # Validate required inputs
        if not image:
            raise ValueError("Image is required (provide image='...' argument)")
        if not question:
            raise ValueError("Question is required (provide question='...' argument)")

        # Use vision provider
        response = self.vision_provider.answer_visual_question(
            image=image, question=question
        )

        result = {
            "answer": response,
            "confidence": 0.85,  # Would need actual confidence from model
            "model": self.config.model,
            "question": question,
        }

        # Store in memory if requested
        if store_in_memory and hasattr(self, "write_to_memory"):
            self.write_to_memory(
                content=result, tags=["vision", "analysis"], importance=0.8
            )

        return result

    def analyze(
        self,
        image: Union[ImageField, str, Path],
        question: str,
        store_in_memory: bool = True,
    ) -> Dict[str, Any]:
        """
        Convenience method for vision analysis.

        Alias for run() - provided for API clarity.

        Args:
            image: Image to analyze
            question: Question about the image
            store_in_memory: Store result in memory

        Returns:
            Dict containing analysis results

        Example:
            >>> agent = VisionAgent(config)
            >>> result = agent.analyze("photo.jpg", "What is in this image?")
            >>> print(result["answer"])
        """
        return self.run(image=image, question=question, store_in_memory=store_in_memory)

    def describe(
        self, image: Union[ImageField, str, Path], detail: str = "auto"
    ) -> str:
        """
        Generate description of image.

        Args:
            image: Image to describe
            detail: Detail level (brief, detailed, auto)

        Returns:
            Image description
        """
        return self.vision_provider.describe_image(image=image, detail=detail)

    def extract_text(self, image: Union[ImageField, str, Path]) -> str:
        """
        Extract text from image (OCR).

        Args:
            image: Image containing text

        Returns:
            Extracted text
        """
        return self.vision_provider.extract_text(image)

    def batch_analyze(
        self, images: List[Union[ImageField, str, Path]], question: str
    ) -> List[Dict[str, Any]]:
        """
        Analyze multiple images with same question.

        Args:
            images: List of images to analyze
            question: Question to ask about each image

        Returns:
            List of analysis results
        """
        results = []

        for image in images:
            result = self.analyze(image, question, store_in_memory=False)
            results.append(result)

        return results

    # ==================== NEW DOCUMENT EXTRACTION METHODS ====================

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
                "Set enable_document_extraction=True in VisionAgentConfig"
            )

        if self._document_agent is None:
            # Import here to avoid circular dependency
            from kaizen.agents.multi_modal.document_extraction_agent import (
                DocumentExtractionAgent,
                DocumentExtractionConfig,
            )

            # Create config from VisionAgent's config (reuse settings)
            doc_config = DocumentExtractionConfig(
                # Reuse LLM settings for agent reasoning (if needed)
                llm_provider=self.config.llm_provider,
                model=self.config.model,
                temperature=self.config.temperature,
                # Provider settings
                provider="auto",  # Let DocumentExtractionAgent choose
                landing_ai_key=self.config.landing_ai_api_key,
                openai_key=self.config.openai_api_key,
                ollama_base_url=self.config.ollama_base_url,
                # RAG defaults from VisionAgentConfig
                chunk_for_rag=False,  # User must explicitly enable
                chunk_size=self.config.default_chunk_size,
            )

            self._document_agent = DocumentExtractionAgent(
                config=doc_config,
                shared_memory=self.shared_memory,
                agent_id=f"{self.agent_id}_doc_extraction" if self.agent_id else None,
                mcp_servers=self.mcp_servers,  # Pass through
            )

        return self._document_agent

    def extract_document(
        self,
        file_path: str,
        extract_tables: bool = True,
        chunk_for_rag: bool = False,
        chunk_size: Optional[int] = None,
        store_in_memory: bool = True,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Extract content from document (PDF, DOCX, TXT, etc.).

        This is a convenience wrapper around DocumentExtractionAgent that
        provides VisionAgent-style API for document extraction.

        Args:
            file_path: Path to document file
            extract_tables: Extract tables with structure
            chunk_for_rag: Generate semantic chunks for RAG
            chunk_size: Chunk size in tokens (uses config default if None)
            store_in_memory: Store result in agent memory
            **kwargs: Additional arguments passed to DocumentExtractionAgent

        Returns:
            Dict with extraction results (text, markdown, chunks, cost, etc.)

        Raises:
            RuntimeError: If document extraction not enabled in config

        Example:
            >>> config = VisionAgentConfig(enable_document_extraction=True)
            >>> agent = VisionAgent(config)
            >>>
            >>> # Basic extraction
            >>> result = agent.extract_document("report.pdf")
            >>> print(f"Text: {result['text'][:100]}...")
            >>>
            >>> # With RAG chunking
            >>> result = agent.extract_document(
            ...     file_path="report.pdf",
            ...     chunk_for_rag=True,
            ...     chunk_size=512
            ... )
            >>> for chunk in result['chunks']:
            ...     print(f"Page {chunk['page']}: {chunk['text'][:50]}...")
        """
        # Use lazy-initialized document agent
        result = self.document_agent.extract(
            file_path=file_path,
            extract_tables=extract_tables,
            chunk_for_rag=chunk_for_rag,
            chunk_size=chunk_size or self.config.default_chunk_size,
            **kwargs,
        )

        # Store in VisionAgent's memory if requested
        if store_in_memory and self.shared_memory:
            self.write_to_memory(
                content={
                    "file_path": file_path,
                    "provider": result["provider"],
                    "cost": result["cost"],
                    "text_length": len(result["text"]),
                    "num_chunks": len(result.get("chunks", [])),
                },
                tags=["document_extraction", result["provider"]],
                importance=0.8,
            )

        return result

    def estimate_document_cost(
        self, file_path: str, provider: str = "auto"
    ) -> Dict[str, float]:
        """
        Estimate document extraction cost before processing.

        Args:
            file_path: Path to document file
            provider: Provider name or "auto" for all providers

        Returns:
            Dict mapping provider names to estimated costs

        Raises:
            RuntimeError: If document extraction not enabled in config

        Example:
            >>> config = VisionAgentConfig(enable_document_extraction=True)
            >>> agent = VisionAgent(config)
            >>> costs = agent.estimate_document_cost("report.pdf")
            >>> print(f"Landing AI: ${costs['landing_ai']:.3f}")
            >>> print(f"Ollama: ${costs['ollama_vision']:.3f}")  # $0.00
        """
        return self.document_agent.estimate_cost(file_path, provider)
