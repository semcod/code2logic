"""
Sample file with functions for reproduction testing.

This file contains functions to test if code2logic
can accurately reproduce function-based code.
"""

from typing import List, Dict, Optional, Any
import json
import os


def calculate_total(items: List[int], tax_rate: float = 0.1) -> float:
    """Calculate total with tax.

    Args:
        items: List of item prices
        tax_rate: Tax rate (default 10%)

    Returns:
        Total price including tax
    """
    subtotal = sum(items)
    return subtotal * (1 + tax_rate)


def filter_by_status(records: List[Dict], status: str) -> List[Dict]:
    """Filter records by status.

    Args:
        records: List of record dictionaries
        status: Status to filter by

    Returns:
        Filtered list of records
    """
    return [r for r in records if r.get("status") == status]


def merge_configs(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Merge two configuration dictionaries.

    Args:
        base: Base configuration
        override: Override values

    Returns:
        Merged configuration
    """
    result = base.copy()
    result.update(override)
    return result


def validate_email(email: str) -> bool:
    """Validate email format.

    Args:
        email: Email address to validate

    Returns:
        True if valid, False otherwise
    """
    if not email or "@" not in email:
        return False
    parts = email.split("@")
    return len(parts) == 2 and len(parts[0]) > 0 and "." in parts[1]


def load_json_file(path: str) -> Optional[Dict]:
    """Load JSON file safely.

    Args:
        path: Path to JSON file

    Returns:
        Parsed JSON data or None if error
    """
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def get_env_or_default(key: str, default: str = "") -> str:
    """Get environment variable or default.

    Args:
        key: Environment variable name
        default: Default value if not found

    Returns:
        Environment value or default
    """
    return os.environ.get(key, default)


def chunk_list(items: List[Any], chunk_size: int) -> List[List[Any]]:
    """Split list into chunks.

    Args:
        items: List to split
        chunk_size: Size of each chunk

    Returns:
        List of chunks
    """
    return [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]


def format_currency(amount: int, currency: str = "USD") -> str:
    """Format amount as currency.

    Args:
        amount: Amount in cents
        currency: Currency code

    Returns:
        Formatted currency string
    """
    dollars = amount / 100
    return f"{currency} {dollars:.2f}"
