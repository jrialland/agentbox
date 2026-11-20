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
