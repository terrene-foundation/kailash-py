"""Suggested solution with code example and explanation.

This module provides the SuggestedSolution data structure that represents a
solution recommendation from the SolutionGenerator.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SuggestedSolution:
    """Suggested solution with code example and explanation.

    The SuggestedSolution contains a complete solution recommendation including:
    - Solution metadata (ID, title, category)
    - Code example demonstrating the fix
    - Detailed explanation of why this solves the problem
    - Difficulty and time estimate
    - Relevance and confidence scores

    Attributes:
        solution_id: Solution identifier (e.g., "SOL_001")
        title: Short, descriptive title of the solution
        category: Solution category (QUICK_FIX, CODE_REFACTORING, CONFIGURATION, ARCHITECTURE)
        description: Brief description of what this solution does
        code_example: Complete code example demonstrating the fix
        explanation: Detailed explanation of why this solves the problem
        references: List of documentation links for more information
        difficulty: Difficulty level (easy, medium, hard)
        estimated_time: Estimated time to implement in minutes
        relevance_score: How relevant this solution is to the error (0.0-1.0)
        confidence: Confidence in this solution (0.0-1.0)

    Example:
        >>> solution = SuggestedSolution(
        ...     solution_id="SOL_001",
        ...     title="Add Missing 'id' Parameter",
        ...     category="QUICK_FIX",
        ...     description="Add required 'id' field to CreateNode",
        ...     code_example='workflow.add_node("UserCreateNode", "create", {"id": "user-123", "name": "Alice"})',
        ...     explanation="The 'id' field is required for all CREATE operations in DataFlow...",
        ...     references=["https://docs.dataflow.dev/nodes/create"],
        ...     difficulty="easy",
        ...     estimated_time=1,
        ...     relevance_score=0.95,
        ...     confidence=0.9
        ... )
        >>> print(solution.title)
        Add Missing 'id' Parameter
    """

    solution_id: str
    title: str
    category: str
    description: str
    code_example: str
    explanation: str
    references: List[str] = field(default_factory=list)
    difficulty: str = "medium"
    estimated_time: int = 5  # minutes
    relevance_score: float = 0.0
    confidence: float = 0.0

    @classmethod
    def from_kb_solution(
        cls,
        solution_id: str,
        kb_solution: Dict[str, Any],
        relevance_score: float,
        confidence: float,
    ) -> "SuggestedSolution":
        """Create SuggestedSolution from KnowledgeBase solution.

        Args:
            solution_id: Solution identifier (e.g., "SOL_001")
            kb_solution: Solution dictionary from KnowledgeBase
            relevance_score: Calculated relevance score (0.0-1.0)
            confidence: Pattern matching confidence (0.0-1.0)

        Returns:
            SuggestedSolution instance

        Example:
            >>> kb_solution = {
            ...     "title": "Add Missing 'id' Parameter",
            ...     "category": "QUICK_FIX",
            ...     "description": "Add required 'id' field",
            ...     "code_example": "...",
            ...     "explanation": "...",
            ...     "references": ["https://docs.dataflow.dev/..."],
            ...     "difficulty": "easy",
            ...     "estimated_time": 1
            ... }
            >>> solution = SuggestedSolution.from_kb_solution(
            ...     "SOL_001", kb_solution, relevance_score=0.95, confidence=0.9
            ... )
            >>> solution.solution_id
            'SOL_001'
        """
        return cls(
            solution_id=solution_id,
            title=kb_solution.get("title", "Unknown Solution"),
            category=kb_solution.get("category", "UNKNOWN"),
            description=kb_solution.get("description", ""),
            code_example=kb_solution.get("code_example", ""),
            explanation=kb_solution.get("explanation", ""),
            references=kb_solution.get("references", []),
            difficulty=kb_solution.get("difficulty", "medium"),
            estimated_time=kb_solution.get("estimated_time", 5),
            relevance_score=relevance_score,
            confidence=confidence,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert SuggestedSolution to dictionary for serialization.

        Returns:
            Dictionary representation with all fields

        Example:
            >>> solution = SuggestedSolution(
            ...     solution_id="SOL_001",
            ...     title="Add Missing 'id' Parameter",
            ...     category="QUICK_FIX",
            ...     description="Add required 'id' field",
            ...     code_example="...",
            ...     explanation="...",
            ...     relevance_score=0.95,
            ...     confidence=0.9
            ... )
            >>> data = solution.to_dict()
            >>> data["solution_id"]
            'SOL_001'
            >>> data["relevance_score"]
            0.95
        """
        return {
            "solution_id": self.solution_id,
            "title": self.title,
            "category": self.category,
            "description": self.description,
            "code_example": self.code_example,
            "explanation": self.explanation,
            "references": self.references,
            "difficulty": self.difficulty,
            "estimated_time": self.estimated_time,
            "relevance_score": self.relevance_score,
            "confidence": self.confidence,
        }

    def format_for_cli(self, include_code_example: bool = True) -> str:
        """Format solution for CLI display.

        Args:
            include_code_example: Whether to include code example in output

        Returns:
            Formatted string for terminal display

        Example:
            >>> solution = SuggestedSolution(
            ...     solution_id="SOL_001",
            ...     title="Add Missing 'id' Parameter",
            ...     category="QUICK_FIX",
            ...     description="Add required 'id' field to CreateNode",
            ...     code_example='workflow.add_node("UserCreateNode", "create", {"id": "user-123"})',
            ...     explanation="The 'id' field is required...",
            ...     difficulty="easy",
            ...     estimated_time=1,
            ...     relevance_score=0.95,
            ...     confidence=0.9
            ... )
            >>> print(solution.format_for_cli())
            [SOL_001] Add Missing 'id' Parameter (QUICK_FIX)
            Difficulty: easy | Time: 1 min | Relevance: 95%
            <BLANKLINE>
            Description:
            Add required 'id' field to CreateNode
            <BLANKLINE>
            Explanation:
            The 'id' field is required...
            <BLANKLINE>
            Code Example:
            workflow.add_node("UserCreateNode", "create", {"id": "user-123"})
        """
        lines = []

        # Header with solution ID and title
        lines.append(f"[{self.solution_id}] {self.title} ({self.category})")

        # Metadata line
        relevance_pct = int(self.relevance_score * 100)
        confidence_pct = int(self.confidence * 100)
        lines.append(
            f"Difficulty: {self.difficulty} | "
            f"Time: {self.estimated_time} min | "
            f"Relevance: {relevance_pct}%"
        )
        lines.append("")

        # Description
        lines.append("Description:")
        lines.append(self.description)
        lines.append("")

        # Explanation
        lines.append("Explanation:")
        lines.append(self.explanation)

        # Code example (optional)
        if include_code_example and self.code_example:
            lines.append("")
            lines.append("Code Example:")
            lines.append(self.code_example)

        # References
        if self.references:
            lines.append("")
            lines.append("References:")
            for ref in self.references:
                lines.append(f"- {ref}")

        return "\n".join(lines)

    def __repr__(self) -> str:
        """Debug representation of SuggestedSolution.

        Returns:
            String representation with solution ID, title, and relevance score

        Example:
            >>> solution = SuggestedSolution(
            ...     solution_id="SOL_001",
            ...     title="Add Missing 'id' Parameter",
            ...     category="QUICK_FIX",
            ...     description="...",
            ...     code_example="...",
            ...     explanation="...",
            ...     relevance_score=0.95,
            ...     confidence=0.9
            ... )
            >>> repr(solution)
            "SuggestedSolution(id='SOL_001', title='Add Missing \\'id\\' Parameter', relevance=0.95)"
        """
        return (
            f"SuggestedSolution("
            f"id='{self.solution_id}', "
            f"title='{self.title}', "
            f"relevance={self.relevance_score:.2f})"
        )
