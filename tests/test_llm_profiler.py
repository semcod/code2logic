"""
Tests for LLM Profiler module.

Tests profile creation, storage, adaptive chunking, and metrics calculation.
"""

from unittest.mock import Mock, patch
import pytest

from code2logic.llm_profiler import (
    LLMProfile,
    LLMProfiler,
    AdaptiveChunker,
    ProfileTestResult,
    load_profiles,
    save_profile,
    get_profile,
    get_or_create_profile,
    get_adaptive_chunker,
    profile_llm,
    _create_default_profile,
    PROFILE_TEST_CASES,
)


class TestLLMProfile:
    """Tests for LLMProfile dataclass."""

    def test_profile_creation(self):
        """Test basic profile creation."""
        profile = LLMProfile(
            provider="openrouter",
            model="qwen/qwen-2.5-coder-32b",
        )

        assert profile.provider == "openrouter"
        assert profile.model == "qwen/qwen-2.5-coder-32b"
        assert profile.profile_id  # Auto-generated
        assert profile.created_at  # Auto-generated

    def test_profile_id_consistency(self):
        """Test that same provider/model gives same profile_id."""
        p1 = LLMProfile(provider="test", model="model1")
        p2 = LLMProfile(provider="test", model="model1")

        assert p1.profile_id == p2.profile_id

    def test_profile_defaults(self):
        """Test default values."""
        profile = LLMProfile(provider="test", model="test")

        assert profile.effective_context == 4000
        assert profile.max_output == 2000
        assert profile.optimal_chunk_size == 1500
        assert profile.syntax_accuracy == 0.0
        assert profile.semantic_accuracy == 0.0
        assert profile.preferred_format == "yaml"

    def test_profile_custom_values(self):
        """Test custom values override defaults."""
        profile = LLMProfile(
            provider="test",
            model="test",
            effective_context=8000,
            optimal_chunk_size=3000,
            syntax_accuracy=0.95,
            preferred_format="toon",
        )

        assert profile.effective_context == 8000
        assert profile.optimal_chunk_size == 3000
        assert profile.syntax_accuracy == 0.95
        assert profile.preferred_format == "toon"


class TestDefaultProfiles:
    """Tests for default profile creation."""

    def test_gpt4_profile(self):
        """Test GPT-4 default profile."""
        profile = _create_default_profile("openai", "gpt-4")

        assert profile.effective_context == 8000
        assert profile.preferred_format == "yaml"

    def test_gpt4_turbo_profile(self):
        """Test GPT-4 Turbo default profile."""
        profile = _create_default_profile("openai", "gpt-4-turbo")

        assert profile.effective_context == 32000
        assert profile.optimal_chunk_size == 3000

    def test_claude_profile(self):
        """Test Claude default profile."""
        profile = _create_default_profile("anthropic", "claude-3-sonnet")

        assert profile.effective_context == 32000
        assert profile.optimal_chunk_size == 4000

    def test_qwen_coder_profile(self):
        """Test Qwen Coder default profile."""
        profile = _create_default_profile("ollama", "qwen2.5-coder:14b")

        assert profile.effective_context == 16000
        assert profile.optimal_chunk_size == 3000
        assert profile.preferred_format == "toon"

    def test_deepseek_profile(self):
        """Test DeepSeek default profile."""
        profile = _create_default_profile("openrouter", "deepseek-coder-33b")

        assert profile.effective_context == 16000
        assert profile.preferred_format == "toon"

    def test_llama_70b_profile(self):
        """Test Llama 70B default profile."""
        profile = _create_default_profile("ollama", "llama-70b-instruct")

        assert profile.effective_context == 4000
        assert profile.optimal_chunk_size == 1500

    def test_llama_7b_profile(self):
        """Test Llama 7B default profile (smaller)."""
        profile = _create_default_profile("ollama", "llama-7b")

        assert profile.effective_context == 2000
        assert profile.optimal_chunk_size == 1000

    def test_mistral_profile(self):
        """Test Mistral default profile."""
        profile = _create_default_profile("ollama", "mistral-7b")

        assert profile.effective_context == 8000
        assert profile.optimal_chunk_size == 2500

    def test_unknown_model_profile(self):
        """Test unknown model gets safe defaults."""
        profile = _create_default_profile("unknown", "some-new-model")

        assert profile.effective_context == 4000
        assert profile.optimal_chunk_size == 1500
        assert profile.preferred_format == "yaml"


