class RunRegistry:
    def __init__(self) -> None:
        self._runs: dict[str, object] = {}

    def register(self, session_id: str, run: object) -> None:
        self._runs[session_id] = run

    def cancel(self, session_id: str) -> bool:
        run = self._runs.get(session_id)
        if run is None:
            return False
        run.cancel()
        return True

    def finish(self, session_id: str) -> None:
        self._runs.pop(session_id, None)
