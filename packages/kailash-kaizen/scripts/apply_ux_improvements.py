#!/usr/bin/env python3
"""
Apply UX Improvements to All Example Workflow Files

This script automatically updates example workflow files with the three UX improvements:
1. Config Auto-Extraction (GAP 1)
2. Shared Memory Convenience (GAP 2)
3. Result Parsing (GAP 3)

Usage:
    python scripts/apply_ux_improvements.py [--dry-run] [--file FILE]
"""

import re
from pathlib import Path
from typing import Tuple

# Files to update
REMAINING_FILES = [
    "examples/2-multi-agent/producer-consumer/workflow.py",
    "examples/2-multi-agent/shared-insights/workflow.py",
    "examples/2-multi-agent/supervisor-worker/workflow.py",
    "examples/3-enterprise-workflows/compliance-monitoring/workflow.py",
    "examples/3-enterprise-workflows/content-generation/workflow.py",
    "examples/3-enterprise-workflows/customer-service/workflow.py",
    "examples/3-enterprise-workflows/data-reporting/workflow.py",
    "examples/3-enterprise-workflows/document-analysis/workflow.py",
    "examples/4-advanced-rag/agentic-rag/workflow.py",
    "examples/4-advanced-rag/federated-rag/workflow.py",
    "examples/4-advanced-rag/graph-rag/workflow.py",
    "examples/4-advanced-rag/multi-hop-rag/workflow.py",
    "examples/4-advanced-rag/self-correcting-rag/workflow.py",
]


def apply_import_fix(content: str) -> Tuple[str, int]:
    """Remove BaseAgentConfig from imports."""
    changes = 0

    # Pattern 1: Same line import
    pattern1 = r"from kaizen\.core\.base_agent import BaseAgent, BaseAgentConfig"
    replacement1 = "from kaizen.core.base_agent import BaseAgent"
    if re.search(pattern1, content):
        content = re.sub(pattern1, replacement1, content)
        changes += 1

    # Pattern 2: Separate import line
    pattern2 = r"from kaizen\.core\.config import BaseAgentConfig\n"
    if re.search(pattern2, content):
        content = re.sub(pattern2, "", content)
        changes += 1

    return content, changes


def apply_config_auto_extraction(content: str) -> Tuple[str, int]:
    """Replace manual BaseAgentConfig construction with auto-extraction."""
    changes = 0

    # Pattern: agent_config = BaseAgentConfig(...) followed by super().__init__(config=agent_config, ...)
    pattern = r"(\s+)agent_config = BaseAgentConfig\(\s*\n.*?(?:llm_provider=config\.llm_provider|model=config\.model).*?\n.*?\)\s*\n\s*\n(\s+)super\(\).__init__\(\s*\n\s+config=agent_config,"

    def replacement(match):
        nonlocal changes
        changes += 1
        indent1 = match.group(1)
        indent2 = match.group(2)
        return f"{indent1}# UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!\n{indent2}super().__init__(\n{indent2}    config=config,  # Auto-extracted!"

    content = re.sub(pattern, replacement, content, flags=re.DOTALL)

    return content, changes


def apply_write_to_memory_convenience(content: str) -> Tuple[str, int]:
    """Replace verbose write_insight with write_to_memory."""
    changes = 0

    # Pattern: if self.shared_memory: self.shared_memory.write_insight({...})
    pattern = r'(\s+)if self\.shared_memory:\s*\n\s+self\.shared_memory\.write_insight\(\{\s*\n\s+"agent_id": self\.agent_id,\s*\n\s+"content": json\.dumps\(([^)]+)\),\s*\n\s+"tags": (\[[^\]]+\]),\s*\n\s+"importance": ([0-9.]+),\s*\n\s+"segment": "([^"]+)"\s*\n\s+\}\)'

    def replacement(match):
        nonlocal changes
        changes += 1
        indent = match.group(1)
        content_var = match.group(2)
        tags = match.group(3)
        importance = match.group(4)
        segment = match.group(5)

        return f'{indent}# UX Improvement: Concise shared memory write\n{indent}self.write_to_memory(\n{indent}    content={content_var},  # Auto-serialized\n{indent}    tags={tags},\n{indent}    importance={importance},\n{indent}    segment="{segment}"\n{indent})'

    content = re.sub(pattern, replacement, content, flags=re.DOTALL)

    return content, changes


def apply_result_parsing_helpers(content: str) -> Tuple[str, int]:
    """Replace manual JSON parsing with extract_* helpers."""
    changes = 0

    # Pattern for list extraction
    pattern_list = r'(\s+)(\w+)_raw = result\.get\("(\w+)", "\[\]"\)\s*\n\s+if isinstance\(\2_raw, str\):\s*\n\s+try:\s*\n\s+\2 = json\.loads\(\2_raw\) if \2_raw else \[\]\s*\n\s+except:\s*\n\s+\2 = \[\]\s*\n\s+else:\s*\n\s+\2 = \2_raw if isinstance\(\2_raw, list\) else \[\]'

    def replacement_list(match):
        nonlocal changes
        changes += 1
        indent = match.group(1)
        var_name = match.group(2)
        field_name = match.group(3)

        return f'{indent}# UX Improvement: One-line extraction\n{indent}{var_name} = self.extract_list(result, "{field_name}", default=[])'

    content = re.sub(pattern_list, replacement_list, content, flags=re.DOTALL)

    return content, changes


def process_file(file_path: Path, dry_run: bool = False) -> Tuple[int, str]:
    """Process a single file with all UX improvements."""
    if not file_path.exists():
        return 0, f"File not found: {file_path}"

    content = file_path.read_text()
    original_content = content
    total_changes = 0

    # Apply all improvements
    content, changes = apply_import_fix(content)
    total_changes += changes

    content, changes = apply_config_auto_extraction(content)
    total_changes += changes

    content, changes = apply_write_to_memory_convenience(content)
    total_changes += changes

    content, changes = apply_result_parsing_helpers(content)
    total_changes += changes

    if total_changes > 0:
        if not dry_run:
            file_path.write_text(content)
            return (
                total_changes,
                f"✅ Updated {file_path.name} ({total_changes} changes)",
            )
        else:
            return (
                total_changes,
                f"🔍 Would update {file_path.name} ({total_changes} changes)",
            )
    else:
        return 0, f"⏭️  No changes needed for {file_path.name}"


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Apply UX improvements to workflow files"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without modifying files",
    )
    parser.add_argument("--file", help="Update specific file only")
    args = parser.parse_args()

    # Get repository root
    script_path = Path(__file__).resolve()
    repo_root = script_path.parent.parent

    # Determine files to process
    if args.file:
        files = [Path(args.file)]
    else:
        files = [repo_root / f for f in REMAINING_FILES]

    print(f"{'DRY RUN - ' if args.dry_run else ''}Processing {len(files)} files...\n")

    total_changes = 0
    results = []

    for file_path in files:
        changes, message = process_file(file_path, dry_run=args.dry_run)
        total_changes += changes
        results.append(message)
        print(message)

    print(f"\n{'Summary (Dry Run):' if args.dry_run else 'Summary:'}")
    print(f"Total changes: {total_changes}")
    print(f"Files processed: {len(files)}")

    if args.dry_run:
        print("\nRun without --dry-run to apply changes.")
    else:
        print("\n✅ All updates complete!")
        print("\nNext steps:")
        print("1. Run tests: pytest tests/unit/examples/ -v")
        print("2. Verify examples still work correctly")


if __name__ == "__main__":
    main()
