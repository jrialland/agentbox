"""A2A per-agent dispatcher, auth, and card building."""

from __future__ import annotations

import contextvars
import json

from a2a import types as a2a_types
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from google.protobuf import json_format
from sqlmodel import select
from starlette.applications import Starlette
from starlette.responses import JSONResponse, PlainTextResponse

from agentbox_models.tables.core import Agent, AgentCard, MediaFile

a2a_user: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "a2a_user", default=None
)


def build_card(stored: dict, agent_name: str, public_url: str):
    card = json_format.ParseDict(stored, a2a_types.AgentCard())
    card.name = stored.get("name") or agent_name
    card.capabilities.streaming = True
    card.supported_interfaces.clear()
    card.supported_interfaces.append(
        a2a_types.AgentInterface(
            protocol_binding="JSONRPC",
            url=f"{public_url}/a2a/{agent_name}",
            protocol_version="1.0",
        )
    )
    return card


class A2ADispatcher:
    def __init__(self, session_factory, settings, media_store):
        self._factory = session_factory
        self._settings = settings
        self._media_store = media_store
        self._apps: dict[str, Starlette] = {}

    async def _agent_with_card(self, name: str):
        async with self._factory() as s:
            agent = (
                await s.execute(select(Agent).where(Agent.name == name))
            ).scalars().first()
            if agent is None:
                return None, None, None
            row = (
                await s.execute(
                    select(AgentCard).where(AgentCard.agent_id == agent.id)
                )
            ).scalars().first()
            media = (
                await s.get(MediaFile, row.file_id)
                if row is not None and row.file_id
                else None
            )
        return agent, row, media

    def _app_for(self, name: str, stored: dict) -> Starlette:
        app = self._apps.get(name)
        if app is not None:
            return app
        from agentbox_api.a2a_executor import AgentboxA2AExecutor

        card = build_card(stored, name, self._settings.a2a_public_url)
        handler = DefaultRequestHandler(
            agent_executor=AgentboxA2AExecutor(name, self._factory, self._settings),
            task_store=InMemoryTaskStore(),
            agent_card=card,
        )
        routes = [*create_agent_card_routes(card), *create_jsonrpc_routes(handler, "/")]
        app = Starlette(routes=routes)
        self._apps[name] = app
        return app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return
        path = scope["path"]
        if path.startswith("/a2a"):
            path = path[len("/a2a") :]
        path = path.lstrip("/")
        name, _, rest = path.partition("/")
        if not name:
            return await PlainTextResponse("Not found", status_code=404)(
                scope, receive, send
            )
        user = scope.get("user")
        auth = scope.get("auth")
        if user is None or not getattr(user, "is_authenticated", False):
            return await JSONResponse({"error": "unauthorized"}, status_code=401)(
                scope, receive, send
            )
        if auth is None or "sessions:create" not in auth.scopes:
            return await JSONResponse({"error": "forbidden"}, status_code=403)(
                scope, receive, send
            )
        _, row, media = await self._agent_with_card(name)
        if row is None or media is None:
            return await PlainTextResponse("Unknown agent", status_code=404)(
                scope, receive, send
            )
        try:
            stored = json.loads(self._media_store.read(media.storage_path))
        except FileNotFoundError:
            return await PlainTextResponse("Unknown agent", status_code=404)(
                scope, receive, send
            )
        app = self._app_for(name, stored)
        token = a2a_user.set(getattr(user, "identity", None))
        try:
            rest_scope = dict(scope)
            rest_scope["path"] = "/" + rest if rest else "/"
            rest_scope["raw_path"] = rest_scope["path"].encode()
            await app(rest_scope, receive, send)
        finally:
            a2a_user.reset(token)
