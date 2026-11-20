# Web Search + URL Fetch - Design

Date: 2026-11-20
Status: Approved (design), spec awaiting review.

## Goal

Give agents two opt-in native tools:

- `web_search` - search the web without an API key or subscription.
- `fetch_url` - retrieve a page and turn it into clean Markdown for the model.

Search is provider-abstracted. v1 ships `ddgs` (keyless metasearch) and a
self-hosted SearXNG provider, selected through configuration. The tools are
read-only and selectable per agent, like the filesystem read tools.

## Research summary

| Option | Keyless | Verdict |
|---|---|---|
| `ddgs` 9.16.1 (MIT) | yes | Default. Metasearch over Bing, Brave, DuckDuckGo, Google, Mojeek, Startpage, Yahoo, Yandex, Wikipedia; returns `title`/`href`/`body`; sync API wrapped with `asyncio.to_thread`; scrape-based and can be rate-limited. |
| SearXNG | yes | Self-hosted JSON search. No vendor key, but the operator must run an instance and enable the JSON format. |
| Brave / Tavily / Google | no | Require an API key or subscription; rejected by the keyless constraint. |
| Wikipedia / MediaWiki | yes | Reliable but Wikipedia-only; not a general web search. |
| Marginalia | mostly | Niche index; not Google-like. |

In the development sandbox, general ddgs backends returned "No results found"
while Wikipedia and `extract()` worked, so live search quality is not verified
there. The `auto` provider order plus SearXNG gives a fallback path.

## Decisions

- **Two tools**: `web_search` and `fetch_url`; both registered with
  `required_flags=("read",)` and selectable per agent.
- **Keyless search only** in v1.
- **Provider abstraction**: `auto` (ddgs, then SearXNG when configured),
  `ddgs`, or `searxng`.
- **Trafilatura** converts HTML to Markdown (not `ddgs.extract`).
- **URL policy**: HTTPS only; HTTP is allowed only for `localhost`,
  `127.0.0.1`, and `::1`; every other scheme is rejected.
- **No database migration**; configuration is environment-based, with no
  settings UI in this iteration.

## Architecture

```text
agentbox-harness/tools/web.py
├── WebToolConfig          # immutable runtime settings
├── SearchResult           # title, url, snippet
├── SearchProvider         # Protocol: async search(query) -> list[SearchResult]
├── DdgsSearchProvider
├── SearxngSearchProvider
└── WebToolbox              # accepts an injected provider + httpx transport for tests
    ├── web_search(query, max_results=None) -> str
    └── fetch_url(url) -> str

agentbox-api/runtime.py
├── web_config_from_settings(Settings) -> WebToolConfig
└── build_registry(..., web_config=None) registers both tools

agentbox-api/skills.py
└── prepare_agent(..., web_config=None) passes it to build_registry

agentbox-api/config.py
└── Settings fields for provider, timeouts, limits, SearXNG URL
```

New dependencies in `agentbox-harness`: `ddgs`, `httpx`, `trafilatura`.

## Configuration

`agentbox_api.config.Settings`:

| Setting | Default | Purpose |
|---|---|---|
| `web_search_provider` | `auto` | `auto`, `ddgs`, or `searxng` |
| `web_search_timeout` | `10.0` | Search request timeout (seconds) |
| `web_search_max_results` | `5` | Default result count |
| `web_search_region` | `us-en` | ddgs region |
| `web_search_safesearch` | `moderate` | ddgs safe-search level |
| `web_search_ddgs_backend` | `auto` | ddgs backend or comma-delimited list |
| `searxng_url` | `None` | Base URL of a SearXNG instance |
| `web_fetch_timeout` | `15.0` | Fetch timeout (seconds) |
| `web_fetch_max_chars` | `40000` | Markdown output cap |
| `web_fetch_max_bytes` | `2000000` | Downloaded body cap |
| `web_fetch_user_agent` | `agentbox/0.1` | Outgoing User-Agent |

`web_config_from_settings` copies these into the harness `WebToolConfig`;
`build_registry` and `prepare_agent` accept an optional config and fall back to
defaults. Chat, ACP, and A2A pass the application settings through.

## `web_search`

Signature: `async def web_search(query: str, max_results: int | None = None) -> str`.

- Empty or whitespace query returns `Search failed: query must not be empty.`
- `max_results=None` uses `web_search_max_results`; an explicit value is
  clamped to 1-10.
- Provider selection:
  - `auto`: try `ddgs`, then `searxng` when `searxng_url` is set. Continue on
    an exception or an empty result list. If every provider raised, report the
    last error; if all returned empty, report no results.
  - `ddgs`: call `DDGS(timeout=...).text(...)` in `asyncio.to_thread`.
  - `searxng`: `GET {searxng_url}/search` with `q` and `format=json`.
