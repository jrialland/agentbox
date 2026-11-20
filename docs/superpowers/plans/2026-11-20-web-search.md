# Web Search + URL Fetch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add opt-in `web_search` and `fetch_url` native tools backed by keyless `ddgs` and SearXNG providers, with Trafilatura Markdown extraction.

**Architecture:** A new `agentbox_harness.tools.web` module owns the provider abstraction, fetch policy, and tool functions. The API maps `Settings` into a harness `WebToolConfig`, registers both tools with the `read` flag, and passes the config through `prepare_agent`. The web UI only adds both names to the existing agent tool picker.

**Tech Stack:** Python 3.12, pydantic-ai tools, `ddgs`, `httpx`, `trafilatura`, FastAPI settings, React/Mantine, Vitest.

## Global Constraints

- Tool names are exactly `web_search` and `fetch_url`; both use `required_flags=("read",)` and are selectable per agent.
- Keyless search only: providers are `auto`, `ddgs`, and `searxng`.
- `fetch_url` allows `https://` for any host; `http://` only for `localhost`, `127.0.0.1`, `::1`; all other schemes are rejected.
- No database migration. Configuration is environment-based; no settings UI.
- HTML is converted with Trafilatura; PDFs and other binaries are unsupported.
- Tool failures are returned as strings (`Search failed: ...`, `Fetch failed: ...`), never `ModelRetry`.
- Defaults: `web_search_provider=auto`, `web_search_timeout=10.0`, `web_search_max_results=5`, `web_search_region=us-en`, `web_search_safesearch=moderate`, `web_search_ddgs_backend=auto`, `searxng_url=None`, `web_fetch_timeout=15.0`, `web_fetch_max_chars=40000`, `web_fetch_max_bytes=2000000`, `web_fetch_user_agent=agentbox/0.1`.
- Run `ruff`/`ty` and the relevant tests before each commit.
- Do not edit generated API artifacts; this feature adds no HTTP routes or schemas.

---

### Task 1: Search providers and `web_search`

**Files:**
- Modify: `packages/agentbox-harness/pyproject.toml`
- Create: `packages/agentbox-harness/src/agentbox_harness/tools/web.py`
- Create: `packages/agentbox-harness/tests/test_web_search.py`
- Modify: `uv.lock` (via `uv add`)

**Interfaces:**
- Produces: `WebToolConfig`, `SearchResult`, `SearchProvider`, `DdgsSearchProvider`, `SearxngSearchProvider`, `WebToolbox`.
- `WebToolbox.__init__(config: WebToolConfig | None = None, *, providers: list[SearchProvider] | None = None, transport: httpx.AsyncBaseTransport | None = None)`.
- `WebToolbox.web_search(query: str, max_results: int | None = None) -> str`.

- [ ] **Step 1: Add dependencies**

```bash
uv add --package agentbox-harness "ddgs>=9.0" "httpx>=0.27" "trafilatura>=2.0"
```

- [ ] **Step 2: Write the failing search tests**

Create `packages/agentbox-harness/tests/test_web_search.py`:

```python
import os

import httpx
import pytest

from agentbox_harness.tools.web import (
    DdgsSearchProvider,
    SearxngSearchProvider,
    SearchResult,
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
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest packages/agentbox-harness/tests/test_web_search.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'agentbox_harness.tools.web'`.

- [ ] **Step 4: Implement the search module**

Create `packages/agentbox-harness/src/agentbox_harness/tools/web.py`:

```python
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
```

- [ ] **Step 5: Run the search tests**

Run: `uv run pytest packages/agentbox-harness/tests/test_web_search.py -q`

Expected: PASS (8 passed, 1 skipped; the live test is skipped).

- [ ] **Step 6: Run lint, types, and commit**

```bash
uv run ruff check --fix packages/agentbox-harness
uv run ty check packages/agentbox-harness
git add packages/agentbox-harness/pyproject.toml uv.lock packages/agentbox-harness/src/agentbox_harness/tools/web.py packages/agentbox-harness/tests/test_web_search.py
git commit -m "feat(harness): keyless web search providers"
```

---

### Task 2: `fetch_url`, llms.txt, and extraction

**Files:**
- Modify: `packages/agentbox-harness/src/agentbox_harness/tools/web.py`
- Create: `packages/agentbox-harness/tests/test_web_fetch.py`

**Interfaces:**
- Consumes: `WebToolConfig`, `WebToolbox`.
- Produces: `WebToolbox.fetch_url(url: str) -> str`.

- [ ] **Step 1: Write the failing fetch tests**

