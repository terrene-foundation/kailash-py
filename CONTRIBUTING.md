# Contributing to Kailash Python SDK

We welcome contributions to the Kailash Python SDK! This document provides guidelines for contributing to the project.

## Getting Started

1. Fork the repository on GitHub
2. Clone your fork locally
3. Set up the development environment:
   ```bash
   pip install -e ".[dev]"
   ```
4. Create a new branch for your feature or bugfix

## Development Process

### Code Style

We use standard Python tools for code quality:
- `black` for code formatting
- `isort` for import sorting
- `mypy` for type checking

Before submitting, run:
```bash
black src/
isort src/
mypy src/
```

### Testing

All new features should include tests:
```bash
pytest
pytest --cov=kailash
```

### Architecture Decision Records (ADRs)

For significant architectural changes, please document them appropriately:
1. Describe the architectural change in your pull request
2. Explain the rationale and trade-offs
3. Update relevant documentation

## Pull Request Process

1. Update the README.md with details of interface changes
2. Ensure all tests pass
3. Update documentation as needed
4. Request review from maintainers

## Code of Conduct

Be respectful and professional in all interactions. We strive to maintain a welcoming environment for all contributors.

## Questions?

Feel free to open an issue for questions or reach out to info@terrene.foundation
