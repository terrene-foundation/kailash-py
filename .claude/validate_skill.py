#!/usr/bin/env python3
"""
Validate skill file compliance with systematic update guidelines.

Usage:
    python validate_skill.py path/to/skill.md
    python validate_skill.py --batch path/to/directory/
"""

import re
import sys
from pathlib import Path
from typing import List, Tuple


class SkillValidator:
    """Validates skill markdown files against update guidelines."""

    REQUIRED_SECTIONS = [
        "## Quick Reference",
        "## Core Pattern",
        "## Common Mistakes",
        "## Related Patterns",
        "## Documentation References",
    ]

    DEPRECATED_PATTERNS = [
        (
            r'workflow\.add_node\("[\w_]+",\s*\w+\(',
            "Instance-based node pattern (use string-based)",
        ),
        (r"workflow\.execute\(", "workflow.execute() (should be runtime.execute())"),
        (r"from\s+\.\.", "Relative imports (use absolute)"),
        (
            r"\.add_connection\([^,]+,\s*[^,]+,\s*[^)]+\)(?!\s*,)",
            "3-parameter connection (use 4 parameters)",
        ),
    ]

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.content = file_path.read_text()
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def validate(self) -> Tuple[List[str], List[str]]:
        """Run all validation checks. Returns (errors, warnings)."""
        self._check_frontmatter()
        self._check_metadata_block()
        self._check_required_sections()
        self._check_deprecated_patterns()
        self._check_execution_patterns()
        self._check_imports()
        self._check_trigger_keywords()
        self._check_code_blocks()
        self._check_links()

        return self.errors, self.warnings

    def _check_frontmatter(self):
        """Check YAML frontmatter exists."""
        if not self.content.startswith("---\n"):
            self.errors.append("Missing YAML frontmatter (---)")
            return

        # Check for name and description
        frontmatter_end = self.content.find("---", 4)
        if frontmatter_end == -1:
            self.errors.append("Unclosed YAML frontmatter")
            return

        frontmatter = self.content[4:frontmatter_end]
        if "name:" not in frontmatter:
            self.errors.append("Missing 'name:' in frontmatter")
        if "description:" not in frontmatter:
            self.errors.append("Missing 'description:' in frontmatter")

    def _check_metadata_block(self):
        """Check Skill Metadata block exists."""
        if "> **Skill Metadata**" not in self.content:
            self.errors.append("Missing '> **Skill Metadata**' block")
            return

        # Check metadata fields
        metadata_pattern = r"> \*\*Skill Metadata\*\*.*?(?=\n##|\n\n\n|\Z)"
        metadata_match = re.search(metadata_pattern, self.content, re.DOTALL)
        if not metadata_match:
            self.errors.append("Malformed Skill Metadata block")
            return

        metadata = metadata_match.group(0)
        if "> Category:" not in metadata:
            self.errors.append("Missing 'Category:' in metadata")
        if "> Priority:" not in metadata:
            self.errors.append("Missing 'Priority:' in metadata")
        if "> SDK Version:" not in metadata:
            self.errors.append("Missing 'SDK Version:' in metadata")

    def _check_required_sections(self):
        """Check all required sections exist."""
        for section in self.REQUIRED_SECTIONS:
            if section not in self.content:
                self.errors.append(f"Missing required section: {section}")

    def _check_deprecated_patterns(self):
        """Check for deprecated API patterns."""
        for pattern, description in self.DEPRECATED_PATTERNS:
            if re.search(pattern, self.content):
                self.errors.append(f"Found deprecated pattern: {description}")

    def _check_execution_patterns(self):
        """Check workflow execution patterns include .build()."""
        # Find all runtime.execute(...) calls
        exec_patterns = re.findall(r"runtime\.execute\([^)]+\)", self.content)

        for pattern in exec_patterns:
            # Skip if it's in a comment showing wrong way
            if ".build()" not in pattern:
                # Check if this is in a "wrong" example
                context_start = max(0, self.content.find(pattern) - 200)
                context_end = min(len(self.content), self.content.find(pattern) + 200)
                context = self.content[context_start:context_end]

                if "# ❌" not in context and "# Wrong" not in context:
                    self.errors.append(
                        f"Missing .build() in execution: {pattern[:50]}..."
                    )

    def _check_imports(self):
        """Check import patterns."""
        # Find code blocks with imports
        code_blocks = re.findall(r"```python\n(.*?)```", self.content, re.DOTALL)

        for block in code_blocks:
            # Check for relative imports (but ignore in wrong examples)
            if "from .." in block:
                # Get context to check if this is wrong example
                block_start = self.content.find(block)
                context = self.content[max(0, block_start - 100) : block_start]

                if "# ❌" not in context and "# Wrong" not in context:
                    self.errors.append("Found relative import in code example")

    def _check_trigger_keywords(self):
        """Check trigger keywords comment exists."""
        if "<!-- Trigger Keywords:" not in self.content:
            self.warnings.append("Missing trigger keywords comment at end of file")

    def _check_code_blocks(self):
        """Check code blocks for syntax issues."""
        code_blocks = re.findall(r"```python\n(.*?)```", self.content, re.DOTALL)

        for i, block in enumerate(code_blocks, 1):
            # Basic syntax checks
            if block.count('"""') % 2 != 0:
                self.warnings.append(f"Code block {i}: Unmatched triple quotes")

            if block.count("(") != block.count(")"):
                self.warnings.append(f"Code block {i}: Unmatched parentheses")

    def _check_links(self):
        """Check internal markdown links."""
        # Find all markdown links
        links = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", self.content)

        for link_text, link_url in links:
            # Skip external links
            if link_url.startswith(("http://", "https://", "#")):
                continue

            # Check if file exists (relative to skill file)
            if link_url.startswith("../"):
                link_path = self.file_path.parent / link_url
                if not link_path.exists():
                    self.warnings.append(f"Broken link: [{link_text}]({link_url})")


