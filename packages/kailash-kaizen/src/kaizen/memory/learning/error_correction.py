"""
Error correction learning from mistakes and failures.

Learns from errors and their corrections to prevent repeated mistakes
and suggest preventive measures.
"""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from kaizen.memory.storage.base import MemoryEntry, MemoryType, StorageBackend


class ErrorCorrectionLearner:
    """
    Learn from errors and their corrections.

    Features:
    - Error pattern detection
    - Correction effectiveness tracking
    - Preventive measure suggestions
    - Error recurrence detection

    Use cases:
    - Prevent repeated mistakes
    - Suggest fixes for known errors
    - Track error resolution success rates
    - Build error knowledge base
    """

    def __init__(
        self,
        storage: StorageBackend,
        recurrence_threshold: int = 2,  # Threshold for flagging recurring errors
        effectiveness_threshold: float = 0.7,  # Min success rate for suggested corrections
    ):
        """
        Initialize error correction learner.

        Args:
            storage: Storage backend for error memories
            recurrence_threshold: Minimum occurrences to flag as recurring error
            effectiveness_threshold: Minimum success rate for correction suggestions
        """
        self.storage = storage
        self.recurrence_threshold = recurrence_threshold
        self.effectiveness_threshold = effectiveness_threshold

    def record_error(
        self,
        error_description: str,
        context: Dict,
        severity: str = "medium",
        error_type: Optional[str] = None,
    ) -> str:
        """
        Record an error occurrence.

        Args:
            error_description: Description of the error
            context: Context information (inputs, state, etc.)
            severity: Error severity ('low', 'medium', 'high', 'critical')
            error_type: Type/category of error (optional)

        Returns:
            Error entry ID
        """
        # Extract error signature for pattern matching
        error_signature = self._extract_error_signature(error_description, error_type)

        # Store as error memory
        entry = MemoryEntry(
            content=error_description,
            memory_type=MemoryType.ERROR,
            metadata={
                "error_signature": error_signature,
                "error_type": error_type or "unknown",
                "severity": severity,
                "context": context,
                "corrected": False,
                "correction_attempts": 0,
            },
            importance=self._severity_to_importance(severity),
        )

        return self.storage.store(entry)

    def record_correction(
        self,
        error_id: str,
        correction: str,
        successful: bool = True,
        time_to_fix_seconds: Optional[float] = None,
    ) -> Optional[str]:
        """
        Record a correction for an error.

        Args:
            error_id: ID of the error being corrected
            correction: Description of the correction applied
            successful: Whether the correction resolved the error
            time_to_fix_seconds: Time taken to fix the error

        Returns:
            Correction entry ID, or None if error not found
        """
        # Retrieve original error
        error_entry = self.storage.retrieve(error_id)
        if error_entry is None:
            return None

        # Update error entry
        error_entry.metadata["corrected"] = successful
        error_entry.metadata["correction_attempts"] += 1
        error_entry.metadata["last_correction_time"] = datetime.now(
            timezone.utc
        ).isoformat()
        if time_to_fix_seconds:
            error_entry.metadata["time_to_fix"] = time_to_fix_seconds

        self.storage.update(error_entry)

        # Store correction as separate entry
        correction_entry = MemoryEntry(
            content=correction,
            memory_type=MemoryType.CORRECTION,
            metadata={
                "error_id": error_id,
                "error_signature": error_entry.metadata.get("error_signature"),
                "successful": successful,
                "time_to_fix": time_to_fix_seconds,
                "error_type": error_entry.metadata.get("error_type"),
            },
            importance=0.8 if successful else 0.5,
        )

        return self.storage.store(correction_entry)

    def detect_recurring_errors(self, days: int = 30) -> List[Dict]:
        """
        Detect errors that occur repeatedly.

        Args:
            days: Days to look back

        Returns:
            List of recurring error patterns with frequency
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        errors = self.storage.list_entries(memory_type=MemoryType.ERROR, limit=10000)

        # Filter to time window
        recent_errors = [e for e in errors if e.timestamp >= cutoff]

        # Group by error signature
        error_groups = defaultdict(list)
        for error in recent_errors:
            signature = error.metadata.get("error_signature", "unknown")
            error_groups[signature].append(error)

        # Identify recurring errors
        recurring = []
        for signature, group in error_groups.items():
            if len(group) >= self.recurrence_threshold:
                # Calculate statistics
                total_occurrences = len(group)
                corrected_count = sum(
                    1 for e in group if e.metadata.get("corrected", False)
                )
                avg_severity = sum(
                    self._severity_to_importance(e.metadata.get("severity", "medium"))
                    for e in group
                ) / len(group)

                # Find most recent occurrence
                latest = max(group, key=lambda e: e.timestamp)

                recurring.append(
                    {
                        "error_signature": signature,
                        "occurrences": total_occurrences,
                        "corrected_count": corrected_count,
                        "correction_rate": (
                            corrected_count / total_occurrences
                            if total_occurrences > 0
                            else 0
                        ),
                        "avg_severity": avg_severity,
                        "latest_occurrence": latest.timestamp,
                        "latest_description": latest.content,
                        "error_type": latest.metadata.get("error_type", "unknown"),
                    }
                )

        # Sort by occurrence frequency
        recurring.sort(key=lambda x: x["occurrences"], reverse=True)

        return recurring

    def suggest_correction(
        self, error_description: str, error_type: Optional[str] = None
    ) -> Optional[Dict]:
        """
        Suggest a correction based on past successful fixes.

        Args:
            error_description: Description of the current error
            error_type: Type of error (optional)

        Returns:
            Suggested correction with confidence score, or None if no suggestion
        """
        # Extract error signature
        error_signature = self._extract_error_signature(error_description, error_type)

        # Find similar past errors
        past_errors = self.storage.list_entries(
            memory_type=MemoryType.ERROR, limit=10000
        )

        # Filter to matching signature
        matching_errors = [
            e
            for e in past_errors
            if e.metadata.get("error_signature") == error_signature
            and e.metadata.get("corrected", False)
        ]

        if not matching_errors:
            return None

        # Find corrections for these errors
        corrections = []
        for error in matching_errors:
            correction_entries = [
                c
                for c in self.storage.list_entries(
                    memory_type=MemoryType.CORRECTION, limit=10000
                )
                if c.metadata.get("error_id") == error.id
                and c.metadata.get("successful", False)
            ]
            corrections.extend(correction_entries)

        if not corrections:
            return None

        # Group corrections by content similarity
        correction_groups = defaultdict(list)
        for correction in corrections:
            key = self._get_correction_key(correction.content)
            correction_groups[key].append(correction)

        # Find most effective correction
        best_correction = None
        best_score = 0.0

        for key, group in correction_groups.items():
            # Calculate effectiveness
            success_rate = sum(
                1 for c in group if c.metadata.get("successful", False)
            ) / len(group)
            recency_factor = sum(
                1.0 / max((datetime.now(timezone.utc) - c.timestamp).days + 1, 1)
                for c in group
            ) / len(group)

            # Combined score
            score = success_rate * 0.7 + recency_factor * 0.3

            if score > best_score and success_rate >= self.effectiveness_threshold:
                best_score = score
                best_correction = {
                    "correction": group[0].content,  # Most recent representative
                    "confidence": score,
                    "success_rate": success_rate,
                    "usage_count": len(group),
                    "avg_time_to_fix": (
                        sum(
                            c.metadata.get("time_to_fix", 0)
                            for c in group
                            if c.metadata.get("time_to_fix")
                        )
                        / len([c for c in group if c.metadata.get("time_to_fix")])
                        if any(c.metadata.get("time_to_fix") for c in group)
                        else None
                    ),
                }

        return best_correction

    def get_error_patterns(self, limit: int = 10) -> List[Dict]:
        """
        Get common error patterns and their characteristics.

        Args:
            limit: Maximum number of patterns to return

        Returns:
            List of error patterns with statistics
        """
        errors = self.storage.list_entries(memory_type=MemoryType.ERROR, limit=10000)

        # Group by error type
        type_groups = defaultdict(list)
        for error in errors:
            error_type = error.metadata.get("error_type", "unknown")
            type_groups[error_type].append(error)

        # Calculate pattern statistics
        patterns = []
        for error_type, group in type_groups.items():
            corrected_count = sum(
                1 for e in group if e.metadata.get("corrected", False)
            )
            total_attempts = sum(
                e.metadata.get("correction_attempts", 0) for e in group
            )

            # Calculate average time to fix
            times_to_fix = [
                e.metadata.get("time_to_fix")
                for e in group
                if e.metadata.get("time_to_fix")
            ]
            avg_time_to_fix = (
                sum(times_to_fix) / len(times_to_fix) if times_to_fix else None
            )

            # Severity distribution
            severities = defaultdict(int)
            for e in group:
                severity = e.metadata.get("severity", "medium")
                severities[severity] += 1

            patterns.append(
                {
                    "error_type": error_type,
                    "total_occurrences": len(group),
                    "corrected_count": corrected_count,
                    "correction_rate": corrected_count / len(group) if group else 0,
                    "avg_correction_attempts": (
                        total_attempts / len(group) if group else 0
                    ),
                    "avg_time_to_fix": avg_time_to_fix,
                    "severity_distribution": dict(severities),
                    "first_seen": min(e.timestamp for e in group),
                    "last_seen": max(e.timestamp for e in group),
                }
            )

        # Sort by occurrence frequency
        patterns.sort(key=lambda x: x["total_occurrences"], reverse=True)

        return patterns[:limit]

    def get_prevention_suggestions(self, error_type: Optional[str] = None) -> List[str]:
        """
        Get suggestions for preventing errors.

        Args:
            error_type: Filter by error type (optional)

        Returns:
            List of prevention suggestions
        """
        # Get recurring errors
        recurring = self.detect_recurring_errors(days=90)

        # Filter by error type if specified
        if error_type:
            recurring = [r for r in recurring if r["error_type"] == error_type]

        # Generate suggestions based on patterns
        suggestions = []

        for pattern in recurring[:5]:  # Top 5 recurring errors
            if pattern["correction_rate"] < 0.5:
                # Poorly corrected errors
                suggestions.append(
                    f"High-priority: '{pattern['error_signature']}' has low correction rate ({pattern['correction_rate']:.1%}). "
                    f"Occurred {pattern['occurrences']} times. Consider root cause analysis."
                )
            elif pattern["occurrences"] > 5:
                # Frequently occurring errors
                suggestions.append(
                    f"Frequent error: '{pattern['error_signature']}' occurred {pattern['occurrences']} times. "
                    f"Consider implementing preventive checks or validation."
                )

        return suggestions

    def get_correction_history(
        self, error_id: Optional[str] = None, days: int = 30
    ) -> List[Dict]:
        """
        Get history of corrections.

        Args:
            error_id: Filter by specific error (optional)
            days: Days to look back

        Returns:
            List of correction attempts
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        corrections = self.storage.list_entries(
            memory_type=MemoryType.CORRECTION, limit=10000
        )

        # Filter by error_id if specified
        if error_id:
            corrections = [
                c for c in corrections if c.metadata.get("error_id") == error_id
            ]

        # Filter by time
        corrections = [c for c in corrections if c.timestamp >= cutoff]

        # Format history
        history = []
        for correction in corrections:
            # Get original error
            error_id_ref = correction.metadata.get("error_id")
            error_entry = self.storage.retrieve(error_id_ref) if error_id_ref else None

            history.append(
                {
                    "correction_id": correction.id,
                    "error_id": error_id_ref,
                    "error_description": (
                        error_entry.content if error_entry else "Unknown"
                    ),
                    "correction": correction.content,
                    "successful": correction.metadata.get("successful", False),
                    "time_to_fix": correction.metadata.get("time_to_fix"),
                    "timestamp": correction.timestamp,
                }
            )

        # Sort by timestamp
        history.sort(key=lambda x: x["timestamp"], reverse=True)

        return history

    def _extract_error_signature(
        self, error_description: str, error_type: Optional[str]
    ) -> str:
        """
        Extract error signature for pattern matching.

        Args:
            error_description: Error description
            error_type: Error type

        Returns:
            Error signature string
        """
        # Simplified: Use first 5 words + error type
        words = error_description.lower().split()[:5]
        signature_parts = [error_type] if error_type else []
        signature_parts.extend(words)
        return " ".join(signature_parts)

    def _get_correction_key(self, correction: str) -> str:
        """
        Get normalized correction key for grouping.

        Args:
            correction: Correction description

        Returns:
            Normalized key
        """
        # Simplified: Use first 5 words
        words = correction.lower().split()[:5]
        return " ".join(words)

    def _severity_to_importance(self, severity: str) -> float:
        """
        Convert severity to importance score.

        Args:
            severity: Severity level

        Returns:
            Importance score (0.0-1.0)
        """
        severity_map = {
            "low": 0.3,
            "medium": 0.6,
            "high": 0.8,
            "critical": 1.0,
        }
        return severity_map.get(severity.lower(), 0.5)

    def get_stats(self) -> Dict:
        """
        Get error correction statistics.

        Returns:
            Dictionary with statistics
        """
        errors = self.storage.list_entries(memory_type=MemoryType.ERROR, limit=10000)
        corrections = self.storage.list_entries(
            memory_type=MemoryType.CORRECTION, limit=10000
        )

        # Calculate statistics
        total_errors = len(errors)
        corrected_errors = sum(1 for e in errors if e.metadata.get("corrected", False))
        successful_corrections = sum(
            1 for c in corrections if c.metadata.get("successful", False)
        )

        # Error types
        error_types = defaultdict(int)
        for error in errors:
            error_type = error.metadata.get("error_type", "unknown")
            error_types[error_type] += 1

        # Recurring errors
        recurring = self.detect_recurring_errors(days=30)

        return {
            "total_errors": total_errors,
            "corrected_errors": corrected_errors,
            "correction_rate": (
                corrected_errors / total_errors if total_errors > 0 else 0.0
            ),
            "total_corrections": len(corrections),
            "successful_corrections": successful_corrections,
            "success_rate": (
                successful_corrections / len(corrections) if corrections else 0.0
            ),
            "error_types": dict(error_types),
            "recurring_error_count": len(recurring),
            "recurrence_threshold": self.recurrence_threshold,
            "effectiveness_threshold": self.effectiveness_threshold,
        }
