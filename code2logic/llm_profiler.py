"""
LLM Profiler for Adaptive Code Reproduction.

Profiles LLM capabilities and enables adaptive chunking/format selection:
- Input capacity: effective context window for code tasks
- Output stability: consistency of generated code
- Error modes: hallucinations, omissions, creative rewrites
- Repair ability: patch mode vs full regeneration

Profiles are stored in ~/.code2logic/llm_profiles.json

Usage:
    from code2logic.llm_profiler import LLMProfiler, get_profile, AdaptiveChunker

    # Profile a model
    profiler = LLMProfiler(client)
    profile = profiler.run_profile()

    # Use adaptive chunking
    chunker = AdaptiveChunker(profile)
    chunks = chunker.chunk_spec(spec, format='yaml')
"""

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Optional

from .utils import estimate_tokens

# Test cases for profiling
PROFILE_TEST_CASES = {
    "simple_function": '''
def calculate_sum(numbers: List[int]) -> int:
    """Calculate sum of numbers."""
    return sum(numbers)
''',
    "class_with_methods": '''
class DataProcessor:
    """Process data with validation."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._cache: dict[str, Any] = {}

    def process(self, data: list[dict]) -> list[dict]:
        """Process data items."""
        return [self._transform(item) for item in data]

    def _transform(self, item: Dict) -> Dict:
        """Transform single item."""
        return {k: v.strip() if isinstance(v, str) else v for k, v in item.items()}
''',
    "async_function": '''
async def fetch_data(url: str, timeout: int = 30) -> Dict[str, Any]:
    """Fetch data from URL with timeout."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()
''',
    "decorator_usage": '''
@dataclass
class User:
    """User model with validation."""
    id: int
    name: str
    email: str
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def display_name(self) -> str:
        return f"{self.name} <{self.email}>"

    @staticmethod
    def validate_email(email: str) -> bool:
        return "@" in email and "." in email
''',
    "complex_logic": '''
def merge_sorted_lists(list1: List[int], list2: List[int]) -> List[int]:
    """Merge two sorted lists into one sorted list."""
    result = []
    i = j = 0

    while i < len(list1) and j < len(list2):
        if list1[i] <= list2[j]:
            result.append(list1[i])
            i += 1
        else:
            result.append(list2[j])
            j += 1

    result.extend(list1[i:])
    result.extend(list2[j:])
    return result
''',
}


@dataclass
class LLMProfile:
    """Profile of LLM capabilities for code reproduction."""

    # Identification
    provider: str
    model: str
    profile_id: str = ""
    created_at: str = ""

    # Capacity metrics
    effective_context: int = 4000  # Tokens that work reliably
    max_output: int = 2000  # Max reliable output tokens
    optimal_chunk_size: int = 1500  # Best chunk size for accuracy

    # Quality metrics (0-1 scale)
    syntax_accuracy: float = 0.0  # Valid Python syntax rate
    semantic_accuracy: float = 0.0  # Code similarity to original
    type_hint_accuracy: float = 0.0  # Type hints preserved
    docstring_accuracy: float = 0.0  # Docstrings preserved

    # Stability metrics
    output_consistency: float = 0.0  # Same prompt → same output
    temperature_sensitivity: float = 0.0  # How much temp affects output

    # Error modes (frequencies 0-1)
    hallucination_rate: float = 0.0  # Invented functions/imports
    omission_rate: float = 0.0  # Missing elements
    rewrite_rate: float = 0.0  # Unnecessary rewrites

    # Capabilities
    supports_patch_mode: bool = False  # Can do diff-based edits
    supports_streaming: bool = True
    preferred_format: str = "yaml"  # Best format for this model

    # Recommendations
    recommended_formats: list[str] = field(default_factory=lambda: ["yaml", "toon"])
    chunk_strategy: str = "by_function"  # by_function, by_class, by_module

    # Test results
    test_results: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.profile_id:
            self.profile_id = hashlib.md5(
                f"{self.provider}:{self.model}".encode()
            ).hexdigest()[:12]
        if not self.created_at:
            self.created_at = datetime.now().isoformat()


@dataclass
class ProfileTestResult:
    """Result of a single profile test."""

    test_name: str
    original_code: str
    reproduced_code: str
    syntax_ok: bool
    similarity: float
    time_seconds: float
    tokens_in: int
    tokens_out: int
    error: str = ""


def _get_profiles_path() -> Path:
    """Get path to profiles storage."""
    config_dir = Path.home() / ".code2logic"
    config_dir.mkdir(exist_ok=True)
    return config_dir / "llm_profiles.json"


