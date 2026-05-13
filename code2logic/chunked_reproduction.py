"""
Chunked Reproduction for Smaller LLMs.

Automatically chunks large specifications for models with limited context.
Adapts chunk size based on LLM capabilities.

Features:
- Auto-detect LLM context limits
- Intelligent function/class grouping
- Merge reproduced chunks
- Token budget management
"""

import re
from dataclasses import dataclass
from typing import List, Optional

from .utils import estimate_tokens

# LLM context limits (approximate)
LLM_CONTEXT_LIMITS = {
    "gpt-4": 8000,
    "gpt-4-turbo": 128000,
    "gpt-3.5-turbo": 4000,
    "claude-3": 100000,
    "claude-2": 100000,
    "llama-7b": 2000,
    "llama-13b": 4000,
    "llama-70b": 4000,
    "mistral-7b": 8000,
    "mixtral-8x7b": 32000,
    "codellama": 4000,
    "deepseek-coder": 16000,
    "default": 4000,
}


@dataclass
class Chunk:
    """A chunk of specification for reproduction."""

    id: int
    content: str
    tokens: int
    elements: List[str]  # Function/class names
    dependencies: List[str]  # Required imports/references


@dataclass
class ChunkedSpec:
    """Chunked specification."""

    chunks: List[Chunk]
    total_tokens: int
    format: str
    file_name: str


@dataclass
class ChunkedResult:
    """Result of chunked reproduction."""

    file_name: str
    chunks_total: int
    chunks_success: int
    merged_code: str
    chunk_codes: List[str]
    errors: List[str]


def get_llm_limit(model_name: str) -> int:
    """Get context limit for LLM model."""
    model_lower = model_name.lower()

    for key, limit in LLM_CONTEXT_LIMITS.items():
        if key in model_lower:
            return limit

    return LLM_CONTEXT_LIMITS["default"]


def chunk_yaml_spec(spec: str, max_tokens: int = 2000) -> List[Chunk]:
    """Chunk YAML specification by modules/classes/functions."""
    chunks = []
    current_chunk = []
    current_tokens = 0
    current_elements = []
    chunk_id = 0

    # Split by top-level items
    lines = spec.split("\n")
    current_section = []

    for line in lines:
        # Detect new top-level item
        if line and not line.startswith(" ") and not line.startswith("#"):
            # Save previous section
            if current_section:
                section_text = "\n".join(current_section)
                section_tokens = estimate_tokens(section_text)

                if current_tokens + section_tokens > max_tokens and current_chunk:
                    # Start new chunk
                    chunks.append(
                        Chunk(
                            id=chunk_id,
                            content="\n".join(current_chunk),
                            tokens=current_tokens,
                            elements=current_elements.copy(),
                            dependencies=[],
                        )
                    )
                    chunk_id += 1
                    current_chunk = []
                    current_tokens = 0
                    current_elements = []

                current_chunk.extend(current_section)
                current_tokens += section_tokens

                # Extract element name
                if ":" in line:
                    elem = line.split(":")[0].strip()
                    if elem and not elem.startswith("-"):
                        current_elements.append(elem)

            current_section = [line]
        else:
            current_section.append(line)

    # Add remaining section
    if current_section:
        current_chunk.extend(current_section)
        current_tokens += estimate_tokens("\n".join(current_section))

    # Add final chunk
    if current_chunk:
        chunks.append(
            Chunk(
                id=chunk_id,
                content="\n".join(current_chunk),
                tokens=current_tokens,
                elements=current_elements,
                dependencies=[],
            )
        )

    return chunks


