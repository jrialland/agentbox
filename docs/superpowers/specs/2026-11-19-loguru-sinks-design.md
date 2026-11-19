# Loguru sink configuration — design

## Goal
Centralize loguru configuration so the app has predictable, low-volume logs
in development and production, with file rotation and stdlib interception.

## Decisions
- **Formats:** human-readable text to stderr and text to a rotating file
  (JSON deferred; easy to add later via a settings flag).
- **Interception:** route `uvicorn`, `uvicorn.error`, `starlette`, `sqlalchemy`
  and `asyncio` through loguru; leave `uvicorn.access` outside loguru.
- **Rotation:** 10 MB, retention 14 days, zip compression (env-overridable).
- **Secret safety:** `diagnose=False` on every sink (never dumps variables).
- **stdout safety:** ACP uses stdout for its protocol, so sinks are
  **stderr + file only** — never stdout.

## Behaviour
`agentbox_api.logging.configure_logging(settings)`:
1. `logger.remove()` (idempotent).
2. Add stderr sink: colorized text, `settings.log_level`, `diagnose=False`.
3. Add `settings.log_dir/agentbox.log`: text, rotation/retention/compression,
   `enqueue=True`, `diagnose=False`.
4. If `settings.log_intercept`: install an `InterceptHandler` on the stdlib
   root (level DEBUG, so per-logger levels pass through) and on the named
   loggers; set `propagate=False`; keep `uvicorn.access` separate.

Called from the FastAPI lifespan (`app.py`) and from the ACP entrypoint
(`acp_server._serve`). The A2A endpoints are served by the same app, so they
are covered by the lifespan.

## Settings (env-driven)
`LOG_LEVEL=INFO`, `LOG_DIR=./logs`, `LOG_ROTATION=10 MB`,
`LOG_RETENTION=14 days`, `LOG_COMPRESSION=zip`, `LOG_INTERCEPT=true`.
`logs/` is gitignored.

## Testing
`test_configure_logging_writes_file_and_intercepts` configures a temp log dir,
asserts the file sink receives a record, and that `InterceptHandler` forwards a
stdlib record into loguru.
