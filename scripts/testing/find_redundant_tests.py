#!/usr/bin/env python3
"""
Find Redundant Tests for Removal

Analyzes the test suite to identify:
1. Duplicate tests (same functionality tested multiple times)
2. Obsolete tests (testing deprecated or removed functionality)
3. Redundant coverage (multiple tests covering identical code paths)
4. Empty or placeholder tests
5. Tests that are no longer relevant
"""

import ast
import re
import sys
from pathlib import Path
from typing import List, Dict, Set, Any
from collections import defaultdict
import hashlib

def extract_test_info(test_file: Path) -> Dict[str, Any]:
    """Extract comprehensive information about a test file."""
    try:
        content = test_file.read_text(encoding='utf-8')
        
        info = {
            "file": str(test_file.relative_to(Path("tests"))),
            "full_path": str(test_file),
            "size_lines": len(content.splitlines()),
            "size_bytes": len(content),
            "test_functions": [],
            "test_classes": [],
            "imports": [],
            "tested_modules": set(),
            "test_patterns": [],
            "markers": [],
            "content_hash": hashlib.md5(content.encode()).hexdigest(),
            "is_empty": False,
            "is_placeholder": False,
            "has_real_tests": False,
            "deprecated_patterns": [],
            "similar_files": []
        }
        
        # Parse AST
        try:
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                    info["test_functions"].append({
                        "name": node.name,
                        "line": node.lineno,
                        "docstring": ast.get_docstring(node) or "",
                        "has_implementation": len(node.body) > 1 or (
                            len(node.body) == 1 and not isinstance(node.body[0], ast.Pass)
                        )
                    })
                elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
                    info["test_classes"].append({
                        "name": node.name,
                        "line": node.lineno,
                        "methods": [n.name for n in node.body if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")]
                    })
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        info["imports"].append(alias.name)
                        if "kailash" in alias.name:
                            info["tested_modules"].add(alias.name)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    info["imports"].append(node.module)
                    if "kailash" in node.module:
                        info["tested_modules"].add(node.module)
        except:
            pass
        
        # Analyze content patterns
        info["test_patterns"] = extract_test_patterns(content)
        info["markers"] = extract_pytest_markers(content)
        info["deprecated_patterns"] = find_deprecated_patterns(content)
        
        # Determine if file is empty/placeholder
        info["is_empty"] = info["size_lines"] <= 10 and len(info["test_functions"]) == 0
        info["is_placeholder"] = (
            len(info["test_functions"]) <= 2 and
            all(not func["has_implementation"] for func in info["test_functions"])
        ) or "placeholder" in content.lower() or "todo" in content.lower()
        
        info["has_real_tests"] = any(func["has_implementation"] for func in info["test_functions"])
        
        return info
        
    except Exception as e:
        return {
            "file": str(test_file.relative_to(Path("tests"))),
            "error": str(e),
            "is_empty": True,
            "has_real_tests": False
        }

def extract_test_patterns(content: str) -> List[str]:
    """Extract common test patterns from content."""
    patterns = []
    
    # Common test patterns
    if "assert" in content:
        patterns.append("assertions")
    if "mock" in content.lower() or "Mock" in content:
        patterns.append("mocking")
    if "pytest.fixture" in content:
        patterns.append("fixtures")
    if "pytest.parametrize" in content:
        patterns.append("parametrized")
    if "asyncio" in content or "async def" in content:
        patterns.append("async")
    if "database" in content.lower() or "db" in content.lower():
        patterns.append("database")
    if "workflow" in content.lower():
        patterns.append("workflow")
    if "node" in content.lower():
        patterns.append("node")
    if "runtime" in content.lower():
        patterns.append("runtime")
    
    return patterns

def extract_pytest_markers(content: str) -> List[str]:
    """Extract pytest markers from content."""
    markers = []
    marker_patterns = [
        r"@pytest\.mark\.(\w+)",
        r"pytestmark = pytest\.mark\.(\w+)"
    ]
    
    for pattern in marker_patterns:
        matches = re.findall(pattern, content)
        markers.extend(matches)
    
    return list(set(markers))

def find_deprecated_patterns(content: str) -> List[str]:
    """Find deprecated patterns in test code."""
    deprecated = []
    
    # Known deprecated patterns
    deprecated_patterns = {
        "AsyncLocalRuntime": "Use LocalRuntime(enable_async=True)",
        "from kailash.core": "Deprecated import path",
        ".process(": "Use .execute() method instead",
        "unittest.TestCase": "Use pytest style tests",
        "setUp": "Use pytest fixtures",
        "tearDown": "Use pytest fixtures"
    }
    
    for pattern, reason in deprecated_patterns.items():
        if pattern in content:
            deprecated.append(f"{pattern}: {reason}")
    
    return deprecated

def find_duplicate_tests(test_infos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Find tests that are duplicates or very similar."""
    duplicates = []
    
    # Group by content hash (exact duplicates)
    hash_groups = defaultdict(list)
    for info in test_infos:
        if info.get("content_hash") and info.get("has_real_tests"):
            hash_groups[info["content_hash"]].append(info)
    
    for hash_val, files in hash_groups.items():
        if len(files) > 1:
            duplicates.append({
                "type": "exact_duplicate",
                "files": [f["file"] for f in files],
                "reason": "Identical file content",
                "action": "keep_one_remove_others"
            })
    
    # Find similar test names
    name_groups = defaultdict(list)
    for info in test_infos:
        for func in info.get("test_functions", []):
            # Group by similar test function names
            base_name = re.sub(r'_\d+$|_new$|_old$|_v2$', '', func["name"])
            name_groups[base_name].append({
                "file": info["file"],
                "function": func["name"],
                "has_impl": func["has_implementation"]
            })
    
    for base_name, tests in name_groups.items():
        if len(tests) > 1:
            # Check for redundant test variations
            implemented = [t for t in tests if t["has_impl"]]
            if len(implemented) > 1:
                duplicates.append({
                    "type": "similar_tests",
                    "base_name": base_name,
                    "tests": tests,
                    "reason": f"Multiple tests with similar names: {base_name}",
                    "action": "review_consolidate"
                })
    
    return duplicates

def find_obsolete_tests(test_infos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Find tests that are obsolete or testing removed functionality."""
    obsolete = []
    
    for info in test_infos:
        obsolete_reasons = []
        
        # Empty or placeholder files
        if info.get("is_empty"):
            obsolete_reasons.append("Empty test file")
        elif info.get("is_placeholder"):
            obsolete_reasons.append("Placeholder test with no implementation")
        
        # Files with deprecated patterns
        if info.get("deprecated_patterns"):
            obsolete_reasons.extend(info["deprecated_patterns"])
        
        # Tests with no real functionality
        if not info.get("has_real_tests") and info.get("test_functions"):
            obsolete_reasons.append("Test functions exist but have no implementation")
        
        # Tests that only import and do nothing
        if (info.get("size_lines", 0) < 50 and 
            len(info.get("test_functions", [])) <= 1 and
            not info.get("has_real_tests")):
            obsolete_reasons.append("Minimal test file with no substantial tests")
        
        if obsolete_reasons:
            obsolete.append({
                "file": info["file"],
                "reasons": obsolete_reasons,
                "action": "remove",
                "size": info.get("size_lines", 0)
            })
    
    return obsolete

def find_redundant_coverage(test_infos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Find tests that provide redundant coverage."""
    redundant = []
    
    # Group tests by what they're testing
    module_groups = defaultdict(list)
    for info in test_infos:
        for module in info.get("tested_modules", []):
            module_groups[module].append(info)
    
    for module, tests in module_groups.items():
        if len(tests) > 3:  # More than 3 files testing the same module
            # Check if some are redundant
            unit_tests = [t for t in tests if "/unit/" in t["file"]]
            integration_tests = [t for t in tests if "/integration/" in t["file"]]
            
            if len(unit_tests) > 2 and len(integration_tests) > 1:
                redundant.append({
                    "type": "redundant_coverage",
                    "module": module,
                    "unit_tests": len(unit_tests),
                    "integration_tests": len(integration_tests),
                    "files": [t["file"] for t in tests],
                    "reason": f"Extensive coverage of {module} might be redundant",
                    "action": "review_consolidate"
                })
    
    return redundant

def analyze_test_suite() -> Dict[str, Any]:
    """Analyze the entire test suite for redundancy."""
    tests_dir = Path("tests")
    
    # Collect all test files
    test_files = list(tests_dir.rglob("test_*.py")) + list(tests_dir.rglob("*_test.py"))
    
    # Extract information from each test file
    test_infos = []
    for test_file in test_files:
        info = extract_test_info(test_file)
        test_infos.append(info)
    
    # Find different types of redundancy
    duplicates = find_duplicate_tests(test_infos)
    obsolete = find_obsolete_tests(test_infos)
    redundant_coverage = find_redundant_coverage(test_infos)
    
    return {
        "total_files": len(test_infos),
        "test_infos": test_infos,
        "duplicates": duplicates,
        "obsolete": obsolete,
        "redundant_coverage": redundant_coverage,
        "summary": {
            "exact_duplicates": len([d for d in duplicates if d["type"] == "exact_duplicate"]),
            "similar_tests": len([d for d in duplicates if d["type"] == "similar_tests"]),
            "obsolete_files": len(obsolete),
            "redundant_modules": len(redundant_coverage)
        }
    }

def print_redundancy_report(analysis: Dict[str, Any]):
    """Print detailed redundancy analysis report."""
    print("🔍 Test Suite Redundancy Analysis")
    print("=" * 50)
    
    total = analysis["total_files"]
    summary = analysis["summary"]
    
    print(f"\n📊 Summary ({total} test files analyzed):")
    print(f"  🔄 Exact duplicates: {summary['exact_duplicates']}")
    print(f"  👥 Similar tests: {summary['similar_tests']}")
    print(f"  🗑️  Obsolete files: {summary['obsolete_files']}")
    print(f"  📦 Redundant coverage: {summary['redundant_modules']}")
    
    total_issues = sum(summary.values())
    if total_issues > 0:
        print(f"\n💡 Cleanup potential: {total_issues} issues found")
    else:
        print(f"\n✨ Test suite appears clean!")
    
    # Detailed findings
    if analysis["duplicates"]:
        print(f"\n🔄 DUPLICATE TESTS:")
        for dup in analysis["duplicates"]:
            if dup["type"] == "exact_duplicate":
                print(f"  📄 Exact duplicates:")
                for file in dup["files"]:
                    print(f"    - {file}")
                print(f"    Action: {dup['action']}")
            else:
                print(f"  👥 Similar tests ({dup['base_name']}):")
                for test in dup["tests"]:
                    status = "✅" if test["has_impl"] else "❌"
                    print(f"    {status} {test['file']}::{test['function']}")
    
    if analysis["obsolete"]:
        print(f"\n🗑️  OBSOLETE TESTS:")
        for obs in analysis["obsolete"]:
            print(f"  ❌ {obs['file']} ({obs['size']} lines)")
            for reason in obs["reasons"]:
                print(f"     {reason}")
    
    if analysis["redundant_coverage"]:
        print(f"\n📦 REDUNDANT COVERAGE:")
        for red in analysis["redundant_coverage"]:
            print(f"  🔄 {red['module']} ({red['unit_tests']} unit + {red['integration_tests']} integration)")
            print(f"     Files: {len(red['files'])} total")

def generate_cleanup_script(analysis: Dict[str, Any]) -> str:
    """Generate script to clean up redundant tests."""
    script_lines = [
        "#!/bin/bash",
        "# Test Suite Redundancy Cleanup Script",
        "# Generated automatically - review before executing",
        "",
        "set -e",
        "",
        "echo '🧹 Cleaning up redundant tests...'",
        ""
    ]
    
    # Remove obsolete files
    obsolete_files = analysis["obsolete"]
    if obsolete_files:
        script_lines.append("echo '🗑️  Removing obsolete test files...'")
        for obs in obsolete_files:
            file_path = f"tests/{obs['file']}"
            reasons = "; ".join(obs['reasons'][:2])  # First 2 reasons
            script_lines.append(f"rm -f '{file_path}'  # {reasons}")
        script_lines.append("")
    
    # Handle exact duplicates
    exact_dups = [d for d in analysis["duplicates"] if d["type"] == "exact_duplicate"]
    if exact_dups:
        script_lines.append("echo '🔄 Removing duplicate files (keeping first)...'")
        for dup in exact_dups:
            files = dup["files"]
            # Keep first file, remove others
            for file_to_remove in files[1:]:
                script_lines.append(f"rm -f 'tests/{file_to_remove}'  # Duplicate of {files[0]}")
        script_lines.append("")
    
    # Calculate duplicate count
    duplicate_count = sum(len(d["files"])-1 for d in exact_dups)
    
    script_lines.extend([
        "echo '✅ Redundancy cleanup completed!'",
        f"echo 'Removed {len(obsolete_files)} obsolete files'",
        f"echo 'Removed {duplicate_count} duplicate files'",
        ""
    ])
    
    return "\n".join(script_lines)

def main():
    """Main analysis function."""
    print("🚀 Starting Test Suite Redundancy Analysis")
    
    # Analyze test suite
    analysis = analyze_test_suite()
    
    # Print report
    print_redundancy_report(analysis)
    
    # Generate cleanup script
    cleanup_script = generate_cleanup_script(analysis)
    
    script_path = Path("scripts/testing/cleanup_redundant_tests.sh")
    script_path.write_text(cleanup_script)
    script_path.chmod(0o755)
    
    print(f"\n🔧 Generated cleanup script: {script_path}")
    print("Review the script before executing!")
    
    # Exit code based on findings
    total_issues = sum(analysis["summary"].values())
    return 0 if total_issues > 0 else 1

if __name__ == "__main__":
    sys.exit(main())