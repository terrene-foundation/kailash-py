"""
Hybrid search enhancement for A2A agent matching.

This module provides advanced search capabilities that combine:
- Semantic similarity using embeddings
- Keyword matching using TF-IDF and fuzzy matching
- Context-aware scoring based on task history
- Performance-weighted ranking
"""

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

from kailash.nodes.base import Node, NodeParameter, register_node

from .a2a import A2AAgentCard
from .semantic_memory import SimpleEmbeddingProvider


@dataclass
class SearchContext:
    """Context information for search operations."""

    task_history: List[Dict[str, Any]] = field(default_factory=list)
    agent_performance: Dict[str, Dict[str, float]] = field(default_factory=dict)
    recent_interactions: Dict[str, datetime] = field(default_factory=dict)
    domain_expertise: Dict[str, List[str]] = field(default_factory=dict)
    collaboration_patterns: Dict[str, List[str]] = field(default_factory=dict)


@dataclass
class SearchResult:
    """Enhanced search result with detailed scoring."""

    agent_id: str
    agent_card: Optional[A2AAgentCard]
    semantic_score: float
    keyword_score: float
    context_score: float
    performance_score: float
    combined_score: float
    explanation: Dict[str, Any]
    confidence: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "agent_id": self.agent_id,
            "agent_card": self.agent_card.to_dict() if self.agent_card else None,
            "semantic_score": self.semantic_score,
            "keyword_score": self.keyword_score,
            "context_score": self.context_score,
            "performance_score": self.performance_score,
            "combined_score": self.combined_score,
            "explanation": self.explanation,
            "confidence": self.confidence,
        }


