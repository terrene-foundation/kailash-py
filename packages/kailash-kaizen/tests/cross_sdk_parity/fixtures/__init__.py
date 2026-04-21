# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Cross-SDK parity fixtures -- hand-curated JSON snapshots of Rust SDK constants.

Refresh protocol: when kailash-rs changes a preset-registry entry, an
observability field name, or an error class, regenerate the corresponding
fixture file from Rust source (see each fixture file's docstring for the
exact Rust symbol path). These fixtures pin the contract both SDKs MUST
honor per EATP D6.
"""
