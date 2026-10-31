"""
Discord notification module
"""
import os
import re
import requests
from typing import Optional, List, Dict, Any
from datetime import datetime
from zoneinfo import ZoneInfo
from ..logger import setup_logger


logger = setup_logger(__name__)

_MAX_EMBED_DESCRIPTION = 4096
_MAX_EMBEDS_PER_MESSAGE = 10
_MAX_CHARS_PER_MESSAGE = 6000


class DiscordNotifier:
    """Send Discord notifications with AI news digest using Webhooks"""

    def __init__(
        self,
        webhook_url: Optional[str] = None,
        username: Optional[str] = None,
        avatar_url: Optional[str] = None,
        timeout: int = 30
    ):
        """
        Initialize DiscordNotifier.

        Args:
            webhook_url: Discord Webhook URL
            username: Optional bot username override
            avatar_url: Optional bot avatar URL
            timeout: Request timeout in seconds
        """
        self.webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL")
        self.username = username or os.getenv("DISCORD_USERNAME", "Morning Digest")
        self.avatar_url = avatar_url or os.getenv("DISCORD_AVATAR_URL")
        self.timeout = timeout

        if not self.webhook_url:
            logger.warning("Discord webhook URL not configured")
        else:
            logger.info(f"DiscordNotifier initialized (username: {self.username})")

    def send(
        self,
        content: str,
        title: Optional[str] = None,
        color: int = 0x0366d6,
        language: str = "en"
    ) -> bool:
        """
        Send Discord notification with news digest using embeds.

        Args:
            content: News digest content
            title: Title for the notification. If None, uses default with current date
            color: Embed color (integer representation of hex color)
            language: Language code to include in title (e.g., 'en', 'zh', 'ja')

        Returns:
            True if message sent successfully, False otherwise
        """
        if not self.webhook_url:
            logger.error("Discord webhook URL is not configured. Skipping Discord send.")
            return False

        try:
            if title is None:
                today = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%Y-%m-%d")
                lang_suffix = f" [{language.upper()}]" if language != "en" else ""
                title = f"Morning digest - {today}{lang_suffix}"

            embeds = self._create_embeds(title, content, color)
            batches = self._batch_embeds_for_limits(embeds)

            success = True
            for idx, embed_batch in enumerate(batches):
                if not self._send_message(embed_batch):
                    success = False
                    logger.error(f"Failed to send Discord message batch {idx + 1}/{len(batches)}")
                    break

            if success:
                logger.info(f"Discord digest sent in {len(batches)} message(s)")

            return success

        except Exception as e:
            logger.error(f"Unexpected error sending Discord message: {str(e)}", exc_info=True)
            return False

    def _send_message(self, embeds: List[Dict[str, Any]]) -> bool:
        """
        Send a Discord message with embeds.

        Args:
            embeds: List of embed objects

        Returns:
            True if successful, False otherwise
        """
        try:
            payload: Dict[str, Any] = {
                "username": self.username,
                "embeds": embeds
            }

            if self.avatar_url:
                payload["avatar_url"] = self.avatar_url

            total_chars = sum(self._embed_char_count(e) for e in embeds)
            logger.info(
                f"Sending Discord message with {len(embeds)} embed(s), ~{total_chars} chars"
            )

            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=self.timeout,
                headers={"Content-Type": "application/json"}
            )

            if response.status_code in [200, 204]:
                return True
            logger.error(f"Discord API returned status {response.status_code}: {response.text}")
            return False

        except requests.exceptions.Timeout:
            logger.error(f"Discord request timed out after {self.timeout} seconds")
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send Discord message: {str(e)}", exc_info=True)
            return False

    def _create_embeds(self, title: str, content: str, color: int) -> List[Dict[str, Any]]:
        """Build embed list from digest content, split on item boundaries."""
        items = self._split_into_items(content)
        descriptions = self._pack_items_into_descriptions(items)

        embeds: List[Dict[str, Any]] = []
        for idx, description in enumerate(descriptions):
            description = description[:_MAX_EMBED_DESCRIPTION]
            if idx == 0:
                embed: Dict[str, Any] = {
                    "title": title[:256],
                    "description": description,
                    "color": color,
                    "timestamp": datetime.now().isoformat(),
                    "footer": {
                        "text": "Morning digest · maxisurfer/ai-news-digest"
                    },
                }
            else:
                embed = {
                    "description": description,
                    "color": color,
                }
            embeds.append(embed)

        return embeds

    def _split_into_items(self, content: str) -> List[str]:
        """Split digest into items (headings / horizontal rules), never mid-link."""
        parts = re.split(r"(?=\n#{2,3} )|\n(?=---\n)", content)
        items = [part.strip() for part in parts if part and part.strip()]
        return items if items else ([content] if content.strip() else [])

    def _pack_items_into_descriptions(self, items: List[str]) -> List[str]:
        """Group items into embed descriptions within per-embed limits."""
        descriptions: List[str] = []
        current_parts: List[str] = []
        current_length = 0

        for item in items:
            separator = 2 if current_parts else 0
            item_length = len(item) + separator

            if len(item) > _MAX_EMBED_DESCRIPTION:
                if current_parts:
                    descriptions.append("\n\n".join(current_parts))
                    current_parts = []
                    current_length = 0
                descriptions.extend(
                    self._split_content(item, _MAX_EMBED_DESCRIPTION)
                )
                continue

            if current_length + item_length > _MAX_EMBED_DESCRIPTION:
                descriptions.append("\n\n".join(current_parts))
                current_parts = [item]
                current_length = len(item)
            else:
                current_parts.append(item)
                current_length += item_length

        if current_parts:
            descriptions.append("\n\n".join(current_parts))

        return descriptions

    def _split_content(self, content: str, max_length: int = _MAX_EMBED_DESCRIPTION) -> List[str]:
        """Split text by lines without breaking markdown links."""
        if len(content) <= max_length:
            return [content]

        sections: List[str] = []
        current_section: List[str] = []
        current_length = 0

        for line in content.split("\n"):
            line_length = len(line) + 1

            if len(line) > max_length:
                if current_section:
                    sections.append("\n".join(current_section))
                    current_section = []
                    current_length = 0
                sections.extend(self._split_long_line(line, max_length))
                continue

            if current_length + line_length > max_length:
                if current_section:
                    sections.append("\n".join(current_section))
                current_section = [line]
                current_length = line_length
            else:
                current_section.append(line)
                current_length += line_length

        if current_section:
            sections.append("\n".join(current_section))

        return sections

    def _split_long_line(self, line: str, max_length: int) -> List[str]:
        """Split an oversized line at safe boundaries (not inside a markdown link)."""
        chunks: List[str] = []
        remaining = line
        while len(remaining) > max_length:
            cut = max_length
            window = remaining[:cut]
            link_start = window.rfind("](")
            if link_start != -1 and ")" not in window[link_start:]:
                cut = link_start
            if cut <= 0:
                cut = max_length
            chunks.append(remaining[:cut])
            remaining = remaining[cut:]
        if remaining:
            chunks.append(remaining)
        return chunks

    def _embed_char_count(self, embed: Dict[str, Any]) -> int:
        """Approximate character count for Discord's per-message embed limit."""
        title = embed.get("title") or ""
        description = embed.get("description") or ""
        footer = (embed.get("footer") or {}).get("text") or ""
        return len(title) + len(description) + len(footer)

    def _batch_embeds_for_limits(
        self, embeds: List[Dict[str, Any]]
    ) -> List[List[Dict[str, Any]]]:
        """Batch embeds respecting count and total character limits per message."""
        batches: List[List[Dict[str, Any]]] = []
        current_batch: List[Dict[str, Any]] = []
        current_total = 0

        for embed in embeds:
            embed_size = self._embed_char_count(embed)
            if embed_size > _MAX_CHARS_PER_MESSAGE:
                logger.warning(
                    "Single Discord embed exceeds message limit; sending in its own batch"
                )

            if current_batch and (
                len(current_batch) >= _MAX_EMBEDS_PER_MESSAGE
                or current_total + embed_size > _MAX_CHARS_PER_MESSAGE
            ):
                batches.append(current_batch)
                current_batch = []
                current_total = 0

            current_batch.append(embed)
            current_total += embed_size

        if current_batch:
            batches.append(current_batch)

        return batches
