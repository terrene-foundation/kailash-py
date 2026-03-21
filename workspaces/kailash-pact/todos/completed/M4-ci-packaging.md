# Milestone 4: CI & Packaging

Dependencies: Milestone 3 (tests must pass before CI integration)
Estimated: Same session as M3

---

## TODO-15: Add dedicated CI job for kailash-pact

**Priority**: HIGH (FINDING-11 — can't use matrix, need dedicated job)
**Files**: `.github/workflows/unified-ci.yml`

### Implementation
Add a `test-pact` job (NOT a matrix entry — FINDING-11):

```yaml
test-pact:
  runs-on: ubuntu-latest
  needs: [lint]  # or whatever the lint job is called
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: "3.11"
    - name: Install kailash core
      run: pip install -e .
    - name: Install kailash-pact with dev deps
      run: pip install -e "packages/kailash-pact[dev]"
    - name: Run pact tests
      run: |
        cd packages/kailash-pact
        pytest tests/ -v --timeout=120 --tb=short
```

### Verify
- CI job runs on PR checks
- Tests pass in CI environment (ubuntu, Python 3.11)
- Job name appears in required status checks

### Acceptance criteria
- `test-pact` job appears in CI workflow
- Job passes on the feat/trust-merge branch

---

## TODO-16: Verify editable install and import resolution

**Priority**: HIGH (smoke test before release)
**Files**: None (validation only)

### Steps
1. Clean install in fresh venv:
   ```bash
   python -m venv /tmp/pact-verify --clear
   source /tmp/pact-verify/bin/activate
   pip install -e .
   pip install -e packages/kailash-pact
   ```
2. Verify imports:
   ```python
   from pact.governance import GovernanceEngine
   from pact.governance.config import ConstraintEnvelopeConfig, TrustPostureLevel
   from pact.governance.config import VerificationLevel
   from pact.examples.university.org import create_university_org
   from kailash.trust import TrustPosture
   assert TrustPostureLevel is TrustPosture
   assert VerificationLevel.AUTO_APPROVED.value == "auto_approved"
   print("All imports OK")
   ```
3. Verify wheel build:
   ```bash
   cd packages/kailash-pact
   pip install build
   python -m build --wheel
   ```

### Acceptance criteria
- All imports resolve correctly
- Wheel builds without errors
- `pact.examples.university` is included in the wheel

---

## TODO-17: Update kailash root pyproject.toml pact extra

**Priority**: MEDIUM
**Files**: `pyproject.toml` (root)

### Changes
Add `pact` optional extra to root kailash pyproject.toml:
```toml
[project.optional-dependencies]
pact = [
    "kailash-pact>=0.2.0",
]
```

Update `all` extra to include pact:
```toml
all = [
    "kailash[server,cli,http,database,...,trust,...,pact]",
    ...
]
```

### Acceptance criteria
- `pip install kailash[pact]` installs kailash-pact
