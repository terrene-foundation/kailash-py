"""
Signature definitions for DataFlow AI Debug Agent.

DebugAgentSignature defines the input/output interface for AI debugging tasks.
Uses Kaizen signature-based programming for automatic optimization.
"""

from kaizen.signatures import Signature
from pydantic import Field


class DebugAgentSignature(Signature):
    """
    Signature for AI debugging task.

    Input fields:
    - error_code: DataFlow error code (DF-XXX)
    - error_context: Error context from ErrorEnhancer
    - workflow_structure: Workflow structure from Inspector

    Output fields:
    - diagnosis: Root cause diagnosis
    - ranked_solutions: Solutions ranked by relevance (1-3)
    - confidence: Confidence score (0.0-1.0)
    - next_steps: Specific actions to take
    """

    def __init__(self):
        """Initialize debug agent signature with inputs and outputs."""
        super().__init__(
            inputs=["error_code", "error_context", "workflow_structure"],
            outputs=["diagnosis", "ranked_solutions", "confidence", "next_steps"],
            signature_type="enterprise",
            name="DebugAgentSignature",
            description="AI-powered debugging signature for DataFlow errors",
            input_types={
                "error_code": str,
                "error_context": dict,
                "workflow_structure": dict,
            },
            output_types={
                "diagnosis": str,
                "ranked_solutions": list,
                "confidence": float,
                "next_steps": list,
            },
        )

        # Store field descriptions for test validation
        self._input_descriptions = {
            "error_code": "DataFlow error code (DF-XXX)",
            "error_context": "Error context from ErrorEnhancer",
            "workflow_structure": "Workflow structure from Inspector",
        }

        self._output_descriptions = {
            "diagnosis": "Root cause diagnosis",
            "ranked_solutions": "Solutions ranked by relevance (1-3)",
            "confidence": "Confidence score (0.0-1.0)",
            "next_steps": "Specific actions to take",
        }

    @property
    def error_code(self):
        """Get error_code field descriptor."""

        class FieldDescriptor:
            description = "DataFlow error code (DF-XXX)"

        return FieldDescriptor()

    @property
    def error_context(self):
        """Get error_context field descriptor."""

        class FieldDescriptor:
            description = "Error context from ErrorEnhancer"

        return FieldDescriptor()

    @property
    def workflow_structure(self):
        """Get workflow_structure field descriptor."""

        class FieldDescriptor:
            description = "Workflow structure from Inspector"

        return FieldDescriptor()

    @property
    def diagnosis(self):
        """Get diagnosis field descriptor."""

        class FieldDescriptor:
            description = "Root cause diagnosis"

        return FieldDescriptor()

    @property
    def ranked_solutions(self):
        """Get ranked_solutions field descriptor."""

        class FieldDescriptor:
            description = "Solutions ranked by relevance (1-3)"

        return FieldDescriptor()

    @property
    def confidence(self):
        """Get confidence field descriptor."""

        class FieldDescriptor:
            description = "Confidence score (0.0-1.0)"

        return FieldDescriptor()

    @property
    def next_steps(self):
        """Get next_steps field descriptor."""

        class FieldDescriptor:
            description = "Specific actions to take"

        return FieldDescriptor()
