"""Offline licence keys (the desktop's license.rs, license_gate.rs, and the
licence messages in error.rs).

A key is Crockford base32 (dashes and case ignored) of:
  2 bytes payload length (big-endian) | JSON payload | 64-byte Ed25519 signature
signed by RxLabel's private key; the public key is built in. The payload
names the app, the facility, the expiry (`exp`, Unix seconds) and the
built-in admin account's password (`secret`). Web and desktop accept the same
keys (app "com.rxlabel.desktop").

Checked against the Rust code itself: web/tests/fixtures/license_cases.json
comes from tools/license_reference.
"""

from __future__ import annotations

import base64
import json
import time
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .errors import AppError

APP_ID = "com.rxlabel.desktop"
PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAkZ3yOcAJgkypUQMA1o0ZIxp+9/L1HEt5XzDLUqXt8Z0=
-----END PUBLIC KEY-----"""
SIGNATURE_LEN = 64

READ_ONLY_MESSAGE = ("The license has expired, so RxLabel is read-only. "
                     "Renew the license to print or make changes.")

# Rust error code -> (app error code, message for people) (error.rs)
MESSAGES = {
    "MALFORMED_KEY": ("LICENSE_INVALID", "This license key is not valid. Check it was copied completely."),
    "MALFORMED_JSON": ("LICENSE_INVALID", "This license key is not valid. Check it was copied completely."),
    "INVALID_SIGNATURE": ("LICENSE_INVALID", "This license key is not genuine."),
    "WRONG_APP": ("LICENSE_INVALID", "This license key is for a different application."),
    "EXPIRED": ("LICENSE_EXPIRED", "This license has expired."),
    "NO_EXPIRY": ("LICENSE_INVALID", "This license key has no expiry date. Contact support."),
}

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_DECODE = {c: i for i, c in enumerate(_CROCKFORD)}
_DECODE.update({"O": 0, "I": 1, "L": 1})  # look-alikes, as Crockford base32 allows
_SPKI_ED25519_PREFIX = bytes.fromhex("302a300506032b6570032100")


class LicenseError(AppError):
    """A refused key. `reason` is the desktop's code (MALFORMED_KEY, EXPIRED, ...)."""

    def __init__(self, reason: str):
        code, message = MESSAGES.get(reason, ("LICENSE_INVALID", "This license key is not valid."))
        super().__init__(code, message)
        self.reason = reason


def crockford_decode(text: str) -> bytes | None:
    """Bytes for upper-case Crockford base32 without padding; None for a bad character.
    Trailing bits that don't make a whole byte are dropped (as the base32 crate)."""
    out, buffer, bits = bytearray(), 0, 0
    for ch in text:
        value = _DECODE.get(ch)
        if value is None:
            return None
        buffer = (buffer << 5) | value
        bits += 5
        if bits >= 8:
            bits -= 8
            out.append((buffer >> bits) & 0xFF)
    return bytes(out)


def public_key_from_pem(pem: str) -> bytes:
    """The raw 32-byte Ed25519 key in a PEM SubjectPublicKeyInfo."""
    body = "".join(line for line in pem.strip().splitlines() if "-----" not in line)
    der = base64.b64decode(body)
    if not der.startswith(_SPKI_ED25519_PREFIX) or len(der) != len(_SPKI_ED25519_PREFIX) + 32:
        raise ValueError("not an Ed25519 public key")
    return der[len(_SPKI_ED25519_PREFIX):]


PUBLIC_KEY = public_key_from_pem(PUBLIC_KEY_PEM)


def verify_with(license_key: str, public_key: bytes, now: int) -> dict[str, Any]:
    """The payload of a valid key at time `now`, or LicenseError (verify_with)."""
    data = crockford_decode(license_key.replace("-", "").upper())
    if data is None or len(data) < 66:
        raise LicenseError("MALFORMED_KEY")
    payload_len = int.from_bytes(data[:2], "big")
    payload_end = 2 + payload_len
    if payload_end + SIGNATURE_LEN != len(data):
        raise LicenseError("MALFORMED_KEY")
    payload_bytes, signature = data[2:payload_end], data[payload_end:]
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, payload_bytes)
    except InvalidSignature:
        raise LicenseError("INVALID_SIGNATURE") from None
    try:
        payload = json.loads(payload_bytes)
        for field in ("app", "facility_name", "facility_address", "facility_contact"):
            if not isinstance(payload[field], str):
                raise TypeError(field)
        for field in ("exp", "secret"):
            payload.setdefault(field, None)
        if payload["exp"] is not None and (isinstance(payload["exp"], bool) or not isinstance(payload["exp"], int)
                                           or payload["exp"] < 0):
            raise TypeError("exp")
        if payload["secret"] is not None and not isinstance(payload["secret"], str):
            raise TypeError("secret")
    except (ValueError, KeyError, TypeError):
        raise LicenseError("MALFORMED_JSON") from None
    if payload["app"] != APP_ID:
        raise LicenseError("WRONG_APP")
    if payload["exp"] is None:
        raise LicenseError("NO_EXPIRY")
    if now >= payload["exp"]:
        raise LicenseError("EXPIRED")
    return payload


def verify(license_key: str, now: int | None = None, public_key: bytes = PUBLIC_KEY) -> dict[str, Any]:
    """Check a key as typed or pasted (surrounding spaces ignored)."""
    return verify_with(license_key.strip(), public_key, int(time.time()) if now is None else now)


def is_expired(expires_at: int | None, now: float) -> bool:
    """No licence, or no expiry date, counts as expired (license_gate::is_expired)."""
    return expires_at is None or now >= expires_at


def summary(payload: dict[str, Any]) -> dict[str, Any]:
    """What the setup and renewal screens show (LicenseResult)."""
    return {"facility_name": payload["facility_name"], "facility_address": payload["facility_address"],
            "facility_contact": payload["facility_contact"], "valid": True, "expires_at": payload["exp"]}