def chunk_gherkin_spec(spec: str, max_tokens: int = 2000) -> List[Chunk]:
    """Chunk Gherkin specification by Features/Scenarios."""
    chunks = []
    chunk_id = 0

    # Split by Feature
    features = re.split(r"(?=Feature:)", spec)

    current_chunk = []
    current_tokens = 0
    current_elements = []

    for feature in features:
        if not feature.strip():
            continue

        feature_tokens = estimate_tokens(feature)

        if feature_tokens > max_tokens:
            # Split feature by scenarios
            scenarios = re.split(r"(?=\s+Scenario)", feature)
            header = scenarios[0] if scenarios else ""

            for scenario in scenarios[1:]:
                scenario_full = header + scenario
                scenario_tokens = estimate_tokens(scenario_full)

                if current_tokens + scenario_tokens > max_tokens and current_chunk:
                    chunks.append(
                        Chunk(
                            id=chunk_id,
                            content="\n".join(current_chunk),
                            tokens=current_tokens,
                            elements=current_elements.copy(),
                            dependencies=[],
                        )
                    )
                    chunk_id += 1
                    current_chunk = []
                    current_tokens = 0
                    current_elements = []

                current_chunk.append(scenario_full)
                current_tokens += scenario_tokens

                # Extract scenario name
                match = re.search(r"Scenario[:\s]+(\w+)", scenario)
                if match:
                    current_elements.append(match.group(1))
        else:
            if current_tokens + feature_tokens > max_tokens and current_chunk:
                chunks.append(
                    Chunk(
                        id=chunk_id,
                        content="\n".join(current_chunk),
                        tokens=current_tokens,
                        elements=current_elements.copy(),
                        dependencies=[],
                    )
                )
                chunk_id += 1
                current_chunk = []
                current_tokens = 0
                current_elements = []

            current_chunk.append(feature)
            current_tokens += feature_tokens

            # Extract feature name
            match = re.search(r"Feature:\s*(.+)", feature)
            if match:
                current_elements.append(match.group(1).split()[0])

    if current_chunk:
        chunks.append(
            Chunk(
                id=chunk_id,
                content="\n".join(current_chunk),
                tokens=current_tokens,
                elements=current_elements,
                dependencies=[],
            )
        )

    return chunks


def chunk_markdown_spec(spec: str, max_tokens: int = 2000) -> List[Chunk]:
    """Chunk Markdown specification by sections."""
    chunks = []
    chunk_id = 0

    # Split by ## headers
    sections = re.split(r"(?=##\s)", spec)

    current_chunk = []
    current_tokens = 0
    current_elements = []

    for section in sections:
        if not section.strip():
            continue

        section_tokens = estimate_tokens(section)

        if current_tokens + section_tokens > max_tokens and current_chunk:
            chunks.append(
                Chunk(
                    id=chunk_id,
                    content="\n".join(current_chunk),
                    tokens=current_tokens,
                    elements=current_elements.copy(),
                    dependencies=[],
                )
            )
            chunk_id += 1
            current_chunk = []
            current_tokens = 0
            current_elements = []

        current_chunk.append(section)
        current_tokens += section_tokens

        # Extract section name
        match = re.search(r"##\s+(.+)", section)
        if match:
            current_elements.append(match.group(1).strip())

    if current_chunk:
        chunks.append(
            Chunk(
                id=chunk_id,
                content="\n".join(current_chunk),
                tokens=current_tokens,
                elements=current_elements,
                dependencies=[],
            )
        )

    return chunks


def chunk_spec(spec: str, fmt: str, max_tokens: int = 2000) -> ChunkedSpec:
    """Chunk specification based on format."""
    if fmt == "yaml":
        chunks = chunk_yaml_spec(spec, max_tokens)
    elif fmt == "gherkin":
        chunks = chunk_gherkin_spec(spec, max_tokens)
    elif fmt == "markdown":
        chunks = chunk_markdown_spec(spec, max_tokens)
    else:
        # Simple chunking by lines
        chunks = chunk_yaml_spec(spec, max_tokens)

    total_tokens = sum(c.tokens for c in chunks)

    return ChunkedSpec(
        chunks=chunks,
        total_tokens=total_tokens,
        format=fmt,
        file_name="",
    )


def get_chunk_prompt(
    chunk: Chunk, fmt: str, file_name: str, chunk_num: int, total_chunks: int
) -> str:
    """Generate prompt for a single chunk."""

    context = f"Part {chunk_num + 1}/{total_chunks}" if total_chunks > 1 else ""

    prompt = f"""Generate Python code from this {fmt.upper()} specification.
{context}

{chunk.content}

Requirements:
- Generate complete Python code for the elements in this chunk
- Include necessary imports
- Use type hints
- Elements to implement: {", ".join(chunk.elements[:10])}

```python
"""
    return prompt


