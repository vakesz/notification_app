"""Notification service for desktop notifications."""

import logging
from typing import List, Dict, Any, Optional, Set
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json

from pywebpush import WebPushException, webpush
from app.core.config import Config

from app.db.models import Post, Notification
from app.db.database import DatabaseManager

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for managing notifications."""

    # This class is only used by the polling service so it doesn't need the
    # background worker threads that existed previously. Notifications are
    # delivered synchronously when created.

    MAX_CONTENT_LENGTH = 75  # Maximum length of notification message content

    def __init__(self, db: DatabaseManager) -> None:
        """Initialize notification service."""
        self.db = db
        self._active_subscriptions: Set[str] = set()

    def get_settings(self, user_key: str) -> Dict[str, Any]:
        """Get notification settings for a user."""
        try:
            # Get settings from database
            settings = self.db.get_notification_settings(user_key)

            # If no settings exist, return defaults
            if not settings:
                return {
                    "language": "en",
                    "desktopNotifications": True,
                    "pushNotifications": True,
                    "updateInterval": 5,  # minutes
                    "locationFilter": {
                        "enabled": False,
                        "locations": [],  # List of location names to filter by
                    },
                    "keywordFilter": {"enabled": False},
                    "keywords": [],
                }

            # Parse settings from JSON if stored as string
            if isinstance(settings, str):
                settings = json.loads(settings)

            # Ensure all required fields are present
            default_settings = {
                "language": "en",
                "desktopNotifications": True,
                "pushNotifications": True,
                "updateInterval": 5,
                "locationFilter": {"enabled": False, "locations": []},
                "keywordFilter": {"enabled": False},
                "keywords": [],
            }

            # Update defaults with user settings
            default_settings.update(settings)
            db_keywords = self.db.get_user_keywords(user_key)
            if db_keywords:
                default_settings["keywords"] = db_keywords

            return default_settings

        except (ValueError, json.JSONDecodeError) as e:
            logger.error("Error getting notification settings: %s", e)
            # Return default settings on error
            return {
                "language": "en",
                "desktopNotifications": True,
                "pushNotifications": True,
                "updateInterval": 5,
                "locationFilter": {"enabled": False, "locations": []},
                "keywordFilter": {"enabled": False},
                "keywords": [],
            }

    def update_settings(self, user_key: str, settings: Dict[str, Any]) -> bool:
        """Update notification settings for a user."""
        try:
            # Validate settings
            required_fields = {
                "language",
                "desktopNotifications",
                "pushNotifications",
                "updateInterval",
                "locationFilter",
                "keywordFilter",
                "keywords",
            }
            if not all(field in settings for field in required_fields):
                logger.error("Missing required fields in settings: %s", settings)
                return False

            # Validate updateInterval
            try:
                interval = int(settings["updateInterval"])
                if interval not in [1, 5, 15, 30, 60]:
                    logger.error("Invalid update interval: %s", interval)
                    return False
            except (ValueError, TypeError):
                logger.error(
                    "Invalid update interval type: %s", settings["updateInterval"]
                )
                return False

            language = settings.get("language", "en")
            if language not in {"en", "hu", "sv"}:
                logger.error("Invalid language: %s", language)
                return False

            keywords = settings.get("keywords", [])
            if not isinstance(keywords, list):
                logger.error("Invalid keywords type")
                return False
            if len(keywords) > 20 or any(
                not isinstance(k, str) or len(k) < 3 for k in keywords
            ):
                logger.error("Keyword validation failed")
                return False

            keyword_filter = settings.get("keywordFilter", {"enabled": False})
            if not isinstance(keyword_filter, dict) or not isinstance(
                keyword_filter.get("enabled"), bool
            ):
                logger.error("Invalid keyword filter settings")
                return False

            self.db.add_global_keywords(keywords)
            self.db.update_user_keywords(user_key, keywords)

            settings_copy = settings.copy()
            settings_copy.pop("keywords", None)
            # Store settings in database
            return self.db.update_notification_settings(user_key, settings_copy)

        except (ValueError, TypeError, json.JSONDecodeError) as e:
            logger.error("Error updating notification settings: %s", e)
            return False

    def create_post_notification(self, post: Post) -> Optional[Notification]:
        """Create a notification for a new post."""
        try:
            # Get all user settings to check location filters
            all_settings = self.db.get_all_notification_settings()

            # Filter users by location and keyword preferences
            filtered_users = set()
            for user_key, settings in all_settings.items():
                if isinstance(settings, str):
                    settings = json.loads(settings)

                location_filter = settings.get("locationFilter", {})
                if not location_filter.get("enabled", False):
                    filtered_users.add(user_key)
                    continue

                user_locations = location_filter.get("locations", [])
                if not user_locations:
                    # filter enabled but no locations selected
                    continue
                if post.location and post.location in user_locations:
                    filtered_users.add(user_key)

            if not filtered_users:
                logger.info("No users match location filter for post %s", post.id)
                return None

            keyword_matched_users = set()
            for user_key in filtered_users:
                settings = all_settings.get(user_key, {})
                if isinstance(settings, str):
                    settings = json.loads(settings)
                keyword_filter = settings.get("keywordFilter", {"enabled": False})
                if not keyword_filter.get("enabled", False):
                    keyword_matched_users.add(user_key)
                    continue
                keywords = self.db.get_user_keywords(user_key)
                if not keywords:
                    keyword_matched_users.add(user_key)
                    continue
                content_lower = f"{post.title} {post.content}".lower()
                if any(kw.lower() in content_lower for kw in keywords):
                    keyword_matched_users.add(user_key)

            if not keyword_matched_users:
                logger.info("No users match keyword filter for post %s", post.id)
                return None

            # Truncate content if too long
            content = post.content or ""
            if len(content) > self.MAX_CONTENT_LENGTH:
                content = content[: self.MAX_CONTENT_LENGTH - 3] + "..."

            notification = Notification(
                post_id=post.id,
                title=f"{'🚨 URGENT: ' if post.is_urgent else ''}{post.title}",
                message=content,
                image_url=post.image_url if post.has_image else None,
                created_at=datetime.now(),
                is_urgent=post.is_urgent,
            )

            if self.db.add_notification(notification):
                self._deliver_notification(notification)
                return notification

        except (ValueError, TypeError, json.JSONDecodeError) as e:
            logger.error("Failed to create notification for post %s: %s", post.id, e)
            # Return a basic notification as fallback
            return Notification(
                post_id=post.id,
                title="New Post Notification",
                message="Content not available",
                created_at=datetime.now(),
                is_urgent=False,
            )

    def create_bulk_notification(self, posts: List[Post]) -> List[Notification]:
        """Create notifications for multiple posts."""
        notifications = []
        urgent_posts = []
        normal_posts = []

        # Separate urgent and normal posts
        for post in posts:
            if post.is_urgent:
                urgent_posts.append(post)
            else:
                normal_posts.append(post)

        # Process urgent posts first
        for post in urgent_posts:
            if notification := self.create_post_notification(post):
                notifications.append(notification)

        # Process normal posts
        for post in normal_posts:
            if notification := self.create_post_notification(post):
                notifications.append(notification)

        return notifications

    def get_notification_summary(self) -> Dict[str, Any]:
        """Get notification summary statistics."""
        try:
            summary = self.db.get_notification_summary()
            summary["active_subscriptions"] = len(self._active_subscriptions)
            return summary
        except (ValueError, TypeError, json.JSONDecodeError) as e:
            logger.error("Failed to get notification summary: %s", e)
            return {
                "total": 0,
                "unread": 0,
                "urgent_unread": 0,
                "active_subscriptions": 0,
            }

    def send_push_notification(
        self, subscription: Dict[str, Any], notification: Notification
    ) -> bool:
        """Send a push notification to a subscription."""

        endpoint = subscription.get("endpoint")
        try:
            if not self._validate_subscription(subscription):
                logger.error("Invalid subscription format")
                return False

            if not Config.PUSH_VAPID_PRIVATE_KEY or not Config.PUSH_VAPID_CLAIMS:
                logger.error("VAPID configuration missing")
                return False

            if endpoint:
                self._active_subscriptions.add(endpoint)

            payload = json.dumps(
                {
                    "title": notification.title,
                    "body": notification.message,
                    "icon": notification.image_url,
                }
            )
            ttl = getattr(Config, "PUSH_TTL", 86400)
            webpush(
                subscription_info=subscription,
                data=payload,
                vapid_private_key=Config.PUSH_VAPID_PRIVATE_KEY,
                vapid_claims=Config.PUSH_VAPID_CLAIMS.copy(),
                ttl=ttl,
            )
            if endpoint:
                self.db.update_subscription_last_used(endpoint)
            return True

        except WebPushException as e:
            logger.error("Push failed %s: %s", endpoint, e)
            if e.response and e.response.status_code in (400, 404, 410):
                self.db.remove_push_subscription(subscription)
            return False
        except (TypeError, ValueError, json.JSONDecodeError) as e:
            logger.error("Error sending push notification: %s", e)
            return False
        finally:
            if endpoint:
                self._active_subscriptions.discard(endpoint)

    def _deliver_notification(self, notification: Notification) -> None:
        """Send a notification to all active subscriptions."""
        subscriptions = self.db.get_all_push_subscriptions()
        with ThreadPoolExecutor(max_workers=min(10, len(subscriptions))) as executor:
            for sub in subscriptions:
                executor.submit(self.send_push_notification, sub, notification)

    def _validate_subscription(self, subscription: Dict[str, Any]) -> bool:
        """Validate push subscription format."""
        required_fields = ["endpoint", "keys"]
        if not all(field in subscription for field in required_fields):
            return False

        keys = subscription.get("keys", {})
        required_keys = ["p256dh", "auth"]
        if not all(key in keys for key in required_keys):
            return False

        return True

    def create_test_notification(self) -> Optional[Notification]:
        """Create a test notification with inline text."""
        try:
            logger.info("Creating test notification to verify settings")
            notif = Notification(
                post_id="test",
                title="🧪 Test Notification",
                message="This is a test notification to verify your settings are working correctly.",
                created_at=datetime.now(),
                is_urgent=False,
            )
            self._deliver_notification(notif)
            return notif

        except (ValueError, TypeError, json.JSONDecodeError) as e:
            logger.error("Failed to create test notification: %s", e)

        return None
