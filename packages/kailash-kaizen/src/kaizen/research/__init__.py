"""
Research Integration Framework - TODO-155 Phase 1

Automated research paper integration with <7 day target (vs 90 day baseline).

This module provides:
1. ResearchParser: Parse arXiv papers, PDFs, DOI references (<30s per paper)
2. ResearchValidator: Validate reproducibility (>95% target)
3. ResearchAdapter: Wrap research as Kaizen signatures (<1s adaptation)
4. ResearchRegistry: Searchable research catalog (<100ms search)

Performance Targets:
- Parse arXiv paper: <30 seconds
- Validate reproducibility: <5 minutes
- Adapt to signature: <1 second
- Registry search: <100ms
- Total integration time: <7 days (vs 90 day baseline)

Integration Points:
- TODO-142 Signatures: ResearchAdapter wraps research as signatures
- TODO-145 Optimization: ResearchValidator uses QualityMetrics
- TODO-151 Monitoring: Integration with MetricsCollector
"""

from .adapter import ResearchAdapter, SignatureAdapter
from .advanced_patterns import (
    AdaptivePattern,
    AdvancedPatternBuilder,
    CompositionalPattern,
    HierarchicalPattern,
    MetaLearningPattern,
)
from .compatibility_checker import CompatibilityChecker
from .documentation_generator import DocumentationGenerator
from .experimental import ExperimentalFeature
from .feature_manager import FeatureManager
from .feature_optimizer import FeatureOptimizer
from .integration_workflow import IntegrationWorkflow
from .intelligent_optimizer import IntelligentOptimizer
from .parser import ResearchPaper, ResearchParser
from .registry import RegistryEntry, ResearchRegistry
from .validator import ResearchValidator, ValidationResult

__all__ = [
    "ResearchParser",
    "ResearchPaper",
    "ResearchValidator",
    "ValidationResult",
    "ResearchAdapter",
    "SignatureAdapter",
    "ResearchRegistry",
    "RegistryEntry",
    "ExperimentalFeature",
    "FeatureManager",
    "IntegrationWorkflow",
    "CompatibilityChecker",
    "FeatureOptimizer",
    "DocumentationGenerator",
    "AdvancedPatternBuilder",
    "CompositionalPattern",
    "HierarchicalPattern",
    "AdaptivePattern",
    "MetaLearningPattern",
    "IntelligentOptimizer",
]
