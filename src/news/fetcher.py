"""
News fetcher — topic-based Google News, Reddit, and YouTube RSS feeds.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

import feedparser
import requests

from ..logger import setup_logger


logger = setup_logger(__name__)

_USER_AGENT = "Mozilla/5.0 (compatible; MorningDigestBot/1.0; +https://github.com/maxisurfer/ai-news-digest)"
_REQUEST_TIMEOUT = 10
_REDDIT_PAUSE_SECONDS = 2


def _google_news_url(phrase: str) -> str:
    q = quote_plus(f"{phrase} when:1d")
    return f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


def _reddit_url(subreddit: str) -> str:
    return f"https://www.reddit.com/r/{subreddit}/top/.rss?t=day"


def _youtube_url(channel_id: str) -> str:
    return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


class NewsFetcher:
    """Fetch recent news from config-driven topic sources."""

    def fetch_recent_news(
        self,
        topics: List[Dict[str, Any]],
        max_items_per_source: int = 10,
        max_age_hours: int = 24,
    ) -> Dict[str, List[Dict[str, str]]]:
        """
        Fetch items for each topic from all configured sources.

        Returns:
            Dict mapping topic id -> list of news item dicts.
        """
        if not topics:
            logger.error("No topics configured in config.yaml")
            return {}

        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        result: Dict[str, List[Dict[str, str]]] = {t["id"]: [] for t in topics}
        source_stats: List[str] = []
        reddit_seen = False

        for topic in topics:
            topic_id = topic["id"]
            topic_name = topic.get("name", topic_id)

            for phrase in topic.get("google_news") or []:
                label = f"Google News ({topic_id}): {phrase}"
                items, stat = self._fetch_feed(
                    url=_google_news_url(phrase),
                    label=label,
                    max_items=max_items_per_source,
                    cutoff=cutoff,
                    topic_id=topic_id,
                    source_type="google_news",
                    is_reddit=False,
                )
                result[topic_id].extend(items)
                source_stats.append(stat)

            for sub in topic.get("reddit") or []:
                if reddit_seen:
                    time.sleep(_REDDIT_PAUSE_SECONDS)
                reddit_seen = True
                label = f"Reddit ({topic_id}): r/{sub}"
                items, stat = self._fetch_feed(
                    url=_reddit_url(sub),
                    label=label,
                    max_items=max_items_per_source,
                    cutoff=cutoff,
                    topic_id=topic_id,
                    source_type="reddit",
                    is_reddit=True,
                    reddit_sub=sub,
                )
                result[topic_id].extend(items)
                source_stats.append(stat)

            for ch in topic.get("youtube") or []:
                name = ch.get("name", "YouTube")
                channel_id = ch.get("channel_id", "")
                if not channel_id:
                    continue
                label = f"YouTube ({topic_id}): {name}"
                items, stat = self._fetch_feed(
                    url=_youtube_url(channel_id),
                    label=label,
                    max_items=max_items_per_source,
                    cutoff=cutoff,
                    topic_id=topic_id,
                    source_type="youtube",
                    is_reddit=False,
                    youtube_name=name,
                )
                result[topic_id].extend(items)
                source_stats.append(stat)

            logger.info(
                f"Topic '{topic_name}' ({topic_id}): {len(result[topic_id])} items fetched"
            )

        logger.info("--- Source summary (last 24h) ---")
        for line in source_stats:
            logger.info(line)
        logger.info("--- End source summary ---")

        total = sum(len(v) for v in result.values())
        logger.info(f"Fetch complete: {total} items across {len(topics)} topics")
        return result

    def _fetch_feed(
        self,
        url: str,
        label: str,
        max_items: int,
        cutoff: datetime,
        topic_id: str,
        source_type: str,
        is_reddit: bool,
        reddit_sub: Optional[str] = None,
        youtube_name: Optional[str] = None,
    ) -> tuple[List[Dict[str, str]], str]:
        """Fetch one feed with retry; return items and a one-line stat."""
        last_error = ""
        attempts = 2 if is_reddit else 2
        for attempt in range(attempts):
            try:
                content = self._http_get(url)
                items = self._parse_feed(
                    content,
                    max_items=max_items,
                    cutoff=cutoff,
                    topic_id=topic_id,
                    source_type=source_type,
                    reddit_sub=reddit_sub,
                    youtube_name=youtube_name,
                )
                return items, f"OK {label}: {len(items)} items (last {int((datetime.now(timezone.utc) - cutoff).total_seconds() // 3600)}h)"
            except Exception as e:
                last_error = str(e)
                if attempt < attempts - 1 and (is_reddit or "429" in last_error or "503" in last_error):
                    wait = _REDDIT_PAUSE_SECONDS if is_reddit else 2
                    logger.warning(f"{label}: retry after error ({last_error})")
                    time.sleep(wait)
                    continue
                break

        logger.warning(f"SKIPPED {label}: {last_error}")
        return [], f"SKIPPED {label}: {last_error}"

    def _http_get(self, url: str) -> bytes:
        response = requests.get(
            url,
            headers={"User-Agent": _USER_AGENT},
            timeout=_REQUEST_TIMEOUT,
        )
        if response.status_code == 429:
            raise requests.HTTPError("HTTP 429 Too Many Requests")
        response.raise_for_status()
        return response.content

    def _parse_feed(
        self,
        content: bytes,
        max_items: int,
        cutoff: datetime,
        topic_id: str,
        source_type: str,
        reddit_sub: Optional[str],
        youtube_name: Optional[str],
    ) -> List[Dict[str, str]]:
        parsed = feedparser.parse(content)
        items: List[Dict[str, str]] = []

        for entry in parsed.entries[: max_items * 3]:
            published_dt = self._entry_datetime(entry)
            if not published_dt:
                continue
            if published_dt < cutoff:
                continue

            title = (entry.get("title") or "").strip()
            link = (entry.get("link") or "").strip()
            if not title or not link:
                continue

            if source_type == "youtube" and entry.get("yt_videoid"):
                link = f"https://www.youtube.com/watch?v={entry.yt_videoid}"

            description = self._entry_summary(entry)
            source_name = self._entry_source_name(
                entry, source_type, reddit_sub, youtube_name
            )

            items.append(
                {
                    "title": title,
                    "link": link,
                    "description": description[:200],
                    "published": published_dt.isoformat() if published_dt else "",
                    "source": source_name,
                    "topic_id": topic_id,
                    "source_type": source_type,
                }
            )
            if len(items) >= max_items:
                break

        return items

    def _entry_datetime(self, entry: Any) -> Optional[datetime]:
        for attr in ("published_parsed", "updated_parsed"):
            parsed = entry.get(attr)
            if parsed:
                try:
                    return datetime(*parsed[:6], tzinfo=timezone.utc)
                except (TypeError, ValueError):
                    pass
        return None

    def _entry_summary(self, entry: Any) -> str:
        for key in ("summary", "description", "content"):
            val = entry.get(key)
            if isinstance(val, list) and val:
                val = val[0].get("value", "")
            if val:
                import re

                return re.sub(r"<[^>]+>", "", str(val)).strip()
        return ""

    def _entry_source_name(
        self,
        entry: Any,
        source_type: str,
        reddit_sub: Optional[str],
        youtube_name: Optional[str],
    ) -> str:
        if source_type == "youtube" and youtube_name:
            return youtube_name
        if source_type == "reddit" and reddit_sub:
            return f"r/{reddit_sub}"
        source = entry.get("source")
        if isinstance(source, dict) and source.get("title"):
            return source["title"]
        if hasattr(source, "title"):
            return source.title
        return "Google News"