def load_profiles() -> dict[str, LLMProfile]:
    """Load all saved profiles."""
    path = _get_profiles_path()
    if not path.exists():
        return {}

    try:
        with open(path) as f:
            data = json.load(f)
        return {k: LLMProfile(**v) for k, v in data.items()}
    except (json.JSONDecodeError, TypeError):
        return {}


def save_profile(profile: LLMProfile) -> None:
    """Save a profile to storage."""
    profiles = load_profiles()
    profiles[profile.profile_id] = profile

    path = _get_profiles_path()
    with open(path, "w") as f:
        json.dump({k: asdict(v) for k, v in profiles.items()}, f, indent=2)


def get_profile(provider: str, model: str) -> Optional[LLMProfile]:
    """Get profile for a specific model."""
    profile_id = hashlib.md5(f"{provider}:{model}".encode()).hexdigest()[:12]
    profiles = load_profiles()
    return profiles.get(profile_id)


def get_or_create_profile(provider: str, model: str) -> LLMProfile:
    """Get existing profile or create default one."""
    profile = get_profile(provider, model)
    if profile:
        return profile

    # Create default profile based on known models
    return _create_default_profile(provider, model)


def _create_default_profile(provider: str, model: str) -> LLMProfile:
    """Create default profile based on model characteristics."""
    model_lower = model.lower()

    # Default values
    context = 4000
    chunk_size = 1500
    preferred_format = "yaml"

    # Adjust based on model
    if "gpt-4" in model_lower:
        context = 8000 if "turbo" not in model_lower else 32000
        chunk_size = 3000
        preferred_format = "yaml"
    elif "claude" in model_lower:
        context = 32000
        chunk_size = 4000
        preferred_format = "yaml"
    elif "qwen" in model_lower and "coder" in model_lower:
        context = 16000
        chunk_size = 3000
        preferred_format = "toon"
    elif "deepseek" in model_lower:
        context = 16000
        chunk_size = 3000
        preferred_format = "toon"
    elif "llama" in model_lower:
        if "70b" in model_lower:
            context = 4000
            chunk_size = 1500
        else:
            context = 2000
            chunk_size = 1000
        preferred_format = "yaml"
    elif "mistral" in model_lower or "mixtral" in model_lower:
        context = 8000
        chunk_size = 2500
        preferred_format = "yaml"

    return LLMProfile(
        provider=provider,
        model=model,
        effective_context=context,
        optimal_chunk_size=chunk_size,
        preferred_format=preferred_format,
        recommended_formats=[preferred_format, "yaml", "json"],
    )


