# ADR-0021: Documentation Structure and Organization

## Status
Accepted

## Context
The project's documentation was becoming mixed between public API documentation intended for users and internal development documentation intended for contributors. Additionally, the nested `docs/api/` structure was unnecessarily complex for Sphinx documentation.

## Decision
We will separate documentation into two distinct directories:
- `docs/` - Public API documentation for end users
- `guide/` - Internal development documentation for contributors

### Public Documentation (`docs/`)
- Sphinx-based API documentation
- Getting started guides
- Installation instructions
- API reference
- User-facing tutorials

### Internal Documentation (`guide/`)
- Architecture Decision Records (ADRs)
- Development todos
- Feature specifications
- PRDs (Product Requirements Documents)
- Internal architecture notes

### Special Case: CLAUDE.md
The CLAUDE.md file must remain in the project root directory as it's required by Claude Code to be in that specific location.

## Consequences

### Positive
- **Clear separation**: Users see only relevant documentation
- **Simpler structure**: Removed unnecessary nesting (docs/api/ → docs/)
- **Better organization**: Internal docs don't clutter public docs
- **PyPI benefit**: Internal docs automatically excluded from package

### Negative
- **Multiple locations**: Documentation split across directories
- **Potential confusion**: Contributors need to know where to look
- **Update overhead**: Need to maintain references when moving files

### Mitigation
- Clear README sections pointing to each documentation type
- Comprehensive guide/README.md explaining internal structure
- Automated checks to ensure cross-references are valid

## Implementation
```
project-root/
├── CLAUDE.md          # Must stay in root
├── docs/              # Public documentation
│   ├── conf.py
│   ├── index.rst
│   ├── api/
│   │   ├── nodes.rst
│   │   └── workflow.rst
│   └── _build/        # Sphinx output
├── guide/             # Internal documentation
│   ├── README.md
│   ├── adr/
│   ├── todos/
│   └── prd/
```

## References
- [Sphinx Documentation](https://www.sphinx-doc.org/)
- [Documentation as Code](https://www.writethedocs.org/guide/docs-as-code/)

## Notes
- Documentation was reorganized as part of the v0.1.1 release
- All internal references were updated to reflect new structure
- GitHub Actions workflows were updated for new paths
