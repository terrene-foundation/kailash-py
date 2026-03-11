"""
Signature Programming System - BLOCKER-002 Implementation

This module provides the signature-based programming system that enables
declarative AI workflow definition and automatic optimization.

Core Features:
1. Signature Creation: kaizen.create_signature("question -> answer")
2. Agent Signature Integration: kaizen.create_agent("qa", signature="question -> answer")
3. Signature Compilation: Convert signatures to Core SDK workflow parameters
4. Structured Execution: agent.execute(question="...") -> {'answer': '...'}
5. Pattern-Specific Methods: agent.execute_react(), agent.execute_cot()

Enterprise Features (Exceeding DSPy):
1. Multi-Modal Signatures: "text, image -> analysis" support
2. Enterprise Validation: Type checking, security validation, audit integration
3. Signature Composition: Combine signatures for complex workflows
4. Auto-Optimization: Signature performance optimization hooks
5. Template System: Reusable signature patterns and templates

Performance Requirements:
- Signature compilation: <50ms for complex signatures
- Agent execution: <200ms for signature-based workflows
- Memory usage: <10MB additional overhead for signature system
- Concurrent signatures: Support 100+ simultaneous signature executions
"""

# Core signature system
from .core import (
    InputField,
    OutputField,
    ParseResult,
    Signature,
    SignatureCompiler,
    SignatureMeta,
    SignatureOptimizer,
    SignatureParser,
    SignatureTemplate,
    SignatureValidator,
    ValidationResult,
)

# Enterprise signature extensions
from .enterprise import (
    EnterpriseSignatureValidator,
    MultiModalSignature,
    SignatureComposition,
    SignatureRegistry,
)

# Multi-modal field descriptors
from .multi_modal import AudioField, ImageField
from .multi_modal import MultiModalSignature as MultiModalSignatureBase

# Execution patterns
from .patterns import (
    ChainOfThoughtPattern,
    EnterpriseValidationPattern,
    ExecutionPattern,
    MultiAgentPattern,
    PatternRegistry,
    PatternResult,
    RAGPipelinePattern,
    ReActPattern,
    pattern_registry,
)

__all__ = [
    # Core signature system
    "Signature",
    "InputField",
    "OutputField",
    "SignatureMeta",
    "SignatureParser",
    "SignatureCompiler",
    "SignatureValidator",
    "SignatureTemplate",
    "SignatureOptimizer",
    "ParseResult",
    "ValidationResult",
    # Enterprise extensions
    "EnterpriseSignatureValidator",
    "MultiModalSignature",
    "SignatureComposition",
    "SignatureRegistry",
    # Multi-modal field descriptors
    "ImageField",
    "AudioField",
    "MultiModalSignatureBase",
    # Execution patterns
    "ExecutionPattern",
    "ChainOfThoughtPattern",
    "ReActPattern",
    "MultiAgentPattern",
    "RAGPipelinePattern",
    "EnterpriseValidationPattern",
    "PatternRegistry",
    "PatternResult",
    "pattern_registry",
]
