"""
Google A2A (Agent-to-Agent) integration mixin for BaseAgent.

Extracts all A2A protocol methods from BaseAgent -- agent card generation,
capability extraction, collaboration style, performance metrics, and
resource requirements.

Uses duck typing -- the host class must provide:
- self.agent_id: str
- self.signature: Signature
- self.config: BaseAgentConfig
- self.memory: optional
- self.shared_memory: optional
- self.strategy: optional

Copyright 2025 Terrene Foundation (Singapore CLG)
Licensed under Apache-2.0
"""

import logging
from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    try:
        from kaizen.nodes.ai.a2a import (
            A2AAgentCard,
            Capability,
            CollaborationStyle,
            PerformanceMetrics,
            ResourceRequirements,
        )
    except ImportError:
        pass

logger = logging.getLogger(__name__)


class A2AMixin:
    """Mixin providing Google A2A protocol support for BaseAgent.

    Generates agent capability cards for semantic discovery, task matching,
    and team formation in multi-agent systems.
    """

    def to_a2a_card(self) -> "A2AAgentCard":
        """Generate Google A2A compliant agent card.

        Returns:
            A2AAgentCard: Complete agent card with capabilities, performance, resources.
        """
        try:
            from kaizen.nodes.ai.a2a import A2AAgentCard
        except ImportError:
            raise ImportError(
                "kaizen.nodes.ai.a2a not available. Install with: pip install kailash-kaizen"
            )

        return A2AAgentCard(
            agent_id=self.agent_id,
            agent_name=self.__class__.__name__,
            agent_type=self._get_agent_type(),
            version=getattr(self, "version", "1.0.0"),
            primary_capabilities=self._extract_primary_capabilities(),
            secondary_capabilities=self._extract_secondary_capabilities(),
            collaboration_style=self._get_collaboration_style(),
            performance=self._get_performance_metrics(),
            resources=self._get_resource_requirements(),
            description=self._get_agent_description(),
            tags=self._get_agent_tags(),
            specializations=self._get_specializations(),
        )

    def _extract_primary_capabilities(self) -> List["Capability"]:
        """Extract primary capabilities from signature."""
        try:
            from kaizen.nodes.ai.a2a import Capability, CapabilityLevel
        except ImportError:
            return []

        capabilities = []
        if hasattr(self, "signature") and self.signature:
            if hasattr(self.signature, "input_fields") and self.signature.input_fields:
                for field in self.signature.input_fields:
                    field_name = field.name if hasattr(field, "name") else "input"
                    field_desc = field.desc if hasattr(field, "desc") else ""

                    capabilities.append(
                        Capability(
                            name=field_name,
                            domain=self._infer_domain(),
                            level=CapabilityLevel.EXPERT,
                            description=field_desc or f"Processes {field_name} inputs",
                            keywords=self._extract_keywords(field_desc),
                            examples=[],
                            constraints=[],
                        )
                    )

        return capabilities

    def _extract_secondary_capabilities(self) -> List["Capability"]:
        """Extract secondary capabilities from strategy and memory."""
        try:
            from kaizen.nodes.ai.a2a import Capability, CapabilityLevel
        except ImportError:
            return []

        capabilities = []

        if hasattr(self, "memory") and self.memory:
            capabilities.append(
                Capability(
                    name="conversation_memory",
                    domain=self._infer_domain(),
                    level=CapabilityLevel.ADVANCED,
                    description="Maintains conversation context across sessions",
                    keywords=["memory", "context", "history"],
                    examples=[],
                    constraints=[],
                )
            )

        if hasattr(self, "shared_memory") and self.shared_memory:
            capabilities.append(
                Capability(
                    name="multi_agent_collaboration",
                    domain="collaboration",
                    level=CapabilityLevel.ADVANCED,
                    description="Shares insights with other agents via shared memory",
                    keywords=["collaboration", "sharing", "insights"],
                    examples=[],
                    constraints=[],
                )
            )

        return capabilities

    def _get_collaboration_style(self) -> "CollaborationStyle":
        """Determine collaboration style from agent configuration."""
        try:
            from kaizen.nodes.ai.a2a import CollaborationStyle
        except ImportError:
            return None

        if hasattr(self, "shared_memory") and self.shared_memory:
            return CollaborationStyle.COOPERATIVE

        return CollaborationStyle.INDEPENDENT

    def _get_performance_metrics(self) -> "PerformanceMetrics":
        """Get performance metrics for agent card."""
        try:
            from datetime import datetime

            from kaizen.nodes.ai.a2a import PerformanceMetrics
        except ImportError:
            return None

        return PerformanceMetrics(
            total_tasks=0,
            successful_tasks=0,
            failed_tasks=0,
            average_response_time_ms=0.0,
            average_insight_quality=0.8,
            average_confidence_score=0.85,
            insights_generated=0,
            unique_insights=0,
            actionable_insights=0,
            collaboration_score=0.7,
            reliability_score=0.9,
            last_active=datetime.now(),
        )

    def _get_resource_requirements(self) -> "ResourceRequirements":
        """Get resource requirements from config."""
        try:
            from kaizen.nodes.ai.a2a import ResourceRequirements
        except ImportError:
            return None

        max_tokens = getattr(self.config, "max_tokens", 4000)
        model = getattr(self.config, "model", "")
        provider = getattr(self.config, "llm_provider", "")

        requires_gpu = "llama" in model.lower() or "mistral" in model.lower()
        requires_internet = provider in ["openai", "anthropic", "google"]

        return ResourceRequirements(
            min_memory_mb=512,
            max_memory_mb=4096,
            min_tokens=100,
            max_tokens=max_tokens,
            requires_gpu=requires_gpu,
            requires_internet=requires_internet,
            estimated_cost_per_task=0.01,
            max_concurrent_tasks=5,
            supported_models=[model] if model else [],
            required_apis=[provider] if provider else [],
        )

    def _infer_domain(self) -> str:
        """Infer domain from agent class name and signature."""
        class_name = self.__class__.__name__.lower()

        if "qa" in class_name or "question" in class_name:
            return "question_answering"
        elif "rag" in class_name or "research" in class_name:
            return "research"
        elif "code" in class_name or "programming" in class_name:
            return "code_generation"
        elif "analysis" in class_name or "analyst" in class_name:
            return "analysis"
        elif "summary" in class_name or "summarize" in class_name:
            return "summarization"
        elif "translation" in class_name or "translate" in class_name:
            return "translation"
        elif "classification" in class_name or "classify" in class_name:
            return "classification"

        return "general"

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text description."""
        if not text:
            return []

        stop_words = {
            "a",
            "an",
            "the",
            "is",
            "are",
            "was",
            "were",
            "to",
            "for",
            "of",
            "in",
            "on",
            "at",
        }
        words = text.lower().split()
        keywords = [w.strip(".,;:!?") for w in words if w not in stop_words]

        return keywords[:10]

    def _get_agent_type(self) -> str:
        """Get agent type identifier."""
        return self.__class__.__name__

    def _get_agent_description(self) -> str:
        """Get agent description from docstring or signature."""
        if self.__class__.__doc__:
            return self.__class__.__doc__.strip().split("\n")[0]

        if hasattr(self, "signature") and self.signature:
            return (
                f"Agent with {len(getattr(self.signature, 'input_fields', []))} inputs"
            )

        return f"{self.__class__.__name__} agent"

    def _get_agent_tags(self) -> List[str]:
        """Get agent tags from domain and capabilities."""
        tags = [self._infer_domain()]

        if hasattr(self, "memory") and self.memory:
            tags.append("memory")
        if hasattr(self, "shared_memory") and self.shared_memory:
            tags.append("collaborative")

        if hasattr(self, "strategy"):
            strategy_name = self.strategy.__class__.__name__.lower()
            if "async" in strategy_name:
                tags.append("async")
            if "multi_cycle" in strategy_name:
                tags.append("iterative")

        return tags

    def _get_specializations(self) -> Dict[str, Any]:
        """Get agent specializations and metadata."""
        return {
            "framework": "kaizen",
            "has_memory": hasattr(self, "memory") and self.memory is not None,
            "has_shared_memory": hasattr(self, "shared_memory")
            and self.shared_memory is not None,
            "strategy": (
                self.strategy.__class__.__name__
                if hasattr(self, "strategy")
                else "none"
            ),
            "model": getattr(self.config, "model", "unknown"),
            "provider": getattr(self.config, "llm_provider", "unknown"),
        }
