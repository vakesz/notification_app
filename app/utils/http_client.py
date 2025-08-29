"""HTTP client utilities for making requests with session management."""

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from requests_ntlm import HttpNtlmAuth
from urllib3.util.retry import Retry

from app.core.config import Config
from app.version import __version__ as version

if TYPE_CHECKING:  # pragma: no cover - imported for type checking only
    from app.core.blog_security import BlogAuthentication

logger = logging.getLogger(__name__)


class HTTPClientError(Exception):
    """Base exception for HTTP client errors."""


class HTTPClient:
    """HTTP client with connection pooling, session persistence, and retry logic."""

    def __init__(
        self,
        base_url: str,
        client_id: str | None = None,
        client_secret: str | None = None,
        tenant_id: str | None = None,
        timeout: int = 30,
        auth_provider: Callable[[], Any | None] | None = None,
        max_retries: int = Config.HTTP_MAX_RETRIES,
        backoff_factor: float = Config.HTTP_RETRY_BACKOFF,
    ) -> None:
        """Initialize HTTP client with configuration."""
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.tenant_id = tenant_id
        self.timeout = timeout
        self._auth_provider = auth_provider
        self._max_retries = max_retries
        self._backoff_factor = backoff_factor

        # Create a persistent session with retry strategy
        self.session = requests.Session()

        # Configure retry strategy
        retry_strategy = Retry(
            total=self._max_retries,
            backoff_factor=self._backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        # Set default headers
        self._update_headers()

    def _update_headers(self) -> None:
        """Update session headers with user agent."""

        self.session.headers.update(
            {
                "User-Agent": f"NotificationApp/{version} (HTTP Client)",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Connection": "keep-alive",
                "Cache-Control": "max-age=0",
            }
        )

    def _apply_auth(self, headers: dict[str, str]) -> dict[str, str]:
        """Apply blog API authentication if configured."""
        if not self._auth_provider:
            self.session.auth = None
            return headers

        creds = self._auth_provider()
        if creds is None:
            self.session.auth = None
            return headers

        if isinstance(creds, HttpNtlmAuth):
            self.session.auth = creds
        elif isinstance(creds, str):
            headers["Authorization"] = f"Bearer {creds}"
            self.session.auth = None
        elif isinstance(creds, dict):
            # Support cookie and header based auth via dict
            # Optional custom headers
            custom_headers = creds.get("headers")
            if isinstance(custom_headers, dict):
                headers.update({str(k): str(v) for k, v in custom_headers.items()})

            # Optional cookie injection
            cookie_map = creds.get("cookies")
            if isinstance(cookie_map, dict) and cookie_map:
                parsed = urlparse(self.base_url)
                domain = creds.get("domain") or parsed.hostname
                path = creds.get("path", "/")
                for cname, cval in cookie_map.items():
                    self._set_cookie_safely(cname, cval, domain=domain, path=path)
            self.session.auth = None
        else:
            logger.warning("Unsupported blog auth credentials: %s", type(creds))
            self.session.auth = None

        return headers

    def _build_url(self, path: str) -> str:
        """Build full URL from path."""
        path = path.lstrip("/")
        return f"{self.base_url}/{path}"

    def _set_cookie_safely(self, name: str, value: str, *, domain: str | None, path: str) -> None:
        """Set a cookie on the session while guarding against cookie errors."""
        try:
            # RequestsCookieJar delegates to http.cookiejar which may raise CookieError/ValueError
            self.session.cookies.set(name, value, domain=domain, path=path)
        except (ValueError, TypeError) as exc:
            logger.warning(
                "Failed to set cookie %s for domain %s: %s",
                name,
                domain,
                exc,
            )

    def _handle_response(self, response: requests.Response) -> str:
        """Handle HTTP response and raise appropriate exceptions."""
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            if response.status_code == 403:
                error_msg = f"Access forbidden (403) - the server is blocking our requests. URL: {response.url}"
                logger.exception(error_msg)
                logger.info("Try using a VPN or different network if this persists")
            elif response.status_code == 429:
                error_msg = f"Rate limited (429) - too many requests. URL: {response.url}"
                logger.exception(error_msg)
            else:
                error_msg = f"HTTP {response.status_code} error: {e}"
                logger.exception(error_msg)
            raise HTTPClientError(error_msg) from e

        # Check if response has content
        if not response.text.strip():
            logger.warning("Received empty response")
            return ""

        # Return response text if successful
        return response.text

    def get(
        self,
        path: str = "",
        headers: dict[str, str] | None = None,
        timeout: int | None = None,
        params: dict[str, Any] | None = None,
    ) -> str:
        """Make GET request."""
        url = self._build_url(path) if path else self.base_url

        # Refresh default headers before each request
        self._update_headers()

        request_headers = self.session.headers.copy()
        if headers:
            request_headers.update(headers)

        # Apply authentication if configured
        request_headers = self._apply_auth(request_headers)

        try:
            response = self.session.get(
                url,
                headers=request_headers,
                timeout=timeout or self.timeout,
                params=params,
            )
            return self._handle_response(response)
        except requests.exceptions.RequestException as e:
            error_msg = f"GET request failed: {e}"
            logger.exception(error_msg)
            raise HTTPClientError(error_msg) from e

    def close(self) -> None:
        """Close the session and release resources."""
        self.session.close()


class BlogClient(HTTPClient):
    """Client for interacting with the blog API."""

    def __init__(self, *args: Any, blog_auth: "BlogAuthentication | None" = None, **kwargs: Any) -> None:
        provider = blog_auth.blog_auth if blog_auth else None
        super().__init__(*args, auth_provider=provider, **kwargs)
        self._blog_auth = blog_auth

    def get_content(
        self,
        path: str = "",
        headers: dict[str, str] | None = None,
    ) -> str:
        """Get HTML content from the blog."""
        try:
            return self.get(path=path, headers=headers)
        except HTTPClientError as e:
            logger.exception("Failed to get HTML source: %s", e)
            raise
