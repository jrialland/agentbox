# Automatic LSP Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect language stacks recursively (including subdirs), run a shared stdio LSP server per `(project, stack)`, append file-scoped diagnostics to file-write tools, and expose active servers in a chat About panel.

**Architecture:** `agentbox_harness/lsp/` holds stacks, detection, a stdio JSON-RPC client, a shared manager, and a `ToolHook`. `prepare_agent` passes the hook to `build_registry`; a sessions endpoint powers the About modal.

**Tech Stack:** Python 3.12 (stdlib JSON-RPC over stdio), SQLModel/FastAPI, pytest (asyncio auto), React/Mantine, Playwright.

## Global Constraints

- Multi-stack: every detected stack may have its own server; subdirectories count.
- Lazy start, shared per `(project_root, stack)`; failure backoff 60 s; never break a file tool on LSP failure.
- Pull-first (`textDocument/diagnostic`), `publishDiagnostics` fallback; timeouts initialize 10 s / diagnostics 5 s.
- Diagnostics are file-scoped, errors+warnings, capped at 10; clean files add nothing.
- Real servers tested with availability skips; fake stdio server for deterministic tests.
- Regenerate `apps/web/openapi.json` + `schema.d.ts` after the sessions endpoint.
- Run `ruff`/`ty` and relevant suites before each commit.

---

### Task 1: Stacks and recursive detection

**Files:**
- Create: `packages/agentbox-harness/src/agentbox_harness/lsp/stacks.py`
- Create: `packages/agentbox-harness/src/agentbox_harness/lsp/detect.py`
- Create: `packages/agentbox-harness/src/agentbox_harness/lsp/__init__.py`
- Test: `packages/agentbox-harness/tests/test_lsp_detection.py`

**Interfaces:**
- Produces: `LspStack`, `DEFAULT_LSP_SERVERS`, `language_for(stack, path)`, `detect_stacks(project_root, stacks=None)`.

- [ ] **Step 1: Write failing tests**

```python
from agentbox_harness.lsp.detect import detect_stacks
from agentbox_harness.lsp.stacks import language_for


def test_detects_multiple_stacks_in_subdirs(tmp_path):
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "main.py").write_text("x = 1", encoding="utf-8")
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "package.json").write_text("{}", encoding="utf-8")
    names = [stack.name for stack in detect_stacks(str(tmp_path))]
    assert "python" in names
    assert "typescript" in names


def test_prunes_vendor_dirs(tmp_path):
    (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
    (tmp_path / "node_modules" / "pkg" / "package.json").write_text("{}", encoding="utf-8")
    assert detect_stacks(str(tmp_path)) == []


def test_no_stack_when_no_markers(tmp_path):
    assert detect_stacks(str(tmp_path)) == []


def test_language_for_extension():
    stack = detect_stacks.__globals__["DEFAULT_LSP_SERVERS"][0]
    assert language_for(stack, "main.py") == "python"
    assert language_for(stack, "main.ts") is None
```

- [ ] **Step 2: Implement**

`stacks.py`:

```python
import pathlib
from dataclasses import dataclass


@dataclass(frozen=True)
class LspStack:
    name: str
    markers: tuple[str, ...]
    command: tuple[str, ...]
    languages: tuple[str, ...]
    extensions: tuple[str, ...]


DEFAULT_LSP_SERVERS = (
    LspStack(
        name="python",
        markers=("pyproject.toml", "setup.py", "requirements.txt", "**/*.py"),
        command=("uvx", "ty", "server"),
        languages=("python",),
        extensions=(".py", ".pyi"),
    ),
    LspStack(
        name="typescript",
        markers=("**/tsconfig.json", "**/package.json"),
        command=("npx", "typescript-language-server", "--stdio"),
        languages=("typescript", "typescriptreact", "javascript", "javascriptreact"),
        extensions=(".ts", ".tsx", ".js", ".jsx"),
    ),
    LspStack(
        name="rust",
        markers=("**/Cargo.toml",),
        command=("rust-analyzer",),
        languages=("rust",),
        extensions=(".rs",),
    ),
)

LANGUAGE_BY_EXTENSION = {
    ".py": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".tsx": "typescriptreact",
    ".js": "javascript",
    ".jsx": "javascriptreact",
    ".rs": "rust",
}


def language_for(stack: LspStack, path: str) -> str | None:
    extension = pathlib.Path(path).suffix.lower()
    if extension not in stack.extensions:
        return None
    language = LANGUAGE_BY_EXTENSION.get(extension)
    return language if language in stack.languages else None
```

