from agentbox_api.security import (
    create_jwt,
    decode_jwt,
    hash_api_key,
    hash_password,
    verify_password,
)


def test_password_roundtrip():
    hashed = hash_password("s3cret")
    assert verify_password("s3cret", hashed)
    assert not verify_password("wrong", hashed)


def test_jwt_roundtrip():
    secret = "s" * 32
    token = create_jwt("u1", secret, "HS256", 3600)
    payload = decode_jwt(token, secret, "HS256")
    assert payload["sub"] == "u1"


def test_api_key_hash_is_deterministic():
    assert hash_api_key("abc") == hash_api_key("abc")
    assert hash_api_key("abc") != hash_api_key("abd")
