"""Basic tests for logic2test package."""


def test_import_logic2test():
    """Test that logic2test can be imported."""
    import logic2test

    assert hasattr(logic2test, "TestGenerator")
    assert hasattr(logic2test, "GeneratorConfig")


def test_import_generator():
    """Test generator module imports."""
    from logic2test import GeneratorConfig, TestGenerator

    assert TestGenerator is not None
    assert GeneratorConfig is not None


def test_config_defaults():
    """Test GeneratorConfig has sensible defaults."""
    from logic2test import GeneratorConfig

    config = GeneratorConfig()
    assert config.framework in ("pytest", "unittest")
    assert isinstance(config.include_private, bool)
    assert isinstance(config.include_dunder, bool)
    assert isinstance(config.max_tests_per_file, int)


def test_generator_config_custom():
    """Test GeneratorConfig accepts custom values."""
    from logic2test import GeneratorConfig

    config = GeneratorConfig(
        framework="unittest",
        include_private=True,
        max_tests_per_file=100,
    )
    assert config.framework == "unittest"
    assert config.include_private is True
    assert config.max_tests_per_file == 100
