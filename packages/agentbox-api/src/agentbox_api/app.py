from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from starlette.middleware.authentication import AuthenticationMiddleware

from agentbox_api.a2a_server import A2ADispatcher
from agentbox_api.auth_backend import JWTAuthenticationBackend
from agentbox_api.config import Settings
from agentbox_api.routers.agents import router as agents_router
from agentbox_api.routers.api_keys import router as api_keys_router
from agentbox_api.routers.auth import router as auth_router
from agentbox_api.routers.models import router as models_router
from agentbox_api.routers.permissions import router as permissions_router
from agentbox_api.routers.projects import router as projects_router
from agentbox_api.routers.providers import router as providers_router
from agentbox_api.routers.roles import router as roles_router
from agentbox_api.routers.sessions import router as sessions_router
from agentbox_api.routers.users import router as users_router
from agentbox_api.sandbox import sandbox_response
from agentbox_models.db import create_engine_and_sessionmaker


def create_app(settings: Settings, engine=None, session_factory=None) -> FastAPI:
    if engine is None or session_factory is None:
        engine, session_factory = create_engine_and_sessionmaker(settings.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("agentbox api starting")
        yield
        logger.info("agentbox api stopping")
        await engine.dispose()

    app = FastAPI(lifespan=lifespan)
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.settings = settings
    app.add_middleware(
        AuthenticationMiddleware,
        backend=JWTAuthenticationBackend(session_factory, settings),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth_router)
    app.include_router(agents_router)
    app.include_router(providers_router)
    app.include_router(models_router)
    app.include_router(permissions_router)
    app.include_router(projects_router)
    app.include_router(sessions_router)
    app.include_router(users_router)
    app.include_router(roles_router)
    app.include_router(api_keys_router)

    @app.get("/sandbox", include_in_schema=False)
    async def sandbox_page(csp: str | None = None):
        return sandbox_response(csp)

    app.mount("/a2a", A2ADispatcher(session_factory, settings))

    return app
