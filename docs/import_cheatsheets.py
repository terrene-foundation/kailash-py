#!/usr/bin/env python3
"""
Import cheatsheets from sdk-users into Sphinx documentation.

This script demonstrates how to convert markdown cheatsheets into
properly formatted RST files for Sphinx documentation.
"""

import os
import re
from pathlib import Path
from typing import List, Tuple


def convert_markdown_to_rst(content: str) -> str:
    """Convert markdown content to RST format."""
    # Convert headers
    content = re.sub(r"^# (.+)$", r"\1\n" + "=" * 50, content, flags=re.MULTILINE)
    content = re.sub(r"^## (.+)$", r"\1\n" + "-" * 50, content, flags=re.MULTILINE)
    content = re.sub(r"^### (.+)$", r"\1\n" + "~" * 50, content, flags=re.MULTILINE)

    # Convert code blocks
    content = re.sub(
        r"```python\n(.*?)\n```",
        r".. code-block:: python\n\n\1",
        content,
        flags=re.DOTALL,
    )
    content = re.sub(
        r"```bash\n(.*?)\n```", r".. code-block:: bash\n\n\1", content, flags=re.DOTALL
    )
    content = re.sub(
        r"```yaml\n(.*?)\n```", r".. code-block:: yaml\n\n\1", content, flags=re.DOTALL
    )
    content = re.sub(
        r"```json\n(.*?)\n```", r".. code-block:: json\n\n\1", content, flags=re.DOTALL
    )

    # Indent code block content
    lines = content.split("\n")
    new_lines = []
    in_code_block = False

    for line in lines:
        if line.startswith(".. code-block::"):
            in_code_block = True
            new_lines.append(line)
            new_lines.append("")  # Empty line after directive
        elif in_code_block and line and not line.startswith(".. "):
            if not line.strip():
                new_lines.append("")
            else:
                new_lines.append("   " + line)  # Indent code content
        else:
            if in_code_block and not line.strip():
                in_code_block = False
            new_lines.append(line)

    content = "\n".join(new_lines)

    # Convert inline code
    content = re.sub(r"`([^`]+)`", r"``\1``", content)

    # Convert bold
    content = re.sub(r"\*\*([^*]+)\*\*", r"**\1**", content)

    # Convert italic
    content = re.sub(r"\*([^*]+)\*", r"*\1*", content)

    # Convert links
    content = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"`\1 <\2>`_", content)

    # Convert bullet lists (already RST compatible)
    # Convert numbered lists (already RST compatible)

    # Add proper spacing for RST
    content = re.sub(r"\n{3,}", "\n\n", content)

    return content


def get_cheatsheet_category(filename: str) -> str:
    """Determine category based on filename number."""
    try:
        num = int(filename[:3])
        if num < 20:
            return "core_patterns"
        elif num < 40:
            return "advanced_patterns"
        elif num < 50:
            return "enterprise_patterns"
        else:
            return "specialized_patterns"
    except:
        return "uncategorized"


def create_category_index(category: str, files: List[str]) -> str:
    """Create an index.rst file for a category."""
    title = category.replace("_", " ").title()
    underline = "=" * len(title)

    content = f"""{title}
{underline}

.. toctree::
   :maxdepth: 1
   :caption: Contents

"""

    for file in sorted(files):
        name = file.replace(".rst", "")
        content += f"   {name}\n"

    return content


def import_cheatsheets(source_dir: str, target_dir: str, limit: int = None):
    """Import cheatsheets from source to target directory."""
    source_path = Path(source_dir)
    target_path = Path(target_dir)

    # Create target directory structure
    categories = [
        "core_patterns",
        "advanced_patterns",
        "enterprise_patterns",
        "specialized_patterns",
    ]
    for category in categories:
        (target_path / category).mkdir(parents=True, exist_ok=True)

    # Track files by category
    files_by_category = {cat: [] for cat in categories}

    # Process cheatsheet files
    count = 0
    for md_file in sorted(source_path.glob("*.md")):
        if limit and count >= limit:
            break

        # Skip README files
        if md_file.name.lower() == "readme.md":
            continue

        print(f"Processing: {md_file.name}")

        # Read markdown content
        with open(md_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Convert to RST
        rst_content = convert_markdown_to_rst(content)

        # Add header with original filename reference
        header = f""".. meta::
   :description: {md_file.stem.replace('-', ' ').replace('_', ' ')}
   :keywords: kailash, workflow, {get_cheatsheet_category(md_file.name).replace('_', ' ')}

.. note::
   This cheatsheet was imported from ``sdk-users/2-core-concepts/cheatsheet/{md_file.name}``

"""
        rst_content = header + rst_content

        # Determine category and output file
        category = get_cheatsheet_category(md_file.name)
        rst_filename = md_file.stem + ".rst"
        output_path = target_path / category / rst_filename

        # Write RST file
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(rst_content)

        files_by_category[category].append(rst_filename)
        count += 1

    # Create category index files
    for category, files in files_by_category.items():
        if files:
            index_content = create_category_index(category, files)
            with open(target_path / category / "index.rst", "w") as f:
                f.write(index_content)

    # Create main cheatsheet index
    main_index = """Cheatsheets
===========

Quick reference patterns for common Kailash SDK tasks.

.. toctree::
   :maxdepth: 2
   :caption: Categories

   core_patterns/index
   advanced_patterns/index
   enterprise_patterns/index
   specialized_patterns/index

Overview
--------

This section contains 54+ cheatsheets covering everything from basic workflow
patterns to advanced enterprise features. Each cheatsheet provides:

- **Quick Examples**: Copy-paste code snippets
- **Best Practices**: Recommended patterns
- **Common Pitfalls**: What to avoid
- **Performance Tips**: Optimization hints

Navigation Tips
---------------

- **By Number**: Cheatsheets are numbered for easy reference (000-054+)
- **By Category**: Organized into core, advanced, enterprise, and specialized
- **By Feature**: Use search to find specific features
- **By Use Case**: Browse examples for your specific needs

.. note::
   All code examples in these cheatsheets are tested and production-ready.
   They follow the patterns established in the main CLAUDE.md guide.
"""

    with open(target_path / "index.rst", "w") as f:
        f.write(main_index)

    print(f"\nImported {count} cheatsheets successfully!")
    print(
        f"Created index files for {len([c for c, f in files_by_category.items() if f])} categories"
    )


def main():
    """Main entry point."""
    # Paths relative to docs directory
    source_dir = "../sdk-users/2-core-concepts/cheatsheet"
    target_dir = "quick_reference/cheatsheets"

    # Import first 10 cheatsheets as proof of concept
    print("Starting cheatsheet import (first 10 as proof of concept)...")
    import_cheatsheets(source_dir, target_dir, limit=10)

    print("\nNext steps:")
    print("1. Run 'make html' to build documentation")
    print("2. Check _build/html/quick_reference/cheatsheets/index.html")
    print("3. Remove limit to import all cheatsheets")
    print("4. Apply similar process to other documentation sections")


if __name__ == "__main__":
    main()
