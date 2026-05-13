from __future__ import annotations

import shutil
from pathlib import Path

from code2logic import analyze_project
from code2logic.generators import YAMLGenerator
from logic2code.generator import CodeGenerator as Logic2CodeGenerator
from logic2code.generator import GeneratorConfig as Logic2CodeGeneratorConfig
from logic2test.generator import GeneratorConfig as Logic2TestGeneratorConfig
from logic2test.generator import TestGenerator as Logic2TestGenerator


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _copy_example_sample_project(tmp_path: Path) -> Path:
    src = _repo_root() / "examples" / "code2logic" / "sample_project"
    dst = tmp_path / "sample_project"
    shutil.copytree(src, dst)
    return dst


def _write_code2logic_compact_yaml(project_dir: Path, out_file: Path) -> None:
    project = analyze_project(str(project_dir), use_treesitter=False, verbose=False)
    yaml_str = YAMLGenerator().generate(project, compact=True, detail="standard")
    out_file.write_text(yaml_str, encoding="utf-8")


def test_e2e_pipeline_code2logic_logic2test_logic2code(tmp_path: Path) -> None:
    project_dir = _copy_example_sample_project(tmp_path)
    logic_file = tmp_path / "project.c2l.yaml"
    _write_code2logic_compact_yaml(project_dir, logic_file)
    assert logic_file.exists()
    assert logic_file.stat().st_size > 0

    tests_out = tmp_path / "generated_tests"
    test_gen = Logic2TestGenerator(
        logic_file, config=Logic2TestGeneratorConfig(framework="pytest")
    )

    unit_result = test_gen.generate_unit_tests(tests_out / "unit")
    assert not unit_result.errors
    assert unit_result.files_generated > 0
    assert unit_result.tests_generated > 0

    integration_result = test_gen.generate_integration_tests(tests_out / "integration")
    assert not integration_result.errors
    assert (tests_out / "integration" / "test_integration.py").exists()

    property_result = test_gen.generate_property_tests(tests_out / "property")
    assert not property_result.errors
    assert (tests_out / "property" / "test_properties.py").exists()

    code_out = tmp_path / "generated_code"
    code_gen = Logic2CodeGenerator(
        logic_file,
        config=Logic2CodeGeneratorConfig(
            language="python",
            stubs_only=True,
            include_docstrings=True,
            include_type_hints=True,
            generate_init=True,
            preserve_structure=True,
        ),
    )
    code_result = code_gen.generate(code_out)
    assert not code_result.errors
    assert code_result.files_generated > 0
    assert (code_out / "calculator.py").exists()


def test_e2e_logic2test_on_examples_input(tmp_path: Path) -> None:
    input_file = (
        _repo_root() / "examples" / "logic2test" / "input" / "sample_project.c2l.yaml"
    )
    assert input_file.exists()

    out_dir = tmp_path / "tests"
    gen = Logic2TestGenerator(
        input_file, config=Logic2TestGeneratorConfig(framework="pytest")
    )
    result = gen.generate_unit_tests(out_dir)

    assert not result.errors
    assert result.files_generated > 0
    assert any(Path(p).suffix == ".py" for p in result.output_files)


def test_e2e_logic2code_on_examples_input(tmp_path: Path) -> None:
    input_file = (
        _repo_root() / "examples" / "logic2code" / "input" / "sample_project.c2l.yaml"
    )
    assert input_file.exists()

    out_dir = tmp_path / "generated_code"
    gen = Logic2CodeGenerator(
        input_file,
        config=Logic2CodeGeneratorConfig(
            language="python",
            stubs_only=True,
            include_docstrings=True,
            include_type_hints=True,
            generate_init=True,
            preserve_structure=True,
        ),
    )
    result = gen.generate(out_dir)

    assert not result.errors
    assert result.files_generated > 0
    assert (out_dir / "calculator.py").exists()
