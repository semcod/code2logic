#!/usr/bin/env python3
"""Generate a Markdown report linking benchmark artifacts and showing commands used.

This is intentionally simple and file-based so `make benchmark` produces
traceable, reviewable outputs.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class Artifact:
    label: str
    path: Path
    description: str


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _sizeof(path: Path) -> int:
    try:
        return path.stat().st_size
    except FileNotFoundError:
        return 0


def _fmt_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / 1024 / 1024:.1f} MB"


def _token_estimate_bytes(n: int) -> int:
    return n // 4


def _calc_function_summary(d: Dict[str, Any]) -> Tuple[int, float, float]:
    """Return (n_functions, avg_similarity, syntax_ok_rate)."""
    fr = d.get("function_results") or []
    if not fr:
        return 0, 0.0, 0.0
    sims = [x.get("similarity", 0.0) for x in fr]
    avg_sim = sum(sims) / len(sims) if sims else 0.0
    ok = sum(1 for x in fr if x.get("syntax_ok"))
    return len(fr), avg_sim, (ok / len(fr)) * 100


def _calc_file_summary(d: Dict[str, Any]) -> Tuple[int, float, float, float]:
    """Return (n_files, avg_score, syntax_ok_rate, runs_ok_rate)."""
    n_files = int(d.get("total_files") or 0)
    return (
        n_files,
        float(d.get("avg_score") or 0.0),
        float(d.get("syntax_ok_rate") or 0.0),
        float(d.get("runs_ok_rate") or 0.0),
    )


def _read_commands(commands_path: Path) -> List[str]:
    if not commands_path.exists():
        return []
    lines = [l.rstrip() for l in commands_path.read_text(encoding="utf-8").splitlines()]
    return [l for l in lines if l.strip()]


def main() -> None:
    out_dir = Path(os.environ.get("BENCH_OUTPUT", "examples/output")).resolve()
    report_path = out_dir / "BENCHMARK_REPORT.md"
    commands_path = out_dir / "BENCHMARK_COMMANDS.sh"

    artifacts: List[Artifact] = [
        Artifact(
            "Format benchmark",
            out_dir / "benchmark_format.json",
            "Format comparison across multiple files",
        ),
        Artifact(
            "Function-logic format benchmark",
            out_dir / "benchmark_function_logic.json",
            "Standalone format benchmark for function-logic TOON (function.toon)",
        ),
        Artifact(
            "Token benchmark",
            out_dir / "benchmark_token.json",
            "Token efficiency comparison",
        ),
        Artifact(
            "Project benchmark",
            out_dir / "benchmark_project.json",
            "Project-level benchmark",
        ),
        Artifact(
            "Function benchmark",
            out_dir / "benchmark_function.json",
            "Function-level benchmark",
        ),
        Artifact(
            "Behavioral benchmark",
            out_dir / "benchmark_behavioral.json",
            "Behavioral equivalence tests (original vs reproduced)",
        ),
        Artifact(
            "Self-analysis: TOON", out_dir / "project.toon", "Project TOON output"
        ),
        Artifact(
            "Self-analysis: function-logic TOON",
            out_dir / "function.toon",
            "Function-logic (TOON; generated with --function-logic function.toon --with-schema --compact --no-repeat-module)",
        ),
        Artifact(
            "Schema: TOON",
            out_dir / "project.toon-schema.json",
            "JSON Schema for project.toon",
        ),
        Artifact(
            "Schema: function-logic",
            out_dir / "function-schema.json",
            "JSON Schema for function.toon",
        ),
        Artifact(
            "Self-analysis: YAML", out_dir / "project.yaml", "YAML compact output"
        ),
        Artifact("Self-analysis: JSON", out_dir / "project.json", "JSON output"),
        Artifact("Self-analysis: Markdown", out_dir / "project.md", "Markdown output"),
        Artifact(
            "Self-analysis: Compact", out_dir / "project.txt", "Compact text output"
        ),
        Artifact("Self-analysis: CSV", out_dir / "project.csv", "CSV standard output"),
    ]

    fmt = _load_json(out_dir / "benchmark_format.json")
    flog = _load_json(out_dir / "benchmark_function_logic.json")
    tok = _load_json(out_dir / "benchmark_token.json")
    proj = _load_json(out_dir / "benchmark_project.json")
    fun = _load_json(out_dir / "benchmark_function.json")
    beh = _load_json(out_dir / "benchmark_behavioral.json")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines: List[str] = []
    lines.append("# Benchmark Report")
    lines.append("")
    lines.append(f"> Generated: {now}")
    lines.append(f"> Output dir: `{out_dir}`")
    lines.append("")

    lines.append("## Summary")
    lines.append("")
    lines.append(
        "| Benchmark | Items | Score/Similarity | Syntax OK | Runs OK | Fail% | Best |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---|")

    def _fail_pct(d: Optional[Dict[str, Any]]) -> str:
        fr = float(d.get("failure_rate", 0.0)) if d else 0.0
        return f"{fr:.0f}%" if fr > 0 else "0%"

    if fmt:
        n, avg, syn, run = _calc_file_summary(fmt)
        lines.append(
            f"| Format | {n} files | {avg:.1f}% | {syn:.0f}% | {run:.0f}% | {_fail_pct(fmt)} | {fmt.get('best_format', '')} ({fmt.get('best_score', 0):.1f}%) |"
        )
    if flog:
        n, avg, syn, run = _calc_file_summary(flog)
        lines.append(
            f"| Function-logic format | {n} files | {avg:.1f}% | {syn:.0f}% | {run:.0f}% | {_fail_pct(flog)} | {flog.get('best_format', '')} ({flog.get('best_score', 0):.1f}%) |"
        )
    if tok:
        n, avg, syn, run = _calc_file_summary(tok)
        lines.append(
            f"| Token | {n} files | {avg:.1f}% | {syn:.0f}% | {run:.0f}% | {_fail_pct(tok)} | {tok.get('best_format', '')} ({tok.get('best_score', 0):.1f}%) |"
        )
    if proj:
        n, avg, syn, run = _calc_file_summary(proj)
        lines.append(
            f"| Project | {n} files | {avg:.1f}% | {syn:.0f}% | {run:.0f}% | {_fail_pct(proj)} | {proj.get('best_format', '')} ({proj.get('best_score', 0):.1f}%) |"
        )
    if fun:
        nfun, avg_sim, syn = _calc_function_summary(fun)
        lines.append(
            f"| Function | {nfun} funcs | {avg_sim:.1f}% | {syn:.0f}% | - | - | - |"
        )

    if beh:
        total = int(beh.get("total_functions") or 0)
        passed = int(beh.get("passed_functions") or 0)
        skipped = int(beh.get("skipped_functions") or 0)
        considered = int(beh.get("considered_functions") or max(total - skipped, 0))
        rate = float(beh.get("pass_rate") or 0.0)
        suffix = f"{passed}/{considered} passed"
        if skipped:
            suffix += f" ({skipped} skipped)"
        lines.append(f"| Behavioral | {total} funcs | {rate:.1f}% | - | - | {suffix} |")

    lines.append("")

    lines.append("## Artifacts")
    lines.append("")
    lines.append("| Artifact | File | Size | ~Tokens | Description |")
    lines.append("|---|---|---:|---:|---|")
    for a in artifacts:
        rel = a.path.relative_to(out_dir) if out_dir in a.path.parents else a.path
        size = _sizeof(a.path)
        tok_est = _token_estimate_bytes(size)
        # Create clickable markdown link
        file_cell = (
            f"[`{rel}`]({rel})" if isinstance(rel, Path) else f"[`{rel}`]({rel})"
        )
        if a.path.exists():
            lines.append(
                f"| {a.label} | {file_cell} | {_fmt_bytes(size)} | {tok_est:,} | {a.description} |"
            )
        else:
            lines.append(
                f"| {a.label} | {file_cell} | - | - | {a.description} *(missing)* |"
            )

    lines.append("")

    lines.append("## Commands used")
    lines.append("")
    cmds = _read_commands(commands_path)
    if cmds:
        lines.append("```bash")
        lines.extend(cmds)
        lines.append("```")
    else:
        lines.append(f"Missing `{commands_path.name}`. Re-run `make benchmark`. ")

    lines.append("")
    lines.append("## Notes on score correctness")
    lines.append("")
    lines.append(
        "- The benchmark **does not prove functional equivalence**. It is a weighted heuristic based on:"
    )
    lines.append("  - Text similarity (SequenceMatcher / token overlap)")
    lines.append(
        "  - Structural heuristics (counts of classes/functions/imports/attributes)"
    )
    lines.append(
        "  - Semantic heuristics (identifier overlap, signature/decorator presence, type hints, docstrings)"
    )
    lines.append(
        "- In `--no-llm` template mode the reproduced code is a placeholder skeleton, so scores reflect spec extractability rather than true code regeneration."
    )
    lines.append(
        "- The behavioral benchmark will **skip** functions that look like template stubs (e.g. `return None`). Run with an LLM-enabled function reproduction to measure behavioral equivalence."
    )

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(str(report_path))


if __name__ == "__main__":
    main()
