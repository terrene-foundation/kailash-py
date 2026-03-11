#!/bin/bash
# Verify trust benchmarks setup
# Usage: ./tests/benchmarks/trust/verify_setup.sh

set -e  # Exit on error

echo "========================================="
echo "Trust Benchmarks Setup Verification"
echo "========================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if we're in the right directory
if [ ! -f "pytest.ini" ]; then
    echo -e "${RED}Error: Must be run from kailash-kaizen root directory${NC}"
    echo "Current directory: $(pwd)"
    echo "Expected: /path/to/kailash-kaizen"
    exit 1
fi

echo -e "${GREEN}✓${NC} Running from correct directory"
echo ""

# Check Python version
echo "Checking Python version..."
PYTHON_VERSION=$(python --version 2>&1 | awk '{print $2}')
echo -e "${GREEN}✓${NC} Python $PYTHON_VERSION"
echo ""

# Check pytest
echo "Checking pytest..."
if ! command -v pytest &> /dev/null; then
    echo -e "${RED}✗ pytest not found${NC}"
    echo "Install with: pip install pytest"
    exit 1
fi
PYTEST_VERSION=$(pytest --version | head -1 | awk '{print $2}')
echo -e "${GREEN}✓${NC} pytest $PYTEST_VERSION"
echo ""

# Check pytest-benchmark
echo "Checking pytest-benchmark..."
if ! python -c "import pytest_benchmark" 2>/dev/null; then
    echo -e "${YELLOW}⚠${NC} pytest-benchmark not found"
    echo "Install with: pip install pytest-benchmark"
    echo ""
else
    echo -e "${GREEN}✓${NC} pytest-benchmark installed"
    echo ""
fi

# Check file structure
echo "Verifying file structure..."
FILES=(
    "tests/benchmarks/__init__.py"
    "tests/benchmarks/conftest.py"
    "tests/benchmarks/trust/__init__.py"
    "tests/benchmarks/trust/benchmark_trust_operations.py"
    "tests/benchmarks/trust/generate_report.py"
    "tests/benchmarks/trust/README.md"
    "tests/benchmarks/trust/QUICKSTART.md"
    "tests/benchmarks/trust/IMPLEMENTATION_SUMMARY.md"
    "tests/benchmarks/trust/INDEX.md"
    "tests/benchmarks/trust/DELIVERY_SUMMARY.md"
)

MISSING=0
for file in "${FILES[@]}"; do
    if [ -f "$file" ]; then
        echo -e "${GREEN}✓${NC} $file"
    else
        echo -e "${RED}✗${NC} $file (missing)"
        MISSING=$((MISSING + 1))
    fi
done
echo ""

if [ $MISSING -gt 0 ]; then
    echo -e "${RED}Error: $MISSING files missing${NC}"
    exit 1
fi

# Check Python syntax
echo "Checking Python syntax..."
python -m py_compile tests/benchmarks/trust/benchmark_trust_operations.py
echo -e "${GREEN}✓${NC} benchmark_trust_operations.py"

python -m py_compile tests/benchmarks/trust/generate_report.py
echo -e "${GREEN}✓${NC} generate_report.py"
echo ""

# Check pytest can discover tests
echo "Checking test discovery..."
TEST_COUNT=$(pytest tests/benchmarks/trust/benchmark_trust_operations.py --collect-only -q 2>/dev/null | grep "test_benchmark" | wc -l | xargs)
if [ "$TEST_COUNT" -eq "12" ]; then
    echo -e "${GREEN}✓${NC} All 12 benchmarks discovered"
else
    echo -e "${YELLOW}⚠${NC} Expected 12 benchmarks, found $TEST_COUNT"
fi
echo ""

# Check executable permissions
echo "Checking executable permissions..."
if [ -x "tests/benchmarks/trust/generate_report.py" ]; then
    echo -e "${GREEN}✓${NC} generate_report.py is executable"
else
    echo -e "${YELLOW}⚠${NC} generate_report.py not executable (optional)"
    echo "Fix with: chmod +x tests/benchmarks/trust/generate_report.py"
fi
echo ""

# Summary
echo "========================================="
echo "Verification Summary"
echo "========================================="
echo ""
echo -e "${GREEN}✓${NC} Setup verified successfully!"
echo ""
echo "Next steps:"
echo "  1. Install pytest-benchmark (if not already):"
echo "     pip install pytest-benchmark"
echo ""
echo "  2. Run benchmarks:"
echo "     pytest tests/benchmarks/trust/benchmark_trust_operations.py --benchmark-only"
echo ""
echo "  3. Generate report:"
echo "     pytest tests/benchmarks/trust/benchmark_trust_operations.py --benchmark-json=results.json"
echo "     python tests/benchmarks/trust/generate_report.py results.json > report.md"
echo ""
echo "Documentation:"
echo "  - Quick Start: tests/benchmarks/trust/QUICKSTART.md"
echo "  - Full Docs: tests/benchmarks/trust/README.md"
echo "  - File Index: tests/benchmarks/trust/INDEX.md"
echo ""
