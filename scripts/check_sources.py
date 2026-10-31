#!/usr/bin/env python3
"""Check every RSS source in config.yaml (no Gemini, no secrets)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import Config
from src.news.fetcher import (
    NewsFetcher,
    _google_news_url,
    _reddit_url,
    _youtube_url,
)


def main() -> int:
    config = Config()
    topics = config.digest_topics
    if not topics:
        print("No topics in config.yaml")
        return 1

    fetcher = NewsFetcher()
    failed = 0

    print(f"Checking sources (max age {config.max_age_hours}h, no LLM calls)\n")

    for topic in topics:
        topic_id = topic["id"]
        print(f"=== {topic.get('name', topic_id)} ({topic_id}) ===")

        for phrase in topic.get("google_news") or []:
            url = _google_news_url(phrase)
            label = f"Google News: {phrase}"
            failed += _check_one(fetcher, url, label, topic_id, "google_news")

        for sub in topic.get("reddit") or []:
            url = _reddit_url(sub)
            label = f"Reddit: r/{sub}"
            failed += _check_one(fetcher, url, label, topic_id, "reddit", reddit_sub=sub)

        for ch in topic.get("youtube") or []:
            cid = ch.get("channel_id", "")
            name = ch.get("name", "YouTube")
            if not cid:
                print(f"FAILED YouTube: {name} (missing channel_id)")
                failed += 1
                continue
            url = _youtube_url(cid)
            label = f"YouTube: {name}"
            failed += _check_one(
                fetcher, url, label, topic_id, "youtube", youtube_name=name
            )
        print()

    if failed:
        print(f"Done: {failed} source(s) failed or returned 0 items.")
        return 1
    print("Done: all sources OK.")
    return 0


def _check_one(
    fetcher: NewsFetcher,
    url: str,
    label: str,
    topic_id: str,
    source_type: str,
    reddit_sub=None,
    youtube_name=None,
) -> int:
    from datetime import datetime, timedelta, timezone

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    try:
        content = fetcher._http_get(url)
        items = fetcher._parse_feed(
            content,
            max_items=10,
            cutoff=cutoff,
            topic_id=topic_id,
            source_type=source_type,
            reddit_sub=reddit_sub,
            youtube_name=youtube_name,
        )
        status = "OK" if items else "OK (0 items in 24h)"
        print(f"  {status}  {label}  -> {len(items)} items")
        return 0
    except Exception as e:
        print(f"  FAILED  {label}  -> {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
