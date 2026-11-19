"""A client wired to a scripted transport, and a record of what it sent."""

from __future__ import annotations

import json
from typing import Any, Callable, Iterable, List, Optional, Union

import httpx

import pulzr

Reply = Union[httpx.Response, Callable[[httpx.Request], httpx.Response], Exception]


class Scripted:
    """Answers each request with the next reply in order, and keeps the
    requests. A reply may be a response, a function of the request, or an
    exception to raise as the transport."""

    def __init__(self, replies: Iterable[Reply]) -> None:
        self.replies = list(replies)
        self.requests: List[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if not self.replies:
            raise AssertionError(f'unexpected request {request.method} {request.url}')
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        if callable(reply):
            return reply(request)
        return reply


def client(replies: Iterable[Reply], **kwargs: Any) -> 'tuple[pulzr.Client, Scripted, List[float]]':
    script = Scripted(replies)
    c = pulzr.Client(kwargs.pop('api_key', 'pzk_test'), transport=httpx.MockTransport(script),
                       base_url='https://net.test', **kwargs)
    slept: List[float] = []
    c._sleep = slept.append
    return c, script, slept


def ok(body: Any, status: int = 200, headers: Optional[dict] = None) -> httpx.Response:
    return httpx.Response(status, json=body, headers=headers)


def sse(text: str, status: int = 200) -> httpx.Response:
    return httpx.Response(status, headers={'Content-Type': 'text/event-stream'},
                          content=text.encode())


def broken_sse(text: str) -> httpx.Response:
    """A stream that sends `text` and then loses the connection."""

    def chunks():
        yield text.encode()
        raise httpx.ReadError('connection reset')

    return httpx.Response(200, headers={'Content-Type': 'text/event-stream'},
                          content=chunks())


def body_of(request: httpx.Request) -> Any:
    return json.loads(request.content)
