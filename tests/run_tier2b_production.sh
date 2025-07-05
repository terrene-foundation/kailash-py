#!/bin/bash
# Run Tier 2B Production Load Tests with proper configuration

echo "=========================================="
echo "Running Tier 2B Production Load Tests"
echo "=========================================="
echo ""
echo "Configuration:"
echo "- PostgreSQL: test_user@localhost:5434/kailash_test"
echo "- Redis: localhost:6380"
echo "- Ollama: localhost:11434"
echo "- Timeout: 10 minutes per test"
echo ""

# Export database credentials
export POSTGRES_USER=test_user
export POSTGRES_PASSWORD=test_password
export POSTGRES_DB=kailash_test
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5434

# Export Redis configuration
export REDIS_HOST=localhost
export REDIS_PORT=6380

# Check Docker services
echo "Checking Docker services..."
docker ps | grep -E "(postgres|redis|ollama|mock)" | head -5
echo ""

# Run the slow/production tests only
echo "Starting production tests..."
echo ""

# Run with extended timeout and verbose output
python -m pytest tests/integration/ \
    -m "slow" \
    -v \
    --tb=short \
    --timeout=600 \
    --timeout-method=thread \
    --disable-warnings \
    -x \
    2>&1 | tee tier2b_results.log

# Check results
if [ ${PIPESTATUS[0]} -eq 0 ]; then
    echo ""
    echo "✅ All Tier 2B production tests passed!"
else
    echo ""
    echo "❌ Some Tier 2B tests failed. Check tier2b_results.log for details."
fi

# Summary
echo ""
echo "=========================================="
echo "Test Summary:"
grep -E "(PASSED|FAILED|ERROR|SKIPPED)" tier2b_results.log | tail -20
echo "=========================================="