`detect.py`:

```python
import pathlib

from agentbox_harness.lsp.stacks import DEFAULT_LSP_SERVERS, LspStack

PRUNE_PARTS = {".git", ".venv", "node_modules", "target", "dist", "build", "__pycache__"}


def _kept(path: pathlib.Path, root: pathlib.Path) -> bool:
    return not any(
        part in PRUNE_PARTS or part.startswith(".")
        for part in path.relative_to(root).parts[:-1]
    )


def detect_stacks(
    project_root: str, stacks: list[LspStack] | tuple[LspStack, ...] | None = None
) -> list[LspStack]:
    root = pathlib.Path(project_root)
    found: list[LspStack] = []
    for stack in stacks or DEFAULT_LSP_SERVERS:
        for marker in stack.markers:
            matches = [p for p in root.glob(marker) if _kept(p, root)]
            if matches:
                found.append(stack)
                break
    return found
```

`__init__.py` re-exports `LspStack`, `DEFAULT_LSP_SERVERS`, `language_for`, `detect_stacks`.

- [ ] **Step 3: Run and commit**

```bash
uv run pytest packages/agentbox-harness/tests/test_lsp_detection.py -q
git add packages/agentbox-harness/src/agentbox_harness/lsp packages/agentbox-harness/tests/test_lsp_detection.py
git commit -m "feat(harness): recursive multi-stack LSP detection"
```

---

### Task 2: Stdio LSP client + fake server tests

**Files:**
- Create: `packages/agentbox-harness/src/agentbox_harness/lsp/client.py`
- Create: `packages/agentbox-harness/tests/fake_lsp_server.py`
- Test: `packages/agentbox-harness/tests/test_lsp_client.py`

**Interfaces:**
- Produces: `LspServer(command, root, *, initialize_timeout=10, diagnostics_timeout=5)`, `start()`, `sync_document(path, language)`, `diagnostics(path)`, `stop()`.

- [ ] **Step 1: Implement the client**

