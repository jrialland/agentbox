import hashlib
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_jwt(user_id: str, secret: str, algorithm: str, expiry_seconds: int) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(seconds=expiry_seconds),
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


def decode_jwt(token: str, secret: str, algorithm: str) -> dict:
    return jwt.decode(token, secret, algorithms=[algorithm])


def hash_api_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()
