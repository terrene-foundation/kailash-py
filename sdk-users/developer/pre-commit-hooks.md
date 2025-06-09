# Pre-commit Hooks Setup and Usage

This document provides comprehensive instructions for setting up and using pre-commit hooks in the Kailash Python SDK project.

## Overview

Pre-commit hooks are automated checks that run before each commit to ensure code quality, consistency, and security. Our configuration includes:

- **Code Formatting**: Black and isort
- **Linting**: Ruff for Python code analysis
- **Testing**: Pytest for unit tests
- **Security**: Trivy for vulnerability scanning and detect-secrets for secret detection
- **Documentation**: doc8 for documentation linting
- **Type Checking**: mypy for static type analysis

## Quick Setup

### 1. Install Dependencies

```bash
# Install pre-commit and related tools
uv add --dev pre-commit detect-secrets doc8

# Install Trivy (macOS with Homebrew)
brew install trivy

# For other systems, see: https://aquasecurity.github.io/trivy/latest/getting-started/installation/
```

### 2. Install Pre-commit Hooks

```bash
# Install git hooks
pre-commit install

# Install pre-push hooks (optional)
pre-commit install --hook-type pre-push

# Migrate deprecated configuration (if prompted)
pre-commit migrate-config
```

### 3. Test Installation

```bash
# Run all hooks on all files (initial setup)
pre-commit run --all-files

# Run specific hooks for testing
pre-commit run black --all-files
pre-commit run ruff --all-files
```

## Hook Configuration

Our `.pre-commit-config.yaml` includes the following hooks:

### Code Quality Hooks

1. **Black** (Code Formatter)
   - Formats Python code with consistent style
   - Line length: 88 characters
   - Runs on: Python files

2. **isort** (Import Sorter)
   - Sorts and organizes imports
   - Profile: black (for compatibility)
   - Runs on: Python files

3. **Ruff** (Linter)
   - Fast Python linter replacing flake8, pylint
   - Auto-fixes issues when possible
   - Runs on: Python files

### Built-in Quality Checks

- Trailing whitespace removal
- End-of-file fixing
- YAML/TOML/JSON syntax validation
- MergeNode conflict detection
- Large file detection (>1MB)
- Debug statement detection

### Security Hooks

1. **Trivy** (Vulnerability Scanner)
   - Scans for security vulnerabilities
   - Checks: vulnerabilities, secrets, configuration issues
   - Severity: HIGH and CRITICAL only
   - Runs on: Entire filesystem

2. **detect-secrets** (Secret Detection)
   - Detects potential secrets in code
   - Uses baseline file: `.secrets.baseline`
   - Excludes: test files, lock files

### Testing Hooks

1. **pytest** (Unit Tests)
   - Runs unit tests before commit
   - Configuration: Stop on first failure, quiet output
   - Maximum 5 failures shown
   - Excludes: Integration tests (too slow for pre-commit)

### Documentation Hooks

1. **doc8** (Documentation Linter)
   - Checks documentation style
   - Max line length: 88 characters
   - Runs on: .rst and .md files

2. **mypy** (Type Checking)
   - Static type analysis
   - Ignores missing imports
   - Excludes: tests/, examples/, docs/

## Usage Examples

### Everyday Development

```bash
# Normal commit (hooks run automatically)
git add .
git commit -m "Add new feature"

# Skip hooks in emergency (not recommended)
git commit -m "Emergency fix" --no-verify

# Run specific hook manually
pre-commit run black
pre-commit run pytest-check

# Run all hooks manually
pre-commit run --all-files
```

### Fixing Hook Failures

```bash
# If Black or isort fail:
# 1. The hooks auto-fix files
# 2. Review changes: git diff
# 3. Add fixed files: git add .
# 4. Commit again: git commit -m "Your message"

# If Ruff fails:
# 1. Review linting errors in output
# 2. Fix issues manually or run: ruff --fix .
# 3. Add fixed files and commit

# If pytest fails:
# 1. Fix failing tests
# 2. Run tests manually: pytest tests/
# 3. Commit when tests pass

# If Trivy fails:
# 1. Review security vulnerabilities
# 2. Update dependencies: uv sync --upgrade
# 3. Fix configuration issues
# 4. Commit when clean

# If detect-secrets fails:
# 1. Review detected secrets
# 2. Remove or mask actual secrets
# 3. Update baseline if false positive:
#    detect-secrets scan . > .secrets.baseline
```

