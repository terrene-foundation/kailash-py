#!/usr/bin/env python3
# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Generate SHA-256 hash index for cross-SDK test vectors.

Per SPEC-09 S8.1, produces ``VECTORS.sha256`` in the test vectors
directory. The format is ``<sha256hex>  <relative-path>`` sorted by
path. This script is idempotent -- running it twice produces the same
output.

Usage:
    python scripts/generate-vector-hashes.py
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

VECTOR_ROOT = Path(__file__).parent.parent / "tests" / "fixtures" / "cross-sdk"
OUTPUT_FILE = VECTOR_ROOT / "VECTORS.sha256"


def generate_hashes() -> list[str]:
    """Compute SHA-256 hashes for all JSON files under the vector root."""
    entries: list[str] = []

    for json_file in sorted(VECTOR_ROOT.rglob("*.json")):
        rel_path = json_file.relative_to(VECTOR_ROOT)
        file_hash = hashlib.sha256(json_file.read_bytes()).hexdigest()
        entries.append(f"{file_hash}  {rel_path}")

    return entries


def main() -> int:
    """Generate and write the VECTORS.sha256 index file."""
    entries = generate_hashes()

    if not entries:
        print("No JSON vector files found under", VECTOR_ROOT, file=sys.stderr)
        return 1

    content = "\n".join(entries) + "\n"
    OUTPUT_FILE.write_text(content)
    print(f"Generated {OUTPUT_FILE} with {len(entries)} entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
