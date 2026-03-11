"""
Unit tests for CostTracker - multi-modal API cost tracking and warnings.

Following TDD methodology: Write tests FIRST, then implement.
"""

from datetime import datetime, timedelta

import pytest

# Test infrastructure
try:
    from kaizen.cost.tracker import CostAlert, CostTracker, UsageRecord

    IMPORTS_AVAILABLE = True
except ImportError:
    IMPORTS_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not IMPORTS_AVAILABLE, reason="CostTracker not yet implemented"
)


class TestUsageRecord:
    """Test UsageRecord data structure."""

    def test_record_creation(self):
        """Test basic usage record creation."""
        record = UsageRecord(
            provider="ollama",
            modality="vision",
            model="llava:13b",
            input_size=1000,
            cost=0.0,
            timestamp=datetime.now(),
        )
        assert record.provider == "ollama"
        assert record.modality == "vision"
        assert record.cost == 0.0

    def test_record_with_metadata(self):
        """Test usage record with additional metadata."""
        record = UsageRecord(
            provider="openai",
            modality="vision",
            model="gpt-4-vision-preview",
            input_size=1500,
            cost=0.015,
            timestamp=datetime.now(),
            metadata={"image_size": "1024x768", "tokens": 500},
        )
        assert record.metadata["image_size"] == "1024x768"
        assert record.metadata["tokens"] == 500


