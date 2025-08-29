"""Notification service for desktop notifications.

This service manages the creation and delivery of notifications for blog posts:

Key Features:
- Urgent posts are broadcast to ALL users with push notifications enabled
- Non-urgent posts are filtered by user preferences (location, keywords)
- Per-user read status tracking via UserNotification model
- Push notification delivery with error handling and subscription cleanup
- User preference management for notification settings

Notification Flow:
1. New post detected by polling service
2. NotificationService.create_post_notification() called
3. If urgent: bypasses all filters, targets all users with push enabled
4. If normal: applies location and keyword filters
5. Notification record created in database
6. UserNotification records created for target users
7. Push notifications sent to eligible subscriptions with opt-out enforcement
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

from pywebpush import WebPushException, webpush

from app.core.config import Config
from app.db.database import DatabaseManager
from app.db.models import Notification, Post

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

    def get_settings(self, user_key: str) -> dict[str, Any]:
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

    def update_settings(self, user_key: str, settings: dict[str, Any]) -> bool:
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
                logger.error("Invalid update interval type: %s", settings["updateInterval"])
                return False

            language = settings.get("language", "en")
            if language not in {"en", "hu", "sv"}:
                logger.error("Invalid language: %s", language)
                return False

            keywords = settings.get("keywords", [])
            if not isinstance(keywords, list):
                logger.error("Invalid keywords type")
                return False
            if len(keywords) > 20 or any(not isinstance(k, str) or len(k) < 3 for k in keywords):
                logger.error("Keyword validation failed")
                return False

            keyword_filter = settings.get("keywordFilter", {"enabled": False})
            if not isinstance(keyword_filter, dict) or not isinstance(keyword_filter.get("enabled"), bool):
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

    def create_post_notification(self, post: Post) -> Notification | None:
        """
        Create a notification for a new post.

        For urgent posts: Creates notification and delivers to ALL users with push notifications enabled.
        For normal posts: Creates notification and delivers only to users matching location/keyword filters.

        Per-user read status is tracked via UserNotification records.

        Args:
            post: The post to create a notification for

        Returns:
            The created notification, or None if creation failed
        """
        try:
            # Truncate content if too long
            content = post.content or ""
            if len(content) > self.MAX_CONTENT_LENGTH:
                content = content[: self.MAX_CONTENT_LENGTH - 3] + "..."

            # URGENT path: For urgent posts, bypass all filters and target all users
            if post.is_urgent:
                target_users = None  # None = "all users with push enabled" - URGENT path
                logger.info(
                    "URGENT post %s will be sent to all users with push notifications enabled",
                    post.id,
                )
            else:
                # Get users who match filters for non-urgent posts
                target_users = self._get_filtered_users_for_post(post)

                # For non-urgent posts, if no users match filters, skip delivery entirely
                if target_users is not None and len(target_users) == 0:
                    logger.info(
                        "No recipients match filters; skipping push delivery for post %s",
                        post.id,
                    )
                    # Still create the notification but return early without delivery
                    notification = Notification(
                        post_id=post.id,
                        title=f"{'🚨 URGENT: ' if post.is_urgent else ''}{post.title}",
                        message=content,
                        image_url=post.image_url if post.has_image else None,
                        created_at=datetime.now(timezone.utc),
                        is_urgent=post.is_urgent,
                    )

                    notification_id = self.db.add_notification(notification)
                    if notification_id:
                        notification.id = str(notification_id)
                    return notification

            notification = Notification(
                post_id=post.id,
                title=f"{'🚨 URGENT: ' if post.is_urgent else ''}{post.title}",
                message=content,
                image_url=post.image_url if post.has_image else None,
                created_at=datetime.now(timezone.utc),
                is_urgent=post.is_urgent,
            )

            notification_id = self.db.add_notification(notification)
            if notification_id:
                # Create user notification entries for targeted users
                if target_users is None:
                    # URGENT path: get all users with push subscriptions as proxy for all users
                    all_subscriptions = self.db.get_push_subscriptions_for_users([], urgent=True)
                    all_settings = self.db.get_all_notification_settings()
                    all_user_keys_combined = list(
                        {sub.get("user_key") for sub in all_subscriptions if sub.get("user_key")}
                        | set(all_settings.keys())
                    )
                    if all_user_keys_combined:
                        self.db.add_user_notifications_bulk(notification_id, all_user_keys_combined)
                    else:
                        logger.warning("No users found for urgent notification %s", notification_id)
                elif target_users:
                    # Normal path: targeted users only (skip if empty)
                    self.db.add_user_notifications_bulk(notification_id, list(target_users))
                else:
                    logger.info("No target users for notification %s", notification_id)

                # Set the ID on our notification object
                notification.id = str(notification_id)

                # Deliver notification to target users with post URL (skip if empty target_users)
                if target_users is None or (target_users is not None and len(target_users) > 0):
                    post_url = post.link if post.link else None
                    self._deliver_notification(notification, target_users, post_url)

                return notification

        except (ValueError, TypeError, json.JSONDecodeError) as e:
            logger.error("Failed to create notification for post %s: %s", post.id, e)
            # Return a basic notification as fallback
            return Notification(
                post_id=post.id,
                title="New Post Notification",
                message="Content not available",
                created_at=datetime.now(timezone.utc),
                is_urgent=False,
            )

    def create_bulk_notification(self, posts: list[Post]) -> list[Notification]:
        """Create notifications for multiple posts."""
        notifications = []

        # Process all posts - no special handling needed since
        # create_post_notification handles filtering internally
        for post in posts:
            if notification := self.create_post_notification(post):
                notifications.append(notification)

        return notifications

    def send_push_notification(
        self,
        subscription: dict[str, Any],
        notification: Notification,
        post_url: str | None = None,
    ) -> bool:
        """Send a push notification to a subscription."""

        endpoint = subscription.get("endpoint")
        user_key = subscription.get("user_key", "unknown")

        try:
            if not self._validate_subscription(subscription):
                logger.error(
                    "Invalid subscription format for user %s, endpoint %s",
                    user_key,
                    endpoint,
                )
                return False

            if not Config.PUSH_VAPID_PRIVATE_KEY or not Config.PUSH_VAPID_CLAIMS:
                logger.error("VAPID configuration missing for push notification")
                return False

            payload = json.dumps(
                {
                    "title": notification.title,
                    "body": notification.message,
                    "icon": notification.image_url,
                    "url": post_url,
                    "data": {
                        "post_url": post_url,
                        "post_id": notification.post_id,
                    },
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
            logger.debug("Push notification sent successfully to user %s", user_key)
            return True

        except WebPushException as e:
            logger.error(
                "Push notification failed for user %s, post %s, endpoint %s: %s",
                user_key,
                notification.post_id,
                endpoint,
                e,
            )
            # Mark invalid subscriptions for removal on HTTP error codes that indicate permanent failure
            if e.response and e.response.status_code in (400, 404, 410, 413):
                logger.info(
                    "Removing invalid subscription for user %s due to HTTP %d",
                    user_key,
                    e.response.status_code,
                )
                self.db.remove_push_subscription(subscription)
            return False
        except (TypeError, ValueError, json.JSONDecodeError) as e:
            logger.error(
                "Error preparing push notification for user %s, post %s: %s",
                user_key,
                notification.post_id,
                e,
            )
            return False

    def _deliver_notification(
        self,
        notification: Notification,
        target_users: set[str] | None = None,
        post_url: str | None = None,
    ) -> None:
        """
        Send a notification to targeted subscriptions based on user filters.

        Args:
            notification: The notification to send.
            target_users: Set of user keys that should receive this notification.
                         If None, sends to all users with push notifications enabled (URGENT path).
            post_url: URL of the blog post associated with the notification.
        """
        # Get subscriptions based on target users
        if target_users is None:
            # URGENT path: For urgent posts - get all subscriptions
            subscriptions = self.db.get_push_subscriptions_for_users([], urgent=True)
        else:
            # Normal path: Get subscriptions only for targeted users
            subscriptions = self.db.get_push_subscriptions_for_users(list(target_users))

        # Apply push notification preference filtering
        all_settings = self.db.get_all_notification_settings()
        filtered_subscriptions = []

        for sub in subscriptions:
            user_key = sub.get("user_key")
            if not user_key:
                continue

            # Check if user has push notifications enabled
            user_settings = all_settings.get(user_key, {})
            if isinstance(user_settings, str):
                try:
                    user_settings = json.loads(user_settings)
                except (ValueError, json.JSONDecodeError):
                    user_settings = {}

            # Only include if push notifications are enabled (default to True for backward compatibility)
            if user_settings.get("pushNotifications", True):
                filtered_subscriptions.append(sub)

        # Send notifications to filtered subscriptions
        with ThreadPoolExecutor(max_workers=min(10, len(filtered_subscriptions))) as executor:
            for sub in filtered_subscriptions:
                executor.submit(self.send_push_notification, sub, notification, post_url)

    def _validate_subscription(self, subscription: dict[str, Any]) -> bool:
        """Validate push subscription format."""
        required_fields = ["endpoint", "keys"]
        if not all(field in subscription for field in required_fields):
            return False

        keys = subscription.get("keys", {})
        required_keys = ["p256dh", "auth"]
        if not all(key in keys for key in required_keys):
            return False

        return True

    def create_test_notification(self) -> Notification | None:
        """Create a test notification with inline text."""
        try:
            logger.info("Creating test notification to verify settings")
            notif = Notification(
                post_id="test",
                title="🧪 Test Notification",
                message="This is a test notification to verify your settings are working correctly.",
                created_at=datetime.now(timezone.utc),
                is_urgent=False,
            )
            self._deliver_notification(notif, None, None)
            return notif

        except (ValueError, TypeError, json.JSONDecodeError) as e:
            logger.error("Failed to create test notification: %s", e)

        return None

    def _get_filtered_users_for_post(self, post: Post) -> set[str]:
        """
        Get the set of user keys who should receive notifications for this post
        based on their location and keyword filter settings.

        Args:
            post: The post to check filters against.

        Returns:
            Set[str]: User keys that match the post filters.
        """
        try:
            # Get all user settings
            all_settings = self.db.get_all_notification_settings()

            # Filter by location first
            location_filtered_users = self._filter_by_location(post, all_settings)
            if not location_filtered_users:
                logger.info("No users match location filter for post %s", post.id)
                return set()

            # Then filter by keywords
            keyword_filtered_users = self._filter_by_keywords(post, location_filtered_users, all_settings)
            if not keyword_filtered_users:
                logger.info("No users match keyword filter for post %s", post.id)

            return keyword_filtered_users

        except (ValueError, TypeError, json.JSONDecodeError) as e:
            logger.error("Error filtering users for post %s: %s", post.id, e)
            return set()

    def _filter_by_location(self, post: Post, all_settings: dict[str, Any]) -> set[str]:
        """Filter users by location preferences."""
        location_filtered_users = set()

        for user_key, raw_settings in all_settings.items():
            settings = json.loads(raw_settings) if isinstance(raw_settings, str) else raw_settings

            location_filter = settings.get("locationFilter", {})
            if not location_filter.get("enabled", False):
                # Location filter disabled - user should receive all posts
                location_filtered_users.add(user_key)
                continue

            user_locations = location_filter.get("locations", [])
            if not user_locations:
                # Filter enabled but no locations selected - treat as "no filter" (send all)
                location_filtered_users.add(user_key)
                continue

            # Handle posts with no location: bypass location filters (include all users)
            # Posts without location are sent to all users regardless of location filter settings
            if post.location is None or post.location == "":
                # No location = all users (subject to keyword filters)
                location_filtered_users.add(user_key)
            elif post.location in user_locations:
                location_filtered_users.add(user_key)

        return location_filtered_users

    def _filter_by_keywords(
        self,
        post: Post,
        location_filtered_users: set[str],
        all_settings: dict[str, Any],
    ) -> set[str]:
        """Filter users by keyword preferences."""
        keyword_filtered_users = set()

        for user_key in location_filtered_users:
            settings = all_settings.get(user_key, {})
            if isinstance(settings, str):
                settings = json.loads(settings)

            keyword_filter = settings.get("keywordFilter", {"enabled": False})
            if not keyword_filter.get("enabled", False):
                # Keyword filter disabled - user should receive all posts
                keyword_filtered_users.add(user_key)
                continue

            # Get user's keywords from database
            keywords = self.db.get_user_keywords(user_key)
            if not keywords:
                # No keywords set - treat as "no filter" (send all)
                keyword_filtered_users.add(user_key)
                continue

            # Check if any keyword matches the post content
            content_lower = f"{post.title} {post.content}".lower()
            if any(kw.lower() in content_lower for kw in keywords):
                keyword_filtered_users.add(user_key)

        return keyword_filtered_users

    def get_user_notification_count(self, user_id: str, unread_only: bool = True) -> int:
        """Get count of notifications for a specific user."""
        return self.db.get_user_notification_count(user_id, unread_only)

    def get_user_notifications(self, user_id: str, limit: int = 10, unread_only: bool = False) -> list[dict[str, Any]]:
        """Get notifications for a specific user with read status."""
        return self.db.get_user_notifications(user_id, limit, unread_only)

    def mark_user_notification_read(self, user_id: str, notification_id: int) -> bool:
        """Mark a specific notification as read for a user."""
        return self.db.mark_user_notification_read(user_id, notification_id)

    def mark_notifications_read(self, user_id: str, notification_ids: list[int]) -> bool:
        """Mark multiple notifications as read for a user."""
        return self.db.mark_notifications_read(user_id, notification_ids)

    def mark_all_user_notifications_read(self, user_id: str) -> bool:
        """Mark all notifications as read for a specific user."""
        return self.db.mark_all_user_notifications_read(user_id)

    # Add a service method to ensure proper cleanup when notifications expire
    def cleanup_expired_notifications(self) -> int:
        """
        Clean up expired notifications and their associated user notifications.
        This replaces the old global cleanup to work with the new user_notifications table.

        Returns:
            int: Number of notifications cleaned up.
        """
        # First clean up user notification entries for expired notifications
        user_notif_count = self.db.cleanup_expired_user_notifications()

        # Then clean up the expired notifications themselves
        notif_count = self.db.cleanup_expired_notifications()

        if notif_count > 0:
            logger.info(
                "Cleaned up %d expired notifications and %d user notification entries",
                notif_count,
                user_notif_count,
            )

        return notif_count

    def cleanup_user_data(self, user_id: str) -> dict[str, int]:
        """
        Clean up all notification data for a user when they're deactivated/removed.

        Args:
            user_id: User identifier

        Returns:
            Dict[str, int]: Number of records cleaned up from each table
        """
        return self.db.cleanup_user_data(user_id)
