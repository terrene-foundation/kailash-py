"""Solution generator for error analysis results.

This module provides the SolutionGenerator that matches error analysis results
to solution templates from the KnowledgeBase and ranks them by relevance.
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from dataflow.debug.analysis_result import AnalysisResult
from dataflow.debug.error_categorizer import ErrorCategory
from dataflow.debug.knowledge_base import KnowledgeBase
from dataflow.debug.suggested_solution import SuggestedSolution


class SolutionGenerator:
    """Generates solution suggestions from analysis results.

    The SolutionGenerator matches error analysis results to solution templates
    from the KnowledgeBase, calculates relevance scores, customizes generic
    solutions with error-specific context, and ranks solutions by relevance.

    Usage:
        kb = KnowledgeBase("patterns.yaml", "solutions.yaml")
        generator = SolutionGenerator(kb)

        solutions = generator.generate_solutions(
            analysis=analysis_result,
            category=error_category,
            max_solutions=5,
            min_relevance=0.3
        )

        for solution in solutions:
            print(solution.title)
            print(solution.code_example)
    """

    def __init__(self, knowledge_base: KnowledgeBase):
        """Initialize SolutionGenerator with KnowledgeBase.

        Args:
            knowledge_base: KnowledgeBase instance with error patterns and solutions
        """
        self.knowledge_base = knowledge_base

    def generate_solutions(
        self,
        analysis: AnalysisResult,
        category: ErrorCategory,
        max_solutions: int = 5,
        min_relevance: float = 0.3,
    ) -> List[SuggestedSolution]:
        """Generate ranked solution suggestions for error analysis.

        Flow:
        1. Get candidate solutions from KnowledgeBase (via pattern)
        2. Calculate relevance scores (pattern confidence + context match)
        3. Filter by minimum relevance threshold
        4. Apply category-specific filters
        5. Customize solutions with error context
        6. Rank by relevance score
        7. Return top N solutions

        Args:
            analysis: AnalysisResult from ContextAnalyzer
            category: ErrorCategory from ErrorCategorizer
            max_solutions: Maximum number of solutions to return
            min_relevance: Minimum relevance score threshold (0.0-1.0)

        Returns:
            List of SuggestedSolution objects ranked by relevance

        Example:
            >>> analysis = AnalysisResult(
            ...     root_cause="Missing parameter 'id'",
            ...     affected_nodes=["create_user"],
            ...     context_data={"missing_parameter": "id", "model_name": "User"}
            ... )
            >>> category = ErrorCategory(
            ...     category="PARAMETER",
            ...     pattern_id="PARAM_001",
            ...     confidence=0.9
            ... )
            >>> solutions = generator.generate_solutions(analysis, category)
            >>> len(solutions) > 0
            True
            >>> solutions[0].relevance_score >= 0.3
            True
        """
        # Get candidate solutions from KnowledgeBase
        candidate_solutions = self._get_candidate_solutions(category)

        # If no candidate solutions and category is UNKNOWN, generate fallback solutions
        if not candidate_solutions:
            if category.category == "UNKNOWN":
                return self._generate_fallback_solutions(analysis, max_solutions)
            return []

        # Calculate relevance scores for each solution
        scored_solutions = []
        for solution_id, solution in candidate_solutions:
            relevance_score = self._calculate_relevance_score(
                solution, analysis, category
            )

            # Filter by minimum relevance
            if relevance_score < min_relevance:
                continue

            scored_solutions.append((solution_id, solution, relevance_score))

        # Apply category-specific filters
        scored_solutions = self._apply_category_filters(
            scored_solutions, analysis, category.category
        )

        # Customize solutions with error context
        suggested_solutions = []
        for solution_id, solution, relevance_score in scored_solutions:
            customized_solution = self._customize_solution(
                solution, analysis, solution_id
            )

            suggested = SuggestedSolution.from_kb_solution(
                solution_id=solution_id,
                kb_solution=customized_solution,
                relevance_score=relevance_score,
                confidence=category.confidence,
            )

            suggested_solutions.append(suggested)

        # Rank solutions by relevance score
        ranked_solutions = self._rank_solutions(suggested_solutions)

        # Return top N solutions
        return ranked_solutions[:max_solutions]

    def _get_candidate_solutions(
        self, category: ErrorCategory
    ) -> List[Tuple[str, Dict[str, Any]]]:
        """Get candidate solutions from KnowledgeBase.

        Retrieves solutions linked to the error pattern identified by the
        ErrorCategorizer.

        Args:
            category: ErrorCategory with pattern_id

        Returns:
            List of (solution_id, solution_dict) tuples

        Example:
            >>> category = ErrorCategory(
            ...     category="PARAMETER",
            ...     pattern_id="PARAM_001",
            ...     confidence=0.9
            ... )
            >>> solutions = generator._get_candidate_solutions(category)
            >>> len(solutions) > 0
            True
        """
        # Get pattern from KnowledgeBase
        pattern = self.knowledge_base.get_pattern(category.pattern_id)
        if not pattern:
            return []

        # Get solutions for this pattern
        solutions = self.knowledge_base.get_solutions_for_pattern(category.pattern_id)

        return [(sol["id"], sol) for sol in solutions]

    def _calculate_relevance_score(
        self,
        solution: Dict[str, Any],
        analysis: AnalysisResult,
        category: ErrorCategory,
    ) -> float:
        """Calculate relevance score for solution.

        Scoring algorithm combines:
        - Pattern confidence (from ErrorCategory): 0.0-1.0 (weight: 0.5)
        - Context match score: 0.0-1.0 (weight: 0.5)
        - Category match bonus: +0.2 if exact match

        Final score = (pattern_confidence * 0.5) + (context_match * 0.5) + category_bonus
        Range: 0.0-1.2 (capped at 1.0)

        Context match factors:
        - Solution addresses affected_nodes? +0.3
        - Solution addresses affected_models? +0.3
        - Solution references context_data fields? +0.4

        Args:
            solution: Solution dictionary from KnowledgeBase
            analysis: AnalysisResult with error context
            category: ErrorCategory with pattern confidence

        Returns:
            Relevance score (0.0-1.0)

        Example:
            >>> solution = {"title": "Add Missing 'id' Parameter", "category": "QUICK_FIX"}
            >>> analysis = AnalysisResult(
            ...     root_cause="Missing parameter 'id'",
            ...     affected_nodes=["UserCreateNode"],
            ...     affected_models=["User"],
            ...     context_data={"missing_parameter": "id"}
            ... )
            >>> category = ErrorCategory(category="PARAMETER", pattern_id="PARAM_001", confidence=0.9, features={})
            >>> score = generator._calculate_relevance_score(solution, analysis, category)
            >>> 0.0 <= score <= 1.0
            True
        """
        # Base score from pattern confidence
        pattern_confidence = category.confidence
        base_score = pattern_confidence * 0.5

        # Calculate context match score
        context_match = 0.0

        # Check if solution addresses affected nodes (+0.3)
        solution_text = f"{solution.get('title', '')} {solution.get('description', '')} {solution.get('code_example', '')}".lower()
        if analysis.affected_nodes:
            for node in analysis.affected_nodes:
                if node.lower() in solution_text:
                    context_match += 0.3
                    break

        # Check if solution addresses affected models (+0.3)
        if analysis.affected_models:
            for model in analysis.affected_models:
                if model.lower() in solution_text:
                    context_match += 0.3
                    break

        # Check if solution references context_data fields (+0.4)
        if analysis.context_data:
            # Check for specific context fields
            missing_param = analysis.context_data.get("missing_parameter", "")
            if missing_param and missing_param.lower() in solution_text:
                context_match += 0.4

            missing_node = analysis.context_data.get("missing_node", "")
            if missing_node and missing_node.lower() in solution_text:
                context_match += 0.4

            table_name = analysis.context_data.get("table_name", "")
            if table_name and table_name.lower() in solution_text:
                context_match += 0.4

        # Cap context_match at 1.0
        context_match = min(context_match, 1.0)

        # Calculate context match contribution
        context_score = context_match * 0.5

        # Calculate total score
        total_score = base_score + context_score

        # Category match bonus (+0.2 if exact match)
        solution_category = solution.get("category", "")
        if solution_category == "QUICK_FIX" and category.category in [
            "PARAMETER",
            "CONNECTION",
        ]:
            total_score += 0.2
        elif solution_category == "CODE_REFACTORING" and category.category in [
            "MIGRATION",
            "RUNTIME",
        ]:
            total_score += 0.1

        # Cap final score at 1.0
        return min(total_score, 1.0)

    def _apply_category_filters(
        self,
        scored_solutions: List[Tuple[str, Dict[str, Any], float]],
        analysis: AnalysisResult,
        category: str,
    ) -> List[Tuple[str, Dict[str, Any], float]]:
        """Apply category-specific filters to solutions.

        Args:
            scored_solutions: List of (solution_id, solution, score) tuples
            analysis: AnalysisResult with error context
            category: Error category string

        Returns:
            Filtered list of (solution_id, solution, score) tuples
        """
        if category == "PARAMETER":
            return self._filter_parameter_solutions(scored_solutions, analysis)
        elif category == "CONNECTION":
            return self._filter_connection_solutions(scored_solutions, analysis)
        elif category == "MIGRATION":
            return self._filter_migration_solutions(scored_solutions, analysis)
        elif category == "CONFIGURATION":
            return self._filter_configuration_solutions(scored_solutions, analysis)
        elif category == "RUNTIME":
            return self._filter_runtime_solutions(scored_solutions, analysis)
        else:
            return scored_solutions

    def _filter_parameter_solutions(
        self,
        scored_solutions: List[Tuple[str, Dict[str, Any], float]],
        analysis: AnalysisResult,
    ) -> List[Tuple[str, Dict[str, Any], float]]:
        """Filter solutions for PARAMETER errors.

        Prioritizes solutions for:
        - Specific parameter (e.g., "id", "email")
        - Primary key parameters
        - Required vs optional parameters

        Args:
            scored_solutions: List of (solution_id, solution, score) tuples
            analysis: AnalysisResult with parameter context

        Returns:
            Filtered and re-scored solutions
        """
        missing_param = analysis.context_data.get("missing_parameter", "")
        is_primary_key = analysis.context_data.get("is_primary_key", False)

        filtered = []
        for solution_id, solution, score in scored_solutions:
            solution_text = (
                f"{solution.get('title', '')} {solution.get('description', '')}".lower()
            )

            # Boost score if solution mentions the specific missing parameter
            if missing_param and missing_param.lower() in solution_text:
                score = min(score + 0.15, 1.0)

            # Boost score if parameter is primary key and solution mentions it
            if is_primary_key and "primary key" in solution_text:
                score = min(score + 0.1, 1.0)

            filtered.append((solution_id, solution, score))

        return filtered

    def _filter_connection_solutions(
        self,
        scored_solutions: List[Tuple[str, Dict[str, Any], float]],
        analysis: AnalysisResult,
    ) -> List[Tuple[str, Dict[str, Any], float]]:
        """Filter solutions for CONNECTION errors.

        Prioritizes solutions for:
        - Missing nodes (if similar_nodes found)
        - Connection parameter mismatches
        - Circular connection detection

        Args:
            scored_solutions: List of (solution_id, solution, score) tuples
            analysis: AnalysisResult with connection context

        Returns:
            Filtered and re-scored solutions
        """
        missing_node = analysis.context_data.get("missing_node", "")
        similar_nodes = analysis.context_data.get("similar_nodes", [])

        filtered = []
        for solution_id, solution, score in scored_solutions:
            solution_text = (
                f"{solution.get('title', '')} {solution.get('description', '')}".lower()
            )

            # Boost score if solution mentions node typos/missing nodes
            if similar_nodes and (
                "typo" in solution_text or "similar" in solution_text
            ):
                score = min(score + 0.2, 1.0)

            # Boost score if solution mentions the specific missing node
            if missing_node and missing_node.lower() in solution_text:
                score = min(score + 0.15, 1.0)

            filtered.append((solution_id, solution, score))

        return filtered

    def _filter_migration_solutions(
        self,
        scored_solutions: List[Tuple[str, Dict[str, Any], float]],
        analysis: AnalysisResult,
    ) -> List[Tuple[str, Dict[str, Any], float]]:
        """Filter solutions for MIGRATION errors.

        Prioritizes solutions for:
        - Table name typos (if similar_tables found)
        - Missing tables
        - Schema mismatches

        Args:
            scored_solutions: List of (solution_id, solution, score) tuples
            analysis: AnalysisResult with migration context

        Returns:
            Filtered and re-scored solutions
        """
        table_name = analysis.context_data.get("table_name", "")
        existing_tables = analysis.context_data.get("existing_tables", [])

        filtered = []
        for solution_id, solution, score in scored_solutions:
            solution_text = (
                f"{solution.get('title', '')} {solution.get('description', '')}".lower()
            )

            # Boost score if solution mentions table name issues
            if table_name and "table" in solution_text:
                score = min(score + 0.1, 1.0)

            # Boost score if solution mentions schema/migration
            if "schema" in solution_text or "migration" in solution_text:
                score = min(score + 0.1, 1.0)

            filtered.append((solution_id, solution, score))

        return filtered

    def _filter_configuration_solutions(
        self,
        scored_solutions: List[Tuple[str, Dict[str, Any], float]],
        analysis: AnalysisResult,
    ) -> List[Tuple[str, Dict[str, Any], float]]:
        """Filter solutions for CONFIGURATION errors.

        Prioritizes solutions for:
        - Database URL format errors
        - Environment variable issues
        - Connection pool configuration

        Args:
            scored_solutions: List of (solution_id, solution, score) tuples
            analysis: AnalysisResult with configuration context

        Returns:
            Filtered and re-scored solutions
        """
        filtered = []
        for solution_id, solution, score in scored_solutions:
            solution_text = (
                f"{solution.get('title', '')} {solution.get('description', '')}".lower()
            )

            # Boost score if solution mentions database URL
            if "database url" in solution_text or "connection string" in solution_text:
                score = min(score + 0.15, 1.0)

            # Boost score if solution mentions environment variables
            if "environment" in solution_text or ".env" in solution_text:
                score = min(score + 0.1, 1.0)

            filtered.append((solution_id, solution, score))

        return filtered

    def _filter_runtime_solutions(
        self,
        scored_solutions: List[Tuple[str, Dict[str, Any], float]],
        analysis: AnalysisResult,
    ) -> List[Tuple[str, Dict[str, Any], float]]:
        """Filter solutions for RUNTIME errors.

        Prioritizes solutions for:
        - Timeout errors
        - Deadlock errors
        - Resource exhaustion

        Args:
            scored_solutions: List of (solution_id, solution, score) tuples
            analysis: AnalysisResult with runtime context

        Returns:
            Filtered and re-scored solutions
        """
        runtime_issue = analysis.context_data.get("runtime_issue", "")

        filtered = []
        for solution_id, solution, score in scored_solutions:
            solution_text = (
                f"{solution.get('title', '')} {solution.get('description', '')}".lower()
            )

            # Boost score if solution matches specific runtime issue
            if runtime_issue and runtime_issue.lower() in solution_text:
                score = min(score + 0.2, 1.0)

            # Boost score if solution mentions timeout
            if runtime_issue == "timeout" and "timeout" in solution_text:
                score = min(score + 0.15, 1.0)

            # Boost score if solution mentions deadlock
            if runtime_issue == "deadlock" and "deadlock" in solution_text:
                score = min(score + 0.15, 1.0)

            filtered.append((solution_id, solution, score))

        return filtered

    def _customize_solution(
        self, solution: Dict[str, Any], analysis: AnalysisResult, solution_id: str
    ) -> Dict[str, Any]:
        """Customize generic solution template with error context.

        Replaces placeholders in code_example and explanation with specific
        values from AnalysisResult context_data.

        Customization rules:
        - ${parameter_name} → context_data["missing_parameter"]
        - ${model_name} → context_data["model_name"]
        - ${node_type} → context_data["node_type"]
        - ${missing_node} → context_data["missing_node"]
        - ${suggested_node} → context_data["similar_nodes"][0][0]
        - ${table_name} → context_data["table_name"]
        - ${correct_table} → context_data["existing_tables"][0]

        Args:
            solution: Solution dictionary from KnowledgeBase
            analysis: AnalysisResult with error context
            solution_id: Solution identifier for tracking

        Returns:
            Customized solution dictionary

        Example:
            >>> solution = {
            ...     "code_example": 'workflow.add_node("${node_type}", "create", {"${parameter_name}": "value"})',
            ...     "explanation": "Add missing parameter ${parameter_name} to ${node_type}"
            ... }
            >>> analysis = AnalysisResult(
            ...     root_cause="Missing parameter",
            ...     context_data={"missing_parameter": "id", "node_type": "UserCreateNode"}
            ... )
            >>> customized = generator._customize_solution(solution, analysis, "SOL_001")
            >>> "id" in customized["code_example"]
            True
        """
        # Create a copy to avoid modifying the original
        customized = solution.copy()

        # Extract context values
        context = analysis.context_data
        replacements = {}

        # PARAMETER error context
        if "missing_parameter" in context:
            replacements["${parameter_name}"] = context["missing_parameter"]
        if "model_name" in context:
            replacements["${model_name}"] = context["model_name"]
        if "node_type" in context:
            replacements["${node_type}"] = context["node_type"]

        # CONNECTION error context
        if "missing_node" in context:
            replacements["${missing_node}"] = context["missing_node"]
        if "similar_nodes" in context and context["similar_nodes"]:
            replacements["${suggested_node}"] = context["similar_nodes"][0][0]

        # MIGRATION error context
        if "table_name" in context:
            replacements["${table_name}"] = context["table_name"]
        if "existing_tables" in context and context["existing_tables"]:
            replacements["${correct_table}"] = context["existing_tables"][0]

        # Apply replacements to code_example
        code_example = customized.get("code_example", "")
        for placeholder, value in replacements.items():
            code_example = code_example.replace(placeholder, value)
        customized["code_example"] = code_example

        # Apply replacements to explanation
        explanation = customized.get("explanation", "")
        for placeholder, value in replacements.items():
            explanation = explanation.replace(placeholder, value)
        customized["explanation"] = explanation

        # Apply replacements to description
        description = customized.get("description", "")
        for placeholder, value in replacements.items():
            description = description.replace(placeholder, value)
        customized["description"] = description

        return customized

    def _rank_solutions(
        self, solutions: List[SuggestedSolution]
    ) -> List[SuggestedSolution]:
        """Rank solutions by relevance score (descending).

        Args:
            solutions: List of SuggestedSolution objects

        Returns:
            Sorted list with highest relevance first

        Example:
            >>> sol1 = SuggestedSolution(
            ...     solution_id="SOL_001", title="Fix 1", category="QUICK_FIX",
            ...     description="", code_example="", explanation="",
            ...     relevance_score=0.95, confidence=0.9
            ... )
            >>> sol2 = SuggestedSolution(
            ...     solution_id="SOL_002", title="Fix 2", category="QUICK_FIX",
            ...     description="", code_example="", explanation="",
            ...     relevance_score=0.75, confidence=0.8
            ... )
            >>> ranked = generator._rank_solutions([sol2, sol1])
            >>> ranked[0].relevance_score > ranked[1].relevance_score
            True
        """
        return sorted(solutions, key=lambda s: s.relevance_score, reverse=True)

    def _generate_fallback_solutions(
        self, analysis: AnalysisResult, max_solutions: int = 5
    ) -> List[SuggestedSolution]:
        """Generate fallback solutions for UNKNOWN error categories.

        When no pattern matches or category is UNKNOWN, this method generates
        generic but actionable solutions based on:
        - Error message keywords
        - Root cause analysis
        - Affected components (nodes, models, connections)
        - Context data hints

        Args:
            analysis: AnalysisResult with error details
            max_solutions: Maximum number of fallback solutions to generate

        Returns:
            List of SuggestedSolution objects with generic recommendations

        Example:
            >>> analysis = AnalysisResult(
            ...     root_cause="Unknown error in node 'create_user'",
            ...     affected_nodes=["create_user"],
            ...     affected_models=["User"],
            ...     context_data={"error_message": "Database connection failed"}
            ... )
            >>> solutions = generator._generate_fallback_solutions(analysis)
            >>> len(solutions) > 0
            True
        """
        fallback_solutions = []

        # Solution 1: Check error message and stack trace
        solution_1 = SuggestedSolution(
            solution_id="FALLBACK_001",
            title="Examine Error Message and Stack Trace",
            category="INVESTIGATION",
            description="Review the full error message and stack trace to identify the specific issue.",
            code_example=f"# Error: {analysis.root_cause}\n# Affected nodes: {', '.join(analysis.affected_nodes) if analysis.affected_nodes else 'None'}",
            explanation=(
                "Since the error pattern is not recognized, start by carefully examining "
                "the error message and stack trace. Look for:\n"
                "- Specific field or parameter names mentioned\n"
                "- Database constraint violations\n"
                "- Connection or node references\n"
                "- File paths or configuration issues"
            ),
            relevance_score=0.5,
            confidence=0.0,
            difficulty="easy",
            estimated_time=5,
        )
        fallback_solutions.append(solution_1)

        # Solution 2: Verify affected components
        if analysis.affected_nodes or analysis.affected_models:
            affected_items = []
            if analysis.affected_nodes:
                affected_items.extend(
                    [f"Node '{node}'" for node in analysis.affected_nodes]
                )
            if analysis.affected_models:
                affected_items.extend(
                    [f"Model '{model}'" for model in analysis.affected_models]
                )

            solution_2 = SuggestedSolution(
                solution_id="FALLBACK_002",
                title="Verify Configuration of Affected Components",
                category="INVESTIGATION",
                description=f"Check the configuration and parameters of: {', '.join(affected_items)}",
                code_example=self._generate_verification_code(analysis),
                explanation=(
                    "The error involves specific components. Verify:\n"
                    "- All required parameters are provided\n"
                    "- Parameter types match expected types\n"
                    "- Node connections are correct\n"
                    "- Model schemas match database tables"
                ),
                relevance_score=0.45,
                confidence=0.0,
                difficulty="easy",
                estimated_time=10,
            )
            fallback_solutions.append(solution_2)

        # Solution 3: Check suggestions from analysis
        if analysis.suggestions:
            solution_3 = SuggestedSolution(
                solution_id="FALLBACK_003",
                title="Follow Context-Specific Recommendations",
                category="INVESTIGATION",
                description="Apply the recommendations identified during error analysis",
                code_example="# Recommendations:\n"
                + "\n".join([f"# - {sug}" for sug in analysis.suggestions[:3]]),
                explanation=(
                    "The error analysis identified specific recommendations:\n\n"
                    + "\n".join([f"• {sug}" for sug in analysis.suggestions[:5]])
                ),
                relevance_score=0.55,
                confidence=0.0,
                difficulty="medium",
                estimated_time=15,
            )
            fallback_solutions.append(solution_3)

        # Solution 4: Enable debug logging
        solution_4 = SuggestedSolution(
            solution_id="FALLBACK_004",
            title="Enable Debug Logging for More Information",
            category="INVESTIGATION",
            description="Run the workflow with debug mode enabled to capture detailed execution information",
            code_example=(
                "from kailash.runtime import LocalRuntime\n\n"
                "runtime = LocalRuntime(debug=True)\n"
                "results, run_id = runtime.execute(workflow.build())"
            ),
            explanation=(
                "Enable debug mode to get more detailed information about:\n"
                "- Node execution order\n"
                "- Parameter values at each step\n"
                "- Intermediate results\n"
                "- Exact point of failure"
            ),
            relevance_score=0.4,
            confidence=0.0,
            difficulty="easy",
            estimated_time=5,
        )
        fallback_solutions.append(solution_4)

        # Solution 5: Review DataFlow patterns documentation
        solution_5 = SuggestedSolution(
            solution_id="FALLBACK_005",
            title="Consult DataFlow Documentation and Patterns",
            category="BEST_PRACTICE",
            description="Review the DataFlow documentation for similar error patterns and solutions",
            code_example=(
                "# Review documentation sections:\n"
                "# - Common error patterns\n"
                "# - Workflow debugging guide\n"
                "# - Node parameter reference\n"
                "# - Connection troubleshooting"
            ),
            explanation=(
                "Check the DataFlow documentation for:\n"
                "- Similar error messages and their solutions\n"
                "- Best practices for the components involved\n"
                "- Common pitfalls and how to avoid them\n"
                "- Example workflows and patterns"
            ),
            relevance_score=0.35,
            confidence=0.0,
            difficulty="easy",
            estimated_time=10,
        )
        fallback_solutions.append(solution_5)

        # Rank solutions by relevance score and return top N
        return self._rank_solutions(fallback_solutions)[:max_solutions]

    def _generate_verification_code(self, analysis: AnalysisResult) -> str:
        """Generate verification code snippet for affected components.

        Args:
            analysis: AnalysisResult with affected components

        Returns:
            Python code snippet for verification
        """
        lines = []

        if analysis.affected_nodes:
            lines.append("# Verify node configuration")
            for node in analysis.affected_nodes[:2]:
                lines.append(f"# Check node '{node}' parameters and connections")

        if analysis.affected_models:
            lines.append("\n# Verify model schema")
            for model in analysis.affected_models[:2]:
                lines.append(f"# Check model '{model}' fields match database table")

        if analysis.context_data:
            lines.append("\n# Review context data:")
            for key, value in list(analysis.context_data.items())[:3]:
                if isinstance(value, (str, int, float, bool)):
                    lines.append(f"# {key}: {value}")

        return (
            "\n".join(lines) if lines else "# No specific verification steps identified"
        )
