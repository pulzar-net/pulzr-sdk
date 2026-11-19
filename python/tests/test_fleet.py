"""Multicast groups, relays and firmware updates reach the routes they name,
with the bodies those routes read (net-api/routes/multicast.py, relays.py,
firmware.py) -- above all the typed confirmation on start, which the server
matches exactly."""

from __future__ import annotations

import base64
import unittest

import pulzr
from support import body_of, client, ok

GROUP = 'aaaaaaaa-0000-4000-8000-000000000001'
DEP = '9c8b7a6d-5e4f-4a3b-9c2d-1e0f9a8b7c6d'
IMAGE = '5b9e7c1a-2d3f-4e5a-8b6c-7d8e9f0a1b2c'
TYPE = '3f2e1d0c-9b8a-4c7d-8e6f-5a4b3c2d1e0f'
RELAY = '0016c001ff100001'
EUI = '0016c001ff100002'


class Multicast(unittest.TestCase):
    def test_routes(self):
        c, script, _ = client([
            ok({'result': []}),
            ok({'id': GROUP, 'keys': {'mcNwkSKey': 'a', 'mcAppSKey': 'b'}}, 201),
            ok({'added': EUI}, 201),
            ok({'added': 'ff'}, 201),
            ok({'fCnt': 3}, 201),
            ok({'removed': EUI}),
            ok({'flushed': True}),
        ])
        c.multicast_groups.list()
        made = c.multicast_groups.create('Lot 4', 'app-1', 'EU868', group_type='B', ping_slot_periodicity=5)
        self.assertEqual(made['keys']['mcAppSKey'], 'b')
        c.multicast_groups.add_device(GROUP, EUI)
        c.multicast_groups.add_gateway(GROUP, '0016c001ff10a235')
        c.multicast_groups.send(GROUP, 10, b'\x01\x02')
        c.multicast_groups.remove_device(GROUP, EUI)
        c.multicast_groups.flush(GROUP)
        self.assertEqual([(r.method, r.url.path) for r in script.requests], [
            ('GET', '/api/v1/multicast-groups'),
            ('POST', '/api/v1/multicast-groups'),
            ('POST', f'/api/v1/multicast-groups/{GROUP}/devices'),
            ('POST', f'/api/v1/multicast-groups/{GROUP}/gateways'),
            ('POST', f'/api/v1/multicast-groups/{GROUP}/queue'),
            ('DELETE', f'/api/v1/multicast-groups/{GROUP}/devices/{EUI}'),
            ('DELETE', f'/api/v1/multicast-groups/{GROUP}/queue'),
        ])
        self.assertEqual(body_of(script.requests[1]), {
            'name': 'Lot 4', 'applicationId': 'app-1', 'region': 'EU868', 'groupType': 'B',
            'pingSlotPeriodicity': 5})
        self.assertEqual(body_of(script.requests[2]), {'devEui': EUI})
        self.assertEqual(body_of(script.requests[3]), {'gatewayId': '0016c001ff10a235'})
        self.assertEqual(body_of(script.requests[4]), {'fPort': 10, 'data': base64.b64encode(b'\x01\x02').decode()})

    def test_relays(self):
        c, script, _ = client([ok({'result': []}), ok({'result': []}), ok({'added': EUI}, 201)])
        c.relays.list()
        c.relays.devices(RELAY)
        c.relays.add_device(RELAY, EUI)
        self.assertEqual([(r.method, r.url.path) for r in script.requests], [
            ('GET', '/api/v1/relays'),
            ('GET', f'/api/v1/relays/{RELAY}/devices'),
            ('POST', f'/api/v1/relays/{RELAY}/devices'),
        ])
        self.assertEqual(body_of(script.requests[2]), {'devEui': EUI})


class Firmware(unittest.TestCase):
    def test_routes(self):
        c, script, _ = client([
            ok({'id': IMAGE, 'sha256': '0' * 64}, 201),
            ok({'devices': [], 'estimate': None}),
            ok({'id': DEP, 'status': 'draft'}, 201),
            ok({'id': DEP, 'status': 'running'}),
            ok({'id': DEP, 'status': 'running', 'devices': []}),
            ok({'id': DEP, 'status': 'canceled'}),
        ])
        c.firmware.upload_image(b'\x7fELF', 'LAS7', device_type_id=TYPE, version='2.1')
        c.firmware.plan(IMAGE, tags={'lot': '4'}, redundancyPercent=20)
        c.firmware.create('Lot 4 to 2.1', IMAGE, dev_euis=[EUI], completeTags={'firmware': '2.1'})
        c.firmware.start(DEP, confirm='Lot 4 to 2.1')
        c.firmware.get(DEP)
        c.firmware.cancel(DEP)
        self.assertEqual([(r.method, r.url.path) for r in script.requests], [
            ('POST', '/api/v1/firmware/images'),
            ('POST', '/api/v1/firmware/plan'),
            ('POST', '/api/v1/firmware/deployments'),
            ('POST', f'/api/v1/firmware/deployments/{DEP}/start'),
            ('GET', f'/api/v1/firmware/deployments/{DEP}'),
            ('POST', f'/api/v1/firmware/deployments/{DEP}/cancel'),
        ])
        upload = script.requests[0]
        self.assertTrue(upload.headers['content-type'].startswith('multipart/form-data'))
        self.assertIn(b'name="file"', upload.content)
        self.assertIn(b'\x7fELF', upload.content)
        self.assertIn(TYPE.encode(), upload.content)
        self.assertEqual(body_of(script.requests[1]), {
            'imageId': IMAGE, 'tags': {'lot': '4'}, 'redundancyPercent': 20})
        self.assertEqual(body_of(script.requests[2]), {
            'name': 'Lot 4 to 2.1', 'imageId': IMAGE, 'devEuis': [EUI],
            'completeTags': {'firmware': '2.1'}})
        self.assertEqual(body_of(script.requests[3]), {'confirm': 'Lot 4 to 2.1'})

    def test_refusals_are_errors(self):
        c, _, _ = client([ok({'error': 'Type the deployment name to start it: Lot 4'}, 400),
                          ok({'error': 'This exact image is already uploaded as LAS7'}, 409)])
        with self.assertRaises(pulzr.errors.PulzrError):
            c.firmware.start(DEP, confirm='lot 4')
        with self.assertRaises(pulzr.errors.PulzrError):
            c.firmware.upload_image(b'x', 'Again', device_type_id=TYPE)


if __name__ == '__main__':
    unittest.main()
