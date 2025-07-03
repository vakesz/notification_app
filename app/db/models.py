"""Data models for the notification app."""

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Optional


@dataclass
class Post:
    """Represents a blog post."""

    title: str
    content: str
    publish_date: datetime
    location: str
    department: str
    category: str
    id: Optional[str] = None
    link: Optional[str] = None
    is_urgent: bool = False
    likes: int = 0
    comments: int = 0
    has_image: bool = False
    image_url: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        # Validate required fields
        for field_name in ("title", "content", "location", "department", "category"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name.capitalize()} is required and must be a non-empty string")

        if not isinstance(self.publish_date, datetime):
            raise ValueError("publish_date must be a datetime object")

        # Generate unique ID if missing
        if not self.id:
            self.id = self._generate_id()

    def _generate_id(self) -> str:
        """Create a short, deterministic ID."""
        hash_input = (
            f"{self.title}{self.content}"
            f"{self.publish_date.isoformat()}{self.location}"
            f"{self.department}{self.category}"
        )
        digest = hashlib.sha256(hash_input.encode()).hexdigest()[:8]
        timestamp = int(self.publish_date.timestamp())
        return f"{digest}-{timestamp}"

    @classmethod
    def from_database_row(cls, data: Dict[str, Any]) -> "Post":
        """Create a Post instance from a database row dictionary."""
        # Handle datetime fields
        if isinstance(data.get("publish_date"), str):
            data["publish_date"] = datetime.fromisoformat(data["publish_date"])
        if isinstance(data.get("created_at"), str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if isinstance(data.get("updated_at"), str):
            data["updated_at"] = datetime.fromisoformat(data["updated_at"])

        # Filter out any extra fields that aren't part of the dataclass
        valid_fields = {
            "id",
            "title",
            "content",
            "publish_date",
            "location",
            "department",
            "category",
            "link",
            "is_urgent",
            "likes",
            "comments",
            "has_image",
            "image_url",
            "created_at",
            "updated_at",
        }
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}

        return cls(**filtered_data)

    def to_dict(self) -> Dict[str, Any]:
        """Convert post to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "publish_date": self.publish_date.isoformat() if self.publish_date else None,
            "location": self.location,
            "department": self.department,
            "category": self.category,
            "link": self.link,
            "is_urgent": self.is_urgent,
            "likes": self.likes,
            "comments": self.comments,
            "has_image": self.has_image,
            "image_url": self.image_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


@dataclass
class Notification:
    """Represents a user notification."""

    post_id: str
    title: str
    message: str
    created_at: datetime
    id: Optional[str] = None
    is_urgent: bool = False
    expires_at: Optional[datetime] = None
    image_url: Optional[str] = "static/img/notification/icon-notification.png"

    def __post_init__(self) -> None:
        """Validate and initialize the notification."""
        if not isinstance(self.post_id, str) or not self.post_id:
            raise ValueError("post_id is required and must be a non-empty string")
        if not isinstance(self.title, str) or not self.title:
            raise ValueError("title is required and must be a non-empty string")
        if not isinstance(self.message, str) or not self.message:
            raise ValueError("message is required and must be a non-empty string")
        if not isinstance(self.created_at, datetime):
            raise ValueError("created_at must be a datetime object")

        # Set default expiration to 30 days after creation
        if self.expires_at is None:
            self.expires_at = self.created_at + timedelta(days=30)

        # Generate notification ID if missing
        if not self.id:
            self.id = self._generate_id()

    def _generate_id(self) -> str:
        """Create a short, deterministic ID based on post_id, message, and created_at."""
        base = f"{self.post_id}{self.message}{self.created_at.isoformat()}"
        return f"notif-{hashlib.sha256(base.encode()).hexdigest()[:8]}"

    @classmethod
    def from_database_row(cls, data: Dict[str, Any]) -> "Notification":
        """Create a Notification instance from a database row dictionary."""
        for key in ("created_at", "expires_at"):
            if isinstance(data.get(key), str):
                data[key] = datetime.fromisoformat(data[key])
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        """Convert notification to dictionary for JSON serialization."""
        return {
            "id": getattr(self, "id", None),
            "post_id": self.post_id,
            "title": self.title,
            "message": self.message,
            "image_url": self.image_url,
            "is_urgent": self.is_urgent,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }


@dataclass
class UserNotification:
    """Represents a user's relationship to a notification with read state."""

    user_id: str
    notification_id: str
    is_read: bool = False
    read_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    id: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate the user notification."""
        if not isinstance(self.user_id, str) or not self.user_id:
            raise ValueError("user_id is required and must be a non-empty string")
        if not isinstance(self.notification_id, str) or not self.notification_id:
            raise ValueError("notification_id is required and must be a non-empty string")
        if not isinstance(self.is_read, bool):
            raise ValueError("is_read must be a boolean")

        # Set created_at if not provided
        if self.created_at is None:
            self.created_at = datetime.now()

    @classmethod
    def from_database_row(cls, data: Dict[str, Any]) -> "UserNotification":
        """Create a UserNotification instance from a database row dictionary."""
        for key in ("read_at", "created_at"):
            if isinstance(data.get(key), str):
                data[key] = datetime.fromisoformat(data[key])

        # Filter out any extra fields that aren't part of the dataclass
        valid_fields = {"id", "user_id", "notification_id", "is_read", "read_at", "created_at"}
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}

        return cls(**filtered_data)

    def to_dict(self) -> Dict[str, Any]:
        """Convert user notification to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "notification_id": self.notification_id,
            "is_read": self.is_read,
            "read_at": self.read_at.isoformat() if self.read_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
