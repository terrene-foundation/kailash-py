# ADR-0003: Using the src Layout for Package Structure

## Status

Accepted

Date: 2025-05-16

## Context

When organizing a Python package, there are multiple conventions for structuring the code. The two main approaches are:

1. **Flat layout**: Where the package code sits directly in the project root
   ```
   kailash_python_sdk/
   ├── __init__.py
   ├── nodes/
   └── ...
   ```

2. **src layout**: Where the package code sits inside a `src` directory
   ```
   kailash_python_sdk/
   ├── src/
   │   └── kailash/
   │       ├── __init__.py
   │       ├── nodes/
   │       └── ...
   └── ...
   ```

We need to decide which structure to use for our package.

## Decision

We will use the src layout for the Kailash Python SDK, with the package name being `kailash` inside the `src` directory of the `kailash_python_sdk` repository.

## Rationale

The src layout offers several significant advantages:

1. **Enforced installation testing**: The src layout forces developers to install the package in development mode to test it, which more closely mimics how end users will use the package.

2. **Import clarity**: It prevents accidental relative imports from your project root, which can mask import problems that would occur in a real installation.

3. **Development/Production parity**: The development environment better matches how users will import your package.

4. **Namespace separation**: There's a clear distinction between the project name (`kailash_python_sdk`) and the package name (`kailash`).

5. **Modern best practice**: This approach is increasingly recommended by the Python packaging community, including in the Python Packaging Authority (PyPA) documentation.

6. **Testing isolation**: It makes it easier to test the package in isolation, without interference from development files.

## Consequences

### Positive

- Better separation between development artifacts and the actual package
- Improved testing discipline by requiring installation
- Clear distinction between the repository name and the importable package name
- More consistent import paths that match production usage

### Negative

- Slightly more complex directory structure
- Requires specific configuration in `pyproject.toml` or `setup.py`
- May require education for team members unfamiliar with the src layout

## Implementation Notes

1. The package will be structured as follows:
   ```
   kailash_python_sdk/
   ├── src/
   │   └── kailash/
   │       ├── __init__.py
   │       ├── nodes/
   │       └── ...
   ├── tests/
   └── ...
   ```

2. The `pyproject.toml` file will include:
   ```toml
   [tool.setuptools]
   package-dir = {"" = "src"}
   ```

3. All imports in the codebase and examples will use the `kailash` package name:
   ```python
   from kailash.nodes import Node
   from kailash.workflow import Workflow
   ```

4. Developers will be instructed to install the package in development mode:
   ```
   pip install -e .
   ```

## Related ADRs

- None

## References

- [PyPA Packaging Guide](https://packaging.python.org/en/latest/tutorials/packaging-projects/)
- [Pytest good practices](https://docs.pytest.org/en/latest/explanation/goodpractices.html)
- [Hypermodern Python article](https://cjolowicz.github.io/posts/hypermodern-python-01-setup/)
