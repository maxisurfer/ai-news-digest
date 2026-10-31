#!/usr/bin/env python3
"""Local check: render full and short digest from fake Stage 2 JSON (no Gemini)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.news.renderer import render_digests  # noqa: E402


def main() -> None:
    topics = [
        {"id": "world", "name": "World news"},
        {"id": "sports", "name": "Sports"},
        {"id": "ai_tech", "name": "AI and technology"},
        {"id": "cars", "name": "Cars"},
    ]
    news_items = {
        "WORLD-1": {
            "title": "Feed title world",
            "description": "Desc.",
            "link": "https://example.com/w1",
            "source": "BBC",
        },
        "SPORTS-1": {
            "title": "Feed title sports",
            "description": "Desc.",
            "link": "https://example.com/s1",
            "source": "ESPN",
        },
    }
    selected_ids = ["WORLD-1", "SPORTS-1"]
    stage2_data = {
        "top_of_day": ["Line one.", "Line two.", "Line three."],
        "items": [
            {
                "id": "WORLD-1",
                "headline": "Headline world",
                "summary": "One friendly sentence about world news.",
            },
            {
                "id": "SPORTS-1",
                "headline": "Headline sports",
                "summary": "One friendly sentence about sports.",
            },
        ],
    }
    out = render_digests(stage2_data, news_items, selected_ids, topics)
    print("=== FULL ===")
    print(out.full_markdown)
    print("\n=== SHORT ===")
    print(out.short_markdown)


if __name__ == "__main__":
    main()
