# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""SSO provider protocol and base classes -- framework-agnostic.

Extracted from ``nexus.auth.sso`` (SPEC-06). Provides the SSO provider
protocol, base class, and concrete provider implementations (Google, Azure,
GitHub, Apple) that work independently of any HTTP framework.

The Nexus SSO route handlers remain in Nexus and delegate to these providers
for the actual OAuth2/OIDC operations.
"""

from __future__ import annotations

import logging

from kailash.trust.auth.sso.apple import AppleProvider
from kailash.trust.auth.sso.azure import AzureADProvider
from kailash.trust.auth.sso.base import (
    BaseSSOProvider,
    SSOAuthError,
    SSOProvider,
    SSOTokenResponse,
    SSOUserInfo,
)
from kailash.trust.auth.sso.github import GitHubProvider
from kailash.trust.auth.sso.google import GoogleProvider

logger = logging.getLogger(__name__)

__all__ = [
    # Protocol and base
    "SSOProvider",
    "BaseSSOProvider",
    "SSOTokenResponse",
    "SSOUserInfo",
    "SSOAuthError",
    # Providers
    "GoogleProvider",
    "AzureADProvider",
    "GitHubProvider",
    "AppleProvider",
]
