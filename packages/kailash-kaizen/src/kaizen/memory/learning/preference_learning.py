"""
Preference learning from user interactions.

Learns user preferences from interaction patterns, feedback, and behavior
to personalize responses and improve user experience.
"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from kaizen.memory.storage.base import MemoryEntry, MemoryType, StorageBackend


class PreferenceLearner:
    """
    Learn and track user preferences from interactions.

    Features:
    - Preference extraction from feedback
    - Behavior pattern analysis
    - Preference consolidation
    - Preference confidence scoring

    Use cases:
    - Personalized response generation
    - Content recommendation
    - User profiling
    - Adaptive user experience
    """

    def __init__(
        self,
        storage: StorageBackend,
        confidence_threshold: float = 0.6,  # Minimum confidence for preferences
        min_evidence: int = 2,  # Minimum interactions to establish preference
    ):
        """
        Initialize preference learner.

        Args:
            storage: Storage backend for preferences
            confidence_threshold: Minimum confidence to consider preference established
            min_evidence: Minimum number of interactions to establish preference
        """
        self.storage = storage
        self.confidence_threshold = confidence_threshold
        self.min_evidence = min_evidence

    def learn_from_feedback(
        self, content: str, feedback: str, feedback_type: str = "positive"
    ) -> str:
        """
        Learn preference from user feedback.

        Args:
            content: The content that received feedback
            feedback: User's feedback text
            feedback_type: Type of feedback ('positive', 'negative', 'neutral')

        Returns:
            Preference entry ID
        """
        # Extract preference from feedback
        preference = self._extract_preference(content, feedback, feedback_type)

        # Store as preference memory
        entry = MemoryEntry(
            content=preference,
            memory_type=MemoryType.PREFERENCE,
            metadata={
                "feedback_type": feedback_type,
                "source": "feedback",
                "original_content": content[:200],  # Store truncated original
                "feedback_text": feedback[:200],
            },
            importance=0.8 if feedback_type == "positive" else 0.6,
        )

        return self.storage.store(entry)

    def learn_from_behavior(self, action: str, context: Dict) -> Optional[str]:
        """
        Learn preference from user behavior.

        Args:
            action: User action (e.g., 'selected', 'ignored', 'requested')
            context: Context information (content, timing, etc.)

        Returns:
            Preference entry ID if preference detected, None otherwise
        """
        # Detect preference signals in behavior
        preference = self._extract_behavior_preference(action, context)

        if not preference:
            return None

        # Store as preference memory
        entry = MemoryEntry(
            content=preference,
            memory_type=MemoryType.PREFERENCE,
            metadata={
                "action": action,
                "source": "behavior",
                "context": context,
            },
            importance=0.7,
        )

        return self.storage.store(entry)

    def get_preferences(
        self, category: Optional[str] = None, limit: int = 20
    ) -> List[Dict]:
        """
        Get learned user preferences.

        Args:
            category: Filter by category (optional)
            limit: Maximum preferences to return

        Returns:
            List of preferences with confidence scores
        """
        # Get all preference entries
        entries = self.storage.list_entries(
            memory_type=MemoryType.PREFERENCE, limit=1000
        )

        # Group by preference content for consolidation
        preference_groups = defaultdict(list)
        for entry in entries:
            # Extract preference key (first few words)
            key = self._get_preference_key(entry.content)
            preference_groups[key].append(entry)

        # Calculate confidence scores
        preferences = []
        for key, group in preference_groups.items():
            if len(group) >= self.min_evidence:
                # Calculate confidence based on:
                # 1. Number of supporting entries
                # 2. Recency of evidence
                # 3. Importance scores
                confidence = self._calculate_confidence(group)

                if confidence >= self.confidence_threshold:
                    # Find most recent representative entry
                    representative = max(group, key=lambda e: e.timestamp)

                    preference = {
                        "preference": representative.content,
                        "confidence": confidence,
                        "evidence_count": len(group),
                        "first_seen": min(e.timestamp for e in group),
                        "last_seen": max(e.timestamp for e in group),
                        "sources": list(
                            set(e.metadata.get("source", "unknown") for e in group)
                        ),
                        "category": category or "general",
                    }
                    preferences.append(preference)

        # Sort by confidence
        preferences.sort(key=lambda x: x["confidence"], reverse=True)

        return preferences[:limit]

    def update_preference(
        self, preference: str, reinforcement: bool = True, strength: float = 0.1
    ) -> None:
        """
        Update existing preference strength.

        Args:
            preference: Preference text to update
            reinforcement: True to strengthen, False to weaken
            strength: Amount to adjust (0.0-1.0)
        """
        # Find matching preference entries
        entries = self.storage.list_entries(
            memory_type=MemoryType.PREFERENCE, limit=1000
        )
        key = self._get_preference_key(preference)

        for entry in entries:
            entry_key = self._get_preference_key(entry.content)
            if entry_key == key:
                # Update importance
                if reinforcement:
                    entry.importance = min(1.0, entry.importance + strength)
                else:
                    entry.importance = max(0.0, entry.importance - strength)

                self.storage.update(entry)

    def consolidate_preferences(self) -> Dict[str, int]:
        """
        Consolidate similar preferences.

        Merges duplicate or conflicting preferences, keeping the strongest.

        Returns:
            Statistics about consolidation
        """
        entries = self.storage.list_entries(
            memory_type=MemoryType.PREFERENCE, limit=1000
        )

        # Group by preference key
        groups = defaultdict(list)
        for entry in entries:
            key = self._get_preference_key(entry.content)
            groups[key].append(entry)

        merged_count = 0
        conflicting_count = 0

        for key, group in groups.items():
            if len(group) > 1:
                # Sort by importance
                group.sort(key=lambda e: e.importance, reverse=True)

                # Keep strongest, delete others
                strongest = group[0]

                # Update strongest with consolidated metadata
                all_sources = set()
                for e in group:
                    all_sources.add(e.metadata.get("source", "unknown"))

                strongest.metadata["sources"] = list(all_sources)
                strongest.metadata["consolidated_count"] = len(group)
                self.storage.update(strongest)

                # Delete weaker duplicates
                for entry in group[1:]:
                    self.storage.delete(entry.id)
                    merged_count += 1

        return {
            "total_groups": len(groups),
            "merged_preferences": merged_count,
            "conflicting_preferences": conflicting_count,
            "unique_preferences": len(groups),
        }

    def detect_preference_drift(self, days: int = 30) -> List[Dict]:
        """
        Detect changes in user preferences over time.

        Args:
            days: Days to look back

        Returns:
            List of preference changes detected
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        entries = self.storage.list_entries(
            memory_type=MemoryType.PREFERENCE, limit=1000
        )

        # Split into old and recent
        old_entries = [e for e in entries if e.timestamp < cutoff]
        recent_entries = [e for e in entries if e.timestamp >= cutoff]

        # Group both by preference key
        old_prefs = defaultdict(list)
        recent_prefs = defaultdict(list)

        for entry in old_entries:
            old_prefs[self._get_preference_key(entry.content)].append(entry)

        for entry in recent_entries:
            recent_prefs[self._get_preference_key(entry.content)].append(entry)

        # Detect changes
        changes = []

        # New preferences
        for key in recent_prefs:
            if key not in old_prefs:
                changes.append(
                    {
                        "type": "new",
                        "preference": recent_prefs[key][0].content,
                        "confidence": self._calculate_confidence(recent_prefs[key]),
                    }
                )

        # Abandoned preferences
        for key in old_prefs:
            if key not in recent_prefs:
                changes.append(
                    {
                        "type": "abandoned",
                        "preference": old_prefs[key][0].content,
                        "last_seen": max(e.timestamp for e in old_prefs[key]),
                    }
                )

        # Changed preferences
        for key in set(old_prefs.keys()) & set(recent_prefs.keys()):
            old_conf = self._calculate_confidence(old_prefs[key])
            new_conf = self._calculate_confidence(recent_prefs[key])

            if abs(new_conf - old_conf) > 0.2:  # Significant change
                changes.append(
                    {
                        "type": "changed",
                        "preference": recent_prefs[key][0].content,
                        "old_confidence": old_conf,
                        "new_confidence": new_conf,
                        "direction": (
                            "strengthened" if new_conf > old_conf else "weakened"
                        ),
                    }
                )

        return changes

    def _extract_preference(
        self, content: str, feedback: str, feedback_type: str
    ) -> str:
        """Extract preference statement from feedback."""
        if feedback_type == "positive":
            return f"User prefers: {feedback}"
        elif feedback_type == "negative":
            return f"User dislikes: {feedback}"
        else:
            return f"User feedback: {feedback}"

    def _extract_behavior_preference(self, action: str, context: Dict) -> Optional[str]:
        """Extract preference from behavior pattern."""
        # Simple heuristics for behavior-based preferences
        if action == "selected":
            return f"User prefers: {context.get('content_type', 'unknown')}"
        elif action == "ignored":
            return f"User ignores: {context.get('content_type', 'unknown')}"
        elif action == "requested":
            return f"User requests: {context.get('feature', 'unknown')}"
        else:
            return None

    def _get_preference_key(self, content: str) -> str:
        """Get normalized preference key for grouping."""
        # Extract first 5 words as key (simplified)
        words = content.lower().split()[:5]
        return " ".join(words)

    def _calculate_confidence(self, entries: List[MemoryEntry]) -> float:
        """
        Calculate confidence score for a preference.

        Based on:
        - Number of supporting entries
        - Recency of evidence
        - Average importance
        """
        if not entries:
            return 0.0

        # Evidence count factor (more evidence = higher confidence)
        evidence_factor = min(len(entries) / 10, 1.0)  # Cap at 10 entries

        # Recency factor (recent evidence = higher confidence)
        recent_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        recent_count = sum(1 for e in entries if e.timestamp >= recent_cutoff)
        recency_factor = recent_count / len(entries)

        # Importance factor
        importance_factor = sum(e.importance for e in entries) / len(entries)

        # Combined confidence
        confidence = (
            evidence_factor * 0.3 + recency_factor * 0.3 + importance_factor * 0.4
        )

        return min(confidence, 1.0)

    def get_stats(self) -> Dict:
        """
        Get preference learning statistics.

        Returns:
            Dictionary with statistics
        """
        entries = self.storage.list_entries(
            memory_type=MemoryType.PREFERENCE, limit=1000
        )

        # Count by source
        sources = defaultdict(int)
        for entry in entries:
            source = entry.metadata.get("source", "unknown")
            sources[source] += 1

        # Calculate average confidence
        preferences = self.get_preferences(limit=100)
        avg_confidence = (
            sum(p["confidence"] for p in preferences) / len(preferences)
            if preferences
            else 0.0
        )

        return {
            "total_preference_entries": len(entries),
            "unique_preferences": len(preferences),
            "avg_confidence": avg_confidence,
            "sources": dict(sources),
            "confidence_threshold": self.confidence_threshold,
            "min_evidence": self.min_evidence,
        }
