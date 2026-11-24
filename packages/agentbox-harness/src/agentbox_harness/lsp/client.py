"""Spawn and talk to a single language server over JSON-RPC.

:class:`LspServer` owns the subprocess, the framed stdin/stdout transport, the
initialize/shutdown handshake, document synchronization, and diagnostic waits.
All network-facing methods are async; process spawning and shutdown are the
operations that touch subprocesses directly.
"""

import asyncio
import contextlib
import json
import os
import pathlib
import shutil
import sys
from collections import OrderedDict, deque
from dataclasses import dataclass
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from loguru import logger

from agentbox_harness.lsp.quiescence import ServerStatusTracker

MAX_MESSAGE_BYTES = 50 * 1024 * 1024


def _path_from_uri(uri: str) -> pathlib.Path:
    return pathlib.Path(url2pathname(unquote(urlparse(uri).path))).resolve()


def _exec_command(command):
    executable = shutil.which(command[0])
    if executable is None:
        return list(command)
    if sys.platform == "win32" and executable.lower().endswith((".cmd", ".bat")):
        return ["cmd", "/c", executable, *command[1:]]
    return [executable, *command[1:]]


@dataclass(frozen=True)
class WriteBaseline:
    """Counters captured at a document write, used to ignore stale results.

    Attributes:
        generation: Diagnostic publish generation for the document.
        busy_seq: Server-status busy counter when the write was recorded.
        status_seq: Total server-status notification counter at write time.
    """

    generation: int
    busy_seq: int
    status_seq: int


