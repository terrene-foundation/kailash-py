"""Example 4: Custom Pattern and Solution

This example demonstrates how to add custom error patterns and solutions
for domain-specific errors.

Usage:
    python examples/debug_agent/04_custom_pattern_example.py
"""

from pathlib import Path

import yaml
from dataflow import DataFlow
from dataflow.debug.debug_agent import DebugAgent
from dataflow.debug.knowledge_base import KnowledgeBase
from dataflow.platform.inspector import Inspector


def create_custom_patterns():
    """Create custom patterns YAML file."""
    custom_patterns = {
        "CUSTOM_API_001": {
            "name": "API Request Timeout",
            "category": "RUNTIME",
            "regex": ".*[Aa]PI.*timeout.*|.*[Rr]equest.*timeout.*",
            "semantic_features": {
                "error_type": ["TimeoutError", "RequestTimeout"],
                "context": "api_request",
            },
            "severity": "high",
            "examples": [
                "TimeoutError: API request timed out after 30 seconds",
                "Request timeout: server did not respond",
            ],
            "related_solutions": ["CUSTOM_SOL_001", "CUSTOM_SOL_002"],
        },
        "CUSTOM_CACHE_001": {
            "name": "Cache Miss with Empty Result",
            "category": "CONFIGURATION",
            "regex": ".*[Cc]ache miss.*empty.*|.*[Nn]o data in cache.*",
            "semantic_features": {
                "error_type": ["CacheMissError", "ValueError"],
                "context": "cache_lookup",
            },
            "severity": "medium",
            "examples": [
                "CacheMissError: No data in cache for key 'user-123'",
                "Cache miss returned empty result",
            ],
            "related_solutions": ["CUSTOM_SOL_003"],
        },
    }

    # Load existing patterns
    patterns_file = Path("src/dataflow/debug/patterns.yaml")
    with open(patterns_file, "r") as f:
        patterns = yaml.safe_load(f)

    # Add custom patterns
    patterns.update(custom_patterns)

    # Save to custom file
    custom_file = Path("custom_patterns.yaml")
    with open(custom_file, "w") as f:
        yaml.dump(patterns, f, default_flow_style=False, sort_keys=False)

    return custom_file


def create_custom_solutions():
    """Create custom solutions YAML file."""
    custom_solutions = {
        "CUSTOM_SOL_001": {
            "id": "CUSTOM_SOL_001",
            "title": "Increase API Request Timeout",
            "category": "QUICK_FIX",
            "description": "Increase the timeout duration for API requests",
            "code_example": """# Increase timeout to 60 seconds
workflow.add_node("APIRequestNode", "request", {
    "url": "https://api.example.com/data",
    "timeout": 60  # Increase from default 30s
})""",
            "explanation": "API requests may take longer depending on server load. Increasing the timeout allows the request to complete.",
            "references": ["https://docs.example.com/api-timeout"],
            "difficulty": "easy",
            "estimated_time": 1,
            "prerequisites": [],
        },
        "CUSTOM_SOL_002": {
            "id": "CUSTOM_SOL_002",
            "title": "Add Retry Logic with Exponential Backoff",
            "category": "BEST_PRACTICE",
            "description": "Implement retry logic for transient API failures",
            "code_example": """# Add retry logic
workflow.add_node("APIRequestNode", "request", {
    "url": "https://api.example.com/data",
    "timeout": 30,
    "retry_count": 3,
    "retry_delay": 2,
    "retry_backoff": 2.0
})""",
            "explanation": "Retry logic handles transient network failures. Exponential backoff prevents overwhelming the server.",
            "references": ["https://docs.example.com/retry-logic"],
            "difficulty": "medium",
            "estimated_time": 5,
            "prerequisites": ["Understanding of exponential backoff"],
        },
        "CUSTOM_SOL_003": {
            "id": "CUSTOM_SOL_003",
            "title": "Implement Cache Fallback Strategy",
            "category": "BEST_PRACTICE",
            "description": "Add fallback to database when cache misses",
            "code_example": """# Cache fallback
try:
    result = cache.get(key)
except CacheMissError:
    # Fallback to database
    result = db.query(key)
    # Populate cache
    cache.set(key, result, ttl=300)""",
            "explanation": "Cache misses should fallback to the primary data source. This ensures data availability even when cache is empty.",
            "references": ["https://docs.example.com/cache-patterns"],
            "difficulty": "medium",
            "estimated_time": 10,
            "prerequisites": ["Understanding of caching patterns"],
        },
    }

    # Load existing solutions
    solutions_file = Path("src/dataflow/debug/solutions.yaml")
    with open(solutions_file, "r") as f:
        solutions = yaml.safe_load(f)

    # Add custom solutions
    solutions.update(custom_solutions)

    # Save to custom file
    custom_file = Path("custom_solutions.yaml")
    with open(custom_file, "w") as f:
        yaml.dump(solutions, f, default_flow_style=False, sort_keys=False)

    return custom_file


def main():
    """Custom pattern example."""
    print("=" * 80)
    print("Example 4: Custom Pattern and Solution")
    print("=" * 80)
    print()

    # Create custom patterns and solutions
    print("Creating custom patterns...")
    patterns_file = create_custom_patterns()
    print(f"✓ Created: {patterns_file}")

    print("Creating custom solutions...")
    solutions_file = create_custom_solutions()
    print(f"✓ Created: {solutions_file}")
    print()

    # Initialize DataFlow
    db = DataFlow(":memory:")

    # Initialize Debug Agent with custom patterns/solutions
    kb = KnowledgeBase(str(patterns_file), str(solutions_file))
    inspector = Inspector(db)
    agent = DebugAgent(kb, inspector)

    # Test Case 1: Custom API timeout error
    print("Test Case 1: Custom API Timeout Error")
    print("-" * 80)

    api_timeout_error = TimeoutError("API request timed out after 30 seconds")
    report1 = agent.debug(api_timeout_error, max_solutions=3, min_relevance=0.0)

    print(f"Category: {report1.error_category.category}")
    print(f"Pattern ID: {report1.error_category.pattern_id}")
    print(f"Confidence: {report1.error_category.confidence * 100:.0f}%")
    print(f"Root Cause: {report1.analysis_result.root_cause}")
    print(f"Solutions: {len(report1.suggested_solutions)}")

    if report1.suggested_solutions:
        print()
        print("Top Solution:")
        top = report1.suggested_solutions[0]
        print(f"  {top.title} ({top.category})")
        print(f"  Relevance: {top.relevance_score * 100:.0f}%")
        print(f"  Difficulty: {top.difficulty}")
        print(f"  Time: {top.estimated_time} min")
    print()

    # Test Case 2: Custom cache miss error
    print("Test Case 2: Custom Cache Miss Error")
    print("-" * 80)

    class CacheMissError(Exception):
        pass

    cache_error = CacheMissError("No data in cache for key 'user-123'")
    report2 = agent.debug_from_string(
        str(cache_error),
        error_type="CacheMissError",
        max_solutions=3,
        min_relevance=0.0,
    )

    print(f"Category: {report2.error_category.category}")
    print(f"Pattern ID: {report2.error_category.pattern_id}")
    print(f"Confidence: {report2.error_category.confidence * 100:.0f}%")
    print(f"Solutions: {len(report2.suggested_solutions)}")
    print()

    # Cleanup
    patterns_file.unlink()
    solutions_file.unlink()

    print("Custom pattern example complete!")


if __name__ == "__main__":
    main()
