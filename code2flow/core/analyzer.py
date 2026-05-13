# Backward-compat shim: code2flow.core.analyzer stubs
from __future__ import annotations

import fnmatch
import hashlib
import pickle
import time
from pathlib import Path
from typing import Any

from code2flow.core.config import FilterConfig


class FileCache:
    """Simple file-content-keyed cache with TTL."""

    def __init__(self, cache_dir: str | None = None, ttl_hours: float = 24) -> None:
        self.cache_dir = cache_dir or str(Path.home() / ".cache" / "code2flow")
        self.ttl_seconds = ttl_hours * 3600
        Path(self.cache_dir).mkdir(parents=True, exist_ok=True)

    def _key_path(self, file_path: str, content: str) -> Path:
        key = hashlib.md5(f"{file_path}:{content}".encode()).hexdigest()
        return Path(self.cache_dir) / f"{key}.pkl"

    def get(self, file_path: str, content: str) -> Any | None:
        p = self._key_path(file_path, content)
        if not p.exists():
            return None
        if self.ttl_seconds == 0:
            return None
        age = time.time() - p.stat().st_mtime
        if age > self.ttl_seconds:
            return None
        with p.open("rb") as f:
            return pickle.load(f)

    def put(self, file_path: str, content: str, data: Any) -> None:
        p = self._key_path(file_path, content)
        with p.open("wb") as f:
            pickle.dump(data, f)

    def clear(self) -> None:
        for p in Path(self.cache_dir).glob("*.pkl"):
            p.unlink(missing_ok=True)


class FastFileFilter:
    """Simple file/function filter backed by FilterConfig."""

    def __init__(self, config: FilterConfig) -> None:
        self.config = config

    def should_process(self, file_path: str) -> bool:
        name = Path(file_path).name
        if self.config.exclude_tests:
            if name.startswith("test_") or name.endswith("_test.py"):
                return False
        for pat in self.config.exclude_patterns:
            if fnmatch.fnmatch(name, pat):
                return False
        return True

    def should_skip_function(
        self,
        name: str,
        lines: int,
        is_private: bool = False,
        is_property: bool = False,
    ) -> bool:
        if self.config.skip_private and is_private:
            return True
        if self.config.skip_properties and is_property:
            return True
        if lines < self.config.min_function_lines:
            return True
        return False
