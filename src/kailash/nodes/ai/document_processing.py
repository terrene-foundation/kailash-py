"""
Specialized nodes for hierarchical document processing and RAG workflows.

This module implements OpenAI's hierarchical document processing methodology:
1. Split documents into 3 parts iteratively
2. Select relevant parts based on query
3. Generate responses using selected context
4. Validate responses with reasoning models

Design Philosophy:
    These nodes are designed to work together in a template-based workflow
    that can be parameterized for different model choices and processing
    strategies while maintaining the core hierarchical processing logic.
"""

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from kailash.nodes.base import Node, NodeMetadata

# HTTPClient will be imported when implemented
# from kailash.nodes.api.http import HTTPClient


class SplittingStrategy(Enum):
    """Document splitting strategies."""

    SEMANTIC = "semantic"
    LENGTH = "length"
    HYBRID = "hybrid"
    PARAGRAPH = "paragraph"


class CombinationStrategy(Enum):
    """Part combination strategies."""

    FLAT = "flat"
    HIERARCHICAL = "hierarchical"
    WEIGHTED = "weighted"


@dataclass
class DocumentPart:
    """Represents a part of a document with metadata."""

    content: str
    part_id: str
    level: int = 0
    parent_id: Optional[str] = None
    relevance_score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.part_id:
            # Generate ID from content hash
            content_hash = hashlib.md5(self.content.encode()).hexdigest()[:8]
            self.part_id = f"part_{self.level}_{content_hash}"


@dataclass
class ProcessingState:
    """Tracks the state of hierarchical processing."""

    iteration: int = 0
    max_iterations: int = 5
    min_iterations: int = 3
    relevance_threshold: float = 0.7
    all_selected: bool = False
    parts_by_level: Dict[int, List[DocumentPart]] = field(default_factory=dict)
    selected_parts: List[DocumentPart] = field(default_factory=list)
    query: str = ""


