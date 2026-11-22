# Protocols

Agentbox exposes the same runtime over several protocols.

## AG-UI

The web UI and HTTP clients stream runs with AG-UI events. See [Streaming](/llms/streaming.md).

## A2A

A2A exposes agents that have a stored agent card.

- Card: `GET /a2a/{agent}/.well-known/agent-card.json`
- JSON-RPC: `POST /a2a/{agent}`

Both routes require a bearer credential with the `sessions:create` scope and an agent with a card. An unauthenticated request returns `401`, a credential without the scope returns `403`, and an unknown agent or missing card returns `404`.

The card's interface URL is built from the server setting `a2a_public_url`; set it to the externally reachable origin when Agentbox runs behind a proxy.

## ACP

ACP is a stdio JSON-RPC protocol for IDEs. It is not an HTTP endpoint. Launch it with the `agentbox-acp` console script or `python -m agentbox_api.acp_server` and speak ACP over stdin/stdout.

## MCP

MCP servers are configured on the agent as remote URL or stdio tool bindings. API clients do not call MCP directly; the running agent does. The session endpoints under `/sessions/{sid}/mcp/...` exist only to relay MCP App requests to the UI.
