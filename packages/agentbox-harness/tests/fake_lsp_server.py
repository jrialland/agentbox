import json
import sys
import time


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
    return json.loads(sys.stdin.buffer.read(length))  # ty: ignore[invalid-argument-type]


def send(message):
    data = json.dumps(message).encode()
    sys.stdout.buffer.write(f"Content-Length: {len(data)}\r\n\r\n".encode() + data)
    sys.stdout.buffer.flush()


def main():
    push = "--push" in sys.argv or "--server-status" in sys.argv
    server_status = "--server-status" in sys.argv
    no_response = "--no-response" in sys.argv
    error = "--error" in sys.argv
    stale = "--stale" in sys.argv
    busy = "--busy" in sys.argv
    busy_then_quiet = "--busy-then-quiet" in sys.argv
    status_enabled = False

    def send_status(quiescent):
        send(
            {
                "jsonrpc": "2.0",
                "method": "experimental/serverStatus",
                "params": {"health": "ok", "quiescent": quiescent},
            }
        )

    def publish(uri, diagnostics):
        send(
            {
                "jsonrpc": "2.0",
                "method": "textDocument/publishDiagnostics",
                "params": {"uri": uri, "diagnostics": diagnostics},
            }
        )

    error_diagnostic = {
        "range": {"start": {"line": 0, "character": 0}},
        "severity": 1,
        "message": "fake error",
        "source": "fake",
    }

    while True:
        message = read_message()
        if message is None:
            break
        method = message.get("method")
        if method == "initialize":
            capability = (
                message.get("params", {})
                .get("capabilities", {})
                .get("experimental", {})
                .get("serverStatusNotification")
            )
            status_enabled = bool(server_status and capability)
            send(
                {
                    "jsonrpc": "2.0",
                    "id": message["id"],
                    "result": {
                        "capabilities": {} if push else {"diagnosticProvider": {}}
                    },
                }
            )
            if status_enabled:
                send_status(True)
        elif method == "textDocument/didOpen":
            if push and not server_status:
                publish(
                    message["params"]["textDocument"]["uri"],
                    [error_diagnostic],
                )
        elif method == "textDocument/didSave":
            if not status_enabled:
                continue
            uri = message["params"]["textDocument"]["uri"]
            if not stale:
                send_status(False)
            if busy:
                publish(uri, [error_diagnostic])
                continue
            if busy_then_quiet:
                time.sleep(0.2)
                send_status(True)
                continue
            if error:
                publish(uri, [error_diagnostic])
            else:
                publish(uri, [])
            if not stale:
                send_status(True)
        elif method == "textDocument/diagnostic":
            if no_response:
                continue
            send(
                {
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
                }
            )
        elif method == "shutdown":
            send({"jsonrpc": "2.0", "id": message["id"], "result": None})
        elif method == "exit":
            break


if __name__ == "__main__":
    main()
