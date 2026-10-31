"""
Build digest Markdown from Stage 2 JSON and fetched items (links from feeds only).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

FORK_URL = "https://github.com/maxisurfer/ai-news-digest"
FOOTER = f"\n\n---\n\n*Morning digest · [fork on GitHub]({FORK_URL})*"


@dataclass
class DigestOutput:
    full_markdown: str
    short_markdown: str


def digest_date() -> str:
    return datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%Y-%m-%d")


def render_digests(
    stage2_data: Dict[str, Any],
    news_items: Dict[str, Dict[str, str]],
    selected_ids: List[str],
    topics: List[Dict[str, Any]],
) -> DigestOutput:
    """Full digest for email; short headlines+links for Discord."""
    date_str = digest_date()
    title = f"# Morning digest - {date_str}"

    top_lines = stage2_data.get("top_of_day") or []
    if isinstance(top_lines, str):
        top_lines = [top_lines]
    top_lines = [str(x).strip() for x in top_lines if str(x).strip()]

    item_copy = _index_stage2_items(stage2_data.get("items") or [])

    full_parts = [title, "", "## Top of the day", ""]
    for line in top_lines:
        full_parts.append(f"- {line}")
    full_parts.append("")

    short_parts = [title, "", "## Top of the day", ""]
    for line in top_lines:
        short_parts.append(f"- {line}")
    short_parts.append("")

    ids_by_topic = _group_ids_by_topic(selected_ids, topics)

    for topic in topics:
        topic_id = topic["id"]
        topic_name = topic.get("name", topic_id)
        ids = ids_by_topic.get(topic_id, [])
        if not ids:
            continue

        full_parts.extend([f"## {topic_name}", ""])
        short_parts.extend([f"**{topic_name}**", ""])

        for news_id in ids:
            feed = news_items.get(news_id, {})
            copy = item_copy.get(news_id, {})
            headline = (copy.get("headline") or feed.get("title") or "News item").strip()
            summary = (copy.get("summary") or feed.get("description") or "").strip()
            link = feed.get("link", "")
            source = feed.get("source", "Source")

            full_parts.append(f"### {headline}")
            if summary:
                full_parts.append(summary)
            if link:
                full_parts.append(f"Source: [{source}]({link})")
            full_parts.append("")

            if link:
                short_parts.append(f"- [{headline}]({link})")
            else:
                short_parts.append(f"- {headline}")

        short_parts.append("")

    full_md = "\n".join(full_parts).strip() + FOOTER
    short_md = "\n".join(short_parts).strip() + FOOTER
    return DigestOutput(full_markdown=full_md, short_markdown=short_md)


def _index_stage2_items(items: List[Any]) -> Dict[str, Dict[str, str]]:
    out: Dict[str, Dict[str, str]] = {}
    for entry in items:
        if not isinstance(entry, dict):
            continue
        news_id = entry.get("id")
        if not news_id:
            continue
        out[str(news_id)] = {
            "headline": str(entry.get("headline", "")),
            "summary": str(entry.get("summary", "")),
        }
    return out


def _group_ids_by_topic(
    selected_ids: List[str],
    topics: List[Dict[str, Any]],
) -> Dict[str, List[str]]:
    topic_order = [t["id"] for t in topics]
    buckets: Dict[str, List[str]] = {tid: [] for tid in topic_order}
    for news_id in selected_ids:
        for tid in topic_order:
            if news_id.startswith(f"{tid.upper()}-"):
                buckets[tid].append(news_id)
                break
    return buckets
