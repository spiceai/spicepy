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

# Format code with ruff
format:
	ruff format spicepy tests
	ruff check --fix spicepy tests

# Check formatting without making changes
format-check:
	ruff format --check spicepy tests

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