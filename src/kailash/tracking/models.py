"""Data models for task tracking."""
from enum import Enum
from datetime import datetime
from typing import Any, Dict, Optional, List
from uuid import uuid4

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """Status of a task execution."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


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
    
    def update_status(self, status: TaskStatus, 
                     result: Optional[Dict[str, Any]] = None,
                     error: Optional[str] = None,
                     ended_at: Optional[datetime] = None) -> None:
        """Update task status.
        
        Args:
            status: New status
            result: Task result (for completed tasks)
            error: Error message (for failed tasks)
            ended_at: When the task ended
        """
        self.status = status
        
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
        data = self.model_dump()
        # Convert datetime objects to strings
        if data.get('started_at'):
            data['started_at'] = data['started_at'].isoformat()
        if data.get('ended_at'):
            data['ended_at'] = data['ended_at'].isoformat()
        return data


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
    
    def update_status(self, status: str, 
                     error: Optional[str] = None) -> None:
        """Update run status.
        
        Args:
            status: New status
            error: Error message (for failed runs)
        """
        self.status = status
        
        if error is not None:
            self.error = error
        
        if status in ["completed", "failed"] and self.ended_at is None:
            self.ended_at = datetime.utcnow()
    
    def add_task(self, task_id: str) -> None:
        """Add a task to this run.
        
        Args:
            task_id: Task ID to add
        """
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
        data = self.model_dump()
        # Convert datetime objects to strings
        data['started_at'] = data['started_at'].isoformat()
        if data.get('ended_at'):
            data['ended_at'] = data['ended_at'].isoformat()
        return data


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
        """Create summary from a TaskRun."""
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
        """Create summary from a WorkflowRun and its tasks."""
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