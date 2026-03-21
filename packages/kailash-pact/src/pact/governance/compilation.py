# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Organization compilation -- transforms OrgDefinition into address-indexed CompiledOrg.

Takes a declarative organization definition (departments, teams, roles, envelopes)
and compiles it into the runtime structures needed for address resolution,
envelope enforcement, clearance checks, and audit anchoring.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from pact.governance.addressing import AddressSegment, GrammarError, NodeType

if TYPE_CHECKING:
    from pact.build.config.schema import DepartmentConfig, TeamConfig
    from pact.build.org.builder import OrgDefinition

logger = logging.getLogger(__name__)

__all__ = [
    "CompilationError",
    "CompiledOrg",
    "MAX_CHILDREN_PER_NODE",
    "MAX_COMPILATION_DEPTH",
    "MAX_TOTAL_NODES",
    "OrgNode",
    "RoleDefinition",
    "VacancyStatus",
    "compile_org",
]

# ---------------------------------------------------------------------------
# Compilation limits (TODO-7008) -- prevent resource exhaustion attacks
# ---------------------------------------------------------------------------

MAX_COMPILATION_DEPTH: int = 50
"""Maximum address depth (number of segments) allowed during compilation."""

MAX_CHILDREN_PER_NODE: int = 500
"""Maximum number of direct children any single role may have."""

MAX_TOTAL_NODES: int = 100_000
"""Maximum total nodes allowed in a compiled organization."""


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class CompilationError(Exception):
    """Raised when organization compilation fails due to structural errors."""

    pass


# ---------------------------------------------------------------------------
# RoleDefinition (TODO-1002) -- dataclass, not Pydantic
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RoleDefinition:
    """A first-class Role node in the PACT organizational model.

    Roles are the accountability anchors -- positions occupied by people.
    Every Department or Team must have exactly one primary Role (head).

    frozen=True (TODO-7006 security fix): prevents post-construction mutation.
    The address field is set during compilation via object.__setattr__ to
    bypass frozen=True during the build phase. After compilation completes,
    the RoleDefinition is immutable.
    """

    role_id: str
    name: str
    reports_to_role_id: str | None = None
    is_primary_for_unit: str | None = None
    unit_id: str | None = None
    is_vacant: bool = False
    is_external: bool = False
    agent_id: str | None = None
    address: str | None = None


# ---------------------------------------------------------------------------
# VacancyStatus (TODO-1005)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VacancyStatus:
    """Vacancy status for a role at a given address.

    Attributes:
        address: The positional address of the role.
        role_id: The original role ID.
        is_vacant: Whether the role position is currently unoccupied.
        is_external: Whether this is an external governance-only role.
    """

    address: str
    role_id: str
    is_vacant: bool
    is_external: bool = False


# ---------------------------------------------------------------------------
# OrgNode (TODO-1003)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OrgNode:
    """A single node in the compiled organization tree.

    Every node has a positional address and a type (Department, Team, or Role).
    Role nodes carry a RoleDefinition reference; Department and Team nodes carry
    their respective config references.

    frozen=True (C2 security fix): prevents post-compilation mutation of
    organizational structure. During compilation, object.__setattr__ is used
    to build the node incrementally; afterward, the node is immutable.
    """

    address: str
    node_type: NodeType
    name: str
    node_id: str
    parent_address: str | None = None
    children_addresses: tuple[str, ...] = ()
    is_vacant: bool = False
    is_external: bool = False
    role_definition: RoleDefinition | None = None
    department: Any = None  # DepartmentConfig (avoid import cycle at runtime)
    team: Any = None  # TeamConfig (avoid import cycle at runtime)