class LLMProfiler:
    """
    Profile LLM capabilities for code reproduction.

    Runs standardized tests to measure:
    - Effective context window
    - Output accuracy and consistency
    - Error modes and failure patterns
    """

    def __init__(self, client, verbose: bool = True):
        """
        Initialize profiler.

        Args:
            client: LLM client with generate() method
            verbose: Print progress
        """
        self.client = client
        self.verbose = verbose
        self.provider = getattr(client, "provider", "unknown")
        self.model = getattr(client, "model", "unknown")

    def run_profile(self, quick: bool = False) -> LLMProfile:
        """
        Run full profiling suite.

        Args:
            quick: Run quick profile (fewer tests)

        Returns:
            LLMProfile with measured capabilities
        """
        profile = LLMProfile(
            provider=self.provider,
            model=self.model,
        )

        if self.verbose:
            print(f"Profiling {self.provider}/{self.model}...")

        # Run tests
        test_cases = list(PROFILE_TEST_CASES.items())
        if quick:
            test_cases = test_cases[:2]

        results = []
        for name, code in test_cases:
            if self.verbose:
                print(f"  Testing: {name}...", end=" ", flush=True)

            result = self._test_reproduction(name, code)
            results.append(result)

            if self.verbose:
                status = "✓" if result.syntax_ok else "✗"
                print(f"{status} ({result.similarity:.0%}, {result.time_seconds:.1f}s)")

        # Calculate metrics
        profile = self._calculate_metrics(profile, results)

        # Test consistency (run same test twice)
        if not quick:
            profile = self._test_consistency(profile)

        # Save profile
        save_profile(profile)

        if self.verbose:
            print(f"\nProfile saved: {profile.profile_id}")
            print(f"  Syntax accuracy: {profile.syntax_accuracy:.0%}")
            print(f"  Semantic accuracy: {profile.semantic_accuracy:.0%}")
            print(f"  Optimal chunk: {profile.optimal_chunk_size} tokens")
            print(f"  Preferred format: {profile.preferred_format}")

        return profile

    def _test_reproduction(self, name: str, code: str) -> ProfileTestResult:
        """Test reproduction of a code snippet."""
        # Create YAML spec
        spec = self._code_to_spec(code)
        tokens_in = estimate_tokens(spec)

        prompt = f"""Reproduce this Python code from its specification.
Output ONLY the Python code, no explanations.

Specification (YAML):
{spec}

Python code:"""

        start = time.time()
        try:
            response = self.client.generate(prompt)
            reproduced = self._extract_code(response)
            elapsed = time.time() - start

            # Check syntax
            syntax_ok = self._check_syntax(reproduced)

            # Calculate similarity
            similarity = self._calculate_similarity(code, reproduced)

            return ProfileTestResult(
                test_name=name,
                original_code=code,
                reproduced_code=reproduced,
                syntax_ok=syntax_ok,
                similarity=similarity,
                time_seconds=elapsed,
                tokens_in=tokens_in,
                tokens_out=estimate_tokens(reproduced),
            )
        except Exception as e:
            return ProfileTestResult(
                test_name=name,
                original_code=code,
                reproduced_code="",
                syntax_ok=False,
                similarity=0.0,
                time_seconds=time.time() - start,
                tokens_in=tokens_in,
                tokens_out=0,
                error=str(e),
            )

    def _code_to_spec(self, code: str) -> str:
        """Convert code to simple YAML spec."""
        lines = []
        lines.append("elements:")

        # Simple parsing
        for line in code.strip().split("\n"):
            stripped = line.strip()
            if stripped.startswith("def "):
                match = stripped[4:].split("(")[0]
                lines.append("  - type: function")
                lines.append(f"    name: {match}")
            elif stripped.startswith("async def "):
                match = stripped[10:].split("(")[0]
                lines.append("  - type: async_function")
                lines.append(f"    name: {match}")
            elif stripped.startswith("class "):
                match = stripped[6:].split("(")[0].split(":")[0]
                lines.append("  - type: class")
                lines.append(f"    name: {match}")
            elif stripped.startswith("@"):
                lines.append(f"  - decorator: {stripped}")

        lines.append("")
        lines.append("source:")
        for line in code.strip().split("\n"):
            lines.append(f"  {line}")

        return "\n".join(lines)

    def _extract_code(self, response: str) -> str:
        """Extract code from LLM response."""
        # Try to find code block
        if "```python" in response:
            start = response.find("```python") + 9
            end = response.find("```", start)
            if end > start:
                return response[start:end].strip()
        elif "```" in response:
            start = response.find("```") + 3
            end = response.find("```", start)
            if end > start:
                return response[start:end].strip()

        # Return as-is if no code block
        return response.strip()

    def _check_syntax(self, code: str) -> bool:
        """Check if code has valid Python syntax."""
        try:
            compile(code, "<string>", "exec")
            return True
        except SyntaxError:
            return False

    def _calculate_similarity(self, original: str, reproduced: str) -> float:
        """Calculate code similarity."""
        # Normalize whitespace
        orig_norm = " ".join(original.split())
        repr_norm = " ".join(reproduced.split())

        return SequenceMatcher(None, orig_norm, repr_norm).ratio()

    def _calculate_metrics(
        self, profile: LLMProfile, results: list[ProfileTestResult]
    ) -> LLMProfile:
        """Calculate aggregate metrics from test results."""
        if not results:
            return profile

        # Syntax accuracy
        syntax_ok_count = sum(1 for r in results if r.syntax_ok)
        profile.syntax_accuracy = syntax_ok_count / len(results)

        # Semantic accuracy (average similarity)
        profile.semantic_accuracy = sum(r.similarity for r in results) / len(results)

        # Estimate optimal chunk size based on accuracy
        # If accuracy is high, can use larger chunks
        if profile.semantic_accuracy > 0.8:
            profile.optimal_chunk_size = 3000
        elif profile.semantic_accuracy > 0.6:
            profile.optimal_chunk_size = 2000
        else:
            profile.optimal_chunk_size = 1000

        # Set preferred format based on accuracy
        if profile.syntax_accuracy > 0.9:
            profile.preferred_format = "toon"  # Can handle compact format
        else:
            profile.preferred_format = "yaml"  # Need more explicit format

        # Store test results
        profile.test_results = {
            r.test_name: {
                "syntax_ok": r.syntax_ok,
                "similarity": r.similarity,
                "time": r.time_seconds,
            }
            for r in results
        }

        return profile

    def _test_consistency(self, profile: LLMProfile) -> LLMProfile:
        """Test output consistency by running same prompt twice."""
        code = PROFILE_TEST_CASES["simple_function"]

        result1 = self._test_reproduction("consistency_1", code)
        result2 = self._test_reproduction("consistency_2", code)

        # Compare outputs
        if result1.reproduced_code and result2.reproduced_code:
            consistency = self._calculate_similarity(
                result1.reproduced_code, result2.reproduced_code
            )
            profile.output_consistency = consistency

        return profile


