# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Fixture module that DELIBERATELY uses PEP 563 to trip the resolver gate.

``from __future__ import annotations`` turns every annotation in this module
into a string, so the resolver cannot tell the ``Request`` extractor from a
flat ``str``. ``Nexus.handler_extract`` MUST raise ``ExtractorPEP563Error`` at
registration when handed a handler defined here (spec §297-313).

This module is intentionally NOT a test module — it is imported by
``test_extractor_request_wiring.py`` to obtain a PEP-563-affected handler.
"""

from __future__ import annotations

from nexus.extractors import Request


async def pep563_handler(request: Request) -> dict:
    return {"host": request.headers.get("x-probe", "none")}
