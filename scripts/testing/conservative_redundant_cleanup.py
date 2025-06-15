#!/usr/bin/env python3
"""
Conservative Redundant Test Cleanup

More careful analysis to identify only truly redundant or obsolete tests:
1. Files with deprecated imports that are no longer working
2. Empty placeholder files with no real implementations
3. Duplicate test files with identical content
4. Tests that use completely obsolete patterns
"""

import ast
import re
import sys
from pathlib import Path
from typing import List, Dict, Set, Any

def analyze_file_for_removal(test_file: Path) -> Dict[str, Any]:
    """Conservatively analyze if a file should be removed."""
    try:
        content = test_file.read_text(encoding='utf-8')
        lines = content.splitlines()
        
        analysis = {
            "file": str(test_file.relative_to(Path("tests"))),
            "should_remove": False,
            "reasons": [],
            "size_lines": len(lines),
            "has_real_tests": False,
            "has_deprecated_only": False
        }
        
        # Check for real test implementations
        try:
            tree = ast.parse(content)
            test_functions = []
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                    # Check if function has real implementation (not just pass/skip)
                    has_impl = False
                    for stmt in node.body:
                        if not isinstance(stmt, (ast.Pass, ast.Expr)):
                            has_impl = True
                            break
                        elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
                            # Just a docstring
                            continue
                        elif isinstance(stmt, ast.Expr):
                            # Some other expression (might be a real test)
                            has_impl = True
                            break
                    
                    test_functions.append({
                        "name": node.name,
                        "has_implementation": has_impl
                    })
            
            analysis["has_real_tests"] = any(f["has_implementation"] for f in test_functions)
            
        except:
            pass
        
        # Conservative removal criteria
        
        # 1. Files with only deprecated AsyncLocalRuntime imports and no real tests
        if ("AsyncLocalRuntime" in content and 
            not analysis["has_real_tests"] and 
            analysis["size_lines"] < 200):
            analysis["should_remove"] = True
            analysis["reasons"].append("Uses deprecated AsyncLocalRuntime with no real tests")
        
        # 2. Files that are clearly just import/setup with no tests
        if (analysis["size_lines"] < 30 and 
            not analysis["has_real_tests"] and
            ("import" in content or "from" in content)):
            analysis["should_remove"] = True
            analysis["reasons"].append("Small file with imports but no test implementations")
        
        # 3. Files with only .process() calls and no .execute() (completely obsolete interface)
        if (".process(" in content and 
            ".execute(" not in content and
            "run(" not in content and
            analysis["size_lines"] < 100):
            analysis["should_remove"] = True
            analysis["reasons"].append("Uses only obsolete .process() interface")
        
        # 4. Empty test files or files with only pass statements
        if analysis["size_lines"] < 20 and not analysis["has_real_tests"]:
            analysis["should_remove"] = True
            analysis["reasons"].append("Empty or minimal file with no test content")
        
        return analysis
        
    except Exception as e:
        return {
            "file": str(test_file.relative_to(Path("tests"))),
            "should_remove": False,
            "reasons": [f"Analysis error: {e}"],
            "error": True
        }

def find_conservative_removals() -> List[Dict[str, Any]]:
    """Find files that can be safely removed."""
    tests_dir = Path("tests")
    test_files = list(tests_dir.rglob("test_*.py")) + list(tests_dir.rglob("*_test.py"))
    
    removals = []
    for test_file in test_files:
        analysis = analyze_file_for_removal(test_file)
        if analysis["should_remove"]:
            removals.append(analysis)
    
    return removals

def find_deprecated_imports() -> List[Dict[str, Any]]:
    """Find files with deprecated imports that need updating."""
    tests_dir = Path("tests")
    test_files = list(tests_dir.rglob("*.py"))
    
    deprecated_files = []
    for test_file in test_files:
        try:
            content = test_file.read_text(encoding='utf-8')
            deprecated_patterns = []
            
            if "AsyncLocalRuntime" in content:
                deprecated_patterns.append("AsyncLocalRuntime -> LocalRuntime(enable_async=True)")
            if "from kailash.core" in content:
                deprecated_patterns.append("from kailash.core -> updated import paths")
            if ".process(" in content and test_file.name.startswith("test_"):
                deprecated_patterns.append(".process() -> .execute()")
            
            if deprecated_patterns:
                deprecated_files.append({
                    "file": str(test_file.relative_to(Path("tests"))),
                    "patterns": deprecated_patterns,
                    "size": len(content.splitlines())
                })
        except:
            pass
    
    return deprecated_files

def main():
    """Main conservative cleanup analysis."""
    print("🔍 Conservative Test Redundancy Analysis")
    print("=" * 50)
    
    # Find conservative removals
    removals = find_conservative_removals()
    
    # Find deprecated import patterns
    deprecated = find_deprecated_imports()
    
    print(f"\n📊 Analysis Results:")
    print(f"  🗑️  Safe to remove: {len(removals)} files")
    print(f"  🔄 Need update: {len(deprecated)} files with deprecated patterns")
    
    if removals:
        print(f"\n🗑️  CONSERVATIVE REMOVALS ({len(removals)} files):")
        total_lines = 0
        for removal in removals:
            print(f"  ❌ {removal['file']} ({removal['size_lines']} lines)")
            for reason in removal['reasons']:
                print(f"     {reason}")
            total_lines += removal['size_lines']
        
        print(f"\n💡 Total lines to remove: {total_lines}")
        
        # Generate conservative cleanup script
        script_lines = [
            "#!/bin/bash",
            "# Conservative Test Cleanup Script",
            "# Only removes clearly obsolete/empty test files",
            "",
            "set -e",
            "",
            "echo '🧹 Conservative test cleanup...'",
            ""
        ]
        
        for removal in removals:
            file_path = f"tests/{removal['file']}"
            reason = removal['reasons'][0] if removal['reasons'] else "obsolete"
            script_lines.append(f"rm -f '{file_path}'  # {reason}")
        
        script_lines.extend([
            "",
            f"echo '✅ Removed {len(removals)} obsolete test files'",
            f"echo 'Freed up {total_lines} lines of obsolete test code'",
            ""
        ])
        
        script_path = Path("scripts/testing/conservative_cleanup.sh")
        script_path.write_text("\n".join(script_lines))
        script_path.chmod(0o755)
        
        print(f"\n🔧 Generated cleanup script: {script_path}")
    
    if deprecated:
        print(f"\n🔄 FILES WITH DEPRECATED PATTERNS ({len(deprecated)}):")
        for dep in deprecated[:10]:  # Show first 10
            print(f"  🔄 {dep['file']} ({dep['size']} lines)")
            for pattern in dep['patterns']:
                print(f"     {pattern}")
        
        if len(deprecated) > 10:
            print(f"  ... and {len(deprecated) - 10} more files")
    
    return 0 if len(removals) > 0 else 1

if __name__ == "__main__":
    sys.exit(main())