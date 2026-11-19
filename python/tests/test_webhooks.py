"""Signature verification against the vectors the server's own code made.

sdk/fixtures/webhook-signatures.json is generated from shared/events.py
(`sign` for the header, `verify` for the expected answer), so a pass here
means this SDK agrees with what net-api actually sends, not with a reading
of the docs.
"""

from __future__ import annotations

import base64
import json
import os
import unittest

import pulzr
from pulzr import webhooks
from support import body_of, client, ok

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'fixtures',
                        'webhook-signatures.json')


def load_cases():
    with open(FIXTURES, encoding='utf-8') as f:
        return json.load(f)


class Vectors(unittest.TestCase):
    def test_every_case(self):
        fixture = load_cases()
        self.assertEqual(fixture['header'], webhooks.SIGNATURE_HEADER)
        self.assertGreaterEqual(len(fixture['cases']), 14)
        for case in fixture['cases']:
            with self.subTest(case['name']):
                body = base64.b64decode(case['bodyBase64'])
                got = webhooks.verify_signature(case['secret'], body, case['header'],
                                                tolerance=case['tolerance'], now=case['now'])
                self.assertIs(got, case['valid'], case['note'])

    def test_every_case_with_a_rotation_pair(self):
        # A receiver holding two secrets accepts whatever either accepts.
        other = 'whsec_' + '00' * 24
        for case in load_cases()['cases']:
            with self.subTest(case['name']):
                body = base64.b64decode(case['bodyBase64'])
                got = webhooks.verify_signature([other, case['secret']], body, case['header'],
                                                tolerance=case['tolerance'], now=case['now'])
                self.assertIs(got, case['valid'])

    def test_construct_event(self):
        case = next(c for c in load_cases()['cases'] if c['name'] == 'valid')
        body = base64.b64decode(case['bodyBase64'])
        event = webhooks.construct_event(case['secret'], body, case['header'], now=case['now'])
        self.assertEqual(event['type'], 'uplink.received')
        self.assertEqual(event['subject'], 'a84041000181c061')

    def test_construct_event_refuses(self):
        case = next(c for c in load_cases()['cases'] if c['name'] == 'tampered-body')
        with self.assertRaises(pulzr.SignatureVerificationError):
            webhooks.construct_event(case['secret'], base64.b64decode(case['bodyBase64']),
                                     case['header'], now=case['now'])

    def test_sign_matches_the_server(self):
        case = next(c for c in load_cases()['cases'] if c['name'] == 'rotation-old-secret')
        body = base64.b64decode(case['bodyBase64'])
        timestamp = int(case['header'].split(',')[0][2:])
        new = 'whsec_' + '1f' * 24
        self.assertEqual(webhooks.sign([new, case['secret']], body, timestamp), case['header'])

    def test_garbage_is_false_not_an_exception(self):
        for header in (None, '', 't=', 'v1=ab,t=1', 't=1,v1=é', ',,,'):
            with self.subTest(header):
                self.assertFalse(webhooks.verify_signature('whsec_x', b'{}', header, now=1))

    def test_top_level_names(self):
        self.assertIs(pulzr.verify_signature, webhooks.verify_signature)
        self.assertIs(pulzr.construct_event, webhooks.construct_event)


class Endpoints(unittest.TestCase):
    def test_routes(self):
        wid = '6f1c1a8e-0d7e-4f57-9a43-0d0f0c6f2f10'
        c, script, _ = client([
            ok({'id': wid, 'secret': 'whsec_abc'}, 201),
            ok({'id': wid, 'secret': 'whsec_new', 'previousSecretExpiresAt': 'x'}),
            ok({'deliveryId': 'd1', 'eventId': 'evt_1'}, 202),
            ok({'result': [{'id': 'd1'}]}),
            ok({'id': 'd1', 'status': 'pending'}, 202),
        ])
        made = c.webhooks.create('https://example.com/hook', ['device.offline'],
                                 description='Pager')
        self.assertEqual(made['secret'], 'whsec_abc')
        c.webhooks.rotate_secret(wid)
        c.webhooks.test(wid)
        self.assertEqual(c.webhooks.deliveries(wid, status='failed'), [{'id': 'd1'}])
        c.webhooks.retry_delivery('d1')
        self.assertEqual([(r.method, r.url.path) for r in script.requests], [
            ('POST', '/api/v1/webhooks'),
            ('POST', f'/api/v1/webhooks/{wid}/rotate-secret'),
            ('POST', f'/api/v1/webhooks/{wid}/test'),
            ('GET', f'/api/v1/webhooks/{wid}/deliveries'),
            ('POST', '/api/v1/webhooks/deliveries/d1/retry'),
        ])
        self.assertEqual(body_of(script.requests[0]), {'url': 'https://example.com/hook',
                                                       'eventTypes': ['device.offline'],
                                                       'description': 'Pager'})


if __name__ == '__main__':
    unittest.main()