# ---------------------------------------------------------------------------
# CompiledOrg (TODO-1003, 1004, 1005)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CompiledOrg:
    """The compiled form of an OrgDefinition -- all nodes indexed by address.

    Provides O(1) address lookup, prefix queries, subtree extraction,
    and vacancy status queries.

    frozen=True (C2 security fix): prevents post-compilation mutation of
    organizational structure. During compilation, object.__setattr__ is used
    to build the nodes dict; afterward, the CompiledOrg is immutable.

    TODO-7007: After compilation completes, the nodes dict is wrapped in
    MappingProxyType to prevent post-compilation insertion, deletion, or
    modification of nodes. Read operations (get, iterate, len, contains)
    still work normally.
    """

    org_id: str
    # Type is dict for static analysis. At runtime, compile_org() wraps this
    # in MappingProxyType via object.__setattr__ after the build phase completes.
    nodes: dict[str, OrgNode] = field(default_factory=dict)

    # ---- Node lookup ----

    def get_node(self, address: str) -> OrgNode:
        """Look up a node by its positional address.

        Args:
            address: A D/T/R positional address string.

        Returns:
            The OrgNode at that address.

        Raises:
            KeyError: If no node exists at the given address.
        """
        if address not in self.nodes:
            raise KeyError(
                f"No node at address '{address}'. "
                f"Available addresses: {sorted(self.nodes.keys())}"
            )
        return self.nodes[address]

    def get_node_by_role_id(self, role_id: str) -> OrgNode | None:
        """Find a node by its original role_id.

        Args:
            role_id: The role_id from the RoleDefinition.

        Returns:
            The OrgNode for that role, or None if not found.
        """
        for node in self.nodes.values():
            if node.role_definition is not None and node.role_definition.role_id == role_id:
                return node
        return None

    # ---- Query (TODO-1004) ----

    def query_by_prefix(self, prefix: str) -> list[OrgNode]:
        """Return all nodes whose address starts with the given prefix.

        Args:
            prefix: An address prefix (e.g., 'D1' or 'D1-R1-D2').

        Returns:
            List of OrgNode objects whose address starts with the prefix.
            Includes the node at the prefix address itself, if it exists.
        """
        results = []
        for addr, node in self.nodes.items():
            if addr == prefix or addr.startswith(prefix + "-"):
                results.append(node)
        return results

    def get_subtree(self, address: str) -> list[OrgNode]:
        """Return the node at address and all its descendants.

        Args:
            address: The root of the subtree.

        Returns:
            List of OrgNode objects including the root and all descendants.

        Raises:
            KeyError: If no node exists at the given address.
        """
        if address not in self.nodes:
            raise KeyError(
                f"No node at address '{address}' for subtree query. "
                f"Available addresses: {sorted(self.nodes.keys())}"
            )
        results = []
        for addr, node in self.nodes.items():
            if addr == address or addr.startswith(address + "-"):
                results.append(node)
        return results

    # ---- Root roles ----

    @property
    def root_roles(self) -> list[OrgNode]:
        """All root-level nodes (those with no parent_address).

        These are typically BOD members and top-level department nodes.
        """
        return [n for n in self.nodes.values() if n.parent_address is None]

    # ---- Vacancy (TODO-1005) ----

    def get_vacancy_status(self, address: str) -> VacancyStatus:
        """Get the vacancy status for a role at the given address.

        Args:
            address: The positional address to query.

        Returns:
            A VacancyStatus indicating whether the role is vacant.

        Raises:
            KeyError: If no node exists at the given address.
        """
        node = self.get_node(address)
        role_id = node.role_definition.role_id if node.role_definition else node.node_id
        return VacancyStatus(
            address=address,
            role_id=role_id,
            is_vacant=node.is_vacant,
            is_external=node.is_external,
        )


# ---------------------------------------------------------------------------
# compile_org() -- the main compilation function
# ---------------------------------------------------------------------------


def _append_child(node: OrgNode, child_address: str) -> None:
    """Append a child address to a frozen OrgNode during compilation.

    Uses object.__setattr__ to bypass frozen=True during the build phase.
    After compilation completes, no further mutations should occur.
    """
    object.__setattr__(
        node,
        "children_addresses",
        node.children_addresses + (child_address,),
    )


