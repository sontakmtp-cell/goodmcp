"""Argon2id for new hashes; upgrade legacy G1 scrypt only after a valid login."""
import base64
import hashlib
import hmac
from argon2 import PasswordHasher, Type
from argon2.exceptions import VerificationError, InvalidHashError

hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=1, type=Type.ID)


def password_hash(value):
    return hasher.hash(value)


def verify_password(encoded, value):
    if encoded.startswith("$argon2id$"):
        try: return hasher.verify(encoded, value)
        except (VerificationError, InvalidHashError): return False
    if encoded.startswith("scrypt$16384$8$1$"):
        try:
            _, _, _, _, salt, expected = encoded.split("$")
            digest = hashlib.scrypt(value.encode(), salt=base64.b64decode(salt, validate=True), n=16384, r=8, p=1)
            return hmac.compare_digest(digest, base64.b64decode(expected, validate=True))
        except (ValueError, TypeError): return False
    return False
