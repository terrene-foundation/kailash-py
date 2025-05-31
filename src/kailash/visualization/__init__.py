"""Visualization components for Kailash SDK.

This module provides comprehensive visualization capabilities for workflows,
performance metrics, execution tracking, real-time monitoring, and reporting.

Components:
- PerformanceVisualizer: Static performance chart generation
- RealTimeDashboard: Live workflow monitoring and metrics collection
- WorkflowPerformanceReporter: Comprehensive performance report generation
- SimpleDashboardAPI: Simple API interface for dashboard functionality
- DashboardAPIServer: Full FastAPI server for web integration (requires FastAPI)
"""

from kailash.visualization.api import SimpleDashboardAPI
from kailash.visualization.dashboard import (
    DashboardConfig,
    DashboardExporter,
    LiveMetrics,
    RealTimeDashboard,
)
from kailash.visualization.performance import PerformanceVisualizer
from kailash.visualization.reports import (
    PerformanceInsight,
    ReportConfig,
    ReportFormat,
    WorkflowPerformanceReporter,
    WorkflowSummary,
)

# Optional FastAPI server (only available if FastAPI is installed)
try:
    from kailash.visualization.api import DashboardAPIServer

    __all__ = [
        "PerformanceVisualizer",
        "RealTimeDashboard",
        "DashboardConfig",
        "LiveMetrics",
        "DashboardExporter",
        "WorkflowPerformanceReporter",
        "ReportConfig",
        "ReportFormat",
        "PerformanceInsight",
        "WorkflowSummary",
        "SimpleDashboardAPI",
        "DashboardAPIServer",
    ]
except ImportError:
    # FastAPI not available
    __all__ = [
        "PerformanceVisualizer",
        "RealTimeDashboard",
        "DashboardConfig",
        "LiveMetrics",
        "DashboardExporter",
        "WorkflowPerformanceReporter",
        "ReportConfig",
        "ReportFormat",
        "PerformanceInsight",
        "WorkflowSummary",
        "SimpleDashboardAPI",
    ]
