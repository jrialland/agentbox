"""HTTP routers that make up the AgentBox REST API.

Each module defines a FastAPI ``APIRouter`` mounted by
:func:`agentbox_api.app.create_app`. Route handlers are the public API surface;
shared dependencies such as permission checks live in :mod:`agentbox_api.deps`.
"""
