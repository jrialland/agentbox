"""SEP-1865 MCP App sandbox page.

Serves the outer "proxy" iframe that ``@mcp-ui/client``'s ``<AppRenderer>``
creates.  The proxy posts ``ui/notifications/sandbox-proxy-ready``, waits for
``ui/notifications/sandbox-resource-ready`` (the app HTML), renders it in an
opaque-origin inner iframe (``srcdoc``), and relays JSON-RPC messages between the
host (parent window) and the app (inner iframe).
"""

from __future__ import annotations

import json

from fastapi.responses import HTMLResponse

SANDBOX_HTML = """<!doctype html>
<html>
  <head><meta charset="utf-8" /><title>MCP App Sandbox</title></head>
  <body style="margin:0">
    <script>
      (function () {
        "use strict";
        var PROXY_READY = "ui/notifications/sandbox-proxy-ready";
        var RESOURCE_READY = "ui/notifications/sandbox-resource-ready";
        var inner = null;

        function toParent(msg) {
          window.parent.postMessage(msg, "*");
        }

        function render(html) {
          if (inner) {
            inner.remove();
          }
          inner = document.createElement("iframe");
          inner.setAttribute(
            "sandbox",
            "allow-scripts allow-forms allow-popups allow-modals"
          );
          inner.style.cssText = "width:100%;height:100%;border:0";
          inner.srcdoc = html;
          document.body.appendChild(inner);
        }

        window.addEventListener("message", function (event) {
          var data = event.data;
          if (event.source === window.parent) {
            if (data && data.method === RESOURCE_READY) {
              render((data.params && data.params.html) || "");
            } else if (inner && inner.contentWindow) {
              inner.contentWindow.postMessage(data, "*");
            }
            return;
          }
          if (inner && event.source === inner.contentWindow) {
            toParent(data);
          }
        });

        toParent({ jsonrpc: "2.0", method: PROXY_READY, params: {} });
      })();
    </script>
  </body>
</html>"""

_BASE_DIRECTIVES = (
    "default-src 'none'",
    "script-src 'unsafe-inline'",
    "style-src 'unsafe-inline'",
    "img-src data: https:",
    "font-src data:",
    "frame-src 'self' data: blob:",
)


def csp_header(raw: str | None = None) -> str:
    """Build a Content-Security-Policy header, honouring ``?csp=<json>``."""
    parts = list(_BASE_DIRECTIVES)
    connect: list[str] = []
    resource: list[str] = []
    if raw:
        try:
            csp = json.loads(raw)
        except ValueError:
            csp = {}
        if isinstance(csp, dict):
            connect = [d for d in (csp.get("connectDomains") or []) if isinstance(d, str)]
            resource = [d for d in (csp.get("resourceDomains") or []) if isinstance(d, str)]
    if resource:
        joined = " ".join(resource)
        parts = [
            p
            for p in parts
            if not p.startswith(("img-src", "style-src", "script-src", "font-src"))
        ]
        parts += [
            f"img-src data: {joined}",
            f"style-src 'unsafe-inline' {joined}",
            f"script-src 'unsafe-inline' {joined}",
            f"font-src data: {joined}",
        ]
    connect_directive = " ".join(connect) if connect else "'none'"
    parts.append(f"connect-src {connect_directive}")
    return "; ".join(parts) + ";"


def sandbox_response(csp_param: str | None = None) -> HTMLResponse:
    return HTMLResponse(
        SANDBOX_HTML,
        headers={
            "Content-Security-Policy": csp_header(csp_param),
            "Cache-Control": "no-store",
        },
    )