def compile_org(org: OrgDefinition) -> CompiledOrg:
    """Compile an OrgDefinition into a CompiledOrg with positional addresses.

    The compilation process:
    1. Validates all role references (no dangling, no duplicates, no cycles).
    2. Validates unit references (departments and teams exist).
    3. Builds a parent-child tree from reports_to_role_id chains.
    4. Assigns positional addresses via depth-first traversal.
    5. Creates OrgNode entries for departments, teams, and roles.

    Args:
        org: The OrgDefinition to compile.

    Returns:
        A CompiledOrg with all nodes indexed by address.

    Raises:
        CompilationError: If the org has structural errors (duplicate IDs,
            dangling references, cycles, etc.).
    """
    # Import here to avoid circular imports at module level
    from pact.build.config.schema import DepartmentConfig, TeamConfig

    roles: list[RoleDefinition] = getattr(org, "roles", [])

    # Short-circuit for empty orgs
    if not roles and not org.departments and not org.teams:
        empty = CompiledOrg(org_id=org.org_id)
        # TODO-7007: Wrap empty dict in MappingProxyType for consistency
        object.__setattr__(empty, "nodes", MappingProxyType(empty.nodes))
        return empty

    # --- Phase 1: Validate role definitions ---
    _validate_roles(roles, org)

    # --- Phase 2: Build indexes ---
    role_index: dict[str, RoleDefinition] = {r.role_id: r for r in roles}
    dept_index: dict[str, DepartmentConfig] = {d.department_id: d for d in org.departments}
    team_index: dict[str, TeamConfig] = {t.id: t for t in org.teams}

    # Map from unit_id -> role that heads it
    unit_head_map: dict[str, RoleDefinition] = {}
    for r in roles:
        if r.is_primary_for_unit:
            unit_head_map[r.is_primary_for_unit] = r

    # Build parent -> children role mapping
    children_of: dict[str | None, list[RoleDefinition]] = defaultdict(list)
    for r in roles:
        children_of[r.reports_to_role_id].append(r)

    # Preserve input order: children_of is populated in the order roles appear
    # in the OrgDefinition, which gives the user control over department/team
    # sequencing in positional addresses.

    # --- Phase 3: Assign addresses via depth-first traversal ---
    compiled = CompiledOrg(org_id=org.org_id)

    # Root roles are those with reports_to_role_id == None
    root_roles = children_of.get(None, [])

    # Separate root roles into categories:
    #   - External governance roles (BOD members) -- get R{n} addresses
    #   - Department-heading roles -- get D{n}-R1 addresses
    #   - Standalone roles -- get R{n} addresses
    role_counter = 0
    dept_counter = 0
    team_counter = 0

    for root_role in root_roles:
        unit_id = root_role.is_primary_for_unit

        if root_role.is_external:
            # External governance role (e.g., BOD) -- gets R{n} address
            role_counter += 1
            root_addr = f"R{role_counter}"
            _create_role_node(compiled, root_role, root_addr, parent_address=None)

            # Children of external roles that head departments get
            # TOP-LEVEL department addresses (D{n}-R1), not nested under R{n}.
            # This is because external roles exist above the operational hierarchy.
            _assign_children_of_external_root(
                compiled=compiled,
                parent_role=root_role,
                parent_role_addr=root_addr,
                children_of=children_of,
                role_index=role_index,
                dept_index=dept_index,
                team_index=team_index,
                unit_head_map=unit_head_map,
                dept_counter_start=dept_counter,
                team_counter_start=team_counter,
                role_counter_start=role_counter,
            )
            # Update counters based on what was emitted
            for addr in compiled.nodes:
                parts = addr.split("-")
                if len(parts) >= 1 and parts[0].startswith("D"):
                    try:
                        n = int(parts[0][1:])
                        dept_counter = max(dept_counter, n)
                    except ValueError:
                        pass

        elif unit_id and unit_id in dept_index:
            # Root role that heads a department
            dept_counter += 1
            dept_config = dept_index[unit_id]

            dept_addr = f"D{dept_counter}"
            dept_node = OrgNode(
                address=dept_addr,
                node_type=NodeType.DEPARTMENT,
                name=dept_config.name,
                node_id=dept_config.department_id,
                parent_address=None,
                department=dept_config,
            )
            compiled.nodes[dept_addr] = dept_node

            role_addr = f"{dept_addr}-R1"
            _create_role_node(compiled, root_role, role_addr, parent_address=dept_addr)
            _append_child(dept_node, role_addr)

            _assign_children_addresses(
                compiled=compiled,
                parent_role=root_role,
                parent_role_addr=role_addr,
                children_of=children_of,
                role_index=role_index,
                dept_index=dept_index,
                team_index=team_index,
                unit_head_map=unit_head_map,
            )

        elif unit_id and unit_id in team_index:
            # Root role that heads a team
            team_counter += 1
            team_config = team_index[unit_id]

            team_addr = f"T{team_counter}"
            team_node = OrgNode(
                address=team_addr,
                node_type=NodeType.TEAM,
                name=team_config.name,
                node_id=team_config.id,
                parent_address=None,
                team=team_config,
            )
            compiled.nodes[team_addr] = team_node

            role_addr = f"{team_addr}-R1"
            _create_role_node(compiled, root_role, role_addr, parent_address=team_addr)
            _append_child(team_node, role_addr)

            _assign_children_addresses(
                compiled=compiled,
                parent_role=root_role,
                parent_role_addr=role_addr,
                children_of=children_of,
                role_index=role_index,
                dept_index=dept_index,
                team_index=team_index,
                unit_head_map=unit_head_map,
            )

        else:
            # Standalone root role (no unit)
            role_counter += 1
            root_addr = f"R{role_counter}"
            _create_role_node(compiled, root_role, root_addr, parent_address=None)

            _assign_children_addresses(
                compiled=compiled,
                parent_role=root_role,
                parent_role_addr=root_addr,
                children_of=children_of,
                role_index=role_index,
                dept_index=dept_index,
                team_index=team_index,
                unit_head_map=unit_head_map,
            )

    # TODO-7007: Wrap nodes dict in MappingProxyType to make it read-only
    # post-compilation. This prevents insertion of malicious nodes after
    # the compilation phase completes.
    object.__setattr__(compiled, "nodes", MappingProxyType(compiled.nodes))

    return compiled


