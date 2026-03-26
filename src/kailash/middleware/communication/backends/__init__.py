# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
EventBus backend implementations.

Currently ships with:

* :class:`InMemoryEventBus` -- zero-dependency, thread-safe, suitable for
  single-process applications and tests.

Additional backends (Redis Streams, Kafka, etc.) can be added as separate
modules in this package.
"""

from .memory import InMemoryEventBus

__all__ = ["InMemoryEventBus"]
