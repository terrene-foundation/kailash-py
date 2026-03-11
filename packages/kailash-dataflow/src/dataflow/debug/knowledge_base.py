"""Knowledge base for error patterns and solutions.

This module provides a centralized knowledge base that loads and queries
error patterns and solutions from YAML databases.
"""

from typing import Dict, List, Optional

import yaml


class KnowledgeBase:
    """Loads and queries error patterns and solutions from YAML databases.

    The KnowledgeBase provides access to:
    - 50+ error patterns (patterns.yaml)
    - 67+ solutions (solutions.yaml)

    Patterns are organized by category (PARAMETER, CONNECTION, MIGRATION,
    CONFIGURATION, RUNTIME) and contain regex patterns, semantic features,
    and related solutions.

    Solutions are categorized (QUICK_FIX, CODE_REFACTORING, CONFIGURATION,
    ARCHITECTURE) and contain code examples, explanations, and metadata.

    Usage:
        kb = KnowledgeBase(
            patterns_path="patterns.yaml",
            solutions_path="solutions.yaml"
        )

        # Get pattern
        pattern = kb.get_pattern("PARAM_001")

        # Get solutions for pattern
        solutions = kb.get_solutions_for_pattern("PARAM_001")
    """

    def __init__(self, patterns_path: str, solutions_path: str):
        """Initialize KnowledgeBase and load YAML files.

        Args:
            patterns_path: Path to patterns.yaml file
            solutions_path: Path to solutions.yaml file

        Raises:
            FileNotFoundError: If YAML files don't exist
            yaml.YAMLError: If YAML files are malformed
        """
        self.patterns_path = patterns_path
        self.solutions_path = solutions_path
        self.patterns: Dict[str, Dict] = {}
        self.solutions: Dict[str, Dict] = {}
        self._load_patterns()
        self._load_solutions()

    def _load_patterns(self):
        """Load patterns from YAML file.

        Patterns structure:
            PARAM_001:
              name: "Missing Required Parameter 'id'"
              category: PARAMETER
              regex: ".*[Mm]issing.*'id'.*"
              semantic_features:
                error_type: [KeyError, ValueError]
                stacktrace_location: [CreateNode, UpdateNode]
              severity: high
              examples: [...]
              related_solutions: [SOL_001, SOL_002]

        Raises:
            FileNotFoundError: If patterns file doesn't exist
            yaml.YAMLError: If YAML is malformed
        """
        with open(self.patterns_path, "r") as f:
            all_data = yaml.safe_load(f)

        # Filter out metadata entry
        self.patterns = {k: v for k, v in all_data.items() if k != "metadata"}

    def _load_solutions(self):
        """Load solutions from YAML file.

        Solutions structure:
            SOL_001:
              title: "Add Missing 'id' Parameter"
              category: QUICK_FIX
              description: "Add required 'id' field"
              code_example: |
                workflow.add_node("UserCreateNode", "create", {
                    "id": "user-123",  # Required
                    "name": "Alice"
                })
              explanation: "..."
              references: [...]
              difficulty: easy
              estimated_time: 1

        Raises:
            FileNotFoundError: If solutions file doesn't exist
            yaml.YAMLError: If YAML is malformed
        """
        with open(self.solutions_path, "r") as f:
            all_data = yaml.safe_load(f)

        # Filter out metadata entry
        self.solutions = {k: v for k, v in all_data.items() if k != "metadata"}

    def get_pattern(self, pattern_id: str) -> Optional[Dict]:
        """Get pattern by ID.

        Args:
            pattern_id: Pattern identifier (e.g., "PARAM_001")

        Returns:
            Pattern dictionary or None if not found

        Example:
            >>> kb = KnowledgeBase("patterns.yaml", "solutions.yaml")
            >>> pattern = kb.get_pattern("PARAM_001")
            >>> pattern["name"]
            "Missing Required Parameter 'id'"
        """
        return self.patterns.get(pattern_id)

    def get_patterns_by_category(self, category: str) -> List[Dict]:
        """Get all patterns for a category.

        Args:
            category: Category name (PARAMETER, CONNECTION, MIGRATION,
                     CONFIGURATION, RUNTIME)

        Returns:
            List of pattern dictionaries with 'id' field added

        Example:
            >>> kb = KnowledgeBase("patterns.yaml", "solutions.yaml")
            >>> param_patterns = kb.get_patterns_by_category("PARAMETER")
            >>> len(param_patterns) >= 15
            True
        """
        return [
            {**pattern, "id": pid}
            for pid, pattern in self.patterns.items()
            if pattern.get("category") == category.upper()
        ]

    def get_solution(self, solution_id: str) -> Optional[Dict]:
        """Get solution by ID.

        Args:
            solution_id: Solution identifier (e.g., "SOL_001")

        Returns:
            Solution dictionary or None if not found

        Example:
            >>> kb = KnowledgeBase("patterns.yaml", "solutions.yaml")
            >>> solution = kb.get_solution("SOL_001")
            >>> solution["title"]
            "Add Missing 'id' Parameter to CreateNode"
        """
        return self.solutions.get(solution_id)

    def get_solutions_for_pattern(self, pattern_id: str) -> List[Dict]:
        """Get solutions for a pattern.

        Looks up the pattern and returns all solutions listed in the
        'related_solutions' field.

        Args:
            pattern_id: Pattern identifier (e.g., "PARAM_001")

        Returns:
            List of solution dictionaries with 'id' field added

        Example:
            >>> kb = KnowledgeBase("patterns.yaml", "solutions.yaml")
            >>> solutions = kb.get_solutions_for_pattern("PARAM_001")
            >>> len(solutions) > 0
            True
            >>> solutions[0]["category"] in ["QUICK_FIX", "CODE_REFACTORING"]
            True
        """
        pattern = self.get_pattern(pattern_id)
        if not pattern:
            return []

        solution_ids = pattern.get("related_solutions", [])
        return [
            {**self.solutions[sid], "id": sid}
            for sid in solution_ids
            if sid in self.solutions
        ]

    def reload_patterns(self):
        """Reload patterns from disk.

        Useful for updating patterns without restarting the application.

        Raises:
            FileNotFoundError: If patterns file doesn't exist
            yaml.YAMLError: If YAML is malformed
        """
        self._load_patterns()

    def reload_solutions(self):
        """Reload solutions from disk.

        Useful for updating solutions without restarting the application.

        Raises:
            FileNotFoundError: If solutions file doesn't exist
            yaml.YAMLError: If YAML is malformed
        """
        self._load_solutions()
