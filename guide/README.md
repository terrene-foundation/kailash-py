# Kailash Python SDK - Internal Development Guide

This directory contains internal documentation for developers and contributors to the Kailash Python SDK. These documents are not included in the PyPI distribution and are only accessible to those with access to this private repository.

## Directory Structure

### In this directory:
- **`adr/`** - Architecture Decision Records
- **`development/`** - Development workflows and processes
- **`features/`** - Feature documentation and specifications
- **`mistakes/`** - Common mistakes and lessons learned
- **`prd/`** - Product Requirements Documents
- **`todos/`** - Task tracking and development history

### In project root:
- **`CLAUDE.md`** - AI assistant guidelines and project conventions (required by Claude Code)

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

## Accessing Documentation

These documents are only available when:
- Cloning the repository directly from GitHub
- Having access to the private repository
- Working on development (not from PyPI installation)
