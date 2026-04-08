# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Shared test fixtures for kailash-mcp."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
_project_root = Path(__file__).resolve().parents[3]
_env_file = _project_root / ".env"
if _env_file.exists():
    load_dotenv(str(_env_file))
