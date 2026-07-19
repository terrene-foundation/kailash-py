"""Google OAuth2/OIDC SSO Provider.

Provides OAuth2/OIDC authentication with Google.

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
        "kailash.trust.auth.sso.google requires PyJWT. "
        "Install with: pip install 'kailash[trust]' (or 'kailash[server]')"
    ) from exc

from kailash.trust.auth.sso.base import (
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
        code_challenge: Optional[str] = None,
        **kwargs,
    ) -> str:
        """Generate Google authorization URL.

        Args:
            state: CSRF state parameter
            redirect_uri: Callback URL
            scope: Override default scopes
            access_type: "online" or "offline" (for refresh token)
            prompt: "none", "consent", "select_account"
            code_challenge: PKCE (RFC 7636) S256 challenge. When present, emits
                ``code_challenge`` + ``code_challenge_method=S256``.
            **kwargs: Additional parameters (login_hint, hd for G Suite, and
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
            "access_type": access_type,
            "prompt": prompt,
        }
        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"
        params.update(kwargs)

        return f"{self.AUTHORIZATION_URL}?{urlencode(params)}"

    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
        code_verifier: Optional[str] = None,
    ) -> SSOTokenResponse:
        """Exchange authorization code for tokens.

        Args:
            code: Authorization code
            redirect_uri: Callback URL
            code_verifier: PKCE (RFC 7636) verifier replayed to the token
                endpoint to prove proof-of-possession.

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
        if code_verifier:
            data["code_verifier"] = code_verifier

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

    def validate_id_token(
        self,
        id_token: str,
        nonce: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Validate and decode Google ID token.

        Args:
            id_token: JWT ID token
            nonce: The nonce minted at authorization time. When present, the
                id_token's ``nonce`` claim MUST match (constant-time) or this
                raises — the id_token replay/injection defense.

        Returns:
            Decoded token claims

        Raises:
            SSOAuthError: If validation fails or the nonce does not match
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

            # Nonce enforced ONLY against the verified payload above.
            self._enforce_nonce(payload, nonce)

            return payload

        except jwt.ExpiredSignatureError:
            raise SSOAuthError("ID token has expired")
        except jwt.InvalidAudienceError:
            raise SSOAuthError("Invalid token audience")
        except jwt.InvalidIssuerError:
            raise SSOAuthError("Invalid token issuer")
        except jwt.InvalidTokenError as e:
            raise SSOAuthError(f"Invalid ID token: {e}")
