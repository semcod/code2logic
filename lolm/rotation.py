"""
LLM Provider Rotation with Rate Limit Detection and Dynamic Prioritization.

Provides automatic failover, rate limit detection, cooldown management,
and priority queue for LLM providers.
"""

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

CONSTANT_3 = 3
CONSTANT_5 = 5
CONSTANT_20 = 20
MIN_25 = 25
CONSTANT_30 = 30
MIN_50 = 50
MIN_60 = 60
CONSTANT_200 = 200
CONSTANT_429 = 429
CONSTANT_3600 = 3600
MAX_4000 = 4000
CONSTANT_86400 = 86400


CONSTANT_3 = CONSTANT_3
CONSTANT_5 = CONSTANT_5
CONSTANT_20 = CONSTANT_20
MIN_25 = MIN_25
CONSTANT_30 = CONSTANT_30
MIN_50 = MIN_50
MIN_60 = MIN_60
CONSTANT_200 = CONSTANT_200
CONSTANT_429 = CONSTANT_429
CONSTANT_3600 = CONSTANT_3600
MAX_4000 = MAX_4000
CONSTANT_86400 = CONSTANT_86400


CONSTANT_3 = CONSTANT_3
CONSTANT_5 = CONSTANT_5
CONSTANT_20 = CONSTANT_20
MIN_25 = MIN_25
CONSTANT_30 = CONSTANT_30
MIN_50 = MIN_50
MIN_60 = MIN_60
CONSTANT_200 = CONSTANT_200
CONSTANT_429 = CONSTANT_429
CONSTANT_3600 = CONSTANT_3600
MAX_4000 = MAX_4000
CONSTANT_86400 = CONSTANT_86400


CONSTANT_3 = CONSTANT_3
CONSTANT_5 = CONSTANT_5
CONSTANT_20 = CONSTANT_20
MIN_25 = MIN_25
CONSTANT_30 = CONSTANT_30
MIN_50 = MIN_50
MIN_60 = MIN_60
CONSTANT_200 = CONSTANT_200
CONSTANT_429 = CONSTANT_429
CONSTANT_3600 = CONSTANT_3600
MAX_4000 = MAX_4000
CONSTANT_86400 = CONSTANT_86400