def validate_file(file_path: Path) -> bool:
    """Validate single file. Returns True if valid."""
    print(f"\n{'='*70}")
    try:
        display_path = file_path.relative_to(Path.cwd())
    except ValueError:
        display_path = file_path
    print(f"Validating: {display_path}")
    print("=" * 70)

    validator = SkillValidator(file_path)
    errors, warnings = validator.validate()

    if errors:
        print(f"\n❌ VALIDATION FAILED ({len(errors)} errors)")
        print("\nErrors:")
        for i, error in enumerate(errors, 1):
            print(f"  {i}. {error}")

    if warnings:
        print(f"\n⚠️  WARNINGS ({len(warnings)} warnings)")
        print("\nWarnings:")
        for i, warning in enumerate(warnings, 1):
            print(f"  {i}. {warning}")

    if not errors and not warnings:
        print("\n✅ VALIDATION PASSED")
        return True
    elif not errors:
        print("\n✅ VALIDATION PASSED (with warnings)")
        return True
    else:
        return False


def validate_directory(dir_path: Path) -> Tuple[int, int]:
    """Validate all .md files in directory. Returns (passed, total)."""
    md_files = list(dir_path.glob("*.md"))

    if not md_files:
        print(f"No .md files found in {dir_path}")
        return 0, 0

    print(f"\n{'='*70}")
    try:
        display_path = dir_path.relative_to(Path.cwd())
    except ValueError:
        display_path = dir_path
    print(f"Batch Validation: {display_path}")
    print(f"Files: {len(md_files)}")
    print("=" * 70)

    passed = 0
    for file_path in md_files:
        if validate_file(file_path):
            passed += 1

    print(f"\n{'='*70}")
    print(f"BATCH SUMMARY: {passed}/{len(md_files)} files passed")
    print("=" * 70)

    return passed, len(md_files)


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python validate_skill.py path/to/skill.md")
        print("  python validate_skill.py --batch path/to/directory/")
        sys.exit(1)

    if sys.argv[1] == "--batch":
        if len(sys.argv) < 3:
            print("Error: --batch requires directory path")
            sys.exit(1)

        dir_path = Path(sys.argv[2])
        if not dir_path.is_dir():
            print(f"Error: {dir_path} is not a directory")
            sys.exit(1)

        passed, total = validate_directory(dir_path)
        if passed < total:
            sys.exit(1)
    else:
        file_path = Path(sys.argv[1])
        if not file_path.exists():
            print(f"Error: {file_path} does not exist")
            sys.exit(1)

        if not validate_file(file_path):
            sys.exit(1)


if __name__ == "__main__":
    main()
