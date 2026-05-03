#!/usr/bin/env bash
# Block reintroduction of TODO-NNN markers in production source without
# a same-line (tracked: ...) link or other tracker. Mirrors the regression
# test at tests/regression/test_no_untracked_todo_nnn.py and the issue
# #781 cleanup workstream. See .claude/rules/zero-tolerance.md Rule 2 + Rule 6.

set -euo pipefail

# `grep -I` skips binary files (e.g. transient *.pyc under __pycache__).
# Exclusions (alternated, anchored by `:` to stay inside grep-output column 3+):
#   :\s*///       Rust doc-comments  (out-of-language for src/ + packages/*/src)
#   :\s*//!       Rust inner doc-comments
#   /build/       transient build artifacts
#   tracked:      explicit tracker link — Class 2 exception per Rule 6
#   /egg-info/    setuptools-generated SOURCES.txt — references filenames, not code comments
hits=$(grep -rInE 'TODO-[0-9]+' src/ packages/*/src/ 2>/dev/null \
       | grep -vE ':\s*///|:\s*//!|/build/|tracked:|\.egg-info/' \
       || true)

if [ -n "$hits" ]; then
    {
        echo "Untracked TODO-NNN markers in production source:"
        echo "$hits"
        echo ""
        echo "Each must either (1) carry a same-line (tracked: gh#NNN) link"
        echo "or (2) be deleted. See .claude/rules/zero-tolerance.md"
        echo "Rule 2 + Rule 6, and the issue #781 cleanup workstream."
    } >&2
    exit 1
fi
