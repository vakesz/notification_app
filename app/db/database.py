"""Database connection and operations."""

import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.core.config import Config
from app.db.models import Notification, Post

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Custom exception raised for database operation failures."""


# TODO: Consider using a different approach with SQLAlchemy or another ORM for better abstraction and ease of use.
class DatabaseManager:
    """
    Simplified manager for SQLite database operations
    in the notifications application.

    Handles table initialization, CRUD operations for
    posts, notifications, push subscriptions,
    blog credentials, and settings.
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
                " title TEXT NOT NULL, image_url TEXT,"
                " is_read INTEGER DEFAULT 0, is_urgent INTEGER DEFAULT 0,"
                " created_at TEXT DEFAULT CURRENT_TIMESTAMP, expires_at TEXT,"
                " FOREIGN KEY(post_id) REFERENCES posts(id)"
            ),
        ),
        (
            "push_subscriptions",
            (
                "id INTEGER PRIMARY KEY AUTOINCREMENT, endpoint TEXT UNIQUE NOT NULL,"
                " auth TEXT NOT NULL, p256dh TEXT NOT NULL, user_key TEXT,"
                " created_at TEXT DEFAULT CURRENT_TIMESTAMP,"
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
            ("user_key TEXT NOT NULL, keyword TEXT NOT NULL," " PRIMARY KEY(user_key, keyword)"),
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
        self._lock = threading.Lock()
        self._conn = self._create_connection()
        self._initialize_db()

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
                timeout=Config.HTTP_TIMEOUT,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            return conn
        except sqlite3.Error as e:
            logger.error("Connection error: %s", e)
            raise DatabaseError(f"Connection error: {e}") from e

    @contextmanager
    def _transaction(self) -> sqlite3.Connection:  # type: ignore
        """
        Context manager for a database transaction.
        Automatically commits on success or rolls back on error.

        Yields:
            sqlite3.Connection: Open transaction connection.

        Raises:
            DatabaseError: If an error occurs during transaction.
        """
        conn = self._conn
        # Using a long-lived connection with a thread lock for simplicity.
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error("Transaction failed: %s", e)
            raise DatabaseError(f"Transaction failed: {e}") from e
        finally:
            pass

    def _initialize_db(self) -> None:
        """
        Create database tables as defined in the schema if they don't exist.
        """
        with self._transaction() as conn:
            for table, definition in self._SCHEMA:
                conn.execute(f"CREATE TABLE IF NOT EXISTS {table} ({definition})")
            self._ensure_column(conn, "auth_tokens", "user_id", "TEXT")
            self._ensure_column(conn, "auth_tokens", "last_accessed", "TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_created ON posts(created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_tokens_user ON auth_tokens(user_id)")

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
        with self._transaction() as conn:
            # TODO: Surface database errors to callers instead of returning the
            #       raw cursor so that failures can be handled upstream.
            return conn.execute(sql, params)

    def add_post(self, post: Post) -> bool:
        """
        Insert or update a post record.

        Args:
            post: Post model instance to save.

        Returns:
            bool: True if successful, False otherwise.
        """
        sql = (
            "INSERT OR REPLACE INTO posts ("
            "id, title, content, publish_date, location, department,"
            " category, link, is_urgent, likes, comments, has_image, image_url,"
            " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        now = datetime.utcnow().isoformat()
        params = (
            post.id,
            post.title,
            post.content,
            post.publish_date.isoformat(),
            post.location,
            post.department,
            post.category,
            post.link,
            int(post.is_urgent),
            post.likes,
            post.comments,
            int(post.has_image),
            post.image_url,
            now,
            now,
        )
        result = self._execute(sql, params)
        if result:
            self._add_post_locations(post.id, [post.location])
        return bool(result)

    def add_posts_bulk(self, posts: List[Post]) -> List[Post]:
        """Insert multiple posts in a single transaction ignoring duplicates."""
        added: List[Post] = []
        sql = (
            "INSERT OR IGNORE INTO posts ("
            "id, title, content, publish_date, location, department,"
            " category, link, is_urgent, likes, comments, has_image, image_url,"
            " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        now = datetime.utcnow().isoformat()
        with self._transaction() as conn:
            for post in posts:
                params = (
                    post.id,
                    post.title,
                    post.content,
                    post.publish_date.isoformat(),
                    post.location,
                    post.department,
                    post.category,
                    post.link,
                    int(post.is_urgent),
                    post.likes,
                    post.comments,
                    int(post.has_image),
                    post.image_url,
                    now,
                    now,
                )
                try:
                    conn.execute(sql, params)
                    if conn.total_changes > len(added):
                        added.append(post)
                        self._add_post_locations(post.id, [post.location], conn)
                except sqlite3.IntegrityError:
                    continue
        return added

    def get_post(self, post_id: str) -> Optional[Post]:
        """
        Retrieve a post by its unique ID.

        Args:
            post_id: Identifier of the post.

        Returns:
            Optional[Post]: Post instance if found, else None.
        """
        row = self._fetch_one("SELECT * FROM posts WHERE id = ?", (post_id,))
        return Post.from_dict(dict(row)) if row else None

    def get_latest_posts(self, limit: int = 10) -> List[Post]:
        """
        Fetch the most recent posts ordered by publish date.

        Args:
            limit: Maximum number of posts to return.

        Returns:
            List[Post]: List of retrieved posts.
        """
        rows = self._fetch_all("SELECT * FROM posts ORDER BY publish_date DESC LIMIT ?", (limit,))
        return [Post.from_dict(dict(r)) for r in rows]

    def add_notification(self, notif: Notification) -> bool:
        """
        Create a new notification entry.

        Args:
            notif: Notification model instance.

        Returns:
            bool: True if insert succeeds, False otherwise.
        """
        sql = (
            "INSERT INTO notifications ("
            "post_id, title, message, image_url, created_at, is_read, is_urgent, expires_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        )
        params = (
            notif.post_id,
            notif.title,
            notif.message,
            notif.image_url,
            notif.created_at.isoformat(),
            notif.is_read,
            notif.is_urgent,
            notif.expires_at.isoformat(),
        )
        return bool(self._execute(sql, params))

    def get_notifications(self, limit: int = 10, include_expired: bool = False) -> List[Notification]:
        """
        Retrieve recent notifications, optionally including expired ones.

        Args:
            limit: Max number of notifications.
            include_expired: Flag to include expired notifications.

        Returns:
            List[Notification]: List of notifications.
        """
        query = "SELECT * FROM notifications WHERE 1=1"
        params: List[Any] = []
        if not include_expired:
            query += " AND (expires_at IS NULL OR expires_at > ?)"
            params.append(datetime.utcnow().isoformat())
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = self._fetch_all(query, tuple(params))
        return [Notification.from_dict(dict(r)) for r in rows]

    def mark_notifications_read(self) -> bool:
        """
        Mark all notifications as read.

        Returns:
            bool: True if update succeeds, False otherwise.
        """
        return bool(self._execute("UPDATE notifications SET is_read = 1"))

    def cleanup_expired_notifications(self) -> int:
        """
        Delete notifications whose expiration date has passed.

        Returns:
            int: Number of deleted rows.
        """
        cursor = self._execute("DELETE FROM notifications WHERE expires_at <= datetime('now')")
        return cursor.rowcount if cursor else 0

    def get_notification_summary(self) -> Dict[str, int]:
        """
        Compute summary counts for active notifications.

        Returns:
            Dict[str, int]: Counts for total, unread, and urgent_unread.
        """
        sql = (
            "SELECT COUNT(*) AS total,"
            " SUM(CASE WHEN is_read = 0 THEN 1 ELSE 0 END) AS unread,"
            " SUM(CASE WHEN is_read = 0 AND is_urgent = 1 THEN 1 ELSE 0 END) AS urgent_unread"
            " FROM notifications WHERE expires_at > datetime('now')"
        )
        row = self._fetch_one(sql)
        return (
            {k: row[k] or 0 for k in ("total", "unread", "urgent_unread")}
            if row
            else {"total": 0, "unread": 0, "urgent_unread": 0}
        )

    def add_push_subscription(self, info: Dict[str, Any], user_key: Optional[str] = None) -> bool:
        """
        Insert or update a push subscription record.

        Args:
            info: Subscription details with endpoint and keys.

        Returns:
            bool: True if operation succeeds.
        """
        now = datetime.utcnow().isoformat()
        return bool(
            self._execute(
                "INSERT OR REPLACE INTO push_subscriptions"
                " (endpoint, auth, p256dh, user_key, created_at, updated_at, is_active)"
                " VALUES (?, ?, ?, ?, ?, ?, 1)",
                (
                    info["endpoint"],
                    info["keys"]["auth"],
                    info["keys"]["p256dh"],
                    user_key,
                    now,
                    now,
                ),
            )
        )

    def push_subscription_exists(self, endpoint: str, user_key: Optional[str] = None) -> bool:
        """Check if a push subscription already exists for the given endpoint and user."""
        params = [endpoint]
        query = "SELECT 1 FROM push_subscriptions WHERE endpoint = ?"
        if user_key is not None:
            query += " AND user_key = ?"
            params.append(user_key)
        row = self._fetch_one(query + " LIMIT 1", tuple(params))
        return row is not None

    def remove_push_subscription(self, info: Dict[str, Any]) -> bool:
        """
        Remove a push subscription by its endpoint.

        Args:
            info: Subscription info containing endpoint.

        Returns:
            bool: True if deletion succeeds.
        """
        return bool(self._execute("DELETE FROM push_subscriptions WHERE endpoint = ?", (info["endpoint"],)))

    def get_all_push_subscriptions(self) -> List[Dict[str, Any]]:
        """
        List all active push subscriptions.

        Returns:
            List[Dict[str, Any]]: Active subscriptions with endpoint and keys.
        """
        rows = self._fetch_all("SELECT endpoint, auth, p256dh FROM push_subscriptions WHERE is_active = 1")
        return [
            {
                "endpoint": r["endpoint"],
                "keys": {"auth": r["auth"], "p256dh": r["p256dh"]},
            }
            for r in rows
        ]

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

    def get_notification_settings(self, user_key: str) -> Optional[str]:
        """
        Fetch notification settings JSON for a user.

        Args:
            user_key: Identifier for settings record.

        Returns:
            Optional[str]: JSON settings if present, else None.
        """
        row = self._fetch_one("SELECT settings FROM notification_settings WHERE user_key = ?", (user_key,))
        return row["settings"] if row else None

    def get_all_notification_settings(self) -> Dict[str, str]:
        """
        Retrieve all users' notification settings.

        Returns:
            Dict[str, str]: Mapping user_key to JSON settings.
        """
        rows = self._fetch_all("SELECT user_key, settings FROM notification_settings")
        return {r["user_key"]: r["settings"] for r in rows}

    def update_notification_settings(self, user_key: str, settings: Dict[str, Any]) -> bool:
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

    def update_user_keywords(self, user_key: str, keywords: List[str]) -> None:
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

    def get_user_keywords(self, user_key: str) -> List[str]:
        """Retrieve keywords associated with a user."""
        rows = self._fetch_all(
            "SELECT keyword FROM notification_keywords WHERE user_key = ?",
            (user_key,),
        )
        return [r["keyword"] for r in rows]

    def add_global_keywords(self, keywords: List[str]) -> None:
        """Add global keywords to the database."""
        if not keywords:
            return
        with self._transaction() as conn:
            for kw in keywords:
                conn.execute("INSERT OR IGNORE INTO keywords (keyword) VALUES (?)", (kw,))

    def get_all_keywords(self) -> List[str]:
        """List all distinct keywords in the database."""
        rows = self._fetch_all("SELECT keyword FROM keywords ORDER BY keyword")
        return [r["keyword"] for r in rows]

    def get_available_locations(self) -> List[str]:
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

    def get_token(self, session_id: str) -> Optional[str]:
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

    def export_posts_to_json(self, file_path: str) -> int:
        """
        Export all posts to a JSON file.

        Args:
            file_path: Path where to save the JSON file.

        Returns:
            int: Number of posts exported.
        """
        try:
            posts = self.get_latest_posts(limit=1000)  # Get a large number of posts
            posts_data = []

            for post in posts:
                post_dict = {
                    "id": post.id,
                    "title": post.title,
                    "content": post.content,
                    "publish_date": (post.publish_date.isoformat() if post.publish_date else None),
                    "category": post.category,
                    "department": post.department,
                    "location": post.location,
                    "is_urgent": post.is_urgent,
                    "has_image": post.has_image,
                    "image_url": post.image_url,
                    "likes": post.likes,
                    "comments": post.comments,
                    "link": post.link,
                    "created_at": (post.created_at.isoformat() if post.created_at else None),
                    "updated_at": (post.updated_at.isoformat() if post.updated_at else None),
                }
                posts_data.append(post_dict)

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(posts_data, f, ensure_ascii=False, indent=2)

            return len(posts_data)

        except Exception as e:
            logger.error("Failed to export posts to JSON: %s", e)
            raise DatabaseError(f"Export failed: {e}") from e

    # Helper methods
    def _fetch_one(self, sql: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        """
        Execute a query and return the first row.

        Args:
            sql: SQL SELECT query.
            params: Query parameters.

        Returns:
            Optional[sqlite3.Row]: First result row or None.
        """
        with self._transaction() as conn:
            cursor = conn.execute(sql, params)
            return cursor.fetchone()

    def _fetch_all(self, sql: str, params: tuple = ()) -> List[sqlite3.Row]:
        """
        Execute a query and return all rows.

        Args:
            sql: SQL SELECT query.
            params: Query parameters.

        Returns:
            List[sqlite3.Row]: List of result rows.
        """
        with self._transaction() as conn:
            cursor = conn.execute(sql, params)
            return cursor.fetchall()

    def _safe_execute(self, sql: str, params: tuple = ()) -> Any:
        """
        Safely execute a SQL statement, suppressing errors.

        Args:
            sql: SQL query or command.
            params: Tuple of parameters.

        Returns:
            sqlite3.Cursor or False: Cursor if successful, else False.
        """
        try:
            return self._execute(sql, params)
        except DatabaseError:
            return False

    def _add_post_locations(
        self,
        post_id: str,
        locations: List[str],
        conn: Optional[sqlite3.Connection] = None,
    ) -> None:
        """Insert mappings between a post and locations."""
        if not locations:
            return
        sql = "INSERT OR IGNORE INTO post_locations (post_id, location) VALUES (?, ?)"
        if conn is None:
            conn = self._conn
        for loc in locations:
            if loc:
                conn.execute(sql, (post_id, loc))
