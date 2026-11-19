"""The Basics Station wrappers reach net-api's routes/basic_station.py with
the body names it reads, and an EUI is a path segment, never a path."""

from __future__ import annotations

import unittest

from support import body_of, client, ok

GW = 'b827ebfffe6151c7'


class BasicStation(unittest.TestCase):
    def test_routes(self):
        c, script, _ = client([ok({'files': {}}, 201), ok({'state': 'active'}), ok({'files': {}}, 201),
                               ok({'state': 'rotating'}), ok({'state': 'revoked'})])
        c.basic_station.register(GW, 'Roof 1')
        self.assertEqual(c.basic_station.status(GW)['state'], 'active')
        c.basic_station.setup(GW, auth='certificate')
        c.basic_station.rotate(GW)
        c.basic_station.revoke(GW, confirm=GW)
        self.assertEqual([(r.method, r.url.path) for r in script.requests], [
            ('POST', '/api/v1/gateways/basic-station'),
            ('GET', f'/api/v1/gateways/{GW}/basic-station'),
            ('POST', f'/api/v1/gateways/{GW}/basic-station/setup'),
            ('POST', f'/api/v1/gateways/{GW}/basic-station/rotate'),
            ('POST', f'/api/v1/gateways/{GW}/basic-station/revoke'),
        ])
        self.assertEqual(body_of(script.requests[0]), {'gatewayId': GW, 'name': 'Roof 1', 'auth': 'token'})
        self.assertEqual(body_of(script.requests[2]), {'auth': 'certificate'})
        self.assertEqual(body_of(script.requests[4]), {'confirm': GW})

    def test_eui_is_one_segment(self):
        c, script, _ = client([ok({})])
        c.basic_station.status('../../me')
        self.assertEqual(script.requests[0].url.raw_path.decode(),
                         '/api/v1/gateways/..%2F..%2Fme/basic-station')


if __name__ == '__main__':
    unittest.main()
