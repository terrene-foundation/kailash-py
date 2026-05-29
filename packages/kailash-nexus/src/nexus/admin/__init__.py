# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Nexus admin HTTP surfaces (privileged operator panels)."""

from nexus.admin.scheduler import register_scheduler_admin

__all__ = ["register_scheduler_admin"]
