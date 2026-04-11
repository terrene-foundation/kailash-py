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
which python   # MUST show .venv/bin/python, NOT /usr/bin/python
which python3  # Same check — shims resolve python3 independently
which pytest   # MUST show .venv/bin/pytest
```

## MUST Rules

### 1. MUST Address the Venv Interpreter Explicitly

Every invocation MUST resolve through `.venv/bin/python` (explicit),
`uv run` (resolves via `pyproject.toml`), or an activated shell. Bare
`python` / `python3` / `python3.13` / `pytest` is BLOCKED — pyenv, asdf,
and Homebrew all install shims that can resolve to a different
interpreter than the project `.venv`.

```bash
# DO
.venv/bin/python -m pytest tests/
.venv/bin/python scripts/migrate.py
uv run pytest tests/
source .venv/bin/activate && pytest tests/

# DO NOT
python -m pytest tests/           # which python? unknown
python3 -m pytest tests/          # pyenv shim — may not be .venv
python3.13 -c "import foo"        # same
pytest tests/                     # same — whose pytest?
```

**BLOCKED rationalizations:**

- "It's fine, `which python` showed the venv earlier"
- "The shim points at the right version most of the time"
- "CI uses `python3`, so the test command should match"

**Why:** The pyenv/asdf shim is the #1 cause of "I edited the file but
tests don't see the change" debugging sessions. An installed package
that conflicts with your source — e.g. a Python binding for a crate
you also have in-tree — resolves silently against the wrong code and
tests "pass" without exercising the edit. Explicit `.venv/bin/python`
turns a silent correctness bug into a loud `No such file or directory`
when the venv is missing.

### 2. Monorepo Sub-Packages MUST Be Installed Editable

When a repo contains `packages/*/pyproject.toml`, every sub-package
MUST be installed editable into the root `.venv` at setup time. A
`PYTHONPATH=packages/foo/src:packages/bar/src ...` prefix as a
workaround is BLOCKED.

```bash
# DO — one-time setup
uv pip install \
  -e packages/kailash-dataflow \
  -e packages/kailash-nexus \
  -e packages/kailash-kaizen

# DO NOT — PYTHONPATH prefix workaround
PYTHONPATH=packages/kailash-dataflow/src:packages/kailash-nexus/src \
  .venv/bin/python -m pytest tests/
```

**BLOCKED rationalizations:**

- "PYTHONPATH works for this one command"
- "I'll add the editable install later"
- "The sub-package has its own pytest config anyway"

**Why:** Editable installs make the sub-package `src/` the canonical
import path, so editors, type checkers, test runners, and scripts all
agree on which code runs. A `PYTHONPATH` prefix is invisible to every
tool except the single command that sets it, leaving IDE jump-to-def,
Pyright, and ad-hoc scripts pointing at stale or absent installations.

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

- No bare `python` / `python3` / `pytest` — always `.venv/bin/python` or `uv run`

**Why:** See MUST Rule 1 above. Pyenv/asdf/Homebrew shims silently redirect to the wrong interpreter, turning correctness bugs into lost debugging sessions.

Origin: `workspaces/arbor-upstream-fixes/.session-notes` § "Traps / gotchas" (2026-04-11) — pyenv shim resolved `python3` to a different interpreter containing Rust bindings for a package also in source; tests "passed" against the wrong code.
