.PHONY: clean install install-dev test test-unit test-integration lint format type-check security-check coverage all check

# Default target
all: check test

# Clean build artifacts
clean:
	@rm -rf build dist spicepy.egg-info spicepy/__pycache__ tests/__pycache__ .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage

# Alias for clean
mrproper: clean

# Install package
install:
	pip install .

# Install with development dependencies
install-dev:
	pip install -e ".[test,params]"

# Run all tests
test:
	pytest -s

# Run only unit tests (no external services required)
test-unit:
	pytest -s -m "unit or not (integration or cloud or slow)"

# Run integration tests (requires local Spice runtime)
test-integration:
	pytest -s -m "integration"

# Run tests with coverage
coverage:
	pytest --cov=spicepy --cov-report=html --cov-report=term-missing --cov-fail-under=80

# Linting with ruff (fast) and pylint
lint:
	ruff check spicepy tests
	pylint spicepy tests --fail-under=8.0

# Apply ruff's lint fixes, then format with black
#
# black is the formatter of record: CI's formatting gate is `black --check`
# (.github/workflows/lint.yml). ruff format is deliberately NOT run here — the
# two disagree on constructs neither can be configured out of (`assert cond,
# msg` wrapping, for one), so running both means whichever went last "wins" and
# the other reports the file as unformatted. ruff still lints and auto-fixes;
# black runs after it so the result is what CI will check.
#
# `--fix-only` rather than `--fix`: `--fix` exits nonzero while any unfixable
# diagnostic remains, so make would stop there and never reach black, leaving a
# file with an ordinary lint finding unformatted by the target whose job is to
# format it. `make lint` is where unfixed findings get reported.
format:
	ruff check --fix-only spicepy tests
	black spicepy tests

# Check formatting without making changes
format-check:
	black --check spicepy tests

# Type checking with mypy
type-check:
	mypy spicepy --ignore-missing-imports

# Security scanning with bandit
security-check:
	bandit -r spicepy -c pyproject.toml

# Run all checks (lint, format-check, type-check, security-check)
check: format-check lint type-check security-check

# CI target: run all checks and tests with coverage
ci: check coverage

# Apple Silicon specific setup
.PHONY: apple-silicon-requirements
apple-silicon-requirements:
	conda install pyarrow=12 pandas