#!/usr/bin/env python3
"""
Quick test to run all examples and categorize by execution time.
This will help us understand which examples work and how long they take.
"""

import subprocess
import sys
import time
import os
from pathlib import Path
from typing import Dict, List, Tuple

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def find_all_examples() -> List[Path]:
    """Find all Python example files."""
    examples_dir = project_root / "examples"
    example_files = []
    
    # Files to exclude
    exclude_files = {
        "__init__.py",
        "test_runner.py",
        "paths.py",
        "maintenance.py",
        "data_paths.py",
    }
    
    # Search all example directories
    for pattern in ["feature_examples", "node_examples", "integration_examples", "workflow_examples"]:
        for file in examples_dir.rglob(f"{pattern}/**/*.py"):
            if file.name not in exclude_files and not file.name.startswith("_"):
                example_files.append(file)
    
    return sorted(set(example_files))


def run_single_example(file_path: Path, timeout: int = 30) -> Dict[str, any]:
    """Run a single example and collect results."""
    start_time = time.time()
    relative_path = file_path.relative_to(project_root)
    
    # Set up environment
    env = os.environ.copy()
    env['PYTHONPATH'] = str(project_root)
    
    result = {
        "file": str(relative_path),
        "status": "unknown",
        "execution_time": 0,
        "error": None,
        "output_lines": 0
    }
    
    try:
        # Run the example
        proc = subprocess.run(
            [sys.executable, str(file_path)],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(file_path.parent),
            env=env
        )
        
        execution_time = time.time() - start_time
        result["execution_time"] = execution_time
        result["output_lines"] = len(proc.stdout.split('\n')) + len(proc.stderr.split('\n'))
        
        if proc.returncode == 0:
            result["status"] = "success"
        else:
            result["status"] = "failed"
            result["error"] = proc.stderr[:500] if proc.stderr else proc.stdout[:500]
            
    except subprocess.TimeoutExpired:
        result["execution_time"] = timeout
        result["status"] = "timeout"
        result["error"] = f"Timeout after {timeout}s"
    except Exception as e:
        result["execution_time"] = time.time() - start_time
        result["status"] = "exception"
        result["error"] = str(e)[:500]
    
    return result


def main():
    """Run all examples and categorize them."""
    print("🔍 Finding and Running All Examples")
    print("=" * 70)
    
    examples = find_all_examples()
    print(f"Found {len(examples)} example files\n")
    
    results = []
    
    # Run each example
    for i, example in enumerate(examples, 1):
        print(f"[{i}/{len(examples)}] Running {example.name}...", end="", flush=True)
        
        result = run_single_example(example)
        results.append(result)
        
        # Print immediate status
        status_symbol = {
            "success": "✅",
            "failed": "❌",
            "timeout": "⏱️",
            "exception": "💥"
        }.get(result["status"], "❓")
        
        print(f" {status_symbol} ({result['execution_time']:.1f}s)")
    
    # Categorize results
    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)
    
    # By status
    status_counts = {}
    for r in results:
        status = r["status"]
        if status not in status_counts:
            status_counts[status] = []
        status_counts[status].append(r)
    
    print("\nBy Status:")
    for status, items in status_counts.items():
        print(f"  {status}: {len(items)} examples")
    
    # By execution time
    print("\nBy Execution Time:")
    fast = [r for r in results if r["execution_time"] < 2]
    medium = [r for r in results if 2 <= r["execution_time"] < 10]
    slow = [r for r in results if 10 <= r["execution_time"] < 30]
    very_slow = [r for r in results if r["execution_time"] >= 30]
    
    print(f"  Fast (<2s): {len(fast)} examples")
    print(f"  Medium (2-10s): {len(medium)} examples")
    print(f"  Slow (10-30s): {len(slow)} examples")
    print(f"  Very slow (>=30s): {len(very_slow)} examples")
    
    # Show failed examples
    if "failed" in status_counts:
        print("\n❌ Failed Examples:")
        for r in status_counts["failed"][:10]:  # Show first 10
            print(f"  - {r['file']}")
            if r["error"]:
                print(f"    Error: {r['error'].split(chr(10))[0]}")
    
    # Show timeout examples
    if "timeout" in status_counts:
        print("\n⏱️  Timeout Examples:")
        for r in status_counts["timeout"]:
            print(f"  - {r['file']} (>{r['execution_time']}s)")
    
    # Show slowest successful examples
    successful = [r for r in results if r["status"] == "success"]
    if successful:
        successful.sort(key=lambda x: x["execution_time"], reverse=True)
        print("\n🐌 Slowest Successful Examples:")
        for r in successful[:5]:
            print(f"  - {r['file']} ({r['execution_time']:.1f}s)")
    
    # Save detailed results
    output_file = project_root / "example_test_results.txt"
    with open(output_file, 'w') as f:
        f.write("DETAILED TEST RESULTS\n")
        f.write("=" * 70 + "\n\n")
        
        for r in results:
            f.write(f"File: {r['file']}\n")
            f.write(f"Status: {r['status']}\n")
            f.write(f"Time: {r['execution_time']:.2f}s\n")
            if r["error"]:
                f.write(f"Error: {r['error']}\n")
            f.write("-" * 50 + "\n")
    
    print(f"\n📄 Detailed results saved to: {output_file}")
    
    # Return status
    total_failed = len(status_counts.get("failed", [])) + len(status_counts.get("exception", []))
    print(f"\n{'✅ All examples working!' if total_failed == 0 else f'❌ {total_failed} examples need fixing'}")
    
    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())