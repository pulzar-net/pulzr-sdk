"""Onboarding: a sensor model from catalog or datasheet to its first uplink."""

from __future__ import annotations

import base64
import json
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple, Union, cast

from .._client import compact, path
from .._sse import SSEDecoder
from ..types import OnboardingSession
from . import Resource

_BASE = '/api/v1/onboarding'

Blob = Union[bytes, bytearray, str, None]


def _b64(value: Blob) -> Optional[str]:
    if value is None or isinstance(value, str):
        return value
    return base64.b64encode(bytes(value)).decode()


class Sessions(Resource):
    def list(self) -> List[OnboardingSession]:
        """The org's 50 most recent."""
        return cast(List[OnboardingSession],
                    self._client.request('GET', f'{_BASE}/sessions')['result'])

    def start(self, *, catalog: Optional[Dict[str, str]] = None,
              datasheet_pdf: Blob = None, datasheet_text: Optional[str] = None,
              label_photo: Blob = None, vendor: Optional[str] = None,
              model: Optional[str] = None, decoder: Optional[str] = None) -> OnboardingSession:
        """Start from a catalog hit (`{'source': 'org'|'parkeze'|'repository',
        'id': ...}`), from a datasheet and/or label photo (bytes, PNG or
        JPEG), or from `vendor` and `model` with the payload format the board
        speaks (`decoder='cayenne_lpp'`). Generating a decoder is for org admins. Returns at once in
        `identifying`; follow it with get() or watch(). RateLimitError while
        the org already has 5 sessions working."""
        body = compact(catalog=catalog, datasheetPdf=_b64(datasheet_pdf),
                       datasheetText=datasheet_text, labelPhoto=_b64(label_photo),
                       vendor=vendor, model=model, decoder=decoder)
        return cast(OnboardingSession, self._client.request('POST', f'{_BASE}/sessions', json=body))

    def get(self, session_id: str) -> OnboardingSession:
        return cast(OnboardingSession,
                    self._client.request('GET', path(f'{_BASE}/sessions', session_id)))


class Onboarding(Resource):
    def __init__(self, client: Any) -> None:
        super().__init__(client)
        self.sessions = Sessions(client)

    def catalog(self, q: Optional[str] = None) -> Dict[str, Any]:
        """Device types this org can use now, and for a search, the device
        repository's too. A hit with `ready` decodes as soon as it is
        registered."""
        return self._client.request('GET', f'{_BASE}/catalog', params={'q': q})

    def accept(self, session_id: str, *, lorawan: Optional[Dict[str, Any]] = None,
               field_schema: Optional[Dict[str, Any]] = None) -> OnboardingSession:
        """Org admin. Accept a `ready` decoder: it is committed, deployed and
        the session moves on to registering."""
        return cast(OnboardingSession, self._client.request(
            'POST', path(f'{_BASE}/sessions', session_id, 'accept'),
            json=compact(lorawan=lorawan, fieldSchema=field_schema)))

    def register_devices(self, session_id: str, *,
                         devices: Optional[Iterable[Dict[str, Any]]] = None,
                         qr: Optional[Iterable[str]] = None, csv: Optional[str] = None,
                         label_photo: Blob = None, application: Optional[str] = None,
                         dry_run: bool = False) -> Dict[str, Any]:
        """Register the model's devices. `devices` rows are `{devEui, joinEui,
        appKey, name}`, `{qr, appKey}` or `{mac, name}`; `qr` takes TR005
        texts. With `dry_run` nothing is registered and the parsed rows come
        back (`{rows, problems}`) to check by eye first."""
        body = compact(devices=list(devices) if devices is not None else None,
                       qr=list(qr) if qr is not None else None, csv=csv,
                       labelPhoto=_b64(label_photo), application=application,
                       dryRun=True if dry_run else None)
        return self._client.request('POST', path(f'{_BASE}/sessions', session_id, 'devices'),
                                    json=body)

    def abandon(self, session_id: str) -> OnboardingSession:
        return cast(OnboardingSession, self._client.request(
            'POST', path(f'{_BASE}/sessions', session_id, 'abandon')))

    def metrics(self) -> Dict[str, Any]:
        """Started to first uplink over 30 days: median and p90 seconds."""
        return self._client.request('GET', f'{_BASE}/metrics')

    def watch(self, session_id: str) -> Iterator[Tuple[str, Dict[str, Any]]]:
        """`(event, data)` as the session moves: `session`, `join`, `uplink`,
        `first_uplink`, and `end` (`{reason}`), after which it stops.

        `end` comes for a failed or abandoned session; with reason `live`
        five minutes after the session goes live, if it has not changed
        since; or after an hour. Stop on `first_uplink` if that is all you
        are waiting for. Not reconnected
        on a drop: every connect replays the joins and uplinks since
        registration, so a reconnect would repeat them.
        """
        response = self._client.send('GET', path(f'{_BASE}/sessions', session_id, 'watch'),
                                     stream=True, headers={'Accept': 'text/event-stream'})
        try:
            for sse in SSEDecoder().iter_events(response.iter_lines()):
                data = json.loads(sse.data)
                yield sse.event, data
                if sse.event == 'end':
                    return
        finally:
            response.close()
