"""Transaction utilities for admin nodes to handle timing and persistence issues.

This module provides utilities to handle common transaction and timing issues
encountered in admin node operations, particularly around user creation,
role assignment, and permission checks.
"""

import logging
import time
from typing import Any, Callable, Dict, Optional, TypeVar

from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError

logger = logging.getLogger(__name__)

T = TypeVar("T")


class TransactionHelper:
    """Helper class for handling database transaction timing and persistence issues."""

    def __init__(self, db_node, max_retries: int = 3, retry_delay: float = 0.1):
        """
        Initialize transaction helper.

        Args:
            db_node: Database node instance (SQLDatabaseNode)
            max_retries: Maximum number of retries for transient failures
            retry_delay: Delay between retries in seconds
        """
        self.db_node = db_node
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def execute_with_retry(self, operation: Callable[[], T], operation_name: str) -> T:
        """
        Execute a database operation with retry logic.

        Args:
            operation: Function that performs the database operation
            operation_name: Description of the operation for logging

        Returns:
            Result of the operation

        Raises:
            NodeExecutionError: If operation fails after all retries
        """
        last_exception = None

        for attempt in range(self.max_retries):
            try:
                result = operation()
                if attempt > 0:
                    logger.info(f"{operation_name} succeeded on attempt {attempt + 1}")
                return result
            except Exception as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    logger.warning(
                        f"{operation_name} failed on attempt {attempt + 1}, retrying: {e}"
                    )
                    time.sleep(self.retry_delay * (2**attempt))  # Exponential backoff
                else:
                    logger.error(
                        f"{operation_name} failed after {self.max_retries} attempts: {e}"
                    )

        raise NodeExecutionError(
            f"{operation_name} failed after {self.max_retries} attempts: {last_exception}"
        )

    def verify_operation_success(
        self,
        verification_query: str,
        expected_result: Any,
        operation_name: str,
        timeout_seconds: float = 5.0,
    ) -> bool:
        """
        Verify that a database operation was successful by checking the result.

        Args:
            verification_query: SQL query to verify the operation
            expected_result: Expected result from the verification query
            operation_name: Description of the operation for logging
            timeout_seconds: Maximum time to wait for verification

        Returns:
            True if verification succeeds

        Raises:
            NodeValidationError: If verification fails after timeout
        """
        start_time = time.time()

        while time.time() - start_time < timeout_seconds:
            try:
                result = self.db_node.execute(
                    query=verification_query, result_format="dict"
                )
                data = result.get("data", [])

                if data and len(data) > 0:
                    # Operation was successful
                    logger.debug(f"{operation_name} verification succeeded")
                    return True

            except Exception as e:
                logger.debug(f"{operation_name} verification error: {e}")

            # Wait before retrying
            time.sleep(0.05)  # 50ms

        raise NodeValidationError(
            f"{operation_name} verification failed after {timeout_seconds}s"
        )

    def create_user_with_verification(
        self, user_data: Dict[str, Any], tenant_id: str
    ) -> Dict[str, Any]:
        """
        Create a user and verify the creation was successful.

        Args:
            user_data: User data dictionary
            tenant_id: Tenant ID

        Returns:
            User creation result
        """
        user_id = user_data.get("user_id")

        def create_operation():
            # Perform the user creation
            from .user_management import UserManagementNode

            user_mgmt = UserManagementNode(database_url=self.db_node.connection_string)
            return user_mgmt.execute(
                operation="create_user", user_data=user_data, tenant_id=tenant_id
            )

        # Execute creation with retry
        result = self.execute_with_retry(
            create_operation, f"User creation for {user_id}"
        )

        # Verify user was created
        verification_query = """
            SELECT user_id FROM users
            WHERE user_id = $1 AND tenant_id = $2
        """

        self.verify_operation_success(
            verification_query,
            user_id,
            f"User {user_id} creation verification",
            timeout_seconds=2.0,
        )

        return result

    def assign_role_with_verification(
        self, user_id: str, role_id: str, tenant_id: str
    ) -> Dict[str, Any]:
        """
        Assign a role to a user and verify the assignment was successful.

        Args:
            user_id: User ID
            role_id: Role ID
            tenant_id: Tenant ID

        Returns:
            Role assignment result
        """

        def assign_operation():
            from .role_management import RoleManagementNode

            role_mgmt = RoleManagementNode(database_url=self.db_node.connection_string)
            return role_mgmt.execute(
                operation="assign_user",
                user_id=user_id,
                role_id=role_id,
                tenant_id=tenant_id,
            )

        # Execute assignment with retry
        result = self.execute_with_retry(
            assign_operation, f"Role assignment {role_id} to {user_id}"
        )

        # Verify role was assigned
        verification_query = """
            SELECT user_id, role_id FROM user_role_assignments
            WHERE user_id = $1 AND role_id = $2 AND tenant_id = $3 AND is_active = true
        """

        self.verify_operation_success(
            verification_query,
            {"user_id": user_id, "role_id": role_id},
            f"Role assignment {role_id} to {user_id} verification",
            timeout_seconds=2.0,
        )

        return result


def with_transaction_retry(max_retries: int = 3, retry_delay: float = 0.1):
    """
    Decorator to add retry logic to admin node operations.

    Args:
        max_retries: Maximum number of retries
        retry_delay: Initial delay between retries
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"{func.__name__} failed on attempt {attempt + 1}, retrying: {e}"
                        )
                        time.sleep(retry_delay * (2**attempt))
                    else:
                        logger.error(
                            f"{func.__name__} failed after {max_retries} attempts: {e}"
                        )

            raise NodeExecutionError(
                f"{func.__name__} failed after {max_retries} attempts: {last_exception}"
            )

        return wrapper

    return decorator
