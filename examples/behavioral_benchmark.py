#!/usr/bin/env python3
"""Behavioral benchmark: compare runtime behavior of reproduced functions vs original.

This benchmark runs a small set of deterministic input/output cases for
functions in `tests/samples/sample_functions.py`.

Input:
- A function benchmark JSON produced by BenchmarkRunner (make benchmark-function)
  which contains `reproduced_code` per function.

Output:
- JSON report with pass/fail per function and aggregate pass rate.

Notes:
- This does NOT sandbox arbitrary code execution. It is designed for trusted
  local runs in this repository.
"""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple


@dataclass
class CaseResult:
    name: str
    ok: bool
    expected: Any = None
    got: Any = None
    error: str = ""


@dataclass
class FunctionBehaviorResult:
    function_name: str
    cases: List[CaseResult]
    ok: bool
    skipped: bool = False
    error: str = ""


def _load_module_from_path(path: Path, module_name: str) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _exec_function_from_code(code: str, function_name: str) -> Callable[..., Any]:
    import json as _json
    import os as _os
    from typing import Any as _Any, Dict as _Dict, List as _List, Optional as _Optional

    glb: Dict[str, Any] = {
        "__builtins__": __builtins__,
        "os": _os,
        "json": _json,
        "Any": _Any,
        "Dict": _Dict,
        "List": _List,
        "Optional": _Optional,
    }
    loc: Dict[str, Any] = {}
    exec(code, glb, loc)
    fn = loc.get(function_name) or glb.get(function_name)
    if not callable(fn):
        raise RuntimeError(f"Function {function_name} not found after exec")
    return fn


def _values_equal(got: Any, expected: Any) -> bool:
    if isinstance(expected, float) and isinstance(got, (float, int)):
        return abs(float(got) - float(expected)) <= 1e-9
    return got == expected


def _run_case(label: str, fn: Callable[[], Any], expected: Any) -> CaseResult:
    try:
        got = fn()
        ok = _values_equal(got, expected)
        err = "" if ok else "mismatch"
        return CaseResult(name=label, ok=ok, expected=expected, got=got, error=err)
    except Exception as e:
        return CaseResult(
            name=label, ok=False, expected=expected, got=None, error=str(e)[:200]
        )


def _looks_like_template_stub(code: str) -> bool:
    s = (code or "").strip()
    if not s:
        return True
    # Very common offline skeleton pattern in this repo's benchmarks.
    return "return None" in s and "pass" not in s and "raise" not in s


def _cases_for(
    function_name: str,
) -> List[Tuple[str, Callable[[], Tuple[Tuple[Any, ...], Dict[str, Any]]]]]:
    """Return list of (label, args_kwargs_builder)."""
    if function_name == "calculate_total":
        return [
            ("basic", lambda: (([100, 200],), {"tax_rate": 0.1})),
            ("no_tax", lambda: (([100, 200],), {"tax_rate": 0.0})),
        ]
    if function_name == "filter_by_status":
        records = [
            {"id": 1, "status": "ok"},
            {"id": 2, "status": "fail"},
            {"id": 3, "status": "ok"},
        ]
        return [("ok_only", lambda: ((records, "ok"), {}))]
    if function_name == "merge_configs":
        base = {"a": 1, "b": 2}
        override = {"b": 9, "c": 3}
        return [("merge", lambda: ((base, override), {}))]
    if function_name == "validate_email":
        return [
            ("valid", lambda: (("a@b.com",), {})),
            ("invalid_missing_at", lambda: (("abc",), {})),
            ("invalid_domain", lambda: (("a@b",), {})),
        ]
    if function_name == "load_json_file":

        def builder_valid() -> Tuple[Tuple[Any, ...], Dict[str, Any]]:
            td = tempfile.mkdtemp(prefix="c2l_json_")
            p_ok = Path(td) / "ok.json"
            p_ok.write_text('{"x": 1}', encoding="utf-8")
            return ((str(p_ok),), {})

        def builder_invalid() -> Tuple[Tuple[Any, ...], Dict[str, Any]]:
            td = tempfile.mkdtemp(prefix="c2l_json_")
            p_bad = Path(td) / "bad.json"
            p_bad.write_text('{"x": ', encoding="utf-8")
            return ((str(p_bad),), {})

        def builder_missing() -> Tuple[Tuple[Any, ...], Dict[str, Any]]:
            td = tempfile.mkdtemp(prefix="c2l_json_")
            return ((str(Path(td) / "missing.json"),), {})

        return [
            ("valid_file", builder_valid),
            ("invalid_json", builder_invalid),
            ("missing", builder_missing),
        ]
    if function_name == "get_env_or_default":
        return [
            ("default", lambda: (("C2L_TEST_MISSING", "zzz"), {})),
            (
                "present",
                lambda: (
                    ("C2L_TEST_KEY", "zzz"),
                    {"__setenv": ("C2L_TEST_KEY", "abc")},
                ),
            ),
        ]
    if function_name == "chunk_list":
        return [("chunks", lambda: (([1, 2, 3, 4, 5], 2), {}))]
    if function_name == "format_currency":
        return [
            ("usd", lambda: ((12345, "USD"), {})),
            ("eur", lambda: ((0, "EUR"), {})),
        ]
    return []


