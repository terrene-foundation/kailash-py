"""
Kaizen Signatures for AI-Enhanced Authentication Nodes.

These signatures define structured outputs for:
- SSO field mapping
- Role assignment
- Risk assessment
- Permission mapping
- Security settings
"""

from typing import List

from kaizen.signatures import InputField, OutputField, Signature


class SSOFieldMappingSignature(Signature):
    """
    Signature for SSO field mapping output.

    Maps various SSO provider attribute formats to internal user profile format.
    """

    # Input fields
    provider = InputField(desc="SSO provider name (azure, google, okta, etc.)")
    raw_attributes = InputField(desc="Raw user attributes from SSO provider")

    # Output fields - all required for complete user profile
    first_name: str = OutputField(desc="User's first name")
    last_name: str = OutputField(desc="User's last name")
    email: str = OutputField(desc="User's email address")
    department: str = OutputField(desc="User's department or team")
    job_title: str = OutputField(desc="User's job title or position")
    groups: List[str] = OutputField(desc="List of groups or teams the user belongs to")


class SSORoleAssignmentSignature(Signature):
    """
    Signature for role assignment output.

    Assigns system roles based on user profile attributes.
    """

    # Input fields
    user_email = InputField(desc="User's email address")
    first_name = InputField(desc="User's first name")
    last_name = InputField(desc="User's last name")
    job_title = InputField(desc="User's job title or position")
    department = InputField(desc="User's department or team")
    groups = InputField(desc="List of groups or teams the user belongs to")

    # Output field - list of assigned roles
    roles: List[str] = OutputField(desc="List of system roles assigned to the user")


class EnterpriseAuthRiskSignature(Signature):
    """
    Signature for AI-powered fraud detection risk assessment.

    Analyzes authentication attempts for security risks and fraud patterns.
    """

    # Input fields
    user_id = InputField(desc="User identifier")
    ip_address = InputField(desc="IP address of authentication attempt")
    device_recognized = InputField(desc="Whether the device is recognized")
    device_info = InputField(
        desc="Device information (user agent, screen resolution, timezone)"
    )
    location = InputField(desc="Geographic location of the attempt")
    timestamp = InputField(desc="Timestamp of the authentication attempt")
    existing_factors = InputField(
        desc="Risk factors already identified by rule-based checks"
    )

    # Output fields
    risk_score: float = OutputField(
        desc="Risk score between 0.0 (no risk) and 1.0 (critical risk)"
    )
    additional_factors: List[str] = OutputField(
        desc="Additional risk factors identified by AI analysis"
    )
    reasoning: str = OutputField(desc="Clear explanation of the risk assessment")
    recommended_action: str = OutputField(
        desc="Recommended action: allow, require_mfa, require_additional_verification, or block"
    )


class DirectorySearchSignature(Signature):
    """
    Signature for AI-powered directory search intent analysis.

    Analyzes search queries to understand search intent and optimize directory queries.
    """

    # Input fields
    search_query = InputField(desc="Natural language search query")
    available_attributes = InputField(desc="Available LDAP/AD attributes to search")

    # Output fields
    search_attributes: List[str] = OutputField(desc="LDAP/AD attributes to search")
    filter_expression: str = OutputField(desc="Optimized LDAP filter expression")
    search_scope: str = OutputField(desc="Search scope: base, one, or sub")


class DirectoryRoleSignature(Signature):
    """
    Signature for AI-powered role assignment from directory attributes.
    """

    # Input fields
    user_dn = InputField(desc="User distinguished name")
    ldap_groups = InputField(desc="LDAP groups the user belongs to")
    user_attributes = InputField(desc="User LDAP attributes")

    # Output fields
    roles: List[str] = OutputField(
        desc="List of system roles assigned based on directory attributes"
    )


class DirectoryPermissionSignature(Signature):
    """
    Signature for AI-powered permission mapping from directory attributes.
    """

    # Input fields
    user_dn = InputField(desc="User distinguished name")
    roles = InputField(desc="User's assigned roles")
    directory_groups = InputField(desc="Directory groups the user belongs to")

    # Output fields
    permissions: List[str] = OutputField(
        desc="List of permissions granted based on directory attributes and roles"
    )


class DirectorySecuritySignature(Signature):
    """
    Signature for AI-powered security settings determination.
    """

    # Input fields
    user_dn = InputField(desc="User distinguished name")
    account_status = InputField(desc="Account status (active, disabled, locked)")
    user_attributes = InputField(desc="User LDAP attributes")

    # Output fields
    mfa_required: bool = OutputField(desc="Whether MFA is required for this user")
    password_expiry_days: int = OutputField(desc="Number of days until password expiry")
    account_locked: bool = OutputField(desc="Whether the account is locked")
    max_sessions: int = OutputField(desc="Maximum concurrent sessions allowed")