- Output is a compact Markdown numbered list:

  ```markdown
  Search results for "pydantic ai" (3):
  1. [Title](https://example.com)
     Snippet text.
  ```

- No results: `No results found for "<query>".`
- Provider/network errors: `Search failed: <message>`; the run continues so the
  model can adapt.

## `fetch_url`

Signature: `async def fetch_url(url: str) -> str`.

### URL policy

- `https://` is allowed for any host.
- `http://` is allowed only when the host is `localhost`, `127.0.0.1`, or
  `::1`.
- `file://`, `ftp://`, and all other schemes are rejected.
- URLs with embedded credentials are rejected.
- Redirects are followed manually, at most 5, revalidating the policy on every
  hop.

### Request limits

- `web_fetch_timeout` (15 s default).
- At most `web_fetch_max_bytes` (2 MB) are downloaded; larger responses return
  a clear error instead of truncated HTML.
- The final Markdown is capped at `web_fetch_max_chars` (40 000) with a
  `[truncated at ...]` note.
- A dedicated User-Agent is sent.

### `llms.txt` preference

When the URL is a bare domain (path empty or `/`, no query, no fragment), try
`<scheme>://<netloc>/llms.txt` first:

- 200 with a text/plain, text/markdown, or non-HTML body: return it with
  `Source: <llms.txt URL> (llms.txt)`.
- Non-200 or HTML-looking body: fall back to the requested URL.

### Content handling

| Content type | Behaviour |
|---|---|
| HTML / XHTML | Trafilatura to Markdown (`include_links`, `include_formatting`, `include_tables`); fall back to `trafilatura.html2txt` if extraction is empty |
| `text/plain`, `text/markdown`, `text/*` | Return decoded text |
| `application/json`, `application/xml` | Return decoded text |
| PDFs and other binaries | `Fetch failed: unsupported content type <type>` |
| Missing content type | Treat HTML-looking bodies as HTML, otherwise text |

Every successful output starts with `Source: <final URL>` (or
`Source: <llms.txt URL> (llms.txt)`) followed by a blank line and the content.
HTML entities are decoded by Trafilatura.

## Error handling

- Tool failures are returned as strings (`Search failed: ...`,
  `Fetch failed: ...`), never raised as `ModelRetry`; network errors are not
  the model's fault and should not burn retries.
- Provider errors are logged at warning/debug level; fetched content is never
  logged.
- Missing `searxng_url` when `web_search_provider=searxng` returns
  `Search failed: searxng_url is not configured.`

## UI

- Add `web_search` and `fetch_url` to `NATIVE_TOOLS` in
  `apps/web/src/pages/AgentsPage.tsx`, so they appear in the existing agent
  tool picker.
- No other UI changes; no settings page.

## Tests

- `packages/agentbox-harness/tests/test_web_tools.py`:
  - fake `SearchProvider` covers formatting, no-results, empty query, clamping,
    and provider failure;
  - `auto` falls back from ddgs to SearXNG, then reports the last error;
  - `fetch_url` policy: HTTPS accepted, HTTP for localhost accepted, HTTP for a
    public host rejected, `file://` rejected, redirects revalidated;
  - `httpx.MockTransport` covers `llms.txt` 200 and 404 fallback, HTML to
    Markdown, plain text, JSON, unsupported binary, oversized body, and output
    truncation.
- `packages/agentbox-api/tests/test_web_wiring.py`:
  - `build_registry` registers both tools with the `read` flag;
  - they are selectable in Ask mode when bound and absent when unbound;
  - `web_config_from_settings` maps fields correctly.
- `apps/web/src/pages/AgentsPage.test.tsx`: the tool list includes both names.
- Optional live test: skipped unless `AGENTBOX_LIVE_WEB=1`; calls real ddgs and
  skips on `DDGSException`/network errors.

## Out of scope

- PDF, image, and other binary extraction.
- JavaScript rendering or browser automation.
- Robots.txt enforcement, caching, rate limiting, and retry/backoff policy.
- Search result pages beyond the first, news/images/video search.
- A settings UI, per-user keys, or vendor search APIs.
- Automatic multi-page browsing or research loops.

## Risks

- `ddgs` scrapes search engines and can be blocked or rate-limited; SearXNG is
  the fallback when configured.
- Some SearXNG deployments disable JSON output; the URL must point at one that
  enables it.
- Trafilatura can miss content on unusual pages; `html2txt` is the fallback.
- HTTPS is allowed for private hosts by decision; this is not an IP-range-based
  SSRF firewall.
