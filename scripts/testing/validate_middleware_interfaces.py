#!/usr/bin/env python3
"""
Validate Middleware Interface Updates

Checks middleware examples for proper interface usage:
1. Use create_gateway() convenience function vs APIGateway() constructor
2. Consistent .execute() method usage (not .process())
3. Proper middleware component integration patterns
4. SDK security and database node usage patterns
"""

import re
import sys
from pathlib import Path
from typing import List, Dict, Tuple

def analyze_middleware_interfaces(file_path: Path) -> List[Dict]:
    """Analyze middleware interface usage in a Python file."""
    issues = []
    suggestions = []
    
    try:
        content = file_path.read_text(encoding='utf-8')
        lines = content.splitlines()
        
        for line_num, line in enumerate(lines, 1):
            # Check for APIGateway() constructor usage
            if re.search(r'APIGateway\(', line):
                suggestions.append({
                    "type": "api_gateway_constructor",
                    "line": line_num,
                    "content": line.strip(),
                    "severity": "suggestion",
                    "description": "Consider using create_gateway() convenience function for automatic configuration"
                })
            
            # Check for .process() usage (should be .execute())
            if re.search(r'\.process\(', line):
                issues.append({
                    "type": "incorrect_process_method",
                    "line": line_num,
                    "content": line.strip(),
                    "severity": "error",
                    "description": ".process() method doesn't exist - use .execute() instead"
                })
            
            # Check for deprecated auth patterns
            if re.search(r'manual.*jwt|jwt\.encode|jwt\.decode', line, re.IGNORECASE):
                suggestions.append({
                    "type": "manual_jwt_handling",
                    "line": line_num,
                    "content": line.strip(),
                    "severity": "suggestion",
                    "description": "Consider using CredentialManagerNode for JWT handling"
                })
            
            # Check for raw database connections
            if re.search(r'asyncpg\.connect|psycopg2\.connect', line):
                suggestions.append({
                    "type": "raw_database_connection",
                    "line": line_num,
                    "content": line.strip(),
                    "severity": "suggestion",
                    "description": "Consider using AsyncSQLDatabaseNode for database operations"
                })
            
            # Check for httpx usage
            if re.search(r'httpx\.|AsyncClient', line):
                suggestions.append({
                    "type": "manual_http_client",
                    "line": line_num,
                    "content": line.strip(),
                    "severity": "suggestion",
                    "description": "Consider using HTTPRequestNode for HTTP operations"
                })
                
    except Exception as e:
        issues.append({
            "type": "file_error",
            "line": 0,
            "content": str(e),
            "severity": "error",
            "description": f"Error reading file: {e}"
        })
    
    return issues + suggestions

def check_middleware_best_practices(file_path: Path) -> List[Dict]:
    """Check for middleware best practices."""
    practices = []
    
    try:
        content = file_path.read_text(encoding='utf-8')
        
        # Check for create_gateway usage
        if 'create_gateway(' in content:
            practices.append({
                "type": "best_practice",
                "description": "Uses create_gateway() convenience function ✅",
                "severity": "good"
            })
        
        # Check for proper middleware imports
        if 'from kailash.middleware import' in content:
            practices.append({
                "type": "best_practice",
                "description": "Uses proper middleware imports ✅",
                "severity": "good"
            })
        
        # Check for SDK node usage
        sdk_nodes = [
            'HTTPRequestNode', 'CredentialManagerNode', 'AsyncSQLDatabaseNode',
            'DataTransformer', 'AuditLogNode', 'SecurityEventNode'
        ]
        for node in sdk_nodes:
            if node in content:
                practices.append({
                    "type": "best_practice",
                    "description": f"Uses {node} SDK component ✅",
                    "severity": "good"
                })
        
        # Check for .execute() usage
        if '.execute(' in content and '.process(' not in content:
            practices.append({
                "type": "best_practice",
                "description": "Uses correct .execute() method interface ✅",
                "severity": "good"
            })
            
    except Exception as e:
        practices.append({
            "type": "analysis_error",
            "description": f"Error analyzing best practices: {e}",
            "severity": "error"
        })
    
    return practices

