"""gateways.network() reaches the route routes/networks.py serves, with the
EUI as a path segment."""

from __future__ import annotations

import unittest

from support import client, ok

GW = 'ac1f09fffe0b1c2d'


class Networks(unittest.TestCase):
    def test_route(self):
        c, script, _ = client([ok({'gatewayId': GW, 'wireguard': None, 'cellular': {
            'kind': 'cellular', 'slug': 'acme', 'name': 'Acme', 'owner': 'organization'},
            'sshCa': False})])
        self.assertEqual(c.gateways.network(GW)['cellular']['owner'], 'organization')
        self.assertEqual([(r.method, r.url.path) for r in script.requests],
                         [('GET', f'/api/v1/gateways/{GW}/network')])


if __name__ == '__main__':
    unittest.main()
