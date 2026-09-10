#!/usr/bin/env bash
# Pole table for dev-push-stopgap.sh — BOTH directions.
#
# A guard never shown to refuse is indistinguishable from one that always
# passes; one that always refuses is equally worthless. Every refusal case here
# has an allow case that differs in exactly one property.
#
# Run:  scripts/ci/dev-push-stopgap.poles.sh
# Requires a CLEAN working tree — the guard refuses on a dirty tree by design,
# which would make every case pass for the wrong reason. That is not
# hypothetical: it silently invalidated the first run of this table.
set -uo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)" || exit 1

GUARD=./scripts/ci/dev-push-stopgap.sh
HEAD_SHA=$(git rev-parse HEAD)
ZERO=0000000000000000000000000000000000000000
NBSP=$(printf '\xc2\xa0')   # U+00A0; git check-ref-format ACCEPTS this in a ref name
FAIL=0

if [ -n "$(git status --porcelain)" ]; then
    echo "poles: REFUSING TO RUN — working tree is dirty."
    echo "  The guard refuses on a dirty tree, so every case would 'pass' for"
    echo "  that reason instead of the one under test."
    exit 1
fi

run() { printf '%s' "$1" | "$GUARD" >/dev/null 2>&1; echo "$?"; }

check() { # desc expect stdin
    got=$(run "$3")
    if [ "$got" = "$2" ]; then v="PASS"; else v="FAIL"; FAIL=1; fi
    printf '  %-46s expect=%s got=%s  %s\n' "$1" "$2" "$got" "$v"
}

echo "poles: dev-push-stopgap (HEAD=$(git rev-parse --short HEAD))"

# --- REFUSALS -------------------------------------------------------------
# git never invokes pre-push with zero refs, so empty means delivery failed.
check "empty stdin" 1 ""
check "malformed 2-field line" 1 "refs/heads/dev $HEAD_SHA"
check "deletion of gated ref" 1 "refs/heads/dev $ZERO refs/heads/dev $HEAD_SHA"
check "gated ref, pushed SHA != HEAD" 1 "refs/heads/dev ${ZERO}1 refs/heads/dev $ZERO"
check "gated ref via NBSP name, SHA != HEAD" 1 \
    "refs/heads/a${NBSP}b ${ZERO}1 refs/heads/dev $ZERO"

# --- ALLOWS ---------------------------------------------------------------
check "non-gated ref" 0 "refs/heads/feat/x $HEAD_SHA refs/heads/feat/x $ZERO"
check "gated ref at HEAD" 0 "refs/heads/dev $HEAD_SHA refs/heads/dev $ZERO"
# An NBSP in the LOCAL ref name is NOT itself an attack. The attack is a
# permissive split shifting the fields so the guard reads the SHA as the remote
# ref and concludes "no gated ref in this push". With an exact ASCII-space
# split the fields stay aligned, dev IS identified, and a HEAD push is
# correctly allowed. Asserting a refusal here would pin the WRONG behaviour.
check "gated ref via NBSP name, at HEAD" 0 \
    "refs/heads/a${NBSP}b $HEAD_SHA refs/heads/dev $ZERO"

# --- the split itself, since the above allow-case cannot show it -----------
echo "  --- field-alignment control (the property the NBSP cases rest on) ---"
python3 - "$HEAD_SHA" "$ZERO" <<'PY'
import sys
head, zero = sys.argv[1], sys.argv[2]
raw = f"refs/heads/a b {head} refs/heads/dev {zero}"
perm, exact = raw.split(), raw.split(" ")
ok = len(perm) == 5 and len(exact) == 4 and exact[2] == "refs/heads/dev"
print(f"  {'permissive split loses the gated ref':<46} "
      f"perm={len(perm)}f exact={len(exact)}f  {'PASS' if ok else 'FAIL'}")
sys.exit(0 if ok else 1)
PY
[ $? -ne 0 ] && FAIL=1

echo
if [ "$FAIL" -ne 0 ]; then echo "poles: FAILED"; exit 1; fi
echo "poles: all cases behaved as specified"