class ProviderState(str, Enum):
    """Provider availability state."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"  # Some failures but still usable
    RATE_LIMITED = "rate_limited"
    UNAVAILABLE = "unavailable"
    COOLING_DOWN = "cooling_down"


class RateLimitType(str, Enum):
    """Type of rate limit encountered."""

    REQUESTS_PER_MINUTE = "rpm"
    REQUESTS_PER_DAY = "rpd"
    TOKENS_PER_MINUTE = "tpm"
    TOKENS_PER_DAY = "tpd"
    CONCURRENT = "concurrent"
    QUOTA_EXCEEDED = "quota"
    UNKNOWN = "unknown"


@dataclass
class RateLimitInfo:
    """Information about a rate limit event."""

    limit_type: RateLimitType
    limit_value: Optional[int] = None
    remaining: Optional[int] = None
    reset_at: Optional[datetime] = None
    retry_after_seconds: Optional[float] = None
    raw_headers: Dict[str, str] = field(default_factory=dict)

    def get_wait_seconds(self) -> float:
        """Calculate how long to wait before retrying."""
        if self.retry_after_seconds:
            return self.retry_after_seconds
        if self.reset_at:
            wait = (self.reset_at - datetime.now()).total_seconds()
            return max(0, wait)
        # Default backoff based on limit type
        defaults = {
            RateLimitType.REQUESTS_PER_MINUTE: MIN_60,
            RateLimitType.TOKENS_PER_MINUTE: MIN_60,
            RateLimitType.REQUESTS_PER_DAY: CONSTANT_3600,
            RateLimitType.TOKENS_PER_DAY: CONSTANT_3600,
            RateLimitType.QUOTA_EXCEEDED: CONSTANT_86400,  # 24h for quota
            RateLimitType.CONCURRENT: CONSTANT_5,
            RateLimitType.UNKNOWN: CONSTANT_30,
        }
        return defaults.get(self.limit_type, MIN_60)


@dataclass
class ProviderHealth:
    """Health metrics for a provider."""

    provider_name: str
    state: ProviderState = ProviderState.HEALTHY
    base_priority: int = 100
    current_priority: int = 100

    # Success/failure tracking
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    consecutive_failures: int = 0
    last_success: Optional[datetime] = None
    last_failure: Optional[datetime] = None
    last_error: Optional[str] = None

    # Rate limit tracking
    rate_limit_hits: int = 0
    last_rate_limit: Optional[RateLimitInfo] = None
    cooldown_until: Optional[datetime] = None

    # Latency tracking (in ms)
    avg_latency_ms: float = 0.0
    latency_samples: int = 0

    def success_rate(self) -> float:
        """Calculate success rate (0.0 - 1.0)."""
        if self.total_requests == 0:
            return 1.0
        return self.successful_requests / self.total_requests

    def is_available(self) -> bool:
        """Check if provider is currently available."""
        if self.state in (ProviderState.UNAVAILABLE, ProviderState.RATE_LIMITED):
            return False
        if self.cooldown_until and datetime.now() < self.cooldown_until:
            return False
        return True

    def record_success(self, latency_ms: float = 0) -> None:
        """Record a successful request."""
        self.total_requests += 1
        self.successful_requests += 1
        self.consecutive_failures = 0
        self.last_success = datetime.now()

        # Update latency average
        if latency_ms > 0:
            self.latency_samples += 1
            self.avg_latency_ms = (
                self.avg_latency_ms * (self.latency_samples - 1) + latency_ms
            ) / self.latency_samples

        # Recover priority if healthy
        if self.state == ProviderState.DEGRADED:
            if self.consecutive_failures == 0 and self.success_rate() > 0.9:
                self.state = ProviderState.HEALTHY
                self._adjust_priority()

    def record_failure(
        self,
        error: str,
        is_rate_limit: bool = False,
        rate_limit_info: Optional[RateLimitInfo] = None,
    ) -> None:
        """Record a failed request."""
        self.total_requests += 1
        self.failed_requests += 1
        self.consecutive_failures += 1
        self.last_failure = datetime.now()
        self.last_error = error

        if is_rate_limit:
            self.rate_limit_hits += 1
            self.last_rate_limit = rate_limit_info
            self.state = ProviderState.RATE_LIMITED

            # Set cooldown
            if rate_limit_info:
                wait_seconds = rate_limit_info.get_wait_seconds()
                self.cooldown_until = datetime.now() + timedelta(seconds=wait_seconds)
            else:
                # Default 60 second cooldown
                self.cooldown_until = datetime.now() + timedelta(seconds=MIN_60)
        else:
            # Non-rate-limit failure
            if self.consecutive_failures >= CONSTANT_3:
                self.state = ProviderState.UNAVAILABLE
            elif self.consecutive_failures >= 1:
                self.state = ProviderState.DEGRADED

        self._adjust_priority()

    def _adjust_priority(self) -> None:
        """Adjust current priority based on health."""
        penalty = 0

        # Penalty for failures
        if self.consecutive_failures > 0:
            penalty += min(self.consecutive_failures * 10, MIN_50)

        # Penalty for low success rate
        if self.success_rate() < 0.9:
            penalty += int((1 - self.success_rate()) * CONSTANT_30)

        # Penalty for rate limits
        penalty += min(self.rate_limit_hits * CONSTANT_5, MIN_25)

        # Penalty for state
        state_penalties = {
            ProviderState.HEALTHY: 0,
            ProviderState.DEGRADED: CONSTANT_20,
            ProviderState.COOLING_DOWN: MIN_50,
            ProviderState.RATE_LIMITED: 100,
            ProviderState.UNAVAILABLE: CONSTANT_200,
        }
        penalty += state_penalties.get(self.state, 0)

        self.current_priority = self.base_priority + penalty

    def check_cooldown(self) -> bool:
        """Check if cooldown has expired and update state."""
        if self.cooldown_until and datetime.now() >= self.cooldown_until:
            self.cooldown_until = None
            if self.state in (ProviderState.RATE_LIMITED, ProviderState.COOLING_DOWN):
                self.state = ProviderState.DEGRADED
                self._adjust_priority()
            return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "provider": self.provider_name,
            "state": self.state.value,
            "base_priority": self.base_priority,
            "current_priority": self.current_priority,
            "total_requests": self.total_requests,
            "success_rate": round(self.success_rate(), CONSTANT_3),
            "consecutive_failures": self.consecutive_failures,
            "rate_limit_hits": self.rate_limit_hits,
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "is_available": self.is_available(),
            "cooldown_until": self.cooldown_until.isoformat() if self.cooldown_until else None,
            "last_error": self.last_error,
        }


class RotationQueue:
    """
    Priority queue for LLM provider rotation with automatic failover.

    Features:
    - Dynamic priority adjustment based on health
    - Rate limit detection and cooldown
    - Automatic rotation on failure
    - Thread-safe operations

    Usage:
        queue = RotationQueue()
        queue.add_provider("openrouter", priority=10)
        queue.add_provider("groq", priority=20)
        queue.add_provider("ollama", priority=15)

        # Get next available provider
        provider = queue.get_next()

        # Record success/failure
        queue.record_success("openrouter", latency_ms=150)
        queue.record_failure("groq", "Rate limit exceeded", is_rate_limit=True)
    """

    def __init__(
        self,
        max_consecutive_failures: int = CONSTANT_3,
        default_cooldown_seconds: float = MIN_60,
        enable_health_recovery: bool = True,
    ):
        self._providers: Dict[str, ProviderHealth] = {}
        self._lock = threading.RLock()
        self._max_failures = max_consecutive_failures
        self._default_cooldown = default_cooldown_seconds
        self._enable_recovery = enable_health_recovery

        # Event callbacks
        self._on_provider_unavailable: Optional[Callable[[str, str], None]] = None
        self._on_rate_limit: Optional[Callable[[str, RateLimitInfo], None]] = None
        self._on_rotation: Optional[Callable[[str, str], None]] = None

    def add_provider(self, name: str, priority: int = 100) -> None:
        """Add a provider to the rotation queue."""
        with self._lock:
            self._providers[name] = ProviderHealth(
                provider_name=name,
                base_priority=priority,
                current_priority=priority,
            )

    def remove_provider(self, name: str) -> bool:
        """Remove a provider from the queue."""
        with self._lock:
            if name in self._providers:
                del self._providers[name]
                return True
            return False

    def set_priority(self, name: str, priority: int) -> bool:
        """Set base priority for a provider (lower = higher priority)."""
        with self._lock:
            if name in self._providers:
                health = self._providers[name]
                health.base_priority = priority
                health._adjust_priority()
                return True
            return False

    def get_priority_order(self) -> List[str]:
        """Get providers ordered by current priority."""
        with self._lock:
            # Check cooldowns first
            for health in self._providers.values():
                health.check_cooldown()

            # Sort by priority (lower = higher priority), then by availability
            available = [
                (h.current_priority, h.provider_name)
                for h in self._providers.values()
                if h.is_available()
            ]
            unavailable = [
                (h.current_priority, h.provider_name)
                for h in self._providers.values()
                if not h.is_available()
            ]

            available.sort()
            unavailable.sort()

            return [name for _, name in available] + [name for _, name in unavailable]

    def get_next(self) -> Optional[str]:
        """Get the next available provider with highest priority."""
        with self._lock:
            for health in self._providers.values():
                health.check_cooldown()

            available = [
                (h.current_priority, h.provider_name)
                for h in self._providers.values()
                if h.is_available()
            ]

            if not available:
                return None

            available.sort()
            return available[0][1]

    def get_available(self) -> List[str]:
        """Get all available providers in priority order."""
        with self._lock:
            for health in self._providers.values():
                health.check_cooldown()

            available = [
                (h.current_priority, h.provider_name)
                for h in self._providers.values()
                if h.is_available()
            ]
            available.sort()
            return [name for _, name in available]

    def record_success(self, name: str, latency_ms: float = 0) -> None:
        """Record a successful request for a provider."""
        with self._lock:
            if name in self._providers:
                self._providers[name].record_success(latency_ms)

    def record_failure(
        self,
        name: str,
        error: str,
        is_rate_limit: bool = False,
        rate_limit_info: Optional[RateLimitInfo] = None,
    ) -> None:
        """Record a failed request for a provider."""
        with self._lock:
            if name not in self._providers:
                return

            health = self._providers[name]
            old_state = health.state
            health.record_failure(error, is_rate_limit, rate_limit_info)

            # Trigger callbacks
            if is_rate_limit and self._on_rate_limit and rate_limit_info:
                self._on_rate_limit(name, rate_limit_info)

            if health.state == ProviderState.UNAVAILABLE and old_state != ProviderState.UNAVAILABLE:
                if self._on_provider_unavailable:
                    self._on_provider_unavailable(name, error)

                # Trigger rotation callback
                next_provider = self.get_next()
                if next_provider and self._on_rotation:
                    self._on_rotation(name, next_provider)

    def mark_rate_limited(
        self,
        name: str,
        rate_limit_info: Optional[RateLimitInfo] = None,
        cooldown_seconds: Optional[float] = None,
    ) -> None:
        """Manually mark a provider as rate limited."""
        with self._lock:
            if name not in self._providers:
                return

            health = self._providers[name]
            health.state = ProviderState.RATE_LIMITED
            health.rate_limit_hits += 1
            health.last_rate_limit = rate_limit_info

            if cooldown_seconds:
                health.cooldown_until = datetime.now() + timedelta(seconds=cooldown_seconds)
            elif rate_limit_info:
                wait = rate_limit_info.get_wait_seconds()
                health.cooldown_until = datetime.now() + timedelta(seconds=wait)
            else:
                health.cooldown_until = datetime.now() + timedelta(seconds=self._default_cooldown)

            health._adjust_priority()

    def reset_provider(self, name: str) -> bool:
        """Reset a provider's health metrics."""
        with self._lock:
            if name not in self._providers:
                return False

            health = self._providers[name]
            health.state = ProviderState.HEALTHY
            health.consecutive_failures = 0
            health.cooldown_until = None
            health.current_priority = health.base_priority
            return True

    def reset_all(self) -> None:
        """Reset all providers' health metrics."""
        with self._lock:
            for health in self._providers.values():
                health.state = ProviderState.HEALTHY
                health.consecutive_failures = 0
                health.cooldown_until = None
                health.current_priority = health.base_priority

    def get_health(self, name: str) -> Optional[ProviderHealth]:
        """Get health info for a specific provider."""
        with self._lock:
            return self._providers.get(name)

    def get_all_health(self) -> Dict[str, Dict[str, Any]]:
        """Get health info for all providers."""
        with self._lock:
            return {name: health.to_dict() for name, health in self._providers.items()}

    def get_status(self) -> Dict[str, Any]:
        """Get overall queue status."""
        with self._lock:
            available = [n for n, h in self._providers.items() if h.is_available()]
            unavailable = [n for n, h in self._providers.items() if not h.is_available()]

            return {
                "total_providers": len(self._providers),
                "available_count": len(available),
                "unavailable_count": len(unavailable),
                "available_providers": available,
                "unavailable_providers": unavailable,
                "priority_order": self.get_priority_order(),
                "next_provider": self.get_next(),
            }

    # Event handler setters
    def on_provider_unavailable(self, callback: Callable[[str, str], None]) -> None:
        """Set callback for when a provider becomes unavailable."""
        self._on_provider_unavailable = callback

    def on_rate_limit(self, callback: Callable[[str, RateLimitInfo], None]) -> None:
        """Set callback for rate limit events."""
        self._on_rate_limit = callback

    def on_rotation(self, callback: Callable[[str, str], None]) -> None:
        """Set callback for provider rotation events."""
        self._on_rotation = callback


