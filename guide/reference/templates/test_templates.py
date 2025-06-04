#!/usr/bin/env python3
"""
Test script to validate template structure and imports.
This doesn't run the workflows but checks they can be imported.
"""

import os
import sys
import importlib.util
from pathlib import Path


def test_template(template_path):
    """Test if a template can be imported without errors."""
    try:
        spec = importlib.util.spec_from_file_location("template", template_path)
        module = importlib.util.module_from_spec(spec)

        # This loads the module but doesn't execute the __main__ block
        spec.loader.exec_module(module)

        print(f"✓ {template_path.name} - imports successfully")
        return True

    except Exception as e:
        print(f"✗ {template_path.name} - import failed: {e}")
        return False


def main():
    """Test all templates."""
    templates_dir = Path(__file__).parent

    print("Testing Kailash SDK Templates")
    print("=" * 40)

    # Find all Python files
    template_files = []
    for root, dirs, files in os.walk(templates_dir):
        for file in files:
            if file.endswith(".py") and file != "test_templates.py":
                template_files.append(Path(root) / file)

    # Test each template
    passed = 0
    total = len(template_files)

    for template_path in sorted(template_files):
        if test_template(template_path):
            passed += 1

    print("\n" + "=" * 40)
    print(f"Results: {passed}/{total} templates passed")

    if passed == total:
        print("All templates are valid!")
        return 0
    else:
        print(f"{total - passed} templates have issues")
        return 1


if __name__ == "__main__":
    exit(main())
