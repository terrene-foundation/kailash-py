#!/usr/bin/env python3
"""
Final Conservative Test Cleanup - Only True Redundancies

Target only files that are:
1. Actual empty test files (no test functions, minimal content)
2. Pure documentation disguised as tests (no pytest content)
3. Broken imports that can't be fixed
"""

import ast
import sys
from pathlib import Path
from typing import List, Dict, Set, Any

def is_actual_test_file(test_file: Path) -> Dict[str, Any]:
    """Determine if file is actually a test vs documentation."""
    try:
        content = test_file.read_text(encoding='utf-8')
        lines = content.splitlines()
        
        analysis = {
            "file": str(test_file.relative_to(Path("tests"))),
            "is_test": False,
            "is_empty": False,
            "is_documentation": False,
            "has_imports": False,
            "has_functions": False,
            "has_test_functions": False,
            "has_pytest": False,
            "size_lines": len(lines)
        }
        
        # Check for test-related content
        if "import pytest" in content or "@pytest" in content:
            analysis["has_pytest"] = True
        
        if "def test_" in content:
            analysis["has_test_functions"] = True
            
        if "def " in content:
            analysis["has_functions"] = True
            
        if "import " in content or "from " in content:
            analysis["has_imports"] = True
        
        # Classify file type
        if analysis["has_test_functions"] or analysis["has_pytest"]:
            analysis["is_test"] = True
        elif analysis["size_lines"] < 10 and not analysis["has_functions"]:
            analysis["is_empty"] = True
        elif not analysis["has_test_functions"] and analysis["has_functions"]:
            # Check if it's documentation pretending to be a test
            first_20_lines = content[:2000].lower()
            doc_keywords = ["analysis", "documentation", "components needed", "missing", "requirements"]
            if any(keyword in first_20_lines for keyword in doc_keywords):
                analysis["is_documentation"] = True
        
        return analysis
        
    except Exception as e:
        return {
            "file": str(test_file.relative_to(Path("tests"))),
            "error": str(e),
            "is_test": False
        }

def find_non_test_files() -> List[Dict[str, Any]]:
    """Find files in tests/ that aren't actually tests."""
    tests_dir = Path("tests")
    test_files = list(tests_dir.rglob("test_*.py")) + list(tests_dir.rglob("*_test.py"))
    
    non_tests = []
    for test_file in test_files:
        analysis = is_actual_test_file(test_file)
        
        # Only flag for removal if clearly not a test
        if (analysis["is_documentation"] or 
            analysis["is_empty"] or 
            (not analysis["is_test"] and not analysis["has_test_functions"] and analysis["size_lines"] > 50)):
            non_tests.append(analysis)
    
    return non_tests

def main():
    """Main analysis - very conservative."""
    print("🔍 Final Conservative Test File Analysis")
    print("=" * 50)
    
    non_tests = find_non_test_files()
    
    empty_files = [f for f in non_tests if f.get("is_empty")]
    doc_files = [f for f in non_tests if f.get("is_documentation")]
    
    print(f"\n📊 Analysis Results:")
    print(f"  📄 Documentation files disguised as tests: {len(doc_files)}")
    print(f"  📭 Empty/minimal files: {len(empty_files)}")
    print(f"  🗑️  Total safe to remove: {len(non_tests)}")
    
    if doc_files:
        print(f"\n📄 DOCUMENTATION FILES (should be moved, not deleted):")
        for doc in doc_files:
            print(f"  📄 {doc['file']} ({doc['size_lines']} lines)")
            print(f"     → Move to # contrib (removed)/architecture/ or docs/")
    
    if empty_files:
        print(f"\n📭 EMPTY FILES (safe to remove):")
        for empty in empty_files:
            print(f"  📭 {empty['file']} ({empty['size_lines']} lines)")
    
    # Generate very conservative cleanup
    if non_tests:
        total_lines = sum(f["size_lines"] for f in non_tests)
        print(f"\n💡 Total lines in non-test files: {total_lines}")
        
        # Only generate removal script for truly empty files
        removable = [f for f in non_tests if f.get("is_empty") or f["size_lines"] < 5]
        
        if removable:
            script_lines = [
                "#!/bin/bash",
                "# Final Conservative Test Cleanup - Only Empty Files",
                "",
                "set -e",
                "",
                "echo '🧹 Removing only truly empty test files...'",
                ""
            ]
            
            for removal in removable:
                file_path = f"tests/{removal['file']}"
                script_lines.append(f"rm -f '{file_path}'  # Empty file with {removal['size_lines']} lines")
            
            script_lines.extend([
                "",
                f"echo '✅ Removed {len(removable)} empty test files'",
                ""
            ])
            
            script_path = Path("scripts/testing/final_cleanup.sh")
            script_path.write_text("\n".join(script_lines))
            script_path.chmod(0o755)
            
            print(f"\n🔧 Generated final cleanup script: {script_path}")
        else:
            print(f"\n✅ No truly empty files found - test suite is already clean!")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())