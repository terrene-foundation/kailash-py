"""
Multi-tenancy specific exceptions for DataFlow.
"""


class TenantIsolationError(Exception):
    """
    Exception raised when tenant isolation cannot be properly enforced.
    """

    pass


class QueryParsingError(Exception):
    """
    Exception raised when SQL query parsing fails.
    """

    pass


class TenantSecurityError(Exception):
    """
    Exception raised when tenant security rules are violated.
    """

    pass


class CrossTenantAccessError(TenantIsolationError):
    """
    Exception raised when cross-tenant access is attempted.
    """

    pass
