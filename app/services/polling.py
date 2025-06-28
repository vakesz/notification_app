"""Service for polling blog posts and creating notifications."""

import logging
import threading
import time
from datetime import datetime
from functools import wraps
from typing import Any, Dict, List

from apscheduler.schedulers.background import BackgroundScheduler  # type: ignore

from app.core.config import Config
from app.db.database import DatabaseManager
from app.db.models import Notification, Post
from app.services.notification import (  # pylint: disable=unused-import
    NotificationService,
)
from app.services.parser import ContentParser
from app.utils.http_client import BlogClient, HTTPClientError

# import is used only as a type‐hint

logger = logging.getLogger(__name__)


def rate_limit(calls: int, period: int) -> Any:
    """Decorator to limit the number of calls per time period."""

    def decorator(func: Any) -> Any:
        last_reset = time.time()
        calls_made = 0
        lock = threading.Lock()

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            nonlocal last_reset, calls_made
            with lock:
                now = time.time()
                if now - last_reset >= period:
                    last_reset = now
                    calls_made = 0

                if calls_made >= calls:
                    sleep_time = period - (now - last_reset)
                    if sleep_time > 0:
                        time.sleep(sleep_time)
                    last_reset = time.time()
                    calls_made = 0

                calls_made += 1
            return func(*args, **kwargs)

        return wrapper

    return decorator


class PollingService:
    """Continuously polls a blog for new posts and records notifications."""

    def __init__(
        self,
        blog_url: str,
        database_manager: DatabaseManager,
        blog_client: BlogClient,
        content_parser: ContentParser,
        notification_service: "NotificationService | None" = None,
        interval_minutes: int = 5,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
        max_backoff: int = 60,
        rate_limit_calls: int = 10,
        rate_limit_period: int = 60,
    ) -> None:
        self.blog_url = blog_url
        self.db = database_manager
        self.client = blog_client
        self.parser = content_parser
        self.notifier = notification_service
        self.interval = interval_minutes * 60

        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.max_backoff = max_backoff
        self.rate_limit_calls = rate_limit_calls
        self.rate_limit_period = rate_limit_period

        self._lock = threading.Lock()
        self._last_poll_time: datetime = None  # type: ignore
        self._last_error: str = ""
        self._is_polling = False
        self._retry_count = 0
        self._last_manual_poll: float = 0.0
        self.scheduler = BackgroundScheduler(daemon=True)

    def start(self) -> None:
        """Start scheduler jobs for polling and cleanup."""
        if self.scheduler.running:
            logger.warning("Polling service is already running")
            return

        # Allow some tolerance for delayed execution to avoid missed runs
        self.scheduler.add_job(
            self._poll_job,
            "interval",
            seconds=self.interval,
            misfire_grace_time=max(60, self.interval // 2),
        )
        self.scheduler.add_job(
            self._cleanup_job,
            "interval",
            seconds=self.interval * 2,
            misfire_grace_time=max(60, self.interval),
        )
        self.scheduler.start()
        logger.info("Polling service started")

    def stop(self) -> None:
        """Stop scheduler jobs."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        logger.info("Polling service stopped")

    def _poll_job(self) -> None:
        """Scheduled job to poll once and send notifications."""
        try:
            new_posts = self._poll_once()
            if new_posts and self.notifier:
                self.notifier.create_bulk_notification(new_posts)
            self._last_error = ""
            self._retry_count = 0
        except (HTTPClientError, ValueError, TypeError) as e:
            self._last_error = str(e)
            logger.error("Polling failed: %s", e)

    def _cleanup_job(self) -> None:
        """Scheduled job to clean up expired data."""
        try:
            removed = self.db.cleanup_expired_notifications()
            logger.debug("Expired notifications removed: %d", removed)
            purged = self.db.cleanup_old_tokens(Config.AUTH_TOKEN_TTL_DAYS)
            if purged:
                logger.debug("Old auth tokens purged: %d", purged)
        except (ValueError, TypeError, RuntimeError) as e:
            logger.error("Cleanup failed: %s", e)

    @rate_limit(calls=10, period=60)
    def _poll_once(self) -> List[Post]:
        """Fetch and process new posts once.

        Returns a list of new posts that were added to the database."""

        logger.debug("Starting single poll iteration")
        with self._lock:
            if self._is_polling:
                return []
            self._is_polling = True

        new_posts: List[Post] = []
        try:
            html = self.client.get_content()
            posts = self.parser.parse_html_content(html)
            self._last_poll_time = datetime.utcnow()
            if posts:
                new_posts = self._process_posts(posts)
        finally:
            self._is_polling = False
        return new_posts

    def _process_posts(self, posts: List[Post]) -> List[Post]:
        """Insert only new posts and create notifications for them.

        Returns a list of posts that were added."""
        new_posts: List[Post] = []
        added = self.db.add_posts_bulk(posts)
        for post in added:
            if post.id is None:
                logger.warning("Skipping post with None id")
                continue
            logger.info("Added new post: %s", post.id)
            notif = Notification(
                post_id=post.id,
                title=post.title,
                message=f"New post: {post.title}",
                created_at=datetime.utcnow(),
                is_urgent=post.is_urgent,
                image_url=post.image_url,
            )
            self.db.add_notification(notif)
            new_posts.append(post)

        return new_posts

    def poll_now(self) -> None:
        """Manually trigger a poll immediately."""
        logger.info("Manual poll triggered")
        if time.time() - self._last_manual_poll < self.rate_limit_period:
            logger.info("Manual poll ignored due to cooldown")
            return

        self._last_manual_poll = time.time()
        try:
            new_posts = self._poll_once()
            if new_posts and self.notifier:
                self.notifier.create_bulk_notification(new_posts)
        except HTTPClientError as e:
            logger.error("Manual poll failed due to network issue: %s", e)
            raise
        except (ValueError, TypeError, RuntimeError) as e:
            logger.error("Manual poll failed: %s", e)
            raise

    def get_status(self) -> Dict[str, Any]:
        """Return current status of the polling service."""
        return {
            "is_running": self.scheduler.running,
            "last_poll": (self._last_poll_time.isoformat() if self._last_poll_time else None),
            "last_error": self._last_error,
            "is_polling": self._is_polling,
        }
