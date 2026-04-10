#!/usr/bin/env bash
# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
#
# Extract the public API surface of kailash-py and save to api-surface.txt.
# This output will be diffed against the Rust SDK equivalent for parity checks.
#
# Usage:
#   ./scripts/check-api-parity.sh
#
# Output:
#   api-surface.txt  (one public symbol per line, sorted alphabetically)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUTPUT_FILE="$REPO_ROOT/api-surface.txt"

echo "Extracting public API surface from src/kailash/ ..."
python3 "$SCRIPT_DIR/extract-api-surface.py" "$REPO_ROOT/src/kailash/" > "$OUTPUT_FILE"

SYMBOL_COUNT=$(wc -l < "$OUTPUT_FILE" | tr -d ' ')
echo "Wrote $SYMBOL_COUNT symbols to $OUTPUT_FILE"

# If a previous api-surface.txt exists in git, show the diff
if git -C "$REPO_ROOT" show HEAD:api-surface.txt > /dev/null 2>&1; then
    DIFF=$(git -C "$REPO_ROOT" diff --no-index -- <(git -C "$REPO_ROOT" show HEAD:api-surface.txt) "$OUTPUT_FILE" 2>/dev/null || true)
    if [ -n "$DIFF" ]; then
        echo ""
        echo "API surface changes since last commit:"
        echo "$DIFF"
    else
        echo "No API surface changes detected."
    fi
fi
