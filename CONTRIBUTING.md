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

## Licensing and Intellectual Property

### License

Kailash SDK is licensed under the Apache License, Version 2.0. By submitting a contribution, you agree that your contribution will be licensed under the same terms as the rest of the project. See the [LICENSE](LICENSE) file for details.

### Contributor License Agreement

By contributing to this repository, you represent that:

1. You have the right to submit the contribution under the project's license terms.
2. Your contribution is your original work, or you have the right to submit it.
3. You grant Terrene Foundation a perpetual, worldwide, non-exclusive, royalty-free license to use, reproduce, modify, and distribute your contribution as part of the project.

### Patent Notice

The Kailash SDK is the subject of patent applications owned by Terrene Foundation See the [PATENTS](PATENTS) file for details.

Under Apache License 2.0, Section 3, each Contributor grants a perpetual, worldwide, non-exclusive, no-charge, royalty-free, irrevocable patent license covering claims necessarily infringed by their Contribution(s) alone or by combination of their Contribution(s) with the Work. This grant applies to all users of the software, whether or not they are contributors.

**Defensive termination**: If you institute patent litigation alleging that the Work constitutes patent infringement, patent licenses granted to you under Section 3 for that Work terminate as of the date such litigation is filed.

### What This Means for You

- **Your code**: You retain copyright of your contributions.
- **License grant**: Your contributions are licensed under Apache License 2.0, the same terms as the rest of the project.
- **Patent grant**: Under Section 3, each Contributor (including you) grants a patent license scoped to claims necessarily infringed by their Contribution(s). All users receive the same grant.
- **No additional obligations**: Beyond the above, there are no further IP obligations for contributors.

## Code of Conduct

Be respectful and professional in all interactions. We strive to maintain a welcoming environment for all contributors.

## Questions?

Feel free to open an issue for questions or reach out to info@terrene.foundation
