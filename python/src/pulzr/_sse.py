"""Server-Sent Events, decoded the way a browser's EventSource decodes them.

Three streams use it (the event log, onboarding watch, agent runs) and they
lean on different corners of the format: the log puts `retry:` and the
`ready` event in one block, the agent stream names every event, and all of
them send comment lines to keep proxies from closing an idle connection. One
decoder that follows the WHATWG rules handles all three without special cases.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Iterator, Optional


@dataclass(frozen=True)
class ServerSentEvent:
    event: str
    data: str
    id: Optional[str]


class SSEDecoder:
    """Turns lines into events. `last_event_id` and `retry` (milliseconds)
    outlive a single event, as the spec has them, so a reconnecting caller
    reads them here."""

    def __init__(self) -> None:
        self.last_event_id: Optional[str] = None
        self.retry: Optional[int] = None
        self._event = ''
        self._data: list = []

    def iter_events(self, lines: Iterable[str]) -> Iterator[ServerSentEvent]:
        for line in lines:
            event = self.feed(line)
            if event is not None:
                yield event
        # A block with no closing blank line is incomplete and is dropped,
        # as EventSource drops it: the server may have died mid-write.

    def feed(self, line: str) -> Optional[ServerSentEvent]:
        line = line.rstrip('\r\n')
        if not line:
            return self._dispatch()
        if line.startswith(':'):
            return None
        name, sep, value = line.partition(':')
        if sep and value.startswith(' '):
            value = value[1:]
        if name == 'event':
            self._event = value
        elif name == 'data':
            self._data.append(value)
        elif name == 'id':
            if '\0' not in value:
                self.last_event_id = value
        elif name == 'retry':
            if value.isdigit():
                self.retry = int(value)
        return None

    def _dispatch(self) -> Optional[ServerSentEvent]:
        event, data = self._event or 'message', self._data
        self._event, self._data = '', []
        if not data:
            return None
        return ServerSentEvent(event=event, data='\n'.join(data), id=self.last_event_id)