class TestCostTracker:
    """Test CostTracker functionality."""

    def test_tracker_creation(self):
        """Test basic tracker creation."""
        tracker = CostTracker()
        assert tracker is not None
        assert tracker.get_total_cost() == 0.0

    def test_tracker_with_budget_limit(self):
        """Test tracker with budget limit."""
        tracker = CostTracker(budget_limit=10.0)
        assert tracker.budget_limit == 10.0

    def test_record_ollama_usage(self):
        """Test recording Ollama usage (always $0)."""
        tracker = CostTracker()

        tracker.record_usage(
            provider="ollama", modality="vision", model="llava:13b", input_size=1000
        )

        assert tracker.get_total_cost() == 0.0
        stats = tracker.get_usage_stats()
        assert stats["total_calls"] == 1
        assert stats["ollama_calls"] == 1

    def test_record_openai_vision_usage(self):
        """Test recording OpenAI vision usage."""
        tracker = CostTracker()

        # GPT-4V: ~$0.01 per image
        tracker.record_usage(
            provider="openai",
            modality="vision",
            model="gpt-4-vision-preview",
            input_size=1000,
            cost=0.01,
        )

        assert tracker.get_total_cost() == 0.01
        stats = tracker.get_usage_stats()
        assert stats["total_calls"] == 1
        assert stats["openai_calls"] == 1
        assert stats["vision_cost"] == 0.01

    def test_record_openai_audio_usage(self):
        """Test recording OpenAI audio usage."""
        tracker = CostTracker()

        # Whisper: $0.006 per minute
        tracker.record_usage(
            provider="openai",
            modality="audio",
            model="whisper-1",
            duration=60,
            cost=0.006,
        )

        assert tracker.get_total_cost() == 0.006
        stats = tracker.get_usage_stats()
        assert stats["audio_cost"] == 0.006

    def test_track_multiple_usages(self):
        """Test tracking multiple API calls."""
        tracker = CostTracker()

        # Mix of Ollama (free) and OpenAI (paid)
        tracker.record_usage("ollama", "vision", "llava:13b", input_size=1000, cost=0.0)
        tracker.record_usage("openai", "vision", "gpt-4v", input_size=1000, cost=0.01)
        tracker.record_usage("ollama", "audio", "whisper", duration=60, cost=0.0)
        tracker.record_usage("openai", "audio", "whisper-1", duration=60, cost=0.006)

        assert tracker.get_total_cost() == 0.016
        stats = tracker.get_usage_stats()
        assert stats["total_calls"] == 4
        assert stats["ollama_calls"] == 2
        assert stats["openai_calls"] == 2

    def test_estimate_openai_equivalent_cost(self):
        """Test estimating OpenAI equivalent cost for Ollama usage."""
        tracker = CostTracker()

        # Record Ollama usage
        tracker.record_usage("ollama", "vision", "llava:13b", input_size=1000, cost=0.0)

        # Estimate what it would cost with OpenAI
        estimated = tracker.estimate_openai_equivalent_cost()
        assert estimated > 0  # Would cost something with OpenAI
        assert 0.005 <= estimated <= 0.02  # Reasonable range

    def test_budget_limit_warning(self):
        """Test budget limit warning."""
        tracker = CostTracker(budget_limit=0.05)

        # Stay under budget
        tracker.record_usage("openai", "vision", "gpt-4v", input_size=1000, cost=0.01)
        assert not tracker.is_over_budget()

        # Approach budget
        tracker.record_usage("openai", "vision", "gpt-4v", input_size=1000, cost=0.03)
        assert tracker.get_budget_remaining() == pytest.approx(0.01, abs=1e-9)
        assert tracker.get_budget_percentage() == pytest.approx(
            80.0, abs=0.1
        )  # 80% used

        # Exceed budget
        tracker.record_usage("openai", "vision", "gpt-4v", input_size=1000, cost=0.02)
        assert tracker.is_over_budget()

    def test_cost_alert_threshold(self):
        """Test cost alert at threshold."""
        tracker = CostTracker(budget_limit=1.0, alert_threshold=0.8)  # Alert at 80%

        alerts = []
        tracker.on_alert = lambda alert: alerts.append(alert)

        # Below threshold - no alert
        tracker.record_usage("openai", "vision", "gpt-4v", cost=0.5)
        assert len(alerts) == 0

        # At threshold - trigger alert
        tracker.record_usage("openai", "vision", "gpt-4v", cost=0.3)
        assert len(alerts) == 1
        assert alerts[0].level == "warning"
        assert "80%" in alerts[0].message

    def test_usage_by_provider(self):
        """Test getting usage breakdown by provider."""
        tracker = CostTracker()

        tracker.record_usage("ollama", "vision", "llava:13b", cost=0.0)
        tracker.record_usage("ollama", "vision", "llava:13b", cost=0.0)
        tracker.record_usage("openai", "vision", "gpt-4v", cost=0.01)

        by_provider = tracker.get_usage_by_provider()
        assert by_provider["ollama"]["calls"] == 2
        assert by_provider["ollama"]["cost"] == 0.0
        assert by_provider["openai"]["calls"] == 1
        assert by_provider["openai"]["cost"] == 0.01

    def test_usage_by_modality(self):
        """Test getting usage breakdown by modality."""
        tracker = CostTracker()

        tracker.record_usage("openai", "vision", "gpt-4v", cost=0.01)
        tracker.record_usage("openai", "vision", "gpt-4v", cost=0.01)
        tracker.record_usage("openai", "audio", "whisper-1", cost=0.006)

        by_modality = tracker.get_usage_by_modality()
        assert by_modality["vision"]["calls"] == 2
        assert by_modality["vision"]["cost"] == 0.02
        assert by_modality["audio"]["calls"] == 1
        assert by_modality["audio"]["cost"] == 0.006

    def test_time_range_filtering(self):
        """Test filtering usage by time range."""
        tracker = CostTracker()

        now = datetime.now()
        yesterday = now - timedelta(days=1)
        hour_ago = now - timedelta(hours=1)

        # Record with specific timestamps
        tracker.record_usage(
            "openai", "vision", "gpt-4v", cost=0.01, timestamp=yesterday
        )
        tracker.record_usage(
            "openai", "vision", "gpt-4v", cost=0.01, timestamp=hour_ago
        )
        tracker.record_usage("openai", "vision", "gpt-4v", cost=0.01, timestamp=now)

        # Get usage for last hour
        recent_usage = tracker.get_usage_in_range(
            start=hour_ago - timedelta(minutes=1), end=now + timedelta(minutes=1)
        )
        assert len(recent_usage) == 2
        assert sum(r.cost for r in recent_usage) == 0.02

    def test_export_usage_report(self):
        """Test exporting usage report."""
        tracker = CostTracker()

        tracker.record_usage("ollama", "vision", "llava:13b", cost=0.0)
        tracker.record_usage("openai", "vision", "gpt-4v", cost=0.01)
        tracker.record_usage("openai", "audio", "whisper-1", cost=0.006)

        report = tracker.export_report()
        assert "summary" in report
        assert "by_provider" in report
        assert "by_modality" in report
        assert report["summary"]["total_cost"] == 0.016
        assert report["summary"]["total_calls"] == 3

    def test_reset_tracker(self):
        """Test resetting tracker."""
        tracker = CostTracker()

        tracker.record_usage("openai", "vision", "gpt-4v", cost=0.01)
        assert tracker.get_total_cost() == 0.01

        tracker.reset()
        assert tracker.get_total_cost() == 0.0
        assert tracker.get_usage_stats()["total_calls"] == 0

    def test_warn_before_openai_call(self):
        """Test warning before OpenAI API call."""
        tracker = CostTracker(warn_on_openai_usage=True)

        warnings = []
        tracker.on_warning = lambda msg: warnings.append(msg)

        # Should warn before OpenAI call
        tracker.check_before_call(provider="openai", estimated_cost=0.01)
        assert len(warnings) == 1
        assert "OpenAI" in warnings[0]
        assert "$0.01" in warnings[0]

        # Should not warn for Ollama
        tracker.check_before_call(provider="ollama", estimated_cost=0.0)
        assert len(warnings) == 1  # No new warning


