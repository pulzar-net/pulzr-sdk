"""The assistant (threads you talk to) and background agents (that run alone).

A message or an approval answers as a stream of typed events, one per SSE
event the server sends. The run belongs to the server, not the connection:
closing the stream early does not stop it, `cancel` does.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, Generator, Iterable, List, Optional, Union, cast

import httpx

from .._client import compact, path
from .._sse import SSEDecoder
from ..types import Agent, Approval, Decision, Finding, Run, Thread
from . import Resource


@dataclass(frozen=True)
class RunEvent:
    """First event: the run exists."""

    run_id: str
    thread_id: Optional[str]
    status: str
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)
    type: str = field(default='run', init=False)


@dataclass(frozen=True)
class TextEvent:
    """Assistant text, markdown, streamed in pieces. Text after a tool result
    starts a new turn."""

    delta: str
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)
    type: str = field(default='text', init=False)


@dataclass(frozen=True)
class ThinkingEvent:
    delta: str
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)
    type: str = field(default='thinking', init=False)


@dataclass(frozen=True)
class ToolCallEvent:
    """`tool_class` is read, write or destructive."""

    id: str
    name: str
    input: Dict[str, Any]
    tool_class: str
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)
    type: str = field(default='tool_call', init=False)


@dataclass(frozen=True)
class ToolResultEvent:
    id: str
    name: str
    is_error: bool
    summary: str
    truncated: bool
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)
    type: str = field(default='tool_result', init=False)


@dataclass(frozen=True)
class ApprovalRequiredEvent:
    """The run is paused. Answer every approval in one `approve()` call; a
    destructive one approved must carry `confirm` equal to its `confirm`."""

    run_id: str
    approvals: List[Approval]
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)
    type: str = field(default='approval_required', init=False)


@dataclass(frozen=True)
class UsageEvent:
    """Run totals so far, not a delta."""

    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)
    type: str = field(default='usage', init=False)


@dataclass(frozen=True)
class DoneEvent:
    """Last event. `status` is the run's: completed, awaiting_approval,
    failed or cancelled."""

    run_id: str
    status: str
    stop_reason: Optional[str]
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)
    type: str = field(default='done', init=False)


@dataclass(frozen=True)
class ErrorEvent:
    error: str
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)
    type: str = field(default='error', init=False)


@dataclass(frozen=True)
class UnknownEvent:
    """An event name newer than this SDK."""

    type: str
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)


AgentEvent = Union[RunEvent, TextEvent, ThinkingEvent, ToolCallEvent, ToolResultEvent,
                   ApprovalRequiredEvent, UsageEvent, DoneEvent, ErrorEvent, UnknownEvent]


def parse_event(name: str, data: Dict[str, Any]) -> AgentEvent:
    d = data
    if name == 'run':
        return RunEvent(d.get('runId', ''), d.get('threadId'), d.get('status', ''), raw=d)
    if name == 'text':
        return TextEvent(d.get('delta', ''), raw=d)
    if name == 'thinking':
        return ThinkingEvent(d.get('delta', ''), raw=d)
    if name == 'tool_call':
        return ToolCallEvent(d.get('id', ''), d.get('name', ''), d.get('input') or {},
                             d.get('class', ''), raw=d)
    if name == 'tool_result':
        return ToolResultEvent(d.get('id', ''), d.get('name', ''), bool(d.get('isError')),
                               d.get('summary') or '', bool(d.get('truncated')), raw=d)
    if name == 'approval_required':
        return ApprovalRequiredEvent(d.get('runId', ''), d.get('approvals') or [], raw=d)
    if name == 'usage':
        return UsageEvent(d.get('inputTokens', 0), d.get('outputTokens', 0),
                          d.get('cacheReadTokens', 0), d.get('cacheWriteTokens', 0), raw=d)
    if name == 'done':
        return DoneEvent(d.get('runId', ''), d.get('status', ''), d.get('stopReason'), raw=d)
    if name == 'error':
        return ErrorEvent(d.get('error') or 'The run failed', raw=d)
    return UnknownEvent(name, raw=d)


class RunStream:
    """The events of one run, as they happen. Iterate it; close it (or use
    `with`) to stop listening. `text` is the assistant text so far."""

    def __init__(self, response: httpx.Response) -> None:
        self._response = response
        self._iterator = self._events()
        self.run_id: Optional[str] = None
        self.text = ''

    def __iter__(self) -> 'RunStream':
        return self

    def __next__(self) -> AgentEvent:
        return next(self._iterator)

    def __enter__(self) -> 'RunStream':
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def close(self) -> None:
        self._iterator.close()
        self._response.close()

    def until_done(self) -> Optional[DoneEvent]:
        """Read to the end; the `done` event, if one came."""
        done = None
        for event in self:
            if isinstance(event, DoneEvent):
                done = event
        return done

    def _events(self) -> Generator[AgentEvent, None, None]:
        try:
            for sse in SSEDecoder().iter_events(self._response.iter_lines()):
                try:
                    data = json.loads(sse.data)
                except ValueError:
                    data = {'data': sse.data}
                event = parse_event(sse.event, data if isinstance(data, dict) else {'data': data})
                if isinstance(event, RunEvent):
                    self.run_id = event.run_id
                elif isinstance(event, TextEvent):
                    self.text += event.delta
                yield event
                if isinstance(event, DoneEvent):
                    return
        finally:
            self._response.close()


class Threads(Resource):
    _BASE = '/api/v1/agent/threads'

    def list(self) -> List[Thread]:
        """Your conversations, newest first."""
        return cast(List[Thread], self._client.request('GET', self._BASE)['result'])

    def create(self, title: Optional[str] = None) -> Thread:
        return cast(Thread, self._client.request('POST', self._BASE, json=compact(title=title)))

    def get(self, thread_id: str) -> Thread:
        """With `messages`, `runs` and `pending` (the run awaiting approval,
        if any)."""
        return cast(Thread, self._client.request('GET', path(self._BASE, thread_id)))

    def delete(self, thread_id: str) -> None:
        self._client.request('DELETE', path(self._BASE, thread_id))


class Findings(Resource):
    _BASE = '/api/v1/agents/findings'

    def list(self, *, status: Optional[str] = None, severity: Optional[str] = None,
             agent: Optional[str] = None) -> List[Finding]:
        return cast(List[Finding], self._client.request(
            'GET', self._BASE,
            params={'status': status, 'severity': severity, 'agent': agent})['result'])

    def update(self, finding_id: str, status: str) -> Finding:
        """`status` is open, acknowledged or resolved."""
        return cast(Finding, self._client.request('POST', path(self._BASE, finding_id),
                                                  json={'status': status}))


class Agents(Resource):
    _BASE = '/api/v1/agents'

    def __init__(self, client: Any) -> None:
        super().__init__(client)
        self.threads = Threads(client)
        self.findings = Findings(client)

    # -- the assistant -------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        """`{configured, model}`."""
        return self._client.request('GET', '/api/v1/agent/status')

    def send(self, thread_id: str, text: str, *, page_context: Optional[Dict[str, Any]] = None,
             auto_approve_writes: bool = False, effort: Optional[str] = None) -> RunStream:
        """Say something in a thread; the reply streams back. Raises
        ConflictError when a run in the thread is still going. Sending while
        a run awaits approval declines its pending actions."""
        body = compact(text=text, pageContext=page_context, effort=effort,
                       autoApproveWrites=True if auto_approve_writes else None)
        return self._stream(path('/api/v1/agent/threads', thread_id, 'messages'), body)

    def approve(self, run_id: str, decisions: Iterable[Decision]) -> RunStream:
        """Decide every pending approval of a run, which then resumes:
        `[{'toolUseId': ..., 'approve': True, 'confirm': ...}]`."""
        return self._stream(path('/api/v1/agent/runs', run_id, 'approvals'),
                            {'decisions': list(decisions)})

    def cancel(self, run_id: str) -> Run:
        return cast(Run, self._client.request('POST', path('/api/v1/agent/runs', run_id, 'cancel')))

    def _stream(self, url: str, body: Dict[str, Any]) -> RunStream:
        # Opened here rather than on first iteration, so a refusal (409, 403)
        # raises at the call that caused it.
        response = self._client.send('POST', url, json=body, stream=True,
                                     headers={'Accept': 'text/event-stream'})
        return RunStream(response)

    # -- background agents ---------------------------------------------------

    def templates(self) -> Dict[str, Any]:
        """`{result: templates, eventTypes, scopes}`."""
        return self._client.request('GET', f'{self._BASE}/templates')

    def list(self) -> List[Agent]:
        return cast(List[Agent], self._client.request('GET', self._BASE)['result'])

    def create(self, name: Optional[str] = None, *, template: Optional[str] = None,
               instructions: Optional[str] = None, triggers: Optional[Dict[str, Any]] = None,
               autonomy: Optional[str] = None, scopes: Optional[List[str]] = None,
               effort: Optional[str] = None, enabled: Optional[bool] = None) -> Agent:
        """Org admin. A `template` fills whatever is not given. `autonomy`:
        observe (reads only), propose (changes wait for approval), act
        (changes run; deletions still wait)."""
        body = compact(name=name, template=template, instructions=instructions,
                       triggers=triggers, autonomy=autonomy, scopes=scopes, effort=effort,
                       enabled=enabled)
        return cast(Agent, self._client.request('POST', self._BASE, json=body))

    def get(self, agent_id: str) -> Agent:
        return cast(Agent, self._client.request('GET', path(self._BASE, agent_id)))

    def update(self, agent_id: str, *, name: Optional[str] = None,
               instructions: Optional[str] = None, triggers: Optional[Dict[str, Any]] = None,
               autonomy: Optional[str] = None, scopes: Optional[List[str]] = None,
               effort: Optional[str] = None, enabled: Optional[bool] = None) -> Agent:
        """Org admin. Only the arguments given change."""
        body = compact(name=name, instructions=instructions, triggers=triggers,
                       autonomy=autonomy, scopes=scopes, effort=effort, enabled=enabled)
        return cast(Agent, self._client.request('PUT', path(self._BASE, agent_id), json=body))

    def delete(self, agent_id: str) -> None:
        """Org admin. Revokes the agent's key and cancels its queued runs."""
        self._client.request('DELETE', path(self._BASE, agent_id))

    def run(self, agent_id: str) -> Run:
        """Org admin. Queue a run now; it comes back `queued`. ConflictError
        when one is already waiting to start; RateLimitError once the org's
        daily token budget is spent (see the agent's `held`). Not retried."""
        return cast(Run, self._client.request('POST', path(self._BASE, agent_id, 'run')))

    def runs(self, agent_id: str) -> List[Run]:
        """The agent's 50 most recent runs."""
        return cast(List[Run], self._client.request(
            'GET', path(self._BASE, agent_id, 'runs'))['result'])

    def get_run(self, run_id: str) -> Dict[str, Any]:
        """Org admin. `{run, messages, approvals}` for a background run;
        members see runs only in `runs()`."""
        return self._client.request('GET', path(self._BASE, 'runs', run_id))