class HierarchicalDocumentSplitter(Node):
    """
    Splits documents into 3 parts using configurable strategies.

    This node implements intelligent document splitting that can adapt to
    different document types and content structures. It supports semantic
    splitting using AI models, length-based splitting, and hybrid approaches.

    Design Features:
        1. Multiple splitting strategies (semantic, length, hybrid)
        2. Configurable part count (default 3 for OpenAI method)
        3. Context preservation across splits
        4. Metadata tracking for part relationships
        5. Model-agnostic LLM integration

    Processing Flow:
        - Input: Document content + splitting configuration
        - Analysis: Determine optimal split points based on strategy
        - Splitting: Create parts with preserved context and metadata
        - Output: List of DocumentPart objects with relationships

    Model Integration:
        - Uses large context, cheap models (e.g., gpt-4o-mini)
        - Focuses on understanding document structure
        - Preserves semantic coherence within parts

    Example:
        >>> # Basic usage with semantic splitting
        >>> splitter = HierarchicalDocumentSplitter(
        ...     strategy=SplittingStrategy.SEMANTIC,
        ...     part_count=3,
        ...     model_config={
        ...         "provider": "openai",
        ...         "model": "gpt-4o-mini",
        ...         "temperature": 0.1
        ...     }
        ... )
        >>>
        >>> # Split a technical document
        >>> document = '''
        ... Introduction to Machine Learning
        ... Machine learning is a subset of AI that enables computers to learn.
        ...
        ... Types of Machine Learning
        ... There are three main types: supervised, unsupervised, and reinforcement.
        ...
        ... Applications
        ... ML is used in healthcare, finance, and many other industries.
        ... '''
        >>>
        >>> result = splitter.run(content=document, level=0)
        >>> parts = result["parts"]
        >>>
        >>> # Each part maintains context and metadata
        >>> for part in parts:
        ...     print(f"Part {part.part_id}:")
        ...     print(f"  Content: {part.content[:50]}...")
        ...     print(f"  Level: {part.level}")
        ...     print(f"  Metadata: {part.metadata}")

        >>> # Length-based splitting for consistent sizes
        >>> length_splitter = HierarchicalDocumentSplitter(
        ...     strategy=SplittingStrategy.LENGTH,
        ...     part_count=3,
        ...     overlap_ratio=0.1  # 10% overlap between parts
        ... )
        >>>
        >>> result = length_splitter.run(content=document)
        >>> # Parts will have equal word counts with slight overlap

        >>> # Hybrid splitting for balanced semantic and length
        >>> hybrid_splitter = HierarchicalDocumentSplitter(
        ...     strategy=SplittingStrategy.HYBRID,
        ...     part_count=3
        ... )
        >>>
        >>> # Hierarchical splitting - split parts of parts
        >>> level_0_parts = splitter.run(content=document, level=0)["parts"]
        >>>
        >>> # Split the first part further (level 1)
        >>> level_1_parts = splitter.run(
        ...     content=level_0_parts[0].content,
        ...     level=1,
        ...     parent_id=level_0_parts[0].part_id
        ... )["parts"]
        >>>
        >>> # Each level 1 part tracks its parent
        >>> print(f"Parent: {level_1_parts[0].parent_id}")
    """

    def __init__(
        self,
        strategy: SplittingStrategy = SplittingStrategy.SEMANTIC,
        part_count: int = 3,
        overlap_ratio: float = 0.1,
        model_config: Optional[Dict[str, Any]] = None,
    ):
        super().__init__()
        self.strategy = strategy
        self.part_count = part_count
        self.overlap_ratio = overlap_ratio
        self.model_config = model_config or {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "temperature": 0.1,
        }

    def get_metadata(self) -> NodeMetadata:
        return NodeMetadata(
            display_name="Hierarchical Document Splitter",
            description="Split documents into parts using configurable strategies",
            category="ai/document_processing",
            parameters={
                "strategy": {
                    "type": "string",
                    "description": "Splitting strategy to use",
                    "choices": [s.value for s in SplittingStrategy],
                    "default": self.strategy.value,
                },
                "part_count": {
                    "type": "integer",
                    "description": "Number of parts to split into",
                    "default": self.part_count,
                    "minimum": 2,
                    "maximum": 10,
                },
                "overlap_ratio": {
                    "type": "float",
                    "description": "Overlap ratio between parts",
                    "default": self.overlap_ratio,
                    "minimum": 0.0,
                    "maximum": 0.5,
                },
            },
            inputs={
                "content": {
                    "type": "string",
                    "description": "Document content to split",
                },
                "level": {
                    "type": "integer",
                    "description": "Current hierarchy level",
                    "default": 0,
                },
                "parent_id": {
                    "type": "string",
                    "description": "Parent part ID for hierarchy tracking",
                    "optional": True,
                },
            },
            outputs={
                "parts": {"type": "list", "description": "List of DocumentPart objects"}
            },
        )

    def run(
        self, content: str, level: int = 0, parent_id: Optional[str] = None, **kwargs
    ) -> Dict[str, Any]:
        """Split document content into parts."""

        if self.strategy == SplittingStrategy.SEMANTIC:
            parts = self._semantic_split(content, level, parent_id)
        elif self.strategy == SplittingStrategy.LENGTH:
            parts = self._length_split(content, level, parent_id)
        elif self.strategy == SplittingStrategy.HYBRID:
            parts = self._hybrid_split(content, level, parent_id)
        else:  # PARAGRAPH
            parts = self._paragraph_split(content, level, parent_id)

        return {"parts": parts}

    def _semantic_split(
        self, content: str, level: int, parent_id: Optional[str]
    ) -> List[DocumentPart]:
        """Split content using semantic analysis."""

        # Prepare prompt for LLM
        prompt = f"""
        Split the following document into exactly {self.part_count} coherent, meaningful parts.
        Each part should be self-contained and cover a distinct topic or section.
        Ensure parts maintain semantic coherence and logical flow.

        Document:
        {content}

        Return the result as JSON with this format:
        {{
            "parts": [
                {{"content": "part 1 text...", "summary": "brief summary"}},
                {{"content": "part 2 text...", "summary": "brief summary"}},
                {{"content": "part 3 text...", "summary": "brief summary"}}
            ]
        }}
        """

        # Call LLM (this would integrate with your LLM node)
        response = self._call_llm(prompt)

        try:
            result = json.loads(response)
            parts = []

            for i, part_data in enumerate(result["parts"]):
                part = DocumentPart(
                    content=part_data["content"],
                    part_id="",  # Will be auto-generated
                    level=level,
                    parent_id=parent_id,
                    metadata={
                        "summary": part_data.get("summary", ""),
                        "splitting_strategy": "semantic",
                        "part_index": i,
                    },
                )
                parts.append(part)

            return parts

        except (json.JSONDecodeError, KeyError):
            # Fallback to length-based splitting
            return self._length_split(content, level, parent_id)

    def _length_split(
        self, content: str, level: int, parent_id: Optional[str]
    ) -> List[DocumentPart]:
        """Split content by length with overlap."""

        words = content.split()
        total_words = len(words)
        words_per_part = total_words // self.part_count
        overlap_words = int(words_per_part * self.overlap_ratio)

        parts = []

        for i in range(self.part_count):
            start_idx = max(0, i * words_per_part - overlap_words)
            if i == self.part_count - 1:
                # Last part gets all remaining words
                end_idx = total_words
            else:
                end_idx = min(total_words, (i + 1) * words_per_part + overlap_words)

            part_words = words[start_idx:end_idx]
            part_content = " ".join(part_words)

            part = DocumentPart(
                content=part_content,
                part_id="",
                level=level,
                parent_id=parent_id,
                metadata={
                    "splitting_strategy": "length",
                    "part_index": i,
                    "word_count": len(part_words),
                    "start_word": start_idx,
                    "end_word": end_idx,
                },
            )
            parts.append(part)

        return parts

    def _hybrid_split(
        self, content: str, level: int, parent_id: Optional[str]
    ) -> List[DocumentPart]:
        """Combine semantic and length-based splitting."""

        # First attempt semantic splitting
        semantic_parts = self._semantic_split(content, level, parent_id)

        # Check if parts are reasonably balanced
        lengths = [len(part.content.split()) for part in semantic_parts]
        max_length = max(lengths)
        min_length = min(lengths)

        # If imbalanced, fall back to length splitting
        if max_length / min_length > 3:
            return self._length_split(content, level, parent_id)
        else:
            return semantic_parts

    def _paragraph_split(
        self, content: str, level: int, parent_id: Optional[str]
    ) -> List[DocumentPart]:
        """Split by paragraphs, grouping into specified number of parts."""

        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        if len(paragraphs) <= self.part_count:
            # If fewer paragraphs than desired parts, use length splitting
            return self._length_split(content, level, parent_id)

        paras_per_part = len(paragraphs) // self.part_count
        parts = []

        for i in range(self.part_count):
            start_idx = i * paras_per_part
            if i == self.part_count - 1:
                end_idx = len(paragraphs)
            else:
                end_idx = (i + 1) * paras_per_part

            part_paragraphs = paragraphs[start_idx:end_idx]
            part_content = "\n\n".join(part_paragraphs)

            part = DocumentPart(
                content=part_content,
                part_id="",
                level=level,
                parent_id=parent_id,
                metadata={
                    "splitting_strategy": "paragraph",
                    "part_index": i,
                    "paragraph_count": len(part_paragraphs),
                    "start_paragraph": start_idx,
                    "end_paragraph": end_idx,
                },
            )
            parts.append(part)

        return parts

    def _call_llm(self, prompt: str) -> str:
        """Call configured LLM with prompt."""
        # This would integrate with your LLM integration system
        # For now, return a placeholder
        return '{"parts": [{"content": "Part 1", "summary": "Summary 1"}, {"content": "Part 2", "summary": "Summary 2"}, {"content": "Part 3", "summary": "Summary 3"}]}'


