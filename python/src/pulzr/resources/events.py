"""The event log: page through it, or hold a stream open on it."""

from __future__ import annotations

import json
import random
from typing import Any, Generator, Iterable, Iterator, List, Optional, Union, cast

import httpx

from .._client import path
from .._sse import SSEDecoder
from ..errors import APIConnectionError, RateLimitError, ServerError
from ..types import Envelope, EventPage, EventType
from . import Resource

Types = Union[str, Iterable[str], None]

_DEFAULT_RETRY_MS = 3000
_RECONNECT_MAX = 30.0


def _types(value: Types) -> Optional[str]:
    if value is None or isinstance(value, str):
        return value
    return ','.join(value)


class Events(Resource):
    def list(self, *, after: Optional[str] = None, before: Optional[str] = None,
             types: Types = None, subject: Optional[str] = None,
             limit: Optional[int] = None) -> EventPage:
        """One page. `after` reads forward, oldest first (no cursor: from the
        start of the log); `before` reads back, newest first (`before='now'`
        is the newest page). `next` is the cursor for the following page."""
        return cast(EventPage, self._client.request('GET', '/api/v1/events', params={
            'after': after, 'before': before, 'types': _types(types), 'subject': subject,
            'limit': limit,
        }))

    def iter(self, *, after: Optional[str] = None, before: Optional[str] = None,
             types: Types = None, subject: Optional[str] = None,
             limit: Optional[int] = None) -> Iterator[Envelope]:
        """Every event from a position, page by page, until the log is caught
        up (forward) or exhausted (backward). `limit` is the page size."""
        backward = before is not None
        cursor = before if backward else after
        while True:
            page = self.list(after=None if backward else cursor,
                             before=cursor if backward else None,
                             types=types, subject=subject, limit=limit)
            yield from page['result']
            if not page['hasMore'] or not page['next']:
                return
            cursor = page['next']

    def get(self, event_id: str) -> Envelope:
        return cast(Envelope, self._client.request('GET', path('/api/v1/events', event_id)))

    def types(self) -> List[EventType]:
        return cast(List[EventType], self._client.request('GET', '/api/v1/events/types')['result'])

    def stream(self, types: Types = None, *, subject: Optional[str] = None,
               after: Optional[str] = None, last_event_id: Optional[str] = None,
               max_reconnects: Optional[int] = None) -> 'EventStream':
        """Events as they happen, as an iterator of envelopes.

        With no position the stream starts at the end of the log. `after` or
        `last_event_id` (the same thing: a cursor) resumes exactly after it,
        backlog first. A dropped connection is reopened from the last event
        received -- or from the position the server's closing `end` names,
        since it ends every stream after an hour -- so nothing is skipped and
        nothing repeated. `stream.cursor` is that position, to persist and
        pass back as `last_event_id` after a restart. A refusal for too many open streams (429) is waited out for
        its Retry-After. `max_reconnects` bounds consecutive failed
        reconnects (None: keep trying, as a browser's EventSource does).
        """
        return EventStream(self._client, _types(types), subject, last_event_id or after,
                           max_reconnects)


class EventStream:
    """Iterator over the live event log. Close it, or use it in `with`."""

    def __init__(self, client: Any, types: Optional[str], subject: Optional[str],
                 cursor: Optional[str], max_reconnects: Optional[int]) -> None:
        self._client = client
        self._types = types
        self._subject = subject
        self.cursor: Optional[str] = cursor
        self._max_reconnects = max_reconnects
        self._retry_ms = _DEFAULT_RETRY_MS
        self._response: Optional[httpx.Response] = None
        self._closed = False
        self._iterator = self._run()

    def __iter__(self) -> 'EventStream':
        return self

    def __next__(self) -> Envelope:
        return next(self._iterator)

    def __enter__(self) -> 'EventStream':
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def close(self) -> None:
        self._closed = True
        self._iterator.close()
        if self._response is not None:
            self._response.close()

    def _open(self) -> httpx.Response:
        # The cursor rides in Last-Event-ID, which the server prefers over
        # `after`, so a reconnect cannot be sent with a stale `after` too.
        headers = {'Accept': 'text/event-stream'}
        if self.cursor:
            headers['Last-Event-ID'] = self.cursor
        return self._client.send('GET', '/api/v1/events/stream', stream=True, retries=0,
                                 params={'types': self._types, 'subject': self._subject},
                                 headers=headers)

    def _run(self) -> Generator[Envelope, None, None]:
        failures = 0
        while not self._closed:
            wait: Optional[float] = None
            try:
                self._response = self._open()
            except (ServerError, RateLimitError, APIConnectionError) as e:
                failures += 1
                if self._max_reconnects is not None and failures > self._max_reconnects:
                    raise
                wait = e.retry_after
            else:
                decoder = SSEDecoder()
                ready = False
                try:
                    for sse in decoder.iter_events(self._response.iter_lines()):
                        if sse.event == 'ready':
                            # The server's position before anything has
                            # happened: kept, so a stream that drops before
                            # its first event still resumes in place.
                            ready = True
                            failures = 0
                            self.cursor = sse.id or json.loads(sse.data).get('cursor') or self.cursor
                        elif sse.event == 'message':
                            envelope = json.loads(sse.data)
                            if sse.id:
                                self.cursor = sse.id
                            yield cast(Envelope, envelope)
                        elif sse.event == 'end':
                            # The server closes a stream after an hour (and
                            # whenever it redeploys); `end` carries the
                            # position, and the reopen resumes from it.
                            self.cursor = sse.id or self.cursor
                            break
                        elif sse.event == 'error':
                            # The server stopped its side; reopened like any
                            # other drop.
                            break
                        # Any other named event is newer than this SDK.
                except httpx.TransportError:
                    pass
                finally:
                    if decoder.retry is not None:
                        self._retry_ms = decoder.retry
                    self._response.close()
                    self._response = None
                if not ready:
                    # Accepted and hung up before `ready`: counted, or a
                    # server doing that would be reconnected to forever.
                    failures += 1
                    if self._max_reconnects is not None and failures > self._max_reconnects:
                        raise APIConnectionError('The event stream closed before it started')
            if self._closed:
                return
            self._client._sleep(self._delay(failures, wait))

    def _delay(self, failures: int, retry_after: Optional[float]) -> float:
        base = self._retry_ms / 1000
        if failures <= 1:
            delay = base
        else:
            # Past the first failure the server asked for `retry` and did not
            # come back; backing off is what keeps a thousand streams from
            # reconnecting in step when it does.
            delay = min(base * (2 ** (failures - 1)), _RECONNECT_MAX) * random.uniform(0.75, 1.0)
        return max(delay, retry_after or 0)

