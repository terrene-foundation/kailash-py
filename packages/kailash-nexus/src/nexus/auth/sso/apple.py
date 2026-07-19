"""Apple Sign-In SSO Provider.

Provides OAuth2/OIDC authentication with Apple.

Apple Sign-In has unique characteristics:
    - Uses ES256 (ECDSA) for JWT signing
    - Client secret is a JWT signed with private key
    - Name is only returned on FIRST authorization
    - Email relay service for privacy

Evidence:
    - production SSO implementation reference
"""

from __future__ import annotations

import logging
import time
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


class AppleProvider(BaseSSOProvider):
    """Apple Sign-In provider.

    Usage:
        >>> from nexus.auth.sso import AppleProvider
        >>>
        >>> apple = AppleProvider(
        ...     team_id="YOUR_TEAM_ID",
        ...     client_id="com.yourapp.service",
        ...     key_id="YOUR_KEY_ID",
        ...     private_key_path="/path/to/AuthKey.p8",
        ... )

    Endpoints:
        - Authorization: https://appleid.apple.com/auth/authorize
        - Token: https://appleid.apple.com/auth/token
        - JWKS: https://appleid.apple.com/auth/keys

    Important Notes:
        - Apple only sends user's name on FIRST authorization
        - Store the name when received, it won't be sent again
        - Email may be a relay address (@privaterelay.appleid.com)
    """

    name = "apple"

    AUTHORIZATION_URL = "https://appleid.apple.com/auth/authorize"
    TOKEN_URL = "https://appleid.apple.com/auth/token"
    JWKS_URL = "https://appleid.apple.com/auth/keys"

    def __init__(
        self,
        team_id: str,
        client_id: str,
        key_id: str,
        private_key: Optional[str] = None,
        private_key_path: Optional[str] = None,
        scopes: Optional[List[str]] = None,
        timeout: int = 30,
    ):
        """Initialize Apple provider.

        Args:
            team_id: Apple Developer Team ID
            client_id: Service ID (e.g., "com.yourapp.service")
            key_id: Key ID from Apple Developer console
            private_key: Private key content (PEM format)
            private_key_path: Path to private key file (.p8)
            scopes: OAuth2 scopes (default: name, email)
            timeout: HTTP request timeout

        Raises:
            ValueError: If neither private_key nor private_key_path provided
        """
        super().__init__(client_id, None, timeout)

        self.team_id = team_id
        self.key_id = key_id
        self.scopes = scopes or ["name", "email"]

        if private_key:
            self._private_key = private_key
        elif private_key_path:
            with open(private_key_path, "r") as f:
                self._private_key = f.read()
        else:
            raise ValueError("Either private_key or private_key_path required")

        self._jwks_client = PyJWKClient(
            self.JWKS_URL,
            cache_keys=True,
            lifespan=86400,  # Apple keys change rarely, cache for 24h
        )

        logger.info(f"AppleProvider initialized: team={team_id}, client={client_id}")

    def _generate_client_secret(self) -> str:
        """Generate client secret JWT for Apple.

        Apple's client_secret is a JWT signed with your private key.

        Returns:
            JWT client secret (valid for 6 months max)
        """
        now = int(time.time())
        exp = now + (86400 * 180)  # 180 days (max allowed)

        payload = {
            "iss": self.team_id,
            "iat": now,
            "exp": exp,
            "aud": "https://appleid.apple.com",
            "sub": self.client_id,
        }

        headers = {
            "kid": self.key_id,
            "alg": "ES256",
        }

        return jwt.encode(
            payload,
            self._private_key,
            algorithm="ES256",
            headers=headers,
        )

    def get_authorization_url(
        self,
        state: str,
        redirect_uri: str,
        scope: Optional[str] = None,
        response_mode: str = "form_post",
        code_challenge: Optional[str] = None,
        **kwargs,
    ) -> str:
        """Generate Apple authorization URL.

        Args:
            state: CSRF state parameter
            redirect_uri: Callback URL
            scope: Override default scopes
            response_mode: "query" or "form_post" (recommended)
            code_challenge: PKCE (RFC 7636) S256 challenge. When present, emits
                ``code_challenge`` + ``code_challenge_method=S256``.
            **kwargs: Additional parameters (incl. ``nonce`` for OIDC id_token
                replay defense)

        Returns:
            Authorization URL

        Note:
            Apple recommends response_mode="form_post" for security.
        """
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": scope or " ".join(self.scopes),
            "state": state,
            "response_mode": response_mode,
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
        client_secret = self._generate_client_secret()

        data = {
            "client_id": self.client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
        if code_verifier:
            data["code_verifier"] = code_verifier

        response = await self._post_form(self.TOKEN_URL, data)

        return SSOTokenResponse(
            access_token=response.get("access_token", ""),
            id_token=response.get("id_token"),
            refresh_token=response.get("refresh_token"),
            token_type=response.get("token_type", "Bearer"),
            expires_in=response.get("expires_in", 3600),
        )

    async def get_user_info(self, access_token: str) -> SSOUserInfo:
        """Get user info from Apple.

        Note: Apple doesn't have a userinfo endpoint.
        User info must be extracted from the ID token.

        Args:
            access_token: Not used for Apple

        Returns:
            Empty SSOUserInfo (use validate_id_token instead)
        """
        logger.warning(
            "Apple doesn't provide userinfo endpoint. "
            "Use validate_id_token() to get user info from ID token."
        )
        return SSOUserInfo(provider_user_id="", raw_data={})

    def validate_id_token(
        self,
        id_token: str,
        user_data: Optional[Dict[str, Any]] = None,
        nonce: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Validate and decode Apple ID token.

        Args:
            id_token: JWT ID token
            user_data: User data from authorization (name, email on first auth)
            nonce: The nonce minted at authorization time. When present, the
                id_token's ``nonce`` claim MUST match (constant-time) or this
                raises — the id_token replay/injection defense.

        Returns:
            Decoded token claims with user data merged

        Raises:
            SSOAuthError: If validation fails or the nonce does not match

        Note:
            Apple only sends user's name on FIRST authorization.
            The user_data parameter contains this data from the callback.
        """
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(id_token)

            payload = jwt.decode(
                id_token,
                signing_key.key,
                algorithms=["ES256"],
                audience=self.client_id,
                issuer="https://appleid.apple.com",
            )

            # Nonce enforced ONLY against the verified payload above, before
            # merging any non-token user_data.
            self._enforce_nonce(payload, nonce)

            if user_data:
                if "name" in user_data:
                    name_data = user_data["name"]
                    payload["given_name"] = name_data.get("firstName")
                    payload["family_name"] = name_data.get("lastName")
                    payload["name"] = (
                        f"{name_data.get('firstName', '')} "
                        f"{name_data.get('lastName', '')}"
                    ).strip()

                if "email" in user_data:
                    payload["email"] = user_data["email"]

            real_user = payload.get("real_user_status")
            if real_user is not None:
                payload["is_likely_real_user"] = real_user == 2

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

    def extract_user_info(
        self,
        id_token_claims: Dict[str, Any],
    ) -> SSOUserInfo:
        """Extract SSOUserInfo from validated ID token claims.

        Args:
            id_token_claims: Claims from validate_id_token()

        Returns:
            Normalized user information
        """
        return SSOUserInfo(
            provider_user_id=id_token_claims.get("sub"),
            email=id_token_claims.get("email"),
            email_verified=id_token_claims.get("email_verified", False),
            name=id_token_claims.get("name"),
            given_name=id_token_claims.get("given_name"),
            family_name=id_token_claims.get("family_name"),
            raw_data=id_token_claims,
        )
