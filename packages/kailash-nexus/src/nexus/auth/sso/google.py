"""Google OAuth2/OIDC SSO Provider.

Provides OAuth2/OIDC authentication with Google.

Evidence:
    - example-project: auth_platform.py Google OAuth flow
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import jwt
from jwt import PyJWKClient
from nexus.auth.sso.base import (
    BaseSSOProvider,
    SSOAuthError,
    SSOTokenResponse,
    SSOUserInfo,
)

logger = logging.getLogger(__name__)


class GoogleProvider(BaseSSOProvider):
    """Google OAuth2/OIDC provider.

    Usage:
        >>> from nexus.auth.sso import GoogleProvider
        >>>
        >>> google = GoogleProvider(
        ...     client_id="your-client-id.apps.googleusercontent.com",
        ...     client_secret="your-client-secret",
        ... )

    Endpoints:
        - Authorization: https://accounts.google.com/o/oauth2/v2/auth
        - Token: https://oauth2.googleapis.com/token
        - JWKS: https://www.googleapis.com/oauth2/v3/certs
        - User Info: https://www.googleapis.com/oauth2/v3/userinfo
    """

    name = "google"

    AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
    JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        scopes: Optional[List[str]] = None,
        timeout: int = 30,
    ):
        """Initialize Google provider.

        Args:
            client_id: OAuth2 client ID
            client_secret: OAuth2 client secret
            scopes: OAuth2 scopes (default: openid, profile, email)
            timeout: HTTP request timeout
        """
        super().__init__(client_id, client_secret, timeout)
        self.scopes = scopes or ["openid", "profile", "email"]

        self._jwks_client = PyJWKClient(
            self.JWKS_URL,
            cache_keys=True,
            lifespan=3600,
        )

        logger.info("GoogleProvider initialized")

    def get_authorization_url(
        self,
        state: str,
        redirect_uri: str,
        scope: Optional[str] = None,
        access_type: str = "offline",
        prompt: str = "consent",
        **kwargs,
    ) -> str:
        """Generate Google authorization URL.

        Args:
            state: CSRF state parameter
            redirect_uri: Callback URL
            scope: Override default scopes
            access_type: "online" or "offline" (for refresh token)
            prompt: "none", "consent", "select_account"
            **kwargs: Additional parameters (login_hint, hd for G Suite)

        Returns:
            Authorization URL
        """
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": scope or " ".join(self.scopes),
            "state": state,
            "access_type": access_type,
            "prompt": prompt,
        }
        params.update(kwargs)

        return f"{self.AUTHORIZATION_URL}?{urlencode(params)}"

    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
    ) -> SSOTokenResponse:
        """Exchange authorization code for tokens.

        Args:
            code: Authorization code
            redirect_uri: Callback URL

        Returns:
            Token response

        Raises:
            SSOAuthError: If exchange fails
        """
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }

        response = await self._post_form(self.TOKEN_URL, data)

        return SSOTokenResponse(
            access_token=response["access_token"],
            id_token=response.get("id_token"),
            refresh_token=response.get("refresh_token"),
            token_type=response.get("token_type", "Bearer"),
            expires_in=response.get("expires_in", 3600),
            scope=response.get("scope"),
        )

    async def get_user_info(self, access_token: str) -> SSOUserInfo:
        """Fetch user info from Google.

        Args:
            access_token: OAuth2 access token

        Returns:
            Normalized user information
        """
        headers = {"Authorization": f"Bearer {access_token}"}
        data = await self._get_json(self.USERINFO_URL, headers=headers)

        return SSOUserInfo(
            provider_user_id=data.get("sub"),
            email=data.get("email"),
            email_verified=data.get("email_verified", False),
            name=data.get("name"),
            given_name=data.get("given_name"),
            family_name=data.get("family_name"),
            picture=data.get("picture"),
            locale=data.get("locale"),
            raw_data=data,
        )

    def validate_id_token(self, id_token: str) -> Dict[str, Any]:
        """Validate and decode Google ID token.

        Args:
            id_token: JWT ID token

        Returns:
            Decoded token claims

        Raises:
            SSOAuthError: If validation fails
        """
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(id_token)

            payload = jwt.decode(
                id_token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.client_id,
                issuer=["https://accounts.google.com", "accounts.google.com"],
            )

            return payload

        except jwt.ExpiredSignatureError:
            raise SSOAuthError("ID token has expired")
        except jwt.InvalidAudienceError:
            raise SSOAuthError("Invalid token audience")
        except jwt.InvalidIssuerError:
            raise SSOAuthError("Invalid token issuer")
        except jwt.InvalidTokenError as e:
            raise SSOAuthError(f"Invalid ID token: {e}")