Create `packages/agentbox-harness/tests/test_web_fetch.py`:

```python
import httpx

from agentbox_harness.tools.web import WebToolbox, WebToolConfig


def _box(handler, config: WebToolConfig | None = None) -> WebToolbox:
    return WebToolbox(
        config or WebToolConfig(),
        providers=[],
        transport=httpx.MockTransport(handler),
    )


async def test_fetch_html_to_markdown():
    def handler(request):
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text="<html><body><article><h1>Hi</h1><p>Hello world</p></article></body></html>",
        )

    text = await _box(handler).fetch_url("https://example.com/page")
    assert text.startswith("Source: https://example.com/page\n\n")
    assert "# Hi" in text
    assert "Hello world" in text


async def test_fetch_allows_http_for_localhost():
    def handler(request):
        return httpx.Response(
            200, headers={"content-type": "text/plain"}, text="local"
        )

    text = await _box(handler).fetch_url("http://localhost:8000/x")
    assert text == "Source: http://localhost:8000/x\n\nlocal"


async def test_fetch_rejects_http_for_public_host():
    text = await _box(lambda request: httpx.Response(200)).fetch_url(
        "http://example.com"
    )
    assert text == (
        "Fetch failed: http:// is only allowed for localhost; use https://."
    )


async def test_fetch_rejects_other_schemes():
    text = await _box(lambda request: httpx.Response(200)).fetch_url(
        "file:///etc/passwd"
    )
    assert text == (
        "Fetch failed: only https:// URLs are supported "
        "(http:// is allowed for localhost)."
    )


async def test_fetch_revalidates_redirects():
    def handler(request):
        if request.url.path == "/start":
            return httpx.Response(
                302, headers={"location": "http://evil.example/"}
            )
        return httpx.Response(200, text="should not be reached")

    text = await _box(handler).fetch_url("https://example.com/start")
    assert text == (
        "Fetch failed: http:// is only allowed for localhost; use https://."
    )


async def test_fetch_prefers_llms_txt_for_bare_domain():
    def handler(request):
        if request.url.path == "/llms.txt":
            return httpx.Response(
                200, headers={"content-type": "text/plain"}, text="# Docs"
            )
        return httpx.Response(
            200, headers={"content-type": "text/html"}, text="<p>Page</p>"
        )

    text = await _box(handler).fetch_url("https://example.com")
    assert text == "Source: https://example.com/llms.txt (llms.txt)\n\n# Docs"


async def test_fetch_falls_back_when_llms_txt_missing():
    def handler(request):
        if request.url.path == "/llms.txt":
            return httpx.Response(404)
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<html><body><p>Page content</p></body></html>",
        )

    text = await _box(handler).fetch_url("https://example.com")
    assert text.startswith("Source: https://example.com\n\n")
    assert "Page content" in text


async def test_fetch_plain_text_and_json():
    def text_handler(request):
        return httpx.Response(
            200, headers={"content-type": "text/plain"}, text="plain body"
        )

    assert await _box(text_handler).fetch_url("https://example.com/a.txt") == (
        "Source: https://example.com/a.txt\n\nplain body"
    )

    def json_handler(request):
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            text='{"a": 1}',
        )

    assert await _box(json_handler).fetch_url("https://example.com/a.json") == (
        'Source: https://example.com/a.json\n\n{"a": 1}'
    )


async def test_fetch_rejects_binary():
    def handler(request):
        return httpx.Response(
            200,
            headers={"content-type": "application/pdf"},
            content=b"%PDF-1.7",
        )

    text = await _box(handler).fetch_url("https://example.com/a.pdf")
    assert text == "Fetch failed: unsupported content type application/pdf"


async def test_fetch_rejects_oversized_body():
    def handler(request):
        return httpx.Response(
            200, headers={"content-type": "text/plain"}, text="x" * 20
        )

    text = await _box(handler, WebToolConfig(fetch_max_bytes=10)).fetch_url(
        "https://example.com/big"
    )
    assert text == "Fetch failed: response exceeds 10 bytes"


async def test_fetch_truncates_output():
    def handler(request):
        return httpx.Response(
            200, headers={"content-type": "text/plain"}, text="a" * 50
        )

    text = await _box(handler, WebToolConfig(fetch_max_chars=20)).fetch_url(
        "https://example.com/long"
    )
    assert "[truncated at 20 characters]" in text


async def test_fetch_reports_http_error():
    def handler(request):
        return httpx.Response(404, text="missing")

    text = await _box(handler).fetch_url("https://example.com/missing")
    assert text == "Fetch failed: HTTP 404 for https://example.com/missing"


async def test_fetch_html_without_content_type():
    def handler(request):
        return httpx.Response(
            200, content=b"<html><body><p>No type</p></body></html>"
        )

    text = await _box(handler).fetch_url("https://example.com/no-type")
    assert "No type" in text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest packages/agentbox-harness/tests/test_web_fetch.py -q`

