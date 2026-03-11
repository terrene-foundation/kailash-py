"""
Optimization metrics dashboard for real-time monitoring.

This module provides a dashboard interface for monitoring optimization
performance in real-time, including metrics visualization and reporting.
"""

import json
import logging
import statistics
import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class DashboardMetrics:
    """Real-time dashboard metrics."""

    timestamp: float
    total_signatures: int
    active_optimizations: int
    average_improvement: float
    target_achievement_rate: float
    optimization_throughput: float  # optimizations per hour
    quality_trend: str  # "improving", "stable", "declining"
    anomaly_rate: float
    system_health: str  # "excellent", "good", "warning", "critical"


@dataclass
class SignatureMetrics:
    """Metrics for individual signature."""

    signature_id: str
    total_executions: int
    baseline_performance: Dict[str, float]
    current_performance: Dict[str, float]
    improvement_metrics: Dict[str, float]
    target_achievements: Dict[str, bool]
    last_optimization: Optional[float]
    optimization_count: int
    quality_trend: List[float]  # Recent quality scores
    anomaly_count: int


class OptimizationDashboard:
    """
    Real-time optimization metrics dashboard.

    Provides comprehensive monitoring and reporting of auto-optimization
    system performance with real-time metrics and visualizations.
    """

    def __init__(self, auto_optimization_engine, update_interval: int = 30):
        self.engine = auto_optimization_engine
        self.update_interval = update_interval

        # Metrics storage
        self.dashboard_history = deque(maxlen=1000)  # Recent dashboard snapshots
        self.signature_metrics = {}  # signature_id -> SignatureMetrics
        self.system_alerts = deque(maxlen=100)  # Recent alerts

        # Performance tracking
        self.optimization_counts = defaultdict(int)  # Count optimizations per signature
        self.last_update = time.time()

        logger.info("Optimization dashboard initialized")

    async def get_real_time_metrics(self) -> DashboardMetrics:
        """Get current real-time metrics for the dashboard."""
        try:
            current_time = time.time()

            # Get optimization engine statistics
            engine_stats = await self.engine.get_optimization_statistics()

            # Calculate dashboard metrics
            total_signatures = len(self.engine.performance_trackers)

            # Count active optimizations (signatures optimized in last hour)
            one_hour_ago = current_time - 3600
            active_optimizations = 0
            total_improvement = 0
            improvement_count = 0
            target_achievements = {"accuracy": 0, "speed": 0, "quality": 0}
            total_targets = (
                len(self.engine.performance_trackers) * 3
            )  # 3 metrics per signature

            for signature_id, tracker in self.engine.performance_trackers.items():
                # Check if optimized recently
                if tracker.improvement_history:
                    latest_timestamp = tracker.improvement_history[-1]["timestamp"]
                    if latest_timestamp >= one_hour_ago:
                        active_optimizations += 1

                # Get improvements
                avg_improvements = tracker.get_average_improvement()
                for metric, improvement in avg_improvements.items():
                    total_improvement += improvement
                    improvement_count += 1

                # Check target achievements
                achievements = tracker.check_target_achievement()
                for metric, achieved in achievements.items():
                    if achieved:
                        target_achievements[metric] += 1

            # Calculate averages
            average_improvement = total_improvement / max(improvement_count, 1)
            target_achievement_rate = sum(target_achievements.values()) / max(
                total_targets, 1
            )

            # Calculate optimization throughput (optimizations per hour)
            time_window = current_time - self.last_update
            recent_optimizations = sum(self.optimization_counts.values())
            optimization_throughput = recent_optimizations / max(
                time_window / 3600, 0.1
            )

            # Determine quality trend
            quality_trend = await self._calculate_quality_trend()

            # Get anomaly rate from feedback system
            feedback_analytics = engine_stats.get("feedback_analytics", {})
            anomaly_count = feedback_analytics.get("anomaly_count", 0)
            feedback_count = feedback_analytics.get("feedback_count", 1)
            anomaly_rate = anomaly_count / max(feedback_count, 1)

            # Determine system health
            system_health = self._calculate_system_health(
                average_improvement, target_achievement_rate, anomaly_rate
            )

            dashboard_metrics = DashboardMetrics(
                timestamp=current_time,
                total_signatures=total_signatures,
                active_optimizations=active_optimizations,
                average_improvement=average_improvement,
                target_achievement_rate=target_achievement_rate,
                optimization_throughput=optimization_throughput,
                quality_trend=quality_trend,
                anomaly_rate=anomaly_rate,
                system_health=system_health,
            )

            # Store in history
            self.dashboard_history.append(dashboard_metrics)

            return dashboard_metrics

        except Exception as e:
            logger.error(f"Error getting real-time metrics: {e}")
            # Return default metrics on error
            return DashboardMetrics(
                timestamp=time.time(),
                total_signatures=0,
                active_optimizations=0,
                average_improvement=0.0,
                target_achievement_rate=0.0,
                optimization_throughput=0.0,
                quality_trend="unknown",
                anomaly_rate=0.0,
                system_health="unknown",
            )

    async def get_signature_details(
        self, signature_id: str
    ) -> Optional[SignatureMetrics]:
        """Get detailed metrics for a specific signature."""
        if signature_id not in self.engine.performance_trackers:
            return None

        try:
            tracker = self.engine.performance_trackers[signature_id]

            # Calculate quality trend
            quality_scores = [
                entry["metrics"].get("quality", 0)
                for entry in tracker.improvement_history[-20:]  # Recent 20
            ]

            # Count anomalies for this signature
            anomaly_count = 0
            for entry in self.engine.feedback_system.anomaly_detector.detection_history:
                if (
                    "signature_id" in entry
                    and entry.get("signature_id") == signature_id
                ):
                    anomaly_count += entry.get("anomalies_detected", 0)

            signature_metrics = SignatureMetrics(
                signature_id=signature_id,
                total_executions=len(tracker.improvement_history),
                baseline_performance=tracker.baseline_metrics.copy(),
                current_performance=tracker.current_metrics.copy(),
                improvement_metrics=tracker.get_average_improvement(),
                target_achievements=tracker.check_target_achievement(),
                last_optimization=(
                    tracker.improvement_history[-1]["timestamp"]
                    if tracker.improvement_history
                    else None
                ),
                optimization_count=self.optimization_counts.get(signature_id, 0),
                quality_trend=quality_scores,
                anomaly_count=anomaly_count,
            )

            # Store/update in cache
            self.signature_metrics[signature_id] = signature_metrics

            return signature_metrics

        except Exception as e:
            logger.error(f"Error getting signature details for {signature_id}: {e}")
            return None

    async def get_dashboard_summary(self) -> Dict[str, Any]:
        """Get comprehensive dashboard summary."""
        try:
            # Get current metrics
            current_metrics = await self.get_real_time_metrics()

            # Get all signature details
            signature_details = {}
            for signature_id in self.engine.performance_trackers.keys():
                details = await self.get_signature_details(signature_id)
                if details:
                    signature_details[signature_id] = details

            # Calculate summary statistics
            summary_stats = await self._calculate_summary_statistics(signature_details)

            # Get recent alerts
            recent_alerts = list(self.system_alerts)[-10:]  # Recent 10 alerts

            # Get performance trends over time
            performance_trends = self._get_performance_trends()

            return {
                "current_metrics": asdict(current_metrics),
                "signature_count": current_metrics.total_signatures,
                "signature_details": {
                    sig_id: asdict(details)
                    for sig_id, details in signature_details.items()
                },
                "summary_statistics": summary_stats,
                "recent_alerts": recent_alerts,
                "performance_trends": performance_trends,
                "system_status": {
                    "health": current_metrics.system_health,
                    "last_update": current_metrics.timestamp,
                    "uptime_hours": (time.time() - self.last_update) / 3600,
                },
            }

        except Exception as e:
            logger.error(f"Error getting dashboard summary: {e}")
            return {"error": str(e)}

    async def _calculate_quality_trend(self) -> str:
        """Calculate overall quality trend across all signatures."""
        try:
            all_quality_scores = []

            for tracker in self.engine.performance_trackers.values():
                recent_scores = [
                    entry["metrics"].get("quality", 0)
                    for entry in tracker.improvement_history[-10:]  # Recent 10
                ]
                all_quality_scores.extend(recent_scores)

            if len(all_quality_scores) < 5:
                return "insufficient_data"

            # Calculate trend using linear regression
            import numpy as np

            x = list(range(len(all_quality_scores)))
            slope = np.polyfit(x, all_quality_scores, 1)[0]

            if slope > 0.01:
                return "improving"
            elif slope < -0.01:
                return "declining"
            else:
                return "stable"

        except Exception as e:
            logger.warning(f"Error calculating quality trend: {e}")
            return "unknown"

    def _calculate_system_health(
        self, avg_improvement: float, target_achievement: float, anomaly_rate: float
    ) -> str:
        """Calculate overall system health status."""
        try:
            health_score = 0

            # Improvement score (0-30 points)
            if avg_improvement >= 0.4:
                health_score += 30
            elif avg_improvement >= 0.2:
                health_score += 20
            elif avg_improvement >= 0.1:
                health_score += 10

            # Target achievement score (0-40 points)
            if target_achievement >= 0.8:
                health_score += 40
            elif target_achievement >= 0.6:
                health_score += 30
            elif target_achievement >= 0.4:
                health_score += 20
            elif target_achievement >= 0.2:
                health_score += 10

            # Anomaly score (0-30 points, inversely related)
            if anomaly_rate <= 0.05:
                health_score += 30
            elif anomaly_rate <= 0.1:
                health_score += 20
            elif anomaly_rate <= 0.2:
                health_score += 10

            # Determine health status
            if health_score >= 80:
                return "excellent"
            elif health_score >= 60:
                return "good"
            elif health_score >= 40:
                return "warning"
            else:
                return "critical"

        except Exception as e:
            logger.warning(f"Error calculating system health: {e}")
            return "unknown"

    async def _calculate_summary_statistics(
        self, signature_details: Dict
    ) -> Dict[str, Any]:
        """Calculate summary statistics across all signatures."""
        if not signature_details:
            return {}

        try:
            # Collect all improvements
            all_improvements = {"accuracy": [], "speed": [], "quality": []}

            total_executions = 0
            total_optimizations = 0
            total_anomalies = 0

            for details in signature_details.values():
                total_executions += details.total_executions
                total_optimizations += details.optimization_count
                total_anomalies += details.anomaly_count

                for metric, improvement in details.improvement_metrics.items():
                    if metric in all_improvements:
                        all_improvements[metric].append(improvement)

            # Calculate statistics
            stats = {
                "total_executions": total_executions,
                "total_optimizations": total_optimizations,
                "total_anomalies": total_anomalies,
                "average_executions_per_signature": total_executions
                / len(signature_details),
                "improvement_statistics": {},
            }

            for metric, improvements in all_improvements.items():
                if improvements:
                    stats["improvement_statistics"][metric] = {
                        "mean": statistics.mean(improvements),
                        "median": statistics.median(improvements),
                        "std": (
                            statistics.stdev(improvements)
                            if len(improvements) > 1
                            else 0
                        ),
                        "min": min(improvements),
                        "max": max(improvements),
                        "count": len(improvements),
                    }

            return stats

        except Exception as e:
            logger.error(f"Error calculating summary statistics: {e}")
            return {}

    def _get_performance_trends(self) -> Dict[str, List]:
        """Get performance trends over time from dashboard history."""
        try:
            if len(self.dashboard_history) < 2:
                return {}

            trends = {
                "timestamps": [],
                "average_improvements": [],
                "target_achievements": [],
                "optimization_throughputs": [],
                "anomaly_rates": [],
            }

            for metrics in self.dashboard_history:
                trends["timestamps"].append(metrics.timestamp)
                trends["average_improvements"].append(metrics.average_improvement)
                trends["target_achievements"].append(metrics.target_achievement_rate)
                trends["optimization_throughputs"].append(
                    metrics.optimization_throughput
                )
                trends["anomaly_rates"].append(metrics.anomaly_rate)

            return trends

        except Exception as e:
            logger.warning(f"Error getting performance trends: {e}")
            return {}

    async def add_alert(
        self, alert_type: str, message: str, severity: str = "info"
    ) -> None:
        """Add a system alert to the dashboard."""
        alert = {
            "timestamp": time.time(),
            "type": alert_type,
            "message": message,
            "severity": severity,  # info, warning, error, critical
        }

        self.system_alerts.append(alert)
        logger.info(f"Dashboard alert: [{severity.upper()}] {alert_type}: {message}")

    async def export_metrics(self, format_type: str = "json") -> str:
        """Export current metrics in specified format."""
        try:
            dashboard_summary = await self.get_dashboard_summary()

            if format_type.lower() == "json":
                return json.dumps(dashboard_summary, indent=2, default=str)
            elif format_type.lower() == "csv":
                return self._export_to_csv(dashboard_summary)
            else:
                raise ValueError(f"Unsupported export format: {format_type}")

        except Exception as e:
            logger.error(f"Error exporting metrics: {e}")
            return f"Error exporting metrics: {e}"

    def _export_to_csv(self, dashboard_summary: Dict) -> str:
        """Export dashboard summary to CSV format."""
        try:
            import csv
            import io

            output = io.StringIO()
            writer = csv.writer(output)

            # Write header
            writer.writerow(["Metric", "Value", "Timestamp"])

            # Write current metrics
            current = dashboard_summary.get("current_metrics", {})
            timestamp = current.get("timestamp", time.time())

            for key, value in current.items():
                if key != "timestamp":
                    writer.writerow([key, value, timestamp])

            # Write signature summaries
            for sig_id, details in dashboard_summary.get(
                "signature_details", {}
            ).items():
                for metric, improvement in details.get(
                    "improvement_metrics", {}
                ).items():
                    writer.writerow(
                        [f"{sig_id}_{metric}_improvement", improvement, timestamp]
                    )

            return output.getvalue()

        except Exception as e:
            logger.error(f"Error exporting to CSV: {e}")
            return f"Error: {e}"

    async def get_optimization_recommendations(self) -> List[Dict[str, Any]]:
        """Get optimization recommendations for the dashboard."""
        try:
            # Get recommendations from the optimization engine
            engine_recommendations = (
                await self.engine.get_optimization_recommendations()
            )

            # Add dashboard-specific recommendations
            dashboard_recommendations = []

            current_metrics = await self.get_real_time_metrics()

            # System health recommendations
            if current_metrics.system_health == "critical":
                dashboard_recommendations.append(
                    {
                        "type": "system_health",
                        "priority": "critical",
                        "title": "Critical System Health",
                        "description": "System health is critical. Immediate attention required.",
                        "actions": [
                            "Review system configuration",
                            "Check for resource constraints",
                            "Analyze recent anomalies",
                            "Consider resetting optimization parameters",
                        ],
                    }
                )

            # Low target achievement recommendations
            if current_metrics.target_achievement_rate < 0.3:
                dashboard_recommendations.append(
                    {
                        "type": "target_achievement",
                        "priority": "high",
                        "title": "Low Target Achievement Rate",
                        "description": f"Only {current_metrics.target_achievement_rate:.1%} of targets are being achieved.",
                        "actions": [
                            "Review target thresholds",
                            "Increase optimization frequency",
                            "Analyze underperforming signatures",
                            "Consider alternative optimization strategies",
                        ],
                    }
                )

            # High anomaly rate recommendations
            if current_metrics.anomaly_rate > 0.2:
                dashboard_recommendations.append(
                    {
                        "type": "anomaly_rate",
                        "priority": "high",
                        "title": "High Anomaly Rate",
                        "description": f"Anomaly rate is {current_metrics.anomaly_rate:.1%}, above recommended threshold.",
                        "actions": [
                            "Investigate anomaly patterns",
                            "Review input data quality",
                            "Check system stability",
                            "Adjust anomaly detection thresholds",
                        ],
                    }
                )

            # Combine recommendations
            all_recommendations = engine_recommendations + dashboard_recommendations

            # Sort by priority
            priority_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
            all_recommendations.sort(
                key=lambda x: priority_order.get(x.get("priority", "low"), 1),
                reverse=True,
            )

            return all_recommendations

        except Exception as e:
            logger.error(f"Error getting optimization recommendations: {e}")
            return []

    async def start_monitoring(self) -> None:
        """Start real-time dashboard monitoring."""
        import asyncio

        logger.info("Starting dashboard monitoring")

        async def monitoring_loop():
            while True:
                try:
                    # Update metrics
                    await self.get_real_time_metrics()

                    # Check for alerts
                    await self._check_system_alerts()

                    # Sleep until next update
                    await asyncio.sleep(self.update_interval)

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Error in dashboard monitoring loop: {e}")
                    await asyncio.sleep(60)  # Wait before retrying

        # Create monitoring task
        self.monitoring_task = asyncio.create_task(monitoring_loop())

    async def stop_monitoring(self) -> None:
        """Stop dashboard monitoring."""
        if hasattr(self, "monitoring_task"):
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass

        logger.info("Dashboard monitoring stopped")

    async def _check_system_alerts(self) -> None:
        """Check for system conditions that require alerts."""
        try:
            current_metrics = await self.get_real_time_metrics()

            # Check for critical conditions
            if current_metrics.system_health == "critical":
                await self.add_alert(
                    "system_health",
                    "System health is critical - immediate attention required",
                    "critical",
                )

            # Check for declining quality trend
            if current_metrics.quality_trend == "declining":
                await self.add_alert(
                    "quality_trend",
                    "Quality trend is declining across signatures",
                    "warning",
                )

            # Check for high anomaly rate
            if current_metrics.anomaly_rate > 0.3:
                await self.add_alert(
                    "anomaly_rate",
                    f"High anomaly rate detected: {current_metrics.anomaly_rate:.1%}",
                    "error",
                )

        except Exception as e:
            logger.error(f"Error checking system alerts: {e}")


# Utility functions for dashboard visualization
def format_improvement_percentage(improvement: float) -> str:
    """Format improvement as percentage with appropriate color coding."""
    if improvement >= 0.6:
        return f"+{improvement:.1%} (Excellent)"
    elif improvement >= 0.3:
        return f"+{improvement:.1%} (Good)"
    elif improvement >= 0.1:
        return f"+{improvement:.1%} (Fair)"
    elif improvement >= 0:
        return f"+{improvement:.1%} (Minimal)"
    else:
        return f"{improvement:.1%} (Decline)"


def format_system_health(health: str) -> Dict[str, str]:
    """Format system health with color and description."""
    health_info = {
        "excellent": {
            "color": "green",
            "description": "All systems performing optimally",
        },
        "good": {
            "color": "blue",
            "description": "Systems performing well with minor issues",
        },
        "warning": {
            "color": "yellow",
            "description": "Some performance issues detected",
        },
        "critical": {
            "color": "red",
            "description": "Critical issues requiring immediate attention",
        },
        "unknown": {
            "color": "gray",
            "description": "System status cannot be determined",
        },
    }

    return health_info.get(health, health_info["unknown"])
