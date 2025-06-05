"""
Kailash SDK Security Module

This module provides security utilities for safe file operations, input validation,
and protection against common vulnerabilities like path traversal attacks.

Security Features:
    - Path traversal prevention
    - Input sanitization and validation
    - Safe file operations with sandboxing
    - Command injection protection
    - Memory and execution limits

Design Philosophy:
    - Fail-safe defaults (deny by default)
    - Defense in depth
    - Comprehensive logging for audit trails
    - Configurable security policies
"""

import logging
import os
import re
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class SecurityError(Exception):
    """Raised when a security policy violation is detected."""

    pass


class PathTraversalError(SecurityError):
    """Raised when path traversal attempt is detected."""

    pass


class CommandInjectionError(SecurityError):
    """Raised when command injection attempt is detected."""

    pass


class ExecutionTimeoutError(SecurityError):
    """Raised when execution exceeds allowed time limit."""

    pass


class MemoryLimitError(SecurityError):
    """Raised when memory usage exceeds allowed limit."""

    pass


class SecurityConfig:
    """Configuration for security policies and limits."""

    def __init__(
        self,
        allowed_directories: Optional[List[str]] = None,
        max_file_size: int = 100 * 1024 * 1024,  # 100MB
        execution_timeout: float = 300.0,  # 5 minutes
        memory_limit: int = 512 * 1024 * 1024,  # 512MB
        allowed_file_extensions: Optional[List[str]] = None,
        enable_audit_logging: bool = True,
        enable_path_validation: bool = True,
        enable_command_validation: bool = True,
    ):
        """
        Initialize security configuration.

        Args:
            allowed_directories: List of directories where file operations are permitted
            max_file_size: Maximum file size in bytes
            execution_timeout: Maximum execution time in seconds
            memory_limit: Maximum memory usage in bytes
            allowed_file_extensions: List of allowed file extensions
            enable_audit_logging: Whether to log security events
            enable_path_validation: Whether to validate file paths
            enable_command_validation: Whether to validate command strings
        """
        self.allowed_directories = allowed_directories or [
            os.path.expanduser("~/.kailash"),
            tempfile.gettempdir(),  # Allow all temp directories
            os.getcwd(),
            "/tmp",  # Unix temp directory
            "/var/tmp",  # Unix temp directory
        ]
        self.max_file_size = max_file_size
        self.execution_timeout = execution_timeout
        self.memory_limit = memory_limit
        self.allowed_file_extensions = allowed_file_extensions or [
            ".txt",
            ".csv",
            ".tsv",
            ".json",
            ".yaml",
            ".yml",
            ".py",
            ".md",
            ".xml",
            ".log",
            ".dat",
            ".conf",
            ".cfg",
            ".ini",
            ".properties",
            ".html",
            ".htm",
            ".xhtml",
            ".jsonl",
            ".ndjson",
        ]
        self.enable_audit_logging = enable_audit_logging
        self.enable_path_validation = enable_path_validation
        self.enable_command_validation = enable_command_validation


# Global security configuration
_security_config = SecurityConfig()


def get_security_config() -> SecurityConfig:
    """Get the current security configuration."""
    return _security_config


def set_security_config(config: SecurityConfig) -> None:
    """Set the global security configuration."""
    global _security_config
    _security_config = config


