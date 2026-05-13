# Monorepo Workflow (Managing All Packages)

This repository contains multiple independently publishable Python packages:

- `code2logic` - core analyzer and format generator
- `lolm` - LLM provider management (shared by other packages)
- `logic2test` - test generation from Code2Logic output
- `logic2code` - code generation from Code2Logic output

You can work with each package independently (inside its folder), or manage everything from the repository root.

# Install all subpackages (dev)
make install-subpackages
```

# Test only subpackages
make test-subpackages
```

# Build all subpackages
make build-subpackages
```

# Publish single package
make publish                 # code2logic
make publish-lolm
make publish-logic2test
make publish-logic2code

# TestPyPI
make publish-test
make publish-all-test
```

### Versions

```bash
make version
make version-all
```

## Working With a Single Package

Each package contains its own `Makefile` and `pyproject.toml`.

Example:

```bash
cd lolm
make install-dev
make test
make build
make publish
```

## CI/CD (GitHub Actions)

Workflow file:

- `.github/workflows/packages.yml`

### What it does

- Runs tests for `lolm`, `logic2test`, `logic2code` on pushes/PRs (paths filtered)
- Publishes packages on GitHub Releases when the tag matches the package prefix

### Release tag conventions

- `lolm-vX.Y.Z` publishes `lolm`
- `logic2test-vX.Y.Z` publishes `logic2test`
- `logic2code-vX.Y.Z` publishes `logic2code`

### Required secrets

Set these repository secrets:

- `PYPI_API_TOKEN_LOLM`
- `PYPI_API_TOKEN_LOGIC2TEST`
- `PYPI_API_TOKEN_LOGIC2CODE`

## Dependency Notes

- `logic2code` depends on `logic2test` (shared parsers)
- LLM support in `logic2code` uses `lolm` (optional dependency)

# 1. Analyze source project into a logic file
code2logic src/ -f hybrid -o out/code2logic/project.c2l.hybrid.yaml

# 2. Generate tests
python -m logic2test out/code2logic/project.c2l.hybrid.yaml -o out/logic2test/tests/ --type all

# 3. Generate code scaffolds (or regenerate)
python -m logic2code out/code2logic/project.c2l.hybrid.yaml -o out/logic2code/generated_code/

