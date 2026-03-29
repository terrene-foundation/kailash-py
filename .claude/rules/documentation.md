---
paths:
  - "README.md"
  - "docs/**"
  - "CHANGELOG.md"
---

# Documentation Rules

## Scope

These rules apply to `README.md`, `docs/**`, `CHANGELOG.md`, and any public-facing documentation files.

## MUST Rules

### 1. Version Numbers Must Match pyproject.toml

All version numbers in documentation MUST match the actual version in `pyproject.toml` for each package.

**Locations to update on version bump:**

- `README.md` — architecture diagram, Key Features heading, ecosystem frameworks table
- `docs/index.rst` — version badge, current release line, framework version list
- `docs/getting_started.rst` — welcome heading, framework chooser table
- Each package's own `README.md`

**Enforced by**: documentation-validator agent, intermediate-reviewer pre-commit check
**Violation**: BLOCK release (see deployment.md release checklist)

### 2. Repository URLs Must Point to Monorepo

All GitHub URLs MUST point to `terrene-foundation/kailash-py` (the monorepo).

**Correct**:

```
https://github.com/terrene-foundation/kailash-py
https://github.com/terrene-foundation/kailash-py/tree/main/docs/kaizen
https://github.com/terrene-foundation/kailash-py/issues
```

**Incorrect**:

```
https://github.com/terrene-foundation/kailash-sdk
https://github.com/terrene-foundation/kailash-kaizen
https://github.com/terrene-foundation/kailash-dataflow
https://github.com/terrene-foundation/kailash-nexus
https://github.com/your-org/kailash-sdk
```

### 3. Clone Instructions Must Use Current Repo Name

All clone and setup instructions MUST use `kailash-py`.

**Correct**:

```bash
git clone https://github.com/terrene-foundation/kailash-py.git
cd kailash-py
```

### 4. No Internal References in Public Docs

Public-facing documentation MUST NOT contain:

- Internal domain names (e.g., `studio.kailash.ai` — use `example.com`)
- Internal project names or session references
- References to `enterprise-app` or other private repos without context

**Enforced by**: intermediate-reviewer pre-commit check
**Violation**: BLOCK commit for public-facing files

### 5. Sphinx Docs Must Build Clean

The `docs/` directory (Sphinx RST and Markdown) MUST build without warnings on any release.

```bash
cd docs && python build_docs.py
```

## MUST NOT Rules

### 1. No Dead Link References

MUST NOT reference paths that don't exist in the repo (e.g., `examples/feature_examples/`).

### 2. No Placeholder URLs

MUST NOT use placeholder URLs like `your-org`, `YOUR_USERNAME` in production documentation. Use `terrene-foundation` for org references and generic instructions for fork-based workflows.

## Documentation Update Triggers

Documentation MUST be reviewed when:

- Package version is bumped
- Repository is restructured (files/directories moved or removed)
- New package is added to the monorepo
- Package is deprecated or removed
- Public-facing URLs change

## Exceptions

Documentation exceptions require:

1. Explicit human approval
2. Tracked issue for remediation
