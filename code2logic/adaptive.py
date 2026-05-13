"""
Adaptive Format System for LLM-based Code Reproduction.

Automatically selects the optimal format and chunking strategy based on:
- LLM model capabilities (context size, code generation quality)
- Source file size and complexity
- Target compression ratio

Usage:
    from code2logic.adaptive import AdaptiveReproducer

    reproducer = AdaptiveReproducer()
    result = reproducer.reproduce("path/to/file.py")
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

# Load .env file
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from .file_formats import generate_file_csv, generate_file_json, generate_file_yaml
from .llm_clients import BaseLLMClient, get_client
from .reproduction import compare_code, extract_code_block, generate_file_gherkin

# LLM Model capabilities database
LLM_CAPABILITIES = {
    # OpenRouter models
    "qwen/qwen-2.5-coder-32b-instruct": {
        "context_size": 32000,
        "code_quality": 0.9,
        "best_formats": ["gherkin", "yaml", "json"],
        "max_output": 8000,
        "supports_chunking": True,
    },
    "nvidia/nemotron-3-nano-30b-a3b:free": {
        "context_size": 8000,
        "code_quality": 0.7,
        "best_formats": ["gherkin", "yaml"],
        "max_output": 4000,
        "supports_chunking": True,
    },
    "meta-llama/llama-3.3-70b-instruct:free": {
        "context_size": 16000,
        "code_quality": 0.8,
        "best_formats": ["gherkin", "yaml", "json"],
        "max_output": 4000,
        "supports_chunking": True,
    },
    "deepseek/deepseek-coder-33b-instruct": {
        "context_size": 16000,
        "code_quality": 0.85,
        "best_formats": ["gherkin", "json", "yaml"],
        "max_output": 8000,
        "supports_chunking": True,
    },
    # Ollama models
    "qwen2.5-coder:14b": {
        "context_size": 8000,
        "code_quality": 0.8,
        "best_formats": ["gherkin", "yaml"],
        "max_output": 4000,
        "supports_chunking": True,
    },
    "qwen2.5-coder:7b": {
        "context_size": 4000,
        "code_quality": 0.7,
        "best_formats": ["gherkin"],
        "max_output": 2000,
        "supports_chunking": True,
    },
    "codellama:7b-instruct": {
        "context_size": 4000,
        "code_quality": 0.65,
        "best_formats": ["gherkin", "csv"],
        "max_output": 2000,
        "supports_chunking": True,
    },
    # Default for unknown models
    "default": {
        "context_size": 4000,
        "code_quality": 0.6,
        "best_formats": ["gherkin"],
        "max_output": 2000,
        "supports_chunking": True,
    },
}


@dataclass
class ChunkInfo:
    """Information about a code chunk."""

    index: int
    total: int
    content: str
    element_type: str  # 'class', 'function', 'imports', etc.
    element_name: str


@dataclass
class AdaptiveResult:
    """Result of adaptive reproduction."""

    source_file: str
    source_chars: int
    format_used: str
    chunks_used: int
    spec_chars: int
    generated_chars: int
    similarity: float
    structural_score: float
    compression_ratio: float
    efficiency_score: float


class AdaptiveReproducer:
    """Adaptive code reproduction with LLM capability detection."""

    def __init__(self, client: BaseLLMClient = None, model: str = None):
        """Initialize adaptive reproducer.

        Args:
            client: LLM client (default: auto-detect)
            model: Model name for capability lookup
        """
        self.client = client or get_client()
        self.model = model or getattr(self.client, "model", "default")
        self.capabilities = self._get_capabilities()

    def _get_capabilities(self) -> Dict[str, Any]:
        """Get LLM capabilities for current model."""
        # Try exact match first
        if self.model in LLM_CAPABILITIES:
            return LLM_CAPABILITIES[self.model]

        # Try partial match
        for model_name, caps in LLM_CAPABILITIES.items():
            if model_name in self.model or self.model in model_name:
                return caps

        return LLM_CAPABILITIES["default"]

    def select_format(self, file_path: Path, content: str) -> str:
        """Select optimal format based on file and LLM capabilities.

        Args:
            file_path: Source file path
            content: File content

        Returns:
            Best format name
        """
        best_formats = self.capabilities["best_formats"]

        # Analyze file characteristics
        is_dataclass = "@dataclass" in content
        has_classes = "class " in content
        has_functions = "def " in content or "function " in content
        is_sql = file_path.suffix == ".sql"

        # Select format based on content type
        if is_sql:
            return "yaml" if "yaml" in best_formats else best_formats[0]

        if is_dataclass:
            # YAML is best for dataclasses
            if "yaml" in best_formats:
                return "yaml"
            return best_formats[0]

        if has_functions and not has_classes:
            # Gherkin is best for function-heavy code
            return "gherkin" if "gherkin" in best_formats else best_formats[0]

        # Default to first best format
        return best_formats[0]

    def should_chunk(self, content: str) -> bool:
        """Determine if content should be chunked.

        Args:
            content: Source content

        Returns:
            True if chunking is needed
        """
        if not self.capabilities["supports_chunking"]:
            return False

        # Estimate tokens (rough: 4 chars per token)
        estimated_tokens = len(content) // 4
        max_context = self.capabilities["context_size"]

        # Leave room for prompt and output
        usable_context = max_context * 0.4

        return estimated_tokens > usable_context

    def chunk_content(self, content: str, file_path: Path) -> List[ChunkInfo]:
        """Split content into logical chunks.

        Args:
            content: Source content
            file_path: Source file path

        Returns:
            List of chunk info objects
        """
        chunks = []
        lines = content.split("\n")

        # Extract imports
        import_lines = []
        current_chunk = []
        current_type = "imports"
        current_name = "imports"
        chunk_index = 0

        in_class = False
        class_name = ""

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Imports
            if stripped.startswith("import ") or stripped.startswith("from "):
                import_lines.append(line)
                continue

            # Class start
            if stripped.startswith("class "):
                if current_chunk:
                    chunks.append(
                        ChunkInfo(
                            index=chunk_index,
                            total=0,  # Will update later
                            content="\n".join(current_chunk),
                            element_type=current_type,
                            element_name=current_name,
                        )
                    )
                    chunk_index += 1
                    current_chunk = []

                class_name = stripped.split("(")[0].split(":")[0].replace("class ", "")
                in_class = True
                current_type = "class"
                current_name = class_name
                current_chunk = [line]
                continue

            # Function outside class
            if stripped.startswith("def ") and not in_class:
                if current_chunk and current_type != "function":
                    chunks.append(
                        ChunkInfo(
                            index=chunk_index,
                            total=0,
                            content="\n".join(current_chunk),
                            element_type=current_type,
                            element_name=current_name,
                        )
                    )
                    chunk_index += 1
                    current_chunk = []

                func_name = stripped.split("(")[0].replace("def ", "")
                current_type = "function"
                current_name = func_name

            current_chunk.append(line)

            # Check if class ends (next line has no indent and is not empty)
            if in_class and i + 1 < len(lines):
                next_line = lines[i + 1]
                if (
                    next_line
                    and not next_line[0].isspace()
                    and not next_line.strip().startswith("#")
                ):
                    if not next_line.strip().startswith(
                        "class "
                    ) and not next_line.strip().startswith("def "):
                        in_class = False
                        chunks.append(
                            ChunkInfo(
                                index=chunk_index,
                                total=0,
                                content="\n".join(current_chunk),
                                element_type=current_type,
                                element_name=current_name,
                            )
                        )
                        chunk_index += 1
                        current_chunk = []
                        current_type = "other"
                        current_name = ""

        # Add remaining content
        if current_chunk:
            chunks.append(
                ChunkInfo(
                    index=chunk_index,
                    total=0,
                    content="\n".join(current_chunk),
                    element_type=current_type,
                    element_name=current_name,
                )
            )

        # Add imports as first chunk if present
        if import_lines:
            chunks.insert(
                0,
                ChunkInfo(
                    index=0,
                    total=0,
                    content="\n".join(import_lines),
                    element_type="imports",
                    element_name="imports",
                ),
            )
            # Reindex
            for i, chunk in enumerate(chunks):
                chunk.index = i

        # Update total count
        total = len(chunks)
        for chunk in chunks:
            chunk.total = total

        return chunks

    def generate_chunk_spec(self, chunk: ChunkInfo, format_name: str) -> str:
        """Generate specification for a single chunk.

        Args:
            chunk: Chunk info
            format_name: Format to use

        Returns:
            Specification string
        """
        # Create temporary file-like content
        content = chunk.content

        if format_name == "gherkin":
            return self._gherkin_for_chunk(chunk)
        elif format_name == "yaml":
            return self._yaml_for_chunk(chunk)
        elif format_name == "json":
            return self._json_for_chunk(chunk)
        else:
            return content

    def _gherkin_for_chunk(self, chunk: ChunkInfo) -> str:
        """Generate Gherkin for a chunk."""
        lines = [
            f"# Chunk {chunk.index + 1}/{chunk.total}: {chunk.element_type}",
            f"@{chunk.element_name}",
            f"Feature: {chunk.element_name}",
            "",
        ]

        if chunk.element_type == "imports":
            lines.append("  Scenario: Required imports")
            lines.append("    Given the following imports:")
            for imp in chunk.content.split("\n"):
                if imp.strip():
                    lines.append(f"      | {imp.strip()} |")

        elif chunk.element_type == "class":
            lines.append(f"  Scenario: Define {chunk.element_name} class")
            lines.append(f'    Given a class named "{chunk.element_name}"')

            # Extract attributes and methods from content
            for line in chunk.content.split("\n"):
                stripped = line.strip()
                if stripped.startswith("def "):
                    method_name = stripped.split("(")[0].replace("def ", "")
                    lines.append(f'    And method "{method_name}"')

        elif chunk.element_type == "function":
            lines.append(f"  Scenario: Define {chunk.element_name} function")
            lines.append(f'    Given a function named "{chunk.element_name}"')

        return "\n".join(lines)

    def _yaml_for_chunk(self, chunk: ChunkInfo) -> str:
        """Generate YAML for a chunk."""
        lines = [
            f"# Chunk {chunk.index + 1}/{chunk.total}",
            f"type: {chunk.element_type}",
            f"name: {chunk.element_name}",
            "content:",
        ]

        for line in chunk.content.split("\n"):
            lines.append(f'  - "{line}"')

        return "\n".join(lines)

    def _json_for_chunk(self, chunk: ChunkInfo) -> str:
        """Generate JSON for a chunk."""
        import json

        return json.dumps(
            {
                "chunk": chunk.index + 1,
                "total": chunk.total,
                "type": chunk.element_type,
                "name": chunk.element_name,
                "content": chunk.content,
            },
            indent=2,
        )

    def reproduce(self, file_path: str, output_dir: str = None) -> AdaptiveResult:
        """Reproduce code with adaptive format selection.

        Args:
            file_path: Source file path
            output_dir: Optional output directory

        Returns:
            AdaptiveResult with metrics
        """
        path = Path(file_path)
        content = path.read_text()

        # Select optimal format
        format_name = self.select_format(path, content)

        # Determine if chunking is needed
        use_chunking = self.should_chunk(content)

        if use_chunking:
            return self._reproduce_chunked(path, content, format_name, output_dir)
        else:
            return self._reproduce_single(path, content, format_name, output_dir)

    def _reproduce_single(
        self, path: Path, content: str, format_name: str, output_dir: str = None
    ) -> AdaptiveResult:
        """Reproduce without chunking."""
        # Generate spec
        if format_name == "gherkin":
            spec = generate_file_gherkin(path)
        elif format_name == "yaml":
            spec = generate_file_yaml(path)
        elif format_name == "json":
            spec = generate_file_json(path)
        elif format_name == "csv":
            spec = generate_file_csv(path)
        else:
            spec = generate_file_gherkin(path)

        spec_chars = len(spec)

        # Generate code
        generated = self._generate_from_spec(spec, format_name, path.suffix)
        generated_chars = len(generated)

        # Compare
        comparison = compare_code(content, generated)

        # Calculate efficiency
        compression_ratio = spec_chars / max(generated_chars, 1)
        efficiency = (comparison["similarity_percent"] / 100) / max(
            compression_ratio, 0.1
        )

        result = AdaptiveResult(
            source_file=str(path),
            source_chars=len(content),
            format_used=format_name,
            chunks_used=1,
            spec_chars=spec_chars,
            generated_chars=generated_chars,
            similarity=comparison["similarity_percent"],
            structural_score=comparison["structural_score"],
            compression_ratio=compression_ratio,
            efficiency_score=efficiency,
        )

        # Save if output_dir provided
        if output_dir:
            self._save_result(Path(output_dir), content, spec, generated, result)

        return result

    def _reproduce_chunked(
        self, path: Path, content: str, format_name: str, output_dir: str = None
    ) -> AdaptiveResult:
        """Reproduce with chunking."""
        chunks = self.chunk_content(content, path)

        generated_parts = []
        total_spec_chars = 0

        for chunk in chunks:
            spec = self.generate_chunk_spec(chunk, format_name)
            total_spec_chars += len(spec)

            generated = self._generate_from_spec(spec, format_name, path.suffix)
            generated_parts.append(generated)

        # Combine generated parts
        generated = "\n\n".join(generated_parts)
        generated_chars = len(generated)

        # Compare
        comparison = compare_code(content, generated)

        # Calculate efficiency
        compression_ratio = total_spec_chars / max(generated_chars, 1)
        efficiency = (comparison["similarity_percent"] / 100) / max(
            compression_ratio, 0.1
        )

        result = AdaptiveResult(
            source_file=str(path),
            source_chars=len(content),
            format_used=format_name,
            chunks_used=len(chunks),
            spec_chars=total_spec_chars,
            generated_chars=generated_chars,
            similarity=comparison["similarity_percent"],
            structural_score=comparison["structural_score"],
            compression_ratio=compression_ratio,
            efficiency_score=efficiency,
        )

        if output_dir:
            self._save_result(
                Path(output_dir),
                content,
                f"# Chunked spec ({len(chunks)} chunks)",
                generated,
                result,
            )

        return result

    def _generate_from_spec(self, spec: str, format_name: str, file_ext: str) -> str:
        """Generate code from specification."""
        # Determine target language
        lang_map = {
            ".py": "Python",
            ".js": "JavaScript",
            ".ts": "TypeScript",
            ".go": "Go",
            ".sql": "SQL",
            ".java": "Java",
            ".rs": "Rust",
        }
        target_lang = lang_map.get(file_ext, "Python")

        system = f"""You are an expert {target_lang} developer. Generate clean, production-ready code.
