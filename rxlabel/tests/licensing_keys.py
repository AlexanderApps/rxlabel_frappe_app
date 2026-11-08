"""Test licence keys in the real format, signed with the same fixed seed as
tools/license_reference (never RxLabel's real private key)."""

import json
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: F401 (re-exported for tests)

from rxlabel_core import license

TEST_SIGNER = Ed25519PrivateKey.from_private_bytes(bytes([1] * 32))
TEST_PUBLIC_KEY = TEST_SIGNER.public_key().public_bytes_raw()
_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def crockford_encode(data: bytes) -> str:
    bits, value, out = 0, 0, []
    for byte in data:
        value = (value << 8) | byte
        bits += 8
        while bits >= 5:
            bits -= 5
            out.append(_ALPHABET[(value >> bits) & 31])
    if bits:
        out.append(_ALPHABET[(value << (5 - bits)) & 31])
    return "".join(out)


def make_license(days: float = 365, app: str = license.APP_ID, secret: str | None = "admin-secret-1",
                 facility: str = "Osu Pharmacy", signer: Ed25519PrivateKey = TEST_SIGNER) -> str:
    payload = {"app": app, "exp": int(time.time() + days * 86400), "facility_name": facility,
               "facility_address": "Osu, Accra", "facility_contact": "024 400 0000"}
    if secret is not None:
        payload["secret"] = secret
    body = json.dumps(payload).encode()
    return crockford_encode(len(body).to_bytes(2, "big") + body + signer.sign(body))
