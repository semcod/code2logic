"""Basic tests for logic2code package."""


def test_import_logic2code():
    """Test that logic2code can be imported."""
    import logic2code

    assert hasattr(logic2code, "CodeGenerator")
    assert hasattr(logic2code, "GeneratorConfig")


def test_import_generator():
    """Test generator module imports."""
    from logic2code import CodeGenerator, GeneratorConfig

    assert CodeGenerator is not None
    assert GeneratorConfig is not None


def test_config_defaults():
    """Test GeneratorConfig has sensible defaults."""
    from logic2code import GeneratorConfig

    config = GeneratorConfig()
    assert config.language == "python"
    assert isinstance(config.stubs_only, bool)
    assert isinstance(config.include_docstrings, bool)
    assert isinstance(config.include_type_hints, bool)


def test_generator_config_custom():
    """Test GeneratorConfig accepts custom values."""
    from logic2code import GeneratorConfig

    config = GeneratorConfig(
        language="python",
        stubs_only=True,
        include_docstrings=False,
    )
    assert config.language == "python"
    assert config.stubs_only is True
    assert config.include_docstrings is False


def test_generator_config_llm():
    """Test GeneratorConfig LLM options."""
    from logic2code import GeneratorConfig

    config = GeneratorConfig(
        use_llm=True,
        llm_provider="openrouter",
    )
    assert config.use_llm is True
    assert config.llm_provider == "openrouter"
