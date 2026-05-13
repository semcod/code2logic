"""
Sample algorithms module for reproduction testing.

Contains common algorithms to test code logic reproduction.
"""

from typing import List, Generator, TypeVar
from functools import lru_cache

T = TypeVar("T")


def binary_search(arr: List[int], target: int) -> int:
    """Binary search implementation.

    Args:
        arr: Sorted list of integers
        target: Value to find

    Returns:
        Index of target or -1 if not found
    """
    left, right = 0, len(arr) - 1

    while left <= right:
        mid = (left + right) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1

    return -1


def quicksort(arr: List[int]) -> List[int]:
    """Quicksort implementation.

    Args:
        arr: List to sort

    Returns:
        Sorted list
    """
    if len(arr) <= 1:
        return arr

    pivot = arr[len(arr) // 2]
    left = [x for x in arr if x < pivot]
    middle = [x for x in arr if x == pivot]
    right = [x for x in arr if x > pivot]

    return quicksort(left) + middle + quicksort(right)


def merge_sort(arr: List[int]) -> List[int]:
    """Merge sort implementation.

    Args:
        arr: List to sort

    Returns:
        Sorted list
    """
    if len(arr) <= 1:
        return arr

    mid = len(arr) // 2
    left = merge_sort(arr[:mid])
    right = merge_sort(arr[mid:])

    return _merge(left, right)


def _merge(left: List[int], right: List[int]) -> List[int]:
    """Merge two sorted lists."""
    result = []
    i = j = 0

    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            result.append(left[i])
            i += 1
        else:
            result.append(right[j])
            j += 1

    result.extend(left[i:])
    result.extend(right[j:])
    return result


@lru_cache(maxsize=100)
def fibonacci(n: int) -> int:
    """Calculate nth Fibonacci number with memoization.

    Args:
        n: Position in Fibonacci sequence

    Returns:
        nth Fibonacci number
    """
    if n <= 1:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)


def fibonacci_generator(limit: int) -> Generator[int, None, None]:
    """Generate Fibonacci numbers up to limit.

    Args:
        limit: Maximum value to generate

    Yields:
        Fibonacci numbers
    """
    a, b = 0, 1
    while a <= limit:
        yield a
        a, b = b, a + b


def is_prime(n: int) -> bool:
    """Check if number is prime.

    Args:
        n: Number to check

    Returns:
        True if prime, False otherwise
    """
    if n < 2:
        return False
    if n == 2:
        return True
    if n % 2 == 0:
        return False

    for i in range(3, int(n**0.5) + 1, 2):
        if n % i == 0:
            return False
    return True


def sieve_of_eratosthenes(limit: int) -> List[int]:
    """Generate all primes up to limit using Sieve of Eratosthenes.

    Args:
        limit: Upper bound for primes

    Returns:
        List of prime numbers
    """
    if limit < 2:
        return []

    is_prime_arr = [True] * (limit + 1)
    is_prime_arr[0] = is_prime_arr[1] = False

    for i in range(2, int(limit**0.5) + 1):
        if is_prime_arr[i]:
            for j in range(i * i, limit + 1, i):
                is_prime_arr[j] = False

    return [i for i, prime in enumerate(is_prime_arr) if prime]


def gcd(a: int, b: int) -> int:
    """Calculate greatest common divisor using Euclidean algorithm.

    Args:
        a: First number
        b: Second number

    Returns:
        GCD of a and b
    """
    while b:
        a, b = b, a % b
    return a


def lcm(a: int, b: int) -> int:
    """Calculate least common multiple.

    Args:
        a: First number
        b: Second number

    Returns:
        LCM of a and b
    """
    return abs(a * b) // gcd(a, b)


def levenshtein_distance(s1: str, s2: str) -> int:
    """Calculate Levenshtein (edit) distance between two strings.

    Args:
        s1: First string
        s2: Second string

    Returns:
        Minimum number of edits to transform s1 to s2
    """
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)

    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def knapsack_01(weights: List[int], values: List[int], capacity: int) -> int:
    """Solve 0/1 knapsack problem using dynamic programming.

    Args:
        weights: List of item weights
        values: List of item values
        capacity: Knapsack capacity

    Returns:
        Maximum value that can be achieved
    """
    n = len(weights)
    dp = [[0] * (capacity + 1) for _ in range(n + 1)]

    for i in range(1, n + 1):
        for w in range(capacity + 1):
            if weights[i - 1] <= w:
                dp[i][w] = max(
                    values[i - 1] + dp[i - 1][w - weights[i - 1]], dp[i - 1][w]
                )
            else:
                dp[i][w] = dp[i - 1][w]

    return dp[n][capacity]
