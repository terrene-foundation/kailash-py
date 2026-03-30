# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Proxy module: kaizen.orchestration -> kaizen_agents.patterns

Registers sys.modules aliases so that mock.patch targets like
``kaizen.orchestration.patterns.blackboard.A2A_AVAILABLE``
resolve to the real kaizen_agents.patterns.patterns module.
"""

import sys

import kaizen_agents.patterns.patterns as _pp  # noqa: E402
import kaizen_agents.patterns.patterns.blackboard as _bb  # noqa: E402
import kaizen_agents.patterns.patterns.ensemble as _en  # noqa: E402
import kaizen_agents.patterns.patterns.meta_controller as _mc  # noqa: E402

sys.modules.setdefault("kaizen.orchestration.patterns", _pp)
sys.modules.setdefault("kaizen.orchestration.patterns.blackboard", _bb)
sys.modules.setdefault("kaizen.orchestration.patterns.ensemble", _en)
sys.modules.setdefault("kaizen.orchestration.patterns.meta_controller", _mc)
