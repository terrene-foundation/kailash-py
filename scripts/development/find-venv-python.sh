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

# Resolve the main checkout root via git-common-dir (worktree-safe).
GIT_COMMON_DIR=$(git rev-parse --git-common-dir 2>/dev/null || true)
if [ -z "${GIT_COMMON_DIR}" ]; then
  echo "find-venv-python.sh: not inside a git repository" >&2
  exit 64
fi

# `--git-common-dir` returns .git (relative). Resolve to the main checkout root.
MAIN_CHECKOUT=$(cd "${GIT_COMMON_DIR}/.." && pwd -P)
VENV_PYTHON="${MAIN_CHECKOUT}/.venv/bin/python"

if [ ! -x "${VENV_PYTHON}" ]; then
  echo "find-venv-python.sh: no executable at ${VENV_PYTHON}" >&2
  echo "  hint: run \`uv sync\` from ${MAIN_CHECKOUT}" >&2
  exit 65
fi

exec "${VENV_PYTHON}" "$@"
