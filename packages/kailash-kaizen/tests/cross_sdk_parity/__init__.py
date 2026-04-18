# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Cross-SDK parity tests for #498 Session 8 (S9).

These tests pin the contract surface that MUST remain byte-identical
between kailash-py and kailash-rs so code ported between the two SDKs
produces matching wire output.
"""