class TestProfileStorage:
    """Tests for profile storage (save/load)."""

    def test_save_and_load_profile(self, tmp_path):
        """Test saving and loading a profile."""
        # Patch the profiles path
        profiles_file = tmp_path / "llm_profiles.json"

        with patch(
            "code2logic.llm_profiler._get_profiles_path", return_value=profiles_file
        ):
            profile = LLMProfile(
                provider="test",
                model="test-model",
                syntax_accuracy=0.9,
                semantic_accuracy=0.85,
            )

            save_profile(profile)

            # Load and verify
            loaded = load_profiles()
            assert profile.profile_id in loaded

            loaded_profile = loaded[profile.profile_id]
            assert loaded_profile.provider == "test"
            assert loaded_profile.model == "test-model"
            assert loaded_profile.syntax_accuracy == 0.9

    def test_load_empty_profiles(self, tmp_path):
        """Test loading when no profiles exist."""
        profiles_file = tmp_path / "nonexistent.json"

        with patch(
            "code2logic.llm_profiler._get_profiles_path", return_value=profiles_file
        ):
            profiles = load_profiles()
            assert profiles == {}

    def test_get_profile(self, tmp_path):
        """Test getting a specific profile."""
        profiles_file = tmp_path / "llm_profiles.json"

        with patch(
            "code2logic.llm_profiler._get_profiles_path", return_value=profiles_file
        ):
            profile = LLMProfile(provider="test", model="model1")
            save_profile(profile)

            loaded = get_profile("test", "model1")
            assert loaded is not None
            assert loaded.profile_id == profile.profile_id

    def test_get_nonexistent_profile(self, tmp_path):
        """Test getting a profile that doesn't exist."""
        profiles_file = tmp_path / "llm_profiles.json"

        with patch(
            "code2logic.llm_profiler._get_profiles_path", return_value=profiles_file
        ):
            loaded = get_profile("nonexistent", "model")
            assert loaded is None

    def test_get_or_create_profile_existing(self, tmp_path):
        """Test get_or_create returns existing profile."""
        profiles_file = tmp_path / "llm_profiles.json"

        with patch(
            "code2logic.llm_profiler._get_profiles_path", return_value=profiles_file
        ):
            profile = LLMProfile(
                provider="test",
                model="model1",
                syntax_accuracy=0.99,
            )
            save_profile(profile)

            loaded = get_or_create_profile("test", "model1")
            assert loaded.syntax_accuracy == 0.99

    def test_get_or_create_profile_new(self, tmp_path):
        """Test get_or_create creates new default profile."""
        profiles_file = tmp_path / "llm_profiles.json"

        with patch(
            "code2logic.llm_profiler._get_profiles_path", return_value=profiles_file
        ):
            profile = get_or_create_profile("openai", "gpt-4-turbo")

            # Should have GPT-4 Turbo defaults
            assert profile.effective_context == 32000


