# Milestone 4b: CI, Documentation & Gap Fixes

Covers items identified in red team review of the todo list.

## TODO-69: Update GitHub Actions CI workflows

Update CI workflows that reference eatp or trust-plane:

### `.github/workflows/trust-plane.yml` (if exists)
- Change test path from `packages/trust-plane/tests/` to `tests/trust/plane/`
- Change install from `packages/eatp` + `packages/trust-plane` to `pip install -e ".[trust]"`
- Change verification from `from trustplane import TrustProject` to `from kailash.trust.plane import TrustProject`

### `.github/workflows/trust-tests.yml` (if exists)
- Add `src/kailash/trust/**` to path triggers
- Add `tests/trust/` to test paths

### `.github/workflows/publish-pypi.yml`
- Verify shim packages (eatp 0.3.0, trust-plane 0.3.0) can still be built and published from `packages/` directories
- Update any version patterns

### `.github/workflows/unified-ci.yml`
- Add trust test paths to the test matrix

**Acceptance**: CI passes on the feature branch. All workflows reference correct paths.

---

## TODO-70: Update Sphinx/RST documentation

Update all `.rst` files that reference `eatp` or `trustplane` imports:

Likely files (verify with grep):
- `docs/frameworks/kaizen.rst`
- `docs/index.rst`
- `docs/core/trust.rst`
- `docs/enterprise/compliance.rst`
- `docs/enterprise/index.rst`
- `docs/quickstart.rst`

**Acceptance**: `grep -r "from eatp\|from trustplane" docs/ --include="*.rst"` returns zero results.

---

## TODO-71: Update docs/trust/ markdown documentation

Update markdown docs in `docs/trust/` that reference old import paths:
- `trust-posture-constraint-guide.md`
- `trust-reasoning-traces.md`
- `trust-security-hardening.md`
- `trust-integration-guide.md`
- And any others found via grep

Also update `docs/00-authority/` files:
- `01-api-reference.md`
- `03-security-model.md`
- `04-enterprise-features.md`
- `00-architecture.md`

**Acceptance**: `grep -r "from eatp\|from trustplane" docs/ --include="*.md"` returns zero results.

---

## TODO-72: Update .claude/skills and .claude/agents references

Update all skill and agent files that reference `eatp`, `trustplane`, or old package paths:

**Skills** (`~9 files in .claude/skills/26-eatp-reference/`):
- Update import examples to use `kailash.trust.*`
- Update scope references

**Agents** (`~12 agent files`):
- `eatp-expert.md` — update scope and references
- `kaizen-specialist.md` — update trust integration references
- `security-reviewer.md` — update file path scopes
- `intermediate-reviewer.md` — update trust file paths
- Other agents that reference trust/eatp

**Acceptance**: `grep -r "from eatp\|from trustplane\|packages/eatp\|packages/trust-plane" .claude/ --include="*.md"` returns zero results (or only historical references in workspace files).

---

## TODO-73: Copy py.typed marker file

Copy PEP 561 typing marker:
```bash
cp packages/eatp/src/eatp/py.typed src/kailash/trust/py.typed
```

Without this, mypy/pyright won't recognize `kailash.trust` as a typed package.

**Acceptance**: `src/kailash/trust/py.typed` exists.

---

## TODO-74: Handle EATP .env file

Check if `packages/eatp/src/eatp/.env` exists and contains anything:
- If it contains test config: DO NOT copy to `src/kailash/trust/` (violates security rules)
- If it's a template: rename to `.env.example` or remove
- Add to `.gitignore` if not already there

**Acceptance**: No `.env` file in `src/kailash/trust/`. Security rules satisfied.

---

## TODO-75: Handle root-level EATP test file

Copy `packages/eatp/tests/test_coverage_verification.py` to `tests/trust/test_coverage_verification.py`.

This file sits at the root of the EATP test directory (not under unit/integration/e2e/) and was missed in TODO-18's tier-based copy description.

**Acceptance**: File copied. Test passes with updated imports.

---

## TODO-76: Create shim generation script

Per risk assessment RISK-02 mitigation, create a script to auto-generate shim files rather than writing 135 files manually:

```python
# scripts/generate_trust_shims.py
# Introspects kailash.trust module tree and generates
# eatp/* and trustplane/* redirect stubs with DeprecationWarning
```

**Acceptance**: Script generates all ~135 shim files. Output matches expected shim pattern. Manual verification of 5 randomly selected shims.

---

## TODO-77: Create PR for merge

Per `rules/branch-protection.md`, create PR with required format:

```bash
gh pr create --title "feat(trust): merge eatp + trust-plane into kailash.trust" \
    --body "## Summary
- Merge eatp and trust-plane packages into kailash.trust.* namespace
- kailash 2.0.0 with kailash[trust] optional extra
- Backward-compatible shim packages for eatp and trust-plane
- kaizen 2.0.0 drops eatp dependency

## Test plan
- [ ] All trust protocol tests pass (tests/trust/)
- [ ] All trust plane tests pass (tests/trust/plane/)
- [ ] Shim backward compat tests pass
- [ ] Security regression tests pass (12 patterns)
- [ ] Clean install verification
- [ ] CLI entry points work

Closes D001"
```

**Acceptance**: PR created, CI green, ready for review.
