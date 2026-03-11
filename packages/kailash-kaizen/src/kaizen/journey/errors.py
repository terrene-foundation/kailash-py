"""
Journey-specific exceptions for Journey Orchestration.

Provides structured error handling for journey execution, pathway navigation,
context management, and state persistence.

Exception Hierarchy:
    JourneyError (base)
    - PathwayNotFoundError
    - SessionNotStartedError
    - ContextSizeExceededError
    - MaxPathwayDepthError
    - TransitionError
    - StateError

Usage:
    from kaizen.journey.errors import (
        PathwayNotFoundError,
        SessionNotStartedError,
        ContextSizeExceededError,
    )

    try:
        await manager.process_message("Hello")
    except SessionNotStartedError:
        await manager.start_session()
        await manager.process_message("Hello")

References:
    - docs/plans/03-journey/05-runtime.md
    - TODO-JO-004: Runtime Components
"""

from typing import Any, Dict, List, Optional


class JourneyError(Exception):
    """
    Base exception for all journey-related errors.

    All journey exceptions inherit from this class, allowing for
    catch-all error handling:

        try:
            result = await journey.process_message(msg)
        except JourneyError as e:
            logger.error(f"Journey error: {e}")
    """

    pass


class PathwayNotFoundError(JourneyError):
    """
    Raised when a pathway is not found in the journey.

    Occurs when:
    - Transitioning to a non-existent pathway
    - Referencing an undefined pathway in __next__
    - Invalid pathway ID in ReturnToSpecific

    Attributes:
        pathway_id: The requested pathway ID that was not found
        available: List of valid pathway IDs in the journey

    Example:
        >>> raise PathwayNotFoundError("faq", ["intake", "booking", "confirmation"])
        PathwayNotFoundError: Pathway 'faq' not found. Available: ['intake', 'booking', 'confirmation']
    """

    def __init__(self, pathway_id: str, available: List[str]):
        """
        Initialize PathwayNotFoundError.

        Args:
            pathway_id: The requested pathway ID that was not found
            available: List of valid pathway IDs in the journey
        """
        self.pathway_id = pathway_id
        self.available = available
        super().__init__(f"Pathway '{pathway_id}' not found. Available: {available}")


class SessionNotStartedError(JourneyError):
    """
    Raised when operating on an unstarted session.

    Occurs when:
    - Calling process_message() before start_session()
    - Accessing session state before initialization
    - Restoring a non-existent session

    The session must be started via PathwayManager.start_session() before
    processing messages.

    Example:
        >>> raise SessionNotStartedError()
        SessionNotStartedError: Session not started. Call start_session() first.

        >>> raise SessionNotStartedError("session-123")
        SessionNotStartedError: Session 'session-123' not started or expired.
    """

    def __init__(self, session_id: Optional[str] = None):
        """
        Initialize SessionNotStartedError.

        Args:
            session_id: Optional session ID for more specific error message
        """
        self.session_id = session_id
        if session_id:
            message = f"Session '{session_id}' not started or expired."
        else:
            message = "Session not started. Call start_session() first."
        super().__init__(message)


class ContextSizeExceededError(JourneyError):
    """
    Raised when accumulated context exceeds size limit.

    Context size limits prevent memory issues and ensure efficient
    serialization. Default limit is 1MB (configurable via JourneyConfig).

    Attributes:
        current_size: Current context size in bytes
        max_size: Maximum allowed size in bytes

    Example:
        >>> raise ContextSizeExceededError(1500000, 1048576)
        ContextSizeExceededError: Context size 1500000 bytes exceeds limit of 1048576 bytes
    """

    def __init__(self, current_size: int, max_size: int):
        """
        Initialize ContextSizeExceededError.

        Args:
            current_size: Current context size in bytes
            max_size: Maximum allowed size in bytes
        """
        self.current_size = current_size
        self.max_size = max_size
        super().__init__(
            f"Context size {current_size} bytes exceeds limit of {max_size} bytes"
        )


class MaxPathwayDepthError(JourneyError):
    """
    Raised when pathway navigation stack exceeds max depth.

    Prevents infinite recursion in pathway navigation. Default max depth
    is 10 (configurable via JourneyConfig.max_pathway_depth).

    This typically indicates:
    - Circular pathway references
    - Excessive use of ReturnToPrevious without completion
    - Logic error in transition rules

    Attributes:
        depth: Current pathway stack depth
        max_depth: Maximum allowed depth
        pathway_stack: Current pathway navigation stack

    Example:
        >>> raise MaxPathwayDepthError(11, 10, ["intake", "faq", "intake", ...])
        MaxPathwayDepthError: Pathway depth 11 exceeds max 10. Stack: ['intake', 'faq', ...]
    """

    def __init__(
        self, depth: int, max_depth: int, pathway_stack: Optional[List[str]] = None
    ):
        """
        Initialize MaxPathwayDepthError.

        Args:
            depth: Current pathway stack depth
            max_depth: Maximum allowed depth
            pathway_stack: Optional pathway stack for debugging
        """
        self.depth = depth
        self.max_depth = max_depth
        self.pathway_stack = pathway_stack or []

        message = f"Pathway depth {depth} exceeds max {max_depth}"
        if pathway_stack:
            # Show truncated stack for debugging
            stack_preview = pathway_stack[:5]
            if len(pathway_stack) > 5:
                stack_preview.append("...")
            message += f". Stack: {stack_preview}"

        super().__init__(message)


class TransitionError(JourneyError):
    """
    Raised when a transition fails to execute.

    Occurs when:
    - Transition target pathway doesn't exist
    - Transition condition raises an exception
    - Context update fails

    Attributes:
        transition_name: Name or description of the failed transition
        reason: Reason for the failure
        context: Optional context data for debugging

    Example:
        >>> raise TransitionError("faq_transition", "Target pathway 'faq' not found")
        TransitionError: Transition 'faq_transition' failed: Target pathway 'faq' not found
    """

    def __init__(
        self,
        transition_name: str,
        reason: str,
        context: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize TransitionError.

        Args:
            transition_name: Name or description of the failed transition
            reason: Reason for the failure
            context: Optional context data for debugging
        """
        self.transition_name = transition_name
        self.reason = reason
        self.context = context or {}
        super().__init__(f"Transition '{transition_name}' failed: {reason}")


class StateError(JourneyError):
    """
    Raised when state operations fail.

    Occurs when:
    - Session serialization fails
    - Session deserialization fails
    - Backend storage operation fails
    - State corruption detected

    Attributes:
        operation: The failed operation (save, load, delete, etc.)
        session_id: Optional session ID involved
        reason: Reason for the failure

    Example:
        >>> raise StateError("save", session_id="session-123", reason="Backend unavailable")
        StateError: State operation 'save' failed for session 'session-123': Backend unavailable
    """

    def __init__(
        self,
        operation: str,
        session_id: Optional[str] = None,
        reason: str = "",
    ):
        """
        Initialize StateError.

        Args:
            operation: The failed operation (save, load, delete, etc.)
            session_id: Optional session ID involved
            reason: Reason for the failure
        """
        self.operation = operation
        self.session_id = session_id
        self.reason = reason

        if session_id:
            message = f"State operation '{operation}' failed for session '{session_id}'"
        else:
            message = f"State operation '{operation}' failed"

        if reason:
            message += f": {reason}"

        super().__init__(message)


__all__ = [
    "JourneyError",
    "PathwayNotFoundError",
    "SessionNotStartedError",
    "ContextSizeExceededError",
    "MaxPathwayDepthError",
    "TransitionError",
    "StateError",
]