```python
import asyncio
import json
import os
import pathlib

from loguru import logger


class LspServer:
    def __init__(
        self, command, root, *, initialize_timeout=10.0, diagnostics_timeout=5.0
    ):
        self.command = list(command)
        self.root = pathlib.Path(root)
        self.initialize_timeout = initialize_timeout
        self.diagnostics_timeout = diagnostics_timeout
        self.process = None
        self._reader = None
        self._pending = {}
        self._next_id = 0
        self._versions = {}
        self._diagnostics = {}
        self._diagnostic_events = {}
        self._capabilities = {}
        self.dead = False
        self._write_lock = asyncio.Lock()

    @property
    def documents(self) -> int:
        return len(self._versions)

    async def start(self):
        self.process = await asyncio.create_subprocess_exec(
            *self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._reader = asyncio.create_task(self._read_loop())
        result = await self._request(
            "initialize",
            {
                "processId": os.getpid(),
                "rootUri": self.root.as_uri(),
                "capabilities": {
                    "textDocument": {"publishDiagnostics": {}, "diagnostic": {}}
                },
                "workspaceFolders": [
                    {"uri": self.root.as_uri(), "name": self.root.name}
                ],
            },
            timeout=self.initialize_timeout,
        )
        self._capabilities = (result or {}).get("capabilities", {})
        await self._notify("initialized", {})
        return self

    async def _send(self, message):
        if self.dead or not self.process or not self.process.stdin:
            raise RuntimeError("LSP server is not running")
        data = json.dumps(message).encode("utf-8")
        async with self._write_lock:
            self.process.stdin.write(
                f"Content-Length: {len(data)}\r\n\r\n".encode() + data
            )
            await self.process.stdin.drain()

    async def _notify(self, method, params):
        await self._send({"jsonrpc": "2.0", "method": method, "params": params})

    async def _request(self, method, params, timeout=None):
        self._next_id += 1
        rid = self._next_id
        future = asyncio.get_running_loop().create_future()
        self._pending[rid] = future
        await self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        try:
            return await asyncio.wait_for(
                future, timeout or self.diagnostics_timeout
            )
        except asyncio.TimeoutError:
            self._pending.pop(rid, None)
            raise

    async def _read_message(self):
        reader = self.process.stdout
        length = None
        while True:
            line = await reader.readline()
            if not line:
                return None
            line = line.strip()
            if not line:
                break
            key, _, value = line.decode("ascii", "ignore").partition(":")
            if key.lower() == "content-length":
                length = int(value)
        if length is None:
            raise ValueError("Missing Content-Length")
        return json.loads(await reader.readexactly(length))

    async def _handle_server_request(self, message):
        method = message.get("method")
        if method == "workspace/configuration":
            result = [{} for _ in message.get("params", {}).get("items", [])]
        else:
            result = None
        await self._send(
            {"jsonrpc": "2.0", "id": message.get("id"), "result": result}
        )

    async def _read_loop(self):
        try:
            while True:
                message = await self._read_message()
                if message is None:
                    break
                if "id" in message and "method" in message:
                    await self._handle_server_request(message)
                elif "id" in message:
                    future = self._pending.pop(message["id"], None)
                    if future and not future.done():
                        if "error" in message:
                            future.set_exception(RuntimeError(str(message["error"])))
                        else:
                            future.set_result(message.get("result"))
                elif message.get("method") == "textDocument/publishDiagnostics":
                    params = message.get("params", {})
                    uri = params.get("uri")
                    self._diagnostics[uri] = params.get("diagnostics", [])
                    event = self._diagnostic_events.get(uri)
                    if event:
                        event.set()
                elif message.get("method") in ("window/logMessage", "window/showMessage"):
                    logger.debug("lsp notification {}", message.get("params", {}))
        except Exception:
            logger.exception("lsp reader failed")
        finally:
            self.dead = True
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(RuntimeError("LSP server closed"))
            self._pending.clear()

    async def sync_document(self, path: str, language: str):
        target = pathlib.Path(path).resolve()
        uri = target.as_uri()
        text = target.read_text(encoding="utf-8")
        version = self._versions.get(uri, 0) + 1
        if uri not in self._versions:
            await self._notify(
                "textDocument/didOpen",
                {
                    "textDocument": {
                        "uri": uri,
                        "languageId": language,
                        "version": version,
                        "text": text,
                    }
                },
            )
        else:
            await self._notify(
                "textDocument/didChange",
                {
                    "textDocument": {"uri": uri, "version": version},
                    "contentChanges": [{"text": text}],
                },
            )
        self._versions[uri] = version

    async def diagnostics(self, path: str):
        uri = pathlib.Path(path).resolve().as_uri()
        if self._capabilities.get("diagnosticProvider"):
            result = await self._request(
                "textDocument/diagnostic",
                {"textDocument": {"uri": uri}},
                timeout=self.diagnostics_timeout,
            )
            return (result or {}).get("items", [])
        if uri in self._diagnostics:
            return self._diagnostics[uri]
        event = asyncio.Event()
        self._diagnostic_events[uri] = event
        try:
            await asyncio.wait_for(event.wait(), self.diagnostics_timeout)
        except asyncio.TimeoutError:
            return []
        finally:
            self._diagnostic_events.pop(uri, None)
        return self._diagnostics.get(uri, [])

    async def stop(self):
        if self.process and self.process.returncode is None:
            try:
                await self._request("shutdown", None, timeout=2.0)
                await self._notify("exit", None)
                await asyncio.wait_for(self.process.wait(), 2.0)
            except Exception:
                self.process.terminate()
        if self._reader:
            self._reader.cancel()
        self.dead = True
```

- [ ] **Step 2: Fake LSP server**