def parse_rate_limit_headers(headers: Dict[str, str]) -> Optional[RateLimitInfo]:
    """
    Parse rate limit information from HTTP response headers.

    Supports common patterns:
    - x-ratelimit-limit-requests / x-ratelimit-remaining-requests
    - x-ratelimit-limit-tokens / x-ratelimit-remaining-tokens
    - retry-after
    - OpenAI/OpenRouter specific headers
    """
    if not headers:
        return None

    # Normalize header names to lowercase
    headers_lower = {k.lower(): v for k, v in headers.items()}

    info = RateLimitInfo(
        limit_type=RateLimitType.UNKNOWN,
        raw_headers=headers,
    )

    # Check for retry-after header
    retry_after = headers_lower.get("retry-after")
    if retry_after:
        try:
            info.retry_after_seconds = float(retry_after)
        except ValueError:
            pass

    # OpenAI/OpenRouter style headers
    if "x-ratelimit-limit-requests" in headers_lower:
        info.limit_type = RateLimitType.REQUESTS_PER_MINUTE
        try:
            info.limit_value = int(headers_lower.get("x-ratelimit-limit-requests", 0))
            info.remaining = int(headers_lower.get("x-ratelimit-remaining-requests", 0))
        except ValueError:
            pass

        reset = headers_lower.get("x-ratelimit-reset-requests")
        if reset:
            try:
                # Could be seconds or ISO timestamp
                if reset.isdigit():
                    info.reset_at = datetime.now() + timedelta(seconds=int(reset))
                elif "s" in reset:
                    # Format like "1s" or "60s"
                    seconds = float(reset.replace("s", "").replace("ms", ""))
                    if "ms" in reset:
                        seconds /= 1000
                    info.reset_at = datetime.now() + timedelta(seconds=seconds)
            except (ValueError, AttributeError):
                pass

    # Token-based rate limiting
    elif "x-ratelimit-limit-tokens" in headers_lower:
        info.limit_type = RateLimitType.TOKENS_PER_MINUTE
        try:
            info.limit_value = int(headers_lower.get("x-ratelimit-limit-tokens", 0))
            info.remaining = int(headers_lower.get("x-ratelimit-remaining-tokens", 0))
        except ValueError:
            pass

    # Groq specific
    elif "x-groq-ratelimit-limit-requests" in headers_lower:
        info.limit_type = RateLimitType.REQUESTS_PER_MINUTE
        try:
            info.limit_value = int(headers_lower.get("x-groq-ratelimit-limit-requests", 0))
            info.remaining = int(headers_lower.get("x-groq-ratelimit-remaining-requests", 0))
        except ValueError:
            pass

    return info