Rules:
1. Generate ONLY code, no explanations
2. Include all imports
3. Add docstrings
4. Include type hints where applicable
5. The code must be complete and runnable

Output: Return ONLY code wrapped in ```{target_lang.lower()} ... ``` blocks."""

        prompt = f"""Generate {target_lang} code from this {format_name} specification:

{spec}

Generate complete, working {target_lang} code."""

        response = self.client.generate(
            prompt, system=system, max_tokens=self.capabilities["max_output"]
        )
        return extract_code_block(response, target_lang.lower())

    def _save_result(
        self,
        output_dir: Path,
        original: str,
        spec: str,
        generated: str,
        result: AdaptiveResult,
    ):
        """Save reproduction results."""
        output_dir.mkdir(parents=True, exist_ok=True)

        (output_dir / "original.txt").write_text(original)
        (output_dir / "specification.txt").write_text(spec)
        (output_dir / "generated.txt").write_text(generated)

        # Report
        report = f"""# Adaptive Reproduction Report

## Configuration
- **Format:** {result.format_used}
- **Chunks:** {result.chunks_used}
- **Model:** {self.model}

## Metrics
| Metric | Value |
|--------|-------|
| Source chars | {result.source_chars} |
| Spec chars | {result.spec_chars} |
| Generated chars | {result.generated_chars} |
| Similarity | {result.similarity:.1f}% |
| Structural | {result.structural_score:.1f}% |
| Compression | {result.compression_ratio:.2f}x |
| Efficiency | {result.efficiency_score:.2f} |
"""
        (output_dir / "REPORT.md").write_text(report)


def get_llm_capabilities(model: str) -> Dict[str, Any]:
    """Get capabilities for a specific model.

    Args:
        model: Model name

    Returns:
        Capabilities dictionary
    """
    if model in LLM_CAPABILITIES:
        return LLM_CAPABILITIES[model]

    for model_name, caps in LLM_CAPABILITIES.items():
        if model_name in model or model in model_name:
            return caps

    return LLM_CAPABILITIES["default"]
