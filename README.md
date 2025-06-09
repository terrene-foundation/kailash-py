# Kailash Python SDK - Internal Development Guide

This directory contains internal documentation for developers and contributors to the Kailash Python SDK. These documents are not included in the PyPI distribution and are only accessible to those with access to this private repository.

## Directory Structure

### Core Directories (with README.md):
- **`adr/`** - Architecture Decision Records (35+ design decisions)
- **`features/`** - In-depth feature implementation guides
- **`reference/`** - LLM-optimized API references and patterns
- **`instructions/`** - Detailed coding and documentation standards
- **`frontend/`** - Frontend development guide
- **`workflows/`** - Development workflows and task checklists

### Additional Directories:
- **`development/`** - SDK development guides and tools
  - **`custom-nodes/`** - Comprehensive custom node development guide (parameter types, examples, troubleshooting)
  - **`pre-commit-hooks.md`** - Development workflow automation
- **`infrastructure/`** - CI/CD and runner configuration
- **`mistakes/`** - Documented mistakes and lessons learned (73+ issues, including critical v0.2.1 base node fixes)
- **`prd/`** - Product Requirements Documents
- **`todos/`** - Active task tracking system
- **`SECURITY.md`** - Comprehensive security documentation

### In project root:
- **`CLAUDE.md`** - Compact LLM quick reference (optimized navigation)

## Important Notes

1. **Private Documentation**: All content in this directory is considered internal and should not be shared publicly.

2. **Not Distributed**: These files are explicitly excluded from PyPI packages via `MANIFEST.in`.

3. **Development Reference**: Use these documents to understand design decisions, development patterns, and project history.

## For Contributors

When contributing to the project:
1. Review `CLAUDE.md` for coding standards and conventions
2. Check ADRs for architectural decisions
3. Consult PRDs for product requirements
4. Learn from documented mistakes to avoid common pitfalls
5. Track tasks using the todos system
6. **Creating custom nodes?** See `development/custom-nodes/` for critical parameter type constraints

## Accessing Documentation

These documents are only available when:
- Cloning the repository directly from GitHub
- Having access to the private repository
- Working on development (not from PyPI installation)
