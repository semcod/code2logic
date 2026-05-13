"""Sample models for re-export testing."""

from dataclasses import dataclass
from typing import List


@dataclass
class User:
    """User model."""

    id: int
    name: str
    email: str


@dataclass
class Order:
    """Order model."""

    id: str
    user_id: int
    items: List[str]


@dataclass
class Product:
    """Product model."""

    sku: str
    name: str
    price: float
