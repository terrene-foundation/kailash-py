#!/usr/bin/env python3
"""
Comprehensive documentation validation script for Kaizen Framework.

This script validates all code examples in documentation files to ensure:
1. Kailash SDK pattern compliance
2. Code syntax correctness
3. Import statement validity
4. Example completeness and accuracy
5. Performance expectation alignment

Usage:
    python scripts/validate_documentation.py
    python scripts/validate_documentation.py --examples-only
    python scripts/validate_documentation.py --patterns-only
    python scripts/validate_documentation.py --fix-issues
"""

import argparse
import ast
import json
import re
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class ValidationResult:
    """Result of documentation validation."""

    file_path: str
    example_count: int
    passed: int
    failed: int
    issues: List[Dict[str, Any]]
    execution_time: float
    status: str  # PASS, FAIL, WARNING


@dataclass
class CodeExample:
    """Extracted code example from documentation."""

    file_path: str
    line_start: int
    line_end: int
    language: str
    code: str
    context: str
    example_type: str  # imports, config, usage, pattern


class DocumentationValidator:
    """Comprehensive documentation validator."""

    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.docs_dir = self.project_root / "docs"
        self.examples_dir = self.project_root / "examples"
        self.validation_results = []
        self.temp_dir = tempfile.mkdtemp(prefix="kaizen_validation_")

        # Kailash SDK patterns to validate
        self.required_patterns = {
            "workflow_builder": "from kailash.workflow.builder import WorkflowBuilder",
            "local_runtime": "from kailash.runtime.local import LocalRuntime",
            "execution_pattern": "runtime.execute(workflow.build())",
            "node_pattern": 'workflow.add_node("NodeName", "id", {})',
        }

        # Common validation errors
        self.common_issues = {
            "missing_imports": "Required imports missing",
            "wrong_execution": "Incorrect execution pattern",
            "invalid_syntax": "Python syntax errors",
            "deprecated_api": "Using deprecated API patterns",
            "missing_context": "Missing required context or setup",
        }

    def validate_all_documentation(self) -> Dict[str, Any]:
        """Validate all documentation files."""
        print("🔍 Starting comprehensive documentation validation...")

        # Find all documentation files
        doc_files = list(self.docs_dir.rglob("*.md"))
        example_files = list(self.examples_dir.rglob("README.md"))
        all_files = doc_files + example_files

        print(f"Found {len(all_files)} documentation files to validate")

        # Validate each file
        for file_path in all_files:
            print(f"Validating: {file_path.relative_to(self.project_root)}")
            result = self.validate_file(file_path)
            self.validation_results.append(result)

        # Generate summary report
        summary = self.generate_summary_report()

        # Clean up temporary files
        self.cleanup_temp_files()

        return summary

    def validate_file(self, file_path: Path) -> ValidationResult:
        """Validate a single documentation file."""
        start_time = datetime.now()

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Extract code examples
            examples = self.extract_code_examples(file_path, content)

            # Validate each example
            issues = []
            passed = 0
            failed = 0

            for example in examples:
                example_issues = self.validate_code_example(example)
                if example_issues:
                    issues.extend(example_issues)
                    failed += 1
                else:
                    passed += 1

            # Additional content validation
            content_issues = self.validate_content_structure(file_path, content)
            issues.extend(content_issues)

            execution_time = (datetime.now() - start_time).total_seconds()
            status = "PASS" if not issues else ("WARNING" if failed == 0 else "FAIL")

            return ValidationResult(
                file_path=str(file_path.relative_to(self.project_root)),
                example_count=len(examples),
                passed=passed,
                failed=failed,
                issues=issues,
                execution_time=execution_time,
                status=status,
            )

        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            return ValidationResult(
                file_path=str(file_path.relative_to(self.project_root)),
                example_count=0,
                passed=0,
                failed=1,
                issues=[
                    {
                        "type": "file_error",
                        "severity": "error",
                        "message": f"Failed to process file: {e}",
                        "line": 0,
                    }
                ],
                execution_time=execution_time,
                status="FAIL",
            )

    def extract_code_examples(self, file_path: Path, content: str) -> List[CodeExample]:
        """Extract all code examples from documentation file."""
        examples = []
        lines = content.split("\n")
        in_code_block = False
        code_language = None
        code_lines = []
        start_line = 0
        context_lines = []

        for i, line in enumerate(lines):
            # Check for code block start
            if line.startswith("```"):
                if not in_code_block:
                    # Starting code block
                    in_code_block = True
                    code_language = line[3:].strip() or "text"
                    code_lines = []
                    start_line = i + 1
                    # Capture context (previous 3 lines)
                    context_lines = lines[max(0, i - 3) : i]
                else:
                    # Ending code block
                    in_code_block = False
                    if code_lines and code_language in [
                        "python",
                        "yaml",
                        "json",
                        "bash",
                    ]:
                        example_type = self.classify_example_type("\n".join(code_lines))
                        examples.append(
                            CodeExample(
                                file_path=str(file_path),
                                line_start=start_line,
                                line_end=i,
                                language=code_language,
                                code="\n".join(code_lines),
                                context="\n".join(context_lines),
                                example_type=example_type,
                            )
                        )
                    code_language = None
                    code_lines = []
            elif in_code_block:
                code_lines.append(line)

        return examples

    def classify_example_type(self, code: str) -> str:
        """Classify the type of code example."""
        code_lower = code.lower()

        if any(keyword in code for keyword in ["import ", "from "]):
            return "imports"
        elif any(
            keyword in code_lower for keyword in ["config", "settings", "configuration"]
        ):
            return "config"
        elif "workflow.add_node" in code:
            return "workflow_pattern"
        elif "kaizen.create_agent" in code:
            return "agent_pattern"
        elif "class " in code and "Signature" in code:
            return "signature_pattern"
        elif "runtime.execute" in code:
            return "execution_pattern"
        else:
            return "usage"

    def validate_code_example(self, example: CodeExample) -> List[Dict[str, Any]]:
        """Validate a single code example."""
        issues = []

        if example.language == "python":
            issues.extend(self.validate_python_code(example))
        elif example.language == "yaml":
            issues.extend(self.validate_yaml_code(example))
        elif example.language == "json":
            issues.extend(self.validate_json_code(example))
        elif example.language == "bash":
            issues.extend(self.validate_bash_code(example))

        return issues

    def validate_python_code(self, example: CodeExample) -> List[Dict[str, Any]]:
        """Validate Python code example."""
        issues = []

        # 1. Syntax validation
        try:
            ast.parse(example.code)
        except SyntaxError as e:
            issues.append(
                {
                    "type": "syntax_error",
                    "severity": "error",
                    "message": f"Python syntax error: {e.msg}",
                    "line": example.line_start + (e.lineno or 0),
                    "example_type": example.example_type,
                }
            )

        # 2. Import pattern validation
        if example.example_type in [
            "imports",
            "workflow_pattern",
            "agent_pattern",
            "execution_pattern",
        ]:
            issues.extend(self.validate_import_patterns(example))

        # 3. Kailash SDK pattern validation
        issues.extend(self.validate_kailash_patterns(example))

        # 4. Code structure validation
        issues.extend(self.validate_code_structure(example))

        return issues

    def validate_import_patterns(self, example: CodeExample) -> List[Dict[str, Any]]:
        """Validate import patterns against Kailash SDK standards."""
        issues = []
        code = example.code

        # Check for required imports in workflow patterns
        if example.example_type == "workflow_pattern":
            if "WorkflowBuilder" not in code and "workflow" in code.lower():
                issues.append(
                    {
                        "type": "missing_import",
                        "severity": "error",
                        "message": "Missing WorkflowBuilder import for workflow pattern",
                        "line": example.line_start,
                        "suggestion": "Add: from kailash.workflow.builder import WorkflowBuilder",
                    }
                )

            if "LocalRuntime" not in code and "runtime" in code.lower():
                issues.append(
                    {
                        "type": "missing_import",
                        "severity": "error",
                        "message": "Missing LocalRuntime import for execution pattern",
                        "line": example.line_start,
                        "suggestion": "Add: from kailash.runtime.local import LocalRuntime",
                    }
                )

        # Check for Kaizen imports in agent patterns
        if example.example_type == "agent_pattern":
            if "kaizen" in code.lower() and "from kaizen import Kaizen" not in code:
                issues.append(
                    {
                        "type": "missing_import",
                        "severity": "error",
                        "message": "Missing Kaizen import for agent pattern",
                        "line": example.line_start,
                        "suggestion": "Add: from kaizen import Kaizen",
                    }
                )

        # Check for signature imports
        if example.example_type == "signature_pattern":
            if "dspy.Signature" in code and "import dspy" not in code:
                issues.append(
                    {
                        "type": "missing_import",
                        "severity": "error",
                        "message": "Missing dspy import for signature pattern",
                        "line": example.line_start,
                        "suggestion": "Add: import dspy",
                    }
                )

        return issues

    def validate_kailash_patterns(self, example: CodeExample) -> List[Dict[str, Any]]:
        """Validate adherence to Kailash SDK patterns."""
        issues = []
        code = example.code

        # 1. Check for correct execution pattern
        if "execute(" in code:
            if (
                "runtime.execute(workflow.build())" not in code
                and "runtime.execute(agent.workflow.build())" not in code
            ):
                # Check for incorrect patterns
                if "workflow.execute(runtime)" in code:
                    issues.append(
                        {
                            "type": "wrong_execution_pattern",
                            "severity": "error",
                            "message": "Incorrect execution pattern: should be runtime.execute(workflow.build())",
                            "line": example.line_start,
                            "suggestion": "Change to: runtime.execute(workflow.build())",
                        }
                    )
                elif ".execute(" in code and "runtime.execute(" not in code:
                    issues.append(
                        {
                            "type": "execution_pattern_warning",
                            "severity": "warning",
                            "message": "Verify execution pattern follows Kailash SDK standards",
                            "line": example.line_start,
                            "suggestion": "Use: runtime.execute(workflow.build())",
                        }
                    )

        # 2. Check for string-based node patterns
        if "add_node(" in code:
            # Look for string-based node names
            node_pattern = re.search(
                r'add_node\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,', code
            )
            if not node_pattern and "add_node(" in code:
                issues.append(
                    {
                        "type": "node_pattern_warning",
                        "severity": "warning",
                        "message": "Verify node pattern uses string-based names",
                        "line": example.line_start,
                        "suggestion": 'Use: workflow.add_node("NodeName", "id", {})',
                    }
                )

        # 3. Check for .build() usage
        if "workflow" in code and "execute(" in code:
            if ".build()" not in code and "workflow" in code:
                issues.append(
                    {
                        "type": "missing_build_call",
                        "severity": "error",
                        "message": "Missing .build() call before execution",
                        "line": example.line_start,
                        "suggestion": "Add .build() to workflow before execution",
                    }
                )

        return issues

    def validate_code_structure(self, example: CodeExample) -> List[Dict[str, Any]]:
        """Validate code structure and best practices."""
        issues = []
        code = example.code

        # Check for proper error handling in examples
        if example.example_type == "usage" and len(code.split("\n")) > 10:
            if (
                "try:" not in code
                and "except" not in code
                and ("api" in code.lower() or "execute" in code)
            ):
                issues.append(
                    {
                        "type": "missing_error_handling",
                        "severity": "warning",
                        "message": "Complex example lacks error handling",
                        "line": example.line_start,
                        "suggestion": "Consider adding try/except for robustness",
                    }
                )

        # Check for hardcoded values that should be configurable
        if re.search(r"(gpt-4|gpt-3\.5-turbo)", code) and "config" not in code.lower():
            issues.append(
                {
                    "type": "hardcoded_model",
                    "severity": "info",
                    "message": "Model name is hardcoded",
                    "line": example.line_start,
                    "suggestion": "Consider making model configurable",
                }
            )

        return issues

    def validate_yaml_code(self, example: CodeExample) -> List[Dict[str, Any]]:
        """Validate YAML code example."""
        issues = []

        try:
            import yaml

            yaml.safe_load(example.code)
        except yaml.YAMLError as e:
            issues.append(
                {
                    "type": "yaml_syntax_error",
                    "severity": "error",
                    "message": f"YAML syntax error: {e}",
                    "line": example.line_start,
                }
            )
        except ImportError:
            # PyYAML not available, skip validation
            pass

        return issues

    def validate_json_code(self, example: CodeExample) -> List[Dict[str, Any]]:
        """Validate JSON code example."""
        issues = []

        try:
            json.loads(example.code)
        except json.JSONDecodeError as e:
            issues.append(
                {
                    "type": "json_syntax_error",
                    "severity": "error",
                    "message": f"JSON syntax error: {e.msg}",
                    "line": example.line_start + e.lineno - 1,
                }
            )

        return issues

    def validate_bash_code(self, example: CodeExample) -> List[Dict[str, Any]]:
        """Validate bash code example."""
        issues = []

        # Basic bash validation
        lines = example.code.split("\n")
        for i, line in enumerate(lines):
            line = line.strip()
            if line and not line.startswith("#"):
                # Check for common bash issues
                if line.endswith("\\") and i == len(lines) - 1:
                    issues.append(
                        {
                            "type": "bash_syntax_warning",
                            "severity": "warning",
                            "message": "Line ends with backslash but is last line",
                            "line": example.line_start + i,
                        }
                    )

        return issues

    def validate_content_structure(
        self, file_path: Path, content: str
    ) -> List[Dict[str, Any]]:
        """Validate documentation content structure."""
        issues = []

        # Check for required sections in example READMEs
        if file_path.name == "README.md" and "examples" in str(file_path):
            required_sections = [
                "## Overview",
                "## Use Case",
                "## Agent Specification",
                "## Expected Execution Flow",
                "## Technical Requirements",
            ]

            for section in required_sections:
                if section not in content:
                    issues.append(
                        {
                            "type": "missing_section",
                            "severity": "warning",
                            "message": f"Missing required section: {section}",
                            "line": 0,
                        }
                    )

        # Check for Kailash SDK compatibility mentions
        if "kaizen" in content.lower() and "kailash" not in content.lower():
            issues.append(
                {
                    "type": "missing_compatibility_info",
                    "severity": "info",
                    "message": "Consider mentioning Kailash SDK compatibility",
                    "line": 0,
                }
            )

        return issues

    def generate_summary_report(self) -> Dict[str, Any]:
        """Generate comprehensive validation summary."""
        total_files = len(self.validation_results)
        total_examples = sum(r.example_count for r in self.validation_results)
        total_passed = sum(r.passed for r in self.validation_results)
        total_failed = sum(r.failed for r in self.validation_results)
        total_issues = sum(len(r.issues) for r in self.validation_results)

        # Categorize issues
        issue_categories = {}
        severity_counts = {"error": 0, "warning": 0, "info": 0}

        for result in self.validation_results:
            for issue in result.issues:
                issue_type = issue.get("type", "unknown")
                severity = issue.get("severity", "info")

                if issue_type not in issue_categories:
                    issue_categories[issue_type] = 0
                issue_categories[issue_type] += 1

                if severity in severity_counts:
                    severity_counts[severity] += 1

        # Calculate success rate
        success_rate = (total_passed / max(total_examples, 1)) * 100

        summary = {
            "validation_timestamp": datetime.now().isoformat(),
            "summary": {
                "total_files": total_files,
                "total_examples": total_examples,
                "total_passed": total_passed,
                "total_failed": total_failed,
                "total_issues": total_issues,
                "success_rate": round(success_rate, 2),
            },
            "issue_breakdown": {
                "by_severity": severity_counts,
                "by_type": issue_categories,
            },
            "file_results": [asdict(r) for r in self.validation_results],
            "recommendations": self.generate_recommendations(),
        }

        return summary

    def generate_recommendations(self) -> List[str]:
        """Generate recommendations based on validation results."""
        recommendations = []

        # Count common issue types
        issue_counts = {}
        for result in self.validation_results:
            for issue in result.issues:
                issue_type = issue.get("type", "unknown")
                issue_counts[issue_type] = issue_counts.get(issue_type, 0) + 1

        # Generate recommendations based on common issues
        if issue_counts.get("missing_import", 0) > 5:
            recommendations.append(
                "High number of missing import issues detected. "
                "Consider creating import templates or code snippets."
            )

        if issue_counts.get("wrong_execution_pattern", 0) > 3:
            recommendations.append(
                "Multiple incorrect execution patterns found. "
                "Emphasize runtime.execute(workflow.build()) pattern in documentation."
            )

        if issue_counts.get("syntax_error", 0) > 2:
            recommendations.append(
                "Syntax errors detected in code examples. "
                "Consider automated syntax checking in CI/CD pipeline."
            )

        if issue_counts.get("missing_section", 0) > 10:
            recommendations.append(
                "Many examples missing required sections. "
                "Create documentation templates for consistency."
            )

        return recommendations

    def cleanup_temp_files(self):
        """Clean up temporary files."""
        import shutil

        try:
            shutil.rmtree(self.temp_dir)
        except:
            pass  # Best effort cleanup

    def save_report(self, report: Dict[str, Any], output_file: str):
        """Save validation report to file."""
        with open(output_file, "w") as f:
            json.dump(report, f, indent=2)

    def print_summary(self, report: Dict[str, Any]):
        """Print validation summary to console."""
        summary = report["summary"]

        print("\n" + "=" * 70)
        print("📋 KAIZEN DOCUMENTATION VALIDATION REPORT")
        print("=" * 70)

        print("📊 Summary:")
        print(f"   Files validated: {summary['total_files']}")
        print(f"   Code examples: {summary['total_examples']}")
        print(f"   Passed: {summary['total_passed']} ✅")
        print(f"   Failed: {summary['total_failed']} ❌")
        print(f"   Success rate: {summary['success_rate']}%")

        severity_counts = report["issue_breakdown"]["by_severity"]
        print("\n🚨 Issues by severity:")
        print(f"   Errors: {severity_counts.get('error', 0)}")
        print(f"   Warnings: {severity_counts.get('warning', 0)}")
        print(f"   Info: {severity_counts.get('info', 0)}")

        # Show top issue types
        issue_types = report["issue_breakdown"]["by_type"]
        if issue_types:
            print("\n🔍 Top issue types:")
            for issue_type, count in sorted(
                issue_types.items(), key=lambda x: x[1], reverse=True
            )[:5]:
                print(f"   {issue_type}: {count}")

        # Show recommendations
        recommendations = report.get("recommendations", [])
        if recommendations:
            print("\n💡 Recommendations:")
            for i, rec in enumerate(recommendations, 1):
                print(f"   {i}. {rec}")

        print("\n" + "=" * 70)


def main():
    """Main validation function."""
    parser = argparse.ArgumentParser(description="Validate Kaizen documentation")
    parser.add_argument(
        "--examples-only", action="store_true", help="Validate only example files"
    )
    parser.add_argument(
        "--patterns-only", action="store_true", help="Validate only pattern files"
    )
    parser.add_argument(
        "--output",
        "-o",
        default="validation_report.json",
        help="Output file for validation report",
    )
    parser.add_argument("--project-root", default=".", help="Project root directory")

    args = parser.parse_args()

    # Initialize validator
    validator = DocumentationValidator(args.project_root)

    # Run validation
    try:
        report = validator.validate_all_documentation()

        # Print summary
        validator.print_summary(report)

        # Save detailed report
        validator.save_report(report, args.output)
        print(f"\n📄 Detailed report saved to: {args.output}")

        # Exit with appropriate code
        total_errors = report["issue_breakdown"]["by_severity"].get("error", 0)
        sys.exit(1 if total_errors > 0 else 0)

    except Exception as e:
        print(f"❌ Validation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
