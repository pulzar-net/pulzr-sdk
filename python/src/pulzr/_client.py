"""The client: one httpx connection pool, auth headers, retries, errors."""

from __future__ import annotations

import os
import random
import time
from typing import Any, Callable, Dict, Mapping, Optional, Union, cast

import httpx
from tenacity import RetryCallState, Retrying, retry_if_exception, stop_after_attempt

from ._version import __version__
from .errors import APIConnectionError, PulzrError, from_response
from .types import SqlResult

DEFAULT_BASE_URL = 'https://app.pulzr.net'


def env(name: str, environ=None) -> Optional[str]:
    """`PULZR_<X>` from the environment, or `PARKEZE_<X>`, the name before Pulzar."""
    environ = os.environ if environ is None else environ
    return environ.get(name) or environ.get('PARKEZE_' + name[len('PULZR_'):])
DEFAULT_TIMEOUT = 30.0

# A stream is quiet between events; each one the server holds open sends a
# comment at least every 20-25 s, so a minute without a byte is a dead
# connection rather than a quiet network.
STREAM_READ_TIMEOUT = 60.0

# Methods that may be sent twice without doing anything twice. A POST that
# timed out may have created the device, queued the downlink or started the
# run, and a retry would do it again; the caller decides that, not the SDK.
_IDEMPOTENT = frozenset({'GET', 'HEAD', 'PUT', 'DELETE', 'OPTIONS'})
_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
_BACKOFF_BASE = 0.5
_BACKOFF_MAX = 8.0
# A Retry-After longer than this is the server saying "not soon" (signup's is
# an hour); sleeping through it inside a library call would look like a hang.
_RETRY_AFTER_MAX = 60.0

Params = Optional[Mapping[str, Any]]


def _clean(params: Params) -> Optional[Dict[str, str]]:
    """Query parameters as net-api reads them: lists comma-joined, booleans
    lowercase, and absent values left out rather than sent empty."""
    if not params:
        return None
    out = {}
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, bool):
            value = 'true' if value else 'false'
        elif isinstance(value, (list, tuple, set, frozenset)):
            if not value:
                continue
            value = ','.join(str(v) for v in value)
        out[key] = str(value)
    return out


def decode(response: httpx.Response) -> Any:
    if response.status_code == 204 or not response.content:
        return None
    try:
        return response.json()
    except ValueError:
        return response.text


