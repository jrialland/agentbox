from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol

import httpx
from ddgs import DDGS
from ddgs.exceptions import DDGSException
from loguru import logger


@dataclass(frozen=True)
class WebToolConfig:
    search_provider: str = "auto"
    search_timeout: float = 10.0
    search_max_results: int = 5
    search_region: str = "us-en"
    search_safesearch: str = "moderate"
    ddgs_backend: str = "auto"
    searxng_url: str | None = None
    fetch_timeout: float = 15.0
    fetch_max_chars: int = 40_000
    fetch_max_bytes: int = 2_000_000
    user_agent: str = "agentbox/0.1"


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str


class SearchProvider(Protocol):
    async def search(self, query: str, max_results: int) -> list[SearchResult]: ...


def _clean(value: object) -> str:
    return " ".join(str(value or "").split())


class DdgsSearchProvider:
    def __init__(self, config: WebToolConfig):
        self._config = config

    def _run_text(self, query: str, max_results: int):
        with DDGS(timeout=int(self._config.search_timeout)) as ddgs:
            return ddgs.text(
                query,
                region=self._config.search_region,
                safesearch=self._config.search_safesearch,
                max_results=max_results,
                backend=self._config.ddgs_backend,
            )

    async def search(self, query: str, max_results: int) -> list[SearchResult]:
        try:
            rows = await asyncio.to_thread(self._run_text, query, max_results)
        except DDGSException as exc:
            raise RuntimeError(str(exc)) from exc
        results: list[SearchResult] = []
        for row in rows or []:
            url = _clean(row.get("href") or row.get("url"))
            if not url:
                continue
            title = _clean(row.get("title")) or url
            snippet = _clean(row.get("body") or row.get("snippet"))
            results.append(SearchResult(title, url, snippet))
        return results[:max_results]


class SearxngSearchProvider:
    def __init__(
        self,
        config: WebToolConfig,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._config = config
        self._transport = transport

    async def search(self, query: str, max_results: int) -> list[SearchResult]:
        if not self._config.searxng_url:
            raise RuntimeError("searxng_url is not configured.")
        url = self._config.searxng_url.rstrip("/") + "/search"
        async with httpx.AsyncClient(
            transport=self._transport,
            timeout=self._config.search_timeout,
            headers={"User-Agent": self._config.user_agent},
        ) as client:
            response = await client.get(url, params={"q": query, "format": "json"})
        response.raise_for_status()
        results: list[SearchResult] = []
        for row in response.json().get("results", [])[:max_results]:
            url_value = _clean(row.get("url"))
            if not url_value:
                continue
            results.append(
                SearchResult(
                    _clean(row.get("title")) or url_value,
                    url_value,
                    _clean(row.get("content") or row.get("snippet")),
                )
            )
        return results


class WebToolbox:
    def __init__(
        self,
        config: WebToolConfig | None = None,
        *,
        providers: list[SearchProvider] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.config = config or WebToolConfig()
        self._transport = transport
        self._config_error: str | None = None
        self._providers = providers if providers is not None else self._build_providers()

    def _build_providers(self) -> list[SearchProvider]:
        name = (self.config.search_provider or "auto").lower()
        ddgs = DdgsSearchProvider(self.config)
        if name == "ddgs":
            return [ddgs]
        if name == "searxng":
            if not self.config.searxng_url:
                self._config_error = "searxng_url is not configured."
                return []
            return [
                SearxngSearchProvider(self.config, transport=self._transport)
            ]
        if name == "auto":
            providers: list[SearchProvider] = [ddgs]
            if self.config.searxng_url:
                providers.append(
                    SearxngSearchProvider(self.config, transport=self._transport)
                )
            return providers
        self._config_error = f"unknown web search provider: {name}"
        return []

    async def web_search(
        self, query: str, max_results: int | None = None
    ) -> str:
        text = (query or "").strip()
        if not text:
            return "Search failed: query must not be empty."
        if self._config_error:
            return f"Search failed: {self._config_error}"
        limit = (
            self.config.search_max_results
            if max_results is None
            else int(max_results)
        )
        limit = max(1, min(10, limit))
        errors: list[str] = []
        for provider in self._providers:
            try:
                results = await provider.search(text, limit)
            except Exception as exc:
                errors.append(str(exc))
                logger.warning("web search provider failed: {}", exc)
                continue
            if results:
                return self._format_results(text, results)
        if errors:
            return f"Search failed: {errors[-1]}"
        return f'No results found for "{text}".'

    @staticmethod
    def _format_results(query: str, results: list[SearchResult]) -> str:
        lines = [f'Search results for "{query}" ({len(results)}):']
        for index, result in enumerate(results, start=1):
            title = result.title.replace("[", "\\[").replace("]", "\\]")
            lines.append(f"{index}. [{title}]({result.url})")
            if result.snippet:
                lines.append(f"   {result.snippet}")
        return "\n".join(lines)
