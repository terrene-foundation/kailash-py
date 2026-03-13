#!/usr/bin/env python3
"""Clean duplicate lines from test files."""

import re
from pathlib import Path


def clean_duplicates(file_path):
    """Remove duplicate mock setup lines."""
    with open(file_path, "r") as f:
        lines = f.readlines()

    cleaned = []
    prev_line = ""
    skip_next = 0

    for i, line in enumerate(lines):
        if skip_next > 0:
            skip_next -= 1
            continue

        # Check for duplicate mock_connection setup
        if "mock_connection.execute = AsyncMock()" in line:
            # Check if the next few lines are duplicates
            if i + 3 < len(lines):
                if (
                    lines[i + 1].strip() == "mock_connection.fetch = AsyncMock()"
                    and lines[i + 2].strip() == "mock_connection.fetchrow = AsyncMock()"
                ):
                    # This is a duplicate block, skip it
                    skip_next = 2
                    continue

        # Check for duplicate mock_connection = Mock() followed by another block
        if line.strip() == "mock_connection.cursor = Mock()":
            # Check if next line starts another mock_connection setup
            if (
                i + 1 < len(lines)
                and "mock_connection.execute = AsyncMock()" in lines[i + 1]
            ):
                # Skip the duplicate block
                skip_next = 3
                cleaned.append(line)
                continue

        cleaned.append(line)

    with open(file_path, "w") as f:
        f.writelines(cleaned)

    return len(lines) - len(cleaned)


def main():
    """Clean duplicate lines from test files."""
    history_file = Path(
        ""
    )

    removed = clean_duplicates(history_file)
    print(f"Removed {removed} duplicate lines from {history_file.name}")

    return 0


if __name__ == "__main__":
    main()
