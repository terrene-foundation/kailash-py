# Milestone 7: Cleanup & Documentation

Post-publish cleanup, documentation updates, and COC sync.

## TODO-61: Remove duplicate source from packages/

After shims are published and verified, the original source code in `packages/eatp/src/eatp/` and `packages/trust-plane/src/trustplane/` has been replaced by shim stubs. Verify that:
1. The shim stubs are the only Python files in both packages
2. No original source code remains alongside shims
3. Tests in `packages/eatp/tests/` and `packages/trust-plane/tests/` are either removed or point to the new test locations

**Acceptance**: Original package directories contain only shim files and pyproject.toml.

---

## TODO-62: Update EATP examples

Move or update examples in `packages/eatp/examples/` to use `kailash.trust.*` imports. Options:
1. Move to `examples/trust/` at project root
2. Update in-place with new imports

**Acceptance**: All example files use `kailash.trust.*` imports and run successfully.

---

## TODO-63: Update trust-plane README.md

Update `packages/trust-plane/README.md` to indicate this is a shim package. Point users to `kailash.trust.plane` for the canonical API.

**Acceptance**: README clearly states this is a compatibility shim.

---

## TODO-64: Update EATP deploy/deployment-config.md

Update `packages/eatp/deploy/deployment-config.md` to reflect the shim package status.

**Acceptance**: Deployment config reflects current state.

---

## TODO-65: Clean up Mock-named docs artifacts

Remove the spurious mock-named doc files from git status:
```
docs/<Mock name='test_workflow.name' id='...'>.md
```

These are test artifacts that should never have been created.

**Acceptance**: `git status` no longer shows these files.

---

## TODO-66: Update packages/trust-plane/CLAUDE.md

Update `packages/trust-plane/CLAUDE.md` to reference new file paths. This file contains the Store Security Contract and 13 security patterns — all references must point to `src/kailash/trust/` paths.

**Acceptance**: All file path references updated. No stale `trustplane/` paths.

---

## TODO-67: COC sync — update USE template repos

Run coc-sync to propagate any rule changes (updated scope in eatp.md, trust-plane-security.md) to the COC template repos:
- `kailash-coc-claude-py`

Per feedback memory: always run coc-sync after codification.

**Acceptance**: COC template repo has updated rules.

---

## TODO-68: Update workspace session notes

Write final session notes to `workspaces/eatp-merge/.session-notes` documenting:
- All todos completed
- Final test results
- Publishing status
- Any issues encountered

**Acceptance**: Session notes reflect completed state.
