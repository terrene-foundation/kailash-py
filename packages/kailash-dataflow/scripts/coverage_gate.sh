#!/usr/bin/env bash
# Coverage gate for DataFlow (Phase 8.5).
#
# Enforces the two-tier coverage policy from rules/testing.md:
#
#   * General code under src/dataflow/      --cov-fail-under=80
#   * Security-critical src/dataflow/security/*   --cov-fail-under=100
#   * Trust-plane     src/dataflow/trust/*         --cov-fail-under=100
#
# Usage: ./scripts/coverage_gate.sh [pytest-args...]
#
# Exit codes:
#   0 = both gates passed
#   1 = general gate failed
#   2 = security/trust gate failed

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}[1/2] General coverage gate: src/dataflow/ ≥ 80%${NC}"
if python -m pytest \
    --cov=src/dataflow \
    --cov-report=term-missing \
    --cov-fail-under=80 \
    tests/ "$@"; then
    echo -e "${GREEN}  ✓ general coverage gate passed${NC}"
else
    echo -e "${RED}  ✗ general coverage gate FAILED (< 80%)${NC}" >&2
    exit 1
fi

echo
echo -e "${YELLOW}[2/2] Security + trust coverage gate: 100%${NC}"
if python -m pytest \
    --cov=src/dataflow/security \
    --cov=src/dataflow/trust \
    --cov-report=term-missing \
    --cov-fail-under=100 \
    tests/unit/security \
    tests/unit/trust \
    tests/integration/security \
    tests/integration/trust \
    2>/dev/null; then
    echo -e "${GREEN}  ✓ security/trust coverage gate passed${NC}"
else
    echo -e "${RED}  ✗ security/trust coverage gate FAILED (< 100%)${NC}" >&2
    echo -e "${RED}    src/dataflow/security and src/dataflow/trust MUST hit 100%"
    echo -e "    per rules/testing.md § Coverage Requirements.${NC}" >&2
    exit 2
fi

echo
echo -e "${GREEN}All coverage gates passed.${NC}"