`tests/fake_lsp_server.py` (run as `python fake_lsp_server.py`):

```python
import json
import sys


def read_message():
    length = None
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        line = line.strip()
        if not line:
            break
        key, _, value = line.decode().partition(":")
        if key.lower() == "content-length":
            length = int(value)
    return json.loads(sys.stdin.buffer.read(length))


def send(message):
    data = json.dumps(message).encode()
    sys.stdout.buffer.write(f"Content-Length: {len(data)}\r\n\r\n".encode() + data)
    sys.stdout.buffer.flush()


def main():
    push = "--push" in sys.argv
    fail = "--no-response" in sys.argv
    docs = {}
    while True:
        message = read_message()
        if message is None:
            break
        method = message.get("method")
        if method == "initialize":
            send({
                "jsonrpc": "2.0",
                "id": message["id"],
                "result": {
                    "capabilities": {} if push else {"diagnosticProvider": {}}
                },
            })
        elif method == "textDocument/didOpen":
            docs[message["params"]["textDocument"]["uri"]] = 1
            if push:
                send({
                    "jsonrpc": "2.0",
                    "method": "textDocument/publishDiagnostics",
                    "params": {
                        "uri": message["params"]["textDocument"]["uri"],
                        "diagnostics": [
                            {
                                "range": {"start": {"line": 0, "character": 0}},
                                "severity": 1,
                                "message": "fake error",
                                "source": "fake",
                            }
                        ],
                    },
                })
        elif method == "textDocument/didChange":
            docs[message["params"]["textDocument"]["uri"]] += 1
        elif method == "textDocument/diagnostic":
            if fail:
                continue
            send({
                "jsonrpc": "2.0",
                "id": message["id"],
                "result": {
                    "items": [
                        {
                            "range": {"start": {"line": 2, "character": 3}},
                            "severity": 1,
                            "message": "fake pull error",
                            "source": "fake",
                        }
                    ]
                },
            })
        elif method == "shutdown":
            send({"jsonrpc": "2.0", "id": message["id"], "result": None})
        elif method == "exit":
            break


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Tests**

```python
import pathlib
import sys

from agentbox_harness.lsp.client import LspServer


def command(*args):
    return [sys.executable, str(pathlib.Path(__file__).parent / "fake_lsp_server.py"), *args]


async def test_pull_diagnostics(tmp_path):
    path = tmp_path / "a.py"
    path.write_text("x = 1", encoding="utf-8")
    server = await LspServer(command(), tmp_path).start()
    try:
        await server.sync_document(str(path), "python")
        result = await server.diagnostics(str(path))
        assert result[0]["message"] == "fake pull error"
        assert server.documents == 1
    finally:
        await server.stop()


async def test_push_fallback(tmp_path):
    path = tmp_path / "a.py"
    path.write_text("x = 1", encoding="utf-8")
    server = await LspServer(command("--push"), tmp_path).start()
    try:
        await server.sync_document(str(path), "python")
        result = await server.diagnostics(str(path))
        assert result[0]["message"] == "fake error"
    finally:
        await server.stop()


async def test_timeout_returns_empty(tmp_path):
    path = tmp_path / "a.py"
    path.write_text("x = 1", encoding="utf-8")
    server = await LspServer(command("--no-response"), tmp_path, diagnostics_timeout=0.2).start()
    try:
        await server.sync_document(str(path), "python")
        assert await server.diagnostics(str(path)) == []
    finally:
        await server.stop()
```

- [ ] **Step 4: Run and commit**

```bash
uv run pytest packages/agentbox-harness/tests/test_lsp_client.py -q
git add packages/agentbox-harness/src/agentbox_harness/lsp/client.py packages/agentbox-harness/tests/fake_lsp_server.py packages/agentbox-harness/tests/test_lsp_client.py
git commit -m "feat(harness): stdio LSP client with pull/push diagnostics"
```

---

### Task 3: Shared manager with active-session tracking

**Files:**
- Create: `packages/agentbox-harness/src/agentbox_harness/lsp/manager.py`
- Test: `packages/agentbox-harness/tests/test_lsp_manager.py`

**Interfaces:**
- Produces: `LspManager`, `get_lsp_manager()`, `configure_lsp(settings)`, `detected`, `get_or_start`, `record_active`, `active_for_session`, `detected_for_project`, `shutdown`, `reset`.

- [ ] **Step 1: Implement**

```python
import json
import time

