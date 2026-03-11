"""Consensus-Building Multi-Agent Pattern."""

from .workflow import (
    ConsensusConfig,
    FacilitatorAgent,
    ProposerAgent,
    ReviewerAgent,
    consensus_building_workflow,
)

__all__ = [
    "ProposerAgent",
    "ReviewerAgent",
    "FacilitatorAgent",
    "consensus_building_workflow",
    "ConsensusConfig",
]