def _assign_children_of_external_root(
    compiled: CompiledOrg,
    parent_role: RoleDefinition,
    parent_role_addr: str,
    children_of: dict[str | None, list[RoleDefinition]],
    role_index: dict[str, RoleDefinition],
    dept_index: dict[str, Any],
    team_index: dict[str, Any],
    unit_head_map: dict[str, RoleDefinition],
    dept_counter_start: int,
    team_counter_start: int,
    role_counter_start: int,
) -> None:
    """Assign addresses to children of an external governance root role.

    External roles (BOD) sit above the operational hierarchy. Their children
    that head departments get TOP-LEVEL department addresses (D{n}-R1), not
    addresses nested under the external role.
    """
    children = children_of.get(parent_role.role_id, [])
    if not children:
        return

    # TODO-7008: Check breadth limit
    if len(children) > MAX_CHILDREN_PER_NODE:
        raise CompilationError(
            f"Role '{parent_role.role_id}' has {len(children)} children, "
            f"exceeding the maximum of {MAX_CHILDREN_PER_NODE}. "
            f"This may indicate a structural error or resource exhaustion attack."
        )

    dept_counter = dept_counter_start
    team_counter = team_counter_start
    role_counter = role_counter_start

    for child_role in children:
        unit_id = child_role.is_primary_for_unit

        if unit_id and unit_id in dept_index:
            dept_counter += 1
            dept_config = dept_index[unit_id]

            dept_addr = f"D{dept_counter}"
            dept_node = OrgNode(
                address=dept_addr,
                node_type=NodeType.DEPARTMENT,
                name=dept_config.name,
                node_id=dept_config.department_id,
                parent_address=parent_role_addr,
                department=dept_config,
            )
            compiled.nodes[dept_addr] = dept_node

            # Add as child of external root
            if parent_role_addr in compiled.nodes:
                _append_child(compiled.nodes[parent_role_addr], dept_addr)

            role_addr = f"{dept_addr}-R1"
            _create_role_node(compiled, child_role, role_addr, parent_address=dept_addr)
            _append_child(dept_node, role_addr)

            _assign_children_addresses(
                compiled=compiled,
                parent_role=child_role,
                parent_role_addr=role_addr,
                children_of=children_of,
                role_index=role_index,
                dept_index=dept_index,
                team_index=team_index,
                unit_head_map=unit_head_map,
            )

        elif unit_id and unit_id in team_index:
            team_counter += 1
            team_config = team_index[unit_id]

            team_addr = f"T{team_counter}"
            team_node = OrgNode(
                address=team_addr,
                node_type=NodeType.TEAM,
                name=team_config.name,
                node_id=team_config.id,
                parent_address=parent_role_addr,
                team=team_config,
            )
            compiled.nodes[team_addr] = team_node

            if parent_role_addr in compiled.nodes:
                _append_child(compiled.nodes[parent_role_addr], team_addr)

            role_addr = f"{team_addr}-R1"
            _create_role_node(compiled, child_role, role_addr, parent_address=team_addr)
            _append_child(team_node, role_addr)

            _assign_children_addresses(
                compiled=compiled,
                parent_role=child_role,
                parent_role_addr=role_addr,
                children_of=children_of,
                role_index=role_index,
                dept_index=dept_index,
                team_index=team_index,
                unit_head_map=unit_head_map,
            )

        else:
            role_counter += 1
            role_addr = f"R{role_counter}"
            _create_role_node(compiled, child_role, role_addr, parent_address=parent_role_addr)

            if parent_role_addr in compiled.nodes:
                _append_child(compiled.nodes[parent_role_addr], role_addr)

            _assign_children_addresses(
                compiled=compiled,
                parent_role=child_role,
                parent_role_addr=role_addr,
                children_of=children_of,
                role_index=role_index,
                dept_index=dept_index,
                team_index=team_index,
                unit_head_map=unit_head_map,
            )


