"""Notification application package."""

# Lazy import of the Flask factory to avoid circular dependencies when other
# modules import ``app`` for metadata such as the version.
from .version import __version__  # re-export for ``app.__version__``

__all__ = ["create_app", "__version__"]


def create_app(config_name: str = "default"):
    """Factory function wrapper for the Flask application."""
    from .web.main import (
        create_app as _create_app,  # pylint:disable=import-outside-toplevel
    )

    return _create_app(config_name)