from loguru import logger

from agentbox_harness.lsp.client import LspServer
from agentbox_harness.lsp.detect import detect_stacks
from agentbox_harness.lsp.stacks import LspStack


class LspManager:
    def __init__(self):
        self.enabled = True
        self.initialize_timeout = 10.0
        self.diagnostics_timeout = 5.0
        self.failure_backoff = 60.0
        self.stacks = None
        self._servers = {}
        self._detected = {}
        self._active = {}
        self._failed = {}

    def configure(self, settings):
        self.enabled = settings.lsp_enabled
        self.initialize_timeout = settings.lsp_initialize_timeout
        self.diagnostics_timeout = settings.lsp_diagnostics_timeout
        self.failure_backoff = settings.lsp_failure_backoff_seconds
        if settings.lsp_servers_json:
            self.stacks = [
                LspStack(**entry)
                for entry in json.loads(settings.lsp_servers_json)
            ]

    def detected(self, project_root):
        if project_root not in self._detected:
            self._detected[project_root] = detect_stacks(project_root, self.stacks)
        return self._detected[project_root]

    async def get_or_start(self, project_root, stack):
        if not self.enabled:
            return None
        key = (project_root, stack.name)
        if (
            key in self._failed
            and time.monotonic() - self._failed[key] < self.failure_backoff
        ):
            return None
        server = self._servers.get(key)
        if server and not server.dead:
            return server
        try:
            server = LspServer(
                stack.command,
                project_root,
                initialize_timeout=self.initialize_timeout,
                diagnostics_timeout=self.diagnostics_timeout,
            )
            await server.start()
            self._servers[key] = server
            self._failed.pop(key, None)
            return server
        except Exception as exc:
            logger.warning(
                "lsp unavailable project={} stack={} error={}",
                project_root,
                stack.name,
                exc,
            )
            self._failed[key] = time.monotonic()
            return None

    def record_active(self, session_id, project_root, stack, server):
        self._active.setdefault(session_id, {})[stack.name] = (
            project_root,
            stack,
            server,
        )

    def active_for_session(self, session_id):
        entries = []
        for project_root, stack, server in self._active.get(session_id, {}).values():
            entries.append(
                {
                    "stack": stack.name,
                    "command": " ".join(stack.command),
                    "root": project_root,
                    "status": "failed" if server.dead else "running",
                    "documents": server.documents,
                }
            )
        return entries

    def detected_for_project(self, project_root):
        return [stack.name for stack in self.detected(project_root)]

    async def shutdown(self):
        for server in list(self._servers.values()):
            await server.stop()
        self._servers.clear()
        self._active.clear()

    def reset(self):
        self._servers.clear()
        self._detected.clear()
        self._active.clear()
        self._failed.clear()


_manager = LspManager()


def get_lsp_manager() -> LspManager:
    return _manager


def configure_lsp(settings):
    _manager.configure(settings)
```

- [ ] **Step 2: Tests**

```python
import pathlib
import sys

from agentbox_harness.lsp.manager import LspManager
from agentbox_harness.lsp.stacks import DEFAULT_LSP_SERVERS


def command():
    return [
        sys.executable,
        str(pathlib.Path(__file__).parent / "fake_lsp_server.py"),
    ]


def test_detected_for_project(tmp_path):
    manager = LspManager()
    (tmp_path / "a.py").write_text("x", encoding="utf-8")
    assert manager.detected_for_project(str(tmp_path)) == ["python"]


async def test_get_or_start_reuses_and_tracks_active(tmp_path):
    manager = LspManager()
    stack = DEFAULT_LSP_SERVERS[0]
    server = await manager.get_or_start(str(tmp_path), stack)
    assert server is not None
    assert await manager.get_or_start(str(tmp_path), stack) is server
    manager.record_active("s1", str(tmp_path), stack, server)
    active = manager.active_for_session("s1")
    assert active[0]["stack"] == "python"
    assert active[0]["status"] == "running"
    await manager.shutdown()


