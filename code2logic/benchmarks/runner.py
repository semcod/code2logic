"""
Unified Benchmark Runner for Code2Logic.

Provides a standardized API for running various benchmark types:
- Format comparison benchmarks
- File reproduction benchmarks
- Function-level reproduction benchmarks
- Project-level benchmarks

Usage:
    from code2logic.benchmarks import BenchmarkRunner, BenchmarkConfig

    runner = BenchmarkRunner()
    result = runner.run_format_benchmark('tests/samples/', formats=['yaml', 'toon'])
    result.save('output/benchmark.json')
"""

import difflib
import re
import sys
import time
from pathlib import Path
from typing import List, Optional

from concurrent.futures import ThreadPoolExecutor, as_completed

from ..analyzer import analyze_project
from ..llm_clients import BaseLLMClient, get_client
from ..metrics import ReproductionMetrics
from ..terminal import render
from ..utils import estimate_tokens
from .common import (
    create_single_project,
    generate_spec_token,
    get_token_reproduction_prompt,
)
from .results import (
    BenchmarkConfig,
    BenchmarkResult,
    FileResult,
    FormatResult,
    FunctionResult,
)

TIMEOUT_5 = 5
CONSTANT_30 = 30
CONSTANT_50 = 50
CONSTANT_80 = 80
MAX_3000 = 3000


TIMEOUT_5 = TIMEOUT_5
CONSTANT_30 = CONSTANT_30
CONSTANT_50 = CONSTANT_50
CONSTANT_80 = CONSTANT_80
MAX_3000 = MAX_3000


TIMEOUT_5 = TIMEOUT_5
CONSTANT_30 = CONSTANT_30
CONSTANT_50 = CONSTANT_50
CONSTANT_80 = CONSTANT_80
MAX_3000 = MAX_3000


TIMEOUT_5 = TIMEOUT_5
CONSTANT_30 = CONSTANT_30
CONSTANT_50 = CONSTANT_50
CONSTANT_80 = CONSTANT_80
MAX_3000 = MAX_3000


def _test_python_syntax(code: str) -> bool:
    """Test if Python code has valid syntax."""
    try:
        compile(code, "<string>", "exec")
        return True
    except SyntaxError:
        return False


def _test_python_runs(code: str, timeout: int = TIMEOUT_5) -> bool:
    """Test if Python code runs without errors."""
    import subprocess
    import tempfile

    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            result = subprocess.run(
                [sys.executable, f.name], capture_output=True, timeout=timeout
            )
            return result.returncode == 0
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False


def _basic_syntax_ok(code: str, language: str) -> bool:
    """Heuristic syntax check for non-Python languages."""
    s = (code or "").strip()
    if not s:
        return False
    if language in ("javascript", "typescript"):
        # Basic bracket/brace balance to catch the most common truncations
        pairs = {")": "(", "]": "[", "}": "{"}
        stack: List[str] = []
        for ch in s:
            if ch in "([{":
                stack.append(ch)
            elif ch in ")]}":
                if not stack or stack[-1] != pairs.get(ch):
                    return False
                stack.pop()
        return not stack
    if language == "go":
        return "package" in s and "func" in s
    if language == "rust":
        return "fn" in s or "struct" in s or "enum" in s
    if language == "java":
        return "class" in s or "interface" in s
    if language == "csharp":
        return "class" in s or "interface" in s or "record" in s
    if language == "sql":
        upper = s.upper()
        return "CREATE" in upper or "SELECT" in upper or "INSERT" in upper
    return len(s) > 10


