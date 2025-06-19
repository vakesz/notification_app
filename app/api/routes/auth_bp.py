"""Authentication Blueprint for handling user login, logout, and session management."""

import secrets
import logging
import time
from flask import (
    Blueprint,
    render_template,
    session,
    redirect,
    url_for,
    request,
    flash,
    current_app,
)

from app.core.utils.session_utils import _validate_session, _token_lock

# Blueprint for authentication routes
auth_bp = Blueprint("auth_bp", __name__)
logger = logging.getLogger(__name__)

# --- Helper Functions ---


def _clear_session(message: str = None, category: str = "info"):
    """Clear the session and optionally flash a message."""
    session.clear()
    if message:
        flash(message, category)


def _auth_redirect(target: str = "dashboard_bp.dashboard"):
    """Redirect to a target endpoint by name."""
    return redirect(url_for(target))


def _ensure_valid_session() -> bool:
    """Check if current session is valid (user + token + validation)."""
    user = session.get("user")
    token = request.cookies.get("access_token")
    return bool(user and token and _validate_session())


# --- Routes ---


@auth_bp.route("/")
def index():
    """Redirect to dashboard if logged-in, otherwise to login."""
    if _ensure_valid_session():
        return _auth_redirect()

    if session.get("state"):
        return redirect(url_for("auth_bp.login"))

    if session.get("user") or request.cookies.get("access_token"):
        _clear_session("Your session has expired. Please log in again.", "info")

    return redirect(url_for("auth_bp.login"))


@auth_bp.route("/login")
def login_page():
    """Render login page or redirect if already authenticated."""
    if _ensure_valid_session():
        return _auth_redirect()
    if session.get("user") or request.cookies.get("access_token"):
        _clear_session("Your session has expired. Please log in again.")
    return render_template(
        "login.html", app_name=current_app.config.get("APP_NAME", "App")
    )


@auth_bp.route("/auth/login")
def login():
    """Initiate Microsoft SSO login flow."""
    session.pop("state", None)
    session["state"] = secrets.token_urlsafe(32)
    auth_url = current_app.auth_service.get_authorization_url(session["state"])
    logger.info("Redirecting to Microsoft login: %s...", auth_url[:100])
    return redirect(auth_url)


@auth_bp.route("/auth/callback")
def auth_callback():
    """Handle OAuth callback and establish user session."""

    def _fail(message: str):
        logger.error(
            "%s | endpoint=%s | ip=%s", message, request.path, request.remote_addr
        )
        flash(message, "error")
        return redirect(url_for("auth_bp.login"))

    code = request.args.get("code")
    if not code:
        return _fail("Authentication failed: No authorization code received")

    state = request.args.get("state")
    session_state = session.get("state", None)
    if not state or not session_state or state != session_state:
        return _fail("Authentication failed: Invalid state parameter")

    # Clear state after successful validation
    session.pop("state", None)

    token_resp = current_app.auth_service.acquire_token(code)
    if not token_resp:
        return _fail("Authentication failed: Could not acquire access token")

    user_info = current_app.auth_service.get_user_info(token_resp["access_token"])
    if not user_info:
        return _fail("Authentication failed: Could not retrieve user info")

    # Store user info in session
    session["user"] = user_info
    session["token_expiry"] = int(time.time()) + token_resp.get("expires_in", 3600)

    # Prepare response and set OAuth tokens in cookies
    response = _auth_redirect()
    response.set_cookie(
        "access_token",
        token_resp["access_token"],
        max_age=token_resp.get("expires_in", 3600),
        httponly=True,
        secure=True,
        samesite="Strict",
    )
    if token_resp.get("refresh_token"):
        response.set_cookie(
            "refresh_token",
            token_resp["refresh_token"],
            httponly=True,
            secure=True,
            samesite="Strict",
        )

    # Store token globally
    with _token_lock:
        current_app.access_token_storage.access_token = token_resp["access_token"]

    # Verify claims
    claims = current_app.auth_service.get_user_claims(token_resp["access_token"])
    if not claims:
        return _fail("Authentication failed: Could not retrieve user claims")

    flash("Successfully logged in!", "success")
    return response


@auth_bp.route("/logout")
def logout():
    """Log out user and clear session."""
    user_name = session.get("user", {}).get("name", "Unknown")
    ip = request.remote_addr

    # Clear session and tokens
    current_app.access_token_storage.access_token = None
    _clear_session()
    logger.info("User logged out | user=%s | ip=%s", user_name, ip)

    logout_url = current_app.auth_service.get_logout_url(
        url_for("auth_bp.login", _external=True)
    )
    response = redirect(logout_url)
    response.set_cookie(
        "access_token", "", expires=0, httponly=True, secure=True, samesite="Strict"
    )
    response.set_cookie(
        "refresh_token", "", expires=0, httponly=True, secure=True, samesite="Strict"
    )
    flash("Successfully logged out!", "info")
    return response
