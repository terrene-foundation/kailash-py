# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#1720 offline legacy-vs-four-axis PARITY HARNESS.

Deterministic, offline (no network) proof that the four-axis
``kaizen.llm.LlmClient`` path is behaviour-equivalent to the legacy
``kaizen.providers.llm`` path across every wire and request/response
shape — the evidence that de-risks the Wave-3 consumer cutover WITHOUT a
live canary. See ``tests/parity/_harness.py`` for the plane definitions
and the SHARED-CANNED-BYTES injection contract.
"""
