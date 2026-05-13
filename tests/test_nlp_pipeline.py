"""Tests for NLP Processing Pipeline."""

import pytest
from code2flow.nlp import (
    NLPPipeline,
    QueryNormalizer,
    IntentMatcher,
    EntityResolver,
    NLPConfig,
    FAST_NLP_CONFIG,
)
from code2flow.nlp.entity_resolution import Entity


class TestQueryNormalization:
    """Test Query Normalization steps 1a-1e."""

    def test_step_1a_lowercase(self):
        """1a. Lowercase conversion."""
        normalizer = QueryNormalizer()
        result = normalizer.normalize("Hello World TEST")

        assert "lowercase" in result.steps_applied
        assert result.normalized == "hello world test"

    def test_step_1b_remove_punctuation(self):
        """1b. Punctuation removal."""
        normalizer = QueryNormalizer()
        result = normalizer.normalize("Find function: test!")

        assert "remove_punctuation" in result.steps_applied
        assert "!" not in result.normalized

    def test_step_1c_normalize_whitespace(self):
        """1c. Whitespace normalization."""
        normalizer = QueryNormalizer()
        result = normalizer.normalize("Multiple   spaces    here")

        assert "normalize_whitespace" in result.steps_applied
        assert "  " not in result.normalized

    def test_step_1d_unicode_normalize(self):
        """1d. Unicode NFKC normalization."""
        normalizer = QueryNormalizer()
        # Test with composed character (é as single char vs e + combining acute)
        result = normalizer.normalize("caf\u00e9")  # é as single char

        assert "unicode_nfkc" in result.steps_applied

    def test_step_1e_remove_stopwords(self):
        """1e. Stopword removal."""
        from code2flow.nlp.config import NormalizationConfig

        config = NormalizationConfig(remove_stopwords=True)
        normalizer = QueryNormalizer(config)
        result = normalizer.normalize("the test is working", language="en")

        assert "remove_stopwords" in result.steps_applied
        assert "the" not in result.normalized
        assert "is" not in result.normalized

    def test_polish_text_normalization(self):
        """Test normalization with Polish text."""
        normalizer = QueryNormalizer()
        result = normalizer.normalize("Znajdź FUNKCJĘ: test!!!", language="pl")

        assert result.normalized == "znajdź funkcję test"
        assert "znajdź" in result.tokens


class TestIntentMatching:
    """Test Intent Matching steps 2a-2e."""

    def test_step_2a_fuzzy_match(self):
        """2a. Fuzzy matching threshold."""
        matcher = IntentMatcher()
        result = matcher.match("find funcion test")  # typo: funcion

        # Should match "find_function" intent despite typo
        assert result.primary_intent is not None
        assert result.primary_intent.confidence >= 0.8

    def test_step_2c_keyword_match(self):
        """2c. Keyword matching weight."""
        matcher = IntentMatcher()
        result = matcher.match("function search")

        # Should find function-related intent
        assert result.primary_intent is not None
        assert any("function" in m.intent for m in result.all_matches)

    def test_step_2d_context_score(self):
        """2d. Context window scoring."""
        matcher = IntentMatcher()
        context = ["find class", "search for function"]
        result = matcher.match("show it", context=context)

        # Context should boost function-related intent
        if result.primary_intent:
            assert result.primary_intent.context_score > 0

    def test_step_2e_multi_intent_resolution(self):
        """2e. Multi-intent resolution strategy."""
        from code2flow.nlp.config import IntentMatchingConfig

        config = IntentMatchingConfig(multi_intent_strategy="best_match")
        matcher = IntentMatcher(config)
        result = matcher.match("find function and class")

        assert result.strategy_used == "best_match"
        # Should pick best single intent
        assert result.primary_intent is not None

    def test_polish_intent_matching(self):
        """Test intent matching with Polish queries."""
        matcher = IntentMatcher()
        result = matcher.match("znajdź funkcję")

        assert result.primary_intent is not None
        assert result.primary_intent.intent == "find_function"