class TestAdaptiveChunker:
    """Tests for AdaptiveChunker."""

    def test_chunker_creation(self):
        """Test chunker creation with profile."""
        profile = LLMProfile(
            provider="test",
            model="test",
            optimal_chunk_size=2000,
            preferred_format="toon",
        )

        chunker = AdaptiveChunker(profile)
        settings = chunker.get_optimal_settings()

        assert settings["max_chunk_tokens"] == 2000
        assert settings["preferred_format"] == "toon"

    def test_chunker_default_profile(self):
        """Test chunker with default profile."""
        chunker = AdaptiveChunker()
        settings = chunker.get_optimal_settings()

        assert "max_chunk_tokens" in settings
        assert "preferred_format" in settings

    def test_chunk_small_spec(self):
        """Test chunking a small spec (single chunk)."""
        profile = LLMProfile(
            provider="test",
            model="test",
            optimal_chunk_size=1000,
        )
        chunker = AdaptiveChunker(profile)

        spec = "name: test\nvalue: 123"
        chunks = chunker.chunk_spec(spec, "yaml")

        assert len(chunks) == 1
        assert chunks[0]["content"] == spec

    def test_chunk_large_spec(self):
        """Test chunking a large spec (multiple chunks)."""
        profile = LLMProfile(
            provider="test",
            model="test",
            optimal_chunk_size=100,  # Very small for testing
        )
        chunker = AdaptiveChunker(profile)

        # Create spec larger than chunk size
        spec = "\n".join([f"item_{i}: value_{i}" for i in range(100)])
        chunks = chunker.chunk_spec(spec, "yaml")

        assert len(chunks) > 1
        # All chunks should have content
        for chunk in chunks:
            assert chunk["content"]
            assert chunk["tokens"] > 0

    def test_chunk_format_adjustment(self):
        """Test that format affects chunk size."""
        profile = LLMProfile(
            provider="test",
            model="test",
            optimal_chunk_size=1000,
        )
        chunker = AdaptiveChunker(profile)

        spec = "x" * 500

        # JSON is more verbose, should get smaller effective chunks
        json_chunks = chunker.chunk_spec(spec, "json")

        # TOON is more compact, should get larger effective chunks
        toon_chunks = chunker.chunk_spec(spec, "toon")

        # Both should work (just verifying no errors)
        assert len(json_chunks) >= 1
        assert len(toon_chunks) >= 1

    def test_recommend_format_small_spec(self):
        """Test format recommendation for small spec."""
        profile = LLMProfile(
            provider="test",
            model="test",
            optimal_chunk_size=2000,
            preferred_format="toon",
        )
        chunker = AdaptiveChunker(profile)

        # Small spec - should use preferred format
        fmt = chunker.recommend_format(500)
        assert fmt == "toon"

    def test_recommend_format_large_spec(self):
        """Test format recommendation for large spec."""
        profile = LLMProfile(
            provider="test",
            model="test",
            optimal_chunk_size=1000,
            effective_context=2000,
        )
        chunker = AdaptiveChunker(profile)

        # Very large spec - should recommend compact format
        fmt = chunker.recommend_format(10000)
        assert fmt == "toon"

    def test_estimate_chunks_needed(self):
        """Test chunk estimation."""
        profile = LLMProfile(
            provider="test",
            model="test",
            optimal_chunk_size=1000,
        )
        chunker = AdaptiveChunker(profile)

        assert chunker.estimate_chunks_needed(500) == 1
        assert chunker.estimate_chunks_needed(1500) == 2
        assert chunker.estimate_chunks_needed(3000) == 4


