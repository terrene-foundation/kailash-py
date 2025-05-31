.. _contributing:

============
Contributing
============

We welcome contributions to the Kailash Python SDK! This guide will help you get started.

Getting Started
---------------

1. **Fork the Repository**

   Visit `GitHub <https://github.com/terrene-foundation/kailash-py>`_ and fork the repository.

2. **Clone Your Fork**

   .. code-block:: bash

      git clone https://github.com/YOUR_USERNAME/kailash-python-sdk.git
      cd kailash-python-sdk

3. **Set Up Development Environment**

   .. code-block:: bash

      # Install uv package manager
      curl -LsSf https://astral.sh/uv/install.sh | sh

      # Sync dependencies
      uv sync

      # Install pre-commit hooks
      pre-commit install

Development Workflow
--------------------

1. **Create a Feature Branch**

   .. code-block:: bash

      git checkout -b feature/your-feature-name

2. **Make Your Changes**

   - Write clean, documented code
   - Follow the existing code style
   - Add tests for new functionality
   - Update documentation as needed

3. **Run Tests**

   .. code-block:: bash

      uv run pytest
      uv run pytest --cov=kailash

4. **Check Code Quality**

   .. code-block:: bash

      # Run all pre-commit hooks
      pre-commit run --all-files

      # Or run individually
      black src/ tests/
      isort src/ tests/
      ruff check src/ tests/

5. **Commit Your Changes**

   .. code-block:: bash

      git add .
      git commit -m "feat: add new feature"

   Follow conventional commit format:
   - ``feat:`` for new features
   - ``fix:`` for bug fixes
   - ``docs:`` for documentation
   - ``test:`` for tests
   - ``refactor:`` for refactoring

6. **Push and Create Pull Request**

   .. code-block:: bash

      git push origin feature/your-feature-name

   Then create a pull request on GitHub.

Code Style Guidelines
---------------------

- **Python Style**: Follow PEP 8
- **Line Length**: 88 characters (Black default)
- **Imports**: Use isort for organizing
- **Type Hints**: Always use type annotations
- **Docstrings**: Use Google style docstrings

Testing Guidelines
------------------

- Write tests for all new functionality
- Maintain test coverage above 80%
- Use pytest for all tests
- Mock external dependencies
- Test both success and error cases

Documentation
-------------

- Update docstrings for new/modified code
- Update API documentation if needed
- Add examples for new features
- Update README if necessary

Pull Request Process
--------------------

1. Ensure all tests pass
2. Update documentation
3. Add entry to CHANGELOG.md
4. Request review from maintainers
5. Address review feedback
6. Squash commits if requested

Community Guidelines
--------------------

- Be respectful and inclusive
- Follow the `Code of Conduct <https://github.com/terrene-foundation/kailash-py/blob/main/CODE_OF_CONDUCT.md>`_
- Help others in issues and discussions
- Share your use cases and feedback

Getting Help
------------

- **Questions**: Open a GitHub issue
- **Discussions**: Use GitHub Discussions
- **Security**: Email security@terrene.foundation

Thank you for contributing to Kailash Python SDK!