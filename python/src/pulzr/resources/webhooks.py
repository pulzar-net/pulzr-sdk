"""Webhook endpoints and their deliveries. Verifying one is pulzr.webhooks."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, cast

from .._client import compact, path
from ..types import Webhook, WebhookDelivery
from . import Resource

_BASE = '/api/v1/webhooks'


class Webhooks(Resource):
    def list(self) -> List[Webhook]:
        return cast(List[Webhook], self._client.request('GET', _BASE)['result'])

    def create(self, url: str, event_types: Iterable[str], *,
               application_ids: Optional[Iterable[str]] = None,
               description: Optional[str] = None) -> Webhook:
        """Org admin. The response carries `secret`, and no later one does:
        store it now."""
        body = compact(url=url, eventTypes=list(event_types),
                       applicationIds=list(application_ids) if application_ids is not None else None,
                       description=description)
        return cast(Webhook, self._client.request('POST', _BASE, json=body))

    def get(self, webhook_id: str) -> Webhook:
        return cast(Webhook, self._client.request('GET', path(_BASE, webhook_id)))

    def update(self, webhook_id: str, *, url: Optional[str] = None,
               event_types: Optional[Iterable[str]] = None,
               application_ids: Optional[Iterable[str]] = None,
               description: Optional[str] = None, enabled: Optional[bool] = None) -> Webhook:
        """Org admin. Only the arguments given change. Re-enabling clears the
        failure count that disabled it."""
        body = compact(url=url,
                       eventTypes=list(event_types) if event_types is not None else None,
                       applicationIds=list(application_ids) if application_ids is not None else None,
                       description=description, enabled=enabled)
        return cast(Webhook, self._client.request('PATCH', path(_BASE, webhook_id), json=body))

    def delete(self, webhook_id: str) -> None:
        self._client.request('DELETE', path(_BASE, webhook_id))

    def rotate_secret(self, webhook_id: str) -> Dict[str, Any]:
        """`{id, secret, previousSecretExpiresAt}`. Deliveries are signed with
        both secrets until then, so receivers can be redeployed in between."""
        return self._client.request('POST', path(_BASE, webhook_id, 'rotate-secret'))

    def test(self, webhook_id: str) -> Dict[str, Any]:
        """Queue a `webhook.test` delivery to this endpoint alone.
        `{deliveryId, eventId}`."""
        return self._client.request('POST', path(_BASE, webhook_id, 'test'))

    def deliveries(self, webhook_id: str, *, status: Optional[str] = None,
                   limit: Optional[int] = None) -> List[WebhookDelivery]:
        """Newest first, with the request sent and the response received."""
        return cast(List[WebhookDelivery], self._client.request(
            'GET', path(_BASE, webhook_id, 'deliveries'),
            params={'status': status, 'limit': limit})['result'])

    def retry_delivery(self, delivery_id: str) -> Dict[str, Any]:
        return self._client.request('POST', path(_BASE, 'deliveries', delivery_id, 'retry'))
