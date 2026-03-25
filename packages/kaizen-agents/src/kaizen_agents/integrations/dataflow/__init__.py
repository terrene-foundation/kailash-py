"""
Kaizen-DataFlow Integration (Optional).

This integration is OPTIONAL and activates only when both frameworks are present.
- Kaizen works independently without DataFlow
- DataFlow works independently without Kaizen
- Integration provides enhanced capabilities when both present

Architecture:
- Check DataFlow availability at import time
- Export integration components only when available
- Provide graceful degradation when DataFlow missing
- Maintain clean separation of concerns

Usage:
    from kaizen.integrations.dataflow import DATAFLOW_AVAILABLE

    if DATAFLOW_AVAILABLE:
        from kaizen.integrations.dataflow import DataFlowAwareAgent
        agent = DataFlowAwareAgent(config=config, db=db)
    else:
        # Fallback to standard Kaizen agent
        agent = BaseAgent(config=config)
"""

# Check DataFlow availability
try:
    from dataflow import DataFlow

    DATAFLOW_AVAILABLE = True
except ImportError:
    DATAFLOW_AVAILABLE = False
    DataFlow = None

# Export integration components only when available
if DATAFLOW_AVAILABLE:
    from .ai_enhanced_ops import (
        DataQualityAgent,
        DataTransformAgent,
        NLToSQLAgent,
        SemanticSearchAgent,
    )
    from .base import DataFlowAwareAgent, DataFlowOperationsMixin
    from .batch_optimizer import BatchConfig, BatchOptimizer, BatchResult
    from .connection import DataFlowConnection
    from .db_driven_ai import (
        DBTrainingPipeline,
        InferencePipeline,
        InferenceSignature,
        PipelineOrchestrationSignature,
        PipelineOrchestrator,
        TrainingPipelineSignature,
    )

    # Performance Optimizations (Phase 4)
    from .query_cache import QueryCache
    from .query_optimizer import BulkOperationOptimizer, QueryOptimizer

    __all__ = [
        "DATAFLOW_AVAILABLE",
        "DataFlowConnection",
        "DataFlowAwareAgent",
        "DataFlowOperationsMixin",
        # AI-Enhanced Operations (Phase 2)
        "NLToSQLAgent",
        "DataTransformAgent",
        "DataQualityAgent",
        "SemanticSearchAgent",
        "QueryOptimizer",
        "BulkOperationOptimizer",
        # Database-Driven AI Workflows (Phase 3)
        "DBTrainingPipeline",
        "InferencePipeline",
        "PipelineOrchestrator",
        "TrainingPipelineSignature",
        "InferenceSignature",
        "PipelineOrchestrationSignature",
        # Performance Optimizations (Phase 4)
        "QueryCache",
        "BatchOptimizer",
        "BatchConfig",
        "BatchResult",
    ]
else:
    __all__ = ["DATAFLOW_AVAILABLE"]

__version__ = "0.1.0"
