#!/usr/bin/env python3
"""
Comprehensive validation of all training material code examples.
Ensures wrong examples are still wrong and correct examples work with current SDK.
"""

import ast
import importlib.util
import re
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

try:
    from kailash.nodes.ai.llm_agent import LLMAgentNode
    from kailash.nodes.base import Node, NodeParameter
    from kailash.nodes.base_cycle_aware import CycleAwareNode
    from kailash.nodes.code.python import PythonCodeNode
    from kailash.nodes.data.readers import CSVReaderNode
    from kailash.nodes.data.sql import SQLDatabaseNode
    from kailash.nodes.logic.operations import SwitchNode
    from kailash.runtime.local import LocalRuntime
    from kailash.workflow.graph import Workflow
except ImportError as e:
    print(f"Failed to import Kailash modules: {e}")
    print("Make sure you're running from the project root and the SDK is installed.")
    sys.exit(1)


class TrainingExampleValidator:
    def __init__(self):
        self.training_dir = project_root / "contrib" / "training"
        self.results = {
            "files_processed": 0,
            "wrong_examples_validated": 0,
            "correct_examples_validated": 0,
            "wrong_examples_broken": [],  # Wrong examples that now work (bad!)
            "correct_examples_broken": [],  # Correct examples that don't work (bad!)
            "validation_errors": [],
            "files_with_issues": [],
        }

    def extract_code_examples(self, content: str, file_path: str) -> List[Dict]:
        """Extract wrong and correct code examples from markdown."""
        examples = []

        # Pattern to match ❌ Wrong: or ✅ Correct: examples
        pattern = r"(❌ Wrong:|✅ Correct:)[^\n]*\n```python\n(.*?)\n```"
        matches = re.findall(pattern, content, re.DOTALL)

        for marker, code in matches:
            is_wrong = "Wrong" in marker
            examples.append(
                {
                    "type": "wrong" if is_wrong else "correct",
                    "code": code.strip(),
                    "file": file_path,
                    "marker": marker.strip(),
                }
            )

        return examples

    def test_code_syntax(self, code: str) -> Tuple[bool, str]:
        """Test if code has valid Python syntax."""
        try:
            ast.parse(code)
            return True, ""
        except SyntaxError as e:
            return False, f"Syntax error: {e}"

    def test_code_execution(self, code: str, file_path: str) -> Tuple[bool, str]:
        """Test if code executes without errors."""
        try:
            # Create a safe execution environment
            exec_globals = {
                "__builtins__": __builtins__,
                "Node": Node,
                "NodeParameter": NodeParameter,
                "CycleAwareNode": CycleAwareNode,
                "PythonCodeNode": PythonCodeNode,
                "SwitchNode": SwitchNode,
                "LLMAgentNode": LLMAgentNode,
                "Workflow": Workflow,
                "LocalRuntime": LocalRuntime,
                "CSVReaderNode": CSVReaderNode,
                "SQLDatabaseNode": SQLDatabaseNode,
                "Dict": Dict,
                "List": List,
                "Any": Any,
                "datetime": __import__("datetime"),
                "json": __import__("json"),
                "os": __import__("os"),
                "Path": Path,
                # Add missing imports that many examples need
                "DataTransformer": Node,  # Placeholder
                "MergeNode": Node,  # Placeholder
                "logger": __import__("logging").getLogger(__name__),
                "workflow": Workflow(
                    "placeholder", "Placeholder"
                ),  # For incomplete examples
                "data": {"placeholder": "data"},  # For incomplete examples
            }

            exec(code, exec_globals)
            return True, ""
        except Exception as e:
            return False, f"Execution error: {str(e)}"

    def validate_example(self, example: Dict) -> Dict:
        """Validate a single code example."""
        code = example["code"]
        example_type = example["type"]

        # Test syntax first
        syntax_ok, syntax_error = self.test_code_syntax(code)

        # Test execution
        execution_ok, execution_error = self.test_code_execution(code, example["file"])

        result = {
            "example": example,
            "syntax_ok": syntax_ok,
            "syntax_error": syntax_error,
            "execution_ok": execution_ok,
            "execution_error": execution_error,
            "validation_status": "unknown",
        }

        # Determine validation status
        if example_type == "wrong":
            # Wrong examples should fail (either syntax or execution)
            if syntax_ok and execution_ok:
                result["validation_status"] = "BROKEN"  # Wrong example works (bad!)
                result["issue"] = "Wrong example now works - needs to be updated"
            else:
                result["validation_status"] = "VALID"  # Wrong example fails (good!)
        else:  # correct
            # Correct examples should work
            if syntax_ok and execution_ok:
                result["validation_status"] = "VALID"  # Correct example works (good!)
            else:
                result["validation_status"] = "BROKEN"  # Correct example fails (bad!)
                result["issue"] = (
                    f"Correct example broken: {syntax_error or execution_error}"
                )

        return result

    def process_file(self, file_path: Path) -> List[Dict]:
        """Process a single training file."""
        try:
            content = file_path.read_text(encoding="utf-8")
            examples = self.extract_code_examples(content, str(file_path))

            if not examples:
                return []

            print(f"\n📄 Processing: {file_path.relative_to(self.training_dir)}")
            print(f"   Found {len(examples)} code examples")

            results = []
            for example in examples:
                result = self.validate_example(example)
                results.append(result)

                # Print status
                status_emoji = "✅" if result["validation_status"] == "VALID" else "❌"
                example_type = example["type"].upper()
                print(
                    f"   {status_emoji} {example_type}: {result['validation_status']}"
                )

                if result["validation_status"] == "BROKEN":
                    print(f"      Issue: {result.get('issue', 'Unknown issue')}")

            return results

        except Exception as e:
            error = f"Failed to process {file_path}: {e}"
            self.results["validation_errors"].append(error)
            print(f"❌ {error}")
            return []

    def run_validation(self):
        """Run validation on all training files."""
        print("🧪 Validating All Training Material Code Examples")
        print("=" * 60)

        # Find all markdown files in training directory
        training_files = list(self.training_dir.rglob("*.md"))
        print(f"Found {len(training_files)} training files to process")

        all_results = []

        for file_path in training_files:
            try:
                file_results = self.process_file(file_path)
                all_results.extend(file_results)
                self.results["files_processed"] += 1

                # Track broken examples
                for result in file_results:
                    if result["validation_status"] == "BROKEN":
                        example_type = result["example"]["type"]
                        if example_type == "wrong":
                            self.results["wrong_examples_broken"].append(result)
                        else:
                            self.results["correct_examples_broken"].append(result)

                        if str(file_path) not in self.results["files_with_issues"]:
                            self.results["files_with_issues"].append(str(file_path))
                    else:
                        if result["example"]["type"] == "wrong":
                            self.results["wrong_examples_validated"] += 1
                        else:
                            self.results["correct_examples_validated"] += 1

            except KeyboardInterrupt:
                print("\n⚠️ Validation interrupted by user")
                break
            except Exception as e:
                error = f"Unexpected error processing {file_path}: {e}"
                self.results["validation_errors"].append(error)
                print(f"❌ {error}")

        self.print_summary()
        return all_results

    def print_summary(self):
        """Print validation summary."""
        print("\n" + "=" * 60)
        print("📊 Validation Summary")
        print("=" * 60)

        print(f"Files processed: {self.results['files_processed']}")
        print(f"Wrong examples validated: {self.results['wrong_examples_validated']}")
        print(
            f"Correct examples validated: {self.results['correct_examples_validated']}"
        )

        print("\n🚨 Issues Found:")
        print(
            f"Wrong examples now working: {len(self.results['wrong_examples_broken'])}"
        )
        print(
            f"Correct examples broken: {len(self.results['correct_examples_broken'])}"
        )
        print(f"Validation errors: {len(self.results['validation_errors'])}")

        # Detailed breakdown
        if self.results["wrong_examples_broken"]:
            print("\n❌ Wrong Examples That Now Work (Need Update):")
            for result in self.results["wrong_examples_broken"]:
                file_rel = Path(result["example"]["file"]).relative_to(
                    self.training_dir
                )
                print(f"   - {file_rel}: {result['example']['marker']}")

        if self.results["correct_examples_broken"]:
            print("\n❌ Correct Examples That Are Broken (Need Fix):")
            for result in self.results["correct_examples_broken"]:
                file_rel = Path(result["example"]["file"]).relative_to(
                    self.training_dir
                )
                print(f"   - {file_rel}: {result['example']['marker']}")
                print(f"     Error: {result.get('issue', 'Unknown')}")

        if self.results["validation_errors"]:
            print("\n⚠️ Validation Errors:")
            for error in self.results["validation_errors"]:
                print(f"   - {error}")

        # Success criteria
        total_issues = (
            len(self.results["wrong_examples_broken"])
            + len(self.results["correct_examples_broken"])
            + len(self.results["validation_errors"])
        )

        if total_issues == 0:
            print("\n🎉 All training examples are correctly validated!")
            print("✅ Wrong examples still fail as expected")
            print("✅ Correct examples work with current SDK")
        else:
            print(f"\n⚠️ Found {total_issues} issues that need attention")


def main():
    validator = TrainingExampleValidator()
    results = validator.run_validation()

    # Return exit code based on validation success
    total_issues = (
        len(validator.results["wrong_examples_broken"])
        + len(validator.results["correct_examples_broken"])
        + len(validator.results["validation_errors"])
    )

    return 0 if total_issues == 0 else 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
