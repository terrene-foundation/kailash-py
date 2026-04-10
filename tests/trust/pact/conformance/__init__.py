# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""PACT N6 Cross-Implementation Conformance test suite.

Validates that PACT implementations produce deterministic, byte-identical
serialization of governance types. Test vectors in ``vectors/`` are
committed JSON files that both the Python and Rust SDKs validate against.
"""
