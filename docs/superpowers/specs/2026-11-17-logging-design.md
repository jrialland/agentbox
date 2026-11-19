# Backend Logging with Loguru — Design Specification

- **Date:** 2026-11-17
- **Status:** Draft (brainstormed, pending implementation plan)
- **Sub-project:** Backend — adopt `loguru.logger` across `agentbox-api`. Sink/format/file/uvicorn configuration is **deferred**.

## 1. Context and Scope

The initial spec lists the backend stack as "FastAPI, SQLModel, **loguru**, etc." (`initial_spec.md:125`). Today the backend has **no application logging**: only Alembic configures stdlib logging; no router or service emits logs.

This sub-project standardizes on `loguru.logger` and adds meaningful log statements at key events. **Only usage is in scope** — configuring loguru (custom sinks, format, rotating file, intercepting uvicorn/stdlib logging) is deferred, so loguru's default stderr handler is what runs.

### 1.1 What this sub-project encompasses
- Add the `loguru` dependency to `agentbox-api`.
- Import `from loguru import logger` and log key events across the API.
- Tests that capture log output via a temporary loguru sink and assert behavior + no secrets.

### 1.2 Boundaries
- No sink/format/file/rotation/uvicorn interception (deferred).
- Backend (`agentbox-api`) only; `agentbox-harness`/`agentbox-models`/`agentbox-providers` are not converted here.
- Log volume stays low (key events, not per-row chatter).

### 1.3 Dependencies
- `agentbox-api`; new Python dep `loguru`.

## 2. Decisions and Rationale

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Use `from loguru import logger` directly in modules (no wrapper module). | Simplest; the spec names loguru explicitly. |
| D2 | Do **not** configure sinks/format/file/uvicorn now. | User choice: configuration deferred; loguru's default stderr handler applies. |
| D3 | Never log secrets (passwords, raw API keys, JWTs, API keys). | Security; log identifiers only. |
| D4 | Log key lifecycle/error events, not every request. | Low noise; meaningful signal. |

## 3. Logged Events

| Module | Level | Event / fields |
|--------|-------|----------------|
| `app.py` (lifespan) | INFO | `agentbox api starting` / `agentbox api stopping` |
| `routers/auth.py` | INFO / WARNING | login ok (`user=<username>`); login failed (`user=<username>`); registered (`user=<username>`) |
| `routers/projects.py` | INFO | project created / deleted (`project=<id>`) |
| `routers/agents.py` | INFO / ERROR | agent created / deleted (`agent=<name>`); avatar upload/reset failed (`agent=<name>`) |
| `routers/providers.py` | INFO | provider created (`provider=<id>`, `kind`); models refreshed (`provider=<id>`, `count`) |
| `routers/sessions.py` | INFO / ERROR | session created (`session=<id>`); run start (`session`, `mode`); run finished (`session`, `status`); run failed (`session`, error) |
| `routers/api_keys.py` | INFO | api key created / deleted (`key=<id>`) — never the raw key |
| `mcp_relay.py` | ERROR | relay error (`server=<id>`, `uri`/`tool`, error) |

Rule: no `password`, `api_key`, `token`, or raw secret values in any message.

## 4. Testing

- **Capture sink**: in tests, `handler_id = logger.add(messages.append, level="DEBUG")`, exercise the endpoint, `logger.remove(handler_id)` in a `finally`.
- `test_login_logs_success_without_password`: POST `/auth/login` succeeds → captured messages contain `login` and `user=alice`, and none contain the password.
- `test_login_failure_logs_warning`: wrong password → a WARNING-level `login failed` message is captured.
- `test_session_create_logs`: create a session → a `session created` message is captured.
- (Manual) run `uvicorn` and confirm loguru's default handler prints logs to stderr.

## 5. Error Handling

- Logging must never break a request: use plain `logger.info/warning/error` (loguru does not raise on formatting/sink issues by default). No try/except around logging.

## 6. Open Items / Future Work

- Configure loguru: colored console format, optional rotating file (`LOG_FILE`), JSON option.
- Intercept stdlib/`uvicorn` logging into loguru (set `log_config=None`, bridge via an `InterceptHandler`).
- Request-logging middleware (method/path/status/duration).
- Extend loguru usage to the harness/providers packages.

## References

- Initial spec — `docs/initial_spec.md:125` (tech stack includes loguru).
- Loguru docs — https://loguru.readthedocs.io/
