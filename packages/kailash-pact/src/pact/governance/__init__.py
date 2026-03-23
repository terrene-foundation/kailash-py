# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""PACT governance primitives -- re-exported from kailash.trust.pact.

Governance primitives now live in kailash.trust.pact (kailash core).
This module re-exports them for kailash-pact internal use (api, cli, testing).
"""
from kailash.trust.pact import *  # noqa: F401,F403
from kailash.trust.pact import __all__  # noqa: F401
