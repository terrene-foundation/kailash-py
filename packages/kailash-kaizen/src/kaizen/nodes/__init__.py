"""
Enhanced AI nodes with signature integration.

This module provides the node system for Kaizen, extending Core SDK nodes
with signature-based programming capabilities and optimization hooks.
"""

from .ai_nodes import (  # Text Processing Nodes; Conversation & Analysis Nodes; Advanced Processing Nodes; Integration Nodes
    KaizenAIModelNode,
    KaizenAIWorkflowNode,
    KaizenCodeGenerationNode,
    KaizenConversationNode,
    KaizenDataAnalysisNode,
    KaizenEntityExtractionNode,
    KaizenPromptTemplateNode,
    KaizenQuestionAnsweringNode,
    KaizenReasoningNode,
    KaizenSentimentAnalysisNode,
    KaizenTextClassificationNode,
    KaizenTextEmbeddingNode,
    KaizenTextGenerationNode,
    KaizenTextSummarizationNode,
    KaizenTextTransformationNode,
)
from .base import KaizenLLMAgentNode, KaizenNode

__all__ = [
    "KaizenNode",
    "KaizenLLMAgentNode",
    # Text Processing Nodes (5 nodes)
    "KaizenTextGenerationNode",
    "KaizenTextClassificationNode",
    "KaizenTextSummarizationNode",
    "KaizenTextEmbeddingNode",
    "KaizenTextTransformationNode",
    # Conversation & Analysis Nodes (4 nodes)
    "KaizenConversationNode",
    "KaizenSentimentAnalysisNode",
    "KaizenEntityExtractionNode",
    "KaizenQuestionAnsweringNode",
    # Advanced Processing Nodes (3 nodes)
    "KaizenCodeGenerationNode",
    "KaizenDataAnalysisNode",
    "KaizenReasoningNode",
    # Integration Nodes (3 nodes)
    "KaizenAIModelNode",
    "KaizenPromptTemplateNode",
    "KaizenAIWorkflowNode",
]