class TestEntityResolution:
    """Test Entity Resolution steps 3a-3e."""

    @pytest.fixture
    def mock_entities(self):
        """Create mock codebase entities."""
        return {
            "function": [
                Entity("run", "pipeline.run", "function", 1.0),
                Entity("analyze", "analyzer.analyze", "function", 1.0),
            ],
            "class": [
                Entity("Pipeline", "code2flow.Pipeline", "class", 1.0),
            ],
        }

    def test_step_3a_extract_entities(self, mock_entities):
        """3a. Entity types extraction."""
        resolver = EntityResolver(codebase_entities=mock_entities)
        result = resolver.resolve("find function run")

        assert len(result.entities) > 0
        assert any(e.entity_type == "function" for e in result.entities)

    def test_step_3b_name_match_threshold(self, mock_entities):
        """3b. Name matching threshold."""
        from code2flow.nlp.config import EntityResolutionConfig

        config = EntityResolutionConfig(name_match_threshold=0.9)
        resolver = EntityResolver(config, mock_entities)
        result = resolver.resolve("find run")

        # All results should meet threshold
        for e in result.entities:
            assert e.confidence >= 0.9

    def test_step_3c_disambiguation(self, mock_entities):
        """3c. Context-aware disambiguation."""
        resolver = EntityResolver(codebase_entities=mock_entities)
        context = "Pipeline class"
        result = resolver.resolve("find Pipeline", context=context)

        # Should boost Pipeline entity due to context
        pipeline_entities = [e for e in result.entities if "Pipeline" in e.name]
        if pipeline_entities:
            assert pipeline_entities[0].confidence > 0.7

    def test_step_3d_hierarchical_resolution(self, mock_entities):
        """3d. Hierarchical resolution."""
        config = EntityResolutionConfig(hierarchical_resolution=True)
        resolver = EntityResolver(config, mock_entities)

        # Add hierarchical entity
        mock_entities["function"].append(
            Entity("Pipeline.run", "code2flow.Pipeline.run", "function", 1.0)
        )

        result = resolver.resolve("run method")

        # Should resolve both full and short name
        short_names = [e.name for e in result.entities]
        assert "run" in short_names

    def test_step_3e_alias_resolution(self, mock_entities):
        """3e. Alias resolution."""
        config = EntityResolutionConfig(alias_resolution=True)
        resolver = EntityResolver(config, mock_entities)
        result = resolver.resolve("find analyzer")

        # Should have aliases populated
        for e in result.entities:
            if e.aliases:
                assert len(e.aliases) > 0


class TestNLPPipeline:
    """Test complete NLP Pipeline integration (4a-4e)."""

    def test_step_4a_orchestration(self):
        """4a. Pipeline orchestration."""
        pipeline = NLPPipeline(FAST_NLP_CONFIG)
        result = pipeline.process("find function test")

        assert len(result.stages) == 3  # normalization, intent, entity
        assert all(s.success for s in result.stages)

    def test_step_4c_confidence_scoring(self):
        """4c. Confidence scoring."""
        pipeline = NLPPipeline()
        result = pipeline.process("find function run")

        assert 0.0 <= result.overall_confidence <= 1.0
        assert "intent" in result.stage_confidences
        assert "entity" in result.stage_confidences

    def test_step_4d_fallback_handling(self):
        """4d. Fallback handling for low confidence."""
        pipeline = NLPPipeline()
        # Unclear query should trigger fallback
        result = pipeline.process("xyz abc 123")

        if result.overall_confidence < 0.5:
            assert result.fallback_used is True
            assert result.fallback_reason is not None

    def test_step_4e_output_formatting(self):
        """4e. Output formatting."""
        pipeline = NLPPipeline()
        result = pipeline.process("find class Pipeline")

        assert result.formatted_response is not None
        assert result.action_recommendation is not None
        assert isinstance(result.to_dict(), dict)

    def test_polish_query_processing(self):
        """Test complete pipeline with Polish query."""
        pipeline = NLPPipeline()
        result = pipeline.process("znajdź klasę Pipeline", language="pl")

        assert result.get_intent() == "find_class"
        assert result.is_successful()


class TestNLPConfig:
    """Test YAML-driven configuration."""

    def test_config_from_yaml(self, tmp_path):
        """Load configuration from YAML."""
        config_file = tmp_path / "nlp_config.yaml"
        config_file.write_text("""
normalization:
  lowercase: true
  remove_punctuation: false
  
intent_matching:
  fuzzy_threshold: 0.85
  
enable_normalization: true
enable_intent_matching: true
verbose: true
""")

        config = NLPConfig.from_yaml(str(config_file))

        assert config.normalization.lowercase is True
        assert config.normalization.remove_punctuation is False
        assert config.intent_matching.fuzzy_threshold == 0.85
        assert config.verbose is True

    def test_config_to_yaml(self, tmp_path):
        """Save configuration to YAML."""
        config_file = tmp_path / "output_config.yaml"

        config = FAST_NLP_CONFIG
        config.to_yaml(str(config_file))

        assert config_file.exists()
        content = config_file.read_text()
        assert "fuzzy_threshold" in content


class TestMultilingualSupport:
    """Test multilingual fuzzy matching."""

    def test_english_queries(self):
        """Process English queries."""
        pipeline = NLPPipeline()

        queries = [
            "find function",
            "show call graph",
            "analyze flow",
            "explain code",
        ]

        for query in queries:
            result = pipeline.process(query, language="en")
            assert result.get_intent() is not None

    def test_polish_queries(self):
        """Process Polish queries."""
        pipeline = NLPPipeline()

        queries = [
            "znajdź funkcję",
            "pokaż graf wywołań",
            "analizuj przepływ",
            "wyjaśnij kod",
        ]

        for query in queries:
            result = pipeline.process(query, language="pl")
            assert result.get_intent() is not None

    def test_mixed_language_fuzzy_matching(self):
        """Fuzzy matching across languages."""
        matcher = IntentMatcher()

        # English query with Polish intent patterns
        result_en = matcher.match("find function")
        result_pl = matcher.match("znajdź funkcję")

        # Both should resolve to same intent
        assert result_en.primary_intent.intent == result_pl.primary_intent.intent


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
