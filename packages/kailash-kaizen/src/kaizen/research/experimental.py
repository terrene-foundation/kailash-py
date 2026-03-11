"""
Experimental Feature System for Kaizen Research Integration.

This module provides the ExperimentalFeature class for wrapping validated
research implementations as experimental features with lifecycle management.

Components:
- ExperimentalFeature: Core wrapper for validated research as experimental feature
"""

from dataclasses import dataclass
from typing import Any, Dict, Type

from kaizen.research.parser import ResearchPaper
from kaizen.research.validator import ValidationResult
from kaizen.signatures import Signature


@dataclass
class ExperimentalFeature:
    """
    Experimental feature wrapping validated research implementation.

    Provides lifecycle management (experimental → beta → stable),
    enable/disable functionality, and automatic documentation generation.

    Attributes:
        feature_id: Unique identifier for the feature
        paper: Original research paper
        validation: Validation results from ResearchValidator
        signature_class: Kaizen signature class for the feature
        version: Semantic version string (e.g., "1.0.0")
        status: Feature lifecycle status ("experimental", "beta", "stable", "deprecated")
        compatibility: Framework version requirements (e.g., {"kaizen": ">=0.1.0"})
        performance: Performance benchmarks (e.g., {"speedup": 2.7})
        metadata: Additional feature metadata (e.g., tags, description)

    Example:
        >>> validation = ValidationResult(
        ...     validation_passed=True,
        ...     reproducibility_score=0.96
        ... )
        >>> feature = ExperimentalFeature(
        ...     feature_id="flash-attention-v1",
        ...     paper=flash_attention_paper,
        ...     validation=validation,
        ...     signature_class=FlashAttentionSignature,
        ...     version="1.0.0",
        ...     status="experimental",
        ...     compatibility={"kaizen": ">=0.1.0"},
        ...     performance={"speedup": 2.7},
        ...     metadata={"tags": ["attention", "optimization"]}
        ... )
        >>> feature.enable()
        >>> result = feature.execute(query="test", key="test", value="test")
    """

    feature_id: str
    paper: ResearchPaper
    validation: ValidationResult
    signature_class: Type[Signature]
    version: str
    status: str  # "experimental", "beta", "stable", "deprecated"
    compatibility: Dict[str, str]
    performance: Dict[str, float]
    metadata: Dict[str, Any]

    def __post_init__(self):
        """Initialize feature state after dataclass construction."""
        self._enabled = False

    def is_enabled(self) -> bool:
        """
        Check if feature is currently enabled.

        Returns:
            True if feature is enabled, False otherwise
        """
        return self._enabled

    def enable(self) -> None:
        """
        Enable the feature for use.

        Once enabled, the feature can be executed via the execute() method.
        """
        self._enabled = True

    def disable(self) -> None:
        """
        Disable the feature.

        After disabling, attempts to execute() will raise RuntimeError.
        """
        self._enabled = False

    def execute(self, **kwargs) -> Any:
        """
        Execute the feature using the wrapped signature.

        Args:
            **kwargs: Arguments to pass to the signature execution

        Returns:
            Result from signature execution

        Raises:
            RuntimeError: If feature is not enabled

        Example:
            >>> feature.enable()
            >>> result = feature.execute(query="test", key="test", value="test")
        """
        if not self._enabled:
            raise RuntimeError(f"Feature {self.feature_id} is not enabled")

        # Create signature instance and execute
        signature_instance = self.signature_class()
        return signature_instance.execute(**kwargs)

    def update_status(self, new_status: str) -> None:
        """
        Update feature lifecycle status with validation.

        Valid transitions:
        - experimental → beta
        - beta → stable
        - any → deprecated

        Invalid transitions:
        - experimental → stable (must go through beta)
        - stable → experimental (can't downgrade)
        - beta → experimental (can't downgrade)

        Args:
            new_status: New status to transition to

        Raises:
            ValueError: If transition is invalid

        Example:
            >>> feature.update_status("beta")  # experimental → beta (valid)
            >>> feature.update_status("stable")  # beta → stable (valid)
        """
        # Define valid transitions
        valid_transitions = {
            "experimental": ["beta", "deprecated"],
            "beta": ["stable", "deprecated"],
            "stable": ["deprecated"],
            "deprecated": [],
        }

        # Check if transition is valid
        if new_status not in valid_transitions.get(self.status, []):
            raise ValueError(
                f"Invalid status transition from '{self.status}' to '{new_status}'. "
                f"Valid transitions: {valid_transitions.get(self.status, [])}"
            )

        self.status = new_status

    def get_documentation(self) -> str:
        """
        Generate automatic documentation for the feature.

        Returns:
            Markdown-formatted documentation string

        Example:
            >>> docs = feature.get_documentation()
            >>> print(docs)
            # Flash Attention v1.0.0

            **Status**: experimental
            ...
        """
        # Build documentation from feature metadata
        doc_parts = []

        # Title
        title = self.metadata.get("description", self.paper.title)
        doc_parts.append(f"# {title}")
        doc_parts.append("")

        # Feature ID and version
        doc_parts.append(f"**Feature ID**: {self.feature_id}")
        doc_parts.append(f"**Version**: {self.version}")
        doc_parts.append(f"**Status**: {self.status}")
        doc_parts.append("")

        # Paper information
        doc_parts.append("## Source Research")
        doc_parts.append(f"**Paper**: {self.paper.title}")
        doc_parts.append(f"**Authors**: {', '.join(self.paper.authors)}")
        if self.paper.arxiv_id:
            doc_parts.append(f"**arXiv**: {self.paper.arxiv_id}")
        doc_parts.append("")

        # Validation results
        doc_parts.append("## Validation")
        doc_parts.append(
            f"**Reproducibility Score**: {self.validation.reproducibility_score:.2%}"
        )
        doc_parts.append(f"**Validation Passed**: {self.validation.validation_passed}")
        doc_parts.append("")

        # Performance metrics
        if self.performance:
            doc_parts.append("## Performance")
            for metric, value in self.performance.items():
                doc_parts.append(f"- **{metric}**: {value}")
            doc_parts.append("")

        # Compatibility requirements
        if self.compatibility:
            doc_parts.append("## Compatibility")
            for framework, requirement in self.compatibility.items():
                doc_parts.append(f"- **{framework}**: {requirement}")
            doc_parts.append("")

        # Metadata tags
        if "tags" in self.metadata:
            doc_parts.append("## Tags")
            doc_parts.append(f"{', '.join(self.metadata['tags'])}")
            doc_parts.append("")

        return "\n".join(doc_parts)


__all__ = ["ExperimentalFeature"]
