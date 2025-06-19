"""Authentication utilities for blog API interactions."""

import logging
import os
from typing import Optional, Any

import requests
from msal import ConfidentialClientApplication
from requests_ntlm import HttpNtlmAuth

from app.core.config import Config

logger = logging.getLogger(__name__)


class BlogAuthentication:
    """Provide authentication credentials for the blog API.

    The authentication method is chosen based on the ``BLOG_API_AUTH_METHOD``
    environment variable. Supported methods are ``oauth2``, ``msal``,
    ``ntlm`` and ``none`` (default).
    """

    def __init__(self) -> None:
        self.method = os.getenv("BLOG_API_AUTH_METHOD", "none").lower()

    def blog_auth(self) -> Optional[Any]:
        """Return credentials suitable for ``requests`` based on settings."""
        if self.method == "oauth2":
            return self._oauth2_token()
        if self.method == "msal":
            return self._msal_token()
        if self.method == "ntlm":
            return self._ntlm_auth()
        logger.info("Blog authentication disabled or unknown method: %s", self.method)
        return None

    def _oauth2_token(self) -> Optional[str]:
        client_id = os.getenv("BLOG_API_OAUTH2_CLIENT_ID")
        client_secret = os.getenv("BLOG_API_OAUTH2_CLIENT_SECRET")
        token_url = os.getenv("BLOG_API_OAUTH2_TOKEN_URL")
        if not all([client_id, client_secret, token_url]):
            logger.error("OAuth2 configuration incomplete")
            return None
        try:
            response = requests.post(
                token_url,
                data={"grant_type": "client_credentials"},
                auth=(client_id, client_secret),
                timeout=Config.HTTP_TIMEOUT,
            )
            response.raise_for_status()
            return response.json().get("access_token")
        except Exception as exc:
            logger.error("OAuth2 token fetch failed: %s", exc)
            return None

    def _msal_token(self) -> Optional[str]:
        client_id = os.getenv("BLOG_API_MSAL_CLIENT_ID")
        client_secret = os.getenv("BLOG_API_MSAL_CLIENT_SECRET")
        tenant_id = os.getenv("BLOG_API_MSAL_TENANT_ID")
        scope = os.getenv("BLOG_API_MSAL_SCOPE")
        if not all([client_id, client_secret, tenant_id, scope]):
            logger.error("MSAL configuration incomplete")
            return None
        authority = f"https://login.microsoftonline.com/{tenant_id}"
        app = ConfidentialClientApplication(
            client_id=client_id,
            client_credential=client_secret,
            authority=authority,
        )
        try:
            result = app.acquire_token_for_client(scopes=[scope])
            return result.get("access_token")
        except Exception as exc:
            logger.error("MSAL token acquisition failed: %s", exc)
            return None

    def _ntlm_auth(self) -> Optional[HttpNtlmAuth]:
        user = os.getenv("BLOG_API_NTLM_USER")
        password = os.getenv("BLOG_API_NTLM_PASSWORD")
        domain = os.getenv("BLOG_API_NTLM_DOMAIN")
        if not all([user, password, domain]):
            logger.error("NTLM configuration incomplete")
            return None
        return HttpNtlmAuth(f"{domain}\\{user}", password)
