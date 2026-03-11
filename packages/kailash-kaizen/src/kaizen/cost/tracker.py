"""
Cost Tracker - Multi-modal API cost tracking and budget management.

Tracks usage across providers (Ollama, OpenAI) and estimates costs.
Provides budget limits, alerts, and usage analytics.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional


@dataclass
class UsageRecord:
    """Record of a single API usage."""

    provider: str  # 'ollama', 'openai'
    modality: str  # 'vision', 'audio', 'text', 'mixed'
    model: str  # Model name
    cost: float  # Cost in USD
    timestamp: datetime
    input_size: Optional[int] = None  # For vision (bytes)
    duration: Optional[int] = None  # For audio (seconds)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CostAlert:
    """Cost alert notification."""

    level: str  # 'info', 'warning', 'error'
    message: str
    current_cost: float = 0.0
    budget_limit: Optional[float] = None
    timestamp: datetime = field(default_factory=datetime.now)


class CostTracker:
    """
    Track multi-modal API usage and costs.

    Features:
    - Track Ollama (free) and OpenAI (paid) usage
    - Budget limits and alerts
    - Estimate OpenAI equivalent costs for Ollama usage
    - Usage analytics by provider, modality, time range
    """

    # OpenAI pricing (for estimation)
    OPENAI_VISION_COST = 0.01  # ~$0.01 per image
    OPENAI_AUDIO_COST_PER_MIN = 0.006  # $0.006 per minute

    def __init__(
        self,
        budget_limit: Optional[float] = None,
        alert_threshold: float = 0.8,  # Alert at 80% of budget
        warn_on_openai_usage: bool = False,
        enable_cost_tracking: bool = True,
    ):
        """
        Initialize cost tracker.

        Args:
            budget_limit: Budget limit in USD
            alert_threshold: Alert when this percentage of budget is used
            warn_on_openai_usage: Warn before OpenAI API calls
            enable_cost_tracking: Enable cost tracking
        """
        self.budget_limit = budget_limit
        self.alert_threshold = alert_threshold
        self.warn_on_openai_usage = warn_on_openai_usage
        self.enable_cost_tracking = enable_cost_tracking

        # Usage records
        self._records: List[UsageRecord] = []

        # Alert callbacks
        self.on_alert: Optional[Callable[[CostAlert], None]] = None
        self.on_warning: Optional[Callable[[str], None]] = None

        # Alert state
        self._alert_triggered = False

    def record_usage(
        self,
        provider: str,
        modality: str,
        model: str,
        cost: float = 0.0,
        input_size: Optional[int] = None,
        duration: Optional[int] = None,
        timestamp: Optional[datetime] = None,
        **metadata,
    ):
        """Record API usage."""
        if not self.enable_cost_tracking:
            return

        record = UsageRecord(
            provider=provider,
            modality=modality,
            model=model,
            cost=cost,
            input_size=input_size,
            duration=duration,
            timestamp=timestamp or datetime.now(),
            metadata=metadata,
        )

        self._records.append(record)

        # Check budget
        if self.budget_limit and not self._alert_triggered:
            percentage = self.get_budget_percentage()
            if percentage >= self.alert_threshold * 100:
                alert = CostAlert(
                    level="warning",
                    message=f"Budget {percentage:.0f}% used (${self.get_total_cost():.2f} / ${self.budget_limit:.2f})",
                    current_cost=self.get_total_cost(),
                    budget_limit=self.budget_limit,
                )
                if self.on_alert:
                    self.on_alert(alert)
                self._alert_triggered = True

    def get_total_cost(self) -> float:
        """Get total cost across all providers."""
        return sum(r.cost for r in self._records)

    def get_usage_stats(self) -> Dict[str, Any]:
        """Get overall usage statistics."""
        stats = {
            "total_calls": len(self._records),
            "total_cost": self.get_total_cost(),
            "ollama_calls": sum(1 for r in self._records if r.provider == "ollama"),
            "openai_calls": sum(1 for r in self._records if r.provider == "openai"),
            "vision_cost": sum(r.cost for r in self._records if r.modality == "vision"),
            "audio_cost": sum(r.cost for r in self._records if r.modality == "audio"),
        }
        return stats

    def estimate_openai_equivalent_cost(self) -> float:
        """
        Estimate what Ollama usage would cost with OpenAI.

        Useful for showing cost savings.
        """
        total = 0.0
        for record in self._records:
            if record.provider == "ollama":
                if record.modality == "vision":
                    total += self.OPENAI_VISION_COST
                elif record.modality == "audio":
                    duration_min = (record.duration or 60) / 60.0
                    total += duration_min * self.OPENAI_AUDIO_COST_PER_MIN
        return total

    def is_over_budget(self) -> bool:
        """Check if over budget."""
        if not self.budget_limit:
            return False
        return self.get_total_cost() > self.budget_limit

    def get_budget_remaining(self) -> float:
        """Get remaining budget."""
        if not self.budget_limit:
            return float("inf")
        return max(0, self.budget_limit - self.get_total_cost())

    def get_budget_percentage(self) -> float:
        """Get budget usage percentage."""
        if not self.budget_limit:
            return 0.0
        return (self.get_total_cost() / self.budget_limit) * 100

    def get_usage_by_provider(self) -> Dict[str, Dict[str, Any]]:
        """Get usage breakdown by provider."""
        by_provider = defaultdict(lambda: {"calls": 0, "cost": 0.0})

        for record in self._records:
            by_provider[record.provider]["calls"] += 1
            by_provider[record.provider]["cost"] += record.cost

        return dict(by_provider)

    def get_usage_by_modality(self) -> Dict[str, Dict[str, Any]]:
        """Get usage breakdown by modality."""
        by_modality = defaultdict(lambda: {"calls": 0, "cost": 0.0})

        for record in self._records:
            by_modality[record.modality]["calls"] += 1
            by_modality[record.modality]["cost"] += record.cost

        return dict(by_modality)

    def get_usage_in_range(self, start: datetime, end: datetime) -> List[UsageRecord]:
        """Get usage records within time range."""
        return [r for r in self._records if start <= r.timestamp <= end]

    def export_report(self) -> Dict[str, Any]:
        """Export comprehensive usage report."""
        return {
            "summary": self.get_usage_stats(),
            "by_provider": self.get_usage_by_provider(),
            "by_modality": self.get_usage_by_modality(),
            "budget": {
                "limit": self.budget_limit,
                "used": self.get_total_cost(),
                "remaining": self.get_budget_remaining(),
                "percentage": self.get_budget_percentage(),
            },
            "savings": {
                "actual_cost": self.get_total_cost(),
                "openai_equivalent": self.estimate_openai_equivalent_cost(),
                "saved": self.estimate_openai_equivalent_cost() - self.get_total_cost(),
            },
        }

    def reset(self):
        """Reset tracker (clear all records)."""
        self._records.clear()
        self._alert_triggered = False

    def check_before_call(self, provider: str, estimated_cost: float):
        """Check and warn before API call."""
        if provider == "openai" and self.warn_on_openai_usage:
            if self.on_warning:
                self.on_warning(f"⚠️  OpenAI API call will cost ~${estimated_cost:.3f}")

    def estimate_cost(
        self,
        provider: str,
        modality: str,
        model: Optional[str] = None,
        input_size: Optional[int] = None,
        duration: Optional[int] = None,
    ) -> float:
        """
        Estimate cost for a processing operation.

        Args:
            provider: 'ollama' or 'openai'
            modality: 'vision', 'audio', 'text', 'mixed'
            model: Model name (optional)
            input_size: Input size in bytes (for vision)
            duration: Duration in seconds (for audio)

        Returns:
            Estimated cost in USD
        """
        if provider == "ollama":
            return 0.0  # Always free

        if provider == "openai":
            if modality == "vision":
                return self.OPENAI_VISION_COST
            elif modality == "audio":
                minutes = (duration or 60) / 60.0
                return minutes * self.OPENAI_AUDIO_COST_PER_MIN
            elif modality == "mixed":
                vision_cost = self.OPENAI_VISION_COST if input_size else 0
                audio_cost = (
                    ((duration or 60) / 60.0) * self.OPENAI_AUDIO_COST_PER_MIN
                    if duration
                    else 0
                )
                return vision_cost + audio_cost

        return 0.0

    def estimate_batch_cost(
        self,
        provider: str,
        modality: str,
        count: int,
        input_size: Optional[int] = None,
        duration: Optional[int] = None,
    ) -> float:
        """Estimate cost for batch processing."""
        single_cost = self.estimate_cost(
            provider=provider,
            modality=modality,
            input_size=input_size,
            duration=duration,
        )
        return single_cost * count

    def compare_providers(
        self,
        modality: str,
        input_size: Optional[int] = None,
        duration: Optional[int] = None,
        providers: List[str] = ["ollama", "openai"],
    ) -> Dict[str, float]:
        """
        Compare costs between providers.

        Returns:
            Dict with provider costs and savings
        """
        comparison = {}

        for provider in providers:
            comparison[provider] = self.estimate_cost(
                provider=provider,
                modality=modality,
                input_size=input_size,
                duration=duration,
            )

        # Calculate savings
        if "ollama" in comparison and "openai" in comparison:
            comparison["savings"] = comparison["openai"] - comparison["ollama"]

        return comparison

    def check_budget_or_raise(self):
        """Check budget and raise exception if exceeded."""
        if self.is_over_budget():
            raise Exception(
                f"Budget exceeded: ${self.get_total_cost():.2f} / ${self.budget_limit:.2f}"
            )
