"""Dashboard blueprint routes."""

import io
import logging
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    session,
    url_for,
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from app.core.config import Config
from app.core.utils.session_utils import _validate_session, require_auth

# Blueprint for dashboard routes
dashboard_bp = Blueprint("dashboard_bp", __name__)
logger = logging.getLogger(__name__)

# Initialize rate limiter
# TODO @vakesz: Configure rate limiter to use Redis storage backend for production
limiter = Limiter(key_func=get_remote_address)

# --- Helper Functions ---


def _get_user_key() -> str | None:
    """Get the user key from session for identification."""
    user = session.get("user") or {}
    return user.get("preferred_username") or user.get("name")


def _render_dashboard_context(**overrides: Any) -> dict[str, Any]:
    """Gather default context for dashboard rendering.

    Args:
        **overrides: Additional context values to override defaults

    Returns:
        Dictionary containing all template context variables
    """
    user = session.get("user", {})
    key = _get_user_key()
    now = datetime.now(timezone.utc)

    # Fetch data
    settings = current_app.notification_service.get_settings(key)
    available_locations = current_app.database_manager.get_available_locations()
    available_keywords = current_app.database_manager.get_all_keywords()
    user_notifications = current_app.database_manager.get_user_notifications(key, limit=10)
    unread_count = current_app.database_manager.get_user_notification_count(key, unread_only=True)
    total_count = current_app.database_manager.get_user_notification_count(key, unread_only=False)
    posts = current_app.database_manager.get_latest_posts(limit=10)

    # Calculate derived values
    total_posts = len(posts)
    new_posts_count = sum(1 for post in posts if post.created_at > now - timedelta(days=1))

    context = {
        "user": user,
        "settings": settings,
        "available_locations": available_locations,
        "available_keywords": available_keywords,
        "notifications": user_notifications,
        "notification_summary": {"unread": unread_count, "total": total_count},
        "posts": posts,
        "new_posts_count": new_posts_count,
        "total_posts": total_posts,
        "app_name": current_app.config.get("APP_NAME"),
    }
    context.update(overrides)
    return context


def _json_response(func: Callable, *args: Any, **kwargs: Any) -> Response | tuple:
    """Helper for JSON API endpoints with standardized error handling.

    Args:
        func: Function to execute that returns API data
        *args: Positional arguments for func
        **kwargs: Keyword arguments for func

    Returns:
        JSON response with success data or error message
    """
    try:
        result = func(*args, **kwargs)
        response_data = result if isinstance(result, dict) else {"success": True, "data": result}
        return jsonify(response_data)
    except (AttributeError, KeyError, ValueError, RuntimeError, TypeError) as e:
        logger.exception(
            "API error: %s | endpoint=%s | user=%s",
            e,
            request.endpoint,
            _get_user_key(),
        )
        return jsonify({"error": str(e)}), 500


# --- Routes ---


@dashboard_bp.route("/dashboard")
@require_auth
def dashboard() -> str:
    """Render the main dashboard view with comprehensive error handling."""
    try:
        context = _render_dashboard_context()
        return render_template("dashboard.html", **context)
    except (AttributeError, KeyError, ValueError, RuntimeError) as e:
        logger.exception("Dashboard error: %s | user=%s", e, _get_user_key())
        flash(f"Error loading dashboard: {e}", "error")

        # Provide fallback context with empty data
        fallback_context = {
            "user": session.get("user", {}),
            "settings": {},
            "available_locations": [],
            "notifications": [],
            "notification_summary": {"unread": 0, "total": 0},
            "posts": [],
            "new_posts_count": 0,
            "total_posts": 0,
            "app_name": current_app.config.get("APP_NAME"),
        }
        return render_template("dashboard.html", **fallback_context)


@dashboard_bp.route("/refresh")
@limiter.limit("5 per minute")
@require_auth
def refresh_posts() -> Response:
    """Trigger a dashboard refresh."""
    try:
        current_app.polling_service.manual_poll()
        flash("Refreshing posts...", "info")
    except (RuntimeError, ValueError, OSError) as e:
        logger.exception("Manual refresh failed: %s | user=%s", e, _get_user_key())
        flash(f"Refresh failed: {e}", "error")
    return redirect(url_for("dashboard_bp.dashboard"))


