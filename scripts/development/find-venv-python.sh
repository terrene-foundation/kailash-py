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
TOPLEVEL=$(git rev-parse --show-toplevel 2>/dev/null || true)
if [ -n "${TOPLEVEL}" ] && [ "${TOPLEVEL}" != "${MAIN_CHECKOUT}" ]; then
  WT_PATHS=""
  [ -d "${TOPLEVEL}/src" ] && WT_PATHS="${TOPLEVEL}/src"
  for pkg_src in "${TOPLEVEL}"/packages/*/src; do
    [ -d "${pkg_src}" ] || continue
    WT_PATHS="${WT_PATHS:+${WT_PATHS}:}${pkg_src}"
  done
  if [ -n "${WT_PATHS}" ]; then
    export PYTHONPATH="${WT_PATHS}${PYTHONPATH:+:${PYTHONPATH}}"
  fi
fi

exec "${VENV_PYTHON}" "$@"
