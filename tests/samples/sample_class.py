"""
Sample file with a class for reproduction testing.

This file contains a class with methods to test if code2logic
can accurately reproduce class-based code.
"""

from typing import List, Optional


class Calculator:
    """Simple calculator with history.

    Attributes:
        history: List of past calculations
        precision: Decimal precision for results
    """

    def __init__(self, precision: int = 2):
        """Initialize calculator.

        Args:
            precision: Decimal places for rounding
        """
        self.history: List[str] = []
        self.precision = precision

    def add(self, a: float, b: float) -> float:
        """Add two numbers.

        Args:
            a: First number
            b: Second number

        Returns:
            Sum of a and b
        """
        result = round(a + b, self.precision)
        self.history.append(f"{a} + {b} = {result}")
        return result

    def subtract(self, a: float, b: float) -> float:
        """Subtract b from a.

        Args:
            a: First number
            b: Second number

        Returns:
            Difference of a and b
        """
        result = round(a - b, self.precision)
        self.history.append(f"{a} - {b} = {result}")
        return result

    def multiply(self, a: float, b: float) -> float:
        """Multiply two numbers.

        Args:
            a: First number
            b: Second number

        Returns:
            Product of a and b
        """
        result = round(a * b, self.precision)
        self.history.append(f"{a} * {b} = {result}")
        return result

    def divide(self, a: float, b: float) -> Optional[float]:
        """Divide a by b.

        Args:
            a: Dividend
            b: Divisor

        Returns:
            Quotient or None if division by zero
        """
        if b == 0:
            return None
        result = round(a / b, self.precision)
        self.history.append(f"{a} / {b} = {result}")
        return result

    def clear_history(self) -> None:
        """Clear calculation history."""
        self.history = []

    def get_history(self) -> List[str]:
        """Get calculation history.

        Returns:
            List of past calculations
        """
        return self.history.copy()
