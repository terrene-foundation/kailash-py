"""
RAG Strategy Router and Analysis Nodes

Intelligent routing and analysis components for RAG strategies.
Includes LLM-powered strategy selection and performance monitoring.
"""

import logging
import time
from typing import Any, Dict, List, Optional

from ..ai.llm_agent import LLMAgentNode
from ..base import Node, NodeParameter, register_node

logger = logging.getLogger(__name__)


@register_node()
class RAGStrategyRouterNode(Node):
    """
    RAG Strategy Router Node

    LLM-powered intelligent routing that analyzes documents and queries
    to automatically select the optimal RAG strategy for each use case.
    """

    def __init__(
        self,
        name: str = "rag_strategy_router",
        llm_model: str = "gpt-4",
        provider: str = "openai",
    ):
        self.llm_model = llm_model
        self.provider = provider
        self.llm_agent = None
        super().__init__(name)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "documents": NodeParameter(
                name="documents",
                type=list,
                required=True,
                description="Documents to analyze for strategy selection",
            ),
            "query": NodeParameter(
                name="query",
                type=str,
                required=False,
                description="Query context for strategy optimization",
            ),
            "user_preferences": NodeParameter(
                name="user_preferences",
                type=dict,
                required=False,
                description="User preferences for strategy selection",
            ),
            "performance_history": NodeParameter(
                name="performance_history",
                type=dict,
                required=False,
                description="Historical performance data for strategy optimization",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Analyze and route to optimal RAG strategy"""
        documents = kwargs.get("documents", [])
        query = kwargs.get("query", "")
        user_preferences = kwargs.get("user_preferences", {})
        performance_history = kwargs.get("performance_history", {})

        # Initialize LLM agent if needed
        if not self.llm_agent:
            self.llm_agent = LLMAgentNode(
                name=f"{self.name}_llm",
                model=self.llm_model,
                provider=self.provider,
                system_prompt=self._get_strategy_selection_prompt(),
            )

        # Analyze documents
        analysis = self._analyze_documents(documents, query)

        # Get LLM recommendation
        llm_input = self._format_llm_input(
            analysis, query, user_preferences, performance_history
        )

        try:
            llm_response = self.llm_agent.execute(
                messages=[{"role": "user", "content": llm_input}]
            )

            strategy_decision = self._parse_llm_response(llm_response)

        except Exception as e:
            logger.warning(f"LLM strategy selection failed: {e}, using fallback")
            strategy_decision = self._fallback_strategy_selection(analysis)

        # Combine analysis with decision
        return {
            "strategy": strategy_decision["recommended_strategy"],
            "reasoning": strategy_decision["reasoning"],
            "confidence": strategy_decision["confidence"],
            "fallback_strategy": strategy_decision.get("fallback_strategy", "hybrid"),
            "document_analysis": analysis,
            "llm_model_used": self.llm_model,
            "routing_metadata": {
                "timestamp": time.time(),
                "documents_count": len(documents),
                "query_provided": bool(query),
                "user_preferences_provided": bool(user_preferences),
            },
        }

    def _get_strategy_selection_prompt(self) -> str:
        """Get system prompt for strategy selection"""
        return """You are an expert RAG (Retrieval Augmented Generation) strategy advisor. Your job is to analyze documents and queries to recommend the optimal RAG approach.

Available RAG strategies:

1. **semantic**: Uses semantic chunking with dense embeddings
   - Best for: Narrative content, general Q&A, conceptual queries
   - Strengths: Excellent semantic similarity matching
   - Use when: Documents have flowing text, user asks conceptual questions

2. **statistical**: Uses statistical chunking with sparse keyword matching
   - Best for: Technical documentation, code, structured content
   - Strengths: Precise keyword matching, handles technical terms well
   - Use when: Documents are technical, contain code, or need exact term matching

3. **hybrid**: Combines semantic + statistical with result fusion
   - Best for: Mixed content types, most general use cases
   - Strengths: 20-30% better performance than single methods
   - Use when: Unsure about content type or want maximum coverage

4. **hierarchical**: Multi-level processing preserving document structure
   - Best for: Long documents, structured content with sections/headings
   - Strengths: Maintains context relationships, handles complex documents
   - Use when: Documents are long (>2000 chars) with clear structure

Performance considerations:
- semantic: Fast, good for most queries
- statistical: Fast, precise for technical content
- hybrid: Slower but more comprehensive
- hierarchical: Slowest but best for complex documents

Respond with ONLY a valid JSON object in this exact format:
{
    "recommended_strategy": "semantic|statistical|hybrid|hierarchical",
    "reasoning": "Brief explanation (max 100 words)",
    "confidence": 0.0-1.0,
    "fallback_strategy": "backup strategy if primary fails"
}"""

    def _analyze_documents(self, documents: List[Dict], query: str) -> Dict[str, Any]:
        """Analyze documents for strategy selection"""
        if not documents:
            return {
                "total_docs": 0,
                "avg_length": 0,
                "total_length": 0,
                "has_structure": False,
                "is_technical": False,
                "content_types": [],
                "complexity_score": 0.0,
            }

        # Basic statistics
        total_length = sum(len(doc.get("content", "")) for doc in documents)
        avg_length = total_length / len(documents)

        # Structure detection
        structure_indicators = [
            "# ",
            "## ",
            "### ",
            "heading",
            "section",
            "chapter",
            "table of contents",
        ]
        has_structure = any(
            any(
                indicator in doc.get("content", "").lower()
                for indicator in structure_indicators
            )
            for doc in documents
        )

        # Technical content detection
        technical_keywords = [
            "function",
            "class",
            "import",
            "def ",
            "return",
            "variable",
            "algorithm",
            "api",
            "code",
            "programming",
            "software",
            "system",
            "method",
            "object",
            "parameter",
            "configuration",
            "install",
        ]
        technical_content_ratio = self._calculate_keyword_ratio(
            documents, technical_keywords
        )
        is_technical = technical_content_ratio > 0.1

        # Content type classification
        content_types = []
        if has_structure:
            content_types.append("structured")
        if is_technical:
            content_types.append("technical")
        if avg_length > 2000:
            content_types.append("long_form")
        if len(documents) > 100:
            content_types.append("large_collection")
        if technical_content_ratio > 0.3:
            content_types.append("highly_technical")

        # Complexity score (0.0 to 1.0)
        complexity_factors = [
            min(avg_length / 5000, 1.0),  # Length complexity
            min(len(documents) / 200, 1.0),  # Collection size complexity
            technical_content_ratio,  # Technical complexity
            1.0 if has_structure else 0.0,  # Structure complexity
        ]
        complexity_score = sum(complexity_factors) / len(complexity_factors)

        return {
            "total_docs": len(documents),
            "avg_length": int(avg_length),
            "total_length": total_length,
            "has_structure": has_structure,
            "is_technical": is_technical,
            "technical_content_ratio": technical_content_ratio,
            "content_types": content_types,
            "complexity_score": complexity_score,
            "query_analysis": self._analyze_query(query) if query else None,
        }

    def _calculate_keyword_ratio(
        self, documents: List[Dict], keywords: List[str]
    ) -> float:
        """Calculate ratio of technical keywords in documents"""
        if not documents:
            return 0.0

        total_words = 0
        keyword_matches = 0

        for doc in documents:
            content = doc.get("content", "").lower()
            words = content.split()
            total_words += len(words)

            for keyword in keywords:
                keyword_matches += content.count(keyword.lower())

        return keyword_matches / max(total_words, 1)

    def _analyze_query(self, query: str) -> Dict[str, Any]:
        """Analyze query characteristics"""
        query_lower = query.lower()

        # Query type detection
        question_indicators = ["what", "how", "why", "when", "where", "who", "which"]
        is_question = any(indicator in query_lower for indicator in question_indicators)

        technical_query_keywords = [
            "function",
            "code",
            "api",
            "error",
            "install",
            "configure",
        ]
        is_technical_query = any(
            keyword in query_lower for keyword in technical_query_keywords
        )

        conceptual_keywords = [
            "explain",
            "understand",
            "concept",
            "idea",
            "meaning",
            "definition",
        ]
        is_conceptual = any(keyword in query_lower for keyword in conceptual_keywords)

        return {
            "length": len(query),
            "is_question": is_question,
            "is_technical": is_technical_query,
            "is_conceptual": is_conceptual,
            "complexity": len(query.split())
            / 10.0,  # Rough complexity based on word count
        }

    def _format_llm_input(
        self,
        analysis: Dict,
        query: str,
        user_preferences: Dict,
        performance_history: Dict,
    ) -> str:
        """Format input for LLM strategy selection"""

        input_text = f"""Analyze this RAG use case and recommend the optimal strategy:

DOCUMENT ANALYSIS:
- Total documents: {analysis['total_docs']}
- Average length: {analysis['avg_length']} characters
- Total content: {analysis['total_length']} characters
- Has structure (headings/sections): {analysis['has_structure']}
- Technical content: {analysis['is_technical']} (ratio: {analysis.get('technical_content_ratio', 0):.2f})
- Content types: {', '.join(analysis['content_types'])}
- Complexity score: {analysis['complexity_score']:.2f}/1.0

QUERY ANALYSIS:"""

        if query:
            query_analysis = analysis.get("query_analysis", {})
            input_text += f"""
- Query: "{query}"
- Is question: {query_analysis.get('is_question', False)}
- Technical query: {query_analysis.get('is_technical', False)}
- Conceptual query: {query_analysis.get('is_conceptual', False)}
- Query complexity: {query_analysis.get('complexity', 0):.2f}"""
        else:
            input_text += "\n- No query provided (indexing mode)"

        if user_preferences:
            input_text += f"\n\nUSER PREFERENCES:\n{user_preferences}"

        if performance_history:
            input_text += f"\n\nPERFORMANCE HISTORY:\n{performance_history}"

        input_text += "\n\nRecommend the optimal RAG strategy:"

        return input_text

    def _parse_llm_response(self, llm_response: Dict) -> Dict[str, Any]:
        """Parse LLM response to extract strategy decision"""
        try:
            import json

            # Extract content from LLM response
            content = llm_response.get("content", "")
            if isinstance(content, list):
                content = content[0] if content else ""

            # Try to parse as JSON
            if "{" in content and "}" in content:
                json_start = content.find("{")
                json_end = content.rfind("}") + 1
                json_str = content[json_start:json_end]

                decision = json.loads(json_str)

                # Validate required fields
                required_fields = ["recommended_strategy", "reasoning", "confidence"]
                if all(field in decision for field in required_fields):
                    return decision

            # Fallback parsing
            return self._parse_fallback_response(content)

        except Exception as e:
            logger.warning(f"Failed to parse LLM response: {e}")
            return {
                "recommended_strategy": "hybrid",
                "reasoning": "LLM parsing failed, using safe default",
                "confidence": 0.5,
                "fallback_strategy": "semantic",
            }

    def _parse_fallback_response(self, content: str) -> Dict[str, Any]:
        """Fallback parsing for non-JSON LLM responses"""
        content_lower = content.lower()

        # Strategy detection
        strategies = ["semantic", "statistical", "hybrid", "hierarchical"]
        detected_strategy = "hybrid"  # default

        for strategy in strategies:
            if strategy in content_lower:
                detected_strategy = strategy
                break

        # Extract reasoning (first sentence or up to 100 chars)
        sentences = content.split(".")
        reasoning = (
            sentences[0][:100]
            if sentences
            else "Strategy selected based on content analysis"
        )

        return {
            "recommended_strategy": detected_strategy,
            "reasoning": reasoning,
            "confidence": 0.7,
            "fallback_strategy": "hybrid",
        }

    def _fallback_strategy_selection(self, analysis: Dict) -> Dict[str, Any]:
        """Rule-based fallback strategy selection when LLM fails"""

        # Rule-based selection
        if analysis["complexity_score"] > 0.7 and analysis["has_structure"]:
            strategy = "hierarchical"
            reasoning = "High complexity with structured content detected"
        elif (
            analysis["is_technical"]
            and analysis.get("technical_content_ratio", 0) > 0.2
        ):
            strategy = "statistical"
            reasoning = "Technical content detected, using keyword-based retrieval"
        elif analysis["total_docs"] > 50 or analysis["avg_length"] > 1000:
            strategy = "hybrid"
            reasoning = "Large document collection, using hybrid approach"
        else:
            strategy = "semantic"
            reasoning = "General content, using semantic similarity"

        return {
            "recommended_strategy": strategy,
            "reasoning": reasoning,
            "confidence": 0.8,
            "fallback_strategy": "hybrid",
        }


@register_node()
class RAGQualityAnalyzerNode(Node):
    """
    RAG Quality Analyzer Node

    Analyzes RAG results quality and provides recommendations for optimization.
    Tracks performance metrics and suggests improvements.
    """

    def __init__(self, name: str = "rag_quality_analyzer"):
        super().__init__(name)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "rag_results": NodeParameter(
                name="rag_results",
                type=dict,
                required=True,
                description="RAG results to analyze",
            ),
            "query": NodeParameter(
                name="query",
                type=str,
                required=False,
                description="Original query for relevance assessment",
            ),
            "expected_results": NodeParameter(
                name="expected_results",
                type=list,
                required=False,
                description="Expected results for validation (if available)",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Analyze RAG results quality"""
        rag_results = kwargs.get("rag_results", {})
        query = kwargs.get("query", "")
        expected_results = kwargs.get("expected_results", [])

        # Extract results and scores
        documents = rag_results.get("results", rag_results.get("documents", []))
        scores = rag_results.get("scores", [])

        # Quality metrics
        quality_analysis = {
            "result_count": len(documents),
            "has_scores": len(scores) > 0,
            "avg_score": sum(scores) / len(scores) if scores else 0.0,
            "min_score": min(scores) if scores else 0.0,
            "max_score": max(scores) if scores else 0.0,
            "score_variance": self._calculate_variance(scores) if scores else 0.0,
        }

        # Content quality analysis
        content_analysis = self._analyze_content_quality(documents, query)

        # Performance assessment
        performance_score = self._calculate_performance_score(
            quality_analysis, content_analysis
        )

        # Recommendations
        recommendations = self._generate_recommendations(
            quality_analysis, content_analysis, rag_results
        )

        return {
            "quality_score": performance_score,
            "quality_analysis": quality_analysis,
            "content_analysis": content_analysis,
            "recommendations": recommendations,
            "passed_quality_check": performance_score > 0.6,
            "analysis_timestamp": time.time(),
        }

    def _analyze_content_quality(
        self, documents: List[Dict], query: str
    ) -> Dict[str, Any]:
        """Analyze the quality of retrieved content"""
        if not documents:
            return {
                "diversity_score": 0.0,
                "avg_content_length": 0,
                "content_coverage": 0.0,
                "duplicate_ratio": 0.0,
            }

        # Content diversity (based on unique content)
        unique_contents = set()
        total_length = 0

        for doc in documents:
            content = doc.get("content", "")
            unique_contents.add(content[:100])  # First 100 chars for uniqueness
            total_length += len(content)

        diversity_score = len(unique_contents) / len(documents)
        avg_content_length = total_length / len(documents)

        # Query coverage (simple keyword matching)
        coverage_score = 0.0
        if query:
            query_words = set(query.lower().split())
            if query_words:
                covered_words = 0
                for doc in documents:
                    doc_words = set(doc.get("content", "").lower().split())
                    covered_words += len(query_words.intersection(doc_words))
                coverage_score = covered_words / (len(query_words) * len(documents))

        # Duplicate detection
        duplicate_ratio = 1.0 - diversity_score

        return {
            "diversity_score": diversity_score,
            "avg_content_length": avg_content_length,
            "content_coverage": coverage_score,
            "duplicate_ratio": duplicate_ratio,
        }

    def _calculate_variance(self, scores: List[float]) -> float:
        """Calculate variance of scores"""
        if len(scores) < 2:
            return 0.0

        mean = sum(scores) / len(scores)
        variance = sum((x - mean) ** 2 for x in scores) / len(scores)
        return variance

    def _calculate_performance_score(
        self, quality_analysis: Dict, content_analysis: Dict
    ) -> float:
        """Calculate overall performance score"""
        factors = [
            min(
                quality_analysis["result_count"] / 5.0, 1.0
            ),  # Result count (max score at 5 results)
            quality_analysis["avg_score"],  # Average relevance score
            content_analysis["diversity_score"],  # Content diversity
            content_analysis["content_coverage"],  # Query coverage
            1.0 - content_analysis["duplicate_ratio"],  # Inverse of duplicate ratio
        ]

        # Weighted average
        weights = [0.2, 0.3, 0.2, 0.2, 0.1]
        performance_score = sum(f * w for f, w in zip(factors, weights))

        return min(max(performance_score, 0.0), 1.0)

    def _generate_recommendations(
        self, quality_analysis: Dict, content_analysis: Dict, rag_results: Dict
    ) -> List[str]:
        """Generate recommendations for improving RAG performance"""
        recommendations = []

        # Result count recommendations
        if quality_analysis["result_count"] < 3:
            recommendations.append(
                "Consider lowering similarity threshold to retrieve more results"
            )
        elif quality_analysis["result_count"] > 10:
            recommendations.append(
                "Consider raising similarity threshold to get more focused results"
            )

        # Score quality recommendations
        if quality_analysis["avg_score"] < 0.5:
            recommendations.append(
                "Low relevance scores detected - consider different chunking strategy"
            )

        if quality_analysis["score_variance"] > 0.3:
            recommendations.append(
                "High score variance - results quality is inconsistent"
            )

        # Content quality recommendations
        if content_analysis["diversity_score"] < 0.7:
            recommendations.append(
                "High duplicate content - consider improving deduplication"
            )

        if content_analysis["content_coverage"] < 0.3:
            recommendations.append(
                "Poor query coverage - consider hybrid retrieval strategy"
            )

        if content_analysis["avg_content_length"] < 100:
            recommendations.append(
                "Very short content chunks - consider larger chunk sizes"
            )
        elif content_analysis["avg_content_length"] > 2000:
            recommendations.append(
                "Very long content chunks - consider smaller chunk sizes"
            )

        # Strategy-specific recommendations
        strategy_used = rag_results.get("strategy_used", "unknown")
        if strategy_used == "semantic" and quality_analysis["avg_score"] < 0.6:
            recommendations.append(
                "Consider switching to hybrid strategy for better coverage"
            )
        elif (
            strategy_used == "statistical"
            and content_analysis["content_coverage"] < 0.4
        ):
            recommendations.append(
                "Consider switching to semantic strategy for better understanding"
            )

        return recommendations


@register_node()
class RAGPerformanceMonitorNode(Node):
    """
    RAG Performance Monitor Node

    Monitors RAG system performance over time and provides insights
    for optimization and strategy adjustment.
    """

    def __init__(self, name: str = "rag_performance_monitor"):
        self.performance_history = []
        super().__init__(name)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "rag_results": NodeParameter(
                name="rag_results",
                type=dict,
                required=True,
                description="RAG results to monitor",
            ),
            "execution_time": NodeParameter(
                name="execution_time",
                type=float,
                required=False,
                description="Execution time in seconds",
            ),
            "strategy_used": NodeParameter(
                name="strategy_used",
                type=str,
                required=False,
                description="RAG strategy that was used",
            ),
            "query_type": NodeParameter(
                name="query_type",
                type=str,
                required=False,
                description="Type of query (technical, conceptual, etc.)",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Monitor and record RAG performance"""
        rag_results = kwargs.get("rag_results", {})
        execution_time = kwargs.get("execution_time", 0.0)
        strategy_used = kwargs.get("strategy_used", "unknown")
        query_type = kwargs.get("query_type", "general")

        # Create performance record
        performance_record = {
            "timestamp": time.time(),
            "strategy_used": strategy_used,
            "query_type": query_type,
            "execution_time": execution_time,
            "result_count": len(rag_results.get("results", [])),
            "avg_score": self._calculate_avg_score(rag_results),
            "success": len(rag_results.get("results", [])) > 0,
        }

        # Add to history
        self.performance_history.append(performance_record)

        # Keep only last 100 records
        if len(self.performance_history) > 100:
            self.performance_history = self.performance_history[-100:]

        # Calculate metrics
        metrics = self._calculate_metrics()

        # Generate insights
        insights = self._generate_insights(metrics)

        return {
            "current_performance": performance_record,
            "metrics": metrics,
            "insights": insights,
            "performance_history_size": len(self.performance_history),
        }

    def _calculate_avg_score(self, rag_results: Dict) -> float:
        """Calculate average score from RAG results"""
        scores = rag_results.get("scores", [])
        return sum(scores) / len(scores) if scores else 0.0

    def _calculate_metrics(self) -> Dict[str, Any]:
        """Calculate performance metrics from history"""
        if not self.performance_history:
            return {}

        recent_records = self.performance_history[-20:]  # Last 20 records

        # Overall metrics
        avg_execution_time = sum(r["execution_time"] for r in recent_records) / len(
            recent_records
        )
        avg_result_count = sum(r["result_count"] for r in recent_records) / len(
            recent_records
        )
        avg_score = sum(r["avg_score"] for r in recent_records) / len(recent_records)
        success_rate = sum(1 for r in recent_records if r["success"]) / len(
            recent_records
        )

        # Strategy performance
        strategy_performance = {}
        for record in recent_records:
            strategy = record["strategy_used"]
            if strategy not in strategy_performance:
                strategy_performance[strategy] = []
            strategy_performance[strategy].append(record)

        # Calculate per-strategy metrics
        strategy_metrics = {}
        for strategy, records in strategy_performance.items():
            strategy_metrics[strategy] = {
                "count": len(records),
                "avg_execution_time": sum(r["execution_time"] for r in records)
                / len(records),
                "avg_score": sum(r["avg_score"] for r in records) / len(records),
                "success_rate": sum(1 for r in records if r["success"]) / len(records),
            }

        return {
            "overall": {
                "avg_execution_time": avg_execution_time,
                "avg_result_count": avg_result_count,
                "avg_score": avg_score,
                "success_rate": success_rate,
            },
            "by_strategy": strategy_metrics,
            "total_queries": len(self.performance_history),
        }

    def _generate_insights(self, metrics: Dict) -> List[str]:
        """Generate performance insights and recommendations"""
        insights = []

        if not metrics:
            return ["Insufficient data for insights"]

        overall = metrics.get("overall", {})
        by_strategy = metrics.get("by_strategy", {})

        # Execution time insights
        if overall.get("avg_execution_time", 0) > 5.0:
            insights.append(
                "High average execution time detected - consider optimizing chunk sizes or vector DB"
            )
        elif overall.get("avg_execution_time", 0) < 0.5:
            insights.append("Excellent response times - system is well optimized")

        # Success rate insights
        success_rate = overall.get("success_rate", 0)
        if success_rate < 0.8:
            insights.append(
                "Low success rate - consider adjusting similarity thresholds"
            )
        elif success_rate > 0.95:
            insights.append("Excellent success rate - RAG system is performing well")

        # Score insights
        avg_score = overall.get("avg_score", 0)
        if avg_score < 0.5:
            insights.append(
                "Low relevance scores - consider different embedding model or chunking strategy"
            )
        elif avg_score > 0.8:
            insights.append("High relevance scores - excellent content matching")

        # Strategy comparison insights
        if len(by_strategy) > 1:
            best_strategy = max(by_strategy.items(), key=lambda x: x[1]["avg_score"])
            worst_strategy = min(by_strategy.items(), key=lambda x: x[1]["avg_score"])

            if best_strategy[1]["avg_score"] - worst_strategy[1]["avg_score"] > 0.2:
                insights.append(
                    f"Strategy '{best_strategy[0]}' significantly outperforms '{worst_strategy[0]}'"
                )

        return insights
