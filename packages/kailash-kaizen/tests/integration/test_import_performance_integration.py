"""
Integration tests for Kaizen import performance optimization.

These tests validate that import performance optimizations work correctly
in real environments with actual infrastructure dependencies.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


class TestImportPerformanceIntegration:
    """Integration tests for import performance in real environments."""

    def test_import_performance_with_environment_variables(self):
        """
        Test: Import performance with environment configuration.

        Expected: Environment variables don't significantly impact import time.
        This tests realistic deployment scenarios with env config.
        """
        # Test script with environment variables set
        test_script = """
import os
import sys
import time

# Set typical environment configuration
os.environ["KAIZEN_DEBUG"] = "true"
os.environ["KAIZEN_MEMORY_ENABLED"] = "false"
os.environ["KAIZEN_SIGNATURE_PROGRAMMING_ENABLED"] = "true"
os.environ["KAIZEN_MCP_ENABLED"] = "false"
os.environ["KAIZEN_SECURITY_LEVEL"] = "standard"

# Clear any cached imports
modules_to_remove = [m for m in sys.modules.keys() if m.startswith('kaizen')]
for mod in modules_to_remove:
    del sys.modules[mod]

# Measure import time with environment
start_time = time.perf_counter()
import kaizen
end_time = time.perf_counter()

import_time_ms = (end_time - start_time) * 1000
print(f"IMPORT_TIME_ENV:{import_time_ms:.1f}")

