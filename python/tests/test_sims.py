"""The SIM wrappers reach the routes net-api serves (routes/sims.py), with the
parameter and body names those routes read, and an ICCID is a path segment."""

from __future__ import annotations

import unittest

from support import body_of, client, ok

ICCID = '8988228066614207616'


class Sims(unittest.TestCase):
    def test_routes(self):
        c, script, _ = client([
            ok({'result': [{'iccid': ICCID, 'can': ['read']}], 'orphaned': []}),
            ok({'result': {ICCID: 'ATTACHED'}, 'cached': False}),
            ok({'result': [], 'recordingSince': None}),
            ok({'iccid': ICCID, 'can': ['read', 'manage']}),
            ok({'volumeMb': 500}),
            ok({'status': 'Disabled'}),
            ok({'ok': True}),
        ])
        self.assertEqual(c.sims.list()['result'][0]['can'], ['read'])
        c.sims.status()
        c.sims.usage(days=30)
        c.sims.get(ICCID)
        c.sims.billing(ICCID)
        c.sims.update(ICCID, enabled=False, imei_lock=False)
        c.sims.reset(ICCID)
        self.assertEqual([(r.method, r.url.path) for r in script.requests], [
            ('GET', '/api/v1/sims'),
            ('GET', '/api/v1/sims/status'),
            ('GET', '/api/v1/sims/usage'),
            ('GET', f'/api/v1/sims/{ICCID}/detail'),
            ('GET', f'/api/v1/sims/{ICCID}/billing'),
            ('PATCH', f'/api/v1/sims/{ICCID}'),
            ('POST', f'/api/v1/sims/{ICCID}/reset'),
        ])
        self.assertEqual(script.requests[2].url.params.get('days'), '30')
        # False is a deliberate disable and a deliberate unlock, so it is sent.
        self.assertEqual(body_of(script.requests[5]), {'enabled': False, 'imeiLock': False})

    def test_an_iccid_is_one_segment(self):
        c, script, _ = client([ok({})])
        c.sims.reset('../orgs')
        self.assertEqual(script.requests[0].url.raw_path.decode(),
                         '/api/v1/sims/..%2Forgs/reset')


if __name__ == '__main__':
    unittest.main()
