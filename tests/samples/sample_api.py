"""
Sample API module for reproduction testing.

Contains REST API patterns, async functions, and error handling.
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class APIResponse:
    """Standard API response structure."""

    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class User:
    """User model for API."""

    id: int
    username: str
    email: str
    roles: List[str] = field(default_factory=list)
    created_at: str = ""


class APIError(Exception):
    """Custom API error."""

    def __init__(self, message: str, code: int = 400):
        self.message = message
        self.code = code
        super().__init__(message)


class UserAPI:
    """User management API."""

    def __init__(self):
        self._users: Dict[int, User] = {}
        self._next_id = 1

    def create_user(
        self, username: str, email: str, roles: List[str] = None
    ) -> APIResponse:
        """Create a new user."""
        if not username or not email:
            raise APIError("Username and email are required", 400)

        if "@" not in email:
            raise APIError("Invalid email format", 400)

        user = User(
            id=self._next_id,
            username=username,
            email=email,
            roles=roles or ["user"],
            created_at=datetime.now().isoformat(),
        )

        self._users[user.id] = user
        self._next_id += 1

        return APIResponse(success=True, data=user)

    def get_user(self, user_id: int) -> APIResponse:
        """Get user by ID."""
        if user_id not in self._users:
            raise APIError(f"User {user_id} not found", 404)

        return APIResponse(success=True, data=self._users[user_id])

    def update_user(self, user_id: int, **kwargs) -> APIResponse:
        """Update user fields."""
        if user_id not in self._users:
            raise APIError(f"User {user_id} not found", 404)

        user = self._users[user_id]

        for key, value in kwargs.items():
            if hasattr(user, key):
                setattr(user, key, value)

        return APIResponse(success=True, data=user)

    def delete_user(self, user_id: int) -> APIResponse:
        """Delete user by ID."""
        if user_id not in self._users:
            raise APIError(f"User {user_id} not found", 404)

        del self._users[user_id]
        return APIResponse(success=True, data={"deleted": user_id})

    def list_users(self, limit: int = 10, offset: int = 0) -> APIResponse:
        """List all users with pagination."""
        users = list(self._users.values())[offset : offset + limit]
        return APIResponse(
            success=True,
            data={
                "users": users,
                "total": len(self._users),
                "limit": limit,
                "offset": offset,
            },
        )

    def search_users(self, query: str) -> APIResponse:
        """Search users by username or email."""
        query = query.lower()
        results = [
            u
            for u in self._users.values()
            if query in u.username.lower() or query in u.email.lower()
        ]
        return APIResponse(success=True, data=results)


async def fetch_user_async(api: UserAPI, user_id: int) -> APIResponse:
    """Async wrapper for get_user."""
    return api.get_user(user_id)


async def create_user_async(api: UserAPI, username: str, email: str) -> APIResponse:
    """Async wrapper for create_user."""
    return api.create_user(username, email)


def handle_api_error(func):
    """Decorator to handle API errors."""

    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except APIError as e:
            return APIResponse(success=False, error=e.message)
        except Exception as e:
            return APIResponse(success=False, error=str(e))

    return wrapper
