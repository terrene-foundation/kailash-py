---
paths:
  - "**/*.py"
  - "pyproject.toml"
  - "conftest.py"
  - "tests/**"
---

# Python Environment Rules

Every Python project MUST use `.venv` at the project root, managed by `uv`. Global Python is BLOCKED.

**Why:** Global Python causes dependency conflicts between projects and makes builds non-reproducible across machines.

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

**Why:** Committed `.venv/` directories bloat the repo with platform-specific binaries and break on every other developer's machine.

- `uv.lock` MUST be committed for applications (may gitignore for libraries)

**Why:** Without a committed lockfile, `uv sync` resolves different versions on different machines, causing "works on my machine" failures.

- One project, one `.venv` (no `.env`, `venv`, `.virtualenv` alternatives)

**Why:** Non-standard venv names are invisible to tooling (IDEs, CI, `uv run`), causing silent use of the wrong Python interpreter.

- No `pip install` in project context — use `uv sync` or `uv pip install`

**Why:** `pip install` bypasses `uv.lock` resolution, installing versions that conflict with the lockfile and creating invisible dependency drift.

- No global/system/Homebrew/pyenv-global Python for project work

**Why:** System Python packages leak into project imports, masking missing dependencies that will crash in CI or on another developer's machine.
