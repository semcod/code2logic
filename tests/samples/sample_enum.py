"""
Sample enum types for testing.

Tests:
- Basic Enum
- IntEnum
- StrEnum
- auto() values
- Custom values
"""

from enum import Enum, IntEnum, auto
from typing import List


class Status(Enum):
    """Status enumeration with auto values."""

    PENDING = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()


class Priority(IntEnum):
    """Priority levels as integers."""

    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4
    URGENT = 5


class Color(Enum):
    """Color enumeration with string values."""

    RED = "red"
    GREEN = "green"
    BLUE = "blue"
    YELLOW = "yellow"

    @classmethod
    def from_hex(cls, hex_code: str) -> "Color":
        """Create color from hex code."""
        hex_map = {
            "#ff0000": cls.RED,
            "#00ff00": cls.GREEN,
            "#0000ff": cls.BLUE,
            "#ffff00": cls.YELLOW,
        }
        return hex_map.get(hex_code.lower(), cls.RED)


class HttpStatus(IntEnum):
    """HTTP status codes."""

    OK = 200
    CREATED = 201
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    INTERNAL_ERROR = 500

    @property
    def is_success(self) -> bool:
        """Check if status is success."""
        return 200 <= self.value < 300

    @property
    def is_error(self) -> bool:
        """Check if status is error."""
        return self.value >= 400


class TaskType(Enum):
    """Task type enumeration."""

    BUILD = "build"
    TEST = "test"
    DEPLOY = "deploy"
    CLEANUP = "cleanup"

    def get_timeout(self) -> int:
        """Get default timeout for task type."""
        timeouts = {
            TaskType.BUILD: 300,
            TaskType.TEST: 600,
            TaskType.DEPLOY: 120,
            TaskType.CLEANUP: 60,
        }
        return timeouts.get(self, 60)

    def get_allowed_statuses(self) -> List[Status]:
        """Get allowed statuses for this task type."""
        if self == TaskType.CLEANUP:
            return [Status.PENDING, Status.COMPLETED, Status.CANCELLED]
        return list(Status)