def is_rate_limit_error(status_code: int = None, error_message: str = None) -> bool:
    """Check if an error indicates a rate limit."""
    if status_code == CONSTANT_429:
        return True

    if error_message:
        error_lower = error_message.lower()
        rate_limit_phrases = [
            "rate limit",
            "rate_limit",
            "ratelimit",
            "too many requests",
            "quota exceeded",
            "request limit",
            "throttl",
        ]
        return any(phrase in error_lower for phrase in rate_limit_phrases)

    return False


class LLMRotationManager:
    """
    High-level manager for LLM rotation with generation capabilities.

    Combines RotationQueue with actual LLM generation, providing
    automatic failover and rate limit handling.

    Usage:
        from lolm.rotation import LLMRotationManager
        from lolm.clients import OpenRouterClient, GroqClient

        manager = LLMRotationManager()
        manager.register("openrouter", OpenRouterClient(), priority=10)
        manager.register("groq", GroqClient(), priority=20)

        # Generate with automatic failover
        response = manager.generate("Explain Python decorators")
    """

    def __init__(
        self, max_retries: int = CONSTANT_3, default_cooldown: float = MIN_60, verbose: bool = False
    ):
        self._queue = RotationQueue(default_cooldown_seconds=default_cooldown)
        self._clients: Dict[str, Any] = {}  # BaseLLMClient instances
        self._max_retries = max_retries
        self._verbose = verbose
        self._lock = threading.RLock()

    def register(self, name: str, client: Any, priority: int = 100) -> None:
        """Register an LLM client with the rotation manager."""
        with self._lock:
            self._clients[name] = client
            self._queue.add_provider(name, priority)

    def unregister(self, name: str) -> bool:
        """Unregister a client."""
        with self._lock:
            if name in self._clients:
                del self._clients[name]
                self._queue.remove_provider(name)
                return True
            return False

    def set_priority(self, name: str, priority: int) -> bool:
        """Set priority for a provider."""
        return self._queue.set_priority(name, priority)

    def generate(
        self,
        prompt: str,
        system: str = None,
        max_tokens: int = MAX_4000,
        preferred_provider: str = None,
    ) -> str:
        """
        Generate completion with automatic rotation on failure.

        Args:
            prompt: User prompt
            system: System prompt
            max_tokens: Maximum tokens
            preferred_provider: Try this provider first

        Returns:
            Generated text

        Raises:
            RuntimeError: If all providers fail
        """
        providers_to_try = self._queue.get_available()

        # Put preferred provider first if specified
        if preferred_provider and preferred_provider in providers_to_try:
            providers_to_try.remove(preferred_provider)
            providers_to_try.insert(0, preferred_provider)

        last_error = None
        attempts = 0

        for provider_name in providers_to_try:
            if attempts >= self._max_retries:
                break

            client = self._clients.get(provider_name)
            if not client:
                continue

            attempts += 1
            start_time = time.time()

            try:
                result = client.generate(prompt, system=system, max_tokens=max_tokens)
                latency_ms = (time.time() - start_time) * 1000
                self._queue.record_success(provider_name, latency_ms)
                return result

            except Exception as e:
                error_str = str(e)
                latency_ms = (time.time() - start_time) * 1000

                # Check for rate limit
                is_rate_limit = is_rate_limit_error(error_message=error_str)

                # Try to extract rate limit info from error
                rate_limit_info = None
                if is_rate_limit:
                    rate_limit_info = RateLimitInfo(limit_type=RateLimitType.UNKNOWN)
                    # Try to parse retry-after from error message
                    if "retry after" in error_str.lower():
                        try:
                            import re

                            match = re.search(r"retry.+?(\d+)", error_str.lower())
                            if match:
                                rate_limit_info.retry_after_seconds = float(match.group(1))
                        except:
                            pass

                self._queue.record_failure(
                    provider_name,
                    error_str,
                    is_rate_limit=is_rate_limit,
                    rate_limit_info=rate_limit_info,
                )

                if self._verbose:
                    print(f"[LLMRotation] {provider_name} failed: {error_str}")

                last_error = e
                continue

        raise RuntimeError(
            f"All providers failed after {attempts} attempts. Last error: {last_error}"
        )

    def get_queue(self) -> RotationQueue:
        """Get the underlying rotation queue for advanced control."""
        return self._queue

    def get_status(self) -> Dict[str, Any]:
        """Get rotation manager status."""
        return {
            "queue": self._queue.get_status(),
            "health": self._queue.get_all_health(),
            "registered_clients": list(self._clients.keys()),
        }

    def reset(self) -> None:
        """Reset all provider health metrics."""
        self._queue.reset_all()


# Convenience function
def create_rotation_manager(
    providers: Dict[str, Tuple[Any, int]] = None, verbose: bool = False
) -> LLMRotationManager:
    """
    Create a rotation manager with providers.

    Args:
        providers: Dict of {name: (client, priority)}
        verbose: Enable verbose logging

    Returns:
        Configured LLMRotationManager
    """
    manager = LLMRotationManager(verbose=verbose)

    if providers:
        for name, (client, priority) in providers.items():
            manager.register(name, client, priority)

    return manager
