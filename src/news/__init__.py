"""
News Module - News fetching, generation, and web search functionality
"""
from .fetcher import NewsFetcher
from .web_search import WebSearchTool, get_search_tool_definition


def __getattr__(name: str):
    if name == "NewsGenerator":
        from .generator import NewsGenerator
        return NewsGenerator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "NewsGenerator",
    "NewsFetcher",
    "WebSearchTool",
    "get_search_tool_definition",
]