Expected: FAIL with `AttributeError: 'WebToolbox' object has no attribute 'fetch_url'`.

- [ ] **Step 3: Add fetch imports and helpers**

At the top of `web.py`, add:

```python
import re
from urllib.parse import urljoin, urlsplit, urlunsplit

import trafilatura
```

Add these module-level constants and helpers after `_clean`:

```python
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
        markdown = trafilatura.html2txt(text, url=url)
    return (markdown or "").strip()
```

- [ ] **Step 4: Add fetch methods to `WebToolbox`**

Insert these methods after `_format_results` (keep the existing indentation at class level):

```python
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
```

- [ ] **Step 5: Run the fetch tests**

Run: `uv run pytest packages/agentbox-harness/tests/test_web_fetch.py -q`

Expected: PASS (13 tests).

- [ ] **Step 6: Run the whole harness suite and commit**

```bash
uv run ruff check --fix packages/agentbox-harness
uv run ty check packages/agentbox-harness
uv run pytest packages/agentbox-harness -q
git add packages/agentbox-harness/src/agentbox_harness/tools/web.py packages/agentbox-harness/tests/test_web_fetch.py
git commit -m "feat(harness): fetch_url with llms.txt and Trafilatura"
```

---

### Task 3: Settings and API wiring

**Files:**
- Modify: `packages/agentbox-api/src/agentbox_api/config.py`
- Modify: `packages/agentbox-api/src/agentbox_api/runtime.py`
- Modify: `packages/agentbox-api/src/agentbox_api/skills.py`
- Modify: `packages/agentbox-api/src/agentbox_api/routers/sessions.py`
- Modify: `packages/agentbox-api/src/agentbox_api/acp_server.py`
- Modify: `packages/agentbox-api/src/agentbox_api/a2a_executor.py`
- Modify: `packages/agentbox-api/tests/test_runtime_tools.py`
- Create: `packages/agentbox-api/tests/test_web_wiring.py`

**Interfaces:**
- Consumes: `WebToolbox`, `WebToolConfig`.
- Produces: `web_config_from_settings(settings) -> WebToolConfig`; `build_registry(..., web_config=None)`; `prepare_agent(..., web_config=None)`.

- [ ] **Step 1: Write the failing wiring tests**

Update `packages/agentbox-api/tests/test_runtime_tools.py` so the read set includes the web tools:

```python
from agentbox_api.runtime import build_registry
from agentbox_harness.spec import Mode


def test_registry_exposes_all_tools_with_flags():
    reg = build_registry(".")
    ask = Mode(name="ask", flags={"write": False})
    agent = Mode(name="agent", flags={"write": True})
    names_ask = {t.__name__ for t in reg.select_tools(ask)}  # ty: ignore[missing-attribute]
    names_agent = {t.__name__ for t in reg.select_tools(agent)}  # ty: ignore[missing-attribute]
    read = {
        "read_text_file",
        "read_file",
        "read_media_file",
        "read_multiple_files",
        "list_directory",
        "list_directory_with_sizes",
        "directory_tree",
        "search_files",
        "get_file_info",
        "list_allowed_directories",
        "web_search",
        "fetch_url",
    }
    write = {
        "write_file",
        "append_file",
        "edit_file",
        "create_directory",
        "move_file",
        "copy_file",
        "delete_path",
    }
    assert names_ask == read
    assert names_agent == read | write
```

Create `packages/agentbox-api/tests/test_web_wiring.py`:

