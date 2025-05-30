# Kailash Python SDK Documentation

This directory contains the documentation for the Kailash Python SDK.

## Structure

- `api/` - Sphinx source files for API documentation
- `adr/` - Architecture Decision Records
- `features/` - Feature documentation
- `prd/` - Product Requirements Documents
- `todos/` - Development task tracking

## Building Documentation

### Prerequisites

- Python 3.8+
- pip

### Build for GitHub Pages

The easiest way to build the documentation for GitHub Pages:

```bash
cd docs
python build_docs.py
```

This will:
1. Install required dependencies
2. Build the Sphinx documentation
3. Prepare files for GitHub Pages deployment

### Manual Build

To build documentation manually:

```bash
cd docs/api
pip install -r requirements.txt
make html
```

The built documentation will be in `docs/api/_build/html/`.

## Deploying to GitHub Pages

1. Build the documentation using the script above
2. Commit the generated files
3. Configure GitHub Pages in repository settings

The repository includes a GitHub Actions workflow that automatically builds and deploys documentation when changes are pushed to the main branch.