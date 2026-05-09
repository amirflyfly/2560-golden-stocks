"""Password hashing.

Use PBKDF2-HMAC-SHA256 from stdlib (no external deps).
Format: pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>
"""

import hashlib
import os


DEFAULT_ITERS = 200_000


def hash_password(password: str, *, iterations: int = DEFAULT_ITERS) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_hex, hash_hex = stored.split('$', 3)
        if algo != 'pbkdf2_sha256':
            return False
        iterations = int(iters)
        salt = bytes.fromhex(salt_hex)
        dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
        return dk.hex() == hash_hex
    except Exception:
        return False
