"""GitHub OAuth2 SSO Provider.

Provides OAuth2 authentication with GitHub.

Note: GitHub uses OAuth2 but not OIDC (no ID token).
User info comes from the /user API endpoint.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from nexus.auth.sso.base import (
    BaseSSOProvider,
    SSOAuthError,
    SSOTokenResponse,
    SSOUserInfo,
)

logger = logging.getLogger(__name__)


class GitHubProvider(BaseSSOProvider):
    """GitHub OAuth2 provider.

    Usage:
        >>> from nexus.auth.sso import GitHubProvider
        >>>
        >>> github = GitHubProvider(
        ...     client_id="your-client-id",
        ...     client_secret="your-client-secret",
        ... )

    Endpoints:
        - Authorization: https://github.com/login/oauth/authorize
        - Token: https://github.com/login/oauth/access_token
        - User Info: https://api.github.com/user
        - Emails: https://api.github.com/user/emails

    Note:
        GitHub doesn't support OIDC/ID tokens. User information
        must be fetched from the API using the access token.
    """

    name = "github"

    AUTHORIZATION_URL = "https://github.com/login/oauth/authorize"
    TOKEN_URL = "https://github.com/login/oauth/access_token"
    USERINFO_URL = "https://api.github.com/user"
    EMAILS_URL = "https://api.github.com/user/emails"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        scopes: Optional[List[str]] = None,
        timeout: int = 30,
    ):
        """Initialize GitHub provider.

        Args:
            client_id: OAuth App client ID
            client_secret: OAuth App client secret
            scopes: OAuth2 scopes (default: user:email)
            timeout: HTTP request timeout
        """
        super().__init__(client_id, client_secret, timeout)
        self.scopes = scopes or ["user:email"]

        logger.info("GitHubProvider initialized")

    def get_authorization_url(
        self,
        state: str,
        redirect_uri: str,
        scope: Optional[str] = None,
        allow_signup: bool = True,
        **kwargs,
    ) -> str:
        """Generate GitHub authorization URL.

        Args:
            state: CSRF state parameter
            redirect_uri: Callback URL
            scope: Override default scopes
            allow_signup: Allow new user signups (default: True)
            **kwargs: Additional parameters (login hint)

        Returns:
            Authorization URL
        """
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "scope": scope or " ".join(self.scopes),
            "state": state,
            "allow_signup": str(allow_signup).lower(),
        }
        params.update(kwargs)

        return f"{self.AUTHORIZATION_URL}?{urlencode(params)}"

    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
    ) -> SSOTokenResponse:
        """Exchange authorization code for access token.

        Args:
            code: Authorization code
            redirect_uri: Callback URL

        Returns:
            Token response (no id_token for GitHub)

        Raises:
            SSOAuthError: If exchange fails
        """
        client = await self._get_http_client()

        response = await client.post(
            self.TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            },
            headers={"Accept": "application/json"},
        )

        if response.status_code != 200:
            logger.error(
                "GitHub token exchange failed: status=%d body=%s",
                response.status_code,
                response.text,
            )
            raise SSOAuthError(
                f"Token exchange failed with status {response.status_code}"
            )

        data = response.json()

        if "error" in data:
            logger.error(
                "GitHub token exchange error: %s - %s",
                data.get("error"),
                data.get("error_description"),
            )
            raise SSOAuthError("Token exchange failed: provider returned an error")

        return SSOTokenResponse(
            access_token=data["access_token"],
            id_token=None,
            refresh_token=None,
            token_type=data.get("token_type", "Bearer"),
            expires_in=0,  # GitHub tokens don't expire
            scope=data.get("scope"),
        )

    async def get_user_info(self, access_token: str) -> SSOUserInfo:
        """Fetch user info from GitHub API.

        Args:
            access_token: OAuth2 access token

        Returns:
            Normalized user information
        """
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github.v3+json",
        }

        user_data = await self._get_json(self.USERINFO_URL, headers=headers)

        email = user_data.get("email")
        email_verified = False

        if not email:
            try:
                emails_data = await self._get_json(self.EMAILS_URL, headers=headers)
                for email_obj in emails_data:
                    if email_obj.get("primary"):
                        email = email_obj.get("email")
                        email_verified = email_obj.get("verified", False)
                        break
            except Exception as e:
                logger.warning(f"Failed to fetch GitHub emails: {e}")

        return SSOUserInfo(
            provider_user_id=str(user_data.get("id")),
            email=email,
            email_verified=email_verified,
            name=user_data.get("name"),
            given_name=None,
            family_name=None,
            picture=user_data.get("avatar_url"),
            locale=None,
            raw_data=user_data,
        )

    def validate_id_token(self, id_token: str) -> Dict[str, Any]:
        """GitHub doesn't support ID tokens.

        Raises:
            SSOAuthError: Always, GitHub doesn't use OIDC
        """
        raise SSOAuthError(
            "GitHub doesn't support ID tokens. "
            "Use get_user_info() with the access token instead."
        )
