#!/usr/bin/env bash
# Resolve the canonical .venv/bin/python path that survives git-worktree cwds.
#
# Pre-commit hooks invoked from inside a git worktree (`.claude/worktrees/<X>/`)
# resolve relative paths against the worktree's cwd, NOT the main checkout. The
# main checkout's `.venv/` does not exist inside worktrees, so a hook entry
# like `entry: .venv/bin/python ...` raises `No such file or directory` and
# blocks the commit. Both W7 worktrees on 2026-04-27 had to bypass via
# `git -c core.hooksPath=/dev/null` per rules/git.md § Pre-Commit Hook
# Workarounds — that bypass is now structurally avoidable.
#
# Resolution mechanism: `git rev-parse --git-common-dir` always returns the
# path to the MAIN `.git/`, whether invoked from main checkout or any
# worktree. The main checkout's root is one level above (`<git-common-dir>/..`)
# and that is where `.venv/` lives by python-environment.md MUST Rule 1.
#
# Usage (in pre-commit-config.yaml):
#   entry: scripts/development/find-venv-python.sh -m pytest tests/unit/
#
# This wrapper exec's the resolved python interpreter with all forwarded args,
# so the `entry:` keeps its original argv shape without indirection.
set -euo pipefail

# Opt in to fleet execution for the expensive pytest hook. Keep the argv and
# exit status intact; a missing launcher must fail rather than run locally.
# Unset the opt-in remotely to prevent recursion if a caller reuses this wrapper.
if [ "${KAILASH_TRESTLE_TESTS:-0}" = "1" ] &&
   [ "${1:-}" = "-m" ] && [ "${2:-}" = "pytest" ]; then
  # One shared launcher honors an optional fleet host for every worker slot.
  # Keep the selector as one argument; never interpret it as shell syntax.
  # Preserve pathname newlines: command substitution only trims record
  # delimiters after a fixed non-newline suffix has protected the payload.
  FLEET_REPO=$(git rev-parse --show-toplevel 2>/dev/null && printf '.') || FLEET_REPO=""
  FLEET_REPO=${FLEET_REPO%.}
  FLEET_REPO=${FLEET_REPO%$'\n'}
  if [ -z "${FLEET_REPO}" ]; then
    echo "find-venv-python.sh: not inside a git repository" >&2
    exit 64
  fi
  FLEET_REPO=$(CDPATH='' cd -- "${FLEET_REPO}" && pwd -P && printf '.')
  FLEET_REPO=${FLEET_REPO%.}
  FLEET_REPO=${FLEET_REPO%$'\n'}
  TRESTLE_ARGS=(run --no-reap-cache --no-reap-mirrors --repo "${FLEET_REPO}")
  # Filter the fleet for platform-gated checks while retaining host arbitration.
  if [ -n "${KAILASH_TRESTLE_OS:-}" ]; then
    TRESTLE_ARGS+=(--os "${KAILASH_TRESTLE_OS}")
  fi
  if [ -n "${KAILASH_TRESTLE_HOST:-}" ]; then
    TRESTLE_ARGS+=(--host "${KAILASH_TRESTLE_HOST}")
  fi
  UV_ARGS=(run --frozen)
  if [ -n "${UV_PYTHON:-}" ]; then
    UV_ARGS+=(--python "${UV_PYTHON}")
  fi
  exec trestle "${TRESTLE_ARGS[@]}" -- env -u KAILASH_TRESTLE_TESTS UV_LINK_MODE=copy uv "${UV_ARGS[@]}" \
    --extra dev --extra server --extra http-client \
    --extra db-postgres --extra db-mysql --extra db-sqlite --extra redis \
    --extra trust --extra auth --extra auth-azure --extra monitoring \
    --extra telemetry --extra scheduler --extra mcp --extra data \
    --extra rfc3161 --extra dataflow --extra nexus --extra kaizen python "$@"
fi

# Resolve the main checkout root via git-common-dir (worktree-safe).
GIT_COMMON_DIR=$(git rev-parse --git-common-dir 2>/dev/null && printf '.') || GIT_COMMON_DIR=""
GIT_COMMON_DIR=${GIT_COMMON_DIR%.}
GIT_COMMON_DIR=${GIT_COMMON_DIR%$'\n'}
if [ -z "${GIT_COMMON_DIR}" ]; then
  echo "find-venv-python.sh: not inside a git repository" >&2
  exit 64
fi

# `--git-common-dir` returns .git (relative). Resolve to the main checkout root.
MAIN_CHECKOUT=$(CDPATH='' cd -- "${GIT_COMMON_DIR}/.." && pwd -P && printf '.')
MAIN_CHECKOUT=${MAIN_CHECKOUT%.}
MAIN_CHECKOUT=${MAIN_CHECKOUT%$'\n'}
VENV_PYTHON="${MAIN_CHECKOUT}/.venv/bin/python"

if [ ! -x "${VENV_PYTHON}" ]; then
  echo "find-venv-python.sh: no executable at ${VENV_PYTHON}" >&2
  echo "  hint: run \`uv sync\` from ${MAIN_CHECKOUT}" >&2
  exit 65
fi

# Resolving the INTERPRETER is only half of the worktree problem. That venv's
# editable installs are `.pth` files holding ABSOLUTE paths into the MAIN
# checkout, so from a linked worktree the hook imports `kailash`,
# `kailash_mcp`, `kaizen`, `nexus` and friends from MAIN while pytest collects
# the tests from the WORKTREE. The gate then reports on a combination that
# exists nowhere: this branch's tests against main's code.
#
# That is worse than a plain failure, because it is wrong in BOTH directions --
# a fix made in a worktree looks broken (its updated test runs against the
# un-fixed main source), and a regression introduced in a worktree can pass.
# Observed on 2026-09-10: a test updated alongside a source fix in the same
# worktree failed here while passing against the worktree's own source.
#
# PYTHONPATH entries precede site-packages `.pth` paths in `sys.path`, so
# prepending the worktree's source roots makes the checkout under test the one
# whose tests are being collected. No-op in the main checkout.
TOPLEVEL=$(git rev-parse --show-toplevel 2>/dev/null && printf '.') || TOPLEVEL=""
TOPLEVEL=${TOPLEVEL%.}
TOPLEVEL=${TOPLEVEL%$'\n'}
if [ -n "${TOPLEVEL}" ] && [ "${TOPLEVEL}" != "${MAIN_CHECKOUT}" ]; then
  WT_PATHS=""
  # PYTHONPATH is a path list, so a colon in an individual source path cannot
  # be represented. Refuse before importing from a different checkout.
  append_worktree_source() {
    case "$1" in
      *:*)
        printf 'find-venv-python.sh: source path contains an unrepresentable colon: %q\n' "$1" >&2
        exit 66
        ;;
    esac
    WT_PATHS="${WT_PATHS:+${WT_PATHS}:}$1"
  }
  [ -d "${TOPLEVEL}/src" ] && append_worktree_source "${TOPLEVEL}/src"
  for pkg_src in "${TOPLEVEL}"/packages/*/src; do
    [ -d "${pkg_src}" ] || continue
    append_worktree_source "${pkg_src}"
  done
  if [ -n "${WT_PATHS}" ]; then
    export PYTHONPATH="${WT_PATHS}${PYTHONPATH:+:${PYTHONPATH}}"
  fi
fi

exec "${VENV_PYTHON}" "$@"
