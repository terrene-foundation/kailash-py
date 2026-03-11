"""
AI-Enhanced Security Nodes for Kailash Kaizen

Extensions that add LLM-powered capabilities to Core SDK's foundation security nodes.
These nodes build on Core SDK's statistical/rule-based approaches with AI enhancements.

## Architecture

**Core SDK Foundation** (kailash.nodes.security):
- BehaviorAnalysisNode: Statistical ML-based behavior analysis
- ThreatDetectionNode: Rule-based threat pattern matching

**Kaizen Extensions** (kaizen.nodes.security):
- AIBehaviorAnalysisNode: LLM-enhanced behavioral analysis with natural language explanations
- AIThreatDetectionNode: LLM-powered threat intelligence with contextual assessment

## Quick Start

```python
from kaizen.nodes.security import AIBehaviorAnalysisNode, AIThreatDetectionNode

# AI-enhanced behavior analysis
workflow.add_node("ai_behavior", AIBehaviorAnalysisNode(
    provider="openai",
    model="gpt-4o-mini",
    enable_explanations=True,
    risk_threshold=0.7
))

# AI-powered threat detection
workflow.add_node("ai_threat", AIThreatDetectionNode(
    provider="openai",
    model="gpt-4o-mini",
    threat_intelligence=True,
    contextual_assessment=True
))
```

## Key Features

### AIBehaviorAnalysisNode
- Natural language explanations for anomalies
- Contextual risk assessment using LLM understanding
- Advanced pattern recognition beyond statistical methods
- Multi-factor correlation with semantic understanding

### AIThreatDetectionNode
- LLM-powered threat intelligence correlation
- Natural language threat reporting
- Contextual threat assessment
- Advanced pattern recognition with semantic understanding
- Threat narrative generation for security teams

## Relationship to Core SDK

These nodes **extend** (not replace) Core SDK's foundation nodes:
- Import from Core SDK: `from kailash.nodes.security import BehaviorAnalysisNode, ThreatDetectionNode`
- Add LLM capabilities on top of statistical/rule-based foundation
- Fallback to Core SDK methods when LLM unavailable
- Maintain backward compatibility with Core SDK APIs
"""

from .ai_behavior_analysis import AIBehaviorAnalysisNode
from .ai_threat_detection import AIThreatDetectionNode

__all__ = [
    "AIBehaviorAnalysisNode",
    "AIThreatDetectionNode",
]
