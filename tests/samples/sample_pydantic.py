"""
Sample Pydantic models for testing.

Tests:
- BaseModel inheritance
- Field() with aliases
- Validators
- model_config
"""

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from datetime import datetime
from enum import Enum


class TaskStatus(str, Enum):
    """Task status enumeration."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Task(BaseModel):
    """Task model with Pydantic features."""

    id: str
    name: str
    description: Optional[str] = None
    status: TaskStatus = TaskStatus.PENDING
    priority: int = Field(default=1, ge=1, le=5)
    created_at: Optional[datetime] = Field(default=None, alias="createdAt")
    tags: List[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        """Validate name is not empty."""
        if not v.strip():
            raise ValueError("Name cannot be empty")
        return v.strip()


class TaskQueue(BaseModel):
    """Task queue container."""

    name: str = "default"
    tasks: List[Task] = Field(default_factory=list)
    max_size: int = Field(default=100, ge=1)

    def add_task(self, task: Task) -> bool:
        """Add task to queue."""
        if len(self.tasks) >= self.max_size:
            return False
        self.tasks.append(task)
        return True

    def get_pending(self) -> List[Task]:
        """Get pending tasks."""
        return [t for t in self.tasks if t.status == TaskStatus.PENDING]

    def get_by_status(self, status: TaskStatus) -> List[Task]:
        """Get tasks by status."""
        return [t for t in self.tasks if t.status == status]


class Project(BaseModel):
    """Project model with nested models."""

    id: str
    name: str
    owner: str
    queues: List[TaskQueue] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)

    def total_tasks(self) -> int:
        """Get total task count."""
        return sum(len(q.tasks) for q in self.queues)
