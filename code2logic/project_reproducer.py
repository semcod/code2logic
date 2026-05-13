"""
Project-level Code Reproduction.

Handles multi-file projects with:
- Dependency tracking between files
- Parallel processing
- Incremental reproduction
- Cross-language support

Usage:
    from code2logic.project_reproducer import ProjectReproducer

    reproducer = ProjectReproducer()
    result = reproducer.reproduce_project("path/to/project")
"""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

# Load .env
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from .llm_clients import BaseLLMClient, get_client
from .universal import (
    Language,
    UniversalParser,
    UniversalReproducer,
)

# Supported file extensions
SUPPORTED_EXTENSIONS = {
    ".py": Language.PYTHON,
    ".js": Language.JAVASCRIPT,
    ".ts": Language.TYPESCRIPT,
    ".tsx": Language.TYPESCRIPT,
    ".go": Language.GO,
    ".rs": Language.RUST,
    ".java": Language.JAVA,
    ".sql": Language.SQL,
    ".cs": Language.CSHARP,
}


@dataclass
class FileResult:
    """Result for a single file reproduction."""

    file_path: str
    language: str
    source_chars: int
    logic_chars: int
    generated_chars: int
    compression: float
    similarity: float
    structural: float
    success: bool
    error: Optional[str] = None


@dataclass
class ProjectResult:
    """Result for project reproduction."""

    project_path: str
    total_files: int
    successful_files: int
    failed_files: int
    total_source_chars: int
    total_logic_chars: int
    total_generated_chars: int
    avg_compression: float
    avg_similarity: float
    avg_structural: float
    files: List[FileResult] = field(default_factory=list)
    by_language: Dict[str, Dict[str, float]] = field(default_factory=dict)


