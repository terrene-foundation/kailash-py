"""
Pattern recognition for detecting repeated queries and FAQ patterns.

Detects common questions, repeated patterns, and frequently accessed information
to optimize memory retrieval and suggest FAQ entries.
"""

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from kaizen.memory.storage.base import MemoryEntry, MemoryType, StorageBackend


class PatternRecognizer:
    """
    Detect and track patterns in memory usage.

    Features:
    - FAQ detection (frequently asked questions)
    - Pattern clustering (similar queries)
    - Access pattern analysis
    - Temporal pattern detection

    Use cases:
    - Suggest FAQ entries for repeated questions
    - Optimize retrieval with pattern-based caching
    - Detect user behavior patterns
    - Identify trending topics
    """

    def __init__(
        self,
        storage: StorageBackend,
        min_frequency: int = 3,  # Minimum occurrences to be a pattern
        time_window_days: int = 7,  # Look back window
        similarity_threshold: float = 0.8,  # For pattern clustering
    ):
        """
        Initialize pattern recognizer.

        Args:
            storage: Storage backend for retrieving entries
            min_frequency: Minimum occurrences to detect as pattern
            time_window_days: Days to look back for patterns
            similarity_threshold: Minimum similarity for pattern clustering
        """
        self.storage = storage
        self.min_frequency = min_frequency
        self.time_window_days = time_window_days
        self.similarity_threshold = similarity_threshold

    def detect_faqs(self, limit: int = 10) -> List[Dict]:
        """
        Detect frequently asked questions from memory.

        Analyzes access patterns and content similarity to identify
        questions that are asked repeatedly.

        Args:
            limit: Maximum number of FAQs to return

        Returns:
            List of FAQ patterns with frequency, example queries, and suggested answers
        """
        # Get entries from time window
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=self.time_window_days)
        entries = self.storage.list_entries(limit=10000)

        # Filter to time window and high access count
        recent_entries = [
            e
            for e in entries
            if e.timestamp >= cutoff_date and e.access_count >= self.min_frequency
        ]

        # Group by content similarity (simple word-based clustering)
        patterns = self._cluster_by_content(recent_entries)

        # Create FAQ entries
        faqs = []
        for pattern_key, cluster in patterns.items():
            if len(cluster) >= self.min_frequency:
                # Calculate total access frequency
                total_accesses = sum(e.access_count for e in cluster)

                # Find most accessed entry as representative
                representative = max(cluster, key=lambda e: e.access_count)

                faq = {
                    "pattern": pattern_key,
                    "frequency": len(cluster),
                    "total_accesses": total_accesses,
                    "example_query": representative.content,
                    "entries": [e.id for e in cluster],
                    "avg_importance": sum(e.importance for e in cluster) / len(cluster),
                    "first_seen": min(e.timestamp for e in cluster),
                    "last_seen": max(e.timestamp for e in cluster),
                }
                faqs.append(faq)

        # Sort by frequency and total accesses
        faqs.sort(key=lambda x: (x["frequency"], x["total_accesses"]), reverse=True)

        return faqs[:limit]

    def detect_access_patterns(self) -> Dict[str, List[MemoryEntry]]:
        """
        Detect temporal access patterns.

        Identifies:
        - Frequently accessed entries
        - Recently trending entries
        - Abandoned entries (high initial access, now dormant)

        Returns:
            Dictionary with 'frequent', 'trending', 'abandoned' keys
        """
        entries = self.storage.list_entries(limit=10000)

        # Frequent: High total access count
        frequent = sorted(entries, key=lambda e: e.access_count, reverse=True)[:20]

        # Trending: High access count + recent last_accessed
        cutoff = datetime.now(timezone.utc) - timedelta(days=2)
        trending = [
            e
            for e in entries
            if e.last_accessed and e.last_accessed >= cutoff and e.access_count >= 2
        ]
        trending.sort(key=lambda e: e.access_count, reverse=True)

        # Abandoned: Old entries with high access count but not accessed recently
        old_cutoff = datetime.now(timezone.utc) - timedelta(days=self.time_window_days)
        abandoned = [
            e
            for e in entries
            if e.access_count >= self.min_frequency
            and (not e.last_accessed or e.last_accessed < old_cutoff)
        ]
        abandoned.sort(key=lambda e: e.access_count, reverse=True)

        return {
            "frequent": frequent[:10],
            "trending": trending[:10],
            "abandoned": abandoned[:10],
        }

    def suggest_consolidation(self) -> List[Dict]:
        """
        Suggest entries that should be consolidated or promoted.

        Identifies entries that:
        - Are frequently accessed (candidates for long-term storage)
        - Have similar content (candidates for merging)
        - Are duplicates (candidates for deduplication)

        Returns:
            List of consolidation suggestions
        """
        entries = self.storage.list_entries(
            memory_type=MemoryType.SHORT_TERM, limit=1000
        )

        suggestions = []

        # Find frequently accessed short-term memories (promotion candidates)
        for entry in entries:
            if entry.access_count >= self.min_frequency:
                calculated_importance = entry.calculate_importance()
                if calculated_importance >= 0.6:  # High importance threshold
                    suggestions.append(
                        {
                            "action": "promote_to_long_term",
                            "entry_id": entry.id,
                            "reason": f"High access count ({entry.access_count}) and importance ({calculated_importance:.2f})",
                            "importance": calculated_importance,
                            "access_count": entry.access_count,
                        }
                    )

        # Sort by importance
        suggestions.sort(key=lambda x: x["importance"], reverse=True)

        return suggestions

    def analyze_query_patterns(self, queries: List[str]) -> Dict:
        """
        Analyze a list of queries for patterns.

        Args:
            queries: List of query strings to analyze

        Returns:
            Dictionary with pattern statistics
        """
        # Extract keywords (simple word-based analysis)
        word_freq = Counter()
        for query in queries:
            words = query.lower().split()
            word_freq.update(words)

        # Find common patterns
        common_words = word_freq.most_common(20)

        # Detect question patterns
        question_words = ["what", "how", "why", "when", "where", "who", "which"]
        question_count = sum(
            1 for q in queries if any(qw in q.lower() for qw in question_words)
        )

        return {
            "total_queries": len(queries),
            "unique_queries": len(set(queries)),
            "question_queries": question_count,
            "common_keywords": common_words,
            "repetition_rate": 1 - (len(set(queries)) / len(queries)) if queries else 0,
        }

    def _cluster_by_content(
        self, entries: List[MemoryEntry]
    ) -> Dict[str, List[MemoryEntry]]:
        """
        Cluster entries by content similarity.

        Simple word-based clustering using keyword overlap.

        Args:
            entries: List of memory entries

        Returns:
            Dictionary mapping pattern key to list of similar entries
        """
        clusters = defaultdict(list)

        for entry in entries:
            # Extract key words (simple: most common words)
            words = entry.content.lower().split()
            # Use first 3 unique words as pattern key (simplified)
            key_words = sorted(set(words))[:3]
            pattern_key = " ".join(key_words)

            clusters[pattern_key].append(entry)

        return dict(clusters)

    def get_stats(self) -> Dict:
        """
        Get pattern recognition statistics.

        Returns:
            Dictionary with statistics
        """
        entries = self.storage.list_entries(limit=10000)
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.time_window_days)
        recent = [e for e in entries if e.timestamp >= cutoff]

        return {
            "total_entries": len(entries),
            "recent_entries": len(recent),
            "time_window_days": self.time_window_days,
            "min_frequency": self.min_frequency,
            "avg_access_count": (
                sum(e.access_count for e in entries) / len(entries) if entries else 0
            ),
            "highly_accessed": len(
                [e for e in entries if e.access_count >= self.min_frequency]
            ),
        }
