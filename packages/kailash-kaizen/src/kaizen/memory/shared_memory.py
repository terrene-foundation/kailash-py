"""
SharedMemoryPool: Shared insight storage for multi-agent collaboration.

This module provides a shared memory pool where multiple agents can write
insights (observations, findings, context) and read insights from other agents.
This enables multi-agent collaboration without tight coupling.

Insight Format:
    {
        "agent_id": str,           # Which agent wrote this insight
        "content": str,            # The insight content
        "tags": List[str],         # Topic tags (e.g., ["customer", "complaint"])
        "importance": float,       # 0.0-1.0 (relevance score)
        "segment": str,            # Phase/segment (e.g., "analysis", "planning")
        "timestamp": str,          # ISO timestamp
        "metadata": Dict[str, Any] # Additional context (optional)
    }

Example Usage:
    >>> pool = SharedMemoryPool()
    >>>
    >>> # Agent 1 writes an insight
    >>> pool.write_insight({
    ...     "agent_id": "analyzer",
    ...     "content": "Customer complaint about delayed shipping",
    ...     "tags": ["customer", "complaint", "shipping"],
    ...     "importance": 0.9,
    ...     "segment": "analysis"
    ... })
    >>>
    >>> # Agent 2 reads all insights
    >>> insights = pool.read_all()

Author: Kaizen Framework Team
Created: 2025-10-02 (Week 3, Phase 2: Shared Memory)
Reference: Inspired by Core SDK A2A memory pattern (adapted for Kaizen)
"""

from collections import Counter
from datetime import datetime, timedelta
from threading import Lock
from typing import Any, Dict, List, Optional


