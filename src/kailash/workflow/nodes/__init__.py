# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Workflow-level node subpackages.

Each subpackage exposes a family of nodes that register themselves with
``kailash.nodes.base.NodeRegistry`` at import time, making them
addressable via the ``WorkflowBuilder.add_node("<NodeName>", ...)``
string-based API.

Subpackages:
  - ``kailash.workflow.nodes.ml`` — ML-lifecycle nodes (Training,
    Inference, RegistryPromote) per ``specs/kailash-core-ml-integration.md``
    §5. Requires ``pip install kailash[ml]`` for full functionality;
    the nodes register on import but raise a typed error at execute
    time if ``kailash-ml`` is not installed.
"""
