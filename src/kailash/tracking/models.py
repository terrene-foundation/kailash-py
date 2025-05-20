"""Data models for task tracking."""
from enum import Enum
from datetime import datetime
from typing import Any, Dict, Optional, List
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from kailash.sdk_exceptions import TaskStateError, TaskException

# Metrics class definition
class TaskMetrics(BaseModel):
    """Metrics for task execution."""
    duration: Optional[float] = None
    memory_usage: Optional[float] = None
    cpu_usage: Optional[float] = None


class TaskStatus(str, Enum):
    """Status of a task execution."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


# Valid state transitions for tasks
VALID_TASK_TRANSITIONS = {
    TaskStatus.PENDING: {TaskStatus.RUNNING, TaskStatus.SKIPPED, TaskStatus.FAILED},
    TaskStatus.RUNNING: {TaskStatus.COMPLETED, TaskStatus.FAILED},
    TaskStatus.COMPLETED: set(),  # No transitions from completed
    TaskStatus.FAILED: set(),     # No transitions from failed
    TaskStatus.SKIPPED: set()     # No transitions from skipped
}


class TaskRun(BaseModel):
    """Model for a single task execution."""
    task_id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str = Field(..., description="Associated run ID")
    node_id: str = Field(..., description="Node ID in the workflow")
    node_type: str = Field(..., description="Type of node")
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    @field_validator('run_id', 'node_id', 'node_type')
    def validate_required_string(cls, v, info):
        """Validate required string fields are not empty."""
        if not v:
            raise ValueError(f"{info.field_name} cannot be empty")
        return v
    
    def update_status(self, status: TaskStatus, 
                     result: Optional[Dict[str, Any]] = None,
                     error: Optional[str] = None,
                     ended_at: Optional[datetime] = None,
                     metadata: Optional[Dict[str, Any]] = None) -> None:
        """Update task status.
        
        Args:
            status: New status
            result: Task result (for completed tasks)
            error: Error message (for failed tasks)
            ended_at: When the task ended
            metadata: Additional metadata to update
            
        Raises:
            TaskStateError: If state transition is invalid
        """
        # Validate state transition
        if self.status not in VALID_TASK_TRANSITIONS:
            raise TaskStateError(
                f"Unknown task status: {self.status}"
            )
            
        valid_transitions = VALID_TASK_TRANSITIONS[self.status]
        if status not in valid_transitions and status != self.status:
            raise TaskStateError(
                f"Invalid state transition from {self.status} to {status}. "
                f"Valid transitions: {', '.join(str(s) for s in valid_transitions)}"
            )
        
        # Update status
        self.status = status
        
        # Update other fields
        if result is not None:
            self.result = result
        
        if error is not None:
            self.error = error
        
        if ended_at is not None:
            self.ended_at = ended_at
        elif status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.SKIPPED]:
            self.ended_at = datetime.utcnow()
        
        if status == TaskStatus.RUNNING and self.started_at is None:
            self.started_at = datetime.utcnow()
            
        if metadata is not None:
            self.metadata.update(metadata)
    
    def get_duration(self) -> Optional[float]:
        """Get task duration in seconds.
        
        Returns:
            Duration in seconds, or None if not completed
        """
        if self.started_at and self.ended_at:
            return (self.ended_at - self.started_at).total_seconds()
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        try:
            data = self.model_dump()
            # Convert datetime objects to strings
            if data.get('started_at'):
                data['started_at'] = data['started_at'].isoformat()
            if data.get('ended_at'):
                data['ended_at'] = data['ended_at'].isoformat()
            return data
        except Exception as e:
            raise TaskException(
                f"Failed to serialize task: {e}"
            ) from e


# Valid state transitions for workflow runs
VALID_RUN_TRANSITIONS = {
    "pending": {"running", "failed"},
    "running": {"completed", "failed"},
    "completed": set(),  # No transitions from completed
    "failed": set()      # No transitions from failed
}


class WorkflowRun(BaseModel):
    """Model for a workflow execution run."""
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    workflow_name: str = Field(..., description="Name of the workflow")
    status: str = Field(default="running", description="Run status")
    started_at: datetime = Field(default_factory=datetime.utcnow)
    ended_at: Optional[datetime] = None
    tasks: List[str] = Field(default_factory=list, description="Task IDs")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    
    @field_validator('workflow_name')
    def validate_workflow_name(cls, v):
        """Validate workflow name is not empty."""
        if not v:
            raise ValueError("Workflow name cannot be empty")
        return v
    
    @field_validator('status')
    def validate_status(cls, v):
        """Validate status is valid."""
        valid_statuses = {"pending", "running", "completed", "failed"}
        if v not in valid_statuses:
            raise ValueError(
                f"Invalid status: {v}. Must be one of: {', '.join(valid_statuses)}"
            )
        return v
    
    def update_status(self, status: str, 
                     error: Optional[str] = None) -> None:
        """Update run status.
        
        Args:
            status: New status
            error: Error message (for failed runs)
            
        Raises:
            TaskStateError: If state transition is invalid
        """
        # Validate state transition
        if self.status not in VALID_RUN_TRANSITIONS:
            raise TaskStateError(
                f"Unknown run status: {self.status}"
            )
            
        valid_transitions = VALID_RUN_TRANSITIONS[self.status]
        if status not in valid_transitions and status != self.status:
            raise TaskStateError(
                f"Invalid state transition from {self.status} to {status}. "
                f"Valid transitions: {', '.join(valid_transitions)}"
            )
        
        self.status = status
        
        if error is not None:
            self.error = error
        
        if status in ["completed", "failed"] and self.ended_at is None:
            self.ended_at = datetime.utcnow()
    
    def add_task(self, task_id: str) -> None:
        """Add a task to this run.
        
        Args:
            task_id: Task ID to add
            
        Raises:
            TaskException: If task_id is invalid
        """
        if not task_id:
            raise TaskException("Task ID cannot be empty")
            
        if task_id not in self.tasks:
            self.tasks.append(task_id)
    
    def get_duration(self) -> Optional[float]:
        """Get run duration in seconds.
        
        Returns:
            Duration in seconds, or None if not completed
        """
        if self.ended_at:
            return (self.ended_at - self.started_at).total_seconds()
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        try:
            data = self.model_dump()
            # Convert datetime objects to strings
            data['started_at'] = data['started_at'].isoformat()
            if data.get('ended_at'):
                data['ended_at'] = data['ended_at'].isoformat()
            return data
        except Exception as e:
            raise TaskException(
                f"Failed to serialize workflow run: {e}"
            ) from e


class TaskSummary(BaseModel):
    """Summary information for a task."""
    task_id: str
    node_id: str
    node_type: str
    status: TaskStatus
    duration: Optional[float] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    error: Optional[str] = None
    
    @classmethod
    def from_task_run(cls, task: TaskRun) -> "TaskSummary":
        """Create summary from a TaskRun.
        
        Args:
            task: TaskRun to summarize
            
        Returns:
            TaskSummary instance
            
        Raises:
            TaskException: If summary creation fails
        """
        try:
            return cls(
                task_id=task.task_id,
                node_id=task.node_id,
                node_type=task.node_type,
                status=task.status,
                duration=task.get_duration(),
                started_at=task.started_at.isoformat() if task.started_at else None,
                ended_at=task.ended_at.isoformat() if task.ended_at else None,
                error=task.error
            )
        except Exception as e:
            raise TaskException(
                f"Failed to create task summary: {e}"
            ) from e


class RunSummary(BaseModel):
    """Summary information for a workflow run."""
    run_id: str
    workflow_name: str
    status: str
    duration: Optional[float] = None
    started_at: str
    ended_at: Optional[str] = None
    task_count: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    error: Optional[str] = None
    
    @classmethod
    def from_workflow_run(cls, run: WorkflowRun, 
                         tasks: List[TaskRun]) -> "RunSummary":
        """Create summary from a WorkflowRun and its tasks.
        
        Args:
            run: WorkflowRun to summarize
            tasks: List of associated TaskRun instances
            
        Returns:
            RunSummary instance
            
        Raises:
            TaskException: If summary creation fails
        """
        try:
            completed = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED)
            failed = sum(1 for t in tasks if t.status == TaskStatus.FAILED)
            
            return cls(
                run_id=run.run_id,
                workflow_name=run.workflow_name,
                status=run.status,
                duration=run.get_duration(),
                started_at=run.started_at.isoformat(),
                ended_at=run.ended_at.isoformat() if run.ended_at else None,
                task_count=len(tasks),
                completed_tasks=completed,
                failed_tasks=failed,
                error=run.error
            )
        except Exception as e:
            raise TaskException(
                f"Failed to create run summary: {e}"
            ) from e

# Legacy compatibility aliases for backward compatibility
Task = TaskRun  # For backward compatibility with tests and existing code