class TestLLMProfiler:
    """Tests for LLMProfiler class."""

    def test_profiler_creation(self):
        """Test profiler creation."""
        mock_client = Mock()
        mock_client.provider = "test"
        mock_client.model = "test-model"

        profiler = LLMProfiler(mock_client, verbose=False)

        assert profiler.provider == "test"
        assert profiler.model == "test-model"

    def test_profiler_with_unknown_client(self):
        """Test profiler with client missing provider/model."""
        mock_client = Mock(spec=[])  # No provider/model attributes

        profiler = LLMProfiler(mock_client, verbose=False)

        assert profiler.provider == "unknown"
        assert profiler.model == "unknown"

    def test_code_to_spec(self):
        """Test code to spec conversion."""
        mock_client = Mock()
        profiler = LLMProfiler(mock_client, verbose=False)

        code = """
def hello():
    pass

class Foo:
    pass
"""
        spec = profiler._code_to_spec(code)

        assert "elements:" in spec
        assert "function" in spec
        assert "hello" in spec
        assert "class" in spec
        assert "Foo" in spec

    def test_extract_code_with_block(self):
        """Test extracting code from response with code block."""
        mock_client = Mock()
        profiler = LLMProfiler(mock_client, verbose=False)

        response = """Here is the code:
```python
def hello():
    return "world"
```
That's it!"""

        code = profiler._extract_code(response)

        assert "def hello():" in code
        assert "return" in code
        assert "```" not in code

    def test_extract_code_without_block(self):
        """Test extracting code from response without code block."""
        mock_client = Mock()
        profiler = LLMProfiler(mock_client, verbose=False)

        response = "def hello(): return 'world'"
        code = profiler._extract_code(response)

        assert code == "def hello(): return 'world'"

    def test_check_syntax_valid(self):
        """Test syntax check with valid code."""
        mock_client = Mock()
        profiler = LLMProfiler(mock_client, verbose=False)

        assert profiler._check_syntax("def foo(): pass") is True
        assert profiler._check_syntax("x = 1 + 2") is True

    def test_check_syntax_invalid(self):
        """Test syntax check with invalid code."""
        mock_client = Mock()
        profiler = LLMProfiler(mock_client, verbose=False)

        assert profiler._check_syntax("def foo(") is False
        assert profiler._check_syntax("x = ") is False

    def test_calculate_similarity(self):
        """Test similarity calculation."""
        mock_client = Mock()
        profiler = LLMProfiler(mock_client, verbose=False)

        # Identical
        sim = profiler._calculate_similarity("hello world", "hello world")
        assert sim == 1.0

        # Similar
        sim = profiler._calculate_similarity("hello world", "hello there")
        assert 0.5 < sim < 1.0

        # Different
        sim = profiler._calculate_similarity("abc", "xyz")
        assert sim < 0.5

    def test_run_profile_quick(self, tmp_path):
        """Test quick profile run."""
        profiles_file = tmp_path / "llm_profiles.json"

        mock_client = Mock()
        mock_client.provider = "test"
        mock_client.model = "test-model"
        mock_client.generate.return_value = (
            "def calculate_sum(numbers): return sum(numbers)"
        )

        with patch(
            "code2logic.llm_profiler._get_profiles_path", return_value=profiles_file
        ):
            profiler = LLMProfiler(mock_client, verbose=False)
            profile = profiler.run_profile(quick=True)

            assert profile.provider == "test"
            assert profile.model == "test-model"
            # Quick mode runs 2 tests
            assert mock_client.generate.call_count == 2

    def test_metrics_calculation(self):
        """Test metrics calculation from results."""
        mock_client = Mock()
        profiler = LLMProfiler(mock_client, verbose=False)

        results = [
            ProfileTestResult(
                test_name="test1",
                original_code="def foo(): pass",
                reproduced_code="def foo(): pass",
                syntax_ok=True,
                similarity=1.0,
                time_seconds=1.0,
                tokens_in=10,
                tokens_out=10,
            ),
            ProfileTestResult(
                test_name="test2",
                original_code="def bar(): pass",
                reproduced_code="def bar(): return None",
                syntax_ok=True,
                similarity=0.8,
                time_seconds=1.0,
                tokens_in=10,
                tokens_out=12,
            ),
        ]

        profile = LLMProfile(provider="test", model="test")
        profile = profiler._calculate_metrics(profile, results)

        assert profile.syntax_accuracy == 1.0
        assert profile.semantic_accuracy == 0.9  # Average of 1.0 and 0.8


class TestProfileTestCases:
    """Tests for built-in test cases."""

    def test_test_cases_exist(self):
        """Test that test cases are defined."""
        assert len(PROFILE_TEST_CASES) >= 5

    def test_test_cases_valid_python(self):
        """Test that all test cases are valid Python."""
        for name, code in PROFILE_TEST_CASES.items():
            try:
                compile(code.strip(), f"<{name}>", "exec")
            except SyntaxError as e:
                pytest.fail(f"Test case '{name}' has invalid syntax: {e}")

    def test_test_cases_have_functions_or_classes(self):
        """Test that test cases contain functions or classes."""
        for name, code in PROFILE_TEST_CASES.items():
            assert "def " in code or "class " in code, (
                f"Test case '{name}' missing def/class"
            )


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_get_adaptive_chunker(self):
        """Test get_adaptive_chunker function."""
        chunker = get_adaptive_chunker("openai", "gpt-4-turbo")

        assert isinstance(chunker, AdaptiveChunker)
        settings = chunker.get_optimal_settings()
        assert settings["max_chunk_tokens"] > 0

    def test_profile_llm_function(self, tmp_path):
        """Test profile_llm convenience function."""
        profiles_file = tmp_path / "llm_profiles.json"

        mock_client = Mock()
        mock_client.provider = "test"
        mock_client.model = "test-model"
        mock_client.generate.return_value = "def foo(): pass"

        with patch(
            "code2logic.llm_profiler._get_profiles_path", return_value=profiles_file
        ):
            profile = profile_llm(mock_client, quick=True)

            assert isinstance(profile, LLMProfile)
            assert profile.provider == "test"
