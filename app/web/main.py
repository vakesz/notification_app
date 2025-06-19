"""Main entry point for the Flask web application."""

import os
import logging
from logging import Formatter
from logging.handlers import RotatingFileHandler
from flask import Flask, request, jsonify, session
from flask_wtf import CSRFProtect

from app.core.config import config
from app.core.security import AuthService
from app.core.blog_security import BlogAuthentication
from app.db.database import DatabaseManager
from app.services.parser import ContentParser
from app.utils.http_client import BlogClient
from app.services.polling import PollingService
from app.services.notification import NotificationService
from app.api.routes.auth_bp import auth_bp
from app.api.routes.dashboard_bp import dashboard_bp
from app.core.utils.session_utils import access_token_storage


def setup_logging(log_path: str = "app.log") -> None:
    """
    Configure root logger with console and rotating file handlers.
    """
    log_formatter = Formatter(
        "%(asctime)s %(levelname)s %(message)s %(filename)s:%(lineno)d"
    )
    root = logging.getLogger()
    env = os.getenv("FLASK_ENV", "default").lower()
    root.setLevel(logging.DEBUG if env in ("development", "default") else logging.INFO)

    console = logging.StreamHandler()
    console.setFormatter(log_formatter)
    root.addHandler(console)

    file_handler = RotatingFileHandler(
        log_path, maxBytes=2 * 1024 * 1024, backupCount=5
    )
    file_handler.setFormatter(log_formatter)
    root.addHandler(file_handler)


def create_app(config_name: str = "default") -> Flask:
    """Factory function to create and configure the Flask app."""
    setup_logging()

    flask_app = Flask(__name__)
    CSRFProtect(flask_app)

    # Load and validate config
    config_cls = config.get(config_name, config["default"])
    flask_app.config.from_object(config_cls)
    try:
        config_cls.validate()
    except ValueError as err:
        flask_app.logger.error("Configuration validation failed: %s", err)
        raise

    # Prepare database path
    db_path = flask_app.config["APP_DATABASE_PATH"]
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    # Initialize core services
    auth_service = AuthService(
        client_id=flask_app.config["AAD_CLIENT_ID"],
        client_secret=flask_app.config["AAD_CLIENT_SECRET"],
        authority=flask_app.config["AUTHORITY"],
        redirect_uri=flask_app.config["AAD_REDIRECT_URI"],
        scope=flask_app.config["SCOPE"],
    )
    blog_auth = BlogAuthentication()
    db_manager = DatabaseManager(db_path)
    parser = ContentParser()
    http_client = BlogClient(
        base_url=flask_app.config["BLOG_API_URL"],
        timeout=flask_app.config["HTTP_TIMEOUT"],
        blog_auth=blog_auth,
    )
    notifier = NotificationService(db_manager)
    poller = PollingService(
        blog_url=flask_app.config["BLOG_API_URL"],
        database_manager=db_manager,
        blog_client=http_client,
        content_parser=parser,
        notification_service=notifier,
        interval_minutes=flask_app.config["POLLING_INTERVAL_MINUTES"],
    )

    # Attach to app context
    flask_app.auth_service = auth_service
    flask_app.database_manager = db_manager
    flask_app.content_parser = parser
    flask_app.blog_client = http_client
    flask_app.notification_service = notifier
    flask_app.polling_service = poller
    flask_app.access_token_storage = access_token_storage

    # Start polling
    flask_app.logger.info("Starting polling service...")
    poller.start()

    # Register blueprints
    flask_app.register_blueprint(auth_bp)
    flask_app.register_blueprint(dashboard_bp)

    # CLI commands
    @flask_app.cli.command("start-polling")
    def start_polling() -> None:
        """Start the polling service."""
        flask_app.logger.info("Starting polling service via CLI")
        poller.start()

    @flask_app.cli.command("stop-polling")
    def stop_polling() -> None:
        """Stop the polling service."""
        flask_app.logger.info("Stopping polling service via CLI")
        poller.stop()

    # Push subscription endpoints
    def _validate_subscription(data: dict) -> bool:
        return (
            isinstance(data, dict)
            and "endpoint" in data
            and "keys" in data
            and all(k in data["keys"] for k in ("p256dh", "auth"))
        )

    @flask_app.route("/subscribe", methods=["POST"])
    def subscribe():
        sub = request.get_json(silent=True)
        if not _validate_subscription(sub):
            return jsonify({"error": "Invalid subscription object"}), 400

        user = session.get("user") or {}
        user_key = user.get("preferred_username") or user.get("name")

        if flask_app.database_manager.push_subscription_exists(
            sub["endpoint"], user_key
        ):
            flask_app.database_manager.update_subscription_last_used(sub["endpoint"])
            flask_app.logger.info(
                "Subscription already exists: %s | user=%s",
                sub["endpoint"],
                user_key,
            )
            return jsonify({"message": "Subscription already active"}), 200

        flask_app.database_manager.add_push_subscription(sub, user_key)
        flask_app.logger.info(
            "Subscription added: %s | user=%s", sub["endpoint"], user_key
        )
        return jsonify({"message": "Subscription successful"}), 201

    @flask_app.route("/notify", methods=["GET"])
    def notify():
        """Send a test notification to all push subscriptions."""
        if flask_app.notification_service.create_test_notification():
            flask_app.logger.info("Test notification sent successfully")
            return jsonify({"message": "Notification sent"}), 200
        else:
            flask_app.logger.error("Failed to send test notification")
            return jsonify({"error": "Failed to send notification"}), 500

    # API for register/deregister
    @flask_app.route("/api/notifications/register", methods=["POST"])
    def api_register():
        try:
            sub = request.get_json(silent=True)
            if not sub:
                return jsonify({"error": "No subscription data"}), 400
            db_manager.add_push_subscription(sub)
            return jsonify({"message": "Registered."}), 200
        except (ValueError, TypeError, KeyError) as e:
            flask_app.logger.error("Register error: %s", e)
            return jsonify({"error": str(e)}), 500

    @flask_app.route("/api/notifications/deregister", methods=["POST"])
    def api_deregister():
        try:
            sub = request.get_json(silent=True)
            if not sub:
                return jsonify({"error": "No subscription data"}), 400
            db_manager.remove_push_subscription(sub)
            return jsonify({"message": "Deregistered."}), 200
        except (ValueError, TypeError, KeyError) as e:
            flask_app.logger.error("Deregister error: %s", e)
            return jsonify({"error": str(e)}), 500

    flask_app.logger.info("Application initialized successfully")
    return flask_app


if __name__ == "__main__":
    app = create_app(os.getenv("FLASK_ENV", "default"))
    try:
        pass  # Application runs via `flask run`
    finally:
        if hasattr(app, "polling_service"):
            app.polling_service.stop()
        if hasattr(app, "blog_client"):
            app.blog_client.close()