def _assign_children_addresses(
    compiled: CompiledOrg,
    parent_role: RoleDefinition,
    parent_role_addr: str,
    children_of: dict[str | None, list[RoleDefinition]],
    role_index: dict[str, RoleDefinition],
    dept_index: dict[str, Any],
    team_index: dict[str, Any],
    unit_head_map: dict[str, RoleDefinition],
) -> None:
    """Recursively assign addresses to child roles of a parent.

    Children of a role can be:
    - Head roles of departments (D{n}-R{m}) => creates D node + R node
    - Head roles of teams (T{n}-R{m}) => creates T node + R node
    - Additional roles (R{n}) => creates R node directly

    Raises:
        CompilationError: If depth, breadth, or total node limits are exceeded.
    """
    children = children_of.get(parent_role.role_id, [])
    if not children:
        return

    # TODO-7008: Check depth limit — count segments in the parent address
    parent_depth = len(parent_role_addr.split("-"))
    # Children will be at least parent_depth + 1 (for R node) or +2 (for D/T + R)
    if parent_depth >= MAX_COMPILATION_DEPTH:
        raise CompilationError(
            f"Compilation depth limit exceeded at address '{parent_role_addr}' "
            f"(depth {parent_depth} >= {MAX_COMPILATION_DEPTH}). "
            f"This may indicate a circular structure or an excessively deep hierarchy."
        )

    # TODO-7008: Check breadth limit
    if len(children) > MAX_CHILDREN_PER_NODE:
        raise CompilationError(
            f"Role '{parent_role.role_id}' at address '{parent_role_addr}' has "
            f"{len(children)} children, exceeding the maximum of {MAX_CHILDREN_PER_NODE}. "
            f"This may indicate a structural error or resource exhaustion attack."
        )

    # TODO-7008: Check total nodes limit
    if len(compiled.nodes) > MAX_TOTAL_NODES:
        raise CompilationError(
            f"Total node count ({len(compiled.nodes)}) exceeds the maximum of "
            f"{MAX_TOTAL_NODES}. This may indicate a resource exhaustion attack."
        )

    # Track counters for each child type under this parent
    dept_counter = 0
    team_counter = 0
    role_counter = 0

    for child_role in children:
        unit_id = child_role.is_primary_for_unit

        if unit_id and unit_id in dept_index:
            # This child heads a department
            dept_counter += 1
            dept_config = dept_index[unit_id]

            # Create department node: parent_addr-D{n}
            dept_addr = f"{parent_role_addr}-D{dept_counter}"
            dept_node = OrgNode(
                address=dept_addr,
                node_type=NodeType.DEPARTMENT,
                name=dept_config.name,
                node_id=dept_config.department_id,
                parent_address=parent_role_addr,
                department=dept_config,
            )
            compiled.nodes[dept_addr] = dept_node

            # Add dept as child of parent role
            if parent_role_addr in compiled.nodes:
                _append_child(compiled.nodes[parent_role_addr], dept_addr)

            # Create head role node: parent_addr-D{n}-R1
            role_addr = f"{dept_addr}-R1"
            _create_role_node(compiled, child_role, role_addr, parent_address=dept_addr)

            # Add role as child of department
            _append_child(dept_node, role_addr)

            # Recurse into children of this role
            _assign_children_addresses(
                compiled=compiled,
                parent_role=child_role,
                parent_role_addr=role_addr,
                children_of=children_of,
                role_index=role_index,
                dept_index=dept_index,
                team_index=team_index,
                unit_head_map=unit_head_map,
            )

        elif unit_id and unit_id in team_index:
            # This child heads a team
            team_counter += 1
            team_config = team_index[unit_id]

            # Create team node: parent_addr-T{n}
            team_addr = f"{parent_role_addr}-T{team_counter}"
            team_node = OrgNode(
                address=team_addr,
                node_type=NodeType.TEAM,
                name=team_config.name,
                node_id=team_config.id,
                parent_address=parent_role_addr,
                team=team_config,
            )
            compiled.nodes[team_addr] = team_node

            # Add team as child of parent role
            if parent_role_addr in compiled.nodes:
                _append_child(compiled.nodes[parent_role_addr], team_addr)

            # Create head role node: parent_addr-T{n}-R1
            role_addr = f"{team_addr}-R1"
            _create_role_node(compiled, child_role, role_addr, parent_address=team_addr)

            # Add role as child of team
            _append_child(team_node, role_addr)

            # Recurse into children of this role
            _assign_children_addresses(
                compiled=compiled,
                parent_role=child_role,
                parent_role_addr=role_addr,
                children_of=children_of,
                role_index=role_index,
                dept_index=dept_index,
                team_index=team_index,
                unit_head_map=unit_head_map,
            )

        else:
            # Additional role (not a unit head)
            role_counter += 1
            role_addr = f"{parent_role_addr}-R{role_counter}"
            _create_role_node(compiled, child_role, role_addr, parent_address=parent_role_addr)

            # Add as child of parent role
            if parent_role_addr in compiled.nodes:
                _append_child(compiled.nodes[parent_role_addr], role_addr)

            # Recurse into children of this role
            _assign_children_addresses(
                compiled=compiled,
                parent_role=child_role,
                parent_role_addr=role_addr,
                children_of=children_of,
                role_index=role_index,
                dept_index=dept_index,
                team_index=team_index,
                unit_head_map=unit_head_map,
            )


