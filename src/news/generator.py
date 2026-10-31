"""
AI News Generator using configurable LLM providers
"""
from typing import List, Optional, Dict, Any
import json
import re
from ..logger import setup_logger
from ..config import LANGUAGE_NAMES
from .web_search import WebSearchTool, get_search_tool_definition
from .fetcher import NewsFetcher
from .dedupe import dedupe_by_topic
from .history import filter_already_covered
from .renderer import DigestOutput, render_digests
from ..llm_providers import get_llm_provider


logger = setup_logger(__name__)


class NewsGenerator:
    """Generate AI news digest using configurable LLM providers"""

    def __init__(
        self,
        provider_name: str = "claude",
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        enable_web_search: bool = False
    ):
        """
        Initialize the NewsGenerator.

        Args:
            provider_name: Name of LLM provider to use ('claude' or 'deepseek')
            api_key: API key for the provider. If None, will read from environment
            model: Model name to use. If None, uses provider's default model
            enable_web_search: Whether to enable web search tool for fetching current news

        Raises:
            ValueError: If provider is not recognized or API key is not provided
        """
        # Initialize LLM provider
        self.provider = get_llm_provider(
            provider_name=provider_name,
            api_key=api_key,
            model=model
        )

        self.enable_web_search = enable_web_search
        self.search_tool = WebSearchTool() if enable_web_search else None
        self.news_fetcher = NewsFetcher()
        self.last_sent_items: List[Dict[str, str]] = []
        logger.info(
            f"NewsGenerator initialized with {self.provider.provider_name} "
            f"(model: {self.provider.model}, web_search: {enable_web_search})"
        )

    def _format_news_with_ids(self, news_data: Dict[str, List[Dict[str, str]]]) -> tuple:
        """
        Format news with unique IDs per topic for selection stage.

        Args:
            news_data: Dict mapping topic id -> list of news items

        Returns:
            Tuple of (formatted_text, news_items_dict)
        """
        formatted = "# Recent News Items for Selection\n\n"
        news_items: Dict[str, Dict[str, str]] = {}

        for topic_id, items in news_data.items():
            if not items:
                continue
            prefix = topic_id.upper()
            formatted += f"## {prefix}\n\n"
            for idx, item in enumerate(items, 1):
                news_id = f"{prefix}-{idx}"
                news_items[news_id] = item
                formatted += f"### [{news_id}] {item['title']}\n"
                formatted += f"**Source:** {item['source']}\n"
                if item.get("description"):
                    formatted += f"**Description:** {item['description'][:200]}\n"
                formatted += f"**Link:** {item['link']}\n"
                if item.get("published"):
                    formatted += f"**Published:** {item['published']}\n"
                formatted += "\n"

        return formatted, news_items

    def generate_news_digest_from_sources(
        self,
        max_tokens: int = 8000,
        language: str = "en",
        max_items_per_source: int = 5,
        stage1_template: Optional[str] = None,
        stage2_template: Optional[str] = None
    ) -> DigestOutput:
        """
        Fetch real-time news and generate a digest using two-stage prompt chaining:
        Stage 1: Analyze and select 15-20 high-quality news items
        Stage 2: JSON copy (top_of_day + headlines/summaries); layout in renderer

        Args:
            max_tokens: Maximum tokens in response
            language: Language code for the response
            max_items_per_source: Maximum items to fetch per source
            stage1_template: Optional Stage 1 prompt template (from config)
            stage2_template: Optional Stage 2 prompt template (from config)

        Returns:
            DigestOutput with full_markdown (email) and short_markdown (Discord)

        Raises:
            Exception: If fetching or generation fails
        """
        try:
            from ..config import Config
            app_config = Config()

            logger.info("Fetching news from configured topic sources...")
            news_data = self.news_fetcher.fetch_recent_news(
                topics=app_config.digest_topics,
                max_items_per_source=max_items_per_source,
                max_age_hours=app_config.max_age_hours,
            )

            news_data = dedupe_by_topic(news_data)
            news_data, _ = filter_already_covered(
                news_data, history_days=app_config.history_days
            )

            if not any(news_data.values()):
                error_msg = (
                    "No news items fetched from any source. "
                    "Check config.yaml sources or network connectivity."
                )
                logger.error(error_msg)
                raise Exception(error_msg)

            # Format news with unique IDs for selection
            formatted_news, news_items = self._format_news_with_ids(news_data)
            total_items = len(news_items)

            logger.info(f"Starting two-stage prompt chaining with {total_items} news items")

            # ============================================================
            # STAGE 1: Selection - Analyze and select 15-20 best items
            # ============================================================
            logger.info(f"Stage 1: Analyzing and selecting high-quality news items...")

            # Use provided template or load from config
            if stage1_template is None:
                from ..config import Config
                config = Config()
                stage1_template = config.stage1_prompt_template

            persona = app_config.personalization
            selection_prompt = stage1_template.format(
                formatted_news=formatted_news,
                total_items=total_items,
                about_me=persona.get("about_me", "").strip(),
                language=persona.get("language", "English"),
            )

            messages = [{"role": "user", "content": selection_prompt}]
            selection_response = self.provider.generate(
                messages=messages,
                max_tokens=4000 # give enough tokens for selection
            )

            topic_ids = [t["id"] for t in app_config.digest_topics]
            selected_ids = self._parse_stage1_selection(
                selection_response, news_items, topic_ids
            )
            if not selected_ids:
                logger.warning("Stage 1 parse failed; using newest-items fallback")
                selected_ids = self._fallback_selection(news_data, news_items)

            counts = self._selection_counts(selected_ids, topic_ids)
            logger.info(
                "Stage 1 completed: selected: "
                + ", ".join(f"{tid} {counts.get(tid, 0)}" for tid in topic_ids)
                + f" (total {len(selected_ids)})"
            )
            self.last_sent_items = [news_items[i] for i in selected_ids if i in news_items]
            logger.debug(f"Selected IDs: {selected_ids}")

            # ============================================================
            # STAGE 2: Summarization - Create detailed summaries
            # ============================================================
            logger.info(f"Stage 2: Creating detailed summaries for selected items...")

            # Format selected news for summarization
            formatted_selected = "# Selected news items\n\n"
            for news_id in selected_ids:
                item = news_items[news_id]
                formatted_selected += f"### [{news_id}] {item['title']}\n"
                formatted_selected += f"**Source:** {item['source']}\n"
                if item['description']:
                    formatted_selected += f"**Content:** {item['description']}\n"
                formatted_selected += f"**Link:** {item['link']}\n"
                if item['published']:
                    formatted_selected += f"**Published:** {item['published']}\n"
                formatted_selected += "\n"

            # Use provided template or load from config
            if stage2_template is None:
                from ..config import Config
                config = Config()
                stage2_template = config.stage2_prompt_template

            top_of_day_lines = int(persona.get("top_of_day_lines", 3))
            summarization_prompt = stage2_template.format(
                count=len(selected_ids),
                selected_news=formatted_selected,
                about_me=persona.get("about_me", "").strip(),
                style=persona.get("style", "").strip(),
                language=persona.get("language", "English"),
                top_of_day_lines=top_of_day_lines,
            )

            if language and language.lower() != "en":
                language_name = LANGUAGE_NAMES.get(language.lower(), language.upper())
                summarization_prompt += (
                    f"\n\nIMPORTANT: Please respond entirely in {language_name}."
                )

            messages = [{"role": "user", "content": summarization_prompt}]
            response_text = self.provider.generate(
                messages=messages,
                max_tokens=max_tokens
            )

            stage2_data = self._parse_stage2_response(response_text, selected_ids)
            if not stage2_data:
                logger.warning("Stage 2 JSON parse failed; using feed title/description fallback")
                stage2_data = self._fallback_stage2(
                    selected_ids, news_items, top_of_day_lines
                )

            digest = render_digests(
                stage2_data=stage2_data,
                news_items=news_items,
                selected_ids=selected_ids,
                topics=app_config.digest_topics,
            )

            logger.info("Stage 2 completed: News digest rendered from JSON")
            logger.info(
                f"Two-stage prompt chaining completed: {total_items} items → "
                f"{len(selected_ids)} selected → full {len(digest.full_markdown)} chars"
            )

            return digest

        except Exception as e:
            logger.error(f"Failed to generate news digest from sources: {str(e)}", exc_info=True)
            raise

    def _parse_stage1_selection(
        self,
        response: str,
        news_items: Dict[str, Dict[str, str]],
        topic_ids: List[str],
    ) -> List[str]:
        """Parse per-topic JSON from Stage 1; retry parsing once via stricter extract."""
        for attempt in range(2):
            payload = self._extract_json_object(response if attempt == 0 else response.strip())
            if not payload:
                continue
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict):
                continue

            selected: List[str] = []
            for topic_id in topic_ids:
                raw_ids = data.get(topic_id, [])
                if not isinstance(raw_ids, list):
                    continue
                valid = [i for i in raw_ids if isinstance(i, str) and i in news_items]
                selected.extend(valid[:5])

            if len(selected) > 20:
                selected = selected[:20]
            if selected:
                return selected
        return []

    def _extract_json_object(self, text: str) -> Optional[str]:
        match = re.search(r"\{[\s\S]*\}", text)
        return match.group(0) if match else None

    def _fallback_selection(
        self,
        news_data: Dict[str, List[Dict[str, str]]],
        news_items: Dict[str, Dict[str, str]],
        max_per_topic: int = 4,
    ) -> List[str]:
        """Newest items per topic without padding."""
        selected: List[str] = []
        for topic_id in news_data:
            prefix = f"{topic_id.upper()}-"
            ids = [k for k in news_items if k.startswith(prefix)]
            ids.sort(key=lambda k: news_items[k].get("published", ""), reverse=True)
            selected.extend(ids[:max_per_topic])
        return selected[:20]

    def _selection_counts(self, selected_ids: List[str], topic_ids: List[str]) -> Dict[str, int]:
        counts = {tid: 0 for tid in topic_ids}
        for news_id in selected_ids:
            for tid in topic_ids:
                if news_id.startswith(f"{tid.upper()}-"):
                    counts[tid] += 1
                    break
        return counts

    def _parse_stage2_response(
        self,
        response: str,
        selected_ids: List[str],
    ) -> Optional[Dict[str, Any]]:
        """Parse Stage 2 JSON; retry extraction once."""
        for attempt in range(2):
            payload = self._extract_json_object(response if attempt == 0 else response.strip())
            if not payload:
                continue
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict):
                continue
            top = data.get("top_of_day")
            items = data.get("items")
            if not isinstance(top, list) or not isinstance(items, list):
                continue
            if not items:
                continue
            normalized_items: List[Dict[str, str]] = []
            seen_ids: set = set()
            for entry in items:
                if not isinstance(entry, dict):
                    continue
                news_id = entry.get("id")
                if not isinstance(news_id, str) or news_id not in selected_ids:
                    continue
                if news_id in seen_ids:
                    continue
                seen_ids.add(news_id)
                normalized_items.append(
                    {
                        "id": news_id,
                        "headline": str(entry.get("headline", "")).strip(),
                        "summary": str(entry.get("summary", "")).strip(),
                    }
                )
            if not normalized_items:
                continue
            top_lines = [str(x).strip() for x in top if str(x).strip()]
            return {"top_of_day": top_lines, "items": normalized_items}
        return None

    def _fallback_stage2(
        self,
        selected_ids: List[str],
        news_items: Dict[str, Dict[str, str]],
        top_of_day_lines: int,
    ) -> Dict[str, Any]:
        """Use feed title and first sentence of description when Stage 2 JSON fails."""
        items: List[Dict[str, str]] = []
        for news_id in selected_ids:
            feed = news_items.get(news_id, {})
            title = (feed.get("title") or "News item").strip()
            desc = (feed.get("description") or "").strip()
            summary = self._first_sentence(desc) if desc else title
            items.append(
                {"id": news_id, "headline": title, "summary": summary}
            )

        top_of_day = [items[i]["headline"] for i in range(min(top_of_day_lines, len(items)))]
        while len(top_of_day) < top_of_day_lines:
            top_of_day.append("See the sections below for today's highlights.")

        return {"top_of_day": top_of_day, "items": items}

    @staticmethod
    def _first_sentence(text: str) -> str:
        cleaned = re.sub(r"\s+", " ", text.strip())
        if not cleaned:
            return ""
        match = re.search(r"^(.+?[.!?])(?:\s|$)", cleaned)
        if match:
            return match.group(1).strip()
        return cleaned[:280].strip()
