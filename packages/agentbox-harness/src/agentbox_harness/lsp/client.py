import asyncio
import json
import os
import pathlib
import shutil
import sys
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from loguru import logger


def _path_from_uri(uri: str) -> pathlib.Path:
    return pathlib.Path(url2pathname(unquote(urlparse(uri).path))).resolve()


def _exec_command(command):
    executable = shutil.which(command[0])
    if executable is None:
        return list(command)
    if sys.platform == "win32" and executable.lower().endswith((".cmd", ".bat")):
        return ["cmd", "/c", executable, *command[1:]]
    return [executable, *command[1:]]


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
            *_exec_command(self.command),
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
        await self._send(
            {"jsonrpc": "2.0", "id": rid, "method": method, "params": params}
        )
        try:
            return await asyncio.wait_for(
                future, timeout or self.diagnostics_timeout
            )
        except TimeoutError:
            self._pending.pop(rid, None)
            raise

    async def _read_message(self):
        reader = self.process.stdout  # ty: ignore[missing-union-attribute]
        length = None
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
        return json.loads(await reader.readexactly(length))  # ty: ignore[missing-union-attribute]

    async def _handle_server_request(self, message):
        if message.get("method") == "workspace/configuration":
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
                    key = _path_from_uri(params.get("uri", ""))
                    self._diagnostics[key] = params.get("diagnostics", [])
                    event = self._diagnostic_events.get(key)
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
        version = self._versions.get(target, 0) + 1
        if target not in self._versions:
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
        self._versions[target] = version

    async def diagnostics(self, path: str):
        target = pathlib.Path(path).resolve()
        uri = target.as_uri()
        try:
            if "diagnosticProvider" in self._capabilities:
                result = await self._request(
                    "textDocument/diagnostic",
                    {"textDocument": {"uri": uri}},
                    timeout=self.diagnostics_timeout,
                )
                return (result or {}).get("items", [])
            if target in self._diagnostics:
                return self._diagnostics[target]
            event = asyncio.Event()
            self._diagnostic_events[target] = event
            if target in self._diagnostics:
                return self._diagnostics[target]
            try:
                await asyncio.wait_for(event.wait(), self.diagnostics_timeout)
            finally:
                self._diagnostic_events.pop(target, None)
            return self._diagnostics.get(target, [])
        except TimeoutError:
            return []

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
