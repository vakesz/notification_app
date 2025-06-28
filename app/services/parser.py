"""Content parser for blog posts using BeautifulSoup."""

import logging
import re
from datetime import datetime
from typing import List, Optional

from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from app.core.config import Config
from app.db.models import Post

logger = logging.getLogger(__name__)


class ContentParser:
    """Parses HTML content to extract blog posts."""

    def parse_html_content(self, html_content: str) -> List[Post]:
        """Parse HTML content to extract posts."""
        if not html_content or not html_content.strip():
            logger.warning("Empty HTML content provided")
            return []

        posts = []
        soup = BeautifulSoup(html_content, "html.parser")
        post_blocks = soup.find_all("div", class_=lambda c: c and c.startswith("one_block"))

        logger.debug("Found %d post blocks", len(post_blocks))

        for i, block in enumerate(post_blocks):
            try:
                logger.debug("Parsing post block %d", i + 1)
                post = self._parse_post_block(block)
                if post:
                    posts.append(post)
                    logger.debug("Successfully parsed post %d: %s", i + 1, post.title)
                else:
                    logger.warning("Failed to parse post block %d", i + 1)
            except (AttributeError, KeyError, ValueError, TypeError) as e:
                logger.error("Error parsing post block %d: %s", i + 1, e)
                continue

        logger.debug("Successfully parsed %d posts", len(posts))
        return posts

    def _parse_post_block(self, block) -> Optional[Post]:
        """Parse individual post block using BeautifulSoup."""
        try:
            tooltip_div = block.find("div", class_="oldtooltip")
            if not tooltip_div:
                logger.debug("No tooltip div found")
                return None

            post_id = tooltip_div.get("id").lstrip("c")
            title = self._clean_text(tooltip_div.find("h5").get_text())
            content_preview = self._clean_text(tooltip_div.find("span").get_text())

            link_tag = block.find("a", onmouseover=True)
            blog_url = Config.BLOG_API_URL.rstrip("/")
            link = f"{blog_url}/{link_tag['href'].lstrip('/')}" if link_tag and link_tag.has_attr("href") else ""

            is_urgent = bool(block.find(class_="urgent"))

            location, department, category, publish_date = self._extract_metadata(block)

            has_image, image_url = self._extract_image_info(block)
            likes, comments = self._extract_engagement_metrics(block)

            # Convert publish_date string to datetime object
            publish_date_obj = self._parse_date(publish_date)

            return Post(
                id=f"c{post_id}",
                title=title,
                content=content_preview,
                location=location,
                publish_date=publish_date_obj,
                link=link,
                has_image=has_image,
                image_url=image_url,
                is_urgent=is_urgent,
                likes=likes,
                comments=comments,
                department=department,
                category=category,
            )

        except (AttributeError, KeyError, ValueError, TypeError) as e:
            logger.error("Error parsing post block: %s", e)
            return None

    def _extract_metadata(self, block) -> tuple:
        """Extract location, department, category, and publish date."""
        text = block.get_text(separator=" ").strip()

        meta_match = re.search(
            r"(Local|Global)\s*-\s*([^-]+)\s*-\s*([^-]+)\s*-\s*([^(]+)\s*\(([^)]+)\)",
            text,
        )

        if meta_match:
            location = self._clean_text(meta_match.group(2))
            department = self._clean_text(meta_match.group(3))
            category = self._clean_text(meta_match.group(4))
            publish_date = self._clean_text(meta_match.group(5))
            return location, department, category, publish_date

        # Fallback if format changes
        date_match = re.search(r"\(([^)]*\d{4}[^)]*)\)", text)
        publish_date = self._clean_text(date_match.group(1)) if date_match else "Unknown"

        return "Unknown", "", "", publish_date

    def _extract_image_info(self, block) -> tuple:
        """Extract image information."""
        image_link = block.find("a", class_="fancybox image")
        if image_link and image_link.has_attr("href"):
            full_url = f"{Config.BLOG_API_URL.rstrip('/')}/{image_link['href'].lstrip('/')}"
            return True, full_url
        return False, ""

    def _extract_engagement_metrics(self, block) -> tuple:
        """Extract likes and comments count."""
        text = block.get_text(" ").lower()
        likes_match = re.search(r"(\d+)\s*like", text)
        comments_match = re.search(r"(\d+)\s*comment", text)

        likes = int(likes_match.group(1)) if likes_match else 0
        comments = int(comments_match.group(1)) if comments_match else 0

        return likes, comments

    def _clean_text(self, text: str) -> str:
        """Clean text by stripping HTML tags and normalizing whitespace."""
        if not text:
            return ""

        # Remove stray HTML tags (paranoid safety if text comes from .get_text() usually clean)
        text = re.sub(r"<[^>]+>", "", text)

        # Decode HTML entities (can also use html.unescape for more comprehensive decoding)
        text = (
            text.replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&quot;", '"')
            .replace("&#39;", "'")
        )

        return " ".join(text.split()).strip()

    def _parse_date(self, date_str: str) -> datetime:
        """Parse date string to datetime object."""
        if not date_str or date_str == "Unknown":
            return datetime.now()

        # Common date formats found in blog posts
        date_formats = [
            "%B %d, %Y",  # January 1, 2025
            "%b %d, %Y",  # Jan 1, 2025
            "%m/%d/%Y",  # 01/01/2025
            "%d/%m/%Y",  # 01/01/2025
            "%Y-%m-%d",  # 2025-01-01
            "%d.%m.%Y",  # 01.01.2025
        ]

        # Clean the date string
        date_str = date_str.strip()

        for fmt in date_formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        try:
            return date_parser.parse(date_str, fuzzy=True)
        except (ValueError, TypeError):
            pass

        # If no format matches, try to extract year and create a basic date
        year_match = re.search(r"\b(20\d{2})\b", date_str)
        if year_match:
            try:
                year = int(year_match.group(1))
                return datetime(year, 1, 1)
            except ValueError:
                pass

        # Fallback to current datetime
        logger.warning("Could not parse date '%s', using current datetime", date_str)
        return datetime.now()
