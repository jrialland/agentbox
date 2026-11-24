"""In-process registry of the active run owned by each session.

A :class:`RunRegistry` maps a session id to its current cancellable run so that
cancellation requests can reach the run from elsewhere in the process. Ownership
is one run per session: registering a new run replaces any previous entry, and
finishing or cancelling means the caller is responsible for removing it.
"""

from typing import Protocol


class Cancellable(Protocol):
    """A run handle that can be asked to cancel.

    Implementations should make cancellation idempotent; callers may request it
    more than once, for example when a session finishes at the same time a
    cancellation arrives.
    """

    def cancel(self) -> None:  # noqa: D102
        ...


class RunRegistry:
    """Track the active run for each session and propagate cancellation.

    Each session owns at most one live run. Cancellation is routed to the run
    stored for that session; when the run is already gone, the request is a
    no-op reported as ``False`` so callers can distinguish a miss.
    """

    def __init__(self) -> None:
        """Create an empty registry with no active runs."""
        self._runs: dict[str, Cancellable] = {}

    def register(self, session_id: str, run: Cancellable) -> None:
        """Record ``run`` as the active run for ``session_id``.

        Any run previously registered for the session is replaced without being
        cancelled; callers replace entries only after the prior run has ended.

        Args:
            session_id: Session that owns the run.
            run: Cancellable handle for the running turn.
        """
        self._runs[session_id] = run

    def cancel(self, session_id: str) -> bool:
        """Cancel the active run for ``session_id``, if any.

        Args:
            session_id: Session whose current run should be cancelled.

        Returns:
            ``True`` if a run was found and asked to cancel, ``False`` if the
            session had no registered run.
        """
        run = self._runs.get(session_id)
        if run is None:
            return False
        # Cancellation targets the run owned by this session; ownership is not
        # transferred or inferred, so an unknown session is simply a no-op.
        run.cancel()
        return True

    def finish(self, session_id: str) -> None:
        """Forget the run for ``session_id`` once it has ended.

        Args:
            session_id: Session whose run has completed or been cancelled.
        """
        self._runs.pop(session_id, None)
