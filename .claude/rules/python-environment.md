---
paths:
  - "**/*.py"
  - "pyproject.toml"
  - "conftest.py"
  - "tests/**"
---

# Python Environment Rules

Every Python project MUST use `.venv` at the project root, managed by `uv`. Global Python is BLOCKED.

## Setup

```bash
uv venv          # Create .venv
uv sync          # Install from pyproject.toml + uv.lock

# ❌ pip install -e .           — installs into global Python
# ❌ python -m venv .venv       — use uv venv instead (faster, lockfile support)
# ❌ pip install -r requirements.txt  — use uv sync
```

## Running

```bash
# Option A: Activate
source .venv/bin/activate
pytest tests/ -x

# Option B: uv run (preferred)
uv run pytest tests/ -x
uv run python scripts/migrate.py

# ❌ pytest tests/   — which Python? Unknown.
# ❌ python -c "..."  — may use global Python
```

## Verification

```bash
which python  # Should show .venv/bin/python, NOT /usr/bin/python
```

## Rules

- `.venv/` MUST be in `.gitignore`
- `uv.lock` MUST be committed for applications (may gitignore for libraries)
- One project, one `.venv` (no `.env`, `venv`, `.virtualenv` alternatives)
- No `pip install` in project context — use `uv sync` or `uv pip install`
- No global/system/Homebrew/pyenv-global Python for project work
