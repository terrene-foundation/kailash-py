"""
Unit tests for interrupt propagation (TODO-169 Day 3).

Tests interrupt propagation from parent to child agents for multi-agent scenarios.

Test Strategy: Tier 1 (Unit) - Real InterruptManager instances (NO MOCKING)
Coverage: 5 tests for Day 3 acceptance criteria
"""

from kaizen.core.autonomy.interrupts.manager import InterruptManager
from kaizen.core.autonomy.interrupts.types import InterruptMode, InterruptSource
from kaizen.signatures import InputField, OutputField, Signature


class TaskSignature(Signature):
    """Simple signature for testing"""

    task: str = InputField(description="Task to perform")
    result: str = OutputField(description="Result")


# ═══════════════════════════════════════════════════════════════
# Test: Interrupt Propagation Setup (2 tests)
# ═══════════════════════════════════════════════════════════════


def test_child_manager_tracking():
    """
    Test that parent agent can track child interrupt managers.

    Validates:
    - add_child_manager() adds child to tracking list
    - Multiple children can be tracked
    - Child managers are stored correctly
    """
    # Arrange
    parent_manager = InterruptManager()
    child_manager_1 = InterruptManager()
    child_manager_2 = InterruptManager()

    # Act
    parent_manager.add_child_manager(child_manager_1)
    parent_manager.add_child_manager(child_manager_2)

    # Assert
    assert hasattr(parent_manager, "_child_managers"), "Should have child_managers list"
    assert len(parent_manager._child_managers) == 2, "Should have 2 children"
    assert child_manager_1 in parent_manager._child_managers, "Should contain child 1"
    assert child_manager_2 in parent_manager._child_managers, "Should contain child 2"


def test_remove_child_manager():
    """
    Test that child managers can be removed from tracking.

    Validates:
    - remove_child_manager() removes child
    - Other children remain tracked
    - Removing non-existent child doesn't error
    """
    # Arrange
    parent_manager = InterruptManager()
    child_manager_1 = InterruptManager()
    child_manager_2 = InterruptManager()

    parent_manager.add_child_manager(child_manager_1)
    parent_manager.add_child_manager(child_manager_2)

    # Act
    parent_manager.remove_child_manager(child_manager_1)

    # Assert
    assert len(parent_manager._child_managers) == 1, "Should have 1 child"
    assert child_manager_2 in parent_manager._child_managers, "Should contain child 2"
    assert (
        child_manager_1 not in parent_manager._child_managers
    ), "Should not contain child 1"

    # Act: Remove non-existent child (should not error)
    parent_manager.remove_child_manager(child_manager_1)  # Already removed
    assert len(parent_manager._child_managers) == 1, "Should still have 1 child"


# ═══════════════════════════════════════════════════════════════
# Test: Interrupt Propagation (3 tests)
# ═══════════════════════════════════════════════════════════════


def test_propagate_to_children_graceful():
    """
    Test that graceful interrupt propagates to all children.

    Validates:
    - propagate_to_children() interrupts all children
    - Children receive same interrupt mode (GRACEFUL)
    - Children receive propagation metadata
    """
    # Arrange
    parent_manager = InterruptManager()
    child_manager_1 = InterruptManager()
    child_manager_2 = InterruptManager()
    child_manager_3 = InterruptManager()

    parent_manager.add_child_manager(child_manager_1)
    parent_manager.add_child_manager(child_manager_2)
    parent_manager.add_child_manager(child_manager_3)

    # Request interrupt on parent
    parent_manager.request_interrupt(
        mode=InterruptMode.GRACEFUL,
        source=InterruptSource.USER,
        message="Parent interrupted, propagating to children",
        metadata={"propagate": True},
    )

    # Act
    parent_manager.propagate_to_children()

    # Assert
    assert parent_manager.is_interrupted(), "Parent should be interrupted"
    assert child_manager_1.is_interrupted(), "Child 1 should be interrupted"
    assert child_manager_2.is_interrupted(), "Child 2 should be interrupted"
    assert child_manager_3.is_interrupted(), "Child 3 should be interrupted"

    # Verify children have correct interrupt reason
    reason_1 = child_manager_1.get_interrupt_reason()
    assert reason_1 is not None, "Child 1 should have interrupt reason"
    assert reason_1.mode == InterruptMode.GRACEFUL, "Child 1 should have GRACEFUL mode"
    assert (
        "propagated" in reason_1.message.lower()
    ), "Child 1 should indicate propagation"


def test_propagate_to_children_immediate():
    """
    Test that immediate interrupt propagates to all children.

    Validates:
    - propagate_to_children() with IMMEDIATE mode
    - Children receive IMMEDIATE mode
    - Propagation is immediate (no delay)
    """
    # Arrange
    parent_manager = InterruptManager()
    child_manager_1 = InterruptManager()
    child_manager_2 = InterruptManager()

    parent_manager.add_child_manager(child_manager_1)
    parent_manager.add_child_manager(child_manager_2)

    # Request immediate interrupt on parent
    parent_manager.request_interrupt(
        mode=InterruptMode.IMMEDIATE,
        source=InterruptSource.TIMEOUT,
        message="Timeout exceeded, immediate stop",
        metadata={"timeout_seconds": 30},
    )

    # Act
    parent_manager.propagate_to_children()

    # Assert
    assert parent_manager.is_interrupted(), "Parent should be interrupted"
    assert child_manager_1.is_interrupted(), "Child 1 should be interrupted"
    assert child_manager_2.is_interrupted(), "Child 2 should be interrupted"

    # Verify children have IMMEDIATE mode
    reason_1 = child_manager_1.get_interrupt_reason()
    assert (
        reason_1.mode == InterruptMode.IMMEDIATE
    ), "Child 1 should have IMMEDIATE mode"

    reason_2 = child_manager_2.get_interrupt_reason()
    assert (
        reason_2.mode == InterruptMode.IMMEDIATE
    ), "Child 2 should have IMMEDIATE mode"


def test_propagate_with_no_children():
    """
    Test that propagate_to_children() works with no children.

    Validates:
    - propagate_to_children() doesn't error with no children
    - Parent interrupt state is preserved
    - No side effects occur
    """
    # Arrange
    parent_manager = InterruptManager()

    # Request interrupt on parent
    parent_manager.request_interrupt(
        mode=InterruptMode.GRACEFUL,
        source=InterruptSource.USER,
        message="Parent interrupted, no children to propagate",
    )

    # Act
    parent_manager.propagate_to_children()  # Should not error

    # Assert
    assert parent_manager.is_interrupted(), "Parent should still be interrupted"
    assert (
        len(parent_manager._child_managers) == 0
    ), "Should have no children (no initialization)"
