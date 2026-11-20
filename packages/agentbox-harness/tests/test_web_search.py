import os

import httpx
import pytest

from agentbox_harness.tools.web import (
    DdgsSearchProvider,
    SearchResult,
    SearxngSearchProvider,
    WebToolbox,
    WebToolConfig,
)


class FakeProvider:
    def __init__(self, results=None, error=None):
        self.results = results or []
        self.error = error
        self.calls = []

    async def search(self, query, max_results):
        self.calls.append((query, max_results))
        if self.error is not None:
            raise self.error
        return self.results


async def test_web_search_formats_results():
    provider = FakeProvider(
        [SearchResult("Title", "https://example.com", "Snippet")]
    )
    box = WebToolbox(providers=[provider])
    text = await box.web_search("hello")
    assert text == (
        'Search results for "hello" (1):\n'
        "1. [Title](https://example.com)\n"
        "   Snippet"
    )


async def test_web_search_no_results_and_empty_query():
    box = WebToolbox(providers=[FakeProvider([])])
    assert await box.web_search("x") == 'No results found for "x".'
    assert await box.web_search("   ") == "Search failed: query must not be empty."


async def test_web_search_clamps_max_results():
    provider = FakeProvider([SearchResult("T", "https://x", "S")])
    box = WebToolbox(WebToolConfig(search_max_results=3), providers=[provider])
    await box.web_search("q")
    await box.web_search("q", 0)
    await box.web_search("q", 99)
    assert provider.calls == [("q", 3), ("q", 1), ("q", 10)]


async def test_web_search_reports_provider_failure():
    box = WebToolbox(providers=[FakeProvider(error=RuntimeError("boom"))])
    assert await box.web_search("q") == "Search failed: boom"


async def test_web_search_auto_falls_back_and_reports_last_error():
    fallback = FakeProvider([SearchResult("T", "https://x", "S")])
    box = WebToolbox(
        providers=[FakeProvider(error=RuntimeError("ddgs down")), fallback]
    )
    assert "T" in await box.web_search("q")

    box = WebToolbox(
        providers=[
            FakeProvider(error=RuntimeError("one")),
            FakeProvider(error=RuntimeError("two")),
        ]
    )
    assert await box.web_search("q") == "Search failed: two"


async def test_searxng_provider_parses_json():
    def handler(request):
        assert request.url.params["q"] == "hello"
        assert request.url.params["format"] == "json"
        return httpx.Response(
            200,
            json={
                "results": [
                    {"title": "T", "url": "https://x", "content": "C"}
                ]
            },
        )

    provider = SearxngSearchProvider(
        WebToolConfig(searxng_url="https://searx.example"),
        transport=httpx.MockTransport(handler),
    )
    results = await provider.search("hello", 5)
    assert results == [SearchResult("T", "https://x", "C")]


async def test_searxng_requires_url():
    box = WebToolbox(WebToolConfig(search_provider="searxng"))
    assert await box.web_search("q") == "Search failed: searxng_url is not configured."


async def test_ddgs_maps_rows(monkeypatch):
    provider = DdgsSearchProvider(WebToolConfig())
    monkeypatch.setattr(
        provider,
        "_run_text",
        lambda query, max_results: [
            {"title": "T", "href": "https://x", "body": "B"}
        ],
    )
    results = await provider.search("q", 5)
    assert results == [SearchResult("T", "https://x", "B")]


@pytest.mark.skipif(
    os.environ.get("AGENTBOX_LIVE_WEB") != "1",
    reason="set AGENTBOX_LIVE_WEB=1 to run live ddgs search",
)
async def test_live_ddgs_search():
    provider = DdgsSearchProvider(WebToolConfig())
    results = await provider.search("pydantic ai", 3)
    assert results
