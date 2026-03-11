"""
Memory promotion from short-term to long-term storage.

Automatically promotes important short-term memories to long-term storage
based on access patterns, importance scores, and learning signals.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from kaizen.memory.long_term import LongTermMemory
from kaizen.memory.short_term import ShortTermMemory
from kaizen.memory.storage.base import MemoryEntry, MemoryType


class MemoryPromoter:
    """
    Promote memories from short-term to long-term storage.

    Features:
    - Automatic promotion based on access patterns
    - Importance-based promotion
    - Manual promotion triggers
    - Promotion history tracking

    Use cases:
    - Convert frequently accessed session data to persistent knowledge
    - Preserve important temporary information
    - Optimize memory hierarchy
    - Learn what information is valuable over time
    """

    def __init__(
        self,
        short_term_memory: ShortTermMemory,
        long_term_memory: LongTermMemory,
        access_threshold: int = 3,  # Min accesses for auto-promotion
        importance_threshold: float = 0.7,  # Min calculated importance
        age_threshold_hours: int = 24,  # Min age before considering promotion
    ):
        """
        Initialize memory promoter.

        Args:
            short_term_memory: Short-term memory instance
            long_term_memory: Long-term memory instance
            access_threshold: Minimum access count for promotion
            importance_threshold: Minimum importance score for promotion
            age_threshold_hours: Minimum age before promotion
        """
        self.short_term = short_term_memory
        self.long_term = long_term_memory
        self.access_threshold = access_threshold
        self.importance_threshold = importance_threshold
        self.age_threshold_hours = age_threshold_hours

    def auto_promote(self) -> Dict[str, int]:
        """
        Automatically promote qualifying short-term memories.

        Criteria for promotion:
        1. Access count >= access_threshold
        2. Calculated importance >= importance_threshold
        3. Age >= age_threshold_hours
        4. Not already expired

        Returns:
            Statistics about promotion
        """
        # Get short-term memories
        candidates = self.short_term.storage.list_entries(
            memory_type=MemoryType.SHORT_TERM, limit=1000
        )

        age_cutoff = datetime.now(timezone.utc) - timedelta(
            hours=self.age_threshold_hours
        )

        promoted_count = 0
        skipped_count = 0
        failed_count = 0

        for entry in candidates:
            # Check if entry meets promotion criteria
            if self._should_promote(entry, age_cutoff):
                try:
                    # Promote to long-term
                    self.promote_entry(entry.id)
                    promoted_count += 1
                except Exception:
                    failed_count += 1
            else:
                skipped_count += 1

        return {
            "promoted": promoted_count,
            "skipped": skipped_count,
            "failed": failed_count,
            "total_candidates": len(candidates),
        }

    def promote_entry(self, entry_id: str, override: bool = False) -> Optional[str]:
        """
        Promote a specific entry from short-term to long-term.

        Args:
            entry_id: ID of entry to promote
            override: Skip eligibility checks if True

        Returns:
            New long-term entry ID if promoted, None otherwise
        """
        # Retrieve from storage directly (bypass TTL for promotion eligibility)
        entry = self.short_term.storage.retrieve(entry_id)

        if entry is None:
            return None

        # Only consider short-term entries
        if entry.memory_type != MemoryType.SHORT_TERM:
            return None

        # Check eligibility unless override
        if not override:
            age_cutoff = datetime.now(timezone.utc) - timedelta(
                hours=self.age_threshold_hours
            )
            if not self._should_promote(entry, age_cutoff):
                return None

        # Calculate final importance for long-term storage
        calculated_importance = entry.calculate_importance()
        final_importance = max(entry.importance, calculated_importance)

        # Store in long-term
        new_id = self.long_term.store(
            content=entry.content,
            metadata={
                **entry.metadata,
                "promoted_from": "short_term",
                "promoted_at": datetime.now(timezone.utc).isoformat(),
                "original_id": entry_id,
                "original_access_count": entry.access_count,
            },
            importance=final_importance,
        )

        # Optionally remove from short-term
        # (keeping it allows TTL to clean up naturally)

        return new_id

    def promote_pattern(
        self, pattern_content: str, importance: float = 0.8
    ) -> Optional[str]:
        """
        Promote a recognized pattern to long-term memory.

        Args:
            pattern_content: Description of the pattern
            importance: Importance score for the pattern

        Returns:
            Long-term entry ID
        """
        return self.long_term.store(
            content=pattern_content,
            metadata={
                "source": "pattern_recognition",
                "promoted_at": datetime.now(timezone.utc).isoformat(),
            },
            importance=importance,
        )

    def promote_preference(self, preference_content: str, confidence: float) -> str:
        """
        Promote a learned preference to long-term memory.

        Args:
            preference_content: Preference description
            confidence: Confidence score (0.0-1.0)

        Returns:
            Long-term entry ID
        """
        return self.long_term.store(
            content=preference_content,
            metadata={
                "source": "preference_learning",
                "promoted_at": datetime.now(timezone.utc).isoformat(),
                "confidence": confidence,
            },
            importance=confidence,
        )

    def get_promotion_candidates(self, limit: int = 20) -> List[Dict]:
        """
        Get entries eligible for promotion.

        Args:
            limit: Maximum candidates to return

        Returns:
            List of promotion candidates with scores
        """
        candidates = self.short_term.storage.list_entries(
            memory_type=MemoryType.SHORT_TERM, limit=1000
        )

        age_cutoff = datetime.now(timezone.utc) - timedelta(
            hours=self.age_threshold_hours
        )

        eligible = []
        for entry in candidates:
            if entry.timestamp < age_cutoff:
                calculated_importance = entry.calculate_importance()

                # Calculate promotion score
                score = self._calculate_promotion_score(entry, calculated_importance)

                if calculated_importance >= self.importance_threshold:
                    eligible.append(
                        {
                            "entry_id": entry.id,
                            "content": entry.content[:100],  # Truncated
                            "access_count": entry.access_count,
                            "importance": entry.importance,
                            "calculated_importance": calculated_importance,
                            "promotion_score": score,
                            "age_hours": (
                                datetime.now(timezone.utc) - entry.timestamp
                            ).total_seconds()
                            / 3600,
                        }
                    )

        # Sort by promotion score
        eligible.sort(key=lambda x: x["promotion_score"], reverse=True)

        return eligible[:limit]

    def get_promotion_history(self, days: int = 7) -> List[Dict]:
        """
        Get history of promoted entries.

        Args:
            days: Days to look back

        Returns:
            List of promoted entries
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        entries = self.long_term.storage.list_entries(
            memory_type=MemoryType.LONG_TERM, limit=1000
        )

        # Filter to promoted entries
        promoted = []
        for entry in entries:
            if entry.metadata.get("promoted_from") and entry.timestamp >= cutoff:
                promoted.append(
                    {
                        "entry_id": entry.id,
                        "content": entry.content[:100],
                        "promoted_from": entry.metadata.get("promoted_from"),
                        "promoted_at": entry.metadata.get("promoted_at"),
                        "original_access_count": entry.metadata.get(
                            "original_access_count", 0
                        ),
                        "importance": entry.importance,
                    }
                )

        return promoted

    def _should_promote(self, entry: MemoryEntry, age_cutoff: datetime) -> bool:
        """
        Check if entry should be promoted.

        Args:
            entry: Memory entry to check
            age_cutoff: Minimum age for promotion

        Returns:
            True if entry should be promoted
        """
        # Age check
        if entry.timestamp > age_cutoff:
            return False

        # Access count check
        if entry.access_count < self.access_threshold:
            return False

        # Importance check
        calculated_importance = entry.calculate_importance()
        if calculated_importance < self.importance_threshold:
            return False

        return True

    def _calculate_promotion_score(
        self, entry: MemoryEntry, calculated_importance: float
    ) -> float:
        """
        Calculate promotion priority score.

        Args:
            entry: Memory entry
            calculated_importance: Pre-calculated importance

        Returns:
            Promotion score (0.0-1.0)
        """
        # Factors:
        # 1. Access count (normalized to 0-1, capped at 10)
        access_score = min(entry.access_count / 10, 1.0)

        # 2. Calculated importance
        importance_score = calculated_importance

        # 3. Age factor (older = higher priority, up to 7 days)
        age_days = (datetime.now(timezone.utc) - entry.timestamp).days
        age_score = min(age_days / 7, 1.0)

        # Weighted combination
        score = access_score * 0.4 + importance_score * 0.5 + age_score * 0.1

        return min(score, 1.0)

    def get_stats(self) -> Dict:
        """
        Get memory promotion statistics.

        Returns:
            Dictionary with statistics
        """
        candidates = self.get_promotion_candidates(limit=100)
        history = self.get_promotion_history(days=7)

        return {
            "eligible_candidates": len(candidates),
            "avg_promotion_score": (
                sum(c["promotion_score"] for c in candidates) / len(candidates)
                if candidates
                else 0.0
            ),
            "promoted_last_7_days": len(history),
            "access_threshold": self.access_threshold,
            "importance_threshold": self.importance_threshold,
            "age_threshold_hours": self.age_threshold_hours,
        }