def merge_chunk_codes(codes: List[str], file_name: str) -> str:
    """Merge code from multiple chunks."""

    # Collect imports and code sections
    imports = set()
    code_sections = []

    for code in codes:
        lines = code.split("\n")
        current_section = []

        for line in lines:
            # Collect imports
            if line.startswith("import ") or line.startswith("from "):
                imports.add(line)
            elif line.strip() and not line.startswith("#"):
                current_section.append(line)

        if current_section:
            code_sections.append("\n".join(current_section))

    # Build merged code
    merged = f'"""{file_name}\nAuto-generated from chunked specification.\n"""\n\n'
    merged += "\n".join(sorted(imports)) + "\n\n"
    merged += "\n\n".join(code_sections)

    return merged


class ChunkedReproducer:
    """Reproduce code from chunked specifications."""

    def __init__(
        self, client, model_name: str = "default", max_tokens: Optional[int] = None
    ):
        self.client = client
        self.model_name = model_name
        if max_tokens is None:
            self.max_tokens = get_llm_limit(model_name) // 2  # Leave room for response
        else:
            self.max_tokens = int(max_tokens)

    def reproduce(self, spec: str, fmt: str, file_name: str) -> ChunkedResult:
        """Reproduce code from specification, chunking if needed."""

        spec_tokens = estimate_tokens(spec)

        # Check if chunking needed
        if spec_tokens <= self.max_tokens:
            # No chunking needed
            prompt = get_chunk_prompt(
                Chunk(0, spec, spec_tokens, [], []), fmt, file_name, 0, 1
            )

            try:
                response = self.client.generate(prompt, max_tokens=4000)
                code = self._extract_code(response)

                return ChunkedResult(
                    file_name=file_name,
                    chunks_total=1,
                    chunks_success=1,
                    merged_code=code,
                    chunk_codes=[code],
                    errors=[],
                )
            except Exception as e:
                return ChunkedResult(
                    file_name=file_name,
                    chunks_total=1,
                    chunks_success=0,
                    merged_code="",
                    chunk_codes=[],
                    errors=[str(e)],
                )

        # Chunk the spec
        chunked = chunk_spec(spec, fmt, self.max_tokens)

        chunk_codes = []
        errors = []

        for i, chunk in enumerate(chunked.chunks):
            prompt = get_chunk_prompt(chunk, fmt, file_name, i, len(chunked.chunks))

            try:
                response = self.client.generate(prompt, max_tokens=4000)
                code = self._extract_code(response)
                chunk_codes.append(code)
            except Exception as e:
                errors.append(f"Chunk {i}: {e}")

        # Merge chunks
        merged = merge_chunk_codes(chunk_codes, file_name) if chunk_codes else ""

        return ChunkedResult(
            file_name=file_name,
            chunks_total=len(chunked.chunks),
            chunks_success=len(chunk_codes),
            merged_code=merged,
            chunk_codes=chunk_codes,
            errors=errors,
        )

    def _extract_code(self, response: str) -> str:
        """Extract code from LLM response."""
        if "```" in response:
            match = re.search(r"```(?:python)?\n(.*?)```", response, re.DOTALL)
            if match:
                return match.group(1).strip()
        return response.strip()


def auto_chunk_reproduce(
    spec: str,
    fmt: str,
    file_name: str,
    client,
    model_name: str = "default",
) -> ChunkedResult:
    """Auto-chunking reproduction with LLM adaptation."""
    reproducer = ChunkedReproducer(client, model_name)
    return reproducer.reproduce(spec, fmt, file_name)


def adaptive_chunk_reproduce(
    spec: str,
    fmt: str,
    file_name: str,
    client,
    provider: str = "unknown",
    model: str = "unknown",
) -> ChunkedResult:
    """
    Adaptive chunking reproduction using LLM profile.

    Uses stored LLM profiles to optimize chunk sizes and format selection.

    Args:
        spec: Specification string
        fmt: Format of specification
        file_name: Target file name
        client: LLM client
        provider: LLM provider name
        model: LLM model name

    Returns:
        ChunkedResult with reproduction
    """
    from .llm_profiler import AdaptiveChunker, get_or_create_profile

    # Get or create profile for this model
    profile = get_or_create_profile(provider, model)
    chunker = AdaptiveChunker(profile)

    # Get optimal settings
    settings = chunker.get_optimal_settings()
    max_tokens = settings["max_chunk_tokens"]

    # Use adaptive reproducer
    reproducer = ChunkedReproducer(client, model, max_tokens=max_tokens)
    return reproducer.reproduce(spec, fmt, file_name)