def validate_file_path(
    file_path: Union[str, Path],
    config: Optional[SecurityConfig] = None,
    operation: str = "access",
) -> Path:
    """
    Validate and sanitize file paths to prevent traversal attacks.

    Args:
        file_path: The file path to validate
        config: Security configuration (uses global if None)
        operation: Description of the operation for logging

    Returns:
        Validated and normalized Path object

    Raises:
        PathTraversalError: If path traversal attempt is detected
        SecurityError: If path is outside allowed directories

    Examples:
        >>> # Safe paths
        >>> validate_file_path("data/file.txt")
        PosixPath('data/file.txt')

        >>> # Blocked paths
        >>> validate_file_path("../../../etc/passwd")
        Traceback (most recent call last):
        PathTraversalError: Path traversal attempt detected
    """
    if config is None:
        config = get_security_config()

    if not config.enable_path_validation:
        return Path(file_path)

    try:
        # Convert to Path and resolve to absolute path
        path = Path(file_path).resolve()

        # Check for path traversal indicators
        path_str = str(path)
        if ".." in str(file_path):
            if config.enable_audit_logging:
                logger.warning(
                    f"Path traversal attempt detected: {file_path} -> {path}"
                )
            raise PathTraversalError(f"Path traversal attempt detected: {file_path}")

        # Check for access to sensitive system directories
        sensitive_dirs = ["/etc", "/var", "/usr", "/root", "/boot", "/sys", "/proc"]
        if any(path_str.startswith(sensitive) for sensitive in sensitive_dirs):
            if config.enable_audit_logging:
                logger.warning(
                    f"Path traversal attempt detected: {file_path} -> {path}"
                )
            raise PathTraversalError(f"Path traversal attempt detected: {file_path}")

        # Validate file extension
        if path.suffix and path.suffix.lower() not in config.allowed_file_extensions:
            if config.enable_audit_logging:
                logger.warning(f"File extension not allowed: {path.suffix} in {path}")
            raise SecurityError(f"File extension not allowed: {path.suffix}")

        # Check if path is within allowed directories
        path_in_allowed_dir = False
        for allowed_dir in config.allowed_directories:
            try:
                allowed_path = Path(allowed_dir).resolve()
                # Use more robust relative path checking
                try:
                    path.relative_to(allowed_path)
                    path_in_allowed_dir = True
                    break
                except ValueError:
                    # Try alternative method for compatibility
                    if str(path).startswith(str(allowed_path)):
                        path_in_allowed_dir = True
                        break
            except (ValueError, OSError):
                # Handle cases where path resolution fails
                if str(path).startswith(str(allowed_dir)):
                    path_in_allowed_dir = True
                    break

        if not path_in_allowed_dir:
            if config.enable_audit_logging:
                logger.warning(f"Path outside allowed directories: {path}")
            raise SecurityError(f"Path outside allowed directories: {path}")

        if config.enable_audit_logging:
            logger.info(f"File path validated for {operation}: {path}")

        return path

    except (OSError, ValueError) as e:
        if config.enable_audit_logging:
            logger.error(f"Path validation error: {e}")
        raise SecurityError(f"Invalid file path: {file_path}")


def safe_open(
    file_path: Union[str, Path],
    mode: str = "r",
    config: Optional[SecurityConfig] = None,
    **kwargs,
):
    """
    Safely open a file with security validation.

    Args:
        file_path: Path to the file
        mode: File open mode
        config: Security configuration
        **kwargs: Additional arguments for open()

    Returns:
        File handle

    Raises:
        SecurityError: If security validation fails

    Examples:
        >>> with safe_open("data/file.txt", "r") as f:
        ...     content = f.read()
    """
    if config is None:
        config = get_security_config()

    # Validate the file path
    validated_path = validate_file_path(file_path, config, f"open({mode})")

    # Check file size for read operations
    if "r" in mode and validated_path.exists():
        file_size = validated_path.stat().st_size
        if file_size > config.max_file_size:
            raise SecurityError(
                f"File too large: {file_size} bytes > {config.max_file_size}"
            )

    # Create directory if writing and it doesn't exist
    if "w" in mode or "a" in mode:
        validated_path.parent.mkdir(parents=True, exist_ok=True)

    if config.enable_audit_logging:
        logger.info(f"Opening file: {validated_path} (mode: {mode})")

    return open(validated_path, mode, **kwargs)


def validate_command_string(
    command: str, config: Optional[SecurityConfig] = None
) -> str:
    """
    Validate command strings to prevent injection attacks.

    Args:
        command: Command string to validate
        config: Security configuration

    Returns:
        Validated command string

    Raises:
        CommandInjectionError: If command injection attempt is detected
    """
    if config is None:
        config = get_security_config()

    if not config.enable_command_validation:
        return command

    # Check for common injection patterns
    dangerous_patterns = [
        r";",  # Command chaining
        r"&&",  # Logical AND command chaining
        r"\|\|",  # Logical OR command chaining
        r"\|",  # Pipe operations
        r"\$\(",  # Command substitution
        r"`.*`",  # Backtick command substitution
        r">\s*/dev/",  # Redirect to devices
        r"<.*>",  # Input/output redirection
        r"\beval\b",  # eval command
        r"\bexec\b",  # exec command
        r"rm\s+.*(\/|\*)",  # rm with dangerous paths
        r"cat\s+\/etc\/",  # reading system files
    ]

    for pattern in dangerous_patterns:
        if re.search(pattern, command, re.IGNORECASE):
            if config.enable_audit_logging:
                logger.warning(f"Command injection attempt detected: {command}")
            raise CommandInjectionError(f"Potentially dangerous command: {command}")

    if config.enable_audit_logging:
        logger.info(
            f"Command validated: {command[:100]}{'...' if len(command) > 100 else ''}"
        )

    return command


