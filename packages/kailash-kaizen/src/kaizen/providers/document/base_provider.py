"""
Base document provider interface for multi-modal document extraction.

This module defines the abstract base class that all document extraction
providers must implement, ensuring consistent interfaces for:
- Document extraction (text, tables, images)
- Cost estimation
- Provider availability checking
- Capability discovery

Provider Implementations:
- LandingAIProvider: Best quality (98%), bounding boxes, tables (99%)
- OpenAIVisionProvider: Fastest (0.8s/page), good quality (95%)
- OllamaVisionProvider: Free, local, acceptable quality (85%)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List


class ProviderCapability(str, Enum):
    """Document extraction capabilities supported by providers."""

    TEXT_EXTRACTION = "text_extraction"
    TABLE_EXTRACTION = "table_extraction"
    IMAGE_DESCRIPTION = "image_description"
    BOUNDING_BOXES = "bounding_boxes"
    MARKDOWN_OUTPUT = "markdown_output"
    SEMANTIC_CHUNKING = "semantic_chunking"


@dataclass
class ExtractionResult:
    """
    Result from document extraction containing text, metadata, and cost info.

    Attributes:
        text: Full extracted text
        markdown: Markdown representation with structure
        tables: Extracted tables (if supported by provider)
        images: Extracted image descriptions (if supported)
        chunks: Semantic chunks for RAG (if chunking enabled)
        metadata: Document metadata (pages, type, etc.)
        bounding_boxes: Spatial coordinates for text regions (if supported)
        cost: Extraction cost in USD
        provider: Provider name that performed extraction
        processing_time: Time taken in seconds
    """

    text: str
    markdown: str = ""
    tables: List[Dict[str, Any]] = field(default_factory=list)
    images: List[Dict[str, Any]] = field(default_factory=list)
    chunks: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    bounding_boxes: List[Dict[str, Any]] = field(default_factory=list)
    cost: float = 0.0
    provider: str = ""
    processing_time: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary for serialization."""
        return {
            "text": self.text,
            "markdown": self.markdown,
            "tables": self.tables,
            "images": self.images,
            "chunks": self.chunks,
            "metadata": self.metadata,
            "bounding_boxes": self.bounding_boxes,
            "cost": self.cost,
            "provider": self.provider,
            "processing_time": self.processing_time,
        }


class BaseDocumentProvider(ABC):
    """
    Abstract base class for document extraction providers.

    All document providers (Landing AI, OpenAI, Ollama) must implement this
    interface to ensure consistent behavior and enable automatic fallback.

    Key Methods:
        extract(): Extract document content (text, tables, images)
        estimate_cost(): Estimate extraction cost before processing
        is_available(): Check if provider is available and configured
        get_capabilities(): Get provider-specific capabilities

    Example:
        >>> class MyProvider(BaseDocumentProvider):
        ...     def extract(self, file_path, file_type, **options):
        ...         # Implementation
        ...         pass
        ...
        ...     def estimate_cost(self, file_path):
        ...         # Cost calculation
        ...         return 0.015  # $0.015 per page
    """

    def __init__(self, provider_name: str, **kwargs):
        """
        Initialize document provider.

        Args:
            provider_name: Unique provider identifier
            **kwargs: Provider-specific configuration
        """
        self.provider_name = provider_name
        self.config = kwargs

    @abstractmethod
    async def extract(
        self,
        file_path: str,
        file_type: str,
        extract_tables: bool = True,
        extract_images: bool = False,
        chunk_for_rag: bool = False,
        chunk_size: int = 512,
        **options,
    ) -> ExtractionResult:
        """
        Extract content from document.

        Args:
            file_path: Path to document file
            file_type: File type (pdf, docx, txt, md)
            extract_tables: Extract tables with structure
            extract_images: Extract and describe images
            chunk_for_rag: Generate semantic chunks for RAG
            chunk_size: Target chunk size in tokens
            **options: Provider-specific options

        Returns:
            ExtractionResult with text, tables, chunks, cost, etc.

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file type not supported
            RuntimeError: If extraction fails

        Example:
            >>> provider = LandingAIProvider(api_key="...")
            >>> result = await provider.extract(
            ...     file_path="report.pdf",
            ...     file_type="pdf",
            ...     extract_tables=True,
            ...     chunk_for_rag=True
            ... )
            >>> print(f"Extracted {len(result.text)} chars")
            >>> print(f"Cost: ${result.cost:.3f}")
        """
        pass

    @abstractmethod
    async def estimate_cost(self, file_path: str) -> float:
        """
        Estimate extraction cost before processing.

        Args:
            file_path: Path to document file

        Returns:
            Estimated cost in USD

        Raises:
            FileNotFoundError: If file doesn't exist

        Example:
            >>> provider = LandingAIProvider(api_key="...")
            >>> cost = await provider.estimate_cost("report.pdf")
            >>> print(f"Estimated cost: ${cost:.3f}")
            >>> if cost < 1.00:
            ...     result = await provider.extract("report.pdf", "pdf")
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if provider is available and properly configured.

        Returns:
            True if provider can be used, False otherwise

        Example:
            >>> provider = LandingAIProvider(api_key="...")
            >>> if provider.is_available():
            ...     result = await provider.extract("report.pdf", "pdf")
            ... else:
            ...     print("Provider not configured")
        """
        pass

    @abstractmethod
    def get_capabilities(self) -> Dict[str, Any]:
        """
        Get provider capabilities and metadata.

        Returns:
            Dict with capabilities, pricing, performance metrics

        Example:
            >>> provider = LandingAIProvider(api_key="...")
            >>> caps = provider.get_capabilities()
            >>> print(f"Accuracy: {caps['accuracy']}")
            >>> print(f"Cost per page: ${caps['cost_per_page']:.3f}")
            >>> print(f"Supports tables: {caps['supports_tables']}")
        """
        pass

    def _get_page_count(self, file_path: str) -> int:
        """
        Get page count from document for cost estimation.

        Args:
            file_path: Path to document file

        Returns:
            Number of pages in document

        Note:
            This is a helper method for subclasses to use in cost estimation.
            Default implementation returns 1 for non-PDF files.
        """
        file_path_obj = Path(file_path)

        if not file_path_obj.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # For PDF files, try to get page count
        if file_path_obj.suffix.lower() == ".pdf":
            try:
                import PyPDF2

                with open(file_path, "rb") as f:
                    pdf_reader = PyPDF2.PdfReader(f)
                    return len(pdf_reader.pages)
            except Exception:
                # Fallback: estimate based on file size
                # Rough heuristic: 1 page ~ 50KB
                file_size_kb = file_path_obj.stat().st_size / 1024
                return max(1, int(file_size_kb / 50))

        # For other formats, assume 1 page
        return 1

    def _validate_file_type(self, file_type: str) -> None:
        """
        Validate that file type is supported.

        Args:
            file_type: File type to validate (pdf, docx, txt, md)

        Raises:
            ValueError: If file type not supported
        """
        supported_types = ["pdf", "docx", "txt", "md"]
        if file_type.lower() not in supported_types:
            raise ValueError(
                f"Unsupported file type: {file_type}. "
                f"Supported types: {', '.join(supported_types)}"
            )