class TestCostAlert:
    """Test CostAlert functionality."""

    def test_alert_creation(self):
        """Test basic alert creation."""
        alert = CostAlert(
            level="warning",
            message="Budget threshold reached",
            current_cost=8.0,
            budget_limit=10.0,
        )
        assert alert.level == "warning"
        assert alert.current_cost == 8.0

    def test_alert_levels(self):
        """Test different alert levels."""
        # Info alert
        info = CostAlert(level="info", message="Usage tracked")
        assert info.level == "info"

        # Warning alert
        warning = CostAlert(level="warning", message="80% budget used")
        assert warning.level == "warning"

        # Error alert
        error = CostAlert(level="error", message="Budget exceeded")
        assert error.level == "error"


class TestCostEstimation:
    """Test cost estimation utilities."""

    def test_estimate_vision_cost_ollama(self):
        """Test estimating vision cost for Ollama (always $0)."""
        tracker = CostTracker()

        cost = tracker.estimate_cost(
            provider="ollama", modality="vision", input_size=1000
        )
        assert cost == 0.0

    def test_estimate_vision_cost_openai(self):
        """Test estimating vision cost for OpenAI."""
        tracker = CostTracker()

        # GPT-4V pricing
        cost = tracker.estimate_cost(
            provider="openai",
            modality="vision",
            model="gpt-4-vision-preview",
            input_size=1000,
        )
        assert 0.005 <= cost <= 0.02  # Reasonable range

    def test_estimate_audio_cost_ollama(self):
        """Test estimating audio cost for Ollama (always $0)."""
        tracker = CostTracker()

        cost = tracker.estimate_cost(provider="ollama", modality="audio", duration=60)
        assert cost == 0.0

    def test_estimate_audio_cost_openai(self):
        """Test estimating audio cost for OpenAI Whisper."""
        tracker = CostTracker()

        # Whisper pricing: $0.006 per minute
        cost = tracker.estimate_cost(
            provider="openai", modality="audio", model="whisper-1", duration=60
        )
        assert 0.005 <= cost <= 0.01  # ~$0.006

    def test_estimate_batch_cost(self):
        """Test estimating cost for batch processing."""
        tracker = CostTracker()

        # Batch of 10 images
        batch_cost = tracker.estimate_batch_cost(
            provider="openai", modality="vision", count=10, input_size=1000
        )
        assert batch_cost >= 0.05  # At least $0.005 per image

    def test_compare_provider_costs(self):
        """Test comparing costs between providers."""
        tracker = CostTracker()

        comparison = tracker.compare_providers(
            modality="vision", input_size=1000, providers=["ollama", "openai"]
        )

        assert comparison["ollama"] == 0.0
        assert comparison["openai"] > 0.0
        assert "savings" in comparison
        assert comparison["savings"] == comparison["openai"]  # 100% savings with Ollama


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