def _create_role_node(
    compiled: CompiledOrg,
    role_def: RoleDefinition,
    address: str,
    parent_address: str | None,
) -> None:
    """Create an OrgNode for a role and add it to the compiled org."""
    # Set the address on the frozen RoleDefinition via object.__setattr__
    # (TODO-7006: RoleDefinition is now frozen=True)
    object.__setattr__(role_def, "address", address)

    node = OrgNode(
        address=address,
        node_type=NodeType.ROLE,
        name=role_def.name,
        node_id=role_def.role_id,
        parent_address=parent_address,
        is_vacant=role_def.is_vacant,
        is_external=role_def.is_external,
        role_definition=role_def,
    )
    compiled.nodes[address] = node


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _validate_roles(roles: list[RoleDefinition], org: Any) -> None:
    """Validate role definitions for structural correctness.

    Checks:
    - No duplicate role IDs
    - All reports_to_role_id references exist
    - No circular reports_to chains
    - All unit_id references exist as departments or teams

    Args:
        roles: The list of RoleDefinitions to validate.
        org: The OrgDefinition (for department/team lookup).

    Raises:
        CompilationError: If validation fails.
    """
    from pact.build.config.schema import DepartmentConfig, TeamConfig

    if not roles:
        return

    # Check duplicate role IDs
    seen_ids: set[str] = set()
    for r in roles:
        if r.role_id in seen_ids:
            raise CompilationError(
                f"Duplicate role ID: '{r.role_id}'. Each role must have a unique ID."
            )
        seen_ids.add(r.role_id)

    role_index = {r.role_id: r for r in roles}

    # Check reports_to references
    for r in roles:
        if r.reports_to_role_id is not None and r.reports_to_role_id not in role_index:
            raise CompilationError(
                f"Role '{r.role_id}' has reports_to_role_id='{r.reports_to_role_id}' "
                f"which was not found in the role definitions. "
                f"Available role IDs: {sorted(role_index.keys())}"
            )

    # Check for circular reports_to chains
    for r in roles:
        visited: set[str] = set()
        current = r.role_id
        while current is not None:
            if current in visited:
                raise CompilationError(
                    f"Circular reports_to chain detected involving role '{r.role_id}'. "
                    f"The chain visits '{current}' more than once."
                )
            visited.add(current)
            if current in role_index and role_index[current].reports_to_role_id is not None:
                current = role_index[current].reports_to_role_id
            else:
                break

    # Check unit_id references
    dept_ids = {d.department_id for d in org.departments}
    team_ids = {t.id for t in org.teams}
    all_unit_ids = dept_ids | team_ids

    for r in roles:
        if r.is_primary_for_unit is not None and r.is_primary_for_unit not in all_unit_ids:
            raise CompilationError(
                f"Role '{r.role_id}' references unit '{r.is_primary_for_unit}' "
                f"which was not found in departments or teams. "
                f"Available units: {sorted(all_unit_ids)}"
            )
        if r.unit_id is not None and r.unit_id not in all_unit_ids:
            raise CompilationError(
                f"Role '{r.role_id}' references unit_id '{r.unit_id}' "
                f"which was not found in departments or teams. "
                f"Available units: {sorted(all_unit_ids)}"
            )
