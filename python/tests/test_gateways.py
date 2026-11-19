"""The gateway wrappers reach the routes net-api serves (routes/gateways.py,
plugins/gateway_ops), with the parameter and body names those routes read,
and an EUI is a path segment, never a path."""

from __future__ import annotations

import unittest

from support import body_of, client, ok

GW = 'ac1f09fffe0b1c2d'
OFFER = '9d3c1a7e-5f2b-4c8d-a1e0-7b6f5d4c3b2a'


class Gateways(unittest.TestCase):
    def test_routes(self):
        c, script, _ = client([
            ok({'result': [{'gatewayId': GW, 'can': ['read']}]}),
            ok({'result': []}),
            ok({'result': [], 'silent': [], 'days': 3}),
            ok({'uptime': '3d'}),
            ok({'reachable': True}),
            ok({'iccid': '8988228066614207616'}),
            ok({'parkezeos': False}),
            ok({'exitStatus': 0, 'output': ''}),
            ok({'ok': True}),
            ok({'id': 1}, 202),
            ok({'id': OFFER, 'status': 'offered'}, 202),
            ok({'result': []}),
            ok({'gatewayId': GW}),
            ok({'id': OFFER, 'status': 'declined'}),
            ok({'id': OFFER, 'status': 'cancelled'}),
            ok({'gatewayId': GW, 'removed': [], 'failed': []}),
        ])
        self.assertEqual(c.gateways.list()[0]['can'], ['read'])
        c.gateways.metrics(GW, hours=48)
        c.gateways.devices(GW, days=3)
        c.gateways.status(GW)
        c.gateways.backhaul(GW)
        c.gateways.sim(GW)
        c.gateways.firmware(GW)
        c.gateways.restart(GW)
        c.gateways.reset_sim(GW)
        c.gateways.update_firmware(GW, 'v0.4.0', over_cellular=True)
        c.gateways.offer(GW, 'columbia', confirm=GW, note='Roof 3')
        c.gateways.transfers()
        c.gateways.accept(OFFER, confirm=GW)
        c.gateways.decline(OFFER)
        c.gateways.cancel(OFFER)
        c.gateways.remove(GW)
        self.assertEqual([(r.method, r.url.path) for r in script.requests], [
            ('GET', '/api/v1/gateways'),
            ('GET', f'/api/v1/gateways/{GW}/metrics'),
            ('GET', f'/api/v1/gateways/{GW}/devices'),
            ('GET', f'/api/v1/gateway-ops/{GW}/status'),
            ('GET', f'/api/v1/gateway-ops/{GW}/backhaul'),
            ('GET', f'/api/v1/gateway-ops/{GW}/sim'),
            ('GET', f'/api/v1/gateway-ops/{GW}/firmware'),
            ('POST', f'/api/v1/gateway-ops/{GW}/restart'),
            ('POST', f'/api/v1/gateway-ops/{GW}/sim/reset'),
            ('POST', f'/api/v1/gateway-ops/{GW}/firmware'),
            ('POST', f'/api/v1/gateway-ops/gateways/{GW}/transfer'),
            ('GET', '/api/v1/gateway-ops/transfers'),
            ('POST', f'/api/v1/gateway-ops/transfers/{OFFER}/accept'),
            ('POST', f'/api/v1/gateway-ops/transfers/{OFFER}/decline'),
            ('POST', f'/api/v1/gateway-ops/transfers/{OFFER}/cancel'),
            ('DELETE', f'/api/v1/gateway-ops/gateways/{GW}'),
        ])
        self.assertEqual(dict(script.requests[1].url.params), {'hours': '48'})
        self.assertEqual(dict(script.requests[2].url.params), {'days': '3'})
        self.assertEqual(body_of(script.requests[9]), {'tag': 'v0.4.0', 'overCellular': True})
        self.assertEqual(body_of(script.requests[10]),
                         {'toOrg': 'columbia', 'confirm': GW, 'note': 'Roof 3'})
        self.assertEqual(body_of(script.requests[12]), {'confirm': GW})

    def test_an_eui_is_one_segment(self):
        c, script, _ = client([ok({})])
        c.gateways.status('../claims')
        self.assertEqual(script.requests[0].url.raw_path.decode(),
                         '/api/v1/gateway-ops/..%2Fclaims/status')


if __name__ == '__main__':
    unittest.main()
