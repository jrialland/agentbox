from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from starlette.middleware.authentication import AuthenticationMiddleware

from agentbox_api.a2a_server import A2ADispatcher
from agentbox_api.auth_backend import JWTAuthenticationBackend
from agentbox_api.config import Settings
from agentbox_api.logging import configure_logging
from agentbox_api.media import MediaStore
from agentbox_api.routers.agents import router as agents_router
from agentbox_api.routers.api_keys import router as api_keys_router
from agentbox_api.routers.auth import router as auth_router
from agentbox_api.routers.labels import router as labels_router
from agentbox_api.routers.llms import router as llms_router
from agentbox_api.routers.models import router as models_router
from agentbox_api.routers.permissions import router as permissions_router
from agentbox_api.routers.plugins import router as plugins_router
from agentbox_api.routers.projects import router as projects_router
from agentbox_api.routers.prompts import router as prompts_router
from agentbox_api.routers.providers import router as providers_router
from agentbox_api.routers.roles import router as roles_router
from agentbox_api.routers.sessions import router as sessions_router
from agentbox_api.routers.skills import router as skills_router
from agentbox_api.routers.users import router as users_router
from agentbox_api.runs import RunRegistry
from agentbox_api.sandbox import sandbox_response
from agentbox_harness.lsp.diagnostics import (
    configure_diagnostics,
    get_diagnostics_service,
)
from agentbox_harness.lsp.manager import configure_lsp, get_lsp_manager
from agentbox_harness.tools.terminal import get_job_manager
from agentbox_models.db import create_engine_and_sessionmaker


def create_app(settings: Settings, engine=None, session_factory=None) -> FastAPI:
    if engine is None or session_factory is None:
        engine, session_factory = create_engine_and_sessionmaker(settings.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        import asyncio
        from contextlib import suppress

        from agentbox_api.plugin_hooks import get_plugin_hook_runtime
        from agentbox_api.subagent_sessions import (
            reconcile_running_subagent_sessions,
            shutdown_subagent_sessions,
        )
        from agentbox_harness.tools.mcp_session import get_mcp_session_manager

        configure_logging(settings)
        configure_lsp(settings)
        configure_diagnostics(settings)
        manager = get_mcp_session_manager()
        manager.start_timeout = settings.mcp_start_timeout_seconds

        async def sweep_loop():
            while True:
                await asyncio.sleep(settings.mcp_sweep_interval_seconds)
                await manager.sweep_idle(settings.mcp_idle_ttl_seconds)

        sweep_task = asyncio.create_task(sweep_loop())
        await reconcile_running_subagent_sessions(session_factory)
        logger.info("agentbox api starting")
        try:
            yield
        finally:
            logger.info("agentbox api stopping")
            sweep_task.cancel()
            with suppress(asyncio.CancelledError):
                await sweep_task
            await manager.close_all()
            await get_diagnostics_service().shutdown()
            await get_lsp_manager().shutdown()
            await get_job_manager().shutdown()
            await shutdown_subagent_sessions()
            await get_plugin_hook_runtime().end_all()
            await engine.dispose()

    app = FastAPI(lifespan=lifespan)
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.settings = settings
    app.state.media_store = MediaStore(settings.media_dir)
    app.state.run_registry = RunRegistry()
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
    app.include_router(prompts_router)
    app.include_router(sessions_router)
    app.include_router(users_router)
    app.include_router(roles_router)
    app.include_router(api_keys_router)
    app.include_router(labels_router)
    app.include_router(llms_router)
    app.include_router(skills_router)
    app.include_router(plugins_router)

    @app.get("/sandbox", include_in_schema=False)
    async def sandbox_page(csp: str | None = None):
        return sandbox_response(csp)

    app.mount("/a2a", A2ADispatcher(session_factory, settings, app.state.media_store))

    return app

