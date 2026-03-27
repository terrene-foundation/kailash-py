# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Thread-safety test for runtime lifecycle ref counting.

Extracted from tests/unit/runtime/test_runtime_lifecycle.py because this test
spawns real OS threads for concurrent acquire/release, which violates the
Tier 1 contract (fast, isolated, deterministic). Belongs in Tier 2.
"""

from __future__ import annotations

import threading

from kailash.runtime.local import LocalRuntime


class TestRefCountingThreadSafety:
    """M1-001: Thread safety for reference counting in LocalRuntime."""

    def test_thread_safety(self):
        rt = LocalRuntime()
        errors = []

        def acquire_release():
            try:
                for _ in range(100):
                    rt.acquire()
                for _ in range(100):
                    rt.release()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=acquire_release) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert rt.ref_count == 1  # Only original ref remains
        rt.close()
