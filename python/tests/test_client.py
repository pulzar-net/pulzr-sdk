"""Headers, error mapping and the retry rules.

The retry rule is the one that matters most: a POST is never sent twice by
the SDK, because a POST that timed out may already have queued the downlink
or registered the device.
"""

from __future__ import annotations

import unittest

import httpx

import pulzr
from support import client, ok


class Headers(unittest.TestCase):
    def test_auth_org_and_user_agent(self):
        c, script, _ = client([ok({'result': []})], org='usc')
        c.quantities.list()
        sent = script.requests[0]
        self.assertEqual(sent.headers['Authorization'], 'Bearer pzk_test')
        self.assertEqual(sent.headers['X-Active-Org'], 'usc')
        self.assertEqual(sent.headers['User-Agent'], f'pulzr-python/{pulzr.__version__}')
        self.assertEqual(sent.url.path, '/api/v1/quantities')

    def test_no_org_header_without_org(self):
        c, script, _ = client([ok({'result': []})])
        c.quantities.list()
        self.assertNotIn('X-Active-Org', script.requests[0].headers)

    def test_key_required(self):
        import os
        saved = {k: os.environ.pop(k, None) for k in ('PULZR_API_KEY', 'PARKEZE_API_KEY')}
        try:
            with self.assertRaises(ValueError):
                pulzr.Client()
        finally:
            os.environ.update({k: v for k, v in saved.items() if v is not None})

    def test_key_from_the_name_before_pulzar(self):
        from pulzr._client import env
        self.assertEqual(env('PULZR_API_KEY', {'PARKEZE_API_KEY': 'pzk_old'}), 'pzk_old')
        self.assertEqual(env('PULZR_API_KEY', {'PULZR_API_KEY': 'pzk_new', 'PARKEZE_API_KEY': 'pzk_old'}), 'pzk_new')

    def test_params_lists_joined_and_none_dropped(self):
        c, script, _ = client([ok({'result': []})])
        c.readings.latest('temperature', devices=['a84041000181c061', 'a84041000181c062'])
        params = script.requests[0].url.params
        self.assertEqual(params['quantity'], 'temperature')
        self.assertEqual(params['devices'], 'a84041000181c061,a84041000181c062')
        self.assertNotIn('channel', params)

    def test_path_segments_escaped(self):
        c, script, _ = client([ok({})])
        c.devices.get('../webhooks')
        self.assertEqual(script.requests[0].url.raw_path, b'/api/v1/data/devices/..%2Fwebhooks')

    def test_context_manager_closes(self):
        c, _, _ = client([])
        with c as same:
            self.assertIs(same, c)
        self.assertTrue(c._http.is_closed)


class Errors(unittest.TestCase):
    def raised(self, response, **kwargs):
        c, _, _ = client([response], max_retries=0, **kwargs)
        with self.assertRaises(pulzr.PulzrError) as caught:
            c.webhooks.list()
        return caught.exception

    def test_status_classes(self):
        cases = {
            400: pulzr.ValidationError,
            401: pulzr.AuthenticationError,
            403: pulzr.PermissionDeniedError,
            404: pulzr.NotFoundError,
            409: pulzr.ConflictError,
            422: pulzr.ValidationError,
            429: pulzr.RateLimitError,
            500: pulzr.ServerError,
            503: pulzr.ServerError,
        }
        for status, cls in cases.items():
            e = self.raised(ok({'error': f'nope {status}'}, status))
            self.assertIs(type(e), cls, status)
            self.assertEqual(e.status, status)
            self.assertEqual(e.message, f'nope {status}')

    def test_details_and_body(self):
        e = self.raised(ok({'error': 'a: bad', 'details': ['a: bad', 'b: bad']}, 400))
        self.assertEqual(e.details, ['a: bad', 'b: bad'])
        self.assertEqual(e.body['error'], 'a: bad')

    def test_quota_carries_resource_and_limit(self):
        e = self.raised(ok({'error': 'devices limit reached (50)', 'resource': 'devices',
                            'limit': 50}, 409))
        self.assertIsInstance(e, pulzr.ConflictError)
        self.assertEqual((e.resource, e.limit), ('devices', 50))

    def test_plain_conflict_has_no_quota(self):
        e = self.raised(ok({'error': 'A run is still going'}, 409))
        self.assertIsNone(e.resource)
        self.assertIsNone(e.limit)

    def test_non_json_error(self):
        e = self.raised(httpx.Response(502, text='<html>Bad gateway</html>'))
        self.assertIsInstance(e, pulzr.ServerError)
        self.assertIn('Bad gateway', e.message)

    def test_rate_limit_retry_after(self):
        e = self.raised(ok({'error': 'slow down'}, 429, {'Retry-After': '12'}))
        self.assertEqual(e.retry_after, 12.0)

    def test_connection_error(self):
        c, _, _ = client([httpx.ConnectError('refused')], max_retries=0)
        with self.assertRaises(pulzr.APIConnectionError) as caught:
            c.webhooks.list()
        self.assertIsNone(caught.exception.status)

    def test_204_is_none(self):
        c, script, _ = client([httpx.Response(204)])
        self.assertIsNone(c.webhooks.delete('6f1c1a8e-0d7e-4f57-9a43-0d0f0c6f2f10'))
        self.assertEqual(script.requests[0].method, 'DELETE')


