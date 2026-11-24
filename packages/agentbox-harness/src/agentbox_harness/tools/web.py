"""Web search and page-fetch tools for the model.

Search tries the configured providers in order. Fetching only allows HTTPS
(HTTP for localhost), rejects embedded credentials, follows a small number of
redirects, and caps response size and extracted text.
"""

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
    """Configuration for web search and fetching, with conservative defaults."""

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
    """One web search hit with a title, URL, and optional snippet."""

    title: str
    url: str
    snippet: str


class SearchProvider(Protocol):
    """Interface implemented by web search backends."""

    async def search(self, query: str, max_results: int) -> list[SearchResult]: ...  # noqa: D102


def _clean(value: object) -> str:
    """Collapse whitespace in a possibly missing value."""
    return " ".join(str(value or "").split())


_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}


def _validate_url(url: str) -> str:
    """Validate that a URL is fetchable under the security policy.

    Only HTTPS is allowed, except plain HTTP for localhost. Embedded
    credentials are rejected.

    Args:
        url: URL to validate.

    Returns:
        The original URL with surrounding whitespace removed.

    Raises:
        ValueError: If the URL is empty, uses a disallowed scheme or host, or
            embeds credentials.
    """
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
    # Plain HTTP is permitted only for loopback hosts, never for the internet.
    if scheme == "http" and host not in _LOCAL_HOSTS:
        raise ValueError("http:// is only allowed for localhost; use https://.")
    if not host:
        raise ValueError("URL must include a host.")
    if parts.username or parts.password:
        raise ValueError("URLs with embedded credentials are not supported.")
    return value


def _content_type(headers: httpx.Headers) -> str:
    """Return a lowercased media type without parameters."""
    return headers.get("content-type", "").split(";", 1)[0].strip().lower()


def _decode(body: bytes, headers: httpx.Headers) -> str:
    """Decode a response body using its declared charset, else UTF-8."""
    match = re.search(
        r"charset=([^\s;]+)", headers.get("content-type", ""), re.IGNORECASE
    )
    encoding = match.group(1).strip("\"'") if match else "utf-8"
    try:
        return body.decode(encoding, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def _looks_html(body: bytes) -> bool:
    """Return whether a body appears to start with HTML."""
    return body.lstrip().startswith(b"<")


def _is_html(content_type: str, body: bytes) -> bool:
    """Return whether a response should be treated as HTML."""
    return content_type in ("text/html", "application/xhtml+xml") or (
        not content_type and _looks_html(body)
    )


def _html_to_markdown(
    body: bytes, headers: httpx.Headers, url: str
) -> str:
    """Convert an HTML body to Markdown, falling back to plain text."""
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
    """Search provider backed by the ``ddgs`` package."""

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
        """Return DuckDuckGo results, raising when the provider errors."""
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
    """Search provider backed by a SearxNG JSON endpoint."""

    def __init__(
        self,
        config: WebToolConfig,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._config = config
        self._transport = transport

    async def search(self, query: str, max_results: int) -> list[SearchResult]:
        """Return results from a SearxNG instance.

        Raises:
            RuntimeError: If no SearxNG URL is configured.
        """
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
    """Search the web and fetch readable page content for the model.

    Fetching only accepts HTTPS (HTTP for localhost), rejects embedded
    credentials, follows a small number of redirects, and caps both response
    bytes and extracted text.
    """

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
        """Search the web and return formatted results.

        Tries the configured providers in order and falls back when one fails.

        Args:
            query: Search query text.
            max_results: Maximum results to return, clamped to 1-10.

        Returns:
            Numbered Markdown links with snippets, or a failure message as
            text.
        """
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
        """Fetch a URL and return readable text for it.

        For a site root, an ``llms.txt`` document is preferred when available.
        HTML is converted to Markdown; other text and JSON/XML content is
        returned as-is.

        Args:
            url: Absolute HTTPS URL (HTTP is allowed only for localhost).

        Returns:
            The source URL and extracted content, or a failure message as text.
        """
        raw = (url or "").strip()
        if not raw:
            return "Fetch failed: URL must not be empty."
        try:
            _validate_url(raw)
        except ValueError as exc:
            return f"Fetch failed: {exc}"
        try:
            # Prefer a site's llms.txt when the URL is a bare site root; fall
            # back to fetching the page itself when there is none.
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
        """Return ``/llms.txt`` content for a site root, or ``None``.

        Only the bare site root is eligible, and the response must be plain
        text that does not look like an HTML error page.
        """
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
        """Fetch a URL, following redirects manually and enforcing the size cap.

        Args:
            url: Initial validated URL.

        Returns:
            Final URL, status code, response headers, and body bytes.

        Raises:
            ValueError: If a redirect target is invalid, the response is too
                large, or redirects exceed the limit.
        """
        async with httpx.AsyncClient(
            transport=self._transport,
            timeout=self.config.fetch_timeout,
            headers={"User-Agent": self.config.user_agent},
        ) as client:
            current = url
            # Follow redirects manually so every hop is re-validated against
            # the URL policy; six iterations allow five redirects plus the
            # final response.
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
                    # Stream and count bytes so an oversized response is
                    # rejected before it is fully held in memory.
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
        """Format a fetched page header and its possibly truncated content."""
        label = f"Source: {final}" + (" (llms.txt)" if llms else "")
        content = (text or "").strip()
        if len(content) > self.config.fetch_max_chars:
            content = content[: self.config.fetch_max_chars].rstrip()
            content += (
                f"\n\n[truncated at {self.config.fetch_max_chars} characters]"
            )
        return f"{label}\n\n{content}"
