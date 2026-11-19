import io

import pytest
from PIL import Image

from agentbox_api.avatars import generate_default_avatar, normalize_upload


def test_default_avatar_is_deterministic_png():
    a = generate_default_avatar("agent-1")
    b = generate_default_avatar("agent-1")
    assert a[:8] == b"\x89PNG\r\n\x1a\n"
    assert a == b


def test_normalize_upload_square_png():
    img = Image.new("RGB", (400, 200), "red")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    out = normalize_upload(buf.getvalue())
    with Image.open(io.BytesIO(out)) as im:
        assert im.format == "PNG"
        assert im.size == (300, 300)


def test_normalize_rejects_garbage():
    with pytest.raises(ValueError):
        normalize_upload(b"not an image")
