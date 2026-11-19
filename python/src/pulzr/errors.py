"""Errors, one class per thing a caller does differently about it.

net-api answers a failure with `{"error": "...", "details"?: [...]}` and a
status. The status picks the class; the body is kept whole on `body` because
some routes add fields (a quota refusal names the resource and its limit).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Type

import httpx

__all__ = [
    'PulzrError',
    'APIConnectionError',
    'AuthenticationError',
    'PermissionDeniedError',
    'NotFoundError',
    'ConflictError',
    'ValidationError',
    'RateLimitError',
    'ServerError',
    'SignatureVerificationError',
]


class PulzrError(Exception):
    """Any failure the API reported, or a request that never got an answer.
    `retry_after` is the server's `Retry-After` in seconds, when it sent one
    (429, and a 503 during a deploy)."""

    retry_after: Optional[float] = None

    def __init__(self, status: Optional[int], message: str,
                 details: Optional[List[Any]] = None, body: Any = None) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.details = details or []
        self.body = body

    def __str__(self) -> str:
        return f'{self.status} {self.message}' if self.status else self.message


class APIConnectionError(PulzrError):
    """No response: DNS, refused connection, TLS, or a timeout."""

    def __init__(self, message: str) -> None:
        super().__init__(None, message)


class AuthenticationError(PulzrError):
    """401. The key is wrong, revoked or expired."""


class PermissionDeniedError(PulzrError):
    """403. The key lacks the scope, or the route needs an org admin."""


class NotFoundError(PulzrError):
    """404. Also what another org's resource looks like from here."""


class ConflictError(PulzrError):
    """409. A state conflict (a run already going, a session not ready) or a
    quota. A quota refusal sets `resource` and `limit`; anything else leaves
    both None."""

    def __init__(self, status: Optional[int], message: str,
                 details: Optional[List[Any]] = None, body: Any = None) -> None:
        super().__init__(status, message, details, body)
        extra = body if isinstance(body, dict) else {}
        self.resource: Optional[str] = extra.get('resource')
        self.limit: Optional[int] = extra.get('limit')


class ValidationError(PulzrError):
    """400 or 422. `details` lists every problem when the route found several."""


class RateLimitError(PulzrError):
    """429."""


class ServerError(PulzrError):
    """5xx, after any retries."""


class SignatureVerificationError(ValueError):
    """A webhook delivery whose `Parkeze-Signature` does not verify."""


_BY_STATUS: Dict[int, Type[PulzrError]] = {
    400: ValidationError,
    401: AuthenticationError,
    403: PermissionDeniedError,
    404: NotFoundError,
    409: ConflictError,
    422: ValidationError,
    429: RateLimitError,
}


def from_response(response: httpx.Response) -> PulzrError:
    """The exception for a failed response. The body must already be read."""
    try:
        body: Any = response.json()
    except ValueError:
        body = response.text or None
    message = None
    details = None
    if isinstance(body, dict):
        # `message` is for the few routes that pass an LNS error through
        # unchanged (codec deploy); everything of ours says `error`.
        message = body.get('error') or body.get('message')
        details = body.get('details') if isinstance(body.get('details'), list) else None
    elif isinstance(body, str):
        message = body.strip()[:500]
    message = str(message or response.reason_phrase or 'Request failed')

    status = response.status_code
    cls = _BY_STATUS.get(status) or (ServerError if status >= 500 else PulzrError)
    error = cls(status, message, details, body)
    error.retry_after = retry_after_seconds(response.headers.get('Retry-After'))
    return error


def retry_after_seconds(value: Optional[str]) -> Optional[float]:
    """`Retry-After` as seconds; it may be a number or an HTTP date."""
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    from datetime import datetime, timezone
    from email.utils import parsedate_to_datetime
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())
