"""
Root conftest.py — Auto-loads .env for ALL pytest sessions.

This ensures that environment variables (API keys, model names, database URLs)
are available in every test without manual setup. Works with any Kailash project.
"""

import os
from pathlib import Path


def pytest_configure(config):
    """Load .env at the very start of the pytest session."""
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        _load_env(env_path)


def _load_env(env_path: Path):
    """Parse .env and inject into os.environ (lightweight, no dependencies)."""
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Handle `export VAR=value` syntax
        if line.startswith("export "):
            line = line[7:].strip()
        eq = line.find("=")
        if eq == -1:
            continue
        key = line[:eq].strip()
        val = line[eq + 1 :].strip()
        # Strip surrounding quotes
        is_quoted = (val.startswith('"') and val.endswith('"') and len(val) >= 2) or (
            val.startswith("'") and val.endswith("'") and len(val) >= 2
        )
        if is_quoted:
            val = val[1:-1]
        else:
            # Strip inline comments for unquoted values (e.g. "value # comment")
            comment_idx = val.find(" #")
            if comment_idx > -1:
                val = val[:comment_idx].strip()
        # Only set if not already in environment (don't override explicit env)
        if key not in os.environ:
            os.environ[key] = val
