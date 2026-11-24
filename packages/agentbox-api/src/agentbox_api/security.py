"""Password, JWT, and API-key helpers.

Passwords are hashed with bcrypt; JWTs are signed with the configured algorithm
(HS256 by default) and carry the user id and an expiry; API keys are hashed with
SHA-256 for storage. These functions perform no I/O and enforce no policy beyond
their arguments—callers are responsible for choosing a strong secret and sane
token lifetimes.
"""

import hashlib
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt.

    Args:
        password: Plaintext password supplied by the user.

    Returns:
        A salted bcrypt hash suitable for storage and
        :func:`verify_password`.
    """
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    """Check a plaintext password against a stored bcrypt hash.

    Args:
        password: Plaintext password to check.
        hashed: Bcrypt hash previously produced by :func:`hash_password`.

    Returns:
        ``True`` when the password matches, otherwise ``False``. A malformed
        hash raises ``ValueError`` from bcrypt.
    """
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_jwt(user_id: str, secret: str, algorithm: str, expiry_seconds: int) -> str:
    """Sign a JWT for a user with an expiry.

    Args:
        user_id: Value stored in the ``sub`` claim; the user is looked up by it.
        secret: HMAC signing secret. Must be long enough for the algorithm;
            :class:`agentbox_api.config.Settings` enforces at least 32 chars.
        algorithm: JWT signing algorithm, e.g. ``HS256``.
        expiry_seconds: Lifetime in seconds; the token expires that long after
            creation.

    Returns:
        The encoded token string.
    """
    # Expiry is absolute UTC so verification does not depend on local time.
    payload = {
        "sub": user_id,
        "exp": datetime.now(UTC) + timedelta(seconds=expiry_seconds),
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


def decode_jwt(token: str, secret: str, algorithm: str) -> dict:
    """Verify a JWT's signature and expiry and return its claims.

    Args:
        token: Encoded token string.
        secret: HMAC verification secret matching the signing secret.
        algorithm: Expected signing algorithm; only this algorithm is accepted.

    Returns:
        The decoded claim mapping, including ``sub`` and ``exp``.

    Raises:
        jwt.InvalidTokenError: If the signature, expiry, or format is invalid.
            Callers such as the authentication backend treat this as an
            authentication failure.
    """
    return jwt.decode(token, secret, algorithms=[algorithm])


def hash_api_key(raw: str) -> str:
    """Hash a raw API key for storage or lookup.

    Args:
        raw: The raw API-key string presented by a client.

    Returns:
        The lowercase hex SHA-256 digest. Hashing keeps raw keys out of the
        database, so only the digest is compared during authentication.
    """
    return hashlib.sha256(raw.encode()).hexdigest()