def _count_structural_elements(code: str, language: str) -> dict:
    s = code or ""
    if language == "python":
        return {
            "classes": len(re.findall(r"^class\s+\w+", s, re.MULTILINE)),
            "functions": len(re.findall(r"^def\s+\w+", s, re.MULTILINE)),
            "imports": len(re.findall(r"^(?:from|import)\s+", s, re.MULTILINE)),
        }
    if language in ("javascript", "typescript"):
        return {
            "classes": len(re.findall(r"\bclass\s+\w+", s)),
            "functions": len(re.findall(r"\bfunction\s+\w+\s*\(", s))
            + len(re.findall(r"\bconst\s+\w+\s*=\s*(?:async\s*)?\([^)]*\)\s*=>", s)),
            "types": len(re.findall(r"\binterface\s+\w+", s))
            + len(re.findall(r"\btype\s+\w+\s*=", s))
            + len(re.findall(r"\benum\s+\w+", s)),
            "imports": len(re.findall(r"^import\s+", s, re.MULTILINE))
            + len(re.findall(r"\brequire\(", s)),
        }
    if language == "go":
        return {
            "types": len(
                re.findall(r"^type\s+\w+\s+(?:struct|interface)\b", s, re.MULTILINE)
            ),
            "functions": len(
                re.findall(r"^func\s+(?:\([^)]*\)\s*)?\w+\s*\(", s, re.MULTILINE)
            ),
            "imports": len(re.findall(r"^import\b", s, re.MULTILINE)),
        }
    if language == "rust":
        return {
            "types": len(re.findall(r"\bstruct\s+\w+", s))
            + len(re.findall(r"\benum\s+\w+", s))
            + len(re.findall(r"\btrait\s+\w+", s)),
            "functions": len(re.findall(r"\bfn\s+\w+\s*\(", s)),
            "imports": len(re.findall(r"^use\s+", s, re.MULTILINE)),
        }
    if language == "java":
        return {
            "types": len(re.findall(r"\bclass\s+\w+", s))
            + len(re.findall(r"\binterface\s+\w+", s))
            + len(re.findall(r"\benum\s+\w+", s))
            + len(re.findall(r"\brecord\s+\w+", s)),
            "functions": len(re.findall(r"\b\w+\s+\w+\s*\([^)]*\)\s*\{", s)),
            "imports": len(re.findall(r"^import\s+", s, re.MULTILINE)),
        }
    if language == "csharp":
        return {
            "types": len(re.findall(r"\bclass\s+\w+", s))
            + len(re.findall(r"\binterface\s+\w+", s))
            + len(re.findall(r"\brecord\s+\w+", s)),
            "functions": len(re.findall(r"\b\w+\s+\w+\s*\([^)]*\)\s*\{", s)),
            "imports": len(re.findall(r"^using\s+", s, re.MULTILINE)),
        }
    if language == "sql":
        upper = s.upper()
        return {
            "types": len(re.findall(r"\bCREATE\s+TABLE\s+\w+", upper))
            + len(re.findall(r"\bCREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+\w+", upper)),
            "functions": len(
                re.findall(r"\bCREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+\w+", upper)
            ),
        }
    return {}


def _structural_score(original: str, generated: str, language: str) -> float:
    o = _count_structural_elements(original, language)
    g = _count_structural_elements(generated, language)
    if not o:
        return 0.0
    keys = list(o.keys())
    total = 0.0
    for k in keys:
        ov = o.get(k, 0)
        gv = g.get(k, 0)
        if ov == 0 and gv == 0:
            total += 1.0
        elif max(ov, gv) > 0:
            total += min(ov, gv) / max(ov, gv)
    return total / max(len(keys), 1) * 100


def _extract_code(response: str) -> str:
    """Extract code from LLM response."""
    if not response:
        return ""

    # Try to find code block — check language-specific markers first, then generic
    markers = [
        "```python",
        "```py",
        "```javascript",
        "```js",
        "```typescript",
        "```ts",
        "```go",
        "```rust",
        "```rs",
        "```java",
        "```csharp",
        "```cs",
        "```c#",
        "```sql",
        "```",
    ]
    for marker in markers:
        if marker in response:
            start = response.find(marker) + len(marker)
            if start < len(response) and response[start] == "\n":
                start += 1
            end = response.find("```", start)
            if end > start:
                return response[start:end].strip()
            return response[start:].strip()

    return response.strip()