async def test_failed_server_backs_off(tmp_path):
    manager = LspManager()
    manager.failure_backoff = 60
    stack = DEFAULT_LSP_SERVERS[0]
    stack = LspStack(
        stack.name, stack.markers, ("definitely-not-a-real-command",), stack.languages, stack.extensions
    )
    assert await manager.get_or_start(str(tmp_path), stack) is None
    assert await manager.get_or_start(str(tmp_path), stack) is None
```

- [ ] **Step 3: Run and commit**

```bash
uv run pytest packages/agentbox-harness/tests/test_lsp_manager.py -q
git add packages/agentbox-harness/src/agentbox_harness/lsp/manager.py packages/agentbox-harness/tests/test_lsp_manager.py
git commit -m "feat(harness): shared per-project LSP manager"
```

---

### Task 4: Diagnostics hook and wiring

**Files:**
- Create: `packages/agentbox-harness/src/agentbox_harness/lsp/hooks.py`
- Modify: `packages/agentbox-api/src/agentbox_api/config.py`
- Modify: `packages/agentbox-api/src/agentbox_api/skills.py`
- Modify: `packages/agentbox-api/src/agentbox_api/app.py`
- Modify: `packages/agentbox-api/src/agentbox_api/acp_server.py`
- Test: `packages/agentbox-harness/tests/test_lsp_hook.py`

**Interfaces:**
- Produces: `make_lsp_hook(manager, session_id, project_root)`, `format_diagnostics`.
- Consumes: `ToolRegistry(hooks=...)`, `prepare_agent(session_id=...)`.

- [ ] **Step 1: Implement**

```python
import pathlib

from loguru import logger

from agentbox_harness.lsp.stacks import language_for
from agentbox_harness.tools.registry import ToolHookContext

WRITE_TOOLS = {"write_file", "append_file", "edit_file"}


def format_diagnostics(path: str, diagnostics: list[dict]) -> str | None:
    rows = []
    for diagnostic in diagnostics:
        if diagnostic.get("severity", 1) not in (1, 2):
            continue
        start = diagnostic.get("range", {}).get("start", {})
        line = start.get("line", 0) + 1
        column = start.get("character", 0) + 1
        level = "error" if diagnostic.get("severity", 1) == 1 else "warning"
        source = f" ({diagnostic['source']})" if diagnostic.get("source") else ""
        rows.append(
            f"  {line}:{column} {level} {diagnostic.get('message', '')}{source}"
        )
    if not rows:
        return None
    suffix = f"\n  ... and {len(rows) - 10} more" if len(rows) > 10 else ""
    return f"LSP diagnostics for {path}:\n" + "\n".join(rows[:10]) + suffix


def make_lsp_hook(manager, session_id: str | None, project_root: str):
    async def hook(ctx: ToolHookContext) -> str | None:
        if ctx.tool_name not in WRITE_TOOLS or not manager.enabled:
            return None
        path = ctx.args.get("path")
        if not path:
            return None
        stack = next(
            (
                item
                for item in manager.detected(project_root)
                if language_for(item, path)
            ),
            None,
        )
        if stack is None:
            return None
        server = await manager.get_or_start(project_root, stack)
        if server is None:
            return None
        language = language_for(stack, path)
        await server.sync_document(path, language)
        diagnostics = await server.diagnostics(path)
        if session_id:
            manager.record_active(session_id, project_root, stack, server)
        return format_diagnostics(path, diagnostics)

    return hook
```

In `config.py`, add the five `lsp_*` settings from the spec.

In `skills.py`:

```python
from agentbox_harness.lsp.hooks import make_lsp_hook
from agentbox_harness.lsp.manager import get_lsp_manager
...
    hooks = []
    manager = get_lsp_manager()
    if session_id and manager.enabled:
        hooks.append(make_lsp_hook(manager, session_id, project_root))
    registry = build_registry(
        project_root,
        extra_read_roots=[s.location.parent for s in skills],
        extra_tools=extra_tools,
        hooks=hooks,
        media_max_dimension=media_max_dimension,
        media_max_bytes=media_max_bytes,
    )
