"""Airtime, location and coverage wrappers reach the routes net-api serves
(routes/airtime.py, routes/location.py, routes/coverage.py), with the
parameter and body names those routes read."""

from __future__ import annotations

import unittest

from support import body_of, client, ok

EUI = 'a84041000181c061'
SESSION = '3f1c2b4a-5d6e-4f70-8a9b-0c1d2e3f4a5b'


class Radio(unittest.TestCase):
    def test_routes(self):
        c, script, _ = client([
            ok({'devEui': EUI, 'days': []}),
            ok({'result': [], 'exceeding': 0}),
            ok({'devEui': EUI, 'location': None}),
            ok({'type': 'FeatureCollection', 'features': []}),
            ok({'heard': False}),
            ok({'result': []}),
            ok({'public': False}),
            ok({'public': True}),
            ok({'type': 'FeatureCollection', 'features': []}),
            ok({'id': SESSION}, 201),
            ok({'id': SESSION, 'samples': 1}),
            ok({'id': SESSION, 'endedAt': '2026-10-13T12:00:00Z'}),
        ])
        c.airtime.device(EUI, days=3)
        self.assertEqual(c.airtime.day('2026-10-13', limit=5)['exceeding'], 0)
        c.devices.location(EUI, history=5)
        c.coverage.cells(gateway_id='aa555a0000000001', resolution=8, bbox=(-118.3, 34.0, -118.2, 34.1))
        self.assertFalse(c.coverage.at(34.02, -118.28)['heard'])
        self.assertEqual(c.coverage.gateways(), [])
        c.coverage.settings()
        c.coverage.settings(public=True)
        c.coverage.public((-118.3, 34.0, -118.2, 34.1))
        c.coverage.start_session(EUI)
        c.coverage.add_fixes(SESSION, [{'time': 1760356800000, 'latitude': 34.02,
                                        'longitude': -118.28, 'accuracy': None}])
        c.coverage.stop_session(SESSION)
        self.assertEqual([(r.method, r.url.path) for r in script.requests], [
            ('GET', f'/api/v1/devices/{EUI}/airtime'),
            ('GET', '/api/v1/airtime'),
            ('GET', f'/api/v1/devices/{EUI}/location'),
            ('GET', '/api/v1/coverage'),
            ('GET', '/api/v1/coverage/at'),
            ('GET', '/api/v1/coverage/gateways'),
            ('GET', '/api/v1/coverage/settings'),
            ('PUT', '/api/v1/coverage/settings'),
            ('GET', '/api/v1/public/coverage'),
            ('POST', '/api/v1/coverage/sessions'),
            ('POST', f'/api/v1/coverage/sessions/{SESSION}/fixes'),
            ('POST', f'/api/v1/coverage/sessions/{SESSION}/stop'),
        ])
        params = [dict(r.url.params) for r in script.requests]
        self.assertEqual(params[0], {'days': '3'})
        self.assertEqual(params[1], {'day': '2026-10-13', 'limit': '5'})
        self.assertEqual(params[2], {'history': '5'})
        self.assertEqual(params[3], {'gatewayId': 'aa555a0000000001', 'resolution': '8',
                                     'bbox': '-118.3,34.0,-118.2,34.1'})
        self.assertEqual(params[4], {'latitude': '34.02', 'longitude': '-118.28'})
        self.assertEqual(body_of(script.requests[7]), {'public': True})
        self.assertEqual(body_of(script.requests[9]), {'devEui': EUI})
        # An absent accuracy is left out rather than sent as null.
        self.assertEqual(body_of(script.requests[10]), {'fixes': [
            {'time': 1760356800000, 'latitude': 34.02, 'longitude': -118.28}]})


if __name__ == '__main__':
    unittest.main()
