"""
Auto-optimization framework.

This module provides automatic optimization capabilities for AI workflows,
including prompt optimization, parameter tuning, and performance improvement.

Features:
- Bayesian optimization for parameter tuning
- Feedback loop system for continuous learning
- Anomaly detection and correction
- Performance tracking and improvement measurement
- Integration with signature and memory systems
- Real-time optimization recommendations

Main Components:
- AutoOptimizationEngine: Main coordination engine
- OptimizationEngine: Core optimization algorithms
- FeedbackSystem: Feedback collection and learning
- PerformanceTracker: Performance measurement and improvement tracking
"""

# Core optimization components
from .core import (
    OptimizationEngine,
    OptimizationResult,
    OptimizationStrategy,
    OptimizationStrategyRegistry,
    ParameterAdjustmentEngine,
    PerformanceMetrics,
    PerformancePattern,
    PerformancePatternAnalyzer,
)

# Dashboard and monitoring
from .dashboard import (
    DashboardMetrics,
    OptimizationDashboard,
    SignatureMetrics,
    format_improvement_percentage,
    format_system_health,
)

# Core optimization engine
from .engine import AutoOptimizationEngine, OptimizationSession, PerformanceTracker

# Feedback and learning system
from .feedback import (
    AnomalyDetector,
    AnomalyReport,
    FeedbackEntry,
    FeedbackSystem,
    FeedbackType,
    LearningEngine,
    LearningUpdate,
    QualityMetric,
    QualityMetrics,
)

# Optimization strategies
from .strategies import (
    BayesianOptimizationStrategy,
    GeneticOptimizationStrategy,
    RandomSearchStrategy,
)

__all__ = [
    # Main engine
    "AutoOptimizationEngine",
    "PerformanceTracker",
    "OptimizationSession",
    # Core optimization
    "OptimizationEngine",
    "OptimizationStrategy",
    "OptimizationResult",
    "PerformanceMetrics",
    "PerformancePattern",
    "PerformancePatternAnalyzer",
    "ParameterAdjustmentEngine",
    "OptimizationStrategyRegistry",
    # Strategies
    "BayesianOptimizationStrategy",
    "GeneticOptimizationStrategy",
    "RandomSearchStrategy",
    # Feedback system
    "FeedbackSystem",
    "FeedbackEntry",
    "FeedbackType",
    "QualityMetrics",
    "QualityMetric",
    "AnomalyDetector",
    "AnomalyReport",
    "LearningEngine",
    "LearningUpdate",
    # Dashboard and monitoring
    "OptimizationDashboard",
    "DashboardMetrics",
    "SignatureMetrics",
    "format_improvement_percentage",
    "format_system_health",
]