class AdaptiveChunker:
    """
    Adaptive chunking based on LLM profile.

    Automatically adjusts chunk sizes and format based on
    model capabilities.
    """

    def __init__(self, profile: Optional[LLMProfile] = None):
        """
        Initialize chunker.

        Args:
            profile: LLM profile (uses defaults if None)
        """
        self.profile = profile or LLMProfile(
            provider="default",
            model="default",
        )

    def get_optimal_settings(self) -> dict[str, Any]:
        """Get optimal settings for the profiled model."""
        return {
            "max_chunk_tokens": self.profile.optimal_chunk_size,
            "preferred_format": self.profile.preferred_format,
            "chunk_strategy": self.profile.chunk_strategy,
            "formats_ranked": self.profile.recommended_formats,
        }

    def chunk_spec(self, spec: str, format: str = "yaml") -> list[dict[str, Any]]:
        """
        Chunk specification based on profile.

        Args:
            spec: Specification string
            format: Specification format

        Returns:
            List of chunks with metadata
        """
        max_tokens = self.profile.optimal_chunk_size

        # Adjust for format verbosity
        format_factors = {
            "json": 1.2,  # More verbose, smaller chunks
            "yaml": 1.0,
            "toon": 0.8,  # More compact, larger chunks
            "gherkin": 1.1,
            "markdown": 1.0,
            "logicml": 0.9,
        }
        factor = format_factors.get(format, 1.0)
        adjusted_max = int(max_tokens / factor)

        # Simple chunking by lines with token budget
        chunks = []
        current_chunk = []
        current_tokens = 0
        chunk_id = 0

        lines = spec.split("\n")

        for line in lines:
            line_tokens = estimate_tokens(line)

            if current_tokens + line_tokens > adjusted_max and current_chunk:
                chunks.append(
                    {
                        "id": chunk_id,
                        "content": "\n".join(current_chunk),
                        "tokens": current_tokens,
                        "format": format,
                    }
                )
                chunk_id += 1
                current_chunk = []
                current_tokens = 0

            current_chunk.append(line)
            current_tokens += line_tokens

        if current_chunk:
            chunks.append(
                {
                    "id": chunk_id,
                    "content": "\n".join(current_chunk),
                    "tokens": current_tokens,
                    "format": format,
                }
            )

        return chunks

    def recommend_format(self, spec_size_tokens: int) -> str:
        """
        Recommend best format based on spec size and model.

        Args:
            spec_size_tokens: Estimated tokens in full spec

        Returns:
            Recommended format name
        """
        # If spec fits in one chunk, use preferred format
        if spec_size_tokens <= self.profile.optimal_chunk_size:
            return self.profile.preferred_format

        # For larger specs, prefer more compact formats
        if spec_size_tokens > self.profile.effective_context:
            # Need chunking, use most compact format
            return "toon"

        # Medium size, balance accuracy and size
        if self.profile.semantic_accuracy > 0.7:
            return self.profile.preferred_format
        else:
            return "yaml"  # More explicit for lower accuracy models

    def estimate_chunks_needed(self, spec_size_tokens: int) -> int:
        """Estimate number of chunks needed."""
        if spec_size_tokens <= self.profile.optimal_chunk_size:
            return 1
        return (spec_size_tokens // self.profile.optimal_chunk_size) + 1


# Convenience functions
def profile_llm(client, quick: bool = False) -> LLMProfile:
    """Profile an LLM client."""
    profiler = LLMProfiler(client)
    return profiler.run_profile(quick=quick)


def get_adaptive_chunker(provider: str, model: str) -> AdaptiveChunker:
    """Get adaptive chunker for a model."""
    profile = get_or_create_profile(provider, model)
    return AdaptiveChunker(profile)
