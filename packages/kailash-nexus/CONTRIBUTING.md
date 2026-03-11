# Contributing to Kailash Nexus

Thank you for your interest in contributing to Kailash Nexus! This document provides guidelines and information for contributors.

## Code of Conduct

We are committed to providing a welcoming and inclusive environment. Please be respectful and constructive in all interactions.

## Getting Started

### Prerequisites

- Python 3.10+
- Git
- Docker (optional, for containerized testing)

### Development Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/terrene-foundation/kailash-nexus.git
   cd kailash-nexus
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -e ".[dev]"
   ```

4. Run tests to verify setup:
   ```bash
   pytest tests/ -v
   ```

## Development Workflow

### Branch Naming

- Feature branches: `feature/<description>`
- Bug fixes: `fix/<description>`
- Documentation: `docs/<description>`

### Commit Messages

Follow conventional commit format:
```
type(scope): description

[optional body]

[optional footer]
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

### Pull Request Process

1. Create a feature branch from `main`
2. Make your changes
3. Run tests and linting
4. Submit a pull request
5. Address review feedback
6. Merge after approval

## Testing Guidelines

### Running Tests

```bash
# Unit tests
pytest tests/ -v

# With coverage
pytest --cov=nexus tests/
```

## Code Style

### Python Style Guide

- Follow PEP 8
- Use type hints
- Maximum line length: 88 characters (Black default)
- Use descriptive variable names

### Linting

```bash
# Run ruff
ruff check .

# Format with black
black .
```

## Documentation

- Update docstrings for public APIs
- Add examples for new features
- Keep README up to date

## Reporting Issues

When reporting issues, please include:

1. Description of the issue
2. Steps to reproduce
3. Expected behavior
4. Actual behavior
5. Python version and OS
6. Relevant logs or error messages

## Feature Requests

For feature requests:

1. Check existing issues for duplicates
2. Describe the use case
3. Propose a solution if possible
4. Be open to discussion

## Questions

For questions about the codebase or architecture:

1. Check existing documentation
2. Search closed issues
3. Open a discussion or issue

## License

By contributing, you agree that your contributions will be licensed under the Apache License, Version 2.0.
