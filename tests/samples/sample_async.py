"""
Sample async Python module for reproduction testing.

Tests async/await patterns, context managers, and concurrent execution.
"""

import asyncio
from typing import List, Dict, Optional, Any, TypeVar
from dataclasses import dataclass
from datetime import datetime
from contextlib import asynccontextmanager

T = TypeVar("T")


@dataclass
class Task:
    """Async task with status tracking."""

    id: str
    name: str
    status: str = "pending"
    result: Optional[Any] = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


@dataclass
class TaskResult:
    """Result of task execution."""

    task_id: str
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    duration_ms: float = 0.0


class AsyncTaskQueue:
    """Async task queue with concurrency control."""

    def __init__(self, max_concurrent: int = 5):
        self._tasks: Dict[str, Task] = {}
        self._queue: asyncio.Queue = asyncio.Queue()
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._results: Dict[str, TaskResult] = {}

    async def add_task(self, task: Task) -> None:
        """Add task to queue."""
        self._tasks[task.id] = task
        await self._queue.put(task.id)

    async def get_task(self, task_id: str) -> Optional[Task]:
        """Get task by ID."""
        return self._tasks.get(task_id)

    async def process_task(self, task_id: str, handler) -> TaskResult:
        """Process a single task with semaphore."""
        async with self._semaphore:
            task = self._tasks.get(task_id)
            if not task:
                return TaskResult(
                    task_id=task_id, success=False, error="Task not found"
                )

            task.status = "running"
            task.started_at = datetime.now().isoformat()
            start = asyncio.get_event_loop().time()

            try:
                result = await handler(task)
                task.status = "completed"
                task.result = result

                return TaskResult(
                    task_id=task_id,
                    success=True,
                    data=result,
                    duration_ms=(asyncio.get_event_loop().time() - start) * 1000,
                )
            except Exception as e:
                task.status = "failed"
                task.error = str(e)

                return TaskResult(
                    task_id=task_id,
                    success=False,
                    error=str(e),
                    duration_ms=(asyncio.get_event_loop().time() - start) * 1000,
                )
            finally:
                task.completed_at = datetime.now().isoformat()

    async def process_all(self, handler) -> List[TaskResult]:
        """Process all tasks in queue concurrently."""
        results = []
        tasks = []

        while not self._queue.empty():
            task_id = await self._queue.get()
            tasks.append(self.process_task(task_id, handler))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)

        return [r for r in results if isinstance(r, TaskResult)]


class AsyncCache:
    """Simple async cache with TTL."""

    def __init__(self, ttl_seconds: int = 300):
        self._cache: Dict[str, tuple] = {}
        self._ttl = ttl_seconds
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        async with self._lock:
            if key in self._cache:
                value, timestamp = self._cache[key]
                if (datetime.now().timestamp() - timestamp) < self._ttl:
                    return value
                del self._cache[key]
        return None

    async def set(self, key: str, value: Any) -> None:
        """Set value in cache."""
        async with self._lock:
            self._cache[key] = (value, datetime.now().timestamp())

    async def delete(self, key: str) -> bool:
        """Delete value from cache."""
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
        return False

    async def clear(self) -> None:
        """Clear all cache entries."""
        async with self._lock:
            self._cache.clear()


@asynccontextmanager
async def async_timer(name: str = "operation"):
    """Async context manager for timing operations."""
    start = asyncio.get_event_loop().time()
    try:
        yield
    finally:
        elapsed = (asyncio.get_event_loop().time() - start) * 1000
        print(f"{name} took {elapsed:.2f}ms")


async def fetch_with_retry(
    url: str, max_retries: int = 3, delay: float = 1.0
) -> Dict[str, Any]:
    """Fetch URL with retry logic."""
    last_error = None

    for attempt in range(max_retries):
        try:
            # Simulated fetch
            await asyncio.sleep(0.1)
            return {"url": url, "status": "ok", "attempt": attempt + 1}
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                await asyncio.sleep(delay * (attempt + 1))

    raise last_error or Exception("Max retries exceeded")


async def parallel_map(items: List[T], handler, max_concurrent: int = 5) -> List[Any]:
    """Apply handler to items in parallel with concurrency limit."""
    semaphore = asyncio.Semaphore(max_concurrent)

    async def process(item: T) -> Any:
        async with semaphore:
            return await handler(item)

    return await asyncio.gather(*[process(item) for item in items])


async def race(*coroutines) -> Any:
    """Return result of first completed coroutine."""
    done, pending = await asyncio.wait(
        [asyncio.create_task(c) for c in coroutines],
        return_when=asyncio.FIRST_COMPLETED,
    )

    # Cancel pending
    for task in pending:
        task.cancel()

    # Return first result
    return done.pop().result()


async def timeout_wrapper(coro, timeout_seconds: float, default=None):
    """Wrap coroutine with timeout, return default on timeout."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        return default
