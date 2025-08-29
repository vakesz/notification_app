"""Session utilities for authentication and token management."""

import logging
import secrets
import time
from functools import wraps
from threading import Lock

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app, redirect, session, url_for

from app.core.config import Config

logger = logging.getLogger(__name__)


class AccessTokenStore:
    """Persist access tokens using the application's database."""

    def __init__(self) -> None:
        key = Config.TOKEN_ENCRYPTION_KEY
        self._cipher = Fernet(key) if key else None

    def set_token(self, token: str | None) -> None:
        """Store the access token in the session and database."""
        if token is None:
            self.clear_token()
            return
        sid = session.get("_sid")
        if not sid:
            sid = secrets.token_urlsafe(16)
            session["_sid"] = sid
        user = session.get("user", {})
        user_id = user.get("preferred_username") or user.get("name") or "unknown"
        if self._cipher:
            token = self._cipher.encrypt(token.encode()).decode()
        current_app.database_manager.store_token(sid, user_id, token)

    def get_token(self) -> str | None:
        """Retrieve the access token from the session or database."""
        sid = session.get("_sid")
        if not sid:
            return None
        token = current_app.database_manager.get_token(sid)
        if token and self._cipher:
            try:
                token = self._cipher.decrypt(token.encode()).decode()
            except InvalidToken:
                logger.error("Token decryption failed")
                return None
        return token

    def clear_token(self) -> None:
        """Clear the access token from the session and database."""
        sid = session.pop("_sid", None)
        if sid:
            current_app.database_manager.delete_token(sid)

    access_token = property(get_token, set_token)


access_token_storage = AccessTokenStore()
_token_lock = Lock()  # Used by flask_login to ensure thread safety

# --- Helper Functions ---


def _has_valid_user() -> bool:
    """Check if a user exists in session."""
    return bool(session.get("user"))


def _redirect_to_login():
    """Redirect helper for unauthenticated access."""
    return redirect(url_for("auth_bp.login"))


# --- Core Utilities ---


def _validate_session() -> bool:
    """Validate that session contains an authenticated user and valid token."""
    if not _has_valid_user():
        return False
    expiry = session.get("token_expiry")
    if expiry and time.time() > expiry:
        return False
    return True


def require_auth(f):
    """Decorator that enforces authentication on route handlers."""

    @wraps(f)
    def wrapper(*args, **kwargs):
        if not _validate_session():
            return _redirect_to_login()
        return f(*args, **kwargs)

    return wrapper