class Retries(unittest.TestCase):
    def test_get_503_retried_then_succeeds(self):
        c, script, slept = client([ok({'error': 'down'}, 503), ok({'error': 'down'}, 503),
                                   ok({'result': [{'id': 'x'}]})])
        self.assertEqual(c.webhooks.list(), [{'id': 'x'}])
        self.assertEqual(len(script.requests), 3)
        self.assertEqual(len(slept), 2)
        # Exponential with jitter: 0.5 s then 1 s, each within +-25 %.
        self.assertTrue(0.375 <= slept[0] <= 0.625, slept)
        self.assertTrue(0.75 <= slept[1] <= 1.25, slept)

    def test_get_gives_up_after_max_retries(self):
        c, script, slept = client([ok({'error': 'down'}, 503)] * 3, max_retries=2)
        with self.assertRaises(pulzr.ServerError):
            c.webhooks.list()
        self.assertEqual(len(script.requests), 3)
        self.assertEqual(len(slept), 2)

    def test_post_503_not_retried(self):
        c, script, slept = client([ok({'error': 'down'}, 503), ok({})])
        with self.assertRaises(pulzr.ServerError):
            c.webhooks.create('https://example.com/hook', ['uplink.received'])
        self.assertEqual(len(script.requests), 1)
        self.assertEqual(slept, [])

    def test_post_connection_error_not_retried(self):
        c, script, _ = client([httpx.ConnectError('refused'), ok({})])
        with self.assertRaises(pulzr.APIConnectionError):
            c.devices.downlinks.enqueue('a84041000181c061', 10, data=b'\x01')
        self.assertEqual(len(script.requests), 1)

    def test_patch_not_retried(self):
        c, script, _ = client([ok({'error': 'down'}, 502), ok({})])
        with self.assertRaises(pulzr.ServerError):
            c.webhooks.update('6f1c1a8e-0d7e-4f57-9a43-0d0f0c6f2f10', enabled=False)
        self.assertEqual(len(script.requests), 1)

    def test_put_and_delete_retried(self):
        c, script, _ = client([ok({'error': 'down'}, 503), ok({'id': 't'}),
                               ok({'error': 'down'}, 504), httpx.Response(204)])
        c.device_types.set_quantities('t', {'temp': {'quantity': 'temperature'}})
        c.agents.delete('a')
        self.assertEqual([r.method for r in script.requests], ['PUT', 'PUT', 'DELETE', 'DELETE'])

    def test_get_connection_error_retried(self):
        c, script, _ = client([httpx.ConnectError('refused'), ok({'result': []})])
        self.assertEqual(c.webhooks.list(), [])
        self.assertEqual(len(script.requests), 2)

    def test_retry_after_honoured(self):
        c, _, slept = client([ok({'error': 'slow'}, 429, {'Retry-After': '7'}),
                              ok({'result': []})])
        c.quantities.list()
        self.assertEqual(slept, [7.0])

    def test_retry_after_too_long_is_raised_not_slept(self):
        c, script, slept = client([ok({'error': 'slow'}, 429, {'Retry-After': '3600'})])
        with self.assertRaises(pulzr.RateLimitError) as caught:
            c.quantities.list()
        self.assertEqual(caught.exception.retry_after, 3600.0)
        self.assertEqual(slept, [])
        self.assertEqual(len(script.requests), 1)

    def test_400_not_retried(self):
        c, script, _ = client([ok({'error': 'bad'}, 400)])
        with self.assertRaises(pulzr.ValidationError):
            c.quantities.list()
        self.assertEqual(len(script.requests), 1)


class Shapes(unittest.TestCase):
    def test_downlink_bytes_are_base64(self):
        c, script, _ = client([ok({'id': 'q1'}, 201)])
        c.devices.downlinks.enqueue('a84041000181c061', 10, data=b'\x01\x02', confirmed=True)
        from support import body_of
        self.assertEqual(body_of(script.requests[0]),
                         {'fPort': 10, 'data': 'AQI=', 'confirmed': True})

    def test_series_sends_from(self):
        c, script, _ = client([ok({'series': []})])
        c.readings.series('temperature', since='now-7d', group_by='device')
        params = script.requests[0].url.params
        self.assertEqual(params['from'], 'now-7d')
        self.assertEqual(params['groupBy'], 'device')


if __name__ == '__main__':
    unittest.main()