class TFIDFVectorizer:
    """Simple TF-IDF vectorizer for keyword matching."""

    def __init__(self, stop_words: Optional[Set[str]] = None):
        self.stop_words = stop_words or {
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "by",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
        }
        self.vocabulary = {}
        self.idf_scores = {}
        self.document_count = 0

    def _tokenize(self, text: str) -> List[str]:
        """Tokenize text into words."""
        text = text.lower()
        tokens = re.findall(r"\b\w+\b", text)
        return [
            token for token in tokens if token not in self.stop_words and len(token) > 2
        ]

    def fit(self, documents: List[str]):
        """Fit the vectorizer on documents."""
        self.document_count = len(documents)
        document_frequencies = defaultdict(int)

        # Count document frequencies
        for doc in documents:
            tokens = set(self._tokenize(doc))
            for token in tokens:
                document_frequencies[token] += 1

        # Build vocabulary and calculate IDF scores
        for token, df in document_frequencies.items():
            self.vocabulary[token] = len(self.vocabulary)
            self.idf_scores[token] = math.log(self.document_count / df)

    def transform(self, documents: List[str]) -> np.ndarray:
        """Transform documents to TF-IDF vectors."""
        vectors = []

        for doc in documents:
            tokens = self._tokenize(doc)
            token_counts = Counter(tokens)

            vector = np.zeros(len(self.vocabulary))
            for token, count in token_counts.items():
                if token in self.vocabulary:
                    tf = count / len(tokens) if tokens else 0
                    idf = self.idf_scores[token]
                    vector[self.vocabulary[token]] = tf * idf

            vectors.append(vector)

        return np.array(vectors)

    def cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Calculate cosine similarity between two vectors."""
        if np.linalg.norm(vec1) == 0 or np.linalg.norm(vec2) == 0:
            return 0.0
        return np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))


class FuzzyMatcher:
    """Fuzzy string matching for capability matching."""

    def __init__(self):
        self.synonyms = {
            "code": ["coding", "programming", "development", "software"],
            "test": ["testing", "qa", "quality", "validation"],
            "research": ["analysis", "investigation", "study", "exploration"],
            "data": ["information", "dataset", "statistics", "analytics"],
            "debug": ["troubleshoot", "fix", "resolve", "diagnose"],
            "design": ["architecture", "planning", "structure", "blueprint"],
            "review": ["evaluation", "assessment", "inspection", "audit"],
            "optimize": ["improve", "enhance", "performance", "efficiency"],
        }

    def expand_terms(self, terms: List[str]) -> Set[str]:
        """Expand terms with synonyms."""
        expanded = set(terms)
        for term in terms:
            term_lower = term.lower()
            for base_term, synonyms in self.synonyms.items():
                if term_lower in synonyms or term_lower == base_term:
                    expanded.update(synonyms)
                    expanded.add(base_term)
        return expanded

    def calculate_fuzzy_score(self, text1: str, text2: str) -> float:
        """Calculate fuzzy matching score between two texts."""
        tokens1 = set(text1.lower().split())
        tokens2 = set(text2.lower().split())

        # Expand with synonyms
        expanded1 = self.expand_terms(list(tokens1))
        expanded2 = self.expand_terms(list(tokens2))

        # Calculate intersection over union
        intersection = len(expanded1.intersection(expanded2))
        union = len(expanded1.union(expanded2))

        return intersection / union if union > 0 else 0.0


class ContextualScorer:
    """Contextual scoring based on task history and agent performance."""

    def __init__(self):
        self.task_success_weight = 0.4
        self.recency_weight = 0.3
        self.collaboration_weight = 0.2
        self.domain_expertise_weight = 0.1

    def calculate_context_score(
        self, agent_id: str, task_requirements: List[str], context: SearchContext
    ) -> Tuple[float, Dict[str, Any]]:
        """Calculate contextual score for an agent."""
        explanation = {}
        total_score = 0.0

        # Task success history
        task_success_score = self._calculate_task_success_score(agent_id, context)
        total_score += task_success_score * self.task_success_weight
        explanation["task_success"] = {
            "score": task_success_score,
            "weight": self.task_success_weight,
        }

        # Recency of interactions
        recency_score = self._calculate_recency_score(agent_id, context)
        total_score += recency_score * self.recency_weight
        explanation["recency"] = {"score": recency_score, "weight": self.recency_weight}

        # Collaboration patterns
        collaboration_score = self._calculate_collaboration_score(agent_id, context)
        total_score += collaboration_score * self.collaboration_weight
        explanation["collaboration"] = {
            "score": collaboration_score,
            "weight": self.collaboration_weight,
        }

        # Domain expertise
        domain_score = self._calculate_domain_expertise_score(
            agent_id, task_requirements, context
        )
        total_score += domain_score * self.domain_expertise_weight
        explanation["domain_expertise"] = {
            "score": domain_score,
            "weight": self.domain_expertise_weight,
        }

        return total_score, explanation

    def _calculate_task_success_score(
        self, agent_id: str, context: SearchContext
    ) -> float:
        """Calculate task success score based on history."""
        performance = context.agent_performance.get(agent_id, {})
        success_rate = performance.get("success_rate", 0.5)  # Default to neutral
        quality_score = performance.get("average_quality", 0.5)

        # Combine success rate and quality
        return success_rate * 0.7 + quality_score * 0.3

    def _calculate_recency_score(self, agent_id: str, context: SearchContext) -> float:
        """Calculate recency score based on recent interactions."""
        last_interaction = context.recent_interactions.get(agent_id)
        if not last_interaction:
            return 0.5  # Neutral for no interaction history

        days_since = (datetime.now() - last_interaction).days
        if days_since == 0:
            return 1.0
        elif days_since <= 7:
            return 0.8
        elif days_since <= 30:
            return 0.6
        else:
            return 0.4

    def _calculate_collaboration_score(
        self, agent_id: str, context: SearchContext
    ) -> float:
        """Calculate collaboration score based on patterns."""
        patterns = context.collaboration_patterns.get(agent_id, [])
        if not patterns:
            return 0.5

        # Score based on successful collaboration patterns
        positive_patterns = sum(1 for p in patterns if "successful" in p.lower())
        return min(1.0, positive_patterns / len(patterns) + 0.3)

    def _calculate_domain_expertise_score(
        self, agent_id: str, requirements: List[str], context: SearchContext
    ) -> float:
        """Calculate domain expertise score."""
        expertise = context.domain_expertise.get(agent_id, [])
        if not expertise or not requirements:
            return 0.5

        # Calculate overlap between requirements and expertise
        req_set = set(req.lower() for req in requirements)
        exp_set = set(exp.lower() for exp in expertise)

        overlap = len(req_set.intersection(exp_set))
        return min(1.0, overlap / len(req_set) + 0.2)


@register_node()
class HybridSearchNode(Node):
    """Enhanced hybrid search for A2A agent matching."""

    def __init__(self, name: str = "hybrid_search", **kwargs):
        """Initialize hybrid search node."""
        self.requirements = None
        self.agents = None
        self.context = None
        self.limit = 10
        self.semantic_weight = 0.3
        self.keyword_weight = 0.3
        self.context_weight = 0.2
        self.performance_weight = 0.2
        self.min_threshold = 0.3
        self.enable_fuzzy_matching = True
        self.enable_tfidf = True
        self.embedding_model = "nomic-embed-text"
        self.embedding_host = "http://localhost:11434"

        # Set attributes from kwargs
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)

        super().__init__(name=name, **kwargs)

        # Initialize components
        self.embedding_provider = SimpleEmbeddingProvider(
            model_name=self.embedding_model, host=self.embedding_host
        )
        self.tfidf_vectorizer = TFIDFVectorizer()
        self.fuzzy_matcher = FuzzyMatcher()
        self.contextual_scorer = ContextualScorer()

        # Fitted state
        self._tfidf_fitted = False

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Get node parameters."""
        return {
            "requirements": NodeParameter(
                name="requirements",
                type=list,
                required=True,
                description="Task requirements",
            ),
            "agents": NodeParameter(
                name="agents",
                type=list,
                required=True,
                description="List of agents to search",
            ),
            "context": NodeParameter(
                name="context",
                type=dict,
                required=False,
                description="Search context with history and performance",
            ),
            "limit": NodeParameter(
                name="limit",
                type=int,
                required=False,
                default=10,
                description="Maximum results to return",
            ),
            "semantic_weight": NodeParameter(
                name="semantic_weight",
                type=float,
                required=False,
                default=0.3,
                description="Weight for semantic similarity",
            ),
            "keyword_weight": NodeParameter(
                name="keyword_weight",
                type=float,
                required=False,
                default=0.3,
                description="Weight for keyword matching",
            ),
            "context_weight": NodeParameter(
                name="context_weight",
                type=float,
                required=False,
                default=0.2,
                description="Weight for contextual scoring",
            ),
            "performance_weight": NodeParameter(
                name="performance_weight",
                type=float,
                required=False,
                default=0.2,
                description="Weight for performance scoring",
            ),
            "min_threshold": NodeParameter(
                name="min_threshold",
                type=float,
                required=False,
                default=0.3,
                description="Minimum combined score threshold",
            ),
            "enable_fuzzy_matching": NodeParameter(
                name="enable_fuzzy_matching",
                type=bool,
                required=False,
                default=True,
                description="Enable fuzzy matching",
            ),
            "enable_tfidf": NodeParameter(
                name="enable_tfidf",
                type=bool,
                required=False,
                default=True,
                description="Enable TF-IDF vectorization",
            ),
            "embedding_model": NodeParameter(
                name="embedding_model",
                type=str,
                required=False,
                default="nomic-embed-text",
                description="Embedding model name",
            ),
            "embedding_host": NodeParameter(
                name="embedding_host",
                type=str,
                required=False,
                default="http://localhost:11434",
                description="Embedding service host",
            ),
        }

    async def run(self, **kwargs) -> Dict[str, Any]:
        """Perform hybrid search with enhanced scoring."""
        # Get parameters
        requirements = kwargs.get("requirements", self.requirements)
        agents = kwargs.get("agents", self.agents)
        context_data = kwargs.get("context", self.context) or {}
        limit = kwargs.get("limit", self.limit)

        if not requirements or not agents:
            raise ValueError("Requirements and agents are required")

        # Parse context
        context = self._parse_context(context_data)

        # Prepare requirements text
        req_text = " ".join(str(req) for req in requirements)

        # Prepare agent texts
        agent_texts = []
        agent_cards = []

        for agent in agents:
            if isinstance(agent, dict):
                # Convert dict to agent card if needed
                if "agent_id" in agent and "agent_name" in agent:
                    try:
                        agent_card = A2AAgentCard.from_dict(agent)
                        agent_cards.append(agent_card)
                        # Create searchable text from agent card
                        agent_text = self._create_agent_text(agent_card)
                    except Exception:
                        # Fallback if conversion fails
                        agent_cards.append(None)
                        agent_text = str(agent)
                else:
                    agent_cards.append(None)
                    agent_text = str(agent)
            else:
                agent_cards.append(None)
                agent_text = str(agent)

            agent_texts.append(agent_text)

        # Perform different types of search
        semantic_scores = await self._calculate_semantic_scores(req_text, agent_texts)
        keyword_scores = await self._calculate_keyword_scores(req_text, agent_texts)
        context_scores = await self._calculate_context_scores(
            requirements, agent_cards, context
        )
        performance_scores = await self._calculate_performance_scores(
            agent_cards, context
        )

        # Combine scores and create results
        results = []
        for i, agent in enumerate(agents):
            agent_id = self._get_agent_id(agent, i)

            # Calculate combined score
            combined_score = (
                semantic_scores[i] * self.semantic_weight
                + keyword_scores[i] * self.keyword_weight
                + context_scores[i] * self.context_weight
                + performance_scores[i] * self.performance_weight
            )

            # Apply minimum threshold
            if combined_score >= self.min_threshold:
                confidence = self._calculate_confidence(
                    semantic_scores[i],
                    keyword_scores[i],
                    context_scores[i],
                    performance_scores[i],
                )

                explanation = {
                    "semantic": {
                        "score": semantic_scores[i],
                        "weight": self.semantic_weight,
                    },
                    "keyword": {
                        "score": keyword_scores[i],
                        "weight": self.keyword_weight,
                    },
                    "context": {
                        "score": context_scores[i],
                        "weight": self.context_weight,
                    },
                    "performance": {
                        "score": performance_scores[i],
                        "weight": self.performance_weight,
                    },
                    "threshold_met": combined_score >= self.min_threshold,
                }

                result = SearchResult(
                    agent_id=agent_id,
                    agent_card=agent_cards[i],
                    semantic_score=semantic_scores[i],
                    keyword_score=keyword_scores[i],
                    context_score=context_scores[i],
                    performance_score=performance_scores[i],
                    combined_score=combined_score,
                    explanation=explanation,
                    confidence=confidence,
                )

                results.append(result)

        # Sort by combined score
        results.sort(key=lambda x: x.combined_score, reverse=True)

        # Limit results
        results = results[:limit]

        return {
            "success": True,
            "requirements": requirements,
            "results": [r.to_dict() for r in results],
            "count": len(results),
            "search_type": "hybrid_enhanced",
            "weights": {
                "semantic": self.semantic_weight,
                "keyword": self.keyword_weight,
                "context": self.context_weight,
                "performance": self.performance_weight,
            },
            "threshold": self.min_threshold,
        }

    def _parse_context(self, context_data: Dict[str, Any]) -> SearchContext:
        """Parse context data into SearchContext object."""
        return SearchContext(
            task_history=context_data.get("task_history", []),
            agent_performance=context_data.get("agent_performance", {}),
            recent_interactions={
                k: datetime.fromisoformat(v) if isinstance(v, str) else v
                for k, v in context_data.get("recent_interactions", {}).items()
            },
            domain_expertise=context_data.get("domain_expertise", {}),
            collaboration_patterns=context_data.get("collaboration_patterns", {}),
        )

    def _create_agent_text(self, agent_card: A2AAgentCard) -> str:
        """Create searchable text from agent card."""
        text_parts = [
            agent_card.agent_name,
            agent_card.description,
            " ".join(agent_card.tags),
            " ".join(cap.name for cap in agent_card.primary_capabilities),
            " ".join(cap.description for cap in agent_card.primary_capabilities),
            " ".join(cap.domain for cap in agent_card.primary_capabilities),
        ]
        return " ".join(filter(None, text_parts))

    def _get_agent_id(self, agent: Any, index: int) -> str:
        """Get agent ID from agent data."""
        if isinstance(agent, dict):
            return agent.get("agent_id", f"agent_{index}")
        elif hasattr(agent, "agent_id"):
            return agent.agent_id
        else:
            return f"agent_{index}"

    async def _calculate_semantic_scores(
        self, req_text: str, agent_texts: List[str]
    ) -> List[float]:
        """Calculate semantic similarity scores."""
        try:
            # Generate embeddings
            all_texts = [req_text] + agent_texts
            result = await self.embedding_provider.embed_text(all_texts)

            req_embedding = result.embeddings[0]
            agent_embeddings = result.embeddings[1:]

            # Calculate similarities
            scores = []
            for agent_embedding in agent_embeddings:
                similarity = np.dot(req_embedding, agent_embedding) / (
                    np.linalg.norm(req_embedding) * np.linalg.norm(agent_embedding)
                )
                scores.append(max(0.0, similarity))

            return scores

        except Exception:
            # Fallback to simple text similarity
            return [0.5] * len(agent_texts)

    async def _calculate_keyword_scores(
        self, req_text: str, agent_texts: List[str]
    ) -> List[float]:
        """Calculate keyword-based similarity scores."""
        scores = []

        # TF-IDF scoring
        if self.enable_tfidf and len(agent_texts) > 1:
            try:
                if not self._tfidf_fitted:
                    self.tfidf_vectorizer.fit([req_text] + agent_texts)
                    self._tfidf_fitted = True

                vectors = self.tfidf_vectorizer.transform([req_text] + agent_texts)
                req_vector = vectors[0]
                agent_vectors = vectors[1:]

                for agent_vector in agent_vectors:
                    similarity = self.tfidf_vectorizer.cosine_similarity(
                        req_vector, agent_vector
                    )
                    scores.append(max(0.0, similarity))
            except Exception:
                scores = [0.5] * len(agent_texts)
        else:
            # Fallback to simple keyword matching
            req_words = set(req_text.lower().split())
            for agent_text in agent_texts:
                agent_words = set(agent_text.lower().split())
                overlap = len(req_words.intersection(agent_words))
                union = len(req_words.union(agent_words))
                score = overlap / union if union > 0 else 0.0
                scores.append(score)

        # Add fuzzy matching boost
        if self.enable_fuzzy_matching:
            for i, agent_text in enumerate(agent_texts):
                fuzzy_score = self.fuzzy_matcher.calculate_fuzzy_score(
                    req_text, agent_text
                )
                scores[i] = max(scores[i], fuzzy_score * 0.8)  # Boost but not dominate

        return scores

    async def _calculate_context_scores(
        self,
        requirements: List[str],
        agent_cards: List[Optional[A2AAgentCard]],
        context: SearchContext,
    ) -> List[float]:
        """Calculate contextual scores."""
        scores = []

        for agent_card in agent_cards:
            if agent_card:
                agent_id = agent_card.agent_id
                score, _ = self.contextual_scorer.calculate_context_score(
                    agent_id, requirements, context
                )
                scores.append(score)
            else:
                scores.append(0.5)  # Neutral for unknown agents

        return scores

    async def _calculate_performance_scores(
        self, agent_cards: List[Optional[A2AAgentCard]], context: SearchContext
    ) -> List[float]:
        """Calculate performance-based scores."""
        scores = []

        for agent_card in agent_cards:
            if agent_card:
                # Use agent card performance metrics
                performance = agent_card.performance
                success_rate = performance.success_rate
                quality_score = performance.insight_quality_score

                # Combine different performance metrics
                perf_score = (
                    success_rate * 0.4
                    + quality_score * 0.4
                    + min(1.0, performance.total_tasks / 100) * 0.2  # Experience factor
                )
                scores.append(perf_score)
            else:
                scores.append(0.5)  # Neutral for unknown agents

        return scores

    def _calculate_confidence(
        self, semantic: float, keyword: float, context: float, performance: float
    ) -> float:
        """Calculate confidence score based on agreement between different scorers."""
        scores = [semantic, keyword, context, performance]

        # Calculate standard deviation (lower = more agreement = higher confidence)
        mean_score = sum(scores) / len(scores)
        variance = sum((s - mean_score) ** 2 for s in scores) / len(scores)
        std_dev = math.sqrt(variance)

        # Convert to confidence (0-1 scale)
        # Scale standard deviation to 0-1 range more appropriately
        confidence = max(0.0, 1.0 - (std_dev / 0.5))  # Assume max std_dev of 0.5

        # Boost confidence for high scores
        if mean_score > 0.7:
            confidence = min(1.0, confidence + 0.1)

        return confidence


