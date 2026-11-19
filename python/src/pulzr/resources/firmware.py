"""Firmware updates over the air: images and deployments."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, cast

from .._client import compact, decode, path
from ..errors import from_response
from ..types import FirmwareDeployment, FirmwareImage
from . import Resource

_BASE = '/api/v1/firmware'


def _selection(dev_euis: Optional[Iterable[str]], device_type_id: Optional[str],
               application_id: Optional[str], tags: Optional[Mapping[str, str]],
               options: Mapping[str, Any]) -> Dict[str, Any]:
    return compact(devEuis=list(dev_euis) if dev_euis is not None else None,
                   deviceTypeId=device_type_id, applicationId=application_id,
                   tags=dict(tags) if tags is not None else None, **options)


class Firmware(Resource):
    # -- images ----------------------------------------------------------------

    def images(self, *, device_type_id: Optional[str] = None) -> List[FirmwareImage]:
        return cast(List[FirmwareImage], self._client.request(
            'GET', path(_BASE, 'images'), params={'deviceTypeId': device_type_id})['result'])

    def upload_image(self, content: bytes, name: str, *, device_type_id: str, version: str = '',
                     filename: str = 'firmware.bin') -> FirmwareImage:
        """Org admin. At most 512 KB, built for `device_type_id`, and only
        ever deployed to devices of that type. The same bytes twice is a
        ConflictError."""
        response = self._client._http.post(
            path(_BASE, 'images'), files={'file': (filename, content, 'application/octet-stream')},
            data=compact(name=name, version=version, deviceTypeId=device_type_id),
            timeout=self._client._timeout)
        if response.status_code >= 400:
            raise from_response(response)
        return cast(FirmwareImage, decode(response))

    def set_image_type(self, image_id: str, device_type_id: str) -> FirmwareImage:
        """Org admin. On an image with no type, or one no deployment used."""
        return cast(FirmwareImage, self._client.request(
            'PATCH', path(_BASE, 'images', image_id), json={'deviceTypeId': device_type_id}))

    def delete_image(self, image_id: str) -> None:
        self._client.request('DELETE', path(_BASE, 'images', image_id))

    # -- deployments -----------------------------------------------------------

    def plan(self, image_id: str, *, dev_euis: Optional[Iterable[str]] = None,
             device_type_id: Optional[str] = None, application_id: Optional[str] = None,
             tags: Optional[Mapping[str, str]] = None, **options: Any) -> Dict[str, Any]:
        """What a deployment would do and how long it would take; changes
        nothing. `options` are the deployment's settings in the API's names
        (`groupType`, `dr`, `redundancyPercent`, ...)."""
        body = _selection(dev_euis, device_type_id, application_id, tags,
                          {'imageId': image_id, **options})
        return self._client.request('POST', path(_BASE, 'plan'), json=body)

    def create(self, name: str, image_id: str, *, dev_euis: Optional[Iterable[str]] = None,
               device_type_id: Optional[str] = None, application_id: Optional[str] = None,
               tags: Optional[Mapping[str, str]] = None, **options: Any) -> FirmwareDeployment:
        """Org admin. A draft: nothing reaches the LNS until `start`."""
        body = _selection(dev_euis, device_type_id, application_id, tags,
                          {'name': name, 'imageId': image_id, **options})
        return cast(FirmwareDeployment, self._client.request('POST', path(_BASE, 'deployments'), json=body))

    def list(self, *, device_type_id: Optional[str] = None) -> List[FirmwareDeployment]:
        """`device_type_id`: only those whose image is built for it."""
        return cast(List[FirmwareDeployment], self._client.request(
            'GET', path(_BASE, 'deployments'), params={'deviceTypeId': device_type_id})['result'])

    def get(self, deployment_id: str) -> FirmwareDeployment:
        """With each device's stage; a running one is synced with the LNS."""
        return cast(FirmwareDeployment, self._client.request('GET', path(_BASE, 'deployments', deployment_id)))

    def start(self, deployment_id: str, confirm: str) -> FirmwareDeployment:
        """Org admin. Reflashes devices: `confirm` is the deployment's name,
        exactly, or the server refuses."""
        return cast(FirmwareDeployment, self._client.request(
            'POST', path(_BASE, 'deployments', deployment_id, 'start'), json={'confirm': confirm}))

    def cancel(self, deployment_id: str) -> FirmwareDeployment:
        return cast(FirmwareDeployment, self._client.request(
            'POST', path(_BASE, 'deployments', deployment_id, 'cancel')))
