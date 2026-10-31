"""
Track recently sent stories so they are not repeated within history_days.
"""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Set, Tuple

from ..logger import setup_logger


logger = setup_logger(__name__)

_DEFAULT_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "sent_history.json"


def _url_hash(url: str) -> str:
    return hashlib.sha256(url.strip().lower().encode()).hexdigest()[:16]


def _title_hash(title: str) -> str:
    normalized = " ".join(title.lower().split())
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def _load_entries(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return list(data.get("entries") or [])
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Could not read history file: {e}")
        return []


def _recent_keys(entries: List[Dict[str, str]], days: int) -> Tuple[Set[str], Set[str]]:
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=days)
    url_keys: Set[str] = set()
    title_keys: Set[str] = set()
    for entry in entries:
        try:
            entry_date = datetime.fromisoformat(entry["date"]).date()
        except (KeyError, ValueError):
            continue
        if entry_date < cutoff:
            continue
        if entry.get("url_hash"):
            url_keys.add(entry["url_hash"])
        if entry.get("title_hash"):
            title_keys.add(entry["title_hash"])
    return url_keys, title_keys


def filter_already_covered(
    news_by_topic: Dict[str, List[Dict[str, str]]],
    history_days: int,
    path: Path = _DEFAULT_PATH,
) -> Tuple[Dict[str, List[Dict[str, str]]], int]:
    """Remove items sent within history_days."""
    entries = _load_entries(path)
    url_keys, title_keys = _recent_keys(entries, history_days)
    skipped = 0
    result: Dict[str, List[Dict[str, str]]] = {}

    for topic_id, items in news_by_topic.items():
        kept = []
        for item in items:
            uh = _url_hash(item.get("link", ""))
            th = _title_hash(item.get("title", ""))
            if uh in url_keys or th in title_keys:
                skipped += 1
                continue
            kept.append(item)
        result[topic_id] = kept

    if skipped:
        logger.info(f"{skipped} items skipped as already covered")
    return result, skipped


def append_sent_items(
    items: List[Dict[str, str]],
    history_days: int,
    path: Path = _DEFAULT_PATH,
) -> None:
    """Record sent items and prune old entries."""
    path.parent.mkdir(parents=True, exist_ok=True)
    entries = _load_entries(path)
    today = datetime.now(timezone.utc).date().isoformat()

    for item in items:
        entries.append(
            {
                "url_hash": _url_hash(item.get("link", "")),
                "title_hash": _title_hash(item.get("title", "")),
                "date": today,
            }
        )

    cutoff = datetime.now(timezone.utc).date() - timedelta(days=history_days)
    pruned = []
    for entry in entries:
        try:
            if datetime.fromisoformat(entry["date"]).date() >= cutoff:
                pruned.append(entry)
        except (KeyError, ValueError):
            continue

    with open(path, "w", encoding="utf-8") as f:
        json.dump({"entries": pruned}, f, indent=2)
        f.write("\n")

    logger.info(f"Sent history updated ({len(pruned)} entries retained)")
