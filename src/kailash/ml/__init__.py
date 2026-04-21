# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Kailash Core ML integration surface.

This is the kailash-core home for the ML-lifecycle contract:

- :mod:`kailash.ml.errors` — canonical :class:`MLError` hierarchy (shared by
  every wave package: kailash-ml, kailash-dataflow, kailash-nexus,
  kailash-kaizen, kailash-align, kailash-pact). The kailash-ml package
  re-exports this hierarchy via ``kailash_ml.errors`` with identity
  preservation so both import paths refer to the same classes.

The :mod:`kailash.ml` namespace is intentionally thin; kailash-ml owns the
engines, tracking, registry, serving, diagnostics, autolog, drift,
feature-store, automl, dashboard, and RL surfaces. This module's job is to
centralise the cross-package contracts that cannot live inside kailash-ml
without creating a dependency inversion.

See ``specs/kailash-core-ml-integration.md`` for the full contract.
"""
from __future__ import annotations

from kailash.ml import errors

__all__ = ["errors"]
