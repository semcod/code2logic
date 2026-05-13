#!/usr/bin/env python3
"""
Logic2Test Custom Templates Example

Customizing test generation templates.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from logic2test.parsers import ClassSpec, FunctionSpec
from logic2test.templates import TestTemplate


def example_function_test():
    """Generate a test for a custom function spec."""
    print("=== Function Test Template ===")

    # Create a function specification
    func = FunctionSpec(
        name="calculate_discount",
        params=["price: float", "percentage: float", "max_discount: float = 100.0"],
        returns="float",
        docstring="Calculate discounted price with maximum cap.",
        is_async=False,
    )

    # Generate test
    template = TestTemplate()
    test_code = template.render_function_test(func, module_path="pricing.discounts")

    print(test_code)


def example_class_test():
    """Generate tests for a custom class spec."""
    print("\n=== Class Test Template ===")

    # Create a class specification
    cls = ClassSpec(
        name="ShoppingCart",
        bases=["BaseCart"],
        docstring="Shopping cart with item management.",
        is_dataclass=False,
    )

    # Add methods
    cls.methods = [
        FunctionSpec(
            name="add_item",
            params=["self", "item: Item", "quantity: int = 1"],
            returns="None",
            docstring="Add item to cart.",
        ),
        FunctionSpec(
            name="remove_item",
            params=["self", "item_id: str"],
            returns="bool",
            docstring="Remove item from cart.",
        ),
        FunctionSpec(
            name="get_total",
            params=["self"],
            returns="float",
            docstring="Calculate total price.",
        ),
    ]

    # Generate test
    template = TestTemplate()
    test_code = template.render_class_test(cls, module_path="cart.shopping")

    print(test_code)


def example_dataclass_test():
    """Generate tests for a dataclass."""
    print("\n=== Dataclass Test Template ===")

    # Create a dataclass specification
    cls = ClassSpec(
        name="Product",
        bases=[],
        docstring="Product data class.",
        is_dataclass=True,
    )

    cls.fields = [
        ("id", "str", None),
        ("name", "str", None),
        ("price", "float", None),
        ("quantity", "int", "0"),
        ("active", "bool", "True"),
    ]

    # Generate test
    template = TestTemplate()
    test_code = template.render_dataclass_test(cls, module_path="models.product")

    print(test_code)


def example_async_function_test():
    """Generate test for an async function."""
    print("\n=== Async Function Test ===")

    func = FunctionSpec(
        name="fetch_user_data",
        params=["user_id: str", "include_details: bool = False"],
        returns="UserData",
        docstring="Fetch user data from API.",
        is_async=True,
    )

    template = TestTemplate()
    test_code = template.render_function_test(func, module_path="api.users")

    print(test_code)


if __name__ == "__main__":
    print("Logic2Test Custom Templates Examples\n")

    example_function_test()
    example_class_test()
    example_dataclass_test()
    example_async_function_test()