# Test that configuration loading works when explicitly called
kaizen.load_config_from_env()  # This triggers environment loading
config = kaizen.get_resolved_config()
print(f"DEBUG_ENABLED:{config.get('debug', False)}")
print(f"SIGNATURE_ENABLED:{config.get('signature_programming_enabled', False)}")
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(test_script)
            script_path = f.name

        try:
            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                timeout=15,
                cwd=str(Path(__file__).parent.parent.parent),
            )

            # Parse results
            output_lines = result.stdout.strip().split("\n")

            import_time = None
            debug_enabled = None
            signature_enabled = None

            for line in output_lines:
                if line.startswith("IMPORT_TIME_ENV:"):
                    import_time = float(line.split(":")[1])
                elif line.startswith("DEBUG_ENABLED:"):
                    debug_enabled = line.split(":")[1] == "True"
                elif line.startswith("SIGNATURE_ENABLED:"):
                    signature_enabled = line.split(":")[1] == "True"

            print("\n=== ENVIRONMENT INTEGRATION TEST ===")
            print(f"Import time with env config: {import_time:.1f}ms")
            print(f"Debug enabled: {debug_enabled}")
            print(f"Signature programming enabled: {signature_enabled}")

            # Validate performance and functionality
            assert import_time is not None, "Failed to measure import time"
            assert (
                import_time < 120
            ), f"Import with env config too slow: {import_time:.1f}ms"
            assert debug_enabled is True, "Environment config not loaded correctly"
            assert signature_enabled is True, "Environment config not loaded correctly"

            print("✓ Environment integration test passed")

        finally:
            os.unlink(script_path)

    def test_concurrent_import_performance(self):
        """
        Test: Import performance under concurrent load.

        Expected: Multiple concurrent imports don't cause performance degradation.
        This tests real-world scenarios with multiple processes.
        """
        # Test script for concurrent imports
        concurrent_test_script = '''
import sys
import time
import concurrent.futures
import threading

def measure_import_time(test_id):
    """Measure import time in isolated thread."""
    # Clear any cached imports for this thread
    modules_to_remove = [m for m in sys.modules.keys() if m.startswith('kaizen')]
    for mod in modules_to_remove:
        if mod in sys.modules:
            del sys.modules[mod]

    start_time = time.perf_counter()
    import kaizen
    end_time = time.perf_counter()

    import_time_ms = (end_time - start_time) * 1000
    return test_id, import_time_ms

# Run concurrent imports
num_concurrent = 3
results = []

with concurrent.futures.ThreadPoolExecutor(max_workers=num_concurrent) as executor:
    futures = [executor.submit(measure_import_time, i) for i in range(num_concurrent)]
    for future in concurrent.futures.as_completed(futures):
        test_id, import_time = future.result()
        results.append(import_time)
        print(f"CONCURRENT_IMPORT:{test_id}:{import_time:.1f}")

# Calculate statistics
avg_time = sum(results) / len(results)
max_time = max(results)
print(f"CONCURRENT_AVG:{avg_time:.1f}")
print(f"CONCURRENT_MAX:{max_time:.1f}")
'''

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(concurrent_test_script)
            script_path = f.name

        try:
            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(Path(__file__).parent.parent.parent),
            )

            # Parse results
            output_lines = result.stdout.strip().split("\n")

            concurrent_times = []
            avg_time = None
            max_time = None

            for line in output_lines:
                if line.startswith("CONCURRENT_IMPORT:"):
                    parts = line.split(":")
                    import_time = float(parts[2])
                    concurrent_times.append(import_time)
                elif line.startswith("CONCURRENT_AVG:"):
                    avg_time = float(line.split(":")[1])
                elif line.startswith("CONCURRENT_MAX:"):
                    max_time = float(line.split(":")[1])

            print("\n=== CONCURRENT IMPORT TEST ===")
            print(f"Concurrent imports: {len(concurrent_times)}")
            print(f"Individual times: {[f'{t:.1f}ms' for t in concurrent_times]}")
            print(f"Average time: {avg_time:.1f}ms")
            print(f"Maximum time: {max_time:.1f}ms")

            # Validate concurrent performance
            assert (
                len(concurrent_times) >= 3
            ), "Should have at least 3 concurrent imports"
            assert avg_time < 150, f"Concurrent average too slow: {avg_time:.1f}ms"
            assert max_time < 200, f"Concurrent maximum too slow: {max_time:.1f}ms"

            print("✓ Concurrent import test passed")

        finally:
            os.unlink(script_path)

    def test_import_performance_after_agent_usage(self):
        """
        Test: Import performance remains good after heavy agent usage.

        Expected: Lazy loading doesn't negatively impact subsequent imports.
        This tests that our optimizations don't have memory leaks or degradation.
        """
        # Test script that uses agents heavily then measures fresh import
        usage_test_script = """
import sys
import time

# First import and heavy usage
print("=== HEAVY USAGE PHASE ===")
import kaizen

# Create framework and agents (triggers lazy loading)
framework = kaizen.Kaizen(config={"signature_programming_enabled": True})

# Create multiple agents to exercise the system
agents = []
for i in range(5):
    agent = framework.create_agent(f"agent_{i}", {"model": "gpt-3.5-turbo"})
    agents.append(agent)

print(f"Created {len(agents)} agents successfully")

# Now clear modules and test fresh import performance
print("=== FRESH IMPORT PERFORMANCE TEST ===")
modules_to_remove = [m for m in sys.modules.keys() if m.startswith('kaizen')]
for mod in modules_to_remove:
    del sys.modules[mod]

# Measure fresh import after heavy usage
start_time = time.perf_counter()
import kaizen
end_time = time.perf_counter()

import_time_ms = (end_time - start_time) * 1000
print(f"FRESH_IMPORT_TIME:{import_time_ms:.1f}")

# Test that basic functionality still works
try:
    new_framework = kaizen.Kaizen()
    new_agent = new_framework.create_agent("test", {"model": "gpt-3.5-turbo"})
    print("FUNCTIONALITY_PRESERVED:True")
except Exception as e:
    print(f"FUNCTIONALITY_PRESERVED:False:{e}")
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(usage_test_script)
            script_path = f.name

        try:
            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                timeout=20,
                cwd=str(Path(__file__).parent.parent.parent),
            )

            # Parse results
            output_lines = result.stdout.strip().split("\n")

            fresh_import_time = None
            functionality_preserved = None

            for line in output_lines:
                if line.startswith("FRESH_IMPORT_TIME:"):
                    fresh_import_time = float(line.split(":")[1])
                elif line.startswith("FUNCTIONALITY_PRESERVED:"):
                    functionality_preserved = line.split(":")[1] == "True"

            print("\n=== POST-USAGE IMPORT TEST ===")
            print(f"Fresh import time after heavy usage: {fresh_import_time:.1f}ms")
            print(f"Functionality preserved: {functionality_preserved}")

            # Validate post-usage performance
            assert fresh_import_time is not None, "Failed to measure fresh import time"
            assert (
                fresh_import_time < 120
            ), f"Fresh import after usage too slow: {fresh_import_time:.1f}ms"
            assert (
                functionality_preserved is True
            ), "Functionality not preserved after heavy usage"

            print("✓ Post-usage import test passed")

        finally:
            os.unlink(script_path)


if __name__ == "__main__":
    # Run integration tests
    pytest.main([__file__, "-v", "-s"])
