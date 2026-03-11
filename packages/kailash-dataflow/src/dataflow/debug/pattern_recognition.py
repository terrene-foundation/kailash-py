"""
Pattern Recognition Engine for DataFlow AI Debug Agent.

Analyzes error patterns and finds similar cached solutions from Knowledge Base.

Responsibilities:
- Generate unique pattern keys for error analysis
- Calculate similarity scores between errors
- Find cached patterns from Knowledge Base
- Retrieve pattern effectiveness from feedback

Pattern Key Strategy:
- Primary: error_code (DF-XXX)
- Secondary: category + node_type (if available)
- Tertiary: context parameters (node_id, parameter names)

Match Score Calculation (0.0-1.0):
- Exact error code match: 1.0
- Same category: 0.7
- Similar context: 0.5
- Different error: 0.0
"""

from typing import Any, Dict, List, Optional

from dataflow.debug.data_structures import (
    ErrorAnalysis,
    KnowledgeBase,
    RankedSolution,
    WorkflowContext,
)


class PatternRecognitionEngine:
    """
    Recognizes error patterns and finds similar cached solutions.

    Responsibilities:
    - Generate unique pattern keys for error analysis
    - Calculate similarity scores between errors
    - Find cached patterns from Knowledge Base
    - Retrieve pattern effectiveness from feedback
    """

    def __init__(self, knowledge_base: KnowledgeBase):
        """
        Initialize PatternRecognitionEngine.

        Args:
            knowledge_base: KnowledgeBase instance for pattern storage
        """
        self.knowledge_base = knowledge_base

    def generate_pattern_key(
        self,
        error_analysis: ErrorAnalysis,
        workflow_context: Optional[WorkflowContext] = None,
    ) -> str:
        """
        Generate unique pattern key for error analysis.

        Pattern Key Strategy:
        - Primary: error_code (DF-XXX)
        - Secondary: category + node_type (if available)
        - Tertiary: context parameters (node_id, parameter names)

        Args:
            error_analysis: Error analysis result
            workflow_context: Optional workflow context

        Returns:
            Pattern key string (e.g., "DF-101:parameter:UserCreateNode")

        Examples:
            >>> generate_pattern_key(error, None)
            "DF-101"

            >>> generate_pattern_key(error, WorkflowContext())
            "DF-101:parameter"

            >>> generate_pattern_key(error, WorkflowContext(node_type="UserCreateNode"))
            "DF-101:parameter:UserCreateNode"
        """
        # Start with error code (primary)
        key_parts = [error_analysis.error_code]

        # Add category if workflow context exists (secondary)
        if workflow_context is not None:
            key_parts.append(error_analysis.category)

            # Add node_type if available (tertiary)
            if workflow_context.node_type:
                key_parts.append(workflow_context.node_type)

        # Join with colon separator
        return ":".join(key_parts)

    def calculate_match_score(
        self, error1: ErrorAnalysis, error2: ErrorAnalysis
    ) -> float:
        """
        Calculate similarity score between two errors.

        Match Score Calculation (0.0-1.0):
        - Exact error code match: 1.0
        - Same category: 0.7
        - Similar context: 0.5
        - Different error: 0.0

        Args:
            error1: First error analysis
            error2: Second error analysis

        Returns:
            Similarity score (0.0-1.0)

        Examples:
            >>> calculate_match_score(error1, error2)  # Same error code
            1.0

            >>> calculate_match_score(error1, error2)  # Same category
            0.7

            >>> calculate_match_score(error1, error2)  # Similar context
            0.5

            >>> calculate_match_score(error1, error2)  # Different
            0.0
        """
        # Exact error code match (highest priority)
        if error1.error_code == error2.error_code:
            return 1.0

        # Same category match (medium priority)
        if error1.category == error2.category:
            return 0.7

        # Similar context match (low priority)
        # Check if any context keys overlap
        context1_keys = set(error1.context.keys())
        context2_keys = set(error2.context.keys())

        if context1_keys & context2_keys:  # Intersection exists
            # Check if any values match for overlapping keys
            for key in context1_keys & context2_keys:
                if error1.context.get(key) == error2.context.get(key):
                    return 0.5

        # Different errors (no match)
        return 0.0

    def find_similar_patterns(
        self,
        error_analysis: ErrorAnalysis,
        workflow_context: Optional[WorkflowContext] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Find similar cached patterns from Knowledge Base.

        Searches Knowledge Base for patterns matching the current error,
        sorted by match score (descending).

        Args:
            error_analysis: Error analysis result
            workflow_context: Optional workflow context
            limit: Maximum number of results to return

        Returns:
            List of matching patterns with:
            - pattern_key: Pattern key string
            - match_score: Similarity score (0.0-1.0)
            - solutions: List of RankedSolution objects

        Examples:
            >>> find_similar_patterns(error)
            [
                {
                    "pattern_key": "DF-101:parameter:UserCreateNode",
                    "match_score": 1.0,
                    "solutions": [RankedSolution(...)]
                }
            ]
        """
        results = []

        # Get all cached patterns from Knowledge Base
        # Note: KnowledgeBase stores patterns as Dict[pattern_key, List[RankedSolution]]
        cached_patterns = self._get_all_cached_patterns()

        # Calculate match score for each cached pattern
        for pattern_key, ranked_solutions in cached_patterns.items():
            # Parse pattern key to extract error_code and category
            cached_error = self._parse_pattern_key(pattern_key)

            if cached_error is None:
                continue

            # Calculate match score
            score = self.calculate_match_score(error_analysis, cached_error)

            # Filter out zero scores
            if score > 0.0:
                results.append(
                    {
                        "pattern_key": pattern_key,
                        "match_score": score,
                        "solutions": ranked_solutions,
                    }
                )

        # Sort by match score (descending)
        results.sort(key=lambda x: x["match_score"], reverse=True)

        # Limit results
        return results[:limit]

    def get_pattern_effectiveness(self, pattern_key: str) -> Optional[Dict[str, Any]]:
        """
        Get pattern effectiveness from feedback.

        Retrieves effectiveness score and feedback statistics for a pattern.

        Args:
            pattern_key: Pattern key string

        Returns:
            Dictionary with:
            - effectiveness_score: Float (-1.0 to 1.0)
            - feedback: Dict with used, thumbs_up, thumbs_down counts

            None if pattern not found

        Examples:
            >>> get_pattern_effectiveness("DF-101:parameter:UserCreateNode")
            {
                "effectiveness_score": 0.8,
                "feedback": {"used": 10, "thumbs_up": 9, "thumbs_down": 1}
            }
        """
        # Check if pattern exists in Knowledge Base
        ranked_solutions = self.knowledge_base.get_ranking(pattern_key)

        if ranked_solutions is None:
            return None

        # Get feedback data for pattern
        if pattern_key not in self.knowledge_base.feedback:
            # No feedback recorded yet
            return {
                "effectiveness_score": 0.0,
                "feedback": {"used": 0, "thumbs_up": 0, "thumbs_down": 0},
            }

        # Get feedback data
        feedback_data = self.knowledge_base.feedback[pattern_key]

        # Calculate effectiveness score from first solution (index 0)
        solution_feedback = feedback_data.get_solution_feedback(0)

        # Calculate effectiveness score: (thumbs_up - thumbs_down) / total_uses
        thumbs_up = solution_feedback["thumbs_up"]
        thumbs_down = solution_feedback["thumbs_down"]
        total_uses = solution_feedback["used"]

        if total_uses > 0:
            effectiveness_score = (thumbs_up - thumbs_down) / total_uses
        else:
            effectiveness_score = 0.0

        return {
            "effectiveness_score": effectiveness_score,
            "feedback": solution_feedback,
        }

    # ========================================================================
    # Helper Methods
    # ========================================================================

    def _get_all_cached_patterns(self) -> Dict[str, List[RankedSolution]]:
        """
        Get all cached patterns from Knowledge Base.

        Returns:
            Dictionary mapping pattern_key to List[RankedSolution]
        """
        # Access KnowledgeBase internal patterns dictionary
        # (memory storage only for Phase 1)
        if self.knowledge_base.storage_type == "memory":
            return self.knowledge_base.patterns
        else:
            # Persistent storage not implemented in Phase 1
            return {}

    def _parse_pattern_key(self, pattern_key: str) -> Optional[ErrorAnalysis]:
        """
        Parse pattern key to extract error analysis details.

        Args:
            pattern_key: Pattern key string (e.g., "DF-101:parameter:UserCreateNode")

        Returns:
            ErrorAnalysis object with extracted details, or None if invalid

        Examples:
            >>> _parse_pattern_key("DF-101:parameter:UserCreateNode")
            ErrorAnalysis(error_code="DF-101", category="parameter", ...)

            >>> _parse_pattern_key("DF-101")
            ErrorAnalysis(error_code="DF-101", category="unknown", ...)
        """
        parts = pattern_key.split(":")

        if len(parts) < 1:
            return None

        # Extract error_code (always present)
        error_code = parts[0]

        # Extract category (if present)
        category = parts[1] if len(parts) > 1 else "unknown"

        # Extract node_type (if present)
        node_type = parts[2] if len(parts) > 2 else None

        # Create ErrorAnalysis object
        return ErrorAnalysis(
            error_code=error_code,
            category=category,
            message="",
            context={"node_type": node_type} if node_type else {},
            causes=[],
            solutions=[],
            severity="error",
            docs_url="",
        )
