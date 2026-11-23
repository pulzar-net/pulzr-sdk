"""Verifying a webhook delivery. Mirrors `verify` in the server's
shared/events.py, and is tested against vectors that code generated
(sdk/fixtures/webhook-signatures.json), so the two cannot drift apart unseen.

    Parkeze-Signature: t=<unix seconds>,v1=<hex HMAC-SHA256 of "<t>.<body>">

Verify the raw request bytes, before any JSON parsing: re-serialising the
parsed body changes its bytes and the MAC with them.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any, Dict, Iterable, List, Optional, Union

from .errors import SignatureVerificationError

SIGNATURE_HEADER = 'Parkeze-Signature'
EVENT_ID_HEADER = 'Parkeze-Event-Id'
EVENT_TYPE_HEADER = 'Parkeze-Event-Type'
TOLERANCE_SECONDS = 300

Secret = Union[str, Iterable[str]]
Body = Union[bytes, bytearray, memoryview, str]


def _secrets(secret: Secret) -> List[str]:
    return [secret] if isinstance(secret, str) else list(secret)


def _bytes(body: Body) -> bytes:
    return body.encode('utf-8') if isinstance(body, str) else bytes(body)


def _mac(secret: str, timestamp: int, body: bytes) -> str:
    return hmac.new(secret.encode(), f'{timestamp}.'.encode() + body, hashlib.sha256).hexdigest()


def verify_signature(secret: Secret, body: Body, header: Optional[str],
                     tolerance: float = TOLERANCE_SECONDS, now: Optional[float] = None) -> bool:
    """Whether `header` is a valid signature of `body`.

    `secret` may be a list: during a rotation a receiver can hold the new and
    the old secret and accept either. Any matching `v1` passes; other schemes
    are ignored.
    """
    if not header:
        return False
    try:
        parts = dict(p.split('=', 1) for p in header.split(','))
        timestamp = int(parts['t'])
    except (ValueError, KeyError):
        return False
    now = time.time() if now is None else now
    if abs(now - timestamp) > tolerance:
        return False
    candidates = [v.encode() for k, v in (p.split('=', 1) for p in header.split(','))
                  if k == 'v1']
    payload = _bytes(body)
    # Comparing bytes, not str: compare_digest refuses non-ASCII text, and a
    # mangled header should be a False, not a TypeError in the receiver.
    return any(hmac.compare_digest(_mac(s, timestamp, payload).encode(), c)
               for s in _secrets(secret) for c in candidates)


def construct_event(secret: Secret, body: Body, header: Optional[str],
                    tolerance: float = TOLERANCE_SECONDS,
                    now: Optional[float] = None) -> Dict[str, Any]:
    """The verified event envelope, or SignatureVerificationError."""
    if not verify_signature(secret, body, header, tolerance=tolerance, now=now):
        raise SignatureVerificationError('Parkeze-Signature does not match this body')
    return json.loads(_bytes(body))


def sign(secret: Secret, body: Body, timestamp: Optional[int] = None) -> str:
    """A signature header for `body`, as the server makes one. For testing a
    receiver; production deliveries are signed by Pulzr."""
    timestamp = int(timestamp if timestamp is not None else time.time())
    payload = _bytes(body)
    return f't={timestamp},' + ','.join(f'v1={_mac(s, timestamp, payload)}'
                                         for s in _secrets(secret))


__all__ = ['verify_signature', 'construct_event', 'sign', 'SignatureVerificationError',
           'SIGNATURE_HEADER', 'EVENT_ID_HEADER', 'EVENT_TYPE_HEADER', 'TOLERANCE_SECONDS']