class SharedMemoryPool:
    """
    Shared insight storage for multi-agent collaboration.

    Provides a shared pool where multiple agents can write insights and
    read relevant insights from other agents. Supports filtering by tags,
    importance, segments, age, and agent ownership.

    Thread-safe for concurrent agent access.
    """

    def __init__(self):
        """
        Initialize an empty shared memory pool.

        The pool is thread-safe and can be safely accessed by multiple
        agents concurrently.
        """
        self._insights: List[Dict[str, Any]] = []
        self._lock = Lock()  # Thread-safety for concurrent agents

    def write_insight(self, insight: Dict[str, Any]) -> None:
        """
        Write an insight to the shared pool.

        Validates that all required fields are present and within valid ranges.
        Auto-generates timestamp if not provided.

        Args:
            insight: Dictionary containing insight data with required fields:
                - agent_id: str (required) - Which agent wrote this
                - content: str (required) - The insight content
                - tags: List[str] (required) - Topic tags
                - importance: float (required) - 0.0-1.0 relevance score
                - segment: str (required) - Phase/segment identifier
                - timestamp: str (optional) - ISO timestamp (auto-generated if missing)
                - metadata: Dict[str, Any] (optional) - Additional context

        Raises:
            ValueError: If required fields are missing or invalid

        Example:
            >>> pool.write_insight({
            ...     "agent_id": "analyzer",
            ...     "content": "High-priority issue detected",
            ...     "tags": ["customer", "urgent"],
            ...     "importance": 0.9,
            ...     "segment": "analysis"
            ... })
        """
        # Validate required fields
        if "agent_id" not in insight:
            raise ValueError("Insight must have 'agent_id' field")
        if "content" not in insight:
            raise ValueError("Insight must have 'content' field")
        if "tags" not in insight:
            raise ValueError("Insight must have 'tags' field")
        if "importance" not in insight:
            raise ValueError("Insight must have 'importance' field")
        if "segment" not in insight:
            raise ValueError("Insight must have 'segment' field")

        # Validate importance range
        importance = insight["importance"]
        if not (0.0 <= importance <= 1.0):
            raise ValueError(
                f"Insight importance must be between 0 and 1, got {importance}"
            )

        # Auto-generate timestamp if missing
        if "timestamp" not in insight:
            insight = insight.copy()  # Don't modify original
            insight["timestamp"] = datetime.now().isoformat()

        # Thread-safe append
        with self._lock:
            self._insights.append(insight)

    def read_all(self) -> List[Dict[str, Any]]:
        """
        Read all insights from the pool.

        Returns a copy of the insights list to prevent external modification
        of the internal state.

        Returns:
            List of all insights in the pool (copy, not reference)

        Example:
            >>> insights = pool.read_all()
            >>> print(f"Found {len(insights)} insights")
        """
        with self._lock:
            return self._insights.copy()

    def read_relevant(
        self,
        agent_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        min_importance: Optional[float] = None,
        segments: Optional[List[str]] = None,
        max_age_seconds: Optional[float] = None,
        exclude_own: bool = True,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Read relevant insights with filtering.

        Applies multiple filters in sequence:
        1. Exclude own insights (if exclude_own=True and agent_id provided)
        2. Filter by tags (ANY match)
        3. Filter by importance threshold
        4. Filter by segments (ANY match)
        5. Filter by age
        6. Sort by importance (descending) then timestamp (descending)
        7. Apply limit

        Args:
            agent_id: Current agent's ID (for exclude_own)
            tags: Filter by tags (keeps insights with ANY matching tag)
            min_importance: Minimum importance threshold (inclusive)
            segments: Filter by segments (keeps insights with matching segment)
            max_age_seconds: Maximum age in seconds (from now)
            exclude_own: If True, exclude insights from agent_id
            limit: Maximum number of insights to return (most relevant first)

        Returns:
            List of filtered insights, sorted by relevance

        Example:
            >>> # Get top 5 customer-related insights from other agents
            >>> insights = pool.read_relevant(
            ...     agent_id="responder",
            ...     tags=["customer"],
            ...     min_importance=0.7,
            ...     exclude_own=True,
            ...     limit=5
            ... )
        """
        with self._lock:
            filtered = self._insights.copy()

        # Filter 1: Exclude own insights
        if exclude_own and agent_id:
            filtered = [i for i in filtered if i.get("agent_id") != agent_id]

        # Filter 2: Tag filtering (ANY match)
        if tags:
            filtered = [
                i for i in filtered if any(tag in i.get("tags", []) for tag in tags)
            ]

        # Filter 3: Importance filtering
        if min_importance is not None:
            filtered = [i for i in filtered if i.get("importance", 0) >= min_importance]

        # Filter 4: Segment filtering (ANY match)
        if segments:
            filtered = [i for i in filtered if i.get("segment") in segments]

        # Filter 5: Age filtering
        if max_age_seconds is not None:
            cutoff = datetime.now() - timedelta(seconds=max_age_seconds)
            filtered = [
                i for i in filtered if datetime.fromisoformat(i["timestamp"]) >= cutoff
            ]

        # Sort by importance (descending), then timestamp (descending)
        filtered.sort(
            key=lambda i: (i.get("importance", 0), i.get("timestamp", "")), reverse=True
        )

        # Apply limit
        if limit:
            filtered = filtered[:limit]

        return filtered

    def clear(self) -> None:
        """
        Clear all insights from the pool.

        Thread-safe operation that removes all insights.

        Example:
            >>> pool.clear()
            >>> assert len(pool.read_all()) == 0
        """
        with self._lock:
            self._insights.clear()

    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the pool.

        Returns:
            Dictionary with statistics:
            - insight_count: Total number of insights
            - agent_count: Number of unique agents
            - tag_distribution: Count of each tag
            - segment_distribution: Count of each segment

        Example:
            >>> stats = pool.get_stats()
            >>> print(f"Insights: {stats['insight_count']}")
            >>> print(f"Agents: {stats['agent_count']}")
            >>> print(f"Tags: {stats['tag_distribution']}")
        """
        with self._lock:
            insights = self._insights.copy()

        if not insights:
            return {
                "insight_count": 0,
                "agent_count": 0,
                "tag_distribution": {},
                "segment_distribution": {},
            }

        # Count unique agents
        agents = set(i.get("agent_id") for i in insights)

        # Count tag occurrences
        all_tags = []
        for insight in insights:
            all_tags.extend(insight.get("tags", []))
        tag_distribution = dict(Counter(all_tags))

        # Count segment occurrences
        all_segments = [i.get("segment") for i in insights]
        segment_distribution = dict(Counter(all_segments))

        return {
            "insight_count": len(insights),
            "agent_count": len(agents),
            "tag_distribution": tag_distribution,
            "segment_distribution": segment_distribution,
        }
