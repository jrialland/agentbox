# Loguru sink configuration — plan

1. Add log settings to `agentbox_api.config.Settings`
   (`log_level`, `log_dir`, `log_rotation`, `log_retention`,
   `log_compression`, `log_intercept`).
2. Add `agentbox_api/logging.py` with `InterceptHandler` and
   `configure_logging(settings)` (stderr + rotating text file, stdlib routing,
   `diagnose=False`, never stdout).
3. Call `configure_logging` in the FastAPI lifespan (`app.py`) and in the ACP
   entrypoint (`acp_server._serve`).
4. Gitignore `logs/`.
5. Add a test that writes to a temp log dir and asserts file output plus
   stdlib interception.
6. Verify `ruff`, `ty`, and the API test suite.
