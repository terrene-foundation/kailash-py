# ADR-0020: Package Distribution Strategy

## Status
Accepted

## Context
When preparing the Kailash Python SDK for distribution via PyPI, we needed to decide what files should be included in the package. The initial v0.1.0 release included all files from the repository (tests, documentation, examples, data files), resulting in a bloated package that was unnecessarily large for end users.

## Decision
We will use a MANIFEST.in file to explicitly control what files are included in the PyPI distribution, following the principle of including only what's necessary for users to use the SDK.

### Included Files
- Source code (`src/` directory)
- Essential metadata files (README.md, LICENSE, setup files)
- Package configuration (pyproject.toml, setup.py, setup.cfg)

### Excluded Files
- Test files (`tests/` directory)
- Documentation source files (`docs/`, `guide/`)
- Example files (`examples/`)
- Data files (`data/`, `outputs/`, `workflow_executions/`)
- Development files (CLAUDE.md, CONTRIBUTING.md, pytest.ini)
- Build artifacts and caches
- Version control files (.git, .github)

## Consequences

### Positive
- **Smaller package size**: Users download only what they need to use the SDK
- **Faster installation**: Reduced download and installation time
- **Cleaner user experience**: No confusion about test/example files
- **Security**: No accidental inclusion of sensitive development files

### Negative
- **Examples not included**: Users must visit GitHub to see examples
- **Tests not runnable**: Users cannot run tests from installed package
- **Documentation separation**: Docs must be hosted separately (e.g., ReadTheDocs)

### Mitigation
- Provide clear links to GitHub repository in README
- Host documentation on ReadTheDocs or GitHub Pages
- Consider creating a separate `kailash-examples` package if needed

## Implementation
```ini
# MANIFEST.in
# Include only essential files
include README.md LICENSE pyproject.toml setup.py setup.cfg
recursive-include src *.py

# Exclude all non-essential directories
prune tests docs examples guide data outputs
```

## References
- [Python Packaging User Guide - Including files in source distributions](https://packaging.python.org/en/latest/guides/using-manifest-in/)
- [PEP 517 - A build-system independent format for source trees](https://www.python.org/dev/peps/pep-0517/)

## Notes
- Version 0.1.0 was released with all files included
- Version 0.1.1 was released with proper exclusions
- Future releases will follow this distribution strategy