# Kailash Python SDK - Development Makefile
# This Makefile provides convenient commands for development tasks

.PHONY: help install install-dev test test-unit test-integration test-all
.PHONY: format lint type-check quality security pre-commit clean docs
.PHONY: build publish pre-release examples studio-dev studio-build

# Default target
help:
	@echo "Kailash Python SDK - Development Commands"
	@echo ""
	@echo "Setup Commands:"
	@echo "  install         Install package in development mode"
	@echo "  install-dev     Install with all development dependencies"
	@echo "  install-hooks   Install pre-commit hooks"
	@echo ""
	@echo "Code Quality Commands:"
	@echo "  format          Format code with Black and isort"
	@echo "  lint            Run Ruff linter"
	@echo "  type-check      Run mypy type checking"
	@echo "  quality         Run all code quality checks"
	@echo "  security        Run security scans (Trivy + detect-secrets)"
	@echo "  pre-commit      Run all pre-commit hooks"
	@echo ""
	@echo "Testing Commands:"
	@echo "  test            Run all tests"
	@echo "  test-unit       Run unit tests only"
	@echo "  test-integration Run integration tests only"
	@echo "  test-examples   Test all examples"
	@echo "  test-fast       Run fast tests (unit + examples)"
	@echo ""
	@echo "Documentation Commands:"
	@echo "  docs            Build Sphinx documentation"
	@echo "  docs-serve      Build and serve docs locally"
	@echo ""
	@echo "Release Commands:"
	@echo "  build           Build distribution packages"
	@echo "  pre-release     Run full pre-release checks"
	@echo ""
	@echo "Utility Commands:"
	@echo "  clean           Clean build artifacts and cache"
	@echo "  update          Update dependencies and pre-commit hooks"
	@echo ""
	@echo "Workflow Studio Commands:"
	@echo "  studio-dev      Start Workflow Studio in development mode"
	@echo "  studio-build    Build Workflow Studio for production"

# Installation commands
install:
	uv sync

install-dev:
	uv sync
	uv add --dev pre-commit detect-secrets doc8

install-hooks:
	pre-commit install
	pre-commit install --hook-type pre-push
	@echo "Pre-commit hooks installed successfully"

# Code quality commands
format:
	@echo "Formatting code with Black..."
	black src/ tests/ examples/ docs/
	@echo "Sorting imports with isort..."
	isort src/ tests/ examples/ docs/

lint:
	@echo "Running Ruff linter..."
	ruff check src/ tests/ examples/ --fix

type-check:
	@echo "Running mypy type checking..."
	mypy src/ --ignore-missing-imports --no-strict-optional

quality: format lint type-check
	@echo "All code quality checks completed"

security:
	@echo "Running Trivy security scan..."
	trivy filesystem --security-checks vuln,secret,config --severity HIGH,CRITICAL --quiet .
	@echo "Running detect-secrets..."
	detect-secrets scan --baseline .secrets.baseline .

pre-commit:
	@echo "Running all pre-commit hooks..."
	pre-commit run --all-files

# Testing commands
test:
	@echo "Running all tests..."
	pytest tests/ -v --tb=short

test-unit:
	@echo "Running unit tests..."
	pytest tests/ -v --tb=short -m "not integration"

test-integration:
	@echo "Running integration tests..."
	pytest tests/integration/ -v --tb=short

test-examples:
	@echo "Testing all examples..."
	cd examples && python utils/test_runner.py

test-fast: test-unit test-examples
	@echo "Fast tests completed"

# Documentation commands
docs:
	@echo "Building Sphinx documentation..."
	cd docs && python build_docs.py

docs-serve: docs
	@echo "Serving documentation locally..."
	cd docs/_build/html && python -m http.server 8000

# Release commands
build:
	@echo "Building distribution packages..."
	uv build

pre-release: clean quality security test docs
	@echo "Pre-release checks completed successfully"
	@echo "Ready for release!"

# Utility commands
clean:
	@echo "Cleaning build artifacts..."
	rm -rf build/
	rm -rf dist/
	rm -rf src/*.egg-info/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	@echo "Clean completed"

update:
	@echo "Updating dependencies..."
	uv sync --upgrade
	@echo "Updating pre-commit hooks..."
	pre-commit autoupdate
	@echo "Update completed"

# Development workflow shortcuts
dev-setup: install-dev install-hooks
	@echo "Development environment setup completed"
	@echo "Run 'make pre-commit' to test your setup"

commit-ready: quality test-fast
	@echo "Code is ready for commit!"

push-ready: quality test security
	@echo "Code is ready for push!"

# CI simulation
ci: quality test security docs
	@echo "CI checks completed successfully"

# Workflow Studio commands
studio-dev:
	@echo "Starting Kailash Workflow Studio in development mode..."
	./scripts/start-studio.sh

studio-build:
	@echo "Building Workflow Studio for production..."
	cd studio && npm run build
