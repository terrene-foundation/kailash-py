"""Subagent execution result types.

Defines the result structure returned by TaskTool when spawning subagents.

See: TODO-203 Task/Skill Tools
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class SubagentResult:
    """Result from subagent execution.

    Contains the output, metrics, and metadata from a spawned subagent.

    Example:
        >>> result = SubagentResult(
        ...     subagent_id="subagent-123",
        ...     output="Analysis complete. Found 3 issues.",
        ...     status="completed",
        ...     tokens_used=1500,
        ...     cost_usd=0.0045,
        ... )
    """

    # Core result
    subagent_id: str
    output: str
    status: str = "completed"  # completed, error, interrupted, timeout, running

    # Metrics
    tokens_used: int = 0
    cost_usd: float = 0.0
    cycles_used: int = 0
    duration_ms: int = 0

    # Metadata
    specialist_name: Optional[str] = None
    model_used: Optional[str] = None
    parent_agent_id: Optional[str] = None
    trust_chain_id: Optional[str] = None

    # Error information
    error_message: Optional[str] = None
    error_type: Optional[str] = None

    # Background execution
    output_file: Optional[str] = None
    is_background: bool = False

    # Tool calls made during execution
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)

    # Timestamps
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    completed_at: Optional[str] = None

    @property
    def success(self) -> bool:
        """Check if execution was successful."""
        return self.status == "completed"

    @property
    def is_running(self) -> bool:
        """Check if execution is still running (background)."""
        return self.status == "running"

    @classmethod
    def from_success(
        cls,
        subagent_id: str,
        output: str,
        **kwargs,
    ) -> "SubagentResult":
        """Create a successful result."""
        return cls(
            subagent_id=subagent_id,
            output=output,
            status="completed",
            completed_at=datetime.now(timezone.utc).isoformat(),
            **kwargs,
        )

    @classmethod
    def from_error(
        cls,
        subagent_id: str,
        error_message: str,
        error_type: str = "ExecutionError",
        **kwargs,
    ) -> "SubagentResult":
        """Create an error result."""
        return cls(
            subagent_id=subagent_id,
            output="",
            status="error",
            error_message=error_message,
            error_type=error_type,
            completed_at=datetime.now(timezone.utc).isoformat(),
            **kwargs,
        )

    @classmethod
    def from_background(
        cls,
        subagent_id: str,
        output_file: str,
        **kwargs,
    ) -> "SubagentResult":
        """Create a result for background execution."""
        return cls(
            subagent_id=subagent_id,
            output="",
            status="running",
            is_background=True,
            output_file=output_file,
            **kwargs,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize result to dictionary."""
        return {
            "subagent_id": self.subagent_id,
            "output": self.output,
            "status": self.status,
            "tokens_used": self.tokens_used,
            "cost_usd": self.cost_usd,
            "cycles_used": self.cycles_used,
            "duration_ms": self.duration_ms,
            "specialist_name": self.specialist_name,
            "model_used": self.model_used,
            "parent_agent_id": self.parent_agent_id,
            "trust_chain_id": self.trust_chain_id,
            "error_message": self.error_message,
            "error_type": self.error_type,
            "output_file": self.output_file,
            "is_background": self.is_background,
            "tool_calls": self.tool_calls,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SubagentResult":
        """Deserialize result from dictionary."""
        return cls(**data)


@dataclass
class SkillResult:
    """Result from skill invocation.

    Contains the skill content and metadata after loading.

    Example:
        >>> result = SkillResult(
        ...     skill_name="python-patterns",
        ...     content="# Python Patterns\n...",
        ...     success=True,
        ... )
    """

    skill_name: str
    content: str = ""
    success: bool = True

    # Skill metadata
    description: Optional[str] = None
    location: Optional[str] = None
    source: Optional[str] = None

    # Additional files
    additional_files: Dict[str, str] = field(default_factory=dict)

    # Error information
    error_message: Optional[str] = None

    @property
    def has_additional_files(self) -> bool:
        """Check if skill has additional files."""
        return len(self.additional_files) > 0

    @classmethod
    def from_success(
        cls,
        skill_name: str,
        content: str,
        **kwargs,
    ) -> "SkillResult":
        """Create a successful result."""
        return cls(
            skill_name=skill_name,
            content=content,
            success=True,
            **kwargs,
        )

    @classmethod
    def from_error(
        cls,
        skill_name: str,
        error_message: str,
    ) -> "SkillResult":
        """Create an error result."""
        return cls(
            skill_name=skill_name,
            content="",
            success=False,
            error_message=error_message,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize result to dictionary."""
        return {
            "skill_name": self.skill_name,
            "content": self.content,
            "success": self.success,
            "description": self.description,
            "location": self.location,
            "source": self.source,
            "additional_files": self.additional_files,
            "error_message": self.error_message,
        }


__all__ = [
    "SubagentResult",
    "SkillResult",
]
