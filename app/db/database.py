"""Database connection and operations."""

import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

from app.core.config import Config
from app.db.models import Notification, Post

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Custom exception raised for database operation failures."""


# TODO @vakesz: Consider using a different approach with SQLAlchemy or another ORM for better abstraction.
class DatabaseManager:
    """
    Simplified manager for SQLite database operations
    in the notifications application.

    Handles table initialization, CRUD operations for
    posts, notifications, push subscriptions and settings.
    """

    _SCHEMA = [
        (
            "posts",
            (
                "id TEXT PRIMARY KEY, title TEXT NOT NULL, content TEXT,"
                " publish_date TEXT, category TEXT, department TEXT, location TEXT,"
                " is_urgent INTEGER DEFAULT 0, has_image INTEGER DEFAULT 0, image_url TEXT,"
                " likes INTEGER DEFAULT 0, comments INTEGER DEFAULT 0,"
                " link TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,"
                " updated_at TEXT DEFAULT CURRENT_TIMESTAMP"
            ),
        ),
        (
            "notifications",
            (
                "id INTEGER PRIMARY KEY AUTOINCREMENT, post_id TEXT, message TEXT NOT NULL,"
                " title TEXT NOT NULL, image_url TEXT, is_urgent INTEGER DEFAULT 0,"
                " created_at TEXT DEFAULT CURRENT_TIMESTAMP, expires_at TEXT,"
                " FOREIGN KEY(post_id) REFERENCES posts(id)"
            ),
        ),
        (
            "user_notifications",
            (
                "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL,"
                " notification_id INTEGER NOT NULL, is_read INTEGER DEFAULT 0,"
                " read_at TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,"
                " FOREIGN KEY(notification_id) REFERENCES notifications(id) ON DELETE CASCADE"
            ),
        ),
        (
            "push_subscriptions",
            (
                "id INTEGER PRIMARY KEY AUTOINCREMENT, endpoint TEXT UNIQUE NOT NULL,"
                " auth TEXT NOT NULL, p256dh TEXT NOT NULL, user_key TEXT,"
                " device_id TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,"
                " updated_at TEXT DEFAULT CURRENT_TIMESTAMP, last_used TEXT,"
                " is_active INTEGER DEFAULT 1"
            ),
        ),
        (
            "notification_settings",
            (
                "id INTEGER PRIMARY KEY AUTOINCREMENT, user_key TEXT UNIQUE NOT NULL,"
                " settings TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP,"
                " updated_at TEXT DEFAULT CURRENT_TIMESTAMP"
            ),
        ),
        (
            "post_locations",
            (
                "post_id TEXT NOT NULL, location TEXT NOT NULL,"
                " PRIMARY KEY(post_id, location),"
                " FOREIGN KEY(post_id) REFERENCES posts(id)"
            ),
        ),
        (
            "notification_keywords",
            ("user_key TEXT NOT NULL, keyword TEXT NOT NULL, PRIMARY KEY(user_key, keyword)"),
        ),
        (
            "keywords",
            ("keyword TEXT PRIMARY KEY"),
        ),
        (
            "auth_tokens",
            (
                "session_id TEXT PRIMARY KEY, user_id TEXT, token TEXT NOT NULL,"
                " created_at TEXT DEFAULT CURRENT_TIMESTAMP,"
                " updated_at TEXT DEFAULT CURRENT_TIMESTAMP,"
                " last_accessed TEXT DEFAULT CURRENT_TIMESTAMP"
            ),
        ),
    ]

    def __init__(self, db_path: str = "notifications.db") -> None:
        """
        Initialize the DatabaseManager.

        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = db_path
        self._lock = threading.RLock()
        self._conn = self._create_connection()
        self._initialize_db()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._close_connection()

    def _create_connection(self) -> sqlite3.Connection:
        """
        Create and configure a new database connection.

        Returns:
            sqlite3.Connection: Configured connection object.

        Raises:
            DatabaseError: If connection cannot be established.
        """
        try:
            conn = sqlite3.connect(
                self.db_path,
                timeout=Config.DB_TIMEOUT,
                check_same_thread=False,
                isolation_level=None,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            return conn
        except sqlite3.Error as e:
            logger.error("Connection error: %s", e)
            raise DatabaseError(f"Connection error: {e}") from e

    def _close_connection(self) -> None:
        """Close the database connection."""
        if hasattr(self, "_conn") and self._conn:
            try:
                self._conn.close()
            except sqlite3.Error as e:
                logger.error("Error closing database connection: %s", e)
            self._conn = None

    @contextmanager
    def _transaction(self) -> sqlite3.Connection:
        """
        Context manager for a database transaction.
        Automatically commits on success or rolls back on error.

        Yields:
            sqlite3.Connection: Open transaction connection.

        Raises:
            DatabaseError: If an error occurs during transaction.
        """
        with self._lock:
            self._conn.execute("BEGIN")
            success = False
            try:
                yield self._conn
                success = True
            except sqlite3.Error as e:
                logger.error("Transaction failed: %s", e)
                # immediate rollback on error
                try:
                    self._conn.rollback()
                except sqlite3.Error as rollback_err:
                    logger.error("Rollback failed: %s", rollback_err)
                    raise DatabaseError(f"Rollback failed: {rollback_err}") from rollback_err
                raise DatabaseError(f"Transaction failed: {e}") from e
            finally:
                if success:
                    self._conn.commit()

    def _initialize_db(self) -> None:
        """
        Create database tables as defined in the schema if they don't exist.
        """
        with self._transaction() as conn:
            for table, definition in self._SCHEMA:
                conn.execute(f"CREATE TABLE IF NOT EXISTS {table} ({definition})")
            self._ensure_column(conn, "auth_tokens", "user_id", "TEXT")
            self._ensure_column(conn, "auth_tokens", "last_accessed", "TEXT")
            self._ensure_column(conn, "push_subscriptions", "device_id", "TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_created ON posts(created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_tokens_user ON auth_tokens(user_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_publish ON posts(publish_date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_notifications_expires ON notifications(expires_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_notifications_created ON notifications(created_at)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_notifications_user_read " "ON user_notifications(user_id, is_read)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_user_notifications_notification "
                "ON user_notifications(notification_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_push_subscriptions_user_device "
                "ON push_subscriptions(user_key, device_id)"
            )

        # Run migration after schema is set up
        self._migrate_notifications_schema()

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        cols = [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """
        Execute a SQL statement within a transaction.

        Args:
            sql: SQL query or command.
            params: Tuple of parameters for placeholders.

        Returns:
            sqlite3.Cursor: Cursor after execution.
        """
        try:
            with self._transaction() as conn:
                return conn.execute(sql, params)
        except sqlite3.Error as e:
            logger.error("SQL execution error. Query: %s, Params: %s, Error: %s", sql, params, e)
            raise DatabaseError(f"Execution failed for SQL: {sql} with params {params}: {e}") from e

    def _upsert_post(self, post: Post, created_at: str, updated_at: str, conn: sqlite3.Connection) -> None:
        """
        Insert or replace a post record in the database.

        Args:
            post: Post instance.
            created_at: Creation timestamp string.
            updated_at: Update timestamp string.
            conn: Active sqlite3.Connection.
        """
        conn.execute(
            """
            INSERT OR REPLACE INTO posts (
                id, title, content, publish_date,
                category, department, location,
                is_urgent, has_image, image_url,
                likes, comments, link,
                created_at, updated_at
            ) VALUES (
                ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?
            )
            """,
            (
                post.id,
                post.title,
                post.content,
                (post.publish_date.strftime("%Y-%m-%d %H:%M:%S") if post.publish_date else None),
                post.category,
                post.department,
                post.location,
                int(post.is_urgent),
                int(post.has_image),
                post.image_url,
                post.likes,
                post.comments,
                post.link,
                created_at,
                updated_at,
            ),
        )

    def add_post(self, post: Post) -> bool:
        """
        Insert or update a post record only if title or content has changed.
        Returns True if we inserted/updated, False if nothing changed.
        """
        with self._transaction() as conn:
            existing = self.get_post(post.id)

            # If it exists and neither title nor content changed, do nothing
            if existing and existing.title == post.title and existing.content == post.content:
                return False

            utc_time_now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            created_at = existing.created_at if existing else utc_time_now

            self._upsert_post(post, created_at, utc_time_now, conn)

            # Sync any location mapping
            self._add_post_locations(post.id, [post.location], conn)

            return True

    def add_posts_bulk(self, posts: list[Post]) -> list[Post]:
        """
        Insert or update multiple posts in one transaction.
        Returns the list of posts that were actually inserted or updated.
        """
        updated: list[Post] = []
        with self._transaction() as conn:
            for post in posts:
                existing = self.get_post(post.id)

                # Skip if exists and neither title nor content changed
                if existing and existing.title == post.title and existing.content == post.content:
                    continue

                utc_time_now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                created_at = existing.created_at if existing else utc_time_now

                self._upsert_post(post, created_at, utc_time_now, conn)
                self._add_post_locations(post.id, [post.location], conn)
                updated.append(post)

        return updated

    def get_post(self, post_id: str) -> Post | None:
        """
        Retrieve a post by its unique ID.

        Args:
            post_id: Identifier of the post.

        Returns:
            Optional[Post]: Post instance if found, else None.
        """
        row = self._conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()

        if not row:
            return None
        return Post.from_database_row(dict(row))

    def get_latest_posts(self, limit: int = 10) -> list[Post]:
        """
        Fetch the most recent posts ordered by publish date.

        Args:
            limit: Maximum number of posts to return.

        Returns:
            List[Post]: List of retrieved posts.
        """
        rows = self._fetch_all("SELECT * FROM posts ORDER BY publish_date DESC LIMIT ?", (limit,))
        return [Post.from_database_row(dict(r)) for r in rows]

    def add_notification(self, notif: Notification) -> int | None:
        """
        Create a new notification entry.

        Args:
            notif: Notification model instance.

        Returns:
            Optional[int]: The notification ID if insert succeeds, None otherwise.
        """
        sql = (
            "INSERT INTO notifications ("
            "post_id, title, message, image_url, created_at, is_urgent, expires_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)"
        )
        params = (
            notif.post_id,
            notif.title,
            notif.message,
            notif.image_url,
            notif.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            notif.is_urgent,
            (notif.expires_at.strftime("%Y-%m-%d %H:%M:%S") if notif.expires_at else None),
        )
        cursor = self._execute(sql, params)
        return cursor.lastrowid if cursor else None

    def get_notifications(self, user_id: str, limit: int = 10, include_expired: bool = False) -> list[dict[str, Any]]:
        """
        Retrieve recent notifications for a specific user.

        Args:
            user_id: User identifier
            limit: Max number of notifications.
            include_expired: Flag to include expired notifications.

        Returns:
            List[Dict[str, Any]]: List of user notifications with read status.

        Raises:
            ValueError: If user_id is empty or None
            DatabaseError: If user_id doesn't match authenticated user (403 Forbidden equivalent)
        """
        if not user_id:
            raise ValueError("User ID is required")

        query = """
            SELECT n.*, un.is_read, un.read_at, un.created_at as user_notification_created_at
            FROM notifications n
            JOIN user_notifications un ON un.notification_id = n.id
            WHERE un.user_id = ?
        """
        params = [user_id]

        if not include_expired:
            query += " AND (n.expires_at IS NULL OR n.expires_at > ?)"
            params.append(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))

        query += " ORDER BY n.created_at DESC LIMIT ?"
        params.append(limit)

        rows = self._fetch_all(query, tuple(params))
        return [dict(row) for row in rows]

    def mark_notifications_read(self, user_id: str, notification_ids: list[int]) -> bool:
        """
        Mark specific notifications as read for a user. Enforces user scoping.

        Args:
            user_id: User identifier - must match the authenticated user
            notification_ids: List of notification IDs to mark as read

        Returns:
            bool: True if update succeeds, False otherwise

        Raises:
            ValueError: If user_id is empty or None
            DatabaseError: If attempting to mark notifications belonging to another user (403 Forbidden)
        """
        if not user_id:
            raise ValueError("User ID is required")

        if not notification_ids:
            return True

        # First verify all notifications belong to this user
        placeholders = ",".join("?" * len(notification_ids))
        verify_query = f"""
            SELECT notification_id FROM user_notifications
            WHERE user_id = ? AND notification_id IN ({placeholders})
        """
        verify_params = [user_id] + notification_ids

        owned_notifications = self._fetch_all(verify_query, tuple(verify_params))
        owned_ids = [row["notification_id"] for row in owned_notifications]

        # Check if user is trying to access notifications they don't own
        unauthorized_ids = set(notification_ids) - set(owned_ids)
        if unauthorized_ids:
            raise DatabaseError("403 Forbidden: Cannot access one or more requested notifications.")

        # Mark notifications as read only for this user
        update_query = f"""
            UPDATE user_notifications
            SET is_read = 1, read_at = CURRENT_TIMESTAMP
            WHERE user_id = ? AND notification_id IN ({placeholders})
        """
        update_params = [user_id] + notification_ids

        cursor = self._execute(update_query, tuple(update_params))
        return cursor.rowcount > 0 if cursor else False

    def cleanup_expired_notifications(self) -> int:
        """
        Delete notifications whose expiration date has passed.

        Returns:
            int: Number of deleted rows.
        """
        cursor = self._execute("DELETE FROM notifications WHERE expires_at <= datetime('now')")
        return cursor.rowcount if cursor else 0

    def add_push_subscription(
        self,
        info: dict[str, Any],
        user_key: str | None = None,
        device_id: str | None = None,
    ) -> bool:
        """
        Insert or update a push subscription record.

        Args:
            info: Subscription details with endpoint and keys.
            user_key: User identifier
            device_id: Device identifier for multi-device support

        Returns:
            bool: True if operation succeeds.
        """
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        # Generate device_id from endpoint if not provided for backward compatibility
        if device_id is None:
            import hashlib

            device_id = hashlib.md5(info["endpoint"].encode()).hexdigest()[:16]

        return bool(
            self._execute(
                "INSERT OR REPLACE INTO push_subscriptions"
                " (endpoint, auth, p256dh, user_key, device_id, created_at, updated_at, is_active)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
                (
                    info["endpoint"],
                    info["keys"]["auth"],
                    info["keys"]["p256dh"],
                    user_key,
                    device_id,
                    now,
                    now,
                ),
            )
        )

    def push_subscription_exists(self, endpoint: str, user_key: str | None = None) -> bool:
        """Check if a push subscription already exists for the given endpoint and user."""
        params = [endpoint]
        query = "SELECT 1 FROM push_subscriptions WHERE endpoint = ?"
        if user_key is not None:
            query += " AND user_key = ?"
            params.append(user_key)
        row = self._fetch_one(query + " LIMIT 1", tuple(params))
        return row is not None

    def remove_push_subscription(
        self,
        info: dict[str, Any],
        user_key: str | None = None,
        device_id: str | None = None,
    ) -> bool:
        """
        Remove a push subscription by its endpoint and device_id for multi-device support.
        Always removes only the specified device to prevent accidental removal of other devices.

        Args:
            info: Subscription info containing endpoint.
            user_key: User identifier for validation.
            device_id: Device identifier - required for multi-device support.

        Returns:
            bool: True if deletion succeeds.
        """
        # Generate device_id from endpoint if not provided for backward compatibility
        if device_id is None:
            import hashlib

            device_id = hashlib.md5(info["endpoint"].encode()).hexdigest()[:16]

        if user_key and device_id:
            # Remove specific device subscription for user (preferred path)
            return bool(
                self._execute(
                    "DELETE FROM push_subscriptions WHERE endpoint = ? AND user_key = ? AND device_id = ?",
                    (info["endpoint"], user_key, device_id),
                )
            )
        if device_id:
            # Remove by device_id and endpoint (fallback)
            return bool(
                self._execute(
                    "DELETE FROM push_subscriptions WHERE endpoint = ? AND device_id = ?",
                    (info["endpoint"], device_id),
                )
            )
        # Endpoint-only removal (legacy fallback - logs warning)
        logger.warning(
            "Removing push subscription by endpoint only. "
            "Consider providing device_id for better multi-device support."
        )
        return bool(
            self._execute(
                "DELETE FROM push_subscriptions WHERE endpoint = ?",
                (info["endpoint"],),
            )
        )

    def update_subscription_last_used(self, endpoint: str) -> bool:
        """Update the last_used timestamp for a push subscription."""
        return bool(
            self._execute(
                "UPDATE push_subscriptions SET last_used = CURRENT_TIMESTAMP WHERE endpoint = ?",
                (endpoint,),
            )
        )

    def has_push_subscription(self, user_key: str) -> bool:
        """Check if the given user has an active push subscription."""
        row = self._fetch_one(
            "SELECT 1 FROM push_subscriptions WHERE user_key = ? AND is_active = 1 LIMIT 1",
            (user_key,),
        )
        return row is not None

    def get_notification_settings(self, user_key: str) -> str | None:
        """
        Fetch notification settings JSON for a user.

        Args:
            user_key: Identifier for settings record.

        Returns:
            Optional[str]: JSON settings if present, else None.
        """
        row = self._fetch_one("SELECT settings FROM notification_settings WHERE user_key = ?", (user_key,))
        return row["settings"] if row else None

    def get_all_notification_settings(self) -> dict[str, str]:
        """
        Retrieve all users' notification settings.

        Returns:
            Dict[str, str]: Mapping user_key to JSON settings.
        """
        rows = self._fetch_all("SELECT user_key, settings FROM notification_settings")
        return {r["user_key"]: r["settings"] for r in rows}

    def update_notification_settings(self, user_key: str, settings: dict[str, Any]) -> bool:
        """
        Upsert notification settings for a user.

        Args:
            user_key: Identifier for the settings.
            settings: Settings dict to store.

        Returns:
            bool: True if operation succeeds.
        """
        text = json.dumps(settings)
        updated = self._execute(
            "UPDATE notification_settings SET settings = ?, updated_at = CURRENT_TIMESTAMP WHERE user_key = ?",
            (text, user_key),
        )
        if updated and isinstance(updated, sqlite3.Cursor) and updated.rowcount > 0:
            return True
        return bool(
            self._execute(
                "INSERT INTO notification_settings (user_key, settings) VALUES (?, ?)",
                (user_key, text),
            )
        )

    def update_user_keywords(self, user_key: str, keywords: list[str]) -> None:
        """Replace user's keywords list."""
        with self._transaction() as conn:
            conn.execute(
                "DELETE FROM notification_keywords WHERE user_key = ?",
                (user_key,),
            )
            for kw in keywords:
                conn.execute(
                    "INSERT OR IGNORE INTO notification_keywords (user_key, keyword) VALUES (?, ?)",
                    (user_key, kw),
                )
                conn.execute(
                    "INSERT OR IGNORE INTO keywords (keyword) VALUES (?)",
                    (kw,),
                )

    def get_user_keywords(self, user_key: str) -> list[str]:
        """Retrieve keywords associated with a user."""
        rows = self._fetch_all(
            "SELECT keyword FROM notification_keywords WHERE user_key = ?",
            (user_key,),
        )
        return [r["keyword"] for r in rows]

    def add_global_keywords(self, keywords: list[str]) -> None:
        """Add global keywords to the database."""
        if not keywords:
            return
        with self._transaction() as conn:
            for kw in keywords:
                conn.execute("INSERT OR IGNORE INTO keywords (keyword) VALUES (?)", (kw,))

    def get_all_keywords(self) -> list[str]:
        """List all distinct keywords in the database."""
        rows = self._fetch_all("SELECT keyword FROM keywords ORDER BY keyword")
        return [r["keyword"] for r in rows]

    def get_available_locations(self) -> list[str]:
        """
        List distinct non-empty locations from posts.

        Returns:
            List[str]: Sorted list of locations.
        """
        rows = self._fetch_all("SELECT DISTINCT location FROM posts WHERE location <> '' ORDER BY location")
        return [r["location"] for r in rows]

    # --- Token Storage ---
    def store_token(self, session_id: str, user_id: str, token: str) -> bool:
        """Store or update an access token for a session."""
        return bool(
            self._execute(
                "INSERT INTO auth_tokens (session_id, user_id, token, last_accessed)"
                " VALUES (?, ?, ?, CURRENT_TIMESTAMP) "
                "ON CONFLICT(session_id) DO UPDATE SET token=excluded.token, user_id=excluded.user_id,"
                " updated_at=CURRENT_TIMESTAMP, last_accessed=CURRENT_TIMESTAMP",
                (session_id, user_id, token),
            )
        )

    def get_token(self, session_id: str) -> str | None:
        """Retrieve the access token for a session ID."""
        row = self._fetch_one("SELECT token FROM auth_tokens WHERE session_id = ?", (session_id,))
        if row:
            self._safe_execute(
                "UPDATE auth_tokens SET last_accessed=CURRENT_TIMESTAMP WHERE session_id = ?",
                (session_id,),
            )
            return row["token"]
        return None

    def delete_token(self, session_id: str) -> bool:
        """Delete the access token for a session ID."""
        return bool(self._execute("DELETE FROM auth_tokens WHERE session_id = ?", (session_id,)))

    def cleanup_old_tokens(self, days: int) -> int:
        """Delete tokens that haven't been accessed in the last `days` days."""
        cursor = self._execute(
            "DELETE FROM auth_tokens WHERE last_accessed <= datetime('now', ?)",
            (f"-{days} day",),
        )
        return cursor.rowcount if cursor else 0

    def get_user_session_count(self, user_id: str) -> int:
        """Count active sessions for a user."""
        row = self._fetch_one(
            "SELECT COUNT(*) as cnt FROM auth_tokens WHERE user_id = ?",
            (user_id,),
        )
        return row["cnt"] if row else 0

    def get_push_subscriptions_for_users(self, user_keys: list[str], urgent: bool = False) -> list[dict[str, Any]]:
        """
        Get push subscriptions for specific users.

        Args:
            user_keys: List of user keys to get subscriptions for. If empty, returns all active subscriptions
                      only when urgent=True, otherwise returns empty list.
            urgent: If True, allows returning all subscriptions when user_keys is empty.

        Returns:
            List[Dict[str, Any]]: Active subscriptions for the specified users with endpoint, keys, and user_key.
        """
        if not user_keys:
            if urgent:
                # Return all active subscriptions when urgent and no specific users requested
                query = """
                    SELECT endpoint, auth, p256dh, user_key, device_id
                    FROM push_subscriptions
                    WHERE is_active = 1 AND user_key IS NOT NULL
                """
                rows = self._fetch_all(query, ())
            else:
                # Return empty list when not urgent and no users specified
                return []
        else:
            placeholders = ",".join("?" * len(user_keys))
            query = f"""
                SELECT endpoint, auth, p256dh, user_key, device_id
                FROM push_subscriptions
                WHERE user_key IN ({placeholders}) AND is_active = 1
            """
            rows = self._fetch_all(query, tuple(user_keys))

        return [
            {
                "endpoint": r["endpoint"],
                "keys": {"auth": r["auth"], "p256dh": r["p256dh"]},
                "user_key": r["user_key"],
                "device_id": r["device_id"],
            }
            for r in rows
        ]

    def add_user_notification(self, user_id: str, notification_id: int) -> bool:
        """
        Create a user notification entry for a specific user and notification.

        Args:
            user_id: User identifier
            notification_id: Notification ID

        Returns:
            bool: True if insert succeeds, False otherwise.
        """
        sql = (
            "INSERT INTO user_notifications (user_id, notification_id, is_read, created_at) "
            "VALUES (?, ?, 0, CURRENT_TIMESTAMP)"
        )
        return bool(self._execute(sql, (user_id, notification_id)))

    def add_user_notifications_bulk(self, notification_id: int, user_ids: list[str]) -> bool:
        """
        Create user notification entries for multiple users for a single notification.

        Args:
            notification_id: Notification ID
            user_ids: List of user identifiers

        Returns:
            bool: True if all inserts succeed, False otherwise.
        """
        if not user_ids:
            return True

        with self._transaction() as conn:
            for user_id in user_ids:
                conn.execute(
                    "INSERT INTO user_notifications (user_id, notification_id, is_read, created_at) "
                    "VALUES (?, ?, 0, CURRENT_TIMESTAMP)",
                    (user_id, notification_id),
                )
        return True

    def mark_user_notification_read(self, user_id: str, notification_id: int) -> bool:
        """
        Mark a specific notification as read for a user.

        Args:
            user_id: User identifier
            notification_id: Notification ID

        Returns:
            bool: True if update succeeds, False otherwise.
        """
        sql = (
            "UPDATE user_notifications SET is_read = 1, read_at = CURRENT_TIMESTAMP "
            "WHERE user_id = ? AND notification_id = ?"
        )
        cursor = self._execute(sql, (user_id, notification_id))
        return cursor.rowcount > 0 if cursor else False

    def mark_all_user_notifications_read(self, user_id: str) -> bool:
        """
        Mark all notifications as read for a specific user.

        Args:
            user_id: User identifier

        Returns:
            bool: True if update succeeds, False otherwise.
        """
        sql = (
            "UPDATE user_notifications SET is_read = 1, read_at = CURRENT_TIMESTAMP "
            "WHERE user_id = ? AND is_read = 0"
        )
        cursor = self._execute(sql, (user_id,))
        return cursor.rowcount > 0 if cursor else False

    def get_user_notifications(self, user_id: str, limit: int = 10, unread_only: bool = False) -> list[dict[str, Any]]:
        """
        Get notifications for a specific user with read status.

        Args:
            user_id: User identifier
            limit: Maximum number of notifications to return
            unread_only: If True, only return unread notifications

        Returns:
            List[Dict[str, Any]]: List of notifications with read status.
        """
        query = """
            SELECT n.*, un.is_read, un.read_at, un.created_at as user_notification_created_at
            FROM notifications n
            JOIN user_notifications un ON un.notification_id = n.id
            WHERE un.user_id = ?
        """
        params = [user_id]

        if unread_only:
            query += " AND un.is_read = 0"

        query += " AND (n.expires_at IS NULL OR n.expires_at > datetime('now'))"
        query += " ORDER BY n.created_at DESC LIMIT ?"
        params.append(limit)

        rows = self._fetch_all(query, tuple(params))
        return [dict(row) for row in rows]

    def get_user_notification_count(self, user_id: str, unread_only: bool = True) -> int:
        """
        Get count of notifications for a user.

        Args:
            user_id: User identifier
            unread_only: If True, only count unread notifications

        Returns:
            int: Number of notifications matching criteria.
        """
        query = """
            SELECT COUNT(*)
            FROM notifications n
            JOIN user_notifications un ON un.notification_id = n.id
            WHERE un.user_id = ?
        """
        params = [user_id]

        if unread_only:
            query += " AND un.is_read = 0"

        query += " AND (n.expires_at IS NULL OR n.expires_at > datetime('now'))"

        row = self._fetch_one(query, tuple(params))
        return row[0] if row else 0

    def cleanup_expired_user_notifications(self) -> int:
        """
        Delete user notifications for expired notifications.

        Returns:
            int: Number of deleted rows.
        """
        cursor = self._execute(
            """
            DELETE FROM user_notifications
            WHERE notification_id IN (
                SELECT id FROM notifications
                WHERE expires_at <= datetime('now')
            )
        """
        )
        return cursor.rowcount if cursor else 0

    def cleanup_user_notifications(self, user_id: str) -> int:
        """
        Delete all user notifications for a specific user.
        Used when deactivating/removing a user.

        Args:
            user_id: User identifier

        Returns:
            int: Number of deleted rows.
        """
        cursor = self._execute("DELETE FROM user_notifications WHERE user_id = ?", (user_id,))
        return cursor.rowcount if cursor else 0

    def delete_notification(self, notification_id: int) -> bool:
        """
        Delete a notification and all associated user notification entries.
        This ensures proper cascade deletion when notifications are removed.

        Args:
            notification_id: The notification ID to delete

        Returns:
            bool: True if deletion succeeded, False otherwise.
        """
        try:
            # The foreign key constraint with ON DELETE CASCADE should handle
            # user_notifications cleanup automatically, but we'll be explicit
            with self._transaction() as conn:
                # First delete user notification entries
                conn.execute(
                    "DELETE FROM user_notifications WHERE notification_id = ?",
                    (notification_id,),
                )

                # Then delete the notification itself
                cursor = conn.execute("DELETE FROM notifications WHERE id = ?", (notification_id,))

                return cursor.rowcount > 0

        except Exception as e:
            logger.error("Error deleting notification %s: %s", notification_id, e)
            return False

    def _migrate_notifications_schema(self) -> None:
        """
        Migrate from old notification schema to new user_notifications schema.
        This is a one-time migration that handles existing data.
        """
        with self._transaction() as conn:
            # Check if migration is needed by looking for the old is_read column
            try:
                conn.execute("SELECT is_read FROM notifications LIMIT 1")
                # Old schema exists, need to migrate
                logger.info("Migrating notification schema to user_notifications table")

                # Get all existing notifications
                old_notifications = conn.execute("SELECT id, is_read FROM notifications").fetchall()

                # For each notification, if it was marked as read, we need to create user_notifications entries
                # Since we don't have user context in the old schema, we'll assume global read state
                # This is a limitation of the old schema - we can't recover per-user read state
                for notif in old_notifications:
                    if notif["is_read"]:
                        # Get all active push subscriptions (as a proxy for active users)
                        subscriptions = conn.execute(
                            "SELECT DISTINCT user_key FROM push_subscriptions WHERE user_key IS NOT NULL"
                        ).fetchall()
                        for sub in subscriptions:
                            if sub["user_key"]:
                                conn.execute(
                                    "INSERT OR IGNORE INTO user_notifications "
                                    "(user_id, notification_id, is_read, read_at) "
                                    "VALUES (?, ?, ?, ?)",
                                    (
                                        sub["user_key"],
                                        notif["id"],
                                        1,
                                        datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                                    ),
                                )

                # Remove the old is_read column
                # SQLite doesn't support DROP COLUMN, so we need to recreate the table
                conn.execute("ALTER TABLE notifications RENAME TO notifications_old")

                # Create new notifications table without is_read
                conn.execute(
                    """
                    CREATE TABLE notifications (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        post_id TEXT,
                        message TEXT NOT NULL,
                        title TEXT NOT NULL,
                        image_url TEXT,
                        is_urgent INTEGER DEFAULT 0,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        expires_at TEXT,
                        FOREIGN KEY(post_id) REFERENCES posts(id)
                    )
                """
                )

                # Copy data without is_read column
                conn.execute(
                    """
                    INSERT INTO notifications (
                        id, post_id, message, title, image_url, is_urgent, created_at, expires_at
                    )
                    SELECT
                        id, post_id, message, title, image_url, is_urgent, created_at, expires_at
                    FROM notifications_old
                    """
                )

                # Drop old table
                conn.execute("DROP TABLE notifications_old")

                # Recreate indexes
                conn.execute("CREATE INDEX IF NOT EXISTS idx_notifications_expires ON notifications(expires_at)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_notifications_created ON notifications(created_at)")

                logger.info("Notification schema migration completed")

            except sqlite3.OperationalError:
                # is_read column doesn't exist, schema is already migrated
                pass

    def cleanup_user_data(self, user_id: str) -> dict[str, int]:
        """
        Clean up all notification data for a user when they're deactivated/removed.

        Args:
            user_id: User identifier

        Returns:
            Dict[str, int]: Number of records cleaned up from each table
        """
        cleanup_counts = {}

        # Clean up user notifications
        cleanup_counts["user_notifications"] = self.cleanup_user_notifications(user_id)

        # Clean up notification settings
        try:
            settings_deleted = self._execute(
                "DELETE FROM notification_settings WHERE user_key = ?", (user_id,)
            ).rowcount
            cleanup_counts["notification_settings"] = settings_deleted
        except (ValueError, TypeError, RuntimeError) as e:
            logger.error("Error cleaning up notification settings for user %s: %s", user_id, e)
            cleanup_counts["notification_settings"] = 0

        # Clean up push subscriptions
        try:
            subs_deleted = self._execute("DELETE FROM push_subscriptions WHERE user_key = ?", (user_id,)).rowcount
            cleanup_counts["push_subscriptions"] = subs_deleted
        except (ValueError, TypeError, RuntimeError) as e:
            logger.error("Error cleaning up push subscriptions for user %s: %s", user_id, e)
            cleanup_counts["push_subscriptions"] = 0

        # Clean up keyword associations
        try:
            keywords_deleted = self._execute(
                "DELETE FROM notification_keywords WHERE user_key = ?", (user_id,)
            ).rowcount
            cleanup_counts["notification_keywords"] = keywords_deleted
        except (ValueError, TypeError, RuntimeError) as e:
            logger.error("Error cleaning up keywords for user %s: %s", user_id, e)
            cleanup_counts["notification_keywords"] = 0

        total_cleaned = sum(cleanup_counts.values())
        if total_cleaned > 0:
            logger.info(
                "Cleaned up %d total records for user %s: %s",
                total_cleaned,
                user_id,
                cleanup_counts,
            )

        return cleanup_counts

    # Helper methods
    def _fetch_one(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        """Fetch a single row from the database."""
        try:
            with self._lock:
                return self._conn.execute(sql, params).fetchone()
        except sqlite3.Error as e:
            logger.error("SQL fetch one error. Query: %s, Params: %s, Error: %s", sql, params, e)
            raise DatabaseError(f"Fetch one failed for SQL: {sql} with params {params}: {e}") from e

    def _fetch_all(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        """Fetch all rows from the database."""
        try:
            with self._lock:
                return self._conn.execute(sql, params).fetchall()
        except sqlite3.Error as e:
            logger.error("SQL fetch all error. Query: %s, Params: %s, Error: %s", sql, params, e)
            raise DatabaseError(f"Fetch all failed for SQL: {sql} with params {params}: {e}") from e

    def _safe_execute(self, sql: str, params: tuple = ()) -> Any:
        """Execute SQL safely without transaction."""
        try:
            with self._lock:
                return self._conn.execute(sql, params)
        except sqlite3.Error as e:
            logger.error("Safe execute error. Query: %s, Params: %s, Error: %s", sql, params, e)
            return None

    def _add_post_locations(
        self,
        post_id: str,
        locations: list[str],
        conn: sqlite3.Connection | None = None,
    ) -> None:
        """
        Insert mappings between a post and one or more locations.

        Args:
            post_id (str): The post's unique identifier.
            locations (List[str]): List of location strings to associate with the post.
            conn (Optional[sqlite3.Connection], optional): Existing DB connection. If None, uses self._conn.
        """
        if not locations:
            return
        sql = "INSERT OR IGNORE INTO post_locations (post_id, location) VALUES (?, ?)"
        if conn is None:
            conn = self._conn
        for loc in locations:
            if loc:
                conn.execute(sql, (post_id, loc))
