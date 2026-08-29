"""
auth.py — minimal, dependency-free account handling.

Passwords are never stored in plain text. We use PBKDF2-HMAC-SHA256 (from the
standard library) with a random per-user salt and a high iteration count.

This is solid for a small personal/friends app. If this ever grows into
something bigger or public, move to a managed auth provider (e.g. Supabase Auth,
Auth0) rather than hand-rolled auth — noted in the README.
"""

import hashlib
import hmac
import os

import db

_ITERATIONS = 200_000


def _hash_password(password: str, salt_hex: str) -> str:
    salt = bytes.fromhex(salt_hex)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return dk.hex()


def register(username: str, password: str):
    """Returns (ok, message). Fails if username taken or inputs invalid."""
    username = (username or "").strip()
    if len(username) < 3:
        return False, "Username must be at least 3 characters."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."
    if db.get_user(username):
        return False, "That username is already taken."
    salt_hex = os.urandom(16).hex()
    pw_hash = _hash_password(password, salt_hex)
    db.create_user(username, salt_hex, pw_hash)
    return True, "Account created — you can log in now."


def login(username: str, password: str):
    """Returns (user_id, message) on success, or (None, message) on failure."""
    username = (username or "").strip()
    user = db.get_user(username)
    if not user:
        return None, "No account with that username."
    candidate = _hash_password(password, user["pw_salt"])
    # constant-time comparison
    if hmac.compare_digest(candidate, user["pw_hash"]):
        return user["id"], "Logged in."
    return None, "Incorrect password."
