# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Conftest for tier_2 integration tests.

Loads .env before any test execution and adds the integration test
directory to sys.path so that `import models` works from test files.
"""

import sys
from pathlib import Path

from dotenv import load_dotenv

# .env is the single source of truth for API keys and configuration
load_dotenv()

# Add this directory to sys.path so `import models` resolves correctly
_this_dir = str(Path(__file__).parent)
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)