class ProjectReproducer:
    """Multi-file project reproduction system."""

    def __init__(
        self,
        client: BaseLLMClient = None,
        max_workers: int = 4,
        target_lang: str = None,
        use_llm: bool = True,
    ):
        """Initialize project reproducer.

        Args:
            client: LLM client
            max_workers: Max parallel workers
            target_lang: Target language for all files (None = same as source)
        """
        self.client = client
        self.max_workers = max_workers
        self.target_lang = target_lang
        self.use_llm = use_llm
        self.parser = UniversalParser()
        self.reproducer = UniversalReproducer(client)

    def _get_client(self) -> BaseLLMClient:
        """Get or create LLM client."""
        if self.client is None:
            self.client = get_client()
            # Keep UniversalReproducer in sync
            self.reproducer.client = self.client
        return self.client

    def find_source_files(
        self,
        project_path: str,
        extensions: Set[str] = None,
        exclude_patterns: List[str] = None,
    ) -> List[Path]:
        """Find all source files in project.

        Args:
            project_path: Project root path
            extensions: File extensions to include
            exclude_patterns: Patterns to exclude

        Returns:
            List of source file paths
        """
        extensions = extensions or set(SUPPORTED_EXTENSIONS.keys())
        exclude_patterns = exclude_patterns or [
            "__pycache__",
            "node_modules",
            ".git",
            "venv",
            "dist",
            "build",
            ".tox",
            ".pytest_cache",
        ]

        files = []
        root = Path(project_path)

        for path in root.rglob("*"):
            if not path.is_file():
                continue

            if path.suffix not in extensions:
                continue

            # Check exclusions
            path_str = str(path)
            if any(pattern in path_str for pattern in exclude_patterns):
                continue

            files.append(path)

        return sorted(files)

    def reproduce_file(
        self,
        file_path: Path,
        output_dir: Path,
    ) -> FileResult:
        """Reproduce a single file.

        Args:
            file_path: Source file path
            output_dir: Output directory

        Returns:
            FileResult
        """
        try:
            if self.use_llm:
                # Ensure we have a client once; UniversalReproducer will also lazy-load,
                # but this keeps provider selection consistent across files.
                self._get_client()
            result = self.reproducer.reproduce(
                str(file_path),
                target_lang=self.target_lang,
                output_dir=str(output_dir / file_path.stem),
                use_llm=self.use_llm,
            )

            return FileResult(
                file_path=str(file_path),
                language=result["source_language"],
                source_chars=result["source_chars"],
                logic_chars=result["logic_chars"],
                generated_chars=result["generated_chars"],
                compression=result["compression_ratio"],
                similarity=result["similarity"],
                structural=result["structural_score"],
                success=True,
            )

        except Exception as e:
            return FileResult(
                file_path=str(file_path),
                language="unknown",
                source_chars=0,
                logic_chars=0,
                generated_chars=0,
                compression=0,
                similarity=0,
                structural=0,
                success=False,
                error=str(e),
            )

    def reproduce_project(
        self,
        project_path: str,
        output_dir: str = None,
        parallel: bool = False,
    ) -> ProjectResult:
        """Reproduce entire project.

        Args:
            project_path: Project root path
            output_dir: Output directory
            parallel: Use parallel processing

        Returns:
            ProjectResult
        """
        output_path = Path(output_dir or f"{project_path}_reproduced")
        output_path.mkdir(parents=True, exist_ok=True)

        # Find files
        files = self.find_source_files(project_path)

        print(f"Found {len(files)} source files")

        # Reproduce files
        results = []

        if parallel and len(files) > 1:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {
                    executor.submit(self.reproduce_file, f, output_path): f
                    for f in files
                }

                for future in as_completed(futures):
                    file_path = futures[future]
                    try:
                        result = future.result()
                        results.append(result)
                        status = "✓" if result.success else "✗"
                        print(f"  {status} {file_path.name}")
                    except Exception as e:
                        print(f"  ✗ {file_path.name}: {e}")
        else:
            for file_path in files:
                print(f"  Processing {file_path.name}...", end=" ")
                result = self.reproduce_file(file_path, output_path)
                results.append(result)

                if result.success:
                    print(f"✓ {result.similarity:.1f}%")
                else:
                    print(f"✗ {result.error[:30]}")

        # Aggregate results
        project_result = self._aggregate_results(project_path, results)

        # Save report
        self._save_report(output_path, project_result)

        return project_result

    def _aggregate_results(
        self,
        project_path: str,
        results: List[FileResult],
    ) -> ProjectResult:
        """Aggregate file results into project result."""
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]

        total_source = sum(r.source_chars for r in successful)
        total_logic = sum(r.logic_chars for r in successful)
        total_generated = sum(r.generated_chars for r in successful)

        avg_compression = (
            sum(r.compression for r in successful) / len(successful)
            if successful
            else 0
        )
        avg_similarity = (
            sum(r.similarity for r in successful) / len(successful) if successful else 0
        )
        avg_structural = (
            sum(r.structural for r in successful) / len(successful) if successful else 0
        )

        # Group by language
        by_language = {}
        for r in successful:
            lang = r.language
            if lang not in by_language:
                by_language[lang] = {
                    "count": 0,
                    "similarity": 0,
                    "structural": 0,
                }
            by_language[lang]["count"] += 1
            by_language[lang]["similarity"] += r.similarity
            by_language[lang]["structural"] += r.structural

        for _lang, data in by_language.items():
            data["similarity"] /= data["count"]
            data["structural"] /= data["count"]

        return ProjectResult(
            project_path=project_path,
            total_files=len(results),
            successful_files=len(successful),
            failed_files=len(failed),
            total_source_chars=total_source,
            total_logic_chars=total_logic,
            total_generated_chars=total_generated,
            avg_compression=avg_compression,
            avg_similarity=avg_similarity,
            avg_structural=avg_structural,
            files=results,
            by_language=by_language,
        )

    def _save_report(self, output_dir: Path, result: ProjectResult):
        """Save project reproduction report."""
        # JSON data
        data = asdict(result)
        (output_dir / "project_results.json").write_text(json.dumps(data, indent=2))

        # Markdown report
        report = f"""# Project Reproduction Report

> Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")}
> Project: {result.project_path}

## Summary

| Metric | Value |
|--------|-------|
| Total files | {result.total_files} |
| Successful | {result.successful_files} |
| Failed | {result.failed_files} |
| Total source | {result.total_source_chars:,} chars |
| Total logic | {result.total_logic_chars:,} chars |
| Avg compression | {result.avg_compression:.2f}x |
| **Avg similarity** | **{result.avg_similarity:.1f}%** |
| Avg structural | {result.avg_structural:.1f}% |

## Results by Language

| Language | Files | Similarity | Structural |
|----------|-------|------------|------------|
"""
        for lang, data in sorted(result.by_language.items()):
            report += f"| {lang} | {data['count']} | {data['similarity']:.1f}% | {data['structural']:.1f}% |\n"

        report += """
## File Details

| File | Language | Similarity | Structural | Compression |
|------|----------|------------|------------|-------------|
"""
        for f in sorted(result.files, key=lambda x: -x.similarity):
            status = "✓" if f.success else "✗"
            report += f"| {status} {Path(f.file_path).name} | {f.language} | {f.similarity:.1f}% | {f.structural:.1f}% | {f.compression:.2f}x |\n"

        (output_dir / "PROJECT_REPORT.md").write_text(report)
        print(f"\nReport saved to: {output_dir}/PROJECT_REPORT.md")


def reproduce_project(
    project_path: str,
    output_dir: str = None,
    target_lang: str = None,
    parallel: bool = False,
    use_llm: bool = True,
) -> ProjectResult:
    """Convenience function for project reproduction.

    Args:
        project_path: Project root path
        output_dir: Output directory
        target_lang: Target language
        parallel: Use parallel processing

    Returns:
        ProjectResult
    """
    reproducer = ProjectReproducer(target_lang=target_lang, use_llm=use_llm)
    return reproducer.reproduce_project(project_path, output_dir, parallel)