```

In `app.py` lifespan and `acp_server._serve`, call `configure_lsp(settings)`.

- [ ] **Step 2: Tests**

`test_lsp_hook.py`:

```python
import pathlib
import sys

from agentbox_harness.lsp.hooks import format_diagnostics, make_lsp_hook
from agentbox_harness.lsp.manager import LspManager
from agentbox_harness.tools.registry import ToolHookContext


async def test_hook_appends_diagnostics(tmp_path):
    manager = LspManager()
    manager.stacks = None
    path = tmp_path / "a.py"
    path.write_text("x = 1", encoding="utf-8")
    hook = make_lsp_hook(manager, "s1", str(tmp_path))
    ctx = ToolHookContext(
        tool_name="write_file", args={"path": str(path)}, root=tmp_path, result="ok"
    )
    text = await hook(ctx)
    assert "fake pull error" in text
    assert manager.active_for_session("s1")[0]["stack"] == "python"
    await manager.shutdown()


async def test_hook_skips_non_code(tmp_path):
    manager = LspManager()
    path = tmp_path / "notes.txt"
    path.write_text("x", encoding="utf-8")
    hook = make_lsp_hook(manager, "s1", str(tmp_path))
    ctx = ToolHookContext(
        tool_name="write_file", args={"path": str(path)}, root=tmp_path, result="ok"
    )
    assert await hook(ctx) is None


async def test_hook_clean_file_returns_none(tmp_path):
    manager = LspManager()
    manager.stacks = []
    path = tmp_path / "a.py"
    path.write_text("x", encoding="utf-8")
    hook = make_lsp_hook(manager, "s1", str(tmp_path))
    ctx = ToolHookContext(
        tool_name="write_file", args={"path": str(path)}, root=tmp_path, result="ok"
    )
    assert await hook(ctx) is None


def test_format_caps_and_filters():
    diagnostics = [
        {
            "severity": 1,
            "range": {"start": {"line": 0, "character": 1}},
            "message": f"error {i}",
        }
        for i in range(12)
    ]
    text = format_diagnostics("a.py", diagnostics)
    assert "and 2 more" in text
```

- [ ] **Step 3: Run and commit**

```bash
uv run pytest packages/agentbox-harness/tests/test_lsp_hook.py -q
uv run pytest packages/agentbox-api/tests/test_prompt_rendering.py -q
git add packages/agentbox-harness/src/agentbox_harness/lsp/hooks.py packages/agentbox-harness/tests/test_lsp_hook.py packages/agentbox-api/src/agentbox_api/config.py packages/agentbox-api/src/agentbox_api/skills.py packages/agentbox-api/src/agentbox_api/app.py packages/agentbox-api/src/agentbox_api/acp_server.py
git commit -m "feat: LSP diagnostics hook and wiring"
```

---

### Task 5: About endpoint and chat modal

**Files:**
- Modify: `packages/agentbox-api/src/agentbox_api/routers/sessions.py`
- Regenerate: `apps/web/openapi.json`, `apps/web/src/api/schema.d.ts`
- Modify: `apps/web/src/api/endpoints.ts`, `queries.ts`, `pages/SessionPage.tsx`
- Modify: `apps/web/e2e/chat.spec.ts`

**Interfaces:**
- Produces: `GET /sessions/{sid}/lsp`, `fetchSessionLsp`, `useSessionLsp`, About modal.

- [ ] **Step 1: Endpoint**

In `sessions.py`, add:

```python
@router.get("/{sid}/lsp")
async def session_lsp(
    sid: str, request: Request, _=Depends(require_permission("sessions:read"))
):
    factory = request.app.state.session_factory
    async with factory() as s:
        srow = (
            await s.execute(select(SessionRow).where(SessionRow.id == sid))
        ).scalars().first()
        if srow is None:
            raise HTTPException(status_code=404, detail="Session not found")
        project = (
            await s.execute(select(Project).where(Project.id == srow.project_id))
        ).scalars().first()
    manager = get_lsp_manager()
    return {
        "detected": manager.detected_for_project(project.path),
        "active": manager.active_for_session(sid),
    }