class RelevanceSelector(Node):
    """
    Selects relevant document parts based on query relevance scoring.

    This node evaluates the relevance of document parts to a given query
    and selects those that meet the relevance threshold. It uses configurable
    selection strategies and can adapt to different domain requirements.

    Design Features:
        1. Multiple relevance scoring methods (LLM, embedding, hybrid)
        2. Configurable relevance thresholds
        3. Query-aware selection logic
        4. Batch processing for efficiency
        5. Selection reasoning and explanations

    Selection Strategies:
        - LLM-based: Uses language models to assess relevance
        - Embedding-based: Uses vector similarity for relevance
        - Hybrid: Combines multiple approaches
        - Rule-based: Uses predefined rules and patterns

    Example:
        >>> # Create a relevance selector with LLM-based scoring
        >>> selector = RelevanceSelector(
        ...     relevance_threshold=0.7,
        ...     selection_strategy="llm",
        ...     model_config={
        ...         "provider": "openai",
        ...         "model": "gpt-4o-mini",
        ...         "temperature": 0.1
        ...     }
        ... )
        >>>
        >>> # Create sample document parts
        >>> parts = [
        ...     DocumentPart(
        ...         content="Machine learning algorithms can learn from data.",
        ...         part_id="part_1",
        ...         level=0
        ...     ),
        ...     DocumentPart(
        ...         content="The weather today is sunny and warm.",
        ...         part_id="part_2",
        ...         level=0
        ...     ),
        ...     DocumentPart(
        ...         content="Neural networks are inspired by the brain.",
        ...         part_id="part_3",
        ...         level=0
        ...     )
        ... ]
        >>>
        >>> # Select parts relevant to a query
        >>> query = "How do neural networks work?"
        >>> result = selector.run(parts=parts, query=query)
        >>>
        >>> # Check selection results
        >>> selected = result["selected_parts"]
        >>> print(f"Selected {len(selected)} parts:")
        >>> for part in selected:
        ...     print(f"  - {part.part_id}: relevance={part.relevance_score:.2f}")
        ...     print(f"    Reasoning: {part.metadata.get('relevance_reasoning', '')}")
        >>>
        >>> # All parts selected?
        >>> if result["all_selected"]:
        ...     print("All parts were relevant - no further splitting needed")
        >>>
        >>> # Get relevance scores for all parts
        >>> scores = result["relevance_scores"]
        >>> for part_id, score in scores.items():
        ...     print(f"{part_id}: {score:.2f}")

        >>> # Rule-based selection for faster processing
        >>> rule_selector = RelevanceSelector(
        ...     relevance_threshold=0.5,
        ...     selection_strategy="rule_based"
        ... )
        >>>
        >>> # Uses keyword matching - faster but less accurate
        >>> result = rule_selector.run(parts=parts, query="neural networks")

        >>> # Adjust threshold for precision vs recall
        >>> # Higher threshold = fewer, more relevant parts (precision)
        >>> precise_selector = RelevanceSelector(relevance_threshold=0.9)
        >>>
        >>> # Lower threshold = more parts selected (recall)
        >>> broad_selector = RelevanceSelector(relevance_threshold=0.5)

        >>> # Batch processing multiple queries
        >>> queries = ["machine learning", "neural networks", "data science"]
        >>> for q in queries:
        ...     result = selector.run(parts=parts, query=q)
        ...     print(f"Query '{q}': {len(result['selected_parts'])} parts selected")
    """

    def __init__(
        self,
        relevance_threshold: float = 0.7,
        selection_strategy: str = "llm",
        model_config: Optional[Dict[str, Any]] = None,
    ):
        super().__init__()
        self.relevance_threshold = relevance_threshold
        self.selection_strategy = selection_strategy
        self.model_config = model_config or {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "temperature": 0.1,
        }

    def get_metadata(self) -> NodeMetadata:
        return NodeMetadata(
            display_name="Relevance Selector",
            description="Select relevant document parts based on query",
            category="ai/document_processing",
            parameters={
                "relevance_threshold": {
                    "type": "float",
                    "description": "Minimum relevance score for selection",
                    "default": self.relevance_threshold,
                    "minimum": 0.0,
                    "maximum": 1.0,
                },
                "selection_strategy": {
                    "type": "string",
                    "description": "Strategy for relevance assessment",
                    "choices": ["llm", "embedding", "hybrid", "rule_based"],
                    "default": self.selection_strategy,
                },
            },
            inputs={
                "parts": {
                    "type": "list",
                    "description": "List of DocumentPart objects to evaluate",
                },
                "query": {
                    "type": "string",
                    "description": "Query to assess relevance against",
                },
            },
            outputs={
                "selected_parts": {
                    "type": "list",
                    "description": "List of selected DocumentPart objects",
                },
                "all_selected": {
                    "type": "boolean",
                    "description": "Whether all parts were selected",
                },
                "relevance_scores": {
                    "type": "dict",
                    "description": "Relevance scores for each part",
                },
            },
        )

    def run(self, parts: List[DocumentPart], query: str, **kwargs) -> Dict[str, Any]:
        """Select relevant parts based on query."""

        if self.selection_strategy == "llm":
            return self._llm_selection(parts, query)
        elif self.selection_strategy == "embedding":
            return self._embedding_selection(parts, query)
        elif self.selection_strategy == "hybrid":
            return self._hybrid_selection(parts, query)
        else:  # rule_based
            return self._rule_based_selection(parts, query)

    def _llm_selection(self, parts: List[DocumentPart], query: str) -> Dict[str, Any]:
        """Use LLM to assess relevance and select parts."""

        # Prepare parts for evaluation
        parts_text = ""
        for i, part in enumerate(parts):
            parts_text += f"\nPart {i+1}:\n{part.content}\n"

        prompt = f"""
        Given the query: "{query}"

        Evaluate the relevance of each part to answering this query.
        Rate each part on a scale of 0.0 to 1.0 where:
        - 1.0 = Highly relevant, directly answers the query
        - 0.7+ = Relevant, contains useful information
        - 0.5 = Somewhat relevant, provides context
        - 0.3 = Minimally relevant, tangentially related
        - 0.0 = Not relevant

        Parts to evaluate:
        {parts_text}

        Return JSON with this format:
        {{
            "evaluations": [
                {{"part_index": 0, "relevance_score": 0.8, "reasoning": "explanation"}},
                {{"part_index": 1, "relevance_score": 0.3, "reasoning": "explanation"}},
                {{"part_index": 2, "relevance_score": 0.9, "reasoning": "explanation"}}
            ]
        }}
        """

        response = self._call_llm(prompt)

        try:
            result = json.loads(response)
            selected_parts = []
            relevance_scores = {}

            for eval_data in result["evaluations"]:
                part_idx = eval_data["part_index"]
                score = eval_data["relevance_score"]
                reasoning = eval_data.get("reasoning", "")

                if part_idx < len(parts):
                    part = parts[part_idx]
                    part.relevance_score = score
                    part.metadata["relevance_reasoning"] = reasoning

                    relevance_scores[part.part_id] = score

                    if score >= self.relevance_threshold:
                        selected_parts.append(part)

            all_selected = len(selected_parts) == len(parts)

            return {
                "selected_parts": selected_parts,
                "all_selected": all_selected,
                "relevance_scores": relevance_scores,
            }

        except (json.JSONDecodeError, KeyError):
            # Fallback: select all parts
            return {
                "selected_parts": parts,
                "all_selected": True,
                "relevance_scores": {part.part_id: 1.0 for part in parts},
            }

    def _embedding_selection(
        self, parts: List[DocumentPart], query: str
    ) -> Dict[str, Any]:
        """Use embedding similarity for relevance assessment."""
        # Placeholder for embedding-based selection
        # Would integrate with embedding models
        return self._llm_selection(parts, query)

    def _hybrid_selection(
        self, parts: List[DocumentPart], query: str
    ) -> Dict[str, Any]:
        """Combine LLM and embedding approaches."""
        # Placeholder for hybrid approach
        return self._llm_selection(parts, query)

    def _rule_based_selection(
        self, parts: List[DocumentPart], query: str
    ) -> Dict[str, Any]:
        """Use rule-based relevance assessment."""
        # Simple keyword matching as fallback
        query_words = set(query.lower().split())
        selected_parts = []
        relevance_scores = {}

        for part in parts:
            part_words = set(part.content.lower().split())
            overlap = len(query_words.intersection(part_words))
            score = overlap / len(query_words) if query_words else 0.0

            part.relevance_score = score
            relevance_scores[part.part_id] = score

            if score >= self.relevance_threshold:
                selected_parts.append(part)

        all_selected = len(selected_parts) == len(parts)

        return {
            "selected_parts": selected_parts,
            "all_selected": all_selected,
            "relevance_scores": relevance_scores,
        }

    def _call_llm(self, prompt: str) -> str:
        """Call configured LLM with prompt."""
        # Placeholder for LLM integration
        return '{"evaluations": [{"part_index": 0, "relevance_score": 0.8, "reasoning": "Relevant"}, {"part_index": 1, "relevance_score": 0.9, "reasoning": "Highly relevant"}, {"part_index": 2, "relevance_score": 0.6, "reasoning": "Somewhat relevant"}]}'


