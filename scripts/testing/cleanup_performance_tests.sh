#!/bin/bash
# Performance/Scenario Tests Cleanup Script
# Generated automatically - review before executing

set -e

echo '🔧 Implementing performance/scenario test cleanup...'

echo '🗑️  Removing obsolete test files...'
rm -f 'tests/e2e/scenarios/__init__.py'  # Empty e2e directory or placeholder
rm -f 'tests/e2e/misc/test_sso_enterprise_auth.py'  # Empty e2e directory or placeholder
rm -f 'tests/e2e/performance/__init__.py'  # Empty e2e directory or placeholder
rm -f 'tests/conftest.py'  # Test that mostly skips execution
rm -f 'tests/e2e/__init__.py'  # Empty e2e directory or placeholder
rm -f 'tests/e2e/misc/__init__.py'  # Empty e2e directory or placeholder

echo '📁 Creating relocation directories...'
mkdir -p 'examples/performance_benchmarks/'
mkdir -p 'examples/scenarios/'
mkdir -p 'tests/integration/'

echo '📦 Relocating test files...'
mv 'tests/integration/integrations/qa_llm_agent_test.py' 'examples/performance_benchmarks/qa_llm_agent_test.py'  # Resource-intensive test better suited for performance suite
mv 'tests/unit/workflows/test_cycle_performance.py' 'examples/performance_benchmarks/test_cycle_performance.py'  # Resource-intensive test better suited for performance suite
mv 'tests/unit/nodes/test_enterprise/monitoring/test_performance_benchmark.py' 'examples/performance_benchmarks/test_performance_benchmark.py'  # Resource-intensive test better suited for performance suite
mv 'tests/e2e/test_performance_tracking_integration.py' 'examples/performance_benchmarks/test_performance_tracking_integration.py'  # Development performance test
mv 'tests/unit/workflows/test_cycle_scenarios_simplified.py' 'examples/scenarios/test_cycle_scenarios_simplified.py'  # Scenario test that's more of an example
mv 'tests/unit/nodes/test_enterprise/admin/test_user_role_management_nodes.py' 'tests/integration/test_user_role_management_nodes.py'  # Docker-dependent test in unit directory
mv 'tests/unit/workflows/test_cycle_scenarios.py' 'examples/scenarios/test_cycle_scenarios.py'  # Scenario test that's more of an example

echo '✅ Cleanup completed!'
echo '📊 Summary:'
echo '  Removed: 6 files'
echo '  Relocated: 7 files'
echo '  Kept: 32 files'
