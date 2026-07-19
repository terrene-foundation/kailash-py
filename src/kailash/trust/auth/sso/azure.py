"""Azure AD (Microsoft Entra ID) SSO Provider.

Provides OAuth2/OIDC authentication with Microsoft Azure AD.

Supports:
    - Single-tenant and multi-tenant apps
    - JWKS-based token validation
    - User info from Microsoft Graph API

Evidence:
    - production SSO implementation reference
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

# `PyJWT` (imported as `jwt`) is an OPTIONAL dependency. It ships under BOTH
# the `trust` extra (SSO + sign/verify) AND the `server` extra (middleware
# auth). Per `rules/dependencies.md` § "Declared = Imported": optional-extra
# imports MUST raise loudly with an actionable error naming the extra.
try:
    import jwt
    from jwt import PyJWKClient
except ImportError as exc:  # pragma: no cover — covered by structural invariant test
    raise ImportError(
        "kailash.trust.auth.sso.azure requires PyJWT. "
        "Install with: pip install 'kailash[trust]' (or 'kailash[server]')"
    ) from exc

from kailash.trust.auth.sso.base import (
    BaseSSOProvider,
    SSOAuthError,
    SSOTokenResponse,
    SSOUserInfo,
)

logger = logging.getLogger(__name__)


class AzureADProvider(BaseSSOProvider):
    """Azure AD (Microsoft Entra ID) SSO provider.

    Usage:
        >>> from nexus.auth.sso import AzureADProvider
        >>>
        >>> azure = AzureADProvider(
        ...     tenant_id="your-tenant-id",
        ...     client_id="your-client-id",
        ...     client_secret="your-client-secret",
        ... )

    Endpoints (single tenant):
        - Authorization: https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize
        - Token: https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token
        - JWKS: https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys
        - User Info: https://graph.microsoft.com/v1.0/me
    """

    name = "azure"

    AUTHORITY_BASE = "https://login.microsoftonline.com"
    GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"

    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        scopes: Optional[List[str]] = None,
        allowed_tenants: Optional[List[str]] = None,
        timeout: int = 30,
    ):
        """Initialize Azure AD provider.

        Args:
            tenant_id: Azure AD tenant ID (or "common" for multi-tenant)
            client_id: Application (client) ID
            client_secret: Client secret
            scopes: OAuth2 scopes (default: openid, profile, email, User.Read)
            allowed_tenants: For multi-tenant apps, list of allowed tenant IDs
            timeout: HTTP request timeout
        """
        super().__init__(client_id, client_secret, timeout)
        self.tenant_id = tenant_id
        self.scopes = scopes or ["openid", "profile", "email", "User.Read"]
        self.allowed_tenants = allowed_tenants
        self.is_multi_tenant = tenant_id in ("common", "organizations", "consumers")

        self._jwks_client = PyJWKClient(
            f"{self.AUTHORITY_BASE}/{tenant_id}/discovery/v2.0/keys",
            cache_keys=True,
            lifespan=3600,
        )

        logger.info(
            f"AzureADProvider initialized: tenant={tenant_id}, "
            f"multi_tenant={self.is_multi_tenant}"
        )

    def get_authorization_url(
        self,
        state: str,
        redirect_uri: str,
        scope: Optional[str] = None,
        prompt: str = "select_account",
        code_challenge: Optional[str] = None,
        **kwargs,
    ) -> str:
        """Generate Azure AD authorization URL.

        Args:
            state: CSRF state parameter
            redirect_uri: Callback URL
            scope: Override default scopes (space-separated)
            prompt: Login prompt behavior (none, login, consent, select_account)
            code_challenge: PKCE (RFC 7636) S256 challenge. When present, emits
                ``code_challenge`` + ``code_challenge_method=S256``.
            **kwargs: Additional parameters (login_hint, domain_hint, and
                ``nonce`` for OIDC id_token replay defense)

        Returns:
            Authorization URL
        """
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": scope or " ".join(self.scopes),
            "state": state,
            "response_mode": "query",
            "prompt": prompt,
        }
        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"
        params.update(kwargs)

        base_url = f"{self.AUTHORITY_BASE}/{self.tenant_id}/oauth2/v2.0/authorize"
        return f"{base_url}?{urlencode(params)}"

    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
        code_verifier: Optional[str] = None,
    ) -> SSOTokenResponse:
        """Exchange authorization code for tokens.

        Args:
            code: Authorization code from callback
            redirect_uri: Same redirect URI used in authorization
            code_verifier: PKCE (RFC 7636) verifier replayed to the token
                endpoint to prove proof-of-possession.

        Returns:
            Token response with access_token and id_token

        Raises:
            SSOAuthError: If exchange fails
        """
        token_url = f"{self.AUTHORITY_BASE}/{self.tenant_id}/oauth2/v2.0/token"

        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
        if code_verifier:
            data["code_verifier"] = code_verifier

        response = await self._post_form(token_url, data)

        return SSOTokenResponse(
            access_token=response["access_token"],
            id_token=response.get("id_token"),
            refresh_token=response.get("refresh_token"),
            token_type=response.get("token_type", "Bearer"),
            expires_in=response.get("expires_in", 3600),
            scope=response.get("scope"),
        )

    async def get_user_info(self, access_token: str) -> SSOUserInfo:
        """Fetch user info from Microsoft Graph API.

        Args:
            access_token: OAuth2 access token

        Returns:
            Normalized user information
        """
        headers = {"Authorization": f"Bearer {access_token}"}
        data = await self._get_json(f"{self.GRAPH_API_BASE}/me", headers=headers)

        return SSOUserInfo(
            provider_user_id=data.get("id"),
            email=data.get("mail") or data.get("userPrincipalName"),
            email_verified=True,  # Azure AD verifies emails
            name=data.get("displayName"),
            given_name=data.get("givenName"),
            family_name=data.get("surname"),
            picture=None,  # Graph API requires separate call for photo
            locale=data.get("preferredLanguage"),
            raw_data=data,
        )

    def validate_id_token(
        self,
        id_token: str,
        nonce: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Validate and decode Azure AD ID token.

        Validates:
            - Signature using JWKS
            - Expiration (exp claim)
            - Audience (aud claim = client_id)
            - Issuer (iss claim = Azure AD)
            - Tenant ID (tid claim, for multi-tenant)
            - Nonce (when provided; id_token replay/injection defense)

        Args:
            id_token: JWT ID token
            nonce: The nonce minted at authorization time. When present, the
                id_token's ``nonce`` claim MUST match (constant-time) or this
                raises.

        Returns:
            Decoded token claims

        Raises:
            SSOAuthError: If validation fails or the nonce does not match
        """
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(id_token)

            if self.is_multi_tenant:
                unverified = jwt.decode(id_token, options={"verify_signature": False})
                tid = unverified.get("tid")
                if self.allowed_tenants and tid not in self.allowed_tenants:
                    raise SSOAuthError(f"Tenant {tid} not in allowed list")
                issuer = f"{self.AUTHORITY_BASE}/{tid}/v2.0"
            else:
                issuer = f"{self.AUTHORITY_BASE}/{self.tenant_id}/v2.0"

            payload = jwt.decode(
                id_token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.client_id,
                issuer=issuer,
            )

            # Nonce enforced ONLY against the verified payload above.
            self._enforce_nonce(payload, nonce)

            return payload

        except SSOAuthError:
            raise
        except jwt.ExpiredSignatureError:
            raise SSOAuthError("ID token has expired")
        except jwt.InvalidAudienceError:
            raise SSOAuthError("Invalid token audience")
        except jwt.InvalidIssuerError:
            raise SSOAuthError("Invalid token issuer")
        except jwt.InvalidTokenError as e:
            raise SSOAuthError(f"Invalid ID token: {e}")

    def get_logout_url(self, post_logout_redirect_uri: Optional[str] = None) -> str:
        """Get Azure AD logout URL.

        Args:
            post_logout_redirect_uri: URL to redirect after logout

        Returns:
            Logout URL
        """
        url = f"{self.AUTHORITY_BASE}/{self.tenant_id}/oauth2/v2.0/logout"
        if post_logout_redirect_uri:
            url += f"?post_logout_redirect_uri={post_logout_redirect_uri}"
        return url
