# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Redis URL validation utility — re-export from kailash.utils.validation.

This module exists for backward compatibility and import convenience.
The canonical implementation lives in ``kailash.utils.validation``.
"""

from kailash.utils.validation import validate_redis_url

__all__ = ["validate_redis_url"]
