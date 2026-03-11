"""Error categorizer using pattern matching.

This module provides error categorization functionality that matches captured
errors against a database of 50+ patterns using regex and semantic features.
"""

import re
from dataclasses import dataclass
from typing import Any, Dict, List

from dataflow.debug.error_capture import CapturedError, StackFrame
from dataflow.debug.knowledge_base import KnowledgeBase


@dataclass
class ErrorCategory:
    """Categorized error with pattern match information.

    Attributes:
        category: Error category (PARAMETER, CONNECTION, MIGRATION,
                 CONFIGURATION, RUNTIME, UNKNOWN)
        pattern_id: Matched pattern identifier (e.g., "PARAM_001")
        confidence: Match confidence score (0.0-1.0)
        features: Extracted semantic features used for matching
    """

    category: str
    pattern_id: str
    confidence: float
    features: Dict[str, Any]


class ErrorCategorizer:
    """Categorizes errors using pattern matching.

    Uses a two-stage matching algorithm:
    1. Regex matching (50% weight) - Match error message against pattern regex
    2. Semantic matching (50% weight) - Match error_type, stacktrace location,
       and keyword overlap

    Patterns with combined score > 0.5 are candidates, and the highest scoring
    pattern is selected.

    Usage:
        kb = KnowledgeBase("patterns.yaml", "solutions.yaml")
        categorizer = ErrorCategorizer(kb)

        captured = error_capture.capture(exception)
        category = categorizer.categorize(captured)

        print(f"Category: {category.category}")
        print(f"Pattern: {category.pattern_id}")
        print(f"Confidence: {category.confidence:.2f}")
    """

    def __init__(self, knowledge_base: KnowledgeBase):
        """Initialize ErrorCategorizer with KnowledgeBase.

        Args:
            knowledge_base: KnowledgeBase instance with patterns loaded
        """
        self.knowledge_base = knowledge_base

    def categorize(self, error: CapturedError) -> ErrorCategory:
        """Categorize error using pattern matching.

        Matches error against all patterns using regex + semantic features,
        selects the best matching pattern (score > 0.5), and returns the
        error category.

        Args:
            error: Captured error to categorize

        Returns:
            ErrorCategory with matched pattern and confidence

        Example:
            >>> kb = KnowledgeBase("patterns.yaml", "solutions.yaml")
            >>> categorizer = ErrorCategorizer(kb)
            >>> error = CapturedError(
            ...     exception=ValueError("Missing 'id'"),
            ...     error_type="ValueError",
            ...     message="Missing required parameter 'id'",
            ...     stacktrace=[],
            ...     context={},
            ...     timestamp=datetime.now()
            ... )
            >>> category = categorizer.categorize(error)
            >>> category.category
            'PARAMETER'
            >>> category.confidence > 0.5
            True
        """
        # Extract semantic features
        features = self._extract_features(error)

        # Match against all patterns
        matches = []
        for pattern_id, pattern in self.knowledge_base.patterns.items():
            score = self._match_pattern(pattern_id, pattern, error, features)
            if score >= 0.5:  # Confidence threshold (>= allows pure regex matches)
                matches.append((pattern_id, pattern, score))

        # Select best match
        if not matches:
            return ErrorCategory(
                category="UNKNOWN",
                pattern_id="UNKNOWN",
                confidence=0.0,
                features=features,
            )

        best_pattern_id, best_pattern, confidence = max(matches, key=lambda x: x[2])

        return ErrorCategory(
            category=best_pattern["category"],
            pattern_id=best_pattern_id,
            confidence=confidence,
            features=features,
        )

    def _extract_features(self, error: CapturedError) -> Dict[str, Any]:
        """Extract semantic features for pattern matching.

        Features extracted:
        - error_type: Exception class name (e.g., "ValueError")
        - message_keywords: Key terms in error message (stop words removed)
        - stacktrace_location: Where error occurred (file:function)
        - parameter_names: Parameter names mentioned in error message
        - node_type: Type of node if from context (e.g., "CreateNode")
        - operation: CRUD operation if from context (e.g., "CREATE")

        Args:
            error: Captured error to extract features from

        Returns:
            Dictionary of extracted features

        Example:
            >>> features = categorizer._extract_features(captured_error)
            >>> features["error_type"]
            'ValueError'
            >>> "id" in features["parameter_names"]
            True
        """
        return {
            "error_type": error.error_type,
            "message_keywords": self._extract_keywords(error.message),
            "stacktrace_location": self._get_error_location(error.stacktrace),
            "parameter_names": self._extract_parameters(error),
            "node_type": error.context.get("node_type"),
            "operation": error.context.get("operation"),
        }

    def _match_pattern(
        self,
        pattern_id: str,
        pattern: Dict,
        error: CapturedError,
        features: Dict[str, Any],
    ) -> float:
        """Calculate match score for a pattern.

        Scoring algorithm:
        - Regex match: 0-0.5 (50% weight)
        - Semantic match: 0-0.5 (50% weight)
        - Total: 0-1.0

        Args:
            pattern_id: Pattern identifier (for logging)
            pattern: Pattern dictionary from KnowledgeBase
            error: Captured error to match
            features: Extracted features from error

        Returns:
            Match score (0.0-1.0)

        Example:
            >>> score = categorizer._match_pattern("PARAM_001", pattern, error, features)
            >>> 0.0 <= score <= 1.0
            True
        """
        # Regex match (50% weight)
        regex_score = self._calculate_regex_match_score(pattern, error)

        # Semantic match (50% weight)
        semantic_score = self._calculate_semantic_match_score(pattern, features)

        # Combined score
        return (regex_score * 0.5) + (semantic_score * 0.5)

    def _calculate_regex_match_score(
        self, pattern: Dict, error: CapturedError
    ) -> float:
        """Calculate regex match score.

        Matches error message against pattern regex. Returns 1.0 for match,
        0.0 for no match.

        Args:
            pattern: Pattern dictionary with 'regex' field
            error: Captured error with message

        Returns:
            1.0 if regex matches, 0.0 otherwise
        """
        regex_pattern = pattern.get("regex", "")
        if not regex_pattern:
            return 0.0

        # Extract innermost error message from nested exception chain
        inner_message = self._extract_inner_error_message(error.message)

        # Match against both full message and inner message (case insensitive)
        if re.search(regex_pattern, error.message, re.IGNORECASE):
            return 1.0

        if re.search(regex_pattern, inner_message, re.IGNORECASE):
            return 1.0

        return 0.0

    def _calculate_semantic_match_score(
        self, pattern: Dict, features: Dict[str, Any]
    ) -> float:
        """Calculate semantic match score.

        Checks semantic features against pattern:
        - error_type matches (33% of semantic score)
        - stacktrace_location matches (33% of semantic score)
        - keyword overlap (33% of semantic score)

        Args:
            pattern: Pattern dictionary with 'semantic_features' field
            features: Extracted features from error

        Returns:
            Semantic match score (0.0-1.0)

        Example:
            >>> pattern = {
            ...     "semantic_features": {
            ...         "error_type": ["ValueError", "KeyError"]
            ...     }
            ... }
            >>> features = {"error_type": "ValueError"}
            >>> score = categorizer._calculate_semantic_match_score(pattern, features)
            >>> score > 0.0
            True
        """
        score = 0.0
        checks = 0

        semantic_features_raw = pattern.get("semantic_features", {})

        # Convert list-of-dicts to flat dict if necessary
        # YAML structure: [{error_type: [...]}, {stacktrace_location: [...]}]
        # Target structure: {error_type: [...], stacktrace_location: [...]}
        if isinstance(semantic_features_raw, list):
            semantic_features = {}
            for item in semantic_features_raw:
                if isinstance(item, dict):
                    semantic_features.update(item)
        else:
            semantic_features = semantic_features_raw

        # Check error_type
        expected_error_types = semantic_features.get("error_type", [])
        if expected_error_types:
            checks += 1
            if features["error_type"] in expected_error_types:
                score += 1.0

        # Check stacktrace_location
        expected_locations = semantic_features.get("stacktrace_location", [])
        if expected_locations:
            checks += 1
            actual_location = features["stacktrace_location"]
            if any(loc in actual_location for loc in expected_locations):
                score += 1.0

        # Check keyword overlap (if we have message keywords)
        message_keywords = features.get("message_keywords", [])
        if message_keywords and expected_error_types:
            checks += 1
            # Check if any expected error types appear in keywords
            keyword_overlap = len(set(message_keywords) & set(expected_error_types))
            if keyword_overlap > 0:
                score += 1.0

        # Average score across all checks
        return score / checks if checks > 0 else 0.0

    def _extract_keywords(self, message: str) -> List[str]:
        """Extract keywords from error message.

        Removes common stop words and short words (<3 chars), returning
        meaningful terms from the error message.

        Args:
            message: Error message string

        Returns:
            List of keyword strings (lowercase, no stop words)

        Example:
            >>> keywords = categorizer._extract_keywords(
            ...     "Missing required parameter 'id' in CreateNode"
            ... )
            >>> "missing" in keywords
            True
            >>> "id" in keywords
            True
            >>> "the" in keywords  # Stop word removed
            False
        """
        # Common stop words to remove
        stop_words = {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "for",
            "to",
            "in",
            "of",
        }

        # Split message into words and clean
        words = re.findall(r"\w+", message.lower())
        keywords = [w for w in words if w not in stop_words and len(w) > 2]

        return keywords

    def _get_error_location(self, stacktrace: List[StackFrame]) -> str:
        """Get error location from stacktrace.

        Returns the location of the last frame (where error was raised) in
        format "filename:function_name".

        Args:
            stacktrace: List of stack frames

        Returns:
            Error location string, or empty string if no frames

        Example:
            >>> location = categorizer._get_error_location(stacktrace)
            >>> ":" in location
            True
            >>> location
            'workflow_builder.py:add_node'
        """
        if not stacktrace:
            return ""

        last_frame = stacktrace[-1]
        return f"{last_frame.filename}:{last_frame.function_name}"

    def _extract_parameters(self, error: CapturedError) -> List[str]:
        """Extract parameter names from error context and message.

        Looks for:
        - 'parameter_name' in error context
        - Parameters in quotes in error message (e.g., 'id', "name")

        Args:
            error: Captured error to extract parameters from

        Returns:
            List of unique parameter names

        Example:
            >>> params = categorizer._extract_parameters(error)
            >>> "id" in params
            True
        """
        params = []

        # From context
        if "parameter_name" in error.context:
            params.append(error.context["parameter_name"])

        # From message (e.g., "Missing required parameter 'id'")
        param_matches = re.findall(r"['\"](\w+)['\"]", error.message)
        params.extend(param_matches)

        return list(set(params))  # Unique parameters only

    def _extract_inner_error_message(self, message: str) -> str:
        """Extract innermost error message from nested exception chain.

        DataFlow errors often have nested exception structure:
            RuntimeExecutionError:
              └─ WorkflowExecutionError:
                  └─ ContentAwareExecutionError:
                      └─ "Database query failed: NOT NULL constraint failed: users.id"

        This method extracts the innermost error message for accurate pattern matching.

        Args:
            message: Full error message (may be nested)

        Returns:
            Innermost error message, or original if no nesting detected

        Example:
            >>> full_msg = "RuntimeExecutionError: Unified enterprise workflow execution failed: WorkflowExecutionError: Content-aware failure in node 'create': Node 'create' reported failure: Database query failed: NOT NULL constraint failed: users.id"
            >>> inner = categorizer._extract_inner_error_message(full_msg)
            >>> inner
            'NOT NULL constraint failed: users.id'
        """
        # Patterns to extract innermost error (ordered by priority)
        extraction_patterns = [
            # Pattern 1: "Database query failed: <actual error>"
            r"Database query failed:\s*(.+?)$",
            # Pattern 2: "Node 'X' reported failure: <actual error>"
            r"Node '.+?' reported failure:\s*(.+?)$",
            # Pattern 3: "Content-aware failure in node 'X': <actual error>"
            r"Content-aware failure in node '.+?':\s*(.+?)$",
            # Pattern 4: Last colon-separated segment (generic fallback)
            r":\s*([^:]+?)$",
        ]

        for pattern in extraction_patterns:
            match = re.search(pattern, message, re.IGNORECASE | re.DOTALL)
            if match:
                extracted = match.group(1).strip()
                # If extracted message is significantly shorter and not just whitespace
                if extracted and len(extracted) < len(message) * 0.8:
                    return extracted

        # No extraction pattern matched - return original message
        return message

    def get_category_statistics(self) -> Dict[str, int]:
        """Get error categorization statistics.

        Counts how many patterns exist for each category in the knowledge base.

        Returns:
            Dictionary mapping category name to pattern count

        Example:
            >>> stats = categorizer.get_category_statistics()
            >>> stats["PARAMETER"] >= 15
            True
            >>> stats["CONNECTION"] >= 10
            True
        """
        stats = {
            "PARAMETER": 0,
            "CONNECTION": 0,
            "MIGRATION": 0,
            "CONFIGURATION": 0,
            "RUNTIME": 0,
            "UNKNOWN": 0,
        }

        for pattern in self.knowledge_base.patterns.values():
            category = pattern.get("category", "UNKNOWN")
            if category in stats:
                stats[category] += 1

        return stats
