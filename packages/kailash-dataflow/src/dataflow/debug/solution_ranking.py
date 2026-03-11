"""
Solution Ranking Engine for DataFlow AI Debug Agent.

Ranks error solutions using LLM reasoning combined with historical effectiveness.

Responsibilities:
- Use LLM to analyze solutions and assign relevance scores
- Integrate pattern effectiveness from knowledge base
- Cache rankings for future use
- Return top 3 ranked solutions sorted by combined score

Ranking Formula:
- Combined Score = 0.7 * relevance_score + 0.3 * effectiveness_score
- Relevance score: From LLM analysis (0.0-1.0)
- Effectiveness score: From historical feedback (-1.0 to 1.0)

Cache Strategy:
- Cache hit: Return cached rankings if confidence > 0.8
- Cache miss: Call LLM, rank solutions, cache results
- Cache invalidation: Update effectiveness scores on new feedback
"""

import re
from typing import Any, Dict, List, Optional

from dataflow.debug.data_structures import (
    ErrorAnalysis,
    ErrorSolution,
    KnowledgeBase,
    RankedSolution,
    WorkflowContext,
)
from dataflow.debug.pattern_recognition import PatternRecognitionEngine


class SolutionRankingEngine:
    """
    Ranks error solutions using LLM reasoning and historical effectiveness.

    Responsibilities:
    - Use LLM to analyze solutions and assign relevance scores
    - Integrate pattern effectiveness from knowledge base
    - Cache rankings for future use
    - Return top 3 ranked solutions sorted by combined score
    """

    def __init__(
        self,
        llm_agent,  # KaizenNode instance
        knowledge_base: KnowledgeBase,
        pattern_engine: PatternRecognitionEngine,
    ):
        """
        Initialize Solution Ranking Engine.

        Args:
            llm_agent: KaizenNode instance for LLM reasoning
            knowledge_base: KnowledgeBase for pattern storage and feedback
            pattern_engine: PatternRecognitionEngine for pattern key generation
        """
        self.llm_agent = llm_agent
        self.knowledge_base = knowledge_base
        self.pattern_engine = pattern_engine

    def rank_solutions(
        self,
        error_analysis: ErrorAnalysis,
        workflow_context: WorkflowContext,
        solutions: List[ErrorSolution],
    ) -> List[RankedSolution]:
        """
        Rank solutions by relevance using LLM and historical effectiveness.

        Args:
            error_analysis: Error analysis result
            workflow_context: Workflow context
            solutions: List of error solutions to rank

        Returns:
            Top 3 ranked solutions sorted by combined score (descending)

        Example:
            >>> ranked = engine.rank_solutions(error, context, solutions)
            >>> print(ranked[0].relevance_score)  # 0.9
            >>> print(ranked[0].reasoning)  # "Directly addresses root cause"
        """
        # Generate pattern key
        pattern_key = self.pattern_engine.generate_pattern_key(
            error_analysis, workflow_context
        )

        # Check for cached rankings (confidence > 0.8)
        cached_ranking = self._get_cached_rankings(pattern_key)
        if cached_ranking is not None:
            return cached_ranking

        # Call LLM to rank solutions
        llm_response = self._call_llm_for_ranking(
            error_analysis, workflow_context, solutions
        )

        # Parse LLM response
        ranked_solutions = self._parse_llm_response(llm_response, solutions)

        # Get pattern effectiveness from knowledge base
        pattern_effectiveness = self.pattern_engine.get_pattern_effectiveness(
            pattern_key
        )

        # Integrate effectiveness scores
        if pattern_effectiveness is not None:
            effectiveness_score = pattern_effectiveness["effectiveness_score"]
        else:
            effectiveness_score = 0.0

        # Update effectiveness scores in ranked solutions
        for solution in ranked_solutions:
            solution.effectiveness_score = effectiveness_score

        # Sort by combined score (descending)
        ranked_solutions.sort(
            key=lambda s: self._calculate_combined_score(
                s.relevance_score, s.effectiveness_score
            ),
            reverse=True,
        )

        # Take top 3
        top_3 = ranked_solutions[:3]

        # Cache results
        self._cache_rankings(pattern_key, top_3)

        return top_3

    def _calculate_combined_score(
        self, relevance_score: float, effectiveness_score: float
    ) -> float:
        """
        Calculate combined score from relevance and effectiveness.

        Formula: 0.7 * relevance_score + 0.3 * effectiveness_score

        Args:
            relevance_score: LLM relevance score (0.0-1.0)
            effectiveness_score: Historical effectiveness (-1.0 to 1.0)

        Returns:
            Combined score (0.0-1.0)

        Examples:
            >>> _calculate_combined_score(0.9, 0.8)
            0.87  # 0.7*0.9 + 0.3*0.8 = 0.63 + 0.24

            >>> _calculate_combined_score(0.9, 0.0)
            0.63  # 0.7*0.9 + 0.3*0.0 = 0.63
        """
        combined = 0.7 * relevance_score + 0.3 * effectiveness_score
        return combined

    def _get_cached_rankings(self, pattern_key: str) -> Optional[List[RankedSolution]]:
        """
        Get cached rankings from knowledge base.

        Returns cached rankings if:
        - Pattern key exists in cache
        - Confidence > 0.8

        Args:
            pattern_key: Pattern key string

        Returns:
            List of RankedSolution if cached with high confidence, None otherwise

        Examples:
            >>> _get_cached_rankings("DF-101:parameter:UserCreateNode")
            [RankedSolution(...), ...]  # If confidence > 0.8

            >>> _get_cached_rankings("DF-999:unknown")
            None  # Cache miss
        """
        # Get cached ranking
        cached_ranking = self.knowledge_base.get_ranking(pattern_key)

        if cached_ranking is None:
            return None

        # Check confidence threshold (> 0.8)
        if len(cached_ranking) > 0:
            confidence = cached_ranking[0].confidence

            if confidence > 0.8:
                return cached_ranking

        # Low confidence, skip cache
        return None

    def _cache_rankings(self, pattern_key: str, ranked_solutions: List[RankedSolution]):
        """
        Store rankings in knowledge base for future use.

        Args:
            pattern_key: Pattern key string
            ranked_solutions: List of ranked solutions to cache

        Example:
            >>> _cache_rankings("DF-101:parameter:UserCreateNode", ranked)
            # Cached for future use
        """
        self.knowledge_base.store_ranking(pattern_key, ranked_solutions)

    def _call_llm_for_ranking(
        self,
        error_analysis: ErrorAnalysis,
        workflow_context: WorkflowContext,
        solutions: List[ErrorSolution],
    ) -> Dict[str, Any]:
        """
        Call LLM to rank solutions by relevance.

        Args:
            error_analysis: Error analysis result
            workflow_context: Workflow context
            solutions: List of solutions to rank

        Returns:
            LLM response dictionary with:
            - response: Ranking text
            - confidence: Confidence score (0.0-1.0)

        Example:
            >>> response = _call_llm_for_ranking(error, context, solutions)
            >>> print(response["response"])
            # "Solution 1: relevance=0.9, reasoning='Best solution'"
        """
        # Build prompt
        prompt = self._build_llm_prompt(error_analysis, workflow_context, solutions)

        # Call LLM - support both test mocks (with .run()) and real LLMAgentNode (with .execute())
        if hasattr(self.llm_agent, "run"):
            # Test mock interface
            llm_response = self.llm_agent.run({"prompt": prompt})
        else:
            # Real LLMAgentNode interface
            result = self.llm_agent.execute(
                messages=[{"role": "user", "content": prompt}],
                provider="mock",  # Use mock provider for now
                model="gpt-4o-mini",
            )
            # Extract response from LLMAgentNode result
            llm_response = {
                "response": result.get("response", ""),
                "confidence": result.get("confidence", 0.85),
            }

        return llm_response

    def _build_llm_prompt(
        self,
        error_analysis: ErrorAnalysis,
        workflow_context: WorkflowContext,
        solutions: List[ErrorSolution],
    ) -> str:
        """
        Build LLM prompt for solution ranking.

        Args:
            error_analysis: Error analysis result
            workflow_context: Workflow context
            solutions: List of solutions to rank

        Returns:
            Prompt string for LLM

        Example:
            >>> prompt = _build_llm_prompt(error, context, solutions)
            >>> print(prompt)
            # "You are a debugging expert..."
        """
        # Format solutions
        solutions_text = self._format_solutions(solutions)

        # Build prompt
        prompt = f"""
You are a debugging expert analyzing DataFlow error solutions.

Error: {error_analysis.error_code}
Message: {error_analysis.message}
Context: {error_analysis.context}

Workflow Context:
- Node type: {workflow_context.node_type or 'unknown'}
- Connections: {len(workflow_context.connections)}

Available Solutions:
{solutions_text}

Rank each solution by relevance (0.0-1.0) and provide reasoning.

Output format:
Solution 1: relevance=0.9, reasoning="Most directly addresses the root cause"
Solution 2: relevance=0.7, reasoning="Alternative approach with moderate complexity"
...
"""
        return prompt

    def _format_solutions(self, solutions: List[ErrorSolution]) -> str:
        """
        Format solutions for LLM prompt.

        Args:
            solutions: List of solutions

        Returns:
            Formatted solutions text

        Example:
            >>> _format_solutions([solution1, solution2])
            # "1. Add 'id' parameter to node\\n2. Check parameter mapping"
        """
        formatted = []
        for i, solution in enumerate(solutions):
            formatted.append(
                f"{i+1}. {solution.description}\n" f"   Code: {solution.code_template}"
            )

        return "\n".join(formatted)

    def _parse_llm_response(
        self, llm_response: Dict[str, Any], solutions: List[ErrorSolution]
    ) -> List[RankedSolution]:
        """
        Parse LLM response to extract relevance scores and reasoning.

        Args:
            llm_response: LLM response dictionary
            solutions: Original solutions list

        Returns:
            List of RankedSolution objects

        Example:
            >>> ranked = _parse_llm_response(response, solutions)
            >>> print(ranked[0].relevance_score)  # 0.9
            >>> print(ranked[0].reasoning)  # "Best solution"
        """
        response_text = llm_response.get("response", "")
        confidence = llm_response.get("confidence", 0.85)

        # Parse response line by line
        ranked_solutions = []

        # Pattern: Solution N: relevance=X.XX, reasoning="..."
        pattern = r'Solution \d+: relevance=([\d.]+), reasoning="([^"]+)"'

        matches = re.findall(pattern, response_text)

        for i, (relevance_str, reasoning) in enumerate(matches):
            if i >= len(solutions):
                break

            # Parse relevance score
            relevance_score = float(relevance_str)

            # Clamp to valid range [0.0, 1.0]
            relevance_score = max(0.0, min(1.0, relevance_score))

            # Create RankedSolution
            ranked_solution = RankedSolution(
                solution=solutions[i],
                relevance_score=relevance_score,
                reasoning=reasoning,
                confidence=confidence,
                effectiveness_score=0.0,  # Will be updated later
            )

            ranked_solutions.append(ranked_solution)

        # Fill missing solutions with default scores
        for i in range(len(ranked_solutions), len(solutions)):
            ranked_solution = RankedSolution(
                solution=solutions[i],
                relevance_score=0.5,  # Default score
                reasoning="No LLM ranking available",
                confidence=confidence,
                effectiveness_score=0.0,
            )
            ranked_solutions.append(ranked_solution)

        return ranked_solutions
