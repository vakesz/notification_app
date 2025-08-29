"""Authentication utilities for blog API interactions."""

import logging
import os
from typing import Any

import requests
from msal import ConfidentialClientApplication
from requests_ntlm import HttpNtlmAuth

from app.core.config import Config

logger = logging.getLogger(__name__)


class BlogAuthentication:
    """Provide authentication credentials for the blog API.

    The authentication method is chosen based on the ``BLOG_API_AUTH_METHOD``
    environment variable. Supported methods are ``oauth2``, ``msal``,
    ``ntlm``, ``cookie`` and ``none`` (default).
    """

    def __init__(self) -> None:
        self.method = os.getenv("BLOG_API_AUTH_METHOD", "none").lower()

    def blog_auth(self) -> Any | None:
        """Return credentials suitable for ``requests`` based on settings."""
        if self.method == "oauth2":
            return self._oauth2_token()
        if self.method == "msal":
            return self._msal_token()
        if self.method == "ntlm":
            return self._ntlm_auth()
        if self.method == "cookie":
            return self._cookie_auth()
        logger.info("Blog authentication disabled or unknown method: %s", self.method)
        return None

    def _oauth2_token(self) -> str | None:
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

    def _msal_token(self) -> str | None:
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

    def _ntlm_auth(self) -> HttpNtlmAuth | None:
        user = os.getenv("BLOG_API_NTLM_USER")
        password = os.getenv("BLOG_API_NTLM_PASSWORD")
        domain = os.getenv("BLOG_API_NTLM_DOMAIN")
        if not all([user, password, domain]):
            logger.error("NTLM configuration incomplete")
            return None
        return HttpNtlmAuth(f"{domain}\\{user}", password)

    def _cookie_auth(self) -> dict | None:
        """Return a cookie descriptor for requests session when configured.

        Supported env vars:
        - BLOG_API_COOKIES: A semicolon-separated cookie string, e.g.
            "name1=value1; name2=value2"
        - BLOG_API_COOKIE_NAME / BLOG_API_COOKIE_VALUE: Fallback single cookie
        - BLOG_API_COOKIE_DOMAIN: Optional cookie domain override
        - BLOG_API_COOKIE_PATH: Optional cookie path (defaults to '/')
        """
        cookie_string = os.getenv("BLOG_API_COOKIES", "").strip()
        cookies: dict[str, str] = {}

        if cookie_string:
            # Parse semicolon-separated cookie pairs
            try:
                for part in cookie_string.split(";"):
                    token = part.strip()
                    if not token:
                        continue
                    if "=" not in token:
                        logger.warning("Skipping invalid cookie pair (no '='): %s", token)
                        continue
                    k, v = token.split("=", 1)
                    k = k.strip()
                    v = v.strip()
                    if k:
                        cookies[k] = v
            except Exception as exc:
                logger.error("Failed to parse BLOG_API_COOKIES: %s", exc)
                return None
        else:
            # Fallback to single cookie env vars
            name = os.getenv("BLOG_API_COOKIE_NAME")
            value = os.getenv("BLOG_API_COOKIE_VALUE")
            if not name or not value:
                logger.error("Cookie auth configuration incomplete: provide BLOG_API_COOKIES or name/value")
                return None
            cookies[name] = value

        if not cookies:
            logger.error("No valid cookies provided for cookie auth")
            return None

        domain = os.getenv("BLOG_API_COOKIE_DOMAIN")
        path = os.getenv("BLOG_API_COOKIE_PATH", "/")
        return {
            "cookies": cookies,
            "domain": domain,
            "path": path,
        }