### Skipping Specific Hooks

```bash
# Skip specific hooks for one commit
SKIP=trivy-fs,pytest-check git commit -m "Skip slow hooks"

# Skip all hooks (emergency only)
git commit -m "Emergency" --no-verify

# Skip hooks in environment variable
export SKIP=mypy,trivy-fs
git commit -m "Skip type checking and security"
unset SKIP
```

### Managing the Secrets Baseline

```bash
# Update secrets baseline (when you have new legitimate secrets)
detect-secrets scan . > .secrets.baseline

# Audit secrets baseline
detect-secrets audit .secrets.baseline

# Check for new secrets
detect-secrets scan .
```

## Troubleshooting

### Common Issues

1. **"trivy not found"**
   ```bash
   # Install Trivy
   brew install trivy  # macOS
   # or follow https://aquasecurity.github.io/trivy/latest/getting-started/installation/
   ```

2. **"No module named 'pip'"**
   ```bash
   # Use uv instead
   uv add --dev pre-commit
   ```

3. **Hooks are slow**
   ```bash
   # Skip slow hooks for rapid development
   SKIP=pytest-check,trivy-fs git commit -m "Quick fix"
   ```

4. **False positive secrets**
   ```bash
   # Update baseline to include false positives
   detect-secrets scan . > .secrets.baseline
   git add .secrets.baseline
   ```

5. **Import order conflicts (isort vs Black)**
   ```bash
   # Run isort with Black profile (already configured)
   isort --profile black .
   ```

### Performance Optimization

```bash
# Run only fast hooks during development
export SKIP=pytest-check,trivy-fs,mypy

# Run full checks before pushing
pre-commit run --all-files --hook-stage pre-push

# Update hook versions for performance improvements
pre-commit autoupdate
```

## Integration with CI/CD

Our pre-commit configuration includes CI settings:

- **pre-commit.ci**: Automatic updates and fixes
- **Skip in CI**: Resource-intensive hooks (pytest, trivy) are skipped in pre-commit.ci
- **Full CI**: GitHub Actions runs complete test suite including skipped hooks

## Customization

### Adding New Hooks

Edit `.pre-commit-config.yaml`:

```yaml
- repo: https://github.com/example/new-hook
  rev: v1.0.0
  hooks:
    - id: new-hook-id
      name: New Hook Description
      args: [--option, value]
```

### Excluding Files

```yaml
- id: hook-name
  exclude: ^(tests/|docs/|\.lock$)
```

### Project-specific Hooks

```yaml
- repo: local
  hooks:
    - id: custom-check
      name: Custom Project Check
      entry: ./scripts/custom-check.sh
      language: system
      pass_filenames: false
```

## Best Practices

1. **Run hooks regularly**: `pre-commit run --all-files`
2. **Update hooks monthly**: `pre-commit autoupdate`
3. **Fix issues promptly**: Don't accumulate hook failures
4. **Use meaningful commits**: Let hooks fix formatting, focus on logic
5. **Test locally**: Run full test suite before pushing
6. **Review auto-fixes**: Always review changes made by formatting hooks
7. **Keep baseline updated**: Update `.secrets.baseline` when needed
8. **Document exceptions**: If you must skip hooks, document why

## Additional Resources

- [Pre-commit Documentation](https://pre-commit.com/)
- [Black Documentation](https://black.readthedocs.io/)
- [Ruff Documentation](https://docs.astral.sh/ruff/)
- [Trivy Documentation](https://aquasecurity.github.io/trivy/)
- [detect-secrets Documentation](https://github.com/Yelp/detect-secrets)

## Support

If you encounter issues with pre-commit hooks:

1. Check this documentation first
2. Review hook output for specific error messages
3. Check tool-specific documentation
4. Ask for help in project discussions
5. Update tools and try again: `pre-commit autoupdate`

Remember: Pre-commit hooks are there to help maintain code quality and catch issues early. Work with them, not against them!