class LspServer:
    """A subprocess-backed language server speaking LSP over stdio.

    The server starts lazily via :meth:`start`, keeps a bounded LRU of open
    documents, and correlates JSON-RPC responses with pending requests by id.
    Diagnostic waits combine a first-change timeout, a settle window, and
    optional server-reported quiescence; see :meth:`wait_for_diagnostics`.
    """

    def __init__(
        self,
        command,
        root,
        *,
        pull=True,
        settle=3.0,
        quiescence: str | None = None,
        initialize_timeout=10.0,
        diagnostics_timeout=5.0,
        first_change_timeout=1.0,
        settle_window=0.3,
        post_quiescence_grace=0.5,
        max_wait: float | None = None,
        stderr_lines=200,
        doc_limit=50,
        stack_name: str | None = None,
    ):
        self.command = list(command)
        self.root = pathlib.Path(root)
        self.pull = pull
        self.settle = settle
        self.quiescence = quiescence
        self.initialize_timeout = initialize_timeout
        self.diagnostics_timeout = diagnostics_timeout
        self.first_change_timeout = first_change_timeout
        self.settle_window = settle_window
        self.post_quiescence_grace = post_quiescence_grace
        self.max_wait = diagnostics_timeout if max_wait is None else max_wait
        self.stderr_lines = stderr_lines
        self.doc_limit = doc_limit
        self.stack_name = stack_name or (self.command[0] if self.command else "lsp")
        self.process = None
        self._reader = None
        self._stderr_reader = None
        self._pending = {}
        self._next_id = 0
        self._versions = {}
        self._diagnostics = {}
        self._publish_gen = {}
        self._waiters: dict[pathlib.Path, set[asyncio.Event]] = {}
        self._last_write: dict[pathlib.Path, WriteBaseline] = {}
        self._open_order: OrderedDict[pathlib.Path, None] = OrderedDict()
        self._capabilities = {}
        self._tracker = (
            ServerStatusTracker() if quiescence == "server_status" else None
        )
        self._stderr: deque[str] = deque(maxlen=stderr_lines)
        self._state = "unstarted"
        self._last_error: str | None = None
        self._root_uri = ""
        self.dead = False
        self._write_lock = asyncio.Lock()
        self._sync_lock = asyncio.Lock()

    @property
    def documents(self) -> int:
        """Return the number of documents currently open on the server."""
        return len(self._versions)

    async def start(self):
        """Spawn the server, perform initialization, and mark it ready.

        This async method creates the subprocess and its reader tasks, sends
        ``initialize`` with client capabilities, then sends ``initialized``.
        Initialization is bounded by ``initialize_timeout``. On any failure the
        process is terminated and the exception is re-raised.

        Returns:
            This server instance, now ready for document synchronization.
        """
        self._state = "starting"
        try:
            self.process = await asyncio.create_subprocess_exec(
                *_exec_command(self.command),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.root),
            )
            self._reader = asyncio.create_task(self._read_loop())
            self._stderr_reader = asyncio.create_task(self._stderr_loop())
            self._root_uri = self.root.as_uri().rstrip("/") + "/"
            # Advertise push diagnostics always, pull diagnostics when enabled,
            # and the experimental server-status extension for quiescence.
            capabilities: dict = {
                "textDocument": {"publishDiagnostics": {}}
            }
            if self.pull:
                capabilities["textDocument"]["diagnostic"] = {}
            if self._tracker is not None:
                capabilities.update(self._tracker.client_capabilities())
            result = await self._request(
                "initialize",
                {
                    "processId": os.getpid(),
                    "rootUri": self._root_uri,
                    "capabilities": capabilities,
                    "workspaceFolders": [
                        {"uri": self._root_uri, "name": self.root.name}
                    ],
                    "clientInfo": {"name": "agentbox"},
                },
                timeout=self.initialize_timeout,
            )
            self._capabilities = (result or {}).get("capabilities", {})
            await self._notify("initialized", {})
            self._state = "ready"
            return self
        except Exception as exc:
            self._state = "error"
            self._last_error = str(exc)
            self.dead = True
            await self._terminate()
            raise

    async def _terminate(self):
        if self.process and self.process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                # A missing process means it already exited; nothing to kill.
                self.process.terminate()
        for task in (self._reader, self._stderr_reader):
            if task is not None:
                task.cancel()

    async def _send(self, message):
        if self.dead or not self.process or not self.process.stdin:
            raise RuntimeError("LSP server is not running")
        data = json.dumps(message).encode("utf-8")
        async with self._write_lock:
            # LSP framing: a Content-Length header, a blank line, then the
            # UTF-8 JSON body. The lock serializes concurrent writes so frames
            # never interleave on stdin.
            self.process.stdin.write(
                f"Content-Length: {len(data)}\r\n\r\n".encode() + data
            )
            await self.process.stdin.drain()

    async def _notify(self, method, params):
        await self._send({"jsonrpc": "2.0", "method": method, "params": params})

    async def _request(self, method, params, timeout=None):
        # Requests carry a unique id and register a future before sending, so a
        # response arriving immediately in the reader loop can correlate back.
        self._next_id += 1
        rid = self._next_id
        future = asyncio.get_running_loop().create_future()
        self._pending[rid] = future
        try:
            await self._send(
                {"jsonrpc": "2.0", "id": rid, "method": method, "params": params}
            )
        except Exception:
            self._pending.pop(rid, None)
            raise
        try:
            return await asyncio.wait_for(
                future, timeout or self.max_wait
            )
        except TimeoutError:
            # Drop the pending future so a late response is ignored.
            self._pending.pop(rid, None)
            raise

    async def _read_message(self):
        reader = self.process.stdout  # ty: ignore[missing-union-attribute]
        length = None
        # Read header lines until the blank separator, then read exactly
        # Content-Length bytes. EOF (an empty line) means the server exited.
        while True:
            line = await reader.readline()  # ty: ignore[missing-union-attribute]
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
        if length > MAX_MESSAGE_BYTES:
            # Refuse oversized frames rather than allocating unbounded memory.
            raise ValueError(f"LSP message too large: {length}")
        return json.loads(await reader.readexactly(length))  # ty: ignore[missing-union-attribute]

    async def _handle_server_request(self, message):
        # Server-initiated requests (configuration, workspace folders, edits,
        # and progress) get lightweight stub responses; unknown methods return
        # JSON-RPC "method not found" so the server is never left blocked.
        method = message.get("method")
        if method == "workspace/configuration":
            result = [{} for _ in message.get("params", {}).get("items", [])]
        elif method == "workspace/workspaceFolders":
            result = [{"uri": self._root_uri, "name": self.root.name}]
        elif method == "workspace/applyEdit":
            result = {"applied": True}
        elif method == "window/showDocument":
            result = {"success": True}
        elif method in (
            "client/registerCapability",
            "window/showMessage",
            "window/showMessageRequest",
            "window/workDoneProgress/create",
        ):
            result = None
        else:
            await self._send(
                {
                    "jsonrpc": "2.0",
                    "id": message.get("id"),
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method}",
                    },
                }
            )
            return
        await self._send(
            {"jsonrpc": "2.0", "id": message.get("id"), "result": result}
        )

    def _wake(self, path: pathlib.Path) -> None:
        for event in list(self._waiters.get(path, ())):
            event.set()

    def _wake_all(self) -> None:
        for events in list(self._waiters.values()):
            for event in list(events):
                event.set()

    def _record_publish(self, key: pathlib.Path, published: list) -> None:
        # Each publish bumps the generation so waiters can distinguish results
        # produced after their write baseline from stale earlier ones.
        self._diagnostics[key] = published
        self._publish_gen[key] = self._publish_gen.get(key, 0) + 1
        self._wake(key)

    async def _read_loop(self):
        try:
            while True:
                message = await self._read_message()
                if message is None:
                    break
                if "id" in message and "method" in message:
                    # id + method means a server-initiated request, not a
                    # response to one of ours.
                    await self._handle_server_request(message)
                elif "id" in message:
                    # Correlate the response id with the future registered by
                    # _request; a missing entry is a late reply after timeout.
                    future = self._pending.pop(message["id"], None)
                    if future and not future.done():
                        if "error" in message:
                            future.set_exception(RuntimeError(str(message["error"])))
                        else:
                            future.set_result(message.get("result"))
                elif message.get("method") == "textDocument/publishDiagnostics":
                    params = message.get("params", {})
                    try:
                        key = _path_from_uri(params.get("uri", ""))
                    except Exception:
                        logger.debug(
                            "lsp publish with invalid uri stack={} uri={}",
                            self.stack_name,
                            params.get("uri"),
                        )
                        continue
                    published = params.get("diagnostics", [])
                    logger.debug(
                        "lsp publish stack={} path={} count={}",
                        self.stack_name,
                        key,
                        len(published),
                    )
                    self._record_publish(key, published)
                elif message.get("method") == "experimental/serverStatus":
                    if self._tracker is not None:
                        self._tracker.handle(message.get("params", {}))
                        self._wake_all()
                elif message.get("method") in (
                    "window/logMessage",
                    "window/showMessage",
                ):
                    logger.debug("lsp notification {}", message.get("params", {}))
        except Exception as exc:
            self._last_error = str(exc)
            self._state = "error"
            logger.exception("lsp reader failed stack={}", self.stack_name)
        finally:
            logger.debug(
                "lsp reader ended stack={} state={} returncode={}",
                self.stack_name,
                self._state,
                self.process.returncode if self.process else None,
            )
            self.dead = True
            if self._state != "error":
                self._state = "stopped"
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(RuntimeError("LSP server closed"))
            self._pending.clear()
            self._wake_all()

    async def _stderr_loop(self):
        stream = self.process.stderr if self.process else None
        if stream is None:
            return
        try:
            while True:
                line = await stream.readline()
                if not line:
                    return
                text = line.decode("utf-8", "replace").rstrip()
                self._stderr.append(text)
                logger.debug(
                    "lsp stderr stack={} {}", self.stack_name, text[:500]
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.debug("lsp stderr reader failed stack={}", self.stack_name)

    def _write_baseline(self, target: pathlib.Path) -> WriteBaseline:
        tracker = self._tracker
        return WriteBaseline(
            generation=self._publish_gen.get(target, 0),
            busy_seq=tracker.busy_seq if tracker is not None else 0,
            status_seq=tracker.seq if tracker is not None else 0,
        )

    def _touch_document(self, target: pathlib.Path) -> None:
        self._open_order.pop(target, None)
        self._open_order[target] = None

    async def _enforce_doc_limit(self) -> None:
        # _open_order is a least-recently-used queue: drop and close documents
        # from the front once the configured limit is exceeded.
        while len(self._open_order) > self.doc_limit:
            target, _ = self._open_order.popitem(last=False)
            await self._notify(
                "textDocument/didClose",
                {"textDocument": {"uri": target.as_uri()}},
            )
            self._drop_document_state(target)

    def _drop_document_state(self, target: pathlib.Path) -> None:
        self._versions.pop(target, None)
        self._diagnostics.pop(target, None)
        self._publish_gen.pop(target, None)
        self._last_write.pop(target, None)
        self._waiters.pop(target, None)

    async def sync_document(
        self, path: str, language: str, *, save: bool = False
    ) -> int:
        """Push the current on-disk text of a document to the server.

        Sends ``didOpen`` the first time a path is seen and ``didChange`` on
        later synchronizations, always under a lock so versions increase
        monotonically. The write baseline is recorded before notifying so later
        diagnostic waits can ignore stale publishes.

        Args:
            path: File path to synchronize.
            language: LSP language id for ``didOpen``.
            save: When true, follow the change with a ``didSave`` notification.

        Returns:
            Diagnostic publish generation captured at the write baseline.
        """
        target = pathlib.Path(path).resolve()
        async with self._sync_lock:
            text = target.read_text(encoding="utf-8")
            baseline = self._write_baseline(target)
            self._last_write[target] = baseline
            version = self._versions.get(target, 0) + 1
            if target not in self._versions:
                await self._notify(
                    "textDocument/didOpen",
                    {
                        "textDocument": {
                            "uri": target.as_uri(),
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
                        "textDocument": {"uri": target.as_uri(), "version": version},
                        "contentChanges": [{"text": text}],
                    },
                )
            self._versions[target] = version
            self._touch_document(target)
            await self._enforce_doc_limit()
            if save:
                await self._notify(
                    "textDocument/didSave",
                    {"textDocument": {"uri": target.as_uri()}},
                )
            return baseline.generation

    async def save_document(self, path: str):
        """Send a ``didSave`` notification for an already open document.

        Args:
            path: File path to announce as saved.
        """
        target = pathlib.Path(path).resolve()
        async with self._sync_lock:
            await self._notify(
                "textDocument/didSave",
                {"textDocument": {"uri": target.as_uri()}},
            )

    async def close_document(self, path: str):
        """Close an open document and drop its cached diagnostic state.

        Closing is a no-op for paths the server never opened.

        Args:
            path: File path to close.
        """
        target = pathlib.Path(path).resolve()
        async with self._sync_lock:
            if target not in self._versions:
                return
            self._open_order.pop(target, None)
            await self._notify(
                "textDocument/didClose",
                {"textDocument": {"uri": target.as_uri()}},
            )
            self._drop_document_state(target)

    async def wait_for_diagnostics(
        self,
        path: str | pathlib.Path,
        since_gen: int | None = None,
        *,
        first: float | None = None,
        settle: float | None = None,
        max_wait: float | None = None,
        quiescence: bool | None = None,
    ) -> list[dict]:
        """Wait for diagnostics that reflect the latest write to a document.

        When server-status quiescence is configured, the wait first learns the
        server's baseline, then waits for a quiescent status that is also after
        a new publish or busy transition. Otherwise it waits for the first
        publish after ``since_gen`` and then for a settle window of silence.
        Any path that times out returns the last cached diagnostics, so this
        method is bounded by ``max_wait``.

        Args:
            path: Document path to await.
            since_gen: Publish generation to treat as stale; defaults to the
                last write baseline for the path.
            first: Seconds to wait for the first diagnostic change.
            settle: Seconds of quiet required before returned results are
                considered stable.
            max_wait: Overall deadline for the wait.
            quiescence: Override whether to use server-status quiescence.

        Returns:
            The most recent diagnostics seen for the path, possibly cached.
        """
        target = pathlib.Path(path).resolve()
        def cached():
            return self._diagnostics.get(target, [])
        if self.dead:
            return cached()
        loop = asyncio.get_running_loop()
        first = self.first_change_timeout if first is None else first
        settle = self.settle_window if settle is None else settle
        max_wait = self.max_wait if max_wait is None else max_wait
        baseline = self._last_write.get(target)
        if since_gen is None:
            since_gen = (
                baseline.generation
                if baseline is not None
                else self._publish_gen.get(target, 0)
            )
        busy_at_start = (
            baseline.busy_seq
            if baseline is not None
            else (self._tracker.busy_seq if self._tracker is not None else 0)
        )
        deadline = loop.time() + max_wait
        started = loop.time()
        event = asyncio.Event()
        self._waiters.setdefault(target, set()).add(event)
        logger.debug(
            "lsp wait start stack={} path={} since={} busy={} quiescent={} max={}",
            self.stack_name,
            target,
            since_gen,
            busy_at_start,
            self._tracker.quiescent if self._tracker else None,
            max_wait,
        )
        quiescence_configured = (
            (quiescence if quiescence is not None else self.quiescence == "server_status")
            and self._tracker is not None
        )
        use_quiescence = (
            quiescence_configured
            and self._tracker is not None
            and self._tracker.seq > 0
        )
        try:
            if quiescence_configured and not use_quiescence:
                # Before the first status notification arrives, briefly probe
                # for quiescence support while still returning early on a new
                # publish so notifications-only servers stay responsive.
                status_deadline = min(deadline, loop.time() + first)
                while loop.time() < status_deadline:
                    event.clear()
                    tracker = self._tracker
                    if tracker is not None and tracker.seq > 0:
                        use_quiescence = True
                        break
                    if self._publish_gen.get(target, 0) > since_gen:
                        break
                    remaining = status_deadline - loop.time()
                    if remaining <= 0:
                        break
                    with contextlib.suppress(TimeoutError):
                        await asyncio.wait_for(event.wait(), min(remaining, 0.05))
            if use_quiescence:
                tracker = self._tracker
                assert tracker is not None

                def settled() -> bool:
                    return tracker.quiescent is True and (
                        self._publish_gen.get(target, 0) > since_gen
                        or tracker.busy_seq > busy_at_start
                    )

                idle_deadline = min(
                    deadline,
                    loop.time() + max(first, self.post_quiescence_grace),
                )
                while True:
                    event.clear()
                    if (
                        tracker.quiescent is True
                        and not settled()
                        and loop.time() >= idle_deadline
                    ):
                        return cached()
                    if settled():
                        if cached():
                            return cached()
                        grace_deadline = min(
                            deadline,
                            loop.time() + self.post_quiescence_grace,
                        )
                        while loop.time() < grace_deadline:
                            remaining = grace_deadline - loop.time()
                            if remaining <= 0:
                                break
                            event.clear()
                            with contextlib.suppress(TimeoutError):
                                await asyncio.wait_for(
                                    event.wait(), min(remaining, 0.05)
                                )
                            if cached():
                                return cached()
                        return cached()
                    if self.dead:
                        return cached()
                    remaining = deadline - loop.time()
                    if remaining <= 0:
                        return cached()
                    with contextlib.suppress(TimeoutError):
                        await asyncio.wait_for(
                            event.wait(), min(remaining, 0.05)
                        )

            while True:
                event.clear()
                if self._publish_gen.get(target, 0) > since_gen:
                    break
                remaining = min(deadline, loop.time() + first) - loop.time()
                if remaining <= 0:
                    return cached()
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(event.wait(), min(remaining, 0.05))
            last_gen = self._publish_gen.get(target, 0)
            stable_since = loop.time()
            # Non-quiescence path: after the first publish, reset the stability
            # clock on every new generation and return once it stays quiet for
            # the settle window.
            while True:
                event.clear()
                gen = self._publish_gen.get(target, 0)
                if gen != last_gen:
                    last_gen = gen
                    stable_since = loop.time()
                elif loop.time() - stable_since >= settle:
                    return cached()
                remaining = deadline - loop.time()
                if remaining <= 0:
                    return cached()
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(event.wait(), min(remaining, 0.05))
        finally:
            events = self._waiters.get(target)
            if events is not None:
                events.discard(event)
                if not events:
                    self._waiters.pop(target, None)
            logger.debug(
                "lsp wait end stack={} path={} elapsed={:.3f} gen={} count={} "
                "quiescent={} dead={} error={} stderr={}",
                self.stack_name,
                target,
                loop.time() - started,
                self._publish_gen.get(target, 0),
                len(cached()),
                self._tracker.quiescent if self._tracker else None,
                self.dead,
                self._last_error,
                list(self._stderr)[-5:],
            )

    async def diagnostics(self, path: str) -> list[dict]:
        """Collect diagnostics for a path using pull or push as available.

        Pull-capable servers are queried directly; an ``unchanged`` result
        reuses the cached report. Otherwise the method waits for a publish
        after the last write baseline and returns an empty list when no fresh
        publish arrived, so stale results are not attributed to a new edit.

        Args:
            path: Document path to analyze.

        Returns:
            Raw LSP diagnostic dictionaries for the path.
        """
        target = pathlib.Path(path).resolve()
        uri = target.as_uri()
        try:
            if self.pull and "diagnosticProvider" in self._capabilities:
                result = await self._request(
                    "textDocument/diagnostic",
                    {"textDocument": {"uri": uri}},
                    timeout=self.max_wait,
                )
                if result and result.get("kind") == "unchanged":
                    return self._diagnostics.get(target, [])
                items = (result or {}).get("items", [])
                self._diagnostics[target] = items
                return items
            baseline = self._last_write.get(target)
            result = await self.wait_for_diagnostics(target)
            if (
                baseline is not None
                and self._publish_gen.get(target, 0) <= baseline.generation
            ):
                # No publish since the write: any cached report is stale.
                return []
            return result
        except TimeoutError:
            return self._diagnostics.get(target, [])
        except Exception:
            logger.exception(
                "lsp diagnostics failed stack={} path={}",
                self.stack_name,
                target,
            )
            return self._diagnostics.get(target, [])

    def health(self) -> dict:
        """Return a small status dictionary for managers and health endpoints."""
        return {
            "stack": self.stack_name,
            "state": self._state,
            "dead": self.dead,
            "documents": len(self._versions),
            "last_error": self._last_error,
            "stderr_tail": list(self._stderr)[-5:],
        }

    async def stop(self):
        """Shut the server down gracefully, then terminate it if needed.

        The LSP shutdown order is a ``shutdown`` request, an ``exit``
        notification, then a bounded wait for the process. If any step fails or
        times out the process is terminated directly, and reader tasks are
        always cancelled so no background task outlives the server.
        """
        if self.process and self.process.returncode is None:
            try:
                await self._request("shutdown", None, timeout=2.0)
                await self._notify("exit", None)
                await asyncio.wait_for(self.process.wait(), 2.0)
            except Exception:
                # Graceful shutdown failed (timeout, closed pipe, crash); fall
                # back to terminating the process.
                with contextlib.suppress(ProcessLookupError):
                    self.process.terminate()
        for task in (self._reader, self._stderr_reader):
            if task is not None:
                task.cancel()
        self.dead = True
        self._state = "stopped"