```python
from agentbox_api.config import Settings
from agentbox_api.runtime import build_registry, web_config_from_settings
from agentbox_api.skills import prepare_agent
from agentbox_harness.spec import Mode
from agentbox_harness.tools.web import WebToolConfig
from agentbox_models.db import create_engine_and_sessionmaker, init_db
from agentbox_models.tables.core import Agent, Model, Provider


def test_web_config_from_settings():
    settings = Settings(
        jwt_secret="s" * 32,
        web_search_provider="searxng",
        searxng_url="https://searx.example",
        web_search_max_results=7,
        web_fetch_max_chars=1234,
    )
    config = web_config_from_settings(settings)
    assert config == WebToolConfig(
        search_provider="searxng",
        search_max_results=7,
        searxng_url="https://searx.example",
        fetch_max_chars=1234,
    )


def test_web_tools_are_selectable_when_bound():
    reg = build_registry(".")
    ask = Mode(name="ask", flags={"write": False})
    names = {
        tool.__name__  # ty: ignore[missing-attribute]
        for tool in reg.select_tools(ask, names={"web_search", "fetch_url"})
    }
    assert names == {"web_search", "fetch_url"}
    assert reg.select_tools(ask, names=set()) == []


async def test_prepare_agent_exposes_bound_web_tools(tmp_path):
    engine, factory = create_engine_and_sessionmaker("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    try:
        async with factory() as s:
            s.add(Provider(id="prov", name="prov", kind="test"))
            s.add(Model(id="m1", provider_id="prov", name="test-model"))
            s.add(
                Agent(
                    id="ag",
                    name="bot",
                    description="d",
                    instructions="i",
                    model_id="m1",
                    tool_bindings='[{"name": "web_search"}, {"name": "fetch_url"}]',
                )
            )
            await s.commit()
        prepared = await prepare_agent(
            factory,
            "bot",
            str(tmp_path),
            str(tmp_path / "skills"),
            web_config=WebToolConfig(search_provider="ddgs"),
        )
        tools = prepared.registry.select_tools(
            Mode(name="ask", flags={"write": False})
        )
        names = {tool.__name__ for tool in tools}  # ty: ignore[missing-attribute]
        assert {"web_search", "fetch_url"} <= names
    finally:
        await engine.dispose()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest packages/agentbox-api/tests/test_web_wiring.py -q`

Expected: FAIL with `ImportError: cannot import name 'web_config_from_settings'`.

- [ ] **Step 3: Add settings fields**

In `packages/agentbox-api/src/agentbox_api/config.py`, add after `lsp_failure_backoff_seconds`:

```python
    web_search_provider: str = "auto"
    web_search_timeout: float = 10.0
    web_search_max_results: int = 5
    web_search_region: str = "us-en"
    web_search_safesearch: str = "moderate"
    web_search_ddgs_backend: str = "auto"
    searxng_url: str | None = None
    web_fetch_timeout: float = 15.0
    web_fetch_max_chars: int = 40_000
    web_fetch_max_bytes: int = 2_000_000
    web_fetch_user_agent: str = "agentbox/0.1"
```

- [ ] **Step 4: Add the config mapper and register the tools**

In `packages/agentbox-api/src/agentbox_api/runtime.py`, add the import:

```python
from agentbox_harness.tools.web import WebToolbox, WebToolConfig
```

Add before `build_registry`:

```python
def web_config_from_settings(settings) -> WebToolConfig:
    return WebToolConfig(
        search_provider=settings.web_search_provider,
        search_timeout=settings.web_search_timeout,
        search_max_results=settings.web_search_max_results,
        search_region=settings.web_search_region,
        search_safesearch=settings.web_search_safesearch,
        ddgs_backend=settings.web_search_ddgs_backend,
        searxng_url=settings.searxng_url,
        fetch_timeout=settings.web_fetch_timeout,
        fetch_max_chars=settings.web_fetch_max_chars,
        fetch_max_bytes=settings.web_fetch_max_bytes,
        user_agent=settings.web_fetch_user_agent,
    )
```

Change `build_registry`'s signature to:

```python
def build_registry(
    project_root: str,
    extra_read_roots: list[pathlib.Path] | None = None,
    extra_tools: dict[str, Callable] | None = None,
    hooks: list | None = None,
    media_max_dimension: int = 1568,
    media_max_bytes: int = 1_500_000,
    web_config: WebToolConfig | None = None,
) -> ToolRegistry:
```

After `read_tools` is defined, add:

```python
    web = WebToolbox(web_config)
    read_tools.extend(
        [
            ("web_search", web.web_search),
            ("fetch_url", web.fetch_url),
        ]
    )
```

- [ ] **Step 5: Pass `web_config` through `prepare_agent`**

In `packages/agentbox-api/src/agentbox_api/skills.py`, add the import:

```python
from agentbox_harness.tools.web import WebToolConfig
```

Change the `prepare_agent` signature to add:

```python
    web_config: WebToolConfig | None = None,
```

after `media_max_bytes`. Pass it to `build_registry`:

