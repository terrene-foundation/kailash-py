"""Document chunking nodes for splitting text into manageable pieces."""

import re
from typing import Any, Optional

import numpy as np

from kailash.nodes.base import Node, NodeParameter, register_node


@register_node()
class HierarchicalChunkerNode(Node):
    """Splits documents into hierarchical chunks for better retrieval."""

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "documents": NodeParameter(
                name="documents",
                type=list,
                required=False,
                description="List of documents to chunk",
            ),
            "chunk_size": NodeParameter(
                name="chunk_size",
                type=int,
                required=False,
                default=200,
                description="Target size for text chunks",
            ),
            "overlap": NodeParameter(
                name="overlap",
                type=int,
                required=False,
                default=50,
                description="Overlap between chunks",
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        documents = kwargs.get("documents", [])
        chunk_size = kwargs.get("chunk_size", 200)
        # overlap = kwargs.get("overlap", 50)  # Currently not used in chunking logic

        print(f"Debug Chunker: received {len(documents)} documents")

        all_chunks = []

        for doc in documents:
            content = doc["content"]
            doc_id = doc["id"]
            title = doc["title"]

            # Simple sentence-aware chunking
            sentences = content.split(". ")
            chunks = []
            current_chunk = ""

            for sentence in sentences:
                if len(current_chunk) + len(sentence) < chunk_size:
                    current_chunk += sentence + ". "
                else:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = sentence + ". "

            if current_chunk:
                chunks.append(current_chunk.strip())

            # Create hierarchical chunk structure
            for i, chunk in enumerate(chunks):
                chunk_data = {
                    "chunk_id": f"{doc_id}_chunk_{i}",
                    "document_id": doc_id,
                    "document_title": title,
                    "chunk_index": i,
                    "content": chunk,
                    "hierarchy_level": "paragraph",
                }
                all_chunks.append(chunk_data)

        return {"chunks": all_chunks}


@register_node()
class SemanticChunkerNode(Node):
    """
    Semantic chunking that splits text based on semantic similarity
    to create meaningful, coherent chunks.

    This node uses embeddings to find natural semantic boundaries in text,
    creating chunks that maintain topical coherence. It's superior to
    simple character/token-based splitting for maintaining context.
    """

    def __init__(self, name: str = "semantic_chunker", **kwargs):
        # Set attributes before calling super().__init__() as Kailash validates during init
        self.chunk_size = kwargs.get("chunk_size", 2000)
        self.chunk_overlap = kwargs.get("chunk_overlap", 200)
        self.similarity_threshold = kwargs.get("similarity_threshold", 0.75)
        self.window_size = kwargs.get("window_size", 3)  # Sentences to consider
        self.min_chunk_size = kwargs.get("min_chunk_size", 100)
        self.preserve_sentences = kwargs.get("preserve_sentences", True)

        super().__init__(name=name)

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "text": NodeParameter(
                name="text",
                type=str,
                required=True,
                description="Text to chunk semantically",
            ),
            "embeddings": NodeParameter(
                name="embeddings",
                type=list,
                required=False,
                description="Pre-computed sentence embeddings (optional)",
            ),
            "chunk_size": NodeParameter(
                name="chunk_size",
                type=int,
                required=False,
                default=self.chunk_size,
                description="Target size for each chunk in characters",
            ),
            "chunk_overlap": NodeParameter(
                name="chunk_overlap",
                type=int,
                required=False,
                default=self.chunk_overlap,
                description="Number of characters to overlap between chunks",
            ),
            "similarity_threshold": NodeParameter(
                name="similarity_threshold",
                type=float,
                required=False,
                default=self.similarity_threshold,
                description="Similarity threshold for semantic boundaries (0.0-1.0)",
            ),
            "window_size": NodeParameter(
                name="window_size",
                type=int,
                required=False,
                default=self.window_size,
                description="Number of sentences to consider for similarity",
            ),
            "metadata": NodeParameter(
                name="metadata",
                type=dict,
                required=False,
                default={},
                description="Additional metadata to include with chunks",
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        text = kwargs.get("text", "")
        embeddings = kwargs.get("embeddings")
        chunk_size = kwargs.get("chunk_size", self.chunk_size)
        chunk_overlap = kwargs.get("chunk_overlap", self.chunk_overlap)
        similarity_threshold = kwargs.get(
            "similarity_threshold", self.similarity_threshold
        )
        window_size = kwargs.get("window_size", self.window_size)
        metadata = kwargs.get("metadata", {})

        if not text.strip():
            return {"chunks": []}

        # Split into sentences
        sentences = self._split_into_sentences(text)

        if len(sentences) <= 1:
            return {"chunks": [self._create_single_chunk(text, 0, metadata)]}

        # Find semantic boundaries
        if embeddings and len(embeddings) == len(sentences):
            # Use provided embeddings
            boundaries = self._find_semantic_boundaries(
                sentences, embeddings, similarity_threshold, window_size
            )
        else:
            # Fall back to statistical boundaries based on sentence length variance
            boundaries = self._find_statistical_boundaries(sentences, chunk_size)

        # Create chunks from boundaries
        chunks = self._create_chunks_from_boundaries(
            text, sentences, boundaries, chunk_overlap, chunk_size, metadata
        )

        return {"chunks": chunks}

    def _split_into_sentences(self, text: str) -> list[str]:
        """Split text into sentences using regex."""
        # Improved sentence splitting pattern
        sentence_pattern = r"(?<=[.!?])\s+(?=[A-Z])"
        sentences = re.split(sentence_pattern, text.strip())

        # Further split long sentences
        final_sentences = []
        for sentence in sentences:
            if len(sentence) > 500:  # Long sentence threshold
                # Try to split on semicolons or commas
                sub_sentences = re.split(r"[;,]\s+", sentence)
                final_sentences.extend(sub_sentences)
            else:
                final_sentences.append(sentence)

        return [s.strip() for s in final_sentences if s.strip()]

    def _find_semantic_boundaries(
        self,
        sentences: list[str],
        embeddings: list[list[float]],
        similarity_threshold: float,
        window_size: int,
    ) -> list[int]:
        """Find semantic boundaries using embedding similarity."""
        boundaries = [0]  # Always start with first sentence

        for i in range(1, len(sentences) - 1):
            # Calculate similarity in sliding window
            window_similarities = []

            for j in range(
                max(0, i - window_size), min(len(sentences), i + window_size + 1)
            ):
                if j != i:
                    similarity = self._cosine_similarity(embeddings[i], embeddings[j])
                    window_similarities.append(similarity)

            # Check if this is a good boundary point
            avg_similarity = np.mean(window_similarities) if window_similarities else 0

            if avg_similarity < similarity_threshold:
                boundaries.append(i)

        boundaries.append(len(sentences))  # Always end with last sentence
        return boundaries

    def _find_statistical_boundaries(
        self, sentences: list[str], target_chunk_size: int
    ) -> list[int]:
        """Find boundaries based on statistical properties when embeddings unavailable."""
        boundaries = [0]
        current_size = 0

        for i, sentence in enumerate(sentences):
            current_size += len(sentence)

            # Check if we should create a boundary
            if current_size >= target_chunk_size and i < len(sentences) - 1:
                # Look for natural break points
                if any(
                    sentence.endswith(end) for end in [".", "!", "?", '."', '!"', '?"']
                ):
                    boundaries.append(i + 1)
                    current_size = 0

        boundaries.append(len(sentences))
        return sorted(list(set(boundaries)))  # Remove duplicates and sort

    def _cosine_similarity(self, vec1: list[float], vec2: list[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        vec1_np = np.array(vec1)
        vec2_np = np.array(vec2)

        norm1 = np.linalg.norm(vec1_np)
        norm2 = np.linalg.norm(vec2_np)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return np.dot(vec1_np, vec2_np) / (norm1 * norm2)

    def _create_chunks_from_boundaries(
        self,
        text: str,
        sentences: list[str],
        boundaries: list[int],
        overlap: int,
        max_chunk_size: int,
        metadata: dict,
    ) -> list[dict[str, Any]]:
        """Create chunks from boundary indices."""
        chunks = []

        for i in range(len(boundaries) - 1):
            start_idx = boundaries[i]
            end_idx = boundaries[i + 1]

            # Get sentences for this chunk
            chunk_sentences = sentences[start_idx:end_idx]
            chunk_text = " ".join(chunk_sentences)

            # Add overlap from previous chunk if not first chunk
            if i > 0 and overlap > 0:
                # Get last part of previous chunk
                prev_chunk_text = chunks[-1]["content"]
                overlap_text = (
                    prev_chunk_text[-overlap:]
                    if len(prev_chunk_text) > overlap
                    else prev_chunk_text
                )

                # Find clean break point for overlap
                last_period = overlap_text.rfind(". ")
                if last_period > 0:
                    overlap_text = overlap_text[last_period + 2 :]

                chunk_text = overlap_text + " " + chunk_text

            # Ensure chunk doesn't exceed max size
            if len(chunk_text) > max_chunk_size:
                # Split further if needed
                sub_chunks = self._split_large_chunk(chunk_text, max_chunk_size)
                for j, sub_chunk in enumerate(sub_chunks):
                    chunk_data = self._create_chunk_data(
                        sub_chunk, len(chunks) + j, start_idx, end_idx, metadata
                    )
                    chunks.append(chunk_data)
            else:
                chunk_data = self._create_chunk_data(
                    chunk_text, len(chunks), start_idx, end_idx, metadata
                )
                chunks.append(chunk_data)

        return chunks

    def _split_large_chunk(self, text: str, max_size: int) -> list[str]:
        """Split a large chunk into smaller pieces."""
        chunks = []
        words = text.split()
        current_chunk = []
        current_size = 0

        for word in words:
            word_size = len(word) + 1  # +1 for space

            if current_size + word_size > max_size and current_chunk:
                chunks.append(" ".join(current_chunk))
                current_chunk = [word]
                current_size = word_size
            else:
                current_chunk.append(word)
                current_size += word_size

        if current_chunk:
            chunks.append(" ".join(current_chunk))

        return chunks

    def _create_single_chunk(
        self, text: str, index: int, metadata: dict
    ) -> dict[str, Any]:
        """Create a single chunk when text is too small to split."""
        return {
            "chunk_id": f"chunk_{index}",
            "chunk_index": index,
            "content": text.strip(),
            "start_sentence": 0,
            "end_sentence": 0,
            "chunk_length": len(text),
            "word_count": len(text.split()),
            "chunking_method": "semantic",
            **metadata,
        }

    def _create_chunk_data(
        self,
        chunk_text: str,
        chunk_index: int,
        start_sentence: int,
        end_sentence: int,
        metadata: dict,
    ) -> dict[str, Any]:
        """Create metadata for a chunk."""
        return {
            "chunk_id": f"chunk_{chunk_index}",
            "chunk_index": chunk_index,
            "content": chunk_text.strip(),
            "start_sentence": start_sentence,
            "end_sentence": end_sentence,
            "chunk_length": len(chunk_text),
            "word_count": len(chunk_text.split()),
            "chunking_method": "semantic",
            **metadata,
        }


@register_node()
class StatisticalChunkerNode(Node):
    """
    Statistical chunking that splits text based on sentence embeddings variance
    to identify natural topic boundaries.

    This method analyzes the statistical properties of sentence embeddings
    to find points where the content significantly shifts, making it ideal
    for technical documents and structured content.
    """

    def __init__(self, name: str = "statistical_chunker", **kwargs):
        # Set attributes before calling super().__init__() as Kailash validates during init
        self.chunk_size = kwargs.get("chunk_size", 2000)
        self.variance_threshold = kwargs.get("variance_threshold", 0.5)
        self.min_sentences_per_chunk = kwargs.get("min_sentences_per_chunk", 3)
        self.max_sentences_per_chunk = kwargs.get("max_sentences_per_chunk", 50)
        self.use_sliding_window = kwargs.get("use_sliding_window", True)
        self.window_size = kwargs.get("window_size", 5)

        super().__init__(name=name)

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "text": NodeParameter(
                name="text",
                type=str,
                required=True,
                description="Text to chunk using statistical analysis",
            ),
            "embeddings": NodeParameter(
                name="embeddings",
                type=list,
                required=False,
                description="Pre-computed sentence embeddings (optional)",
            ),
            "chunk_size": NodeParameter(
                name="chunk_size",
                type=int,
                required=False,
                default=self.chunk_size,
                description="Target size for each chunk in characters",
            ),
            "variance_threshold": NodeParameter(
                name="variance_threshold",
                type=float,
                required=False,
                default=self.variance_threshold,
                description="Variance threshold for detecting boundaries",
            ),
            "min_sentences_per_chunk": NodeParameter(
                name="min_sentences_per_chunk",
                type=int,
                required=False,
                default=self.min_sentences_per_chunk,
                description="Minimum sentences per chunk",
            ),
            "max_sentences_per_chunk": NodeParameter(
                name="max_sentences_per_chunk",
                type=int,
                required=False,
                default=self.max_sentences_per_chunk,
                description="Maximum sentences per chunk",
            ),
            "metadata": NodeParameter(
                name="metadata",
                type=dict,
                required=False,
                default={},
                description="Additional metadata to include with chunks",
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        text = kwargs.get("text", "")
        embeddings = kwargs.get("embeddings")
        chunk_size = kwargs.get("chunk_size", self.chunk_size)
        variance_threshold = kwargs.get("variance_threshold", self.variance_threshold)
        min_sentences = kwargs.get(
            "min_sentences_per_chunk", self.min_sentences_per_chunk
        )
        max_sentences = kwargs.get(
            "max_sentences_per_chunk", self.max_sentences_per_chunk
        )
        metadata = kwargs.get("metadata", {})

        if not text.strip():
            return {"chunks": []}

        # Split into sentences
        sentences = self._split_into_sentences(text)

        if len(sentences) <= min_sentences:
            return {"chunks": [self._create_single_chunk(text, 0, metadata)]}

        # Find statistical boundaries
        if embeddings and len(embeddings) == len(sentences):
            # Use provided embeddings
            boundaries = self._find_statistical_boundaries(
                sentences, embeddings, variance_threshold, min_sentences, max_sentences
            )
        else:
            # Fall back to length-based boundaries
            boundaries = self._find_length_based_boundaries(
                sentences, chunk_size, min_sentences, max_sentences
            )

        # Create chunks from boundaries
        chunks = self._create_chunks_from_boundaries(
            text, sentences, boundaries, metadata
        )

        return {"chunks": chunks}

    def _split_into_sentences(self, text: str) -> list[str]:
        """Split text into sentences."""
        # Use same sentence splitting as SemanticChunkerNode
        sentence_pattern = r"(?<=[.!?])\s+(?=[A-Z])"
        sentences = re.split(sentence_pattern, text.strip())
        return [s.strip() for s in sentences if s.strip()]

    def _find_statistical_boundaries(
        self,
        sentences: list[str],
        embeddings: list[list[float]],
        variance_threshold: float,
        min_sentences: int,
        max_sentences: int,
    ) -> list[int]:
        """Find boundaries based on embedding variance analysis."""
        boundaries = [0]

        if self.use_sliding_window:
            # Calculate variance in sliding windows
            variances = []
            for i in range(len(embeddings) - self.window_size + 1):
                window_embeddings = embeddings[i : i + self.window_size]
                variance = self._calculate_embedding_variance(window_embeddings)
                variances.append(variance)

            # Find peaks in variance (indicating topic shifts)
            current_chunk_start = 0
            for i, variance in enumerate(variances):
                sentences_in_chunk = i - current_chunk_start

                # Check if we should create boundary
                if (
                    variance > variance_threshold
                    and sentences_in_chunk >= min_sentences
                ) or sentences_in_chunk >= max_sentences:
                    boundaries.append(i + self.window_size // 2)
                    current_chunk_start = i + self.window_size // 2
        else:
            # Simple variance-based splitting
            current_chunk_start = 0
            for i in range(min_sentences, len(sentences), min_sentences):
                if i - current_chunk_start >= max_sentences:
                    boundaries.append(i)
                    current_chunk_start = i
                elif i < len(sentences) - min_sentences:
                    # Check variance between chunks
                    chunk1_embeddings = embeddings[current_chunk_start:i]
                    chunk2_embeddings = embeddings[
                        i : min(i + min_sentences, len(embeddings))
                    ]

                    inter_variance = self._calculate_inter_chunk_variance(
                        chunk1_embeddings, chunk2_embeddings
                    )

                    if inter_variance > variance_threshold:
                        boundaries.append(i)
                        current_chunk_start = i

        boundaries.append(len(sentences))
        return sorted(list(set(boundaries)))

    def _calculate_embedding_variance(self, embeddings: list[list[float]]) -> float:
        """Calculate variance of embeddings."""
        if not embeddings:
            return 0.0

        embeddings_array = np.array(embeddings)
        mean_embedding = np.mean(embeddings_array, axis=0)

        # Calculate distances from mean
        distances = [np.linalg.norm(emb - mean_embedding) for emb in embeddings_array]

        return np.var(distances)

    def _calculate_inter_chunk_variance(
        self, chunk1_embeddings: list[list[float]], chunk2_embeddings: list[list[float]]
    ) -> float:
        """Calculate variance between two chunks."""
        if not chunk1_embeddings or not chunk2_embeddings:
            return 0.0

        # Calculate centroids
        centroid1 = np.mean(chunk1_embeddings, axis=0)
        centroid2 = np.mean(chunk2_embeddings, axis=0)

        # Return distance between centroids
        return np.linalg.norm(centroid1 - centroid2)

    def _find_length_based_boundaries(
        self,
        sentences: list[str],
        target_chunk_size: int,
        min_sentences: int,
        max_sentences: int,
    ) -> list[int]:
        """Find boundaries based on length when embeddings unavailable."""
        boundaries = [0]
        current_size = 0
        current_sentences = 0

        for i, sentence in enumerate(sentences):
            current_size += len(sentence)
            current_sentences += 1

            # Check if we should create boundary
            if (
                current_size >= target_chunk_size and current_sentences >= min_sentences
            ) or current_sentences >= max_sentences:
                if i < len(sentences) - 1:  # Don't create boundary at last sentence
                    boundaries.append(i + 1)
                    current_size = 0
                    current_sentences = 0

        boundaries.append(len(sentences))
        return sorted(list(set(boundaries)))

    def _create_chunks_from_boundaries(
        self, text: str, sentences: list[str], boundaries: list[int], metadata: dict
    ) -> list[dict[str, Any]]:
        """Create chunks from boundary indices."""
        chunks = []

        for i in range(len(boundaries) - 1):
            start_idx = boundaries[i]
            end_idx = boundaries[i + 1]

            # Get sentences for this chunk
            chunk_sentences = sentences[start_idx:end_idx]
            chunk_text = " ".join(chunk_sentences)

            chunk_data = {
                "chunk_id": f"chunk_{i}",
                "chunk_index": i,
                "content": chunk_text.strip(),
                "start_sentence": start_idx,
                "end_sentence": end_idx,
                "sentence_count": len(chunk_sentences),
                "chunk_length": len(chunk_text),
                "word_count": len(chunk_text.split()),
                "chunking_method": "statistical",
                **metadata,
            }
            chunks.append(chunk_data)

        return chunks

    def _create_single_chunk(
        self, text: str, index: int, metadata: dict
    ) -> dict[str, Any]:
        """Create a single chunk when text is too small to split."""
        return {
            "chunk_id": f"chunk_{index}",
            "chunk_index": index,
            "content": text.strip(),
            "start_sentence": 0,
            "end_sentence": 0,
            "sentence_count": 1,
            "chunk_length": len(text),
            "word_count": len(text.split()),
            "chunking_method": "statistical",
            **metadata,
        }