```

Import `get_lsp_manager`.

- [ ] **Step 2: Web client + modal**

Add `fetchSessionLsp`/`useSessionLsp`, an About button on `SessionPage`, and a modal rendering detected and active stacks.

- [ ] **Step 3: E2E**

In `chat.spec.ts`, open an existing session, click About, and assert the modal lists the detected `python` stack (the repo contains `.py` files).

- [ ] **Step 4: Run and commit**

```bash
uv run python apps/web/scripts/gen-openapi.py
cd apps/web && bun run codegen && bun run build && bun run e2e -- chat.spec.ts
git add packages/agentbox-api/src/agentbox_api/routers/sessions.py apps/web/openapi.json apps/web/src/api/schema.d.ts apps/web/src/api/endpoints.ts apps/web/src/api/queries.ts apps/web/src/pages/SessionPage.tsx apps/web/e2e/chat.spec.ts
git commit -m "feat: session About panel with active LSP servers"
```

---

### Task 6: Real-server integration tests (availability-skipped)

**Files:**
- Create: `packages/agentbox-harness/tests/test_lsp_real.py`

- [ ] **Step 1: Write tests**

```python
import pathlib
import shutil

import pytest

from agentbox_harness.lsp.hooks import make_lsp_hook
from agentbox_harness.lsp.manager import LspManager
from agentbox_harness.tools.registry import ToolHookContext

pytestmark = pytest.mark.slow


async def _run(project: pathlib.Path, filename: str, content: str):
    manager = LspManager()
    path = project / filename
    path.write_text(content, encoding="utf-8")
    hook = make_lsp_hook(manager, "real", str(project))
    ctx = ToolHookContext(
        tool_name="write_file", args={"path": str(path)}, root=project, result="ok"
    )
    try:
        return await hook(ctx)
    finally:
        await manager.shutdown()


@pytest.mark.skipif(shutil.which("uvx") is None, reason="uvx not installed")
async def test_python_ty(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    text = await _run(tmp_path, "a.py", 'x: int = "not an int"\n')
    assert text and "error" in text.lower()


@pytest.mark.skipif(shutil.which("npx") is None, reason="npx not installed")
async def test_typescript_language_server(tmp_path):
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    text = await _run(tmp_path, "a.ts", 'const x: number = "no";\n')
    assert text and "error" in text.lower()


@pytest.mark.skipif(shutil.which("rust-analyzer") is None, reason="rust-analyzer not installed")
async def test_rust_analyzer(tmp_path):
    (tmp_path / "Cargo.toml").write_text("[package]\nname = \"x\"\n", encoding="utf-8")
    text = await _run(tmp_path, "a.rs", 'fn main() { let x: i32 = "no"; }\n')
    assert text and "error" in text.lower()
```

- [ ] **Step 2: Run and commit**

```bash
uv run pytest packages/agentbox-harness/tests/test_lsp_real.py -q
git add packages/agentbox-harness/tests/test_lsp_real.py
git commit -m "test(harness): real LSP integration tests"
```

---

### Task 7: Roadmap and full verification

**Files:**
- Modify: `docs/ROADMAP.md`

- [ ] **Step 1: Update the roadmap**

Remove D1 from the deferred backlog and add:

```markdown
| 24 | Automatic LSP diagnostics (multi-stack + About panel) | `specs/2026-11-19-lsp-diagnostics-design.md` | `plans/2026-11-19-lsp-diagnostics.md` |
```

- [ ] **Step 2: Verify**

```bash
uv run ruff check --fix packages
uv run ty check packages
uv run pytest packages/agentbox-harness -q
uv run pytest packages/agentbox-models -q
uv run pytest packages/agentbox-api -q
cd apps/web && bun run test && bun run build
```

- [ ] **Step 3: Commit**

```bash
git add docs/ROADMAP.md
git commit -m "docs(roadmap): automatic LSP diagnostics complete"
```
