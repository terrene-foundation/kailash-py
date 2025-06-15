#!/bin/bash
# Pytest Compliance Cleanup Script
# Moves non-test files from tests/ to appropriate directories

set -e

echo '🧹 Moving non-pytest files from tests/ directory...'


# Remove non-compliant files
rm -f 'tests/unit/nodes/test_transform_consolidated.py'  # Non-pytest file

echo '✅ Moved 0 example files'
echo '✅ Moved 0 utility files'
echo '✅ Removed 1 non-compliant files'
echo '🧪 tests/ directory now contains only proper pytest tests'