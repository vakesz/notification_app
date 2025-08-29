"""Authentication service for Microsoft Azure AD."""

import logging
import re
from typing import Any
from urllib.parse import quote

import requests
from msal import ConfidentialClientApplication

from app.core.config import Config

logger = logging.getLogger(__name__)


class AuthService:
    """Handles Microsoft Azure AD authentication."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        authority: str,
        redirect_uri: str,
        scope: list,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.authority = authority
        self.redirect_uri = redirect_uri
        self.scope = scope

        self.msal_app = ConfidentialClientApplication(client_id, authority=authority, client_credential=client_secret)

    def get_authorization_url(self, state: str) -> str:
        """Get the authorization URL for Microsoft SSO."""
        try:
            auth_url = self.msal_app.get_authorization_request_url(
                self.scope, state=state, redirect_uri=self.redirect_uri
            )
            logger.info("Generated authorization URL")
            return auth_url
        except Exception as e:
            logger.error("Error generating authorization URL: %s", e)
            raise RuntimeError("Failed to generate authorization URL") from e

    def acquire_token(self, authorization_code: str) -> dict[str, Any]:
        """Acquire token using authorization code."""
        try:
            result = self.msal_app.acquire_token_by_authorization_code(
                authorization_code, scopes=self.scope, redirect_uri=self.redirect_uri
            )

            if "error" in result:
                error_desc = result.get("error_description", "Unknown error")
                logger.error("Token acquisition error: %s", error_desc)
                raise RuntimeError(f"Token acquisition failed: {error_desc}")

            logger.info("Successfully acquired token")
            return result

        except Exception as e:
            logger.error("Error acquiring token: %s", e)
            raise RuntimeError("Failed to acquire token") from e

    def get_logout_url(self, post_logout_redirect_uri: str) -> str:
        """Get the logout URL with properly encoded redirect URI."""
        encoded_uri = quote(post_logout_redirect_uri, safe="")
        return f"{self.authority}/oauth2/v2.0/logout?post_logout_redirect_uri={encoded_uri}"

    def validate_user(self, user_claims: dict[str, Any]) -> bool:
        """Validate user claims with content validation."""
        # Check required fields
        required_fields = ["name", "preferred_username"]
        if not all(field in user_claims for field in required_fields):
            logger.warning("Missing required user claim fields")
            return False

        # Validate name format
        name = user_claims.get("name", "")
        if not name or len(name) > 100:  # Reasonable length limit
            logger.warning("Invalid name format in user claims")
            return False

        # Validate username format (email or domain\username)
        username = user_claims.get("preferred_username", "")
        if not username:
            logger.warning("Missing username in user claims")
            return False

        # Check for valid email format
        if "@" in username:
            email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
            if not re.match(email_pattern, username):
                logger.warning("Invalid email format in user claims")
                return False
        # Check for valid domain\username format
        elif "\\" in username:
            domain_user = username.split("\\")
            if len(domain_user) != 2 or not all(domain_user):
                logger.warning("Invalid domain\\username format in user claims")
                return False

        # Validate other optional fields if present
        if "email" in user_claims:
            email = user_claims["email"]
            if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
                logger.warning("Invalid email format in user claims")
                return False

        if "oid" in user_claims:
            oid = user_claims["oid"]
            if not re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", oid):
                logger.warning("Invalid object ID format in user claims")
                return False

        return True

    def get_user_info(self, access_token: str) -> dict[str, Any]:
        """Get user information from Microsoft Graph API."""
        try:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }
            response = requests.get(
                "https://graph.microsoft.com/v1.0/me",
                headers=headers,
                timeout=Config.HTTP_TIMEOUT,
            )
            response.raise_for_status()
            user_info = response.json()

            # Log the received user info for debugging
            logger.debug("Received user info from Microsoft Graph API: %s", user_info)

            # Map Microsoft Graph API fields to our expected format
            mapped_info = {
                "name": user_info.get("displayName"),
                "preferred_username": user_info.get("userPrincipalName"),
                "email": user_info.get("mail"),
                "oid": user_info.get("id"),
            }

            # Validate the mapped user info
            if not self.validate_user(mapped_info):
                logger.error("Invalid user info after mapping: %s", mapped_info)
                return None

            return mapped_info

        except requests.exceptions.RequestException as e:
            logger.error("Error fetching user info from Microsoft Graph API: %s", e)
            return None
        except ValueError as e:
            logger.error("Unexpected error while fetching user info: %s", e)
            return None

    def get_user_claims(self, access_token: str) -> dict[str, Any]:
        """Get user claims from the access token."""
        try:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }
            response = requests.get(
                "https://graph.microsoft.com/v1.0/me",
                headers=headers,
                timeout=Config.HTTP_TIMEOUT,
            )
            response.raise_for_status()
            claims = response.json()

            # Map Microsoft Graph API fields to our expected format
            mapped_claims = {
                "name": claims.get("displayName"),
                "preferred_username": claims.get("userPrincipalName"),
                "email": claims.get("mail"),
                "oid": claims.get("id"),
            }

            # Validate the mapped claims
            if not self.validate_user(mapped_claims):
                logger.error("Invalid claims after mapping: %s", mapped_claims)
                return None

            return mapped_claims

        except requests.exceptions.RequestException as e:
            logger.error("Error fetching user claims from Microsoft Graph API: %s", e)
            return None
        except ValueError as e:
            logger.error("Unexpected error while fetching user claims: %s", e)
            return None