@register_node()
class AdaptiveSearchNode(Node):
    """Adaptive search that learns from feedback and improves over time."""

    def __init__(self, name: str = "adaptive_search", **kwargs):
        """Initialize adaptive search node."""
        self.requirements = None
        self.agents = None
        self.feedback_history = None
        self.adaptation_rate = 0.1
        self.memory_window = 100  # Number of recent searches to remember

        # Adaptive weights (will be learned)
        self.semantic_weight = 0.3
        self.keyword_weight = 0.3
        self.context_weight = 0.2
        self.performance_weight = 0.2

        # Set attributes from kwargs
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)

        super().__init__(name=name, **kwargs)

        # Learning history
        self.search_history = []
        self.weight_history = []

        # Initialize hybrid search
        self.hybrid_search = HybridSearchNode(
            name="internal_hybrid_search",
            semantic_weight=self.semantic_weight,
            keyword_weight=self.keyword_weight,
            context_weight=self.context_weight,
            performance_weight=self.performance_weight,
        )

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Get node parameters."""
        return {
            "requirements": NodeParameter(
                name="requirements",
                type=list,
                required=True,
                description="Task requirements",
            ),
            "agents": NodeParameter(
                name="agents",
                type=list,
                required=True,
                description="List of agents to search",
            ),
            "feedback_history": NodeParameter(
                name="feedback_history",
                type=list,
                required=False,
                description="History of search feedback for learning",
            ),
            "adaptation_rate": NodeParameter(
                name="adaptation_rate",
                type=float,
                required=False,
                default=0.1,
                description="Rate of weight adaptation",
            ),
            "memory_window": NodeParameter(
                name="memory_window",
                type=int,
                required=False,
                default=100,
                description="Number of searches to remember",
            ),
        }

    async def run(self, **kwargs) -> Dict[str, Any]:
        """Perform adaptive search with learning."""
        # Get parameters
        requirements = kwargs.get("requirements", self.requirements)
        agents = kwargs.get("agents", self.agents)
        feedback_history = kwargs.get("feedback_history", self.feedback_history) or []

        if not requirements or not agents:
            raise ValueError("Requirements and agents are required")

        # Learn from feedback
        if feedback_history:
            self._learn_from_feedback(feedback_history)

        # Update hybrid search weights
        self.hybrid_search.semantic_weight = self.semantic_weight
        self.hybrid_search.keyword_weight = self.keyword_weight
        self.hybrid_search.context_weight = self.context_weight
        self.hybrid_search.performance_weight = self.performance_weight

        # Perform search
        # Filter kwargs to avoid duplicate parameters
        filtered_kwargs = {
            k: v
            for k, v in kwargs.items()
            if k
            not in [
                "requirements",
                "agents",
                "feedback_history",
                "adaptation_rate",
                "memory_window",
            ]
        }

        result = await self.hybrid_search.run(
            requirements=requirements, agents=agents, **filtered_kwargs
        )

        # Add adaptive information
        result.update(
            {
                "adaptive_weights": {
                    "semantic": self.semantic_weight,
                    "keyword": self.keyword_weight,
                    "context": self.context_weight,
                    "performance": self.performance_weight,
                },
                "learning_enabled": True,
                "search_history_size": len(self.search_history),
            }
        )

        # Store search in history
        self._store_search_history(requirements, agents, result)

        return result

    def _learn_from_feedback(self, feedback_history: List[Dict[str, Any]]):
        """Learn and adapt weights from feedback."""
        if not feedback_history:
            return

        # Process recent feedback
        recent_feedback = feedback_history[-self.memory_window :]

        # Calculate performance by component
        semantic_performance = []
        keyword_performance = []
        context_performance = []
        performance_performance = []

        for feedback in recent_feedback:
            if "component_scores" in feedback:
                scores = feedback["component_scores"]
                success = feedback.get("success", 0.5)

                semantic_performance.append(scores.get("semantic", 0.5) * success)
                keyword_performance.append(scores.get("keyword", 0.5) * success)
                context_performance.append(scores.get("context", 0.5) * success)
                performance_performance.append(scores.get("performance", 0.5) * success)

        if not semantic_performance:
            return

        # Calculate average performance per component
        avg_semantic = sum(semantic_performance) / len(semantic_performance)
        avg_keyword = sum(keyword_performance) / len(keyword_performance)
        avg_context = sum(context_performance) / len(context_performance)
        avg_performance = sum(performance_performance) / len(performance_performance)

        # Adjust weights based on performance
        total_performance = avg_semantic + avg_keyword + avg_context + avg_performance

        if total_performance > 0:
            # Normalize to proportional weights
            target_semantic = avg_semantic / total_performance
            target_keyword = avg_keyword / total_performance
            target_context = avg_context / total_performance
            target_performance = avg_performance / total_performance

            # Gradually adjust weights
            self.semantic_weight += (
                target_semantic - self.semantic_weight
            ) * self.adaptation_rate
            self.keyword_weight += (
                target_keyword - self.keyword_weight
            ) * self.adaptation_rate
            self.context_weight += (
                target_context - self.context_weight
            ) * self.adaptation_rate
            self.performance_weight += (
                target_performance - self.performance_weight
            ) * self.adaptation_rate

            # Ensure weights sum to 1
            total_weight = (
                self.semantic_weight
                + self.keyword_weight
                + self.context_weight
                + self.performance_weight
            )
            if total_weight > 0:
                self.semantic_weight /= total_weight
                self.keyword_weight /= total_weight
                self.context_weight /= total_weight
                self.performance_weight /= total_weight

    def _store_search_history(
        self, requirements: List[str], agents: List[Any], result: Dict[str, Any]
    ):
        """Store search in history for learning."""
        search_record = {
            "timestamp": datetime.now().isoformat(),
            "requirements": requirements,
            "agent_count": len(agents),
            "result_count": result.get("count", 0),
            "weights": {
                "semantic": self.semantic_weight,
                "keyword": self.keyword_weight,
                "context": self.context_weight,
                "performance": self.performance_weight,
            },
        }

        self.search_history.append(search_record)

        # Keep only recent history
        if len(self.search_history) > self.memory_window:
            self.search_history = self.search_history[-self.memory_window :]

        # Store weight history
        self.weight_history.append(
            {
                "timestamp": datetime.now().isoformat(),
                "weights": search_record["weights"].copy(),
            }
        )

        if len(self.weight_history) > self.memory_window:
            self.weight_history = self.weight_history[-self.memory_window :]
