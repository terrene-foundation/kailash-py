"""Error capture component for Debug Agent.

This module provides error capture functionality that hooks into ErrorEnhancer
to intercept exceptions with full context.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class StackFrame:
    """Represents a single stack frame in a stacktrace.

    Attributes:
        filename: Source file path where error occurred
        line_number: Line number in source file
        function_name: Function name where error occurred
        code_context: Code context around error line (3 lines before/after)
    """

    filename: str
    line_number: int
    function_name: str
    code_context: str


@dataclass
class CapturedError:
    """Captured error with full context from ErrorEnhancer.

    Attributes:
        exception: Original exception object
        error_type: Exception class name (e.g., "ValueError", "KeyError")
        message: Error message string
        stacktrace: List of stack frames showing execution path
        context: Additional context from ErrorEnhancer (node_id, operation, etc.)
        timestamp: When error was captured
    """

    exception: Exception
    error_type: str
    message: str
    stacktrace: List[StackFrame]
    context: Dict[str, Any]
    timestamp: datetime

    def to_dict(self) -> Dict[str, Any]:
        """Convert CapturedError to dictionary for serialization.

        Returns:
            Dictionary representation with all fields

        Example:
            >>> captured = CapturedError(...)
            >>> data = captured.to_dict()
            >>> data["error_type"]
            'ValueError'
        """
        return {
            "error_type": self.error_type,
            "message": self.message,
            "stacktrace": [
                {
                    "filename": frame.filename,
                    "line_number": frame.line_number,
                    "function_name": frame.function_name,
                    "code_context": frame.code_context,
                }
                for frame in self.stacktrace
            ],
            "context": self.context,
            "timestamp": self.timestamp.isoformat(),
        }


class ErrorCapture:
    """Captures errors with full context for Debug Agent analysis.

    This component intercepts exceptions and extracts:
    - Exception type and message
    - Full structured stacktrace with code context
    - ErrorEnhancer context (if available)
    - Capture timestamp

    Usage:
        capture = ErrorCapture()

        try:
            # Code that might fail
            raise ValueError("Something went wrong")
        except Exception as e:
            captured = capture.capture(e)
            # captured contains full error context
    """

    def __init__(self):
        """Initialize ErrorCapture with empty error history."""
        self.captured_errors: List[CapturedError] = []

    def capture(self, exception: Exception) -> CapturedError:
        """Capture exception with full context.

        Extracts:
        - Exception type and message
        - Structured stacktrace with code context
        - ErrorEnhancer context (if available)
        - Capture timestamp

        Args:
            exception: Exception to capture

        Returns:
            CapturedError with complete error context

        Example:
            >>> capture = ErrorCapture()
            >>> try:
            ...     raise ValueError("Test error")
            ... except Exception as e:
            ...     captured = capture.capture(e)
            >>> captured.error_type
            'ValueError'
            >>> captured.message
            'Test error'
        """
        stacktrace = self._extract_stacktrace(exception)
        context = self._extract_context(exception)

        captured = CapturedError(
            exception=exception,
            error_type=type(exception).__name__,
            message=str(exception),
            stacktrace=stacktrace,
            context=context,
            timestamp=datetime.now(),
        )

        self.captured_errors.append(captured)
        return captured

    def _extract_stacktrace(self, exception: Exception) -> List[StackFrame]:
        """Extract structured stacktrace from exception.

        Walks the traceback chain and creates StackFrame objects for each frame,
        including code context around the error line.

        Args:
            exception: Exception with traceback

        Returns:
            List of StackFrame objects representing execution path
        """
        frames = []
        tb = exception.__traceback__

        while tb is not None:
            frame = tb.tb_frame
            line_number = tb.tb_lineno

            frames.append(
                StackFrame(
                    filename=frame.f_code.co_filename,
                    line_number=line_number,
                    function_name=frame.f_code.co_name,
                    code_context=self._get_code_context(frame, line_number),
                )
            )
            tb = tb.tb_next

        return frames

    def _get_code_context(self, frame, line_number: int, context_lines: int = 3) -> str:
        """Get code context around error line.

        Reads source file and extracts N lines before and after the error line
        to provide context for debugging.

        Args:
            frame: Stack frame object
            line_number: Line number where error occurred
            context_lines: Number of lines before/after to include (default: 3)

        Returns:
            Code context as multi-line string, or empty string if file not found

        Example:
            For error at line 10 with context_lines=3:
            - Returns lines 7-13 (3 before, line 10, 3 after)
        """
        filename = frame.f_code.co_filename

        try:
            with open(filename, "r") as f:
                lines = f.readlines()

            # Calculate start and end indices (0-based)
            start = max(0, line_number - context_lines - 1)
            end = min(len(lines), line_number + context_lines)

            context = "".join(lines[start:end])
            return context
        except (FileNotFoundError, IOError, PermissionError):
            # File might not exist (e.g., <stdin>, dynamically generated code)
            return ""

    def _extract_context(self, exception: Exception) -> Dict[str, Any]:
        """Extract context from exception attributes.

        Looks for ErrorEnhancer context and other useful attributes attached to
        the exception object.

        Context extracted:
        - ErrorEnhancer context dict (if available)
        - node_id (if available)
        - parameter_name (if available)
        - operation (if available)

        Args:
            exception: Exception object to extract context from

        Returns:
            Dictionary of context information
        """
        context = {}

        # Extract ErrorEnhancer context if available
        if hasattr(exception, "context"):
            context.update(exception.context)

        # Extract other useful attributes
        if hasattr(exception, "node_id"):
            context["node_id"] = exception.node_id
        if hasattr(exception, "parameter_name"):
            context["parameter_name"] = exception.parameter_name
        if hasattr(exception, "operation"):
            context["operation"] = exception.operation

        return context

    def get_all_captured_errors(self) -> List[CapturedError]:
        """Get all captured errors in chronological order.

        Returns:
            List of all CapturedError objects
        """
        return self.captured_errors

    def clear_captured_errors(self):
        """Clear captured error history.

        Useful for resetting state between test runs or analysis sessions.
        """
        self.captured_errors.clear()
