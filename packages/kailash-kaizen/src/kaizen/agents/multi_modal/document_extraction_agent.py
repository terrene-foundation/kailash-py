"""
DocumentExtractionAgent - Multi-modal document extraction with provider abstraction.

This agent provides production-ready document extraction with:
- 3 provider backends (Landing AI, OpenAI, Ollama)
- Automatic fallback chain (quality → cost → availability)
- Semantic chunking for RAG applications
- Budget constraint enforcement
- Bounding box coordinates for precise citations

Key Features:
- Extends BaseAgent for automatic error handling, monitoring, audit trails
- Signature-based I/O for type safety and validation
- Universal tool integration (ADR-016 compliant)
- Cost tracking and estimation
- RAG-ready output with page numbers and bounding boxes

Example:
    >>> from kaizen.agents.multi_modal import DocumentExtractionAgent, DocumentExtractionConfig
    >>>
    >>> config = DocumentExtractionConfig(
    ...     llm_provider="openai",
    ...     model="gpt-4",
    ...     provider="auto",  # Automatic selection
    ...     prefer_free=False,
    ...     max_cost_per_doc=1.00
    ... )
    >>>
    >>> # MCP auto-connect provides 12 builtin tools automatically
    >>> agent = DocumentExtractionAgent(config=config)
    >>>
    >>> result = agent.extract("report.pdf", extract_tables=True, chunk_for_rag=True)
    >>> print(f"Extracted {len(result['text'])} chars")
    >>> print(f"Provider: {result['provider']}")
    >>> print(f"Cost: ${result['cost']:.3f}")
    >>> print(f"Chunks: {len(result['chunks'])}")
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from kaizen.core.base_agent import BaseAgent
from kaizen.providers.document import ProviderManager
from kaizen.signatures import InputField, OutputField, Signature

logger = logging.getLogger(__name__)


class DocumentExtractionSignature(Signature):
    """
    Signature for document extraction with multi-provider support.

    Input Fields:
        file_path: Path to document file (required)
        file_type: File type (pdf, docx, txt, md) - auto-detected from extension
        provider: Provider name or "auto" for automatic selection
        extract_tables: Extract tables with structure
        extract_images: Extract and describe images
        chunk_for_rag: Generate semantic chunks for RAG
        chunk_size: Target chunk size in tokens (default: 512)
        prefer_free: Prefer free providers (Ollama) when available
        max_cost: Maximum cost in USD (budget constraint)

    Output Fields:
        text: Extracted full text
        markdown: Markdown representation with structure
        tables: Extracted tables (if extract_tables=True)
        images: Extracted image descriptions (if extract_images=True)
        chunks: Semantic chunks for RAG (if chunk_for_rag=True)
        metadata: Document metadata (pages, type, etc.)
        bounding_boxes: Spatial coordinates (Landing AI only)
        cost: Extraction cost in USD
        provider: Provider name that performed extraction
        processing_time: Time taken in seconds

    Example:
        >>> sig = DocumentExtractionSignature()
        >>> inputs = {
        ...     "file_path": "report.pdf",
        ...     "file_type": "pdf",
        ...     "provider": "auto",
        ...     "extract_tables": True,
        ...     "chunk_for_rag": True
        ... }
        >>> validated = sig.validate_inputs(inputs)
    """

    # Input fields
    file_path: str = InputField(
        description="Path to document file (PDF, DOCX, TXT, MD)",
        required=True,
    )
    file_type: str = InputField(
        description="File type (pdf, docx, txt, md) - auto-detected if not provided",
        default="pdf",
    )
    provider: str = InputField(
        description="Provider name (landing_ai, openai_vision, ollama_vision) or 'auto'",
        default="auto",
    )
    extract_tables: bool = InputField(
        description="Extract tables with structure",
        default=True,
    )
    extract_images: bool = InputField(
        description="Extract and describe images",
        default=False,
    )
    chunk_for_rag: bool = InputField(
        description="Generate semantic chunks for RAG",
        default=False,
    )
    chunk_size: int = InputField(
        description="Target chunk size in tokens",
        default=512,
    )
    prefer_free: bool = InputField(
        description="Prefer free providers (Ollama) when available",
        default=False,
    )
    max_cost: Optional[float] = InputField(
        description="Maximum cost in USD (budget constraint)",
        default=None,
    )

    # Output fields
    text: str = OutputField(
        description="Extracted full text from document",
    )
    markdown: str = OutputField(
        description="Markdown representation with structure",
    )
    tables: List[Dict[str, Any]] = OutputField(
        description="Extracted tables with headers and rows",
    )
    images: List[Dict[str, Any]] = OutputField(
        description="Extracted image descriptions",
    )
    chunks: List[Dict[str, Any]] = OutputField(
        description="Semantic chunks for RAG with page numbers and bounding boxes",
    )
    metadata: Dict[str, Any] = OutputField(
        description="Document metadata (file name, pages, type)",
    )
    bounding_boxes: List[Dict[str, Any]] = OutputField(
        description="Bounding box coordinates for text regions (Landing AI only)",
    )
    cost: float = OutputField(
        description="Extraction cost in USD",
    )
    provider: str = OutputField(
        description="Provider name that performed extraction",
    )
    processing_time: float = OutputField(
        description="Processing time in seconds",
    )


@dataclass
class DocumentExtractionConfig:
    """
    Configuration for DocumentExtractionAgent.

    This config extends BaseAgentConfig patterns with document extraction
    specific parameters. The config supports progressive configuration:
    - Zero-config: Use defaults (auto provider, Landing AI preferred)
    - Basic config: Set provider preference
    - Advanced config: Set budget constraints, chunking options

    Attributes:
        # Provider configuration
        provider: Provider name or "auto" (default: "auto")
        prefer_free: Prefer free providers (Ollama) (default: False)
        max_cost_per_doc: Maximum cost per document in USD (default: None)
        landing_ai_key: Landing AI API key (env: LANDING_AI_API_KEY)
        openai_key: OpenAI API key (env: OPENAI_API_KEY)
        ollama_base_url: Ollama API base URL (default: localhost:11434)

        # Extraction options
        extract_tables: Extract tables by default (default: True)
        extract_images: Extract images by default (default: False)
        chunk_for_rag: Generate RAG chunks by default (default: False)
        chunk_size: Default chunk size in tokens (default: 512)

        # BaseAgentConfig parameters (auto-extracted)
        llm_provider: LLM provider for agent reasoning (optional)
        model: LLM model name (optional)
        temperature: Sampling temperature (optional)
        max_tokens: Max response tokens (optional)

    Example:
        >>> # Zero-config (use defaults)
        >>> config = DocumentExtractionConfig()
        >>>
        >>> # Basic config (prefer free)
        >>> config = DocumentExtractionConfig(
        ...     provider="auto",
        ...     prefer_free=True
        ... )
        >>>
        >>> # Advanced config (budget constraint)
        >>> config = DocumentExtractionConfig(
        ...     provider="auto",
        ...     max_cost_per_doc=0.50,
        ...     chunk_for_rag=True,
        ...     chunk_size=512
        ... )
    """

    # Provider configuration
    provider: str = "auto"
    prefer_free: bool = False
    max_cost_per_doc: Optional[float] = None
    landing_ai_key: Optional[str] = None
    openai_key: Optional[str] = None
    ollama_base_url: Optional[str] = None

    # Extraction options
    extract_tables: bool = True
    extract_images: bool = False
    chunk_for_rag: bool = False
    chunk_size: int = 512

    # BaseAgentConfig parameters (for agent reasoning, optional)
    llm_provider: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    provider_config: Optional[Dict[str, Any]] = None

    # Feature flags (inherited from BaseAgentConfig)
    logging_enabled: bool = True
    performance_enabled: bool = False
    error_handling_enabled: bool = True


class DocumentExtractionAgent(BaseAgent):
    """
    Multi-modal document extraction agent with provider abstraction.

    DocumentExtractionAgent extends BaseAgent to provide production-ready
    document extraction with automatic provider selection, fallback handling,
    and RAG-ready output.

    Key Features:
    - 3 provider backends (Landing AI 98%, OpenAI 95%, Ollama 85%)
    - Automatic fallback chain (quality → cost → availability)
    - Semantic chunking with page numbers and bounding boxes
    - Budget constraint enforcement
    - Universal tool integration (ADR-016)
    - Cost tracking and estimation

    Provider Comparison:
    - Landing AI: 98% accuracy, $0.015/page, bounding boxes, 99% tables
    - OpenAI: 95% accuracy, $0.068/page, fastest (0.8s/page), 90% tables
    - Ollama: 85% accuracy, FREE, local, privacy-preserving, 70% tables

    Architecture:
    - Extends BaseAgent for error handling, monitoring, audit trails
    - Uses ProviderManager for provider coordination
    - Signature-based I/O for type safety
    - Tool registry integration (ADR-016 compliant)

    Example:
        >>> from kaizen.agents.multi_modal import DocumentExtractionAgent, DocumentExtractionConfig
        >>>
        >>> # Create agent with auto provider selection
        >>> config = DocumentExtractionConfig(
        ...     provider="auto",
        ...     max_cost_per_doc=1.00
        ... )
        >>> # MCP auto-connect provides 12 builtin tools automatically
        >>> agent = DocumentExtractionAgent(config=config)
        >>>
        >>> # Extract with default options
        >>> result = agent.extract("report.pdf")
        >>> print(f"Provider: {result['provider']}")
        >>> print(f"Cost: ${result['cost']:.3f}")
        >>>
        >>> # Extract with RAG chunking
        >>> result = agent.extract(
        ...     file_path="report.pdf",
        ...     extract_tables=True,
        ...     chunk_for_rag=True,
        ...     chunk_size=512
        ... )
        >>> # Use chunks for RAG
        >>> for chunk in result['chunks']:
        ...     print(f"Page {chunk['page']}: {chunk['text']}")
        ...     if chunk['bbox']:
        ...         print(f"Location: {chunk['bbox']}")  # Precise citation
    """

    def __init__(
        self,
        config: DocumentExtractionConfig,
        signature: Optional[DocumentExtractionSignature] = None,
        mcp_servers: Optional[List[str]] = None,
        **kwargs,
    ):
        """
        Initialize DocumentExtractionAgent.

        Args:
            config: DocumentExtractionConfig with provider and extraction options
            signature: Optional custom signature (uses DocumentExtractionSignature if None)
            mcp_servers: Optional MCP server list for external tools (ADR-016)
            **kwargs: Additional arguments passed to BaseAgent

        Note:
            12 builtin tools are automatically available via MCP auto-connect
            to kaizen_builtin MCP server (file, HTTP, bash, web operations).

        Example:
            >>> config = DocumentExtractionConfig(provider="auto")
            >>> agent = DocumentExtractionAgent(
            ...     config=config,
            ...     mcp_servers=["filesystem", "web"]
            ... )
        """
        # Store original document extraction config
        self.doc_extraction_config = config

        # Use default signature if not provided
        if signature is None:
            signature = DocumentExtractionSignature()

        # Initialize BaseAgent (will auto-convert config to BaseAgentConfig)
        # MCP auto-connect provides 12 builtin tools automatically
        super().__init__(
            config=config,
            signature=signature,
            mcp_servers=mcp_servers,
            **kwargs,
        )

        # Initialize provider manager
        self.provider_manager = ProviderManager(
            landing_ai_key=config.landing_ai_key,
            openai_key=config.openai_key,
            ollama_base_url=config.ollama_base_url,
        )

        logger.info("DocumentExtractionAgent initialized with ProviderManager")

    def extract(
        self,
        file_path: str,
        file_type: Optional[str] = None,
        provider: Optional[str] = None,
        extract_tables: Optional[bool] = None,
        extract_images: Optional[bool] = None,
        chunk_for_rag: Optional[bool] = None,
        chunk_size: Optional[int] = None,
        prefer_free: Optional[bool] = None,
        max_cost: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Extract content from document.

        Args:
            file_path: Path to document file (required)
            file_type: File type (pdf, docx, txt, md) - auto-detected from extension
            provider: Provider name or "auto" (overrides config)
            extract_tables: Extract tables (overrides config)
            extract_images: Extract images (overrides config)
            chunk_for_rag: Generate RAG chunks (overrides config)
            chunk_size: Chunk size in tokens (overrides config)
            prefer_free: Prefer free providers (overrides config)
            max_cost: Maximum cost in USD (overrides config)

        Returns:
            Dict with extraction results matching DocumentExtractionSignature outputs

        Example:
            >>> # Basic extraction
            >>> result = agent.extract("report.pdf")
            >>>
            >>> # With RAG chunking
            >>> result = agent.extract(
            ...     file_path="report.pdf",
            ...     extract_tables=True,
            ...     chunk_for_rag=True,
            ...     chunk_size=512
            ... )
            >>>
            >>> # Budget-constrained
            >>> result = agent.extract(
            ...     file_path="invoice.pdf",
            ...     prefer_free=True,
            ...     max_cost=0.05
            ... )
        """
        # Apply defaults from config
        file_type = file_type or self._auto_detect_file_type(file_path)
        provider = provider or self.doc_extraction_config.provider
        extract_tables = (
            extract_tables
            if extract_tables is not None
            else self.doc_extraction_config.extract_tables
        )
        extract_images = (
            extract_images
            if extract_images is not None
            else self.doc_extraction_config.extract_images
        )
        chunk_for_rag = (
            chunk_for_rag
            if chunk_for_rag is not None
            else self.doc_extraction_config.chunk_for_rag
        )
        chunk_size = chunk_size or self.doc_extraction_config.chunk_size
        prefer_free = (
            prefer_free
            if prefer_free is not None
            else self.doc_extraction_config.prefer_free
        )
        max_cost = max_cost or self.doc_extraction_config.max_cost_per_doc

        logger.info(
            f"Extracting {file_path} (provider={provider}, "
            f"tables={extract_tables}, rag={chunk_for_rag})"
        )

        # Use run() method from BaseAgent with signature validation
        # This provides automatic error handling, monitoring, audit trails
        inputs = {
            "file_path": file_path,
            "file_type": file_type,
            "provider": provider,
            "extract_tables": extract_tables,
            "extract_images": extract_images,
            "chunk_for_rag": chunk_for_rag,
            "chunk_size": chunk_size,
            "prefer_free": prefer_free,
            "max_cost": max_cost,
        }

        # Execute with BaseAgent infrastructure
        # Note: For document extraction, we bypass LLM and directly use providers
        # This is an optimization - we don't need LLM for extraction
        result = self._extract_direct(inputs)

        return result

    def _extract_direct(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Direct extraction using provider manager (bypasses LLM for efficiency).

        This method directly calls the ProviderManager instead of going through
        the LLM, since document extraction doesn't require reasoning.

        Args:
            inputs: Validated inputs from signature

        Returns:
            ExtractionResult converted to dict matching signature outputs
        """
        # Extract with provider manager (async, but we'll handle sync for now)
        # TODO: Add async support
        import asyncio

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        extraction_result = loop.run_until_complete(
            self.provider_manager.extract(
                file_path=inputs["file_path"],
                file_type=inputs["file_type"],
                provider=inputs["provider"],
                prefer_free=inputs["prefer_free"],
                max_cost=inputs["max_cost"],
                extract_tables=inputs["extract_tables"],
                extract_images=inputs["extract_images"],
                chunk_for_rag=inputs["chunk_for_rag"],
                chunk_size=inputs["chunk_size"],
            )
        )

        # Convert ExtractionResult to dict matching signature
        return extraction_result.to_dict()

    async def extract_async(
        self,
        file_path: str,
        file_type: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Async version of extract() for use in async contexts.

        Args:
            file_path: Path to document file
            file_type: File type (auto-detected if not provided)
            **kwargs: Same as extract()

        Returns:
            ExtractionResult dict

        Example:
            >>> result = await agent.extract_async("report.pdf", chunk_for_rag=True)
        """
        # Apply defaults
        file_type = file_type or self._auto_detect_file_type(file_path)
        provider = kwargs.get("provider", self.doc_extraction_config.provider)
        extract_tables = kwargs.get(
            "extract_tables", self.doc_extraction_config.extract_tables
        )
        extract_images = kwargs.get(
            "extract_images", self.doc_extraction_config.extract_images
        )
        chunk_for_rag = kwargs.get(
            "chunk_for_rag", self.doc_extraction_config.chunk_for_rag
        )
        chunk_size = kwargs.get("chunk_size", self.doc_extraction_config.chunk_size)
        prefer_free = kwargs.get("prefer_free", self.doc_extraction_config.prefer_free)
        max_cost = kwargs.get("max_cost", self.doc_extraction_config.max_cost_per_doc)

        # Extract with provider manager (native async)
        extraction_result = await self.provider_manager.extract(
            file_path=file_path,
            file_type=file_type,
            provider=provider,
            prefer_free=prefer_free,
            max_cost=max_cost,
            extract_tables=extract_tables,
            extract_images=extract_images,
            chunk_for_rag=chunk_for_rag,
            chunk_size=chunk_size,
        )

        return extraction_result.to_dict()

    def estimate_cost(self, file_path: str, provider: str = "auto") -> Dict[str, float]:
        """
        Estimate extraction cost before processing.

        Args:
            file_path: Path to document file
            provider: Provider name or "auto" for all providers

        Returns:
            Dict mapping provider names to estimated costs

        Example:
            >>> costs = agent.estimate_cost("report.pdf")
            >>> print(f"Landing AI: ${costs['landing_ai']:.3f}")
            >>> print(f"OpenAI: ${costs['openai_vision']:.3f}")
            >>> print(f"Ollama: ${costs['ollama_vision']:.3f}")  # $0.00
            >>> print(f"Recommended: {costs['recommended']}")
        """
        import asyncio

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(
            self.provider_manager.estimate_cost(
                file_path=file_path,
                provider=provider,
                prefer_free=self.doc_extraction_config.prefer_free,
            )
        )

    def get_available_providers(self) -> List[str]:
        """
        Get list of available providers (properly configured).

        Returns:
            List of available provider names

        Example:
            >>> available = agent.get_available_providers()
            >>> print(f"Available: {', '.join(available)}")
        """
        return self.provider_manager.get_available_providers()

    def get_provider_capabilities(self) -> Dict[str, Dict[str, Any]]:
        """
        Get capabilities for all providers.

        Returns:
            Dict mapping provider names to capability dicts

        Example:
            >>> caps = agent.get_provider_capabilities()
            >>> for provider, info in caps.items():
            ...     print(f"{provider}:")
            ...     print(f"  Accuracy: {info['accuracy']}")
            ...     print(f"  Cost: ${info['cost_per_page']:.3f}/page")
            ...     print(f"  Tables: {info['table_accuracy']}")
        """
        return self.provider_manager.get_provider_capabilities()

    def _auto_detect_file_type(self, file_path: str) -> str:
        """
        Auto-detect file type from file extension.

        Args:
            file_path: Path to file

        Returns:
            File type (pdf, docx, txt, md)
        """
        from pathlib import Path

        extension = Path(file_path).suffix.lower()
        extension_map = {
            ".pdf": "pdf",
            ".docx": "docx",
            ".txt": "txt",
            ".md": "md",
            ".markdown": "md",
        }

        file_type = extension_map.get(extension, "pdf")
        logger.debug(f"Auto-detected file type: {file_type} from {extension}")

        return file_type
