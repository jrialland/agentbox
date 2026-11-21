import asyncio

from agentbox_harness.lsp.quiescence import ServerStatusTracker


def test_client_capabilities():
    tracker = ServerStatusTracker()
    assert tracker.client_capabilities() == {
        "experimental": {"serverStatusNotification": True}
    }


def test_handle_updates_state_and_busy_counter():
    tracker = ServerStatusTracker()
    tracker.handle({"health": "ok", "quiescent": False})
    assert tracker.health == "ok"
    assert tracker.quiescent is False
    assert tracker.seq == 1
    assert tracker.busy_seq == 1
    tracker.handle({"health": "ok", "quiescent": True})
    assert tracker.quiescent is True
    assert tracker.seq == 2
    assert tracker.busy_seq == 1


def test_handle_records_health_and_message_without_raising():
    tracker = ServerStatusTracker()
    tracker.handle({"health": "warning", "quiescent": True, "message": "loading"})
    assert tracker.health == "warning"
    assert tracker.quiescent is True


def test_handle_wakes_waiters():
    tracker = ServerStatusTracker()
    event = asyncio.Event()
    tracker.waiters.add(event)
    tracker.handle({"health": "ok", "quiescent": True})
    assert event.is_set()
