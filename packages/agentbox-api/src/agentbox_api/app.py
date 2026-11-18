from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.authentication import AuthenticationMiddleware

from agentbox_api.auth_backend import JWTAuthenticationBackend
from agentbox_api.config import Settings
from agentbox_api.routers.agents import router as agents_router
from agentbox_api.routers.api_keys import router as api_keys_router
from agentbox_api.routers.auth import router as auth_router
from agentbox_api.routers.projects import router as projects_router
from agentbox_api.routers.providers import router as providers_router
from agentbox_api.routers.roles import router as roles_router
from agentbox_api.routers.sessions import router as sessions_router
from agentbox_api.routers.users import router as users_router
from agentbox_models.db import create_engine_and_sessionmaker


def create_app(settings: Settings, engine=None, session_factory=None) -> FastAPI:
    if engine is None or session_factory is None:
        engine, session_factory = create_engine_and_sessionmaker(settings.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        await engine.dispose()

    app = FastAPI(lifespan=lifespan)
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.settings = settings
    app.add_middleware(
        AuthenticationMiddleware,
        backend=JWTAuthenticationBackend(session_factory, settings),
    )
    app.include_router(auth_router)
    app.include_router(agents_router)
    app.include_router(providers_router)
    app.include_router(projects_router)
    app.include_router(sessions_router)
    app.include_router(users_router)
    app.include_router(roles_router)
    app.include_router(api_keys_router)
    return app
