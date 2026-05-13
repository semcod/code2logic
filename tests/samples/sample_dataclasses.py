"""
Sample file with dataclasses for reproduction testing.

This file contains simple dataclasses to test if code2logic
can accurately reproduce data model definitions.
"""

from dataclasses import dataclass, field
from typing import List, Dict


@dataclass
class User:
    """Represents a user in the system.

    Attributes:
        id: Unique user identifier
        name: User's full name
        email: Email address
        is_active: Whether user is active
        created_at: Account creation timestamp
    """

    id: int
    name: str
    email: str
    is_active: bool = True
    created_at: str = ""


@dataclass
class Product:
    """Represents a product in the catalog.

    Attributes:
        sku: Stock keeping unit
        name: Product name
        price: Price in cents
        quantity: Available quantity
        tags: List of product tags
    """

    sku: str
    name: str
    price: int
    quantity: int = 0
    tags: List[str] = field(default_factory=list)


@dataclass
class Order:
    """Represents a customer order.

    Attributes:
        order_id: Unique order identifier
        user_id: ID of the ordering user
        items: List of product SKUs
        total: Order total in cents
        status: Order status
        metadata: Additional order data
    """

    order_id: str
    user_id: int
    items: List[str]
    total: int
    status: str = "pending"
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class Address:
    """Represents a shipping address.

    Attributes:
        street: Street address
        city: City name
        country: Country code
        postal_code: Postal/ZIP code
    """

    street: str
    city: str
    country: str
    postal_code: str
