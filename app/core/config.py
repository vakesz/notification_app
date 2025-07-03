"""Configuration management for the notification app."""

import logging
import os
from urllib.parse import urlparse

from dotenv import load_dotenv

logger = logging.getLogger(__name__)


# Load environment variables
load_dotenv()


class Config:
    """Base configuration for the notification app."""

    # Flask
    SECRET_KEY = os.environ.get("SECRET_KEY")
    if not SECRET_KEY:
        raise ValueError("SECRET_KEY must be set in the environment for security.")

    # Azure AD
    AAD_CLIENT_ID = os.environ.get("AAD_CLIENT_ID")
    AAD_CLIENT_SECRET = os.environ.get("AAD_CLIENT_SECRET")
    AAD_TENANT_ID = os.environ.get("AAD_TENANT_ID")
    AAD_REDIRECT_URI = os.environ.get("AAD_REDIRECT_URI")
    AUTHORITY = f"https://login.microsoftonline.com/{AAD_TENANT_ID}" if AAD_TENANT_ID else None
    SCOPE = ["User.Read"]

    # Application
    APP_NAME = os.environ.get("APP_NAME", "Blog Notifications Parser")
    BLOG_API_URL = os.environ.get("BLOG_API_URL")

    # Blog API authentication
    BLOG_API_AUTH_METHOD = os.environ.get("BLOG_API_AUTH_METHOD", "none").lower()
    BLOG_API_OAUTH2_CLIENT_ID = os.environ.get("BLOG_API_OAUTH2_CLIENT_ID")
    BLOG_API_OAUTH2_CLIENT_SECRET = os.environ.get("BLOG_API_OAUTH2_CLIENT_SECRET")
    BLOG_API_OAUTH2_TOKEN_URL = os.environ.get("BLOG_API_OAUTH2_TOKEN_URL")
    BLOG_API_MSAL_CLIENT_ID = os.environ.get("BLOG_API_MSAL_CLIENT_ID")
    BLOG_API_MSAL_CLIENT_SECRET = os.environ.get("BLOG_API_MSAL_CLIENT_SECRET")
    BLOG_API_MSAL_TENANT_ID = os.environ.get("BLOG_API_MSAL_TENANT_ID")
    BLOG_API_MSAL_SCOPE = os.environ.get("BLOG_API_MSAL_SCOPE")
    BLOG_API_NTLM_USER = os.environ.get("BLOG_API_NTLM_USER")
    BLOG_API_NTLM_PASSWORD = os.environ.get("BLOG_API_NTLM_PASSWORD")
    BLOG_API_NTLM_DOMAIN = os.environ.get("BLOG_API_NTLM_DOMAIN")

    # Request settings
    HTTP_TIMEOUT = int(os.environ.get("HTTP_TIMEOUT", "30"))
    HTTP_MAX_RETRIES = int(os.environ.get("HTTP_MAX_RETRIES", "3"))
    HTTP_RETRY_BACKOFF = float(os.environ.get("HTTP_RETRY_BACKOFF", "1"))

    # Polling interval in minutes
    POLLING_INTERVAL_MINUTES = int(os.environ.get("POLLING_INTERVAL_MINUTES", "15"))
    POLLING_BACKOFF_FACTOR = float(os.environ.get("POLLING_BACKOFF_FACTOR", "1.5"))
    POLLING_MAX_BACKOFF = int(os.environ.get("POLLING_MAX_BACKOFF", "3600"))  # 1 hour

    # Auth token lifetime in days for cleanup
    AUTH_TOKEN_TTL_DAYS = int(os.environ.get("AUTH_TOKEN_TTL_DAYS", "30"))

    # Push notification settings
    PUSH_TTL = int(os.environ.get("PUSH_TTL", "86400"))  # seconds

    # Database
    APP_DATABASE_PATH = os.environ.get("APP_DATABASE_PATH", "db/posts.db")
    DB_TIMEOUT = int(os.environ.get("DB_TIMEOUT", "30"))

    # VAPID keys for Web Push
    PUSH_VAPID_PUBLIC_KEY = os.environ.get("PUSH_VAPID_PUBLIC_KEY")
    PUSH_VAPID_PRIVATE_KEY = os.environ.get("PUSH_VAPID_PRIVATE_KEY")
    PUSH_VAPID_CLAIMS = {"sub": f"mailto:{os.environ.get('PUSH_CONTACT_EMAIL')}"}
    TOKEN_ENCRYPTION_KEY = os.environ.get("TOKEN_ENCRYPTION_KEY")

    @classmethod
    def validate(cls) -> None:
        """Validate required configuration."""
        required_vars = [
            "SECRET_KEY",
            "AAD_CLIENT_ID",
            "AAD_CLIENT_SECRET",
            "AAD_TENANT_ID",
            "AAD_REDIRECT_URI",
            "BLOG_API_URL",
            "PUSH_VAPID_PUBLIC_KEY",
            "PUSH_VAPID_PRIVATE_KEY",
        ]
        missing = [var for var in required_vars if not getattr(cls, var)]
        if missing:
            raise ValueError(f"Missing required configuration: {', '.join(missing)}")

        # Validate URLs
        if cls.BLOG_API_URL:
            if not cls.BLOG_API_URL.startswith(("http://", "https://")):
                raise ValueError(f"BLOG_API_URL must start with http:// or https://: {cls.BLOG_API_URL}")

            # Validate URL format
            try:
                parsed = urlparse(cls.BLOG_API_URL)
                if not parsed.netloc:
                    raise ValueError(f"Invalid BLOG_API_URL format: {cls.BLOG_API_URL}")
            except Exception as e:
                raise ValueError(f"Invalid BLOG_API_URL format: {cls.BLOG_API_URL}") from e

        # Validate numeric settings
        if cls.HTTP_TIMEOUT < 1:
            raise ValueError("HTTP_TIMEOUT must be at least 1 second")
        if cls.HTTP_MAX_RETRIES < 1:
            raise ValueError("HTTP_MAX_RETRIES must be at least 1")
        if cls.HTTP_RETRY_BACKOFF <= 0:
            raise ValueError("HTTP_RETRY_BACKOFF must be positive")
        if cls.POLLING_INTERVAL_MINUTES < 1:
            raise ValueError("POLLING_INTERVAL_MINUTES must be at least 1 minute")
        if cls.POLLING_BACKOFF_FACTOR < 1:
            raise ValueError("POLLING_BACKOFF_FACTOR must be at least 1")
        if cls.POLLING_MAX_BACKOFF < cls.POLLING_INTERVAL_MINUTES:
            raise ValueError("POLLING_MAX_BACKOFF must be greater than POLLING_INTERVAL_MINUTES")
        if cls.AUTH_TOKEN_TTL_DAYS < 1:
            raise ValueError("AUTH_TOKEN_TTL_DAYS must be at least 1 day")
        if cls.PUSH_TTL < 0:
            raise ValueError("PUSH_TTL must be non-negative")


class DevelopmentConfig(Config):
    """Development configuration."""


class ProductionConfig(Config):
    """Production configuration."""


# Select configuration based on environment
config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