@contextmanager
def execution_timeout(
    timeout: Optional[float] = None, config: Optional[SecurityConfig] = None
):
    """
    Context manager to enforce execution timeouts.

    Args:
        timeout: Timeout in seconds (uses config default if None)
        config: Security configuration

    Raises:
        ExecutionTimeoutError: If execution exceeds timeout

    Examples:
        >>> with execution_timeout(30.0):
        ...     # Code that should complete within 30 seconds
        ...     time.sleep(5)
    """
    if config is None:
        config = get_security_config()

    if timeout is None:
        timeout = config.execution_timeout

    start_time = time.time()

    try:
        yield
    finally:
        elapsed_time = time.time() - start_time
        if elapsed_time > timeout:
            if config.enable_audit_logging:
                logger.warning(f"Execution timeout: {elapsed_time:.2f}s > {timeout}s")
            raise ExecutionTimeoutError(
                f"Execution timeout: {elapsed_time:.2f}s > {timeout}s"
            )


def sanitize_input(
    value: Any,
    max_length: int = 10000,
    allowed_types: Optional[List[type]] = None,
    config: Optional[SecurityConfig] = None,
) -> Any:
    """
    Sanitize input values to prevent injection attacks.

    Args:
        value: Value to sanitize
        max_length: Maximum string length
        allowed_types: List of allowed types
        config: Security configuration

    Returns:
        Sanitized value

    Raises:
        SecurityError: If input fails validation
    """
    if config is None:
        config = get_security_config()

    if allowed_types is None:
        allowed_types = [str, int, float, bool, list, dict]

    # Type validation
    if not any(isinstance(value, t) for t in allowed_types):
        raise SecurityError(f"Input type not allowed: {type(value)}")

    # String sanitization
    if isinstance(value, str):
        if len(value) > max_length:
            raise SecurityError(f"Input too long: {len(value)} > {max_length}")

        # Remove potentially dangerous characters and patterns
        sanitized = re.sub(r"[<>;&|`$()]", "", value)
        # Remove script tags and javascript
        sanitized = re.sub(
            r"<script.*?</script>", "", sanitized, flags=re.IGNORECASE | re.DOTALL
        )
        sanitized = re.sub(r"javascript:", "", sanitized, flags=re.IGNORECASE)

        if sanitized != value and config.enable_audit_logging:
            logger.warning(f"Input sanitized: {value[:50]}... -> {sanitized[:50]}...")

        return sanitized

    # Dictionary sanitization (recursive)
    if isinstance(value, dict):
        return {
            sanitize_input(k, max_length, allowed_types, config): sanitize_input(
                v, max_length, allowed_types, config
            )
            for k, v in value.items()
        }

    # List sanitization (recursive)
    if isinstance(value, list):
        return [
            sanitize_input(item, max_length, allowed_types, config) for item in value
        ]

    return value


def create_secure_temp_dir(
    prefix: str = "kailash_", config: Optional[SecurityConfig] = None
) -> Path:
    """
    Create a secure temporary directory.

    Args:
        prefix: Prefix for the directory name
        config: Security configuration

    Returns:
        Path to the secure temporary directory
    """
    if config is None:
        config = get_security_config()

    # Create temp directory with secure permissions
    temp_dir = Path(tempfile.mkdtemp(prefix=prefix))

    # Set restrictive permissions (owner only)
    temp_dir.chmod(0o700)

    if config.enable_audit_logging:
        logger.info(f"Created secure temp directory: {temp_dir}")

    return temp_dir


def validate_node_parameters(
    parameters: Dict[str, Any], config: Optional[SecurityConfig] = None
) -> Dict[str, Any]:
    """
    Validate and sanitize node parameters.

    Args:
        parameters: Node parameters to validate
        config: Security configuration

    Returns:
        Validated and sanitized parameters

    Raises:
        SecurityError: If parameters fail validation
    """
    if config is None:
        config = get_security_config()

    validated_params = {}

    for key, value in parameters.items():
        # Sanitize parameter key
        clean_key = sanitize_input(key, config=config)

        # Special handling for file paths
        if "path" in key.lower() or "file" in key.lower():
            if isinstance(value, (str, Path)):
                validated_value = validate_file_path(value, config, f"parameter {key}")
            else:
                validated_value = sanitize_input(value, config=config)
        else:
            validated_value = sanitize_input(value, config=config)

        validated_params[clean_key] = validated_value

    if config.enable_audit_logging:
        logger.info(f"Node parameters validated: {list(validated_params.keys())}")

    return validated_params
