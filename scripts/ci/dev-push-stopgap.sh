#!/usr/bin/env bash
# Stopgap push guard for the CI-free `dev` integration trunk.
#
# STATUS: TEMPORARY. This is NOT the canonical `dev-preflight` described in the
# 2026-09-10 dev memo (corpus + inventory audit + register chain, with the guard
# refusing a push unless a green RECEIPT matching HEAD exists). That script was
# referenced but not supplied. This file deliberately does NOT invent a receipt
# format: a second, divergent receipt chain would be worse than none, because it
# would then have to be migrated. DELETE THIS FILE when the canonical preflight
# lands.
#
# What it does: `dev` has no CI by construction (rules/dev-integration-trunk.md
# MUST-2), so a push to it is otherwise wholly unchecked. This runs the checks
# that already exist in this repo against the commit being pushed, and refuses
# on red.
#
# Usage:
#   scripts/ci/dev-push-stopgap.sh            # check HEAD
#   COC_DEV_PUSH_SKIP=1 git push origin dev   # documented, loud escape
#
# Install as a git hook:
#   ln -sf ../../scripts/ci/dev-push-stopgap.sh .git/hooks/pre-push
set -uo pipefail

REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)
cd "$REPO_ROOT" || exit 1

PY=".venv/bin/python"
FAILED=0
note() { printf '  %-52s %s\n' "$1" "$2"; }

if [ "${COC_DEV_PUSH_SKIP:-0}" = "1" ]; then
    echo "dev-push-stopgap: SKIPPED via COC_DEV_PUSH_SKIP=1"
    echo "  This is a deliberate bypass of the only gate on a CI-free trunk."
    echo "  rules/git.md § Discipline: document the bypass in the commit body."
    exit 0
fi

echo "dev-push-stopgap: checking $(git rev-parse --short HEAD) (stopgap; not the canonical preflight)"

# --- 0. The interpreter must be the venv one, not a pyenv/asdf shim ---------
if [ ! -x "$PY" ]; then
    note "venv interpreter" "MISSING ($PY) — cannot verify; REFUSING"
    echo "dev-push-stopgap: REFUSED — run 'uv venv && uv sync' first."
    exit 1
fi

# --- 1. Working tree must be clean -----------------------------------------
# A dirty tree means what is pushed is not what was checked.
if [ -n "$(git status --porcelain)" ]; then
    note "working tree" "DIRTY — pushed commit != checked tree"
    FAILED=1
else
    note "working tree" "clean"
fi

# --- 2. Never push a checkpoint(UNREVIEWED): commit to a shared trunk -------
# orchestration-launch-ledger.md MUST-5 mandates that prefix on rescue
# checkpoints precisely so a merge gate can detect one; this is that gate.
if git log origin/main..HEAD --format=%s 2>/dev/null | grep -q '^checkpoint(UNREVIEWED):'; then
    note "unreviewed checkpoints" "PRESENT — refusing"
    FAILED=1
else
    note "unreviewed checkpoints" "none"
fi

# --- 3. Pre-commit over the range being pushed ------------------------------
# Scoped to changed files, never --all-files: a full run rewrites 2,022 files
# here (#1995), and test-parsimony.md MUST-1 blocks the broad invocation.
CHANGED=$(git diff --name-only origin/dev...HEAD 2>/dev/null || git diff --name-only HEAD~1...HEAD 2>/dev/null || true)
if [ -z "$CHANGED" ]; then
    note "pre-commit (changed files)" "no changed files resolved — SKIPPED"
else
    if echo "$CHANGED" | xargs .venv/bin/pre-commit run --files >/tmp/devpush_precommit.log 2>&1; then
        note "pre-commit (changed files)" "pass"
    else
        note "pre-commit (changed files)" "FAIL (see /tmp/devpush_precommit.log)"
        FAILED=1
    fi
fi

# --- 4. Test suites covering the changed areas ------------------------------
# Mapped by path so an unrelated change does not pay for the whole tree
# (test-parsimony.md MUST-1). Add a mapping when you add a surface.
declare -a SUITES=()
echo "$CHANGED" | grep -q '^src/kailash/trust/' && SUITES+=("tests/trust/unit/")
echo "$CHANGED" | grep -qE '^src/kailash/trust/a2a/|^packages/kailash-kaizen/' \
    && SUITES+=("packages/kailash-kaizen/tests/integration/trust/test_a2a_service.py")

if [ ${#SUITES[@]} -eq 0 ]; then
    note "targeted suites" "no mapped surface touched — SKIPPED"
else
    for suite in "${SUITES[@]}"; do
        # Root tests/ and packages/*/tests/ cannot share one pytest process
        # (ImportPathMismatchError on conftest) — orphan-detection.md Rule 5a.
        if timeout 900 "$PY" -m pytest "$suite" -q -p no:cacheprovider \
             --timeout=120 --timeout-method=signal >"/tmp/devpush_$(basename "$suite").log" 2>&1; then
            note "pytest $suite" "pass"
        else
            note "pytest $suite" "FAIL (see /tmp/devpush_$(basename "$suite").log)"
            FAILED=1
        fi
    done
fi

if [ "$FAILED" -ne 0 ]; then
    echo "dev-push-stopgap: REFUSED. dev has no CI — this was the only check."
    echo "  Fix, or bypass deliberately with COC_DEV_PUSH_SKIP=1 and say why in the commit body."
    exit 1
fi

echo "dev-push-stopgap: OK"
echo "  NOTE: this is a stopgap. It does NOT do the corpus/inventory audit or"
echo "  the register chain the canonical dev-preflight performs, and it issues"
echo "  no receipt. A green here is NOT a canonical-preflight green."
exit 0
