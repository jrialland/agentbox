from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
import trafilatura
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


_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}


def _validate_url(url: str) -> str:
    value = (url or "").strip()
    if not value:
        raise ValueError("URL must not be empty.")
    parts = urlsplit(value)
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    if scheme not in ("http", "https"):
        raise ValueError(
            "only https:// URLs are supported (http:// is allowed for localhost)."
        )
    if scheme == "http" and host not in _LOCAL_HOSTS:
        raise ValueError("http:// is only allowed for localhost; use https://.")
    if not host:
        raise ValueError("URL must include a host.")
    if parts.username or parts.password:
        raise ValueError("URLs with embedded credentials are not supported.")
    return value


def _content_type(headers: httpx.Headers) -> str:
    return headers.get("content-type", "").split(";", 1)[0].strip().lower()


def _decode(body: bytes, headers: httpx.Headers) -> str:
    match = re.search(
        r"charset=([^\s;]+)", headers.get("content-type", ""), re.IGNORECASE
    )
    encoding = match.group(1).strip("\"'") if match else "utf-8"
    try:
        return body.decode(encoding, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def _looks_html(body: bytes) -> bool:
    return body.lstrip().startswith(b"<")


def _is_html(content_type: str, body: bytes) -> bool:
    return content_type in ("text/html", "application/xhtml+xml") or (
        not content_type and _looks_html(body)
    )


def _html_to_markdown(
    body: bytes, headers: httpx.Headers, url: str
) -> str:
    text = _decode(body, headers)
    markdown = trafilatura.extract(
        text,
        url=url,
        output_format="markdown",
        include_links=True,
        include_formatting=True,
        include_tables=True,
    )
    if not markdown:
        markdown = trafilatura.html2txt(text)
    return (markdown or "").strip()


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

    async def fetch_url(self, url: str) -> str:
        raw = (url or "").strip()
        if not raw:
            return "Fetch failed: URL must not be empty."
        try:
            _validate_url(raw)
        except ValueError as exc:
            return f"Fetch failed: {exc}"
        try:
            llms = await self._try_llms(raw)
            if llms is not None:
                final, text = llms
                return self._format(final, text, llms=True)
            final, status, headers, body = await self._fetch(raw)
        except Exception as exc:
            return f"Fetch failed: {exc}"
        if status >= 400:
            return f"Fetch failed: HTTP {status} for {final}"
        content_type = _content_type(headers)
        if _is_html(content_type, body):
            try:
                text = _html_to_markdown(body, headers, final)
            except Exception as exc:
                return f"Fetch failed: {exc}"
            if not text:
                return f"Fetch failed: no readable content found at {final}."
        elif content_type.startswith("text/") or content_type in (
            "application/json",
            "application/xml",
        ):
            text = _decode(body, headers)
        else:
            return (
                "Fetch failed: unsupported content type "
                f"{content_type or 'unknown'}"
            )
        return self._format(final, text)

    async def _try_llms(self, url: str) -> tuple[str, str] | None:
        parts = urlsplit(url)
        if parts.path not in ("", "/") or parts.query or parts.fragment:
            return None
        candidate = urlunsplit((parts.scheme, parts.netloc, "/llms.txt", "", ""))
        try:
            final, status, headers, body = await self._fetch(candidate)
        except Exception:
            return None
        if status != 200:
            return None
        content_type = _content_type(headers)
        if content_type not in (
            "",
            "text/plain",
            "text/markdown",
            "text/x-markdown",
        ):
            return None
        text = _decode(body, headers).strip()
        if not text or text.startswith("<"):
            return None
        return final, text

    async def _fetch(
        self, url: str
    ) -> tuple[str, int, httpx.Headers, bytes]:
        async with httpx.AsyncClient(
            transport=self._transport,
            timeout=self.config.fetch_timeout,
            headers={"User-Agent": self.config.user_agent},
        ) as client:
            current = url
            for _ in range(6):
                _validate_url(current)
                async with client.stream(
                    "GET", current, follow_redirects=False
                ) as response:
                    if response.status_code in _REDIRECT_STATUSES:
                        location = response.headers.get("location")
                        if not location:
                            return (
                                current,
                                response.status_code,
                                response.headers,
                                b"",
                            )
                        current = urljoin(current, location)
                        continue
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > self.config.fetch_max_bytes:
                            raise ValueError(
                                "response exceeds "
                                f"{self.config.fetch_max_bytes} bytes"
                            )
                        chunks.append(chunk)
                    return (
                        current,
                        response.status_code,
                        response.headers,
                        b"".join(chunks),
                    )
        raise ValueError("too many redirects (limit 5)")

    def _format(self, final: str, text: str, *, llms: bool = False) -> str:
        label = f"Source: {final}" + (" (llms.txt)" if llms else "")
        content = (text or "").strip()
        if len(content) > self.config.fetch_max_chars:
            content = content[: self.config.fetch_max_chars].rstrip()
            content += (
                f"\n\n[truncated at {self.config.fetch_max_chars} characters]"
            )
        return f"{label}\n\n{content}"
