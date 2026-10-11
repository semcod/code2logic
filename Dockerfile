# Code2Logic Docker Image
# Multi-stage build for smaller image

FROM python:3.12-slim@sha256:05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f AS builder

WORKDIR /app

# Install build dependencies
RUN pip install --no-cache-dir build

# Copy source code
COPY pyproject.toml README.md LICENSE CHANGELOG.md ./
COPY code2logic/ ./code2logic/

# Build wheel
RUN python -m build --wheel

# ============================================================================
# Final image
# ============================================================================
FROM python:3.12-slim@sha256:05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f

LABEL maintainer="Softreck <info@softreck.dev>"
LABEL description="Code2Logic - Convert source code to logical representation for LLM analysis"
LABEL version="1.0.1"

WORKDIR /app

# Install the wheel with all dependencies
COPY --from=builder /app/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl[full] && \
    rm /tmp/*.whl

# Create volume mount points
VOLUME ["/project", "/output"]

# Default command
ENTRYPOINT ["code2logic"]
CMD ["--help"]

# Usage examples:
# docker build -t code2logic .
# docker run -v /path/to/project:/project -v /path/to/output:/output code2logic /project -f csv -o /output/analysis.csv
# docker run -v $(pwd):/project code2logic /project -f json --flat