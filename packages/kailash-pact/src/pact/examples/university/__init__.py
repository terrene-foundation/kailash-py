# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""University example vertical -- demonstrates all PACT governance concepts.

This package contains a complete university organization that exercises:
- D/T/R positional addressing with 4+ levels of nesting
- Knowledge clearance independent of authority (IRB Director > Dean)
- Information barriers (Student Affairs vs Academic Affairs)
- Cross-Functional Bridges (Standing, Scoped)
- Knowledge Share Policies (one-way HR to Academic Affairs)
- Compartmentalized access (human-subjects, student-records, personnel)

The university domain was chosen because it requires ZERO domain expertise
to understand -- everyone has encountered academic organizational structures.

Modules:
    org         -- University D/T/R structure with compile_org()
    clearance   -- Clearance assignments demonstrating independence from authority
    barriers    -- Information barriers, bridges, and KSPs
    envelopes   -- Operating envelope assignments with monotonic tightening
    demo        -- Runnable script showing all 14 E2E scenarios
"""

from pact.examples.university.barriers import (
    create_university_bridges,
    create_university_ksps,
)
from pact.examples.university.clearance import create_university_clearances
from pact.examples.university.envelopes import create_university_envelopes
from pact.examples.university.org import create_university_org

__all__ = [
    "create_university_org",
    "create_university_clearances",
    "create_university_bridges",
    "create_university_ksps",
    "create_university_envelopes",
]
