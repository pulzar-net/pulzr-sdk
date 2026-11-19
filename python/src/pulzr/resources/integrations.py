"""Integrations: events pushed into InfluxDB, Datacake, ThingsBoard, AWS IoT
Core, Azure IoT Hub, Akenza, Ubidots, TagoIO or S3 in each one's own format."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, cast

from .._client import compact, path
from ..types import Integration, IntegrationDelivery, IntegrationTemplate
from . import Resource

_BASE = '/api/v1/integrations'


class Integrations(Resource):
    def templates(self) -> List[IntegrationTemplate]:
        """Every target, with its settings as JSON Schema. `x-secret` marks a
        credential: sent on create, never returned."""
        return cast(List[IntegrationTemplate], self._client.request('GET', path(_BASE, 'templates'))['result'])

    def list(self) -> List[Integration]:
        return cast(List[Integration], self._client.request('GET', _BASE)['result'])

    def create(self, template: str, name: str, settings: Mapping[str, Any], *,
               event_types: Optional[Iterable[str]] = None,
               application_ids: Optional[Iterable[str]] = None) -> Integration:
        """Org admin. `event_types` defaults to every type the template takes."""
        body = compact(template=template, name=name, settings=dict(settings),
                       eventTypes=list(event_types) if event_types is not None else None,
                       applicationIds=list(application_ids) if application_ids is not None else None)
        return cast(Integration, self._client.request('POST', _BASE, json=body))

    def get(self, integration_id: str) -> Integration:
        return cast(Integration, self._client.request('GET', path(_BASE, integration_id)))

    def update(self, integration_id: str, *, name: Optional[str] = None,
               settings: Optional[Mapping[str, Any]] = None,
               event_types: Optional[Iterable[str]] = None,
               application_ids: Optional[Iterable[str]] = None,
               enabled: Optional[bool] = None) -> Integration:
        """Org admin. `settings` is merged over what is stored; a secret left
        out is kept."""
        body = compact(name=name, settings=dict(settings) if settings is not None else None,
                       eventTypes=list(event_types) if event_types is not None else None,
                       applicationIds=list(application_ids) if application_ids is not None else None,
                       enabled=enabled)
        return cast(Integration, self._client.request('PATCH', path(_BASE, integration_id), json=body))

    def delete(self, integration_id: str) -> None:
        self._client.request('DELETE', path(_BASE, integration_id))

    def test(self, integration_id: str, *, dev_eui: Optional[str] = None) -> Dict[str, Any]:
        """Queue a synthetic uplink to this integration alone.
        `{deliveryId, eventId, request}`, the request with credentials masked."""
        return self._client.request('POST', path(_BASE, integration_id, 'test'),
                                    json=compact(devEui=dev_eui))

    def deliveries(self, integration_id: str, *, status: Optional[str] = None,
                   limit: Optional[int] = None) -> List[IntegrationDelivery]:
        return cast(List[IntegrationDelivery], self._client.request(
            'GET', path(_BASE, integration_id, 'deliveries'),
            params={'status': status, 'limit': limit})['result'])

    def retry_delivery(self, delivery_id: str) -> Dict[str, Any]:
        return self._client.request('POST', path(_BASE, 'deliveries', delivery_id, 'retry'))
