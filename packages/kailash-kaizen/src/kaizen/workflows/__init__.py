"""
Multi-agent workflow templates for coordination patterns.

This module provides workflow template classes for various multi-agent
coordination patterns built on Core SDK infrastructure.
"""

from .consensus import ConsensusWorkflow
from .debate import DebateWorkflow
from .supervisor_worker import SupervisorWorkerWorkflow

__all__ = ["DebateWorkflow", "ConsensusWorkflow", "SupervisorWorkerWorkflow"]
