import pytest

from agentbox_api.media import MediaStore


def test_save_read_and_delete(tmp_path):
    store = MediaStore(tmp_path)
    stored = store.save(
        b"hello", category="attachments", media_type="text/plain", suffix=".txt"
    )

    assert stored.size_bytes == 5
    assert len(stored.sha256) == 64
    assert stored.storage_path.startswith("attachments/")
    assert store.read(stored.storage_path) == b"hello"
    assert store.path(stored.storage_path).read_bytes() == b"hello"

    store.delete(stored.storage_path)
    assert not store.exists(stored.storage_path)


def test_delete_missing_is_tolerated(tmp_path):
    store = MediaStore(tmp_path)
    store.delete("attachments/missing.txt")


def test_rejects_path_traversal(tmp_path):
    store = MediaStore(tmp_path)
    with pytest.raises(ValueError):
        store.path("../outside.txt")
    with pytest.raises(ValueError):
        store.path("C:/absolute.txt")


def test_rejects_bad_category(tmp_path):
    store = MediaStore(tmp_path)
    with pytest.raises(ValueError):
        store.save(b"x", category="../bad", media_type="text/plain")
    with pytest.raises(ValueError):
        store.save(b"x", category="ok", media_type="text/plain", suffix="/bad")