class BenchmarkRunner:
    """
    Unified benchmark runner for code2logic.

    Consolidates benchmarking logic from multiple example scripts
    into a standardized, reusable API.
    """

    def __init__(
        self,
        client: Optional[BaseLLMClient] = None,
        config: Optional[BenchmarkConfig] = None,
    ):
        """
        Initialize benchmark runner.

        Args:
            client: LLM client (auto-detected if None)
            config: Benchmark configuration
        """
        self.client = client
        self.config = config or BenchmarkConfig()
        # Note: avoid sharing ReproductionMetrics instance across threads.

    def _should_use_llm(self) -> bool:
        """Return whether this runner should call an LLM."""
        return bool(getattr(self.config, "use_llm", True))

    def _get_client(self) -> BaseLLMClient:
        """Get or create LLM client."""
        if not self._should_use_llm():
            raise RuntimeError("LLM usage disabled (BenchmarkConfig.use_llm=False)")
        if self.client is None:
            self.client = get_client()
        return self.client

    def _template_generate_code(
        self, spec: str, fmt: str, file_name: str, language: str = "python"
    ) -> str:
        """Generate minimal code without an LLM (fallback mode)."""
        import re

        # Try to infer class/function names from spec
        classes: List[str] = []
        functions: List[str] = []

        # Common patterns across formats
        classes.extend(re.findall(r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)", spec))
        classes.extend(re.findall(r'"name":\s*"([A-Z][A-Za-z0-9_]*)"', spec))
        functions.extend(re.findall(r"\bdef\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", spec))
        functions.extend(re.findall(r"\bFunction:\s*([A-Za-z_][A-Za-z0-9_]*)", spec))
        functions.extend(re.findall(r"\bScenario:\s*([A-Za-z_][A-Za-z0-9_]*)", spec))
        # TOON format: function lines like "  42,func_name,(params)"
        functions.extend(
            re.findall(r"^\s+\d+,([A-Za-z_][A-Za-z0-9_]*),", spec, re.MULTILINE)
        )
        # TOON class.method: "  42,ClassName.method_name,"
        for cm in re.findall(
            r"^\s+\d+,([A-Z][A-Za-z0-9_]*)\.([a-z_][A-Za-z0-9_]*),", spec, re.MULTILINE
        ):
            classes.append(cm[0])
            functions.append(cm[1])
        # YAML/JSON: "n: ClassName" or name patterns
        classes.extend(
            re.findall(r"(?:^|\s)n:\s*([A-Z][A-Za-z0-9_]*)", spec, re.MULTILINE)
        )
        # CSV format: path,type,name columns
        for row_m in re.findall(r",class,([A-Z][A-Za-z0-9_]*),", spec):
            classes.append(row_m)
        for row_m in re.findall(r",(?:function|method),([a-z_][A-Za-z0-9_]*),", spec):
            functions.append(row_m)
        # Gherkin: Feature/Scenario names
        functions.extend(
            re.findall(
                r"Scenario(?:\s+Outline)?:\s*(?:Test\s+)?([A-Za-z_][A-Za-z0-9_]*)", spec
            )
        )
        # Non-Python: func/fn/function declarations
        functions.extend(re.findall(r"\bfunc\s+([A-Za-z_][A-Za-z0-9_]*)", spec))
        functions.extend(re.findall(r"\bfn\s+([A-Za-z_][A-Za-z0-9_]*)", spec))
        functions.extend(
            re.findall(r"\bfunction\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", spec)
        )
        # Java/C# style: "public static Type methodName("
        functions.extend(
            re.findall(
                r"(?:public|private)\s+(?:static\s+)?\w+\s+([a-z][A-Za-z0-9_]*)\s*\(",
                spec,
            )
        )
        # Interfaces/structs/enums
        classes.extend(re.findall(r"\binterface\s+([A-Za-z_][A-Za-z0-9_]*)", spec))
        classes.extend(re.findall(r"\bstruct\s+([A-Za-z_][A-Za-z0-9_]*)", spec))
        classes.extend(re.findall(r"\benum\s+([A-Za-z_][A-Za-z0-9_]*)", spec))

        # Deduplicate while preserving order
        def uniq(items: List[str]) -> List[str]:
            seen = set()
            out: List[str] = []
            for it in items:
                if it and it not in seen:
                    seen.add(it)
                    out.append(it)
            return out

        classes = [c for c in uniq(classes) if c.isidentifier()][:TIMEOUT_5]
        functions = [
            f for f in uniq(functions) if f.isidentifier() and f not in classes
        ][:10]

        language_norm = (language or "python").strip().lower()
        if language_norm == "python":
            code = """from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, List, Dict

"""
        elif language_norm in ("javascript", "typescript"):
            code = """// Auto-generated placeholder
"""
        elif language_norm == "go":
            code = """package main

"""
        elif language_norm == "rust":
            code = """// Auto-generated placeholder
"""
        elif language_norm == "java":
            code = """// Auto-generated placeholder
"""
        elif language_norm == "csharp":
            code = """// Auto-generated placeholder
"""
        elif language_norm == "sql":
            code = """-- Auto-generated placeholder
"""
        else:
            code = """// Auto-generated placeholder
"""

        if not classes and not functions:
            # Always emit something valid
            safe_name = Path(file_name).stem.replace("-", "_").replace(".", "_")
            safe_name = safe_name if safe_name.isidentifier() else "GeneratedModule"
            classes = ["GeneratedClass"]
            functions = ["generated_function"]

        if language_norm == "python":
            for cls in classes:
                code += f"""@dataclass
class {cls}:
    \"\"\"Generated placeholder for {file_name} ({fmt}).\"\"\"
    value: Any = None

"""

            for fn in functions:
                code += f"""def {fn}(*args: Any, **kwargs: Any) -> Any:
    \"\"\"Generated placeholder for {file_name} ({fmt}).\"\"\"
    return None

"""
        elif language_norm in ("javascript", "typescript"):
            for fn in functions:
                export_kw = "export " if language_norm == "typescript" else ""
                code += f"{export_kw}function {fn}(...args) {{\n  return null;\n}}\n\n"
            for cls in classes:
                export_kw = "export " if language_norm == "typescript" else ""
                code += f"{export_kw}class {cls} {{\n  constructor() {{}}\n}}\n\n"
        elif language_norm == "go":
            for fn in functions:
                code += f"func {fn}() {{\n}}\n\n"
            for cls in classes:
                code += f"type {cls} struct {{\n}}\n\n"
        elif language_norm == "rust":
            for fn in functions:
                code += f"pub fn {fn}() {{\n}}\n\n"
            for cls in classes:
                code += f"pub struct {cls} {{\n}}\n\n"
        elif language_norm == "java":
            safe_class = classes[0] if classes else "Generated"
            code += f"public class {safe_class} {{\n"
            for fn in functions:
                code += f"    public static void {fn}() {{ }}\n"
            code += "}\n"
        elif language_norm == "csharp":
            safe_class = classes[0] if classes else "Generated"
            code += f"public class {safe_class} {{\n"
            for fn in functions:
                code += f"    public static void {fn}() {{ }}\n"
            code += "}\n"
        elif language_norm == "sql":
            for cls in classes:
                code += f"CREATE TABLE {cls} (id INT);\n"
        else:
            for fn in functions:
                code += f"function {fn}() {{}}\n"

        return code

    def run_format_benchmark(
        self,
        folder: str,
        formats: List[str] = None,
        limit: Optional[int] = None,
        verbose: bool = False,
    ) -> BenchmarkResult:
        """
        Run format comparison benchmark.

        Compares reproduction quality across different spec formats.

        Args:
            folder: Folder containing source files
            formats: Formats to test (default from config)
            limit: Max files to process
            verbose: Print progress

        Returns:
            BenchmarkResult with format comparison data
        """
        formats = formats or self.config.formats

        client: Optional[BaseLLMClient]
        if self._should_use_llm():
            try:
                client = self._get_client()
            except Exception as e:
                client = None
                if verbose:
                    render.warning(
                        f"LLM not available ({str(e)[:CONSTANT_80]}). Falling back to template mode."
                    )
        else:
            client = None

        result = BenchmarkResult(
            benchmark_type="format",
            source_path=folder,
            provider=getattr(client, "provider", "none") if client else "none",
            model=getattr(client, "model", "none") if client else "none",
        )

        # Analyze project
        path = Path(folder)
        project = analyze_project(str(path), use_treesitter=False)
        modules = project.modules[:limit] if limit else project.modules

        result.total_files = len(modules)

        if verbose:
            render.heading(2, "Format Benchmark")
            render.codeblock(
                "yaml",
                f"folder: {folder}\nfiles: {len(modules)}\nformats: [{', '.join(formats)}]",
            )

        start_time = time.time()

        # Process each file with each format
        for module_info in modules:
            abs_file = path / module_info.path
            if not abs_file.exists():
                continue
            original = abs_file.read_text(encoding="utf-8", errors="ignore")

            single_project = create_single_project(module_info, abs_file)

            file_result = FileResult(
                file_path=str(abs_file),
                language=module_info.language,
                original_size=len(original),
            )

            max_workers = int(getattr(self.config, "workers", 1) or 1)
            if max_workers < 1:
                max_workers = 1

            # Parallelize per-format reproduction (LLM calls) for the same file.
            if len(formats) > 1 and max_workers > 1:
                with ThreadPoolExecutor(max_workers=max_workers) as ex:
                    futs = {
                        ex.submit(
                            self._test_format,
                            single_project,
                            original,
                            fmt,
                            abs_file.name,
                            client,
                            verbose,
                            module_info.language,
                        ): fmt
                        for fmt in formats
                    }
                    for fut in as_completed(futs):
                        fmt = futs[fut]
                        file_result.format_results[fmt] = fut.result()
            else:
                for fmt in formats:
                    fmt_result = self._test_format(
                        single_project,
                        original,
                        fmt,
                        abs_file.name,
                        client,
                        verbose,
                        language=module_info.language,
                    )
                    file_result.format_results[fmt] = fmt_result

            # Set best result as file score
            if file_result.format_results:
                best = max(file_result.format_results.values(), key=lambda r: r.score)
                file_result.score = best.score
                file_result.syntax_ok = best.syntax_ok
                file_result.runs_ok = best.runs_ok

            result.file_results.append(file_result)

        result.total_time = time.time() - start_time

        # Calculate format aggregates – include ALL scores (zeros = failures)
        for fmt in formats:
            scores = [
                fr.format_results[fmt].score
                for fr in result.file_results
                if fmt in fr.format_results
            ]
            if scores:
                result.format_scores[fmt] = sum(scores) / len(scores)

        result.calculate_aggregates()

        return result

    def _test_format(
        self,
        project,
        original: str,
        fmt: str,
        file_name: str,
        client: Optional[BaseLLMClient],
        verbose: bool = False,
        language: str = "python",
    ) -> FormatResult:
        """Test a single format."""
        result = FormatResult(format_name=fmt)

        try:
            # Generate spec
            spec = generate_spec_token(project, fmt)
            result.spec_size = len(spec)
            result.spec_tokens = estimate_tokens(spec)

            # Generate prompt
            prompt = get_token_reproduction_prompt(
                spec, fmt, file_name, language=language
            )

            # Reproduce
            start = time.time()
            if client is None:
                generated = self._template_generate_code(
                    spec, fmt, file_name, language=language
                )
                result.gen_time = 0.0
            else:
                response = client.generate(prompt, max_tokens=self.config.max_tokens)
                result.gen_time = time.time() - start
                generated = _extract_code(response)
            result.generated_size = len(generated)

            # Test quality
            language_norm = (language or "python").strip().lower()
            if language_norm == "python":
                result.syntax_ok = _test_python_syntax(generated)
                if result.syntax_ok:
                    result.runs_ok = _test_python_runs(generated)
            else:
                result.syntax_ok = _basic_syntax_ok(generated, language_norm)
                result.runs_ok = False

            # Calculate metrics
            if original and generated:
                if language_norm == "python":
                    metrics = ReproductionMetrics()
                    analysis = metrics.analyze(
                        original, generated, spec, format_name=fmt
                    )
                    result.score = analysis.overall_score
                    result.similarity = analysis.text.char_similarity
                else:
                    sim = (
                        difflib.SequenceMatcher(
                            None,
                            " ".join(original.split()),
                            " ".join(generated.split()),
                        ).ratio()
                        * 100
                    )
                    struct = _structural_score(original, generated, language_norm)
                    result.similarity = sim
                    result.score = (sim * 0.7) + (struct * 0.3)

            # Efficiency
            if result.spec_size and len(original) > 0:
                result.compression_ratio = result.spec_size / len(original)
            if result.score > 0 and result.spec_tokens > 0:
                result.token_efficiency = result.score / result.spec_tokens * 100

            if verbose:
                if result.score > CONSTANT_50:
                    render.task(f"{fmt}: {result.score:.1f}%", "done")
                else:
                    render.task(f"{fmt}: {result.score:.1f}%", "pending")

        except Exception as e:
            result.error = str(e)[:100]
            if verbose:
                render.task(f"{fmt}: {str(e)[:CONSTANT_50]}", "failed")

        return result

    def run_file_benchmark(
        self,
        file_path: str,
        formats: List[str] = None,
        verbose: bool = False,
    ) -> BenchmarkResult:
        """
        Run benchmark on a single file.

        Args:
            file_path: Path to source file
            formats: Formats to test
            verbose: Print progress

        Returns:
            BenchmarkResult
        """
        formats = formats or self.config.formats

        client: Optional[BaseLLMClient]
        if self._should_use_llm():
            try:
                client = self._get_client()
            except Exception as e:
                client = None
                if verbose:
                    render.warning(
                        f"LLM not available ({str(e)[:CONSTANT_80]}). Falling back to template mode."
                    )
        else:
            client = None

        result = BenchmarkResult(
            benchmark_type="file",
            source_path=file_path,
            total_files=1,
            provider=getattr(client, "provider", "none") if client else "none",
            model=getattr(client, "model", "none") if client else "none",
        )

        path = Path(file_path)
        original = path.read_text()

        # Analyze
        project = analyze_project(str(path.parent), use_treesitter=False)

        module_info = None
        for m in project.modules:
            if Path(m.path).name == path.name:
                module_info = m
                break

        if not module_info:
            result.file_results.append(
                FileResult(
                    file_path=file_path,
                    language="python",
                    error="Module not found in analysis",
                )
            )
            return result

        single_project = create_single_project(module_info, path)

        file_result = FileResult(
            file_path=file_path,
            language="python",
            original_size=len(original),
        )

        start_time = time.time()

        for fmt in formats:
            if verbose:
                render.task(f"Testing {fmt}", "running")

            fmt_result = self._test_format(
                single_project, original, fmt, path.name, client, verbose=False
            )
            file_result.format_results[fmt] = fmt_result

            if verbose:
                if fmt_result.error:
                    render.task(f"{fmt}: {fmt_result.error[:CONSTANT_30]}", "failed")
                elif fmt_result.score > CONSTANT_50:
                    render.task(f"{fmt}: {fmt_result.score:.1f}%", "done")
                else:
                    render.task(f"{fmt}: {fmt_result.score:.1f}%", "pending")

        result.total_time = time.time() - start_time

        # Best format
        if file_result.format_results:
            best = max(file_result.format_results.values(), key=lambda r: r.score)
            file_result.score = best.score
            file_result.syntax_ok = best.syntax_ok
            result.best_format = best.format_name
            result.best_score = best.score

        result.file_results.append(file_result)
        result.calculate_aggregates()

        return result

    def run_function_benchmark(
        self,
        file_path: str,
        function_names: List[str] = None,
        limit: Optional[int] = None,
        verbose: bool = False,
    ) -> BenchmarkResult:
        """
        Run function-level reproduction benchmark.

        Args:
            file_path: Path to source file
            function_names: Specific functions to test (None = all)
            limit: Max functions to test
            verbose: Print progress

        Returns:
            BenchmarkResult with function results
        """
        from ..parsers import UniversalParser

        client: Optional[BaseLLMClient]
        if self._should_use_llm():
            try:
                client = self._get_client()
            except Exception as e:
                client = None
                if verbose:
                    render.warning(
                        f"LLM not available ({str(e)[:CONSTANT_80]}). Falling back to template mode."
                    )
        else:
            client = None

        result = BenchmarkResult(
            benchmark_type="function",
            source_path=file_path,
            provider=getattr(client, "provider", "none") if client else "none",
            model=getattr(client, "model", "none") if client else "none",
        )

        path = Path(file_path)
        content = path.read_text()

        # Detect language
        ext_to_lang = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".go": "go",
        }
        language = ext_to_lang.get(path.suffix, "python")

        # Parse file
        parser = UniversalParser()
        module = parser.parse(str(path), content, language)

        functions = module.functions
        if function_names:
            functions = [f for f in functions if f.name in function_names]
        if limit:
            functions = functions[:limit]

        result.total_functions = len(functions)

        if verbose:
            print(f"Function Benchmark: {file_path}")
            print(f"Functions: {len(functions)}")

        start_time = time.time()

        for func in functions:
            func_result = self._test_function(
                func, content, language, path, client, verbose
            )
            result.function_results.append(func_result)

        result.total_time = time.time() - start_time
        result.calculate_aggregates()

        return result

    def _test_function(
        self,
        func,
        content: str,
        language: str,
        file_path: Path,
        client: Optional[BaseLLMClient],
        verbose: bool = False,
    ) -> FunctionResult:
        """Test reproduction of a single function."""
        result = FunctionResult(
            file_path=str(file_path),
            function_name=func.name,
            language=language,
        )

        try:
            # Extract original code
            lines = content.split("\n")
            start = func.start_line - 1
            end = func.end_line if func.end_line else start + func.lines

            # Include decorators for Python
            if language == "python" and start > 0:
                i = start - 1
                while i >= 0 and lines[i].strip().startswith("@"):
                    start = i
                    i -= 1

            result.original_code = "\n".join(lines[start:end])

            # Create spec with richer context
            calls_str = ", ".join(getattr(func, "calls", []) or []) or "None"
            raises_str = ", ".join(getattr(func, "raises", []) or []) or "None"
            cc = getattr(func, "complexity", 1) or 1
            spec = f"""Function: {func.name}
Language: {language}
Signature: {func.name}({", ".join(func.params)}) -> {func.return_type or "None"}
Description: {func.intent or func.docstring or "No description"}
Is Async: {func.is_async}
Decorators: {", ".join(func.decorators) if func.decorators else "None"}
Calls: {calls_str}
Raises: {raises_str}
Complexity: {cc}
Lines: {func.lines}
"""

            prompt = f"""Generate ONLY the complete function code based on this specification:

{spec}

REQUIREMENTS:
- Generate a complete, working {language} function with REAL logic (not a stub)
- Match the signature EXACTLY: {func.name}({", ".join(func.params)}) -> {func.return_type or "None"}
- Use the Description to implement actual behavior
- Include decorators if specified
- The function should be ~{func.lines} lines long
- Include proper error handling if Raises is specified
- Output ONLY the function code, no explanations

```{language}
"""

            if client is None:
                # Offline fallback: emit a skeleton function with matching name/params.
                params = (
                    ", ".join(func.params)
                    if getattr(func, "params", None)
                    else "*args, **kwargs"
                )
                rt = func.return_type or "Any"
                async_kw = "async " if getattr(func, "is_async", False) else ""
                result.reproduced_code = (
                    f"{async_kw}def {func.name}({params}) -> {rt}:\n    return None\n"
                )
                result.gen_time = 0.0
            else:
                start_time = time.time()
                response = client.generate(prompt, max_tokens=MAX_3000)
                result.gen_time = time.time() - start_time
                result.reproduced_code = _extract_code(response)

            # Test syntax
            if language == "python":
                result.syntax_ok = _test_python_syntax(result.reproduced_code)
            else:
                result.syntax_ok = len(result.reproduced_code) > 10

            # Calculate similarity
            from difflib import SequenceMatcher

            orig_norm = " ".join(result.original_code.split())
            repr_norm = " ".join(result.reproduced_code.split())
            result.similarity = (
                SequenceMatcher(None, orig_norm, repr_norm).ratio() * 100
            )

            if verbose:
                syntax = "S✓" if result.syntax_ok else "S✗"
                print(f"  {func.name}: {result.similarity:.1f}% {syntax}")

        except Exception as e:
            result.error = str(e)[:100]
            if verbose:
                print(f"  {func.name}: ERROR - {e}")

        return result

    def run_project_benchmark(
        self,
        project_path: str,
        formats: List[str] = None,
        limit: Optional[int] = None,
        verbose: bool = False,
    ) -> BenchmarkResult:
        """
        Run benchmark on entire project.

        Args:
            project_path: Path to project
            formats: Formats to test
            limit: Max files to process
            verbose: Print progress

        Returns:
            BenchmarkResult with project-level data
        """
        formats = formats or self.config.formats

        client: Optional[BaseLLMClient]
        if self._should_use_llm():
            try:
                client = self._get_client()
            except Exception as e:
                client = None
                if verbose:
                    render.warning(
                        f"LLM not available ({str(e)[:CONSTANT_80]}). Falling back to template mode."
                    )
        else:
            client = None

        result = BenchmarkResult(
            benchmark_type="project",
            source_path=project_path,
            provider=getattr(client, "provider", "none") if client else "none",
            model=getattr(client, "model", "none") if client else "none",
        )

        # Analyze
        project = analyze_project(project_path, use_treesitter=False)
        modules = project.modules[:limit] if limit else project.modules
        result.total_files = len(modules)

        if verbose:
            print(f"Project Benchmark: {project_path}")
            print(f"Files: {len(modules)}, Formats: {', '.join(formats)}")

        start_time = time.time()

        for fmt in formats:
            if verbose:
                print(f"\n--- Format: {fmt.upper()} ---")

            max_workers = int(getattr(self.config, "workers", 1) or 1)
            if max_workers < 1:
                max_workers = 1

            # Parallelize per-module reproduction for a given format.
            if len(modules) > 1 and max_workers > 1:
                with ThreadPoolExecutor(max_workers=max_workers) as ex:
                    futs = {
                        ex.submit(
                            self._reproduce_module,
                            module,
                            fmt,
                            project_path,
                            client,
                            verbose,
                        ): (i, module)
                        for i, module in enumerate(modules)
                    }
                    for fut in as_completed(futs):
                        i, _module = futs[fut]
                        file_result = fut.result()

                        # Add format to result
                        if file_result.format_results:
                            fmt_result = list(file_result.format_results.values())[0]
                        else:
                            fmt_result = FormatResult(
                                format_name=fmt, score=file_result.score
                            )
                            file_result.format_results[fmt] = fmt_result

                        # Find existing file result or create new
                        existing = None
                        for fr in result.file_results:
                            if fr.file_path == file_result.file_path:
                                existing = fr
                                break

                        if existing:
                            existing.format_results[fmt] = fmt_result
                        else:
                            result.file_results.append(file_result)

                        if verbose:
                            status = "✓" if file_result.score > CONSTANT_50 else "○"
                            print(
                                f"  [{i + 1}/{len(modules)}] {Path(file_result.file_path).name}: {file_result.score:.1f}% {status}"
                            )
            else:
                for i, module in enumerate(modules):
                    file_result = self._reproduce_module(
                        module, fmt, project_path, client, verbose
                    )

                    # Add format to result
                    if file_result.format_results:
                        fmt_result = list(file_result.format_results.values())[0]
                    else:
                        fmt_result = FormatResult(
                            format_name=fmt, score=file_result.score
                        )
                        file_result.format_results[fmt] = fmt_result

                    # Find existing file result or create new
                    existing = None
                    for fr in result.file_results:
                        if fr.file_path == file_result.file_path:
                            existing = fr
                            break

                    if existing:
                        existing.format_results[fmt] = fmt_result
                    else:
                        result.file_results.append(file_result)

                    if verbose:
                        status = "✓" if file_result.score > CONSTANT_50 else "○"
                        print(
                            f"  [{i + 1}/{len(modules)}] {Path(file_result.file_path).name}: {file_result.score:.1f}% {status}"
                        )

        result.total_time = time.time() - start_time

        # Calculate format aggregates – include ALL scores (zeros = failures)
        for fmt in formats:
            scores = []
            for fr in result.file_results:
                if fmt in fr.format_results:
                    scores.append(fr.format_results[fmt].score)
            if scores:
                result.format_scores[fmt] = sum(scores) / len(scores)

        # Recalculate each file's score as average across all its formats
        for fr in result.file_results:
            if fr.format_results:
                fmt_scores = [r.score for r in fr.format_results.values()]
                fr.score = sum(fmt_scores) / len(fmt_scores)
                fr.syntax_ok = all(r.syntax_ok for r in fr.format_results.values())
                fr.runs_ok = any(r.runs_ok for r in fr.format_results.values())

        result.calculate_aggregates()

        return result

    def _reproduce_module(
        self,
        module_info,
        fmt: str,
        project_root: str,
        client: Optional[BaseLLMClient],
        verbose: bool = False,
    ) -> FileResult:
        """Reproduce a single module."""
        from datetime import datetime

        from ..models import ProjectInfo

        # Build path
        rel_path = module_info.path
        if not Path(rel_path).is_absolute():
            abs_path = Path(project_root) / rel_path
        else:
            abs_path = Path(rel_path)

        file_result = FileResult(
            file_path=str(abs_path),
            language=module_info.language,
        )

        try:
            original = abs_path.read_text()
            file_result.original_size = len(original)
        except Exception as e:
            file_result.error = f"Cannot read file: {e}"
            return file_result

        try:
            # Create single-file project
            single_project = ProjectInfo(
                name=abs_path.name,
                root_path=str(abs_path.parent),
                languages={module_info.language: 1},
                modules=[module_info],
                dependency_graph={},
                dependency_metrics={},
                entrypoints=[],
                similar_functions={},
                total_files=1,
                total_lines=module_info.lines_total,
                generated_at=datetime.now().isoformat(),
            )

            # Test format
            fmt_result = self._test_format(
                single_project,
                original,
                fmt,
                abs_path.name,
                client,
                verbose=False,
                language=module_info.language,
            )

            file_result.format_results[fmt] = fmt_result
            file_result.score = fmt_result.score
            file_result.syntax_ok = fmt_result.syntax_ok
            file_result.runs_ok = fmt_result.runs_ok
            file_result.gen_time = fmt_result.gen_time

        except Exception as e:
            file_result.error = str(e)[:100]

        return file_result


def run_benchmark(
    source: str,
    benchmark_type: str = "format",
    formats: List[str] = None,
    limit: Optional[int] = None,
    output: Optional[str] = None,
    verbose: bool = False,
) -> BenchmarkResult:
    """
    Convenience function to run benchmarks.

    Args:
        source: Source file or folder
        benchmark_type: 'format', 'file', 'function', or 'project'
        formats: Formats to test
        limit: Max items to process
        output: Output file path
        verbose: Print progress

    Returns:
        BenchmarkResult

    Example:
        result = run_benchmark('tests/samples/', 'format', formats=['yaml', 'toon'])
        result.save('output/benchmark.json')
    """
    runner = BenchmarkRunner()

    if benchmark_type == "format":
        result = runner.run_format_benchmark(source, formats, limit, verbose)
    elif benchmark_type == "file":
        result = runner.run_file_benchmark(source, formats, verbose)
    elif benchmark_type == "function":
        result = runner.run_function_benchmark(source, limit=limit, verbose=verbose)
    elif benchmark_type == "project":
        result = runner.run_project_benchmark(source, formats, limit, verbose)
    else:
        raise ValueError(f"Unknown benchmark type: {benchmark_type}")

    if output:
        result.save(output)

    return result
