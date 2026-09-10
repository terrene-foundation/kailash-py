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
#   scripts/ci/dev-push-stopgap.sh --manual   # check HEAD (no stdin contract)
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

# --- Determine WHAT is being pushed -----------------------------------------
# As a pre-push hook git delivers one line per ref on stdin:
#   <local-ref> <local-sha> <remote-ref> <remote-sha>
# Ignoring stdin and checking HEAD is a FAIL-OPEN: `git push origin
# other:dev` pushes `other` while the guard validates HEAD. Two further
# fail-opens are pinned here because they shipped in a sibling repo's guard:
#
#  1. Splitting on /\s+/ (or unquoted word-splitting) accepts U+00A0, which
#     `git check-ref-format` PERMITS in a ref name -- so a crafted branch name
#     splits into five fields and the destination binds to the wrong token.
#     git emits single ASCII spaces and forbids a space in a ref name, so an
#     exact 4-field ASCII split is precise, not heuristic.
#  2. Empty stdin read as "nothing to push". git never invokes pre-push with
#     zero refs, so empty always means the delivery path failed -> REFUSE.
GATED_REFS="refs/heads/dev refs/heads/main"
TARGET_SHA=""
TARGET_DESC=""

# `--manual` is EXPLICIT, not inferred. Relying on `[ -t 0 ]` alone makes the
# guard unrunnable wherever stdin is a non-tty pipe (CI, `cmd >log 2>&1`,
# most automation) -- it would take the hook path, see empty stdin and refuse.
# The tempting "fix" for that is deleting the empty-stdin refusal, which
# reinstates the fail-open it exists to close. So manual mode gets its own
# flag and the hook path keeps its contract intact.
if [ "${1:-}" = "--manual" ] || { [ -t 0 ] && [ $# -eq 0 ]; }; then
    TARGET_SHA=$(git rev-parse HEAD)
    TARGET_DESC="HEAD (manual run; NOT a pre-push invocation -- the ref-line contract was not exercised)"
else
    STDIN_CONTENT=$(cat)
    if [ -z "$STDIN_CONTENT" ]; then
        echo "dev-push-stopgap: REFUSED — empty stdin."
        echo "  git never invokes pre-push with zero refs, so this means the"
        echo "  delivery path failed. Treating it as 'nothing to push' would be"
        echo "  a fail-open."
        exit 1
    fi
    while IFS= read -r raw; do
        [ -z "$raw" ] && continue
        # Exact ASCII-space split. NOT $(...) word-splitting, NOT /\s+/.
        OLDIFS=$IFS; IFS=' '; set -f; set -- $raw; set +f; IFS=$OLDIFS
        if [ "$#" -ne 4 ] || [ -z "$1" ] || [ -z "$2" ] || [ -z "$3" ] || [ -z "$4" ]; then
            echo "dev-push-stopgap: REFUSED — malformed ref line ($# fields, expected 4)."
            echo "  A ref name containing a non-ASCII space would split wrong here."
            exit 1
        fi
        LOCAL_SHA="$2"; REMOTE_REF="$3"
        case " $GATED_REFS " in
            *" $REMOTE_REF "*)
                if [ "$LOCAL_SHA" = "0000000000000000000000000000000000000000" ]; then
                    echo "dev-push-stopgap: REFUSED — deletion of gated ref $REMOTE_REF."
                    exit 1
                fi
                TARGET_SHA="$LOCAL_SHA"; TARGET_DESC="$REMOTE_REF"
                ;;
        esac
    done <<EOF
$STDIN_CONTENT
EOF
    if [ -z "$TARGET_SHA" ]; then
        echo "dev-push-stopgap: OK — no gated ref in this push (nothing to check)."
        exit 0
    fi
fi

echo "dev-push-stopgap: checking $(git rev-parse --short "$TARGET_SHA") -> $TARGET_DESC"

# The commit being pushed MUST be the one we test. Checking HEAD while a
# different SHA is pushed is the fail-open this block exists to close.
if [ "$TARGET_SHA" != "$(git rev-parse HEAD)" ]; then
    note "pushed SHA vs HEAD" "MISMATCH — refusing (would test the wrong tree)"
    echo "dev-push-stopgap: REFUSED — pushing $TARGET_SHA but HEAD is $(git rev-parse HEAD)."
    echo "  Check out the commit you intend to push, or push HEAD."
    exit 1
fi

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
# `grep -c`, never `grep -q`. Under `set -o pipefail`, `grep -q` exits on the
# FIRST match, `git log` then dies writing to the closed pipe with SIGPIPE, and
# pipefail surfaces git's 141 as the pipeline status — so the `if` takes the
# ELSE branch on a match and the guard silently reports "none". Measured here:
# `grep_status=141` with the checkpoint commit present. It is a RACE (git
# sometimes finishes first), so the bug is intermittent, which is worse.
# `grep -c` reads all input, so nothing exits early.
CHECKPOINTS=$(git log origin/main..HEAD --format=%s 2>/dev/null | grep -c '^checkpoint(UNREVIEWED):' || true)
if [ "${CHECKPOINTS:-0}" -gt 0 ]; then
    note "unreviewed checkpoints" "$CHECKPOINTS PRESENT — refusing"
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
# Counts, not `grep -q` — same pipefail/SIGPIPE race as above.
# Map SOURCE *and* TEST paths. Keying only on source was a real hole: a change
# touching just a test file mapped to NO suite, so a broken test sailed through
# (measured — the failing-suite pole exited 0 until this was added).
[ "$(printf '%s\n' "$CHANGED" | grep -cE '^src/kailash/trust/|^tests/trust/' || true)" -gt 0 ] \
    && SUITES+=("tests/trust/unit/")
[ "$(printf '%s\n' "$CHANGED" | grep -cE '^src/kailash/trust/a2a/|^packages/kailash-kaizen/' || true)" -gt 0 ] \
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
