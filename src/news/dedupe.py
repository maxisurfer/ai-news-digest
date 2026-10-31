"""
De-duplicate news items before LLM selection.
"""
import re
from typing import Dict, List
from ..logger import setup_logger


logger = setup_logger(__name__)

_SOURCE_PRIORITY = {
    "google_news": 0,
    "youtube": 1,
    "reddit": 2,
}


def _normalize_title(title: str) -> str:
    t = title.lower().strip()
    t = re.sub(r"\s*[-|]\s*[^-|]+$", "", t)
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _item_key(item: Dict[str, str]) -> str:
    link = (item.get("link") or "").strip().lower()
    if link:
        return f"url:{link}"
    title = _normalize_title(item.get("title", ""))
    return f"title:{title}"


def _is_better(new_item: Dict[str, str], existing: Dict[str, str]) -> bool:
    new_rank = _SOURCE_PRIORITY.get(new_item.get("source_type", ""), 99)
    old_rank = _SOURCE_PRIORITY.get(existing.get("source_type", ""), 99)
    if new_rank != old_rank:
        return new_rank < old_rank
    return bool(new_item.get("published", "")) >= bool(existing.get("published", ""))


def dedupe_by_topic(
    news_by_topic: Dict[str, List[Dict[str, str]]],
) -> Dict[str, List[Dict[str, str]]]:
    """Merge duplicate stories within each topic."""
    result: Dict[str, List[Dict[str, str]]] = {}
    total_before = 0
    total_after = 0

    for topic_id, items in news_by_topic.items():
        total_before += len(items)
        seen: Dict[str, Dict[str, str]] = {}
        order: List[str] = []

        for item in items:
            key = _item_key(item)
            if key not in seen:
                seen[key] = item
                order.append(key)
            elif _is_better(item, seen[key]):
                seen[key] = item

        deduped = [seen[k] for k in order]
        total_after += len(deduped)
        result[topic_id] = deduped

    logger.info(
        f"De-duplication: {total_before} items -> {total_after} after de-duplication"
    )
    return result