class Client:
    """A Pulzar API client.

        client = pulzr.Client(api_key='pzk_...')

    `org` is the org alias to act in; an API key belongs to one org and needs
    none, a person's token with several memberships does. `transport` is
    passed to httpx (an `httpx.MockTransport` in tests).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        org: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: Union[float, httpx.Timeout] = DEFAULT_TIMEOUT,
        max_retries: int = 2,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        api_key = api_key or env('PULZR_API_KEY')
        if not api_key:
            raise ValueError('An API key is required: pass api_key or set PULZR_API_KEY')
        self.org = org
        self.max_retries = max(0, int(max_retries))
        self._timeout = timeout if isinstance(timeout, httpx.Timeout) else httpx.Timeout(timeout)
        headers = {
            'Authorization': f'Bearer {api_key}',
            'User-Agent': f'pulzr-python/{__version__}',
            'Accept': 'application/json',
        }
        if org:
            headers['X-Active-Org'] = org
        self._http = httpx.Client(base_url=base_url.rstrip('/'), headers=headers,
                                  timeout=self._timeout, transport=transport)
        # Swapped in tests so a retry schedule is asserted, not waited out.
        self._sleep: Callable[[float], None] = time.sleep

        from .resources.agents import Agents
        from .resources.basic_station import BasicStation
        from .resources.device_types import DeviceTypes
        from .resources.devices import Devices
        from .resources.events import Events
        from .resources.firmware import Firmware
        from .resources.gateways import Gateways
        from .resources.integrations import Integrations
        from .resources.mqtt import Mqtt
        from .resources.multicast import MulticastGroups, Relays
        from .resources.onboarding import Onboarding
        from .resources.readings import Quantities, Readings
        from .resources.radio import Airtime, Coverage
        from .resources.sims import Sims
        from .resources.webhooks import Webhooks

        self.devices = Devices(self)
        self.gateways = Gateways(self)
        self.sims = Sims(self)
        self.basic_station = BasicStation(self)
        self.readings = Readings(self)
        self.quantities = Quantities(self)
        self.airtime = Airtime(self)
        self.coverage = Coverage(self)
        self.events = Events(self)
        self.webhooks = Webhooks(self)
        self.integrations = Integrations(self)
        self.onboarding = Onboarding(self)
        self.agents = Agents(self)
        self.device_types = DeviceTypes(self)
        self.mqtt = Mqtt(self)
        self.multicast_groups = MulticastGroups(self)
        self.relays = Relays(self)
        self.firmware = Firmware(self)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> 'Client':
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def sql(self, query: str, limit: Optional[int] = None) -> SqlResult:
        """Run one read-only SELECT over the org's own tables. `limit` caps
        the rows, default 1000, at most 10000; `truncated` says it was hit.
        A refused query raises ValidationError with `position` on `.body`."""
        return cast(SqlResult, self.request('POST', '/api/v1/sql',
                                            json=compact(query=query, limit=limit)))

    # -- transport -----------------------------------------------------------

    def request(self, method: str, path: str, *, params: Params = None,
                json: Any = None) -> Any:
        """Send one request and return its decoded JSON (None for 204).

        Public so a route the SDK does not wrap yet is still one call away.
        """
        return decode(self.send(method, path, params=params, json=json))

    def send(self, method: str, path: str, *, params: Params = None, json: Any = None,
             headers: Optional[Mapping[str, str]] = None, stream: bool = False,
             retries: Optional[int] = None) -> httpx.Response:
        """The response, or the mapped error. Idempotent methods are retried
        on 429, 5xx and connection failures; a streamed response is returned
        open and the caller closes it."""
        method = method.upper()
        budget = self.max_retries if retries is None else retries
        if method not in _IDEMPOTENT:
            budget = 0
        timeout = self._stream_timeout() if stream else self._timeout

        def attempt() -> httpx.Response:
            request = self._http.build_request(method, path, params=_clean(params), json=json,
                                               headers=headers, timeout=timeout)
            try:
                response = self._http.send(request, stream=stream)
            except httpx.TransportError as e:
                raise APIConnectionError(f'{method} {path}: {e.__class__.__name__}: {e}') from e
            if response.status_code < 400:
                return response
            response.read()
            response.close()
            raise from_response(response)

        retrying = Retrying(stop=stop_after_attempt(budget + 1), retry=retry_if_exception(_retryable),
                            wait=_wait, sleep=self._sleep, reraise=True)
        return retrying(attempt)

    def _stream_timeout(self) -> httpx.Timeout:
        t = self._timeout
        return httpx.Timeout(connect=t.connect, read=max(t.read or 0, STREAM_READ_TIMEOUT),
                             write=t.write, pool=t.pool)


def _retryable(error: BaseException) -> bool:
    """No answer, or one that says to come back: 429 and 5xx, unless the
    server asked for longer than a library call should sit through."""
    if isinstance(error, APIConnectionError):
        return True
    return (isinstance(error, PulzrError) and error.status in _RETRY_STATUSES
            and (error.retry_after is None or error.retry_after <= _RETRY_AFTER_MAX))


def _wait(state: RetryCallState) -> float:
    """The server's Retry-After when it sent one, else exponential backoff,
    jittered so a fleet of clients that all saw the same 503 does not come
    back in step and cause the next one."""
    error = state.outcome.exception() if state.outcome else None
    if getattr(error, 'retry_after', None) is not None:
        return error.retry_after
    delay = min(_BACKOFF_BASE * (2 ** (state.attempt_number - 1)), _BACKOFF_MAX)
    return delay * random.uniform(0.75, 1.25)


def path(base: str, *segments: Any) -> str:
    """`base` with each segment escaped: a DevEUI or id from a caller is data,
    and a `../` in one must not reach a different route."""
    from urllib.parse import quote
    escaped = []
    for segment in segments:
        text = quote(str(segment), safe='')
        # quote() leaves dots alone, and a URL resolves `..` before routing.
        escaped.append(text.replace('.', '%2E') if text in ('.', '..') else text)
    return base + ''.join('/' + s for s in escaped)


def compact(**fields: Any) -> Dict[str, Any]:
    """A JSON body without the arguments the caller did not give."""
    return {k: v for k, v in fields.items() if v is not None}

