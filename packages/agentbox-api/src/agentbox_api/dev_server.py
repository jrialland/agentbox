import asyncio
import os

import uvicorn

from agentbox_api.app import create_app
from agentbox_api.config import Settings
from agentbox_api.dev_seed import seed_admin
from agentbox_models.db import create_engine_and_sessionmaker, init_db


def main() -> None:
    settings = Settings()
    engine, factory = create_engine_and_sessionmaker(settings.database_url)
    asyncio.run(init_db(engine))
    asyncio.run(seed_admin(factory))
    app = create_app(settings, engine=engine, session_factory=factory)
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8000")))


if __name__ == "__main__":
    main()
