"""
Integration Workflow for Automated Research Integration.

This module provides the IntegrationWorkflow class for automated
research paper integration: arXiv → parse → validate → adapt → feature.

Components:
- IntegrationWorkflow: Automated research integration pipeline
"""

from typing import Any, Dict, List

from kaizen.research.adapter import ResearchAdapter
from kaizen.research.experimental import ExperimentalFeature
from kaizen.research.feature_manager import FeatureManager
from kaizen.research.parser import ResearchParser
from kaizen.research.registry import ResearchRegistry
from kaizen.research.validator import ResearchValidator


class IntegrationWorkflow:
    """
    Automated research integration workflow.

    Orchestrates the complete pipeline:
    1. Parse research paper (arXiv, PDF, DOI)
    2. Validate implementation reproducibility
    3. Adapt to Kaizen signature
    4. Register in ResearchRegistry
    5. Create ExperimentalFeature
    6. Register in FeatureManager

    Attributes:
        parser: ResearchParser for paper parsing
        validator: ResearchValidator for reproducibility validation
        adapter: ResearchAdapter for signature adaptation
        registry: ResearchRegistry for paper catalog
        feature_manager: FeatureManager for feature lifecycle

    Example:
        >>> workflow = IntegrationWorkflow(
        ...     parser=ResearchParser(),
        ...     validator=ResearchValidator(),
        ...     adapter=ResearchAdapter(),
        ...     registry=ResearchRegistry(),
        ...     feature_manager=FeatureManager(registry)
        ... )
        >>> feature = workflow.integrate_from_arxiv("2205.14135")
        >>> print(f"Integrated: {feature.feature_id}")
    """

    def __init__(
        self,
        parser: ResearchParser,
        validator: ResearchValidator,
        adapter: ResearchAdapter,
        registry: ResearchRegistry,
        feature_manager: FeatureManager,
    ):
        """
        Initialize IntegrationWorkflow with Phase 1 components.

        Args:
            parser: ResearchParser instance
            validator: ResearchValidator instance
            adapter: ResearchAdapter instance
            registry: ResearchRegistry instance
            feature_manager: FeatureManager instance
        """
        self.parser = parser
        self.validator = validator
        self.adapter = adapter
        self.registry = registry
        self.feature_manager = feature_manager
        self._integration_status: Dict[str, Dict[str, Any]] = {}

    def integrate_from_arxiv(
        self, arxiv_id: str, auto_enable: bool = False
    ) -> ExperimentalFeature:
        """
        Automatic integration from arXiv ID.

        Complete pipeline: arXiv → parse → validate → adapt → feature.

        Args:
            arxiv_id: arXiv paper ID (e.g., "2205.14135")
            auto_enable: If True, enable feature immediately

        Returns:
            ExperimentalFeature instance

        Raises:
            ValueError: If parsing or validation fails

        Example:
            >>> feature = workflow.integrate_from_arxiv(
            ...     "2205.14135",
            ...     auto_enable=True
            ... )
            >>> feature.execute(query="test", key="test", value="test")
        """
        # Step 1: Parse paper
        try:
            paper = self.parser.parse_from_arxiv(arxiv_id)
        except Exception as e:
            raise ValueError(f"Failed to parse paper {arxiv_id}: {e}")

        # Step 2: Validate implementation
        # Try to get code URL from paper metadata
        code_url = getattr(paper, "code_url", None)
        if not code_url:
            # Default to common pattern
            code_url = f"https://github.com/research/{arxiv_id}"

        validation = self.validator.validate_implementation(
            paper=paper, code_url=code_url, validation_dataset=None
        )

        if not validation.validation_passed:
            raise ValueError(f"Validation failed for paper {arxiv_id}")

        # Step 3: Adapt to signature
        signature_class = self.adapter.create_signature_adapter(
            paper=paper, implementation_module="research_impl", main_function="main"
        )

        # Step 4: Register in ResearchRegistry
        self.registry.register_paper(
            paper=paper, validation=validation, signature_class=signature_class
        )

        # Step 5: Create ExperimentalFeature
        feature_id = f"{paper.arxiv_id}-v1.0.0"
        feature = ExperimentalFeature(
            feature_id=feature_id,
            paper=paper,
            validation=validation,
            signature_class=signature_class,
            version="1.0.0",
            status="experimental",
            compatibility={"kaizen": ">=0.1.0"},
            performance=validation.reproduced_metrics or {},
            metadata={},
        )

        # Step 6: Register in FeatureManager
        self.feature_manager.register_feature(feature)

        # Step 7: Enable if requested
        if auto_enable:
            feature.enable()

        # Track integration status
        self._integration_status[feature_id] = {
            "status": "completed",
            "paper_id": paper.arxiv_id,
            "feature_id": feature_id,
            "validation_passed": validation.validation_passed,
        }

        return feature

    def integrate_from_url(
        self, code_url: str, paper_id: str, auto_enable: bool = False
    ) -> ExperimentalFeature:
        """
        Automatic integration from code URL with paper ID.

        Args:
            code_url: URL to code repository
            paper_id: arXiv paper ID
            auto_enable: If True, enable feature immediately

        Returns:
            ExperimentalFeature instance

        Raises:
            ValueError: If parsing or validation fails

        Example:
            >>> feature = workflow.integrate_from_url(
            ...     "https://github.com/Dao-AILab/flash-attention",
            ...     "2205.14135"
            ... )
        """
        # Step 1: Parse paper
        try:
            paper = self.parser.parse_from_arxiv(paper_id)
        except Exception as e:
            raise ValueError(f"Failed to parse paper {paper_id}: {e}")

        # Step 2: Validate with provided code URL
        validation = self.validator.validate_implementation(
            paper=paper, code_url=code_url, validation_dataset=None
        )

        if not validation.validation_passed:
            raise ValueError(f"Validation failed for paper {paper_id}")

        # Step 3: Adapt to signature
        signature_class = self.adapter.create_signature_adapter(
            paper=paper, implementation_module="research_impl", main_function="main"
        )

        # Step 4: Register in ResearchRegistry
        self.registry.register_paper(
            paper=paper, validation=validation, signature_class=signature_class
        )

        # Step 5: Create ExperimentalFeature
        feature_id = f"{paper.arxiv_id}-v1.0.0"
        feature = ExperimentalFeature(
            feature_id=feature_id,
            paper=paper,
            validation=validation,
            signature_class=signature_class,
            version="1.0.0",
            status="experimental",
            compatibility={"kaizen": ">=0.1.0"},
            performance=validation.reproduced_metrics or {},
            metadata={},
        )

        # Step 6: Register in FeatureManager
        self.feature_manager.register_feature(feature)

        # Step 7: Enable if requested
        if auto_enable:
            feature.enable()

        # Track integration status
        self._integration_status[feature_id] = {
            "status": "completed",
            "paper_id": paper.arxiv_id,
            "feature_id": feature_id,
            "validation_passed": validation.validation_passed,
        }

        return feature

    def batch_integrate(self, arxiv_ids: List[str]) -> List[ExperimentalFeature]:
        """
        Batch integration of multiple papers.

        Args:
            arxiv_ids: List of arXiv paper IDs

        Returns:
            List of ExperimentalFeature instances

        Example:
            >>> features = workflow.batch_integrate([
            ...     "2205.14135",
            ...     "1703.03400"
            ... ])
            >>> print(f"Integrated {len(features)} papers")
        """
        features = []

        for arxiv_id in arxiv_ids:
            try:
                feature = self.integrate_from_arxiv(arxiv_id)
                features.append(feature)
            except Exception as e:
                # Log error but continue with other papers
                print(f"Failed to integrate {arxiv_id}: {e}")
                continue

        return features

    def get_integration_status(self, integration_id: str) -> Dict[str, Any]:
        """
        Get status of ongoing or completed integration.

        Args:
            integration_id: Feature ID of integration

        Returns:
            Status dictionary with keys: status, paper_id, feature_id, validation_passed

        Example:
            >>> status = workflow.get_integration_status("2205.14135-v1.0.0")
            >>> print(status["status"])  # "completed", "in_progress", "failed"
        """
        return self._integration_status.get(
            integration_id,
            {
                "status": "not_found",
                "paper_id": None,
                "feature_id": integration_id,
                "validation_passed": False,
            },
        )


__all__ = ["IntegrationWorkflow"]
