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
- "PYTHONPATH=packages/foo/src:packages/bar/src is fine for one test run"

**Why:** Editable installs make the sub-package `src/` the canonical
import path, so editors, type checkers, test runners, and scripts all
agree on which code runs. A `PYTHONPATH` prefix is invisible to every
tool except the single command that sets it, leaving IDE jump-to-def,
Pyright, and ad-hoc scripts pointing at stale or absent installations.

### 3. Monorepo `[tool.uv.sources]` Over PyPI Version Pin

Root `pyproject.toml` constraints on monorepo sub-packages MUST be
expressed as a `[tool.uv.sources]` editable path entry, NOT as a PyPI
version pin. Version pins on sub-packages that are also installed
editable are BLOCKED.

```toml
# DO — editable path entry in root pyproject.toml
[tool.uv.sources]
kailash-dataflow = { path = "packages/kailash-dataflow", editable = true }
kailash-nexus = { path = "packages/kailash-nexus", editable = true }
kailash-kaizen = { path = "packages/kailash-kaizen", editable = true }

# DO NOT — PyPI version pin on a sub-package you're editing locally
[project]
dependencies = [
    "kailash-dataflow>=2.0.3",   # uv sync downloads stale PyPI tarball
    "kailash-nexus>=1.5.0",       # masks your local edits
]
```

**BLOCKED rationalizations:**

- "The PyPI pin ensures minimum version compatibility"
- "Editable installs are only for dev, CI uses the pin"
- "The version pin and local source happen to match"

**Why:** A PyPI version pin on a sub-package the developer is editing
forces `uv sync` to download a stale tarball from PyPI, masking the
editable changes. This is recurring monorepo bootstrap pain that wastes
debugging time every session.

Origin: `workspaces/arbor-upstream-fixes/.session-notes` (2026-04-12)

### 4. MUST NOT Duplicate Sub-Package Test Deps In Root Dev Deps

A dev dependency declared by a sub-package (`packages/*/pyproject.toml`)
MUST NOT also be declared in the root `pyproject.toml [dev]` section.
Re-declaring at the root is BLOCKED — it installs the package into the
root test venv where pytest's plugin auto-discovery loads it for every
test run, including runs that don't need it.

```toml
# DO — sub-packages own their test deps
# packages/kailash-pact/pyproject.toml:
[project.optional-dependencies]
test = ["hypothesis>=6.98"]

# pyproject.toml [dev]:
# (no hypothesis entry — sub-package venv provides it for its own tests)

# DO NOT — duplicate the dep at the root
[project.optional-dependencies]
dev = [
    "hypothesis>=6.0.0",   # already in kailash-pact + kailash-ml
]
```

**BLOCKED rationalizations:**

- "The version is different, it's not a duplicate"
- "hypothesis is small, it won't hurt to install at root"
- "Our test command might need it someday"
- "The sub-package pin is for test-time only, this one is for dev-time"

**Why:** `hypothesis` registers itself as a pytest plugin. When pytest
starts a test run in the root venv, it auto-discovers hypothesis and
imports `hypothesis.internal.conjecture.shrinking.collection` through
pytest's assertion rewriter. The recursive AST rewrite of that module
exhausts memory on GitHub runners, producing a `MemoryError` during
test collection with no root-cause signal (the stack trace points at
`_pytest/assertion/rewrite.py` internals). This bit us twice — once
caught by main CI, once in a cross-SDK PR — and cost hours of
debugging. Root cause: the root venv shouldn't install what only
sub-package test venvs need.

Origin: PR #430 CI failure (2026-04-12), commit a9fd4e56 — hypothesis
was added to root `[dev]` to enable a prior test collection workaround
and surfaced as a MemoryError three commits later. Fixed by removing
hypothesis from root dev deps.

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