class IterationController(Node):
    """
    Controls the iterative hierarchical processing loop.

    This node manages the iteration logic for hierarchical document processing,
    deciding when to continue splitting and when to terminate based on
    selection results and iteration limits.

    Termination Conditions:
        1. All parts in current iteration are selected
        2. Maximum iteration limit reached
        3. Minimum iterations completed and high selection rate
        4. No parts selected (edge case)

    Example:
        >>> # Create iteration controller
        >>> controller = IterationController()
        >>>
        >>> # Initialize processing state
        >>> state = ProcessingState(
        ...     max_iterations=5,
        ...     min_iterations=3,
        ...     relevance_threshold=0.7,
        ...     query="How do transformers work in NLP?"
        ... )
        >>>
        >>> # Simulate first iteration results
        >>> all_parts = [part1, part2, part3]  # 3 document parts
        >>> selected_parts = [part1, part3]    # 2 parts selected
        >>>
        >>> # Check if we should continue
        >>> result = controller.run(
        ...     processing_state=state,
        ...     selected_parts=selected_parts,
        ...     all_parts=all_parts
        ... )
        >>>
        >>> if result["continue_processing"]:
        ...     print(f"Continue splitting {len(result['parts_to_split'])} parts")
        ...     print(f"Current iteration: {result['updated_state'].iteration}")
        ... else:
        ...     print("Processing complete!")

        >>> # Example: All parts selected (termination condition)
        >>> selected_all = [part1, part2, part3]
        >>> result = controller.run(
        ...     processing_state=state,
        ...     selected_parts=selected_all,
        ...     all_parts=all_parts
        ... )
        >>> assert not result["continue_processing"]  # Should stop
        >>> assert result["updated_state"].all_selected

        >>> # Example: Maximum iterations reached
        >>> state.iteration = 4  # One below max
        >>> result = controller.run(
        ...     processing_state=state,
        ...     selected_parts=[part1],
        ...     all_parts=all_parts
        ... )
        >>> # After this iteration, we'll be at max
        >>> assert result["updated_state"].iteration == 5
        >>>
        >>> # Next iteration would exceed max - must stop
        >>> result2 = controller.run(
        ...     processing_state=result["updated_state"],
        ...     selected_parts=[part2],
        ...     all_parts=[part2, part3]
        ... )
        >>> assert not result2["continue_processing"]

        >>> # Example: High selection rate after minimum iterations
        >>> state = ProcessingState(min_iterations=2, iteration=2)
        >>> # 80% selected (4 out of 5 parts)
        >>> result = controller.run(
        ...     processing_state=state,
        ...     selected_parts=[p1, p2, p3, p4],
        ...     all_parts=[p1, p2, p3, p4, p5]
        ... )
        >>> # High selection rate (80%) - can stop
        >>> assert not result["continue_processing"]

        >>> # Track parts across levels
        >>> state = ProcessingState()
        >>> for level in range(3):
        ...     # Each level's parts are tracked
        ...     level_parts = [DocumentPart(f"content_{level}_{i}", f"part_{level}_{i}", level)
        ...                    for i in range(3)]
        ...     result = controller.run(
        ...         processing_state=state,
        ...         selected_parts=level_parts[:2],  # Select first 2
        ...         all_parts=level_parts
        ...     )
        ...     state = result["updated_state"]
        ...     print(f"Level {level}: {len(state.parts_by_level[level])} parts")
    """

    def get_metadata(self) -> NodeMetadata:
        return NodeMetadata(
            display_name="Iteration Controller",
            description="Control hierarchical processing iterations",
            category="ai/document_processing",
            inputs={
                "processing_state": {
                    "type": "object",
                    "description": "Current processing state",
                },
                "selected_parts": {
                    "type": "list",
                    "description": "Parts selected in current iteration",
                },
                "all_parts": {
                    "type": "list",
                    "description": "All parts from current iteration",
                },
            },
            outputs={
                "continue_processing": {
                    "type": "boolean",
                    "description": "Whether to continue iterating",
                },
                "parts_to_split": {
                    "type": "list",
                    "description": "Parts that need further splitting",
                },
                "updated_state": {
                    "type": "object",
                    "description": "Updated processing state",
                },
            },
        )

    def run(
        self,
        processing_state: ProcessingState,
        selected_parts: List[DocumentPart],
        all_parts: List[DocumentPart],
        **kwargs,
    ) -> Dict[str, Any]:
        """Control iteration logic."""

        # Update state
        processing_state.iteration += 1
        processing_state.selected_parts.extend(selected_parts)
        processing_state.parts_by_level[processing_state.iteration - 1] = all_parts

        # Check termination conditions
        all_selected = len(selected_parts) == len(all_parts)
        max_iterations_reached = (
            processing_state.iteration >= processing_state.max_iterations
        )
        min_iterations_done = (
            processing_state.iteration >= processing_state.min_iterations
        )

        # Decide whether to continue
        if all_selected or max_iterations_reached:
            continue_processing = False
            parts_to_split = []
        elif not min_iterations_done:
            # Must continue until minimum iterations
            continue_processing = True
            parts_to_split = [part for part in all_parts if part not in selected_parts]
        else:
            # Check selection rate
            selection_rate = len(selected_parts) / len(all_parts) if all_parts else 0
            if selection_rate >= 0.8:  # High selection rate, can stop
                continue_processing = False
                parts_to_split = []
            else:
                continue_processing = True
                parts_to_split = [
                    part for part in all_parts if part not in selected_parts
                ]

        processing_state.all_selected = all_selected

        return {
            "continue_processing": continue_processing,
            "parts_to_split": parts_to_split,
            "updated_state": processing_state,
        }