```python
    registry = build_registry(
        project_root,
        extra_read_roots=[s.location.parent for s in skills],
        extra_tools=extra_tools or None,
        hooks=hooks,
        media_max_dimension=media_max_dimension,
        media_max_bytes=media_max_bytes,
        web_config=web_config,
    )
```

- [ ] **Step 6: Pass settings from every `prepare_agent` caller**

In `packages/agentbox-api/src/agentbox_api/routers/sessions.py`, import `web_config_from_settings`
next to the other `runtime` import, then add to the chat `prepare_agent` call:

```python
            web_config=web_config_from_settings(request.app.state.settings),
```

In `packages/agentbox-api/src/agentbox_api/acp_server.py`, import
`web_config_from_settings` from `agentbox_api.runtime`, then add the same
argument to both `prepare_agent` calls in `new_session` and `_restore`:

```python
            web_config=web_config_from_settings(self._settings),
```

In `packages/agentbox-api/src/agentbox_api/a2a_executor.py`, import
`web_config_from_settings` from `agentbox_api.runtime`, then add to its
`prepare_agent` call:

```python
            web_config=web_config_from_settings(self._settings),
```

- [ ] **Step 7: Run the API tests**

Run: `uv run pytest packages/agentbox-api/tests/test_web_wiring.py packages/agentbox-api/tests/test_runtime_tools.py packages/agentbox-api/tests/test_plan_wiring.py packages/agentbox-api/tests/test_plan_tools.py -q`

Expected: PASS.

- [ ] **Step 8: Run lint, types, and commit**

```bash
uv run ruff check --fix packages
uv run ty check packages
git add packages/agentbox-api/src/agentbox_api/config.py packages/agentbox-api/src/agentbox_api/runtime.py packages/agentbox-api/src/agentbox_api/skills.py packages/agentbox-api/src/agentbox_api/routers/sessions.py packages/agentbox-api/src/agentbox_api/acp_server.py packages/agentbox-api/src/agentbox_api/a2a_executor.py packages/agentbox-api/tests/test_runtime_tools.py packages/agentbox-api/tests/test_web_wiring.py
git commit -m "feat(api): wire web tools into agents"
```

---

### Task 4: Frontend tool picker

**Files:**
- Modify: `apps/web/src/pages/AgentsPage.tsx`
- Modify: `apps/web/src/pages/AgentsPage.test.tsx`

- [ ] **Step 1: Update the failing frontend test**

Replace `apps/web/src/pages/AgentsPage.test.tsx` with:

```tsx
import { NATIVE_TOOLS } from "./AgentsPage";

test("lists the full native toolset", () => {
  expect(NATIVE_TOOLS).toContain("delete_path");
  expect(NATIVE_TOOLS).toContain("read_media_file");
  expect(NATIVE_TOOLS).toContain("directory_tree");
  expect(NATIVE_TOOLS).toContain("web_search");
  expect(NATIVE_TOOLS).toContain("fetch_url");
  expect(NATIVE_TOOLS).toHaveLength(18);
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps/web && bun run test -- src/pages/AgentsPage.test.tsx`

Expected: FAIL because `web_search`/`fetch_url` are missing (length 16).

- [ ] **Step 3: Add the tools to the picker**

In `apps/web/src/pages/AgentsPage.tsx`, add two entries to `NATIVE_TOOLS`:

```tsx
  "web_search",
  "fetch_url",
```

- [ ] **Step 4: Run the frontend tests and build**

```bash
cd apps/web
bun run test
bun run build
```

Expected: PASS, build succeeds.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/pages/AgentsPage.tsx apps/web/src/pages/AgentsPage.test.tsx
git commit -m "feat(web): list web tools in the agent picker"
```

---

### Task 5: Roadmap and full verification

**Files:**
- Modify: `docs/ROADMAP.md`

- [ ] **Step 1: Update the roadmap**

Remove the `D4` row from the deferred backlog and add to the sub-project history:

```markdown
| 26 | Web search + URL fetch (keyless ddgs/SearXNG) | `specs/2026-11-20-web-search-design.md` | `plans/2026-11-20-web-search.md` |
```

- [ ] **Step 2: Run the full verification**

```bash
uv run ruff check packages
uv run ty check packages
uv run pytest packages/agentbox-models -q
uv run pytest packages/agentbox-harness -q
uv run pytest packages/agentbox-providers -q
uv run pytest packages/agentbox-api -q
cd apps/web && bun run test && bun run build
```

Expected: all checks pass.

- [ ] **Step 3: Commit the roadmap**

```bash
git add docs/ROADMAP.md
git commit -m "docs(roadmap): web search and url fetch complete"
```