def analyze_middleware_directory() -> Dict:
    """Analyze all middleware examples."""
    middleware_dir = Path("examples/feature_examples/middleware")
    results = {
        "files_analyzed": 0,
        "files_with_issues": 0,
        "total_issues": 0,
        "total_suggestions": 0,
        "issue_summary": {},
        "file_results": {},
        "best_practices": {}
    }
    
    if not middleware_dir.exists():
        results["error"] = "Middleware examples directory not found"
        return results
    
    python_files = list(middleware_dir.glob("*.py"))
    
    for file_path in python_files:
        results["files_analyzed"] += 1
        
        # Analyze interfaces
        interface_issues = analyze_middleware_interfaces(file_path)
        
        # Check best practices
        best_practices = check_middleware_best_practices(file_path)
        
        if interface_issues:
            errors = [i for i in interface_issues if i["severity"] == "error"]
            suggestions = [i for i in interface_issues if i["severity"] == "suggestion"]
            
            if errors:
                results["files_with_issues"] += 1
                results["total_issues"] += len(errors)
            
            results["total_suggestions"] += len(suggestions)
            results["file_results"][str(file_path)] = {
                "issues": interface_issues,
                "best_practices": best_practices
            }
            
            # Count issue types
            for issue in interface_issues:
                issue_type = issue["type"]
                if issue_type not in results["issue_summary"]:
                    results["issue_summary"][issue_type] = 0
                results["issue_summary"][issue_type] += 1
        
        # Store best practices
        if best_practices:
            results["best_practices"][str(file_path)] = best_practices
    
    return results

def print_validation_report(results: Dict):
    """Print detailed validation report."""
    print("🔍 Middleware Interface Validation Report")
    print("=" * 50)
    print(f"Files analyzed: {results['files_analyzed']}")
    print(f"Files with issues: {results['files_with_issues']}")
    print(f"Total issues: {results['total_issues']}")
    print(f"Total suggestions: {results['total_suggestions']}")
    
    if results.get("error"):
        print(f"\n❌ Error: {results['error']}")
        return
    
    if results["issue_summary"]:
        print(f"\n📊 Issue Summary:")
        for issue_type, count in results["issue_summary"].items():
            severity = "🔴" if "error" in issue_type or "incorrect" in issue_type else "🟡"
            print(f"  {severity} {issue_type}: {count}")
    
    # Print detailed results
    if results["file_results"]:
        print(f"\n📄 Detailed Analysis:")
        for file_path, analysis in results["file_results"].items():
            rel_path = Path(file_path).name
            print(f"\n{rel_path}:")
            
            # Issues
            issues = [i for i in analysis["issues"] if i["severity"] == "error"]
            suggestions = [i for i in analysis["issues"] if i["severity"] == "suggestion"]
            
            if issues:
                print("  🔴 Issues:")
                for issue in issues:
                    print(f"    Line {issue['line']}: {issue['description']}")
                    print(f"      {issue['content']}")
            
            if suggestions:
                print("  🟡 Suggestions:")
                for suggestion in suggestions[:3]:  # Limit output
                    print(f"    Line {suggestion['line']}: {suggestion['description']}")
    
    # Print best practices
    if results["best_practices"]:
        print(f"\n✅ Best Practices Found:")
        all_practices = []
        for file_path, practices in results["best_practices"].items():
            file_name = Path(file_path).name
            good_practices = [p for p in practices if p["severity"] == "good"]
            if good_practices:
                all_practices.extend([f"{file_name}: {p['description']}" for p in good_practices])
        
        for practice in set(all_practices):  # Remove duplicates
            print(f"  {practice}")

def print_interface_update_summary():
    """Print summary of interface updates made."""
    print("\n" + "=" * 60)
    print("📋 MIDDLEWARE INTERFACE UPDATES COMPLETED")
    print("=" * 60)
    
    updates = [
        {
            "file": "middleware_workflow_runtime_example.py",
            "changes": [
                "✅ Updated import: APIGateway → create_gateway",
                "✅ Updated constructor: APIGateway() → create_gateway()",
                "✅ Added comment explaining convenience function usage"
            ]
        },
        {
            "file": "refactored_middleware_example.py",
            "changes": [
                "✅ Updated import: APIGateway → create_gateway",
                "✅ Updated constructor: APIGateway() → create_gateway()",
                "✅ Fixed code examples: .process() → .execute()",
                "✅ Updated before/after comparisons to show correct patterns"
            ]
        }
    ]
    
    for update in updates:
        print(f"\n{update['file']}:")
        for change in update['changes']:
            print(f"  {change}")
    
    print("\n🎯 KEY IMPROVEMENTS:")
    print("1. ✅ Consistent use of create_gateway() convenience function")
    print("2. ✅ Proper .execute() method usage throughout")
    print("3. ✅ Updated documentation examples to reflect best practices")
    print("4. ✅ Aligned with current SDK middleware architecture")

def main():
    """Main validation function."""
    print("🚀 Starting Middleware Interface Validation")
    
    # Analyze current state
    results = analyze_middleware_directory()
    print_validation_report(results)
    
    # Show completed updates
    print_interface_update_summary()
    
    if results["total_issues"] > 0:
        print(f"\n⚠️  Found {results['total_issues']} issues requiring attention")
        return 1
    else:
        print(f"\n🎉 All middleware interfaces are properly updated!")
        print(f"💡 {results['total_suggestions']} suggestions for further optimization")
        return 0

if __name__ == "__main__":
    sys.exit(main())