def _apply_env_hook(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    hook = kwargs.pop("__setenv", None)
    if hook:
        k, v = hook
        os.environ[k] = v
    return kwargs


def main() -> None:
    bench_path = Path(
        os.environ.get("BENCH_FUNCTION_JSON", "examples/output/benchmark_function.json")
    )
    out_dir = Path(os.environ.get("BENCH_OUTPUT", "examples/output"))
    source_path = Path(
        os.environ.get("BENCH_FUNCTION_SOURCE", "tests/samples/sample_functions.py")
    )

    out_dir.mkdir(parents=True, exist_ok=True)

    d = json.loads(bench_path.read_text(encoding="utf-8"))
    function_results = d.get("function_results") or []

    original_mod = _load_module_from_path(source_path, "c2l_sample_functions")

    results: List[FunctionBehaviorResult] = []

    for fr in function_results:
        fn_name = fr.get("function_name")
        reproduced_code = fr.get("reproduced_code") or ""

        if not fn_name:
            continue

        cases_spec = _cases_for(fn_name)
        if not cases_spec:
            results.append(
                FunctionBehaviorResult(
                    function_name=fn_name, cases=[], ok=False, error="no cases defined"
                )
            )
            continue

        if _looks_like_template_stub(reproduced_code):
            results.append(
                FunctionBehaviorResult(
                    function_name=fn_name,
                    cases=[],
                    ok=False,
                    skipped=True,
                    error="template stub (run with LLM to measure behavioral equivalence)",
                )
            )
            continue

        try:
            repro_fn = _exec_function_from_code(reproduced_code, fn_name)
        except Exception as e:
            results.append(
                FunctionBehaviorResult(
                    function_name=fn_name,
                    cases=[],
                    ok=False,
                    error=f"exec failed: {str(e)[:200]}",
                )
            )
            continue

        case_results = []
        for label, builder in cases_spec:
            try:
                args, kwargs = builder()
                kwargs = dict(kwargs)
                kwargs = _apply_env_hook(kwargs)
                expected_val = getattr(original_mod, fn_name)(*args, **kwargs)
            except Exception as e:
                case_results.append(
                    CaseResult(
                        name=label, ok=False, error=f"original failed: {str(e)[:200]}"
                    )
                )
                continue

            def thunk(a=args, k=kwargs):
                return repro_fn(*a, **k)

            case_results.append(_run_case(label, thunk, expected_val))

        ok = all(c.ok for c in case_results) if case_results else False
        results.append(
            FunctionBehaviorResult(function_name=fn_name, cases=case_results, ok=ok)
        )

    total = len(results)
    skipped = sum(1 for r in results if r.skipped)
    considered = max(total - skipped, 0)
    passed = sum(1 for r in results if r.ok)
    pass_rate = (passed / considered * 100) if considered else 0.0

    out = {
        "benchmark_type": "behavioral",
        "timestamp": d.get("timestamp"),
        "source": str(source_path),
        "input_function_benchmark": str(bench_path),
        "note": "If function reproduction was run with --no-llm template stubs, behavioral equivalence is expected to be skipped/low.",
        "total_functions": total,
        "skipped_functions": skipped,
        "considered_functions": considered,
        "passed_functions": passed,
        "pass_rate": pass_rate,
        "results": [
            {
                "function_name": r.function_name,
                "ok": r.ok,
                "skipped": r.skipped,
                "error": r.error,
                "cases": [asdict(c) for c in r.cases],
            }
            for r in results
        ],
    }

    out_path = out_dir / "benchmark_behavioral.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(str(out_path))


if __name__ == "__main__":
    main()