@dashboard_bp.route("/api/notifications/mark-read", methods=["POST"])
@require_auth
def mark_notifications_read() -> Response | tuple:
    """Mark all notifications as read for the authenticated user."""

    def action() -> dict[str, Any]:
        user_key = _get_user_key()
        if not user_key:
            raise ValueError("User key not found in session")

        # Only mark notifications for the authenticated user
        success = current_app.database_manager.mark_all_user_notifications_read(user_key)
        if not success:
            raise RuntimeError("Failed to mark notifications as read")

        unread_count = current_app.database_manager.get_user_notification_count(user_key, unread_only=True)
        logger.info("Notifications marked read | user=%s", user_key)
        return {"success": True, "unread": unread_count}

    return _json_response(action)


@dashboard_bp.route("/api/notifications/status")
@require_auth
def get_notification_status() -> Response | tuple:
    """Fetch current notification summary for the authenticated user."""

    def action() -> dict[str, Any]:
        user_key = _get_user_key()
        if not user_key:
            raise ValueError("User key not found in session")

        logger.debug("Fetching notification status for user: %s", user_key)
        # Fetch user-specific notifications and counts
        notifications = current_app.database_manager.get_user_notifications(user_key, limit=10, unread_only=False)
        unread_count = current_app.database_manager.get_user_notification_count(user_key, unread_only=True)
        total_count = current_app.database_manager.get_user_notification_count(user_key, unread_only=False)
        push_enabled = current_app.database_manager.has_push_subscription(user_key)

        summary = {
            "unread": unread_count,
            "total": total_count,
            "push_enabled": push_enabled,
            "unread_count": unread_count,
            "latest_notifications": notifications,
        }

        logger.info("Notification status fetched | user=%s", user_key)
        return summary

    return _json_response(action)


@dashboard_bp.route("/api/test-notification", methods=["POST"])
@require_auth
def send_test_notification() -> Response | tuple:
    """Sends a test notification via service to subscribers."""

    def action() -> dict[str, Any]:
        notif = current_app.notification_service.create_test_notification()
        return {"notification": notif}

    return _json_response(action)


@dashboard_bp.route("/api/session/validate")
def validate_session_api() -> Response | tuple:
    """Validate user session and return status."""
    user = session.get("user")
    token = request.cookies.get("access_token")
    if not user or not token or not _validate_session():
        logger.info("Session invalid | ip=%s", request.remote_addr)
        session.clear()
        current_app.access_token_storage.access_token = None
        return jsonify({"valid": False, "message": "Session expired"}), 401
    logger.info("Session valid | user=%s | ip=%s", user.get("name"), request.remote_addr)
    return jsonify({"valid": True, "user": user.get("name")})


@dashboard_bp.route("/user_photo")
@require_auth
def user_photo() -> Response:
    """Serve user photo or default if unavailable."""
    token = request.cookies.get("access_token")
    if not token or not _validate_session():
        logger.warning("User photo invalid session | ip=%s", request.remote_addr)
        return send_from_directory(current_app.static_folder + "/img/user", "default_profile.webp")
    try:
        resp = requests.get(
            "https://graph.microsoft.com/v1.0/me/photo/$value",
            headers={"Authorization": f"Bearer {token}"},
            timeout=Config.HTTP_TIMEOUT,
        )
        if resp.status_code == 200:
            return send_file(io.BytesIO(resp.content), mimetype=resp.headers.get("Content-Type"))
        if resp.status_code == 401:
            session.clear()
        logger.warning("User photo fetch status %s | user=%s", resp.status_code, _get_user_key())
    except (requests.RequestException, OSError) as e:
        logger.warning("Failed to fetch user photo: %s | user=%s", e, _get_user_key())
    return send_from_directory(current_app.static_folder + "/img/user", "default_profile.webp")


@dashboard_bp.route("/api/notifications/settings", methods=["GET"])
@require_auth
def get_notification_settings() -> Response | tuple:
    """Get current notification settings."""

    def action() -> dict[str, Any]:
        key = _get_user_key()
        return current_app.notification_service.get_settings(key)

    return _json_response(action)


@dashboard_bp.route("/api/notifications/settings", methods=["POST"])
@require_auth
def save_notification_settings() -> Response | tuple:
    """Save new notification settings."""

    def action() -> dict[str, bool]:
        key = _get_user_key()
        data = request.get_json()
        if not data:
            raise ValueError("No settings provided")
        success = current_app.notification_service.update_settings(key, data)
        if not success:
            raise RuntimeError("Failed to save settings")
        return {"success": True}

    return _json_response(action)
