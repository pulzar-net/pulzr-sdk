"""Each wrapper reaches the route it names, with the body that route reads.

Paths and field names are checked against net-api/routes, not the docs: a
wrapper that posts `event_types` where the route reads `eventTypes` passes
every test that only mocks itself.
"""

from __future__ import annotations

import json
import unittest

import httpx

import pulzr
from support import body_of, client, ok, sse

EUI = 'a84041000181c061'


class Devices(unittest.TestCase):
    def test_routes(self):
        c, script, _ = client([
            ok({'online': 1, 'offline': 0, 'result': [{'devEui': EUI}]}),
            ok({'devEui': EUI}),
            ok({'readings': []}),
            ok({'deviceId': EUI, 'created': True}, 201),
            ok({'result': {'devEui': EUI, 'removed': True}}),
            ok({'result': []}),
            ok({'flushed': True}),
            ok({'commands': [], 'sent': []}),
            ok({'id': 1}, 201),
        ])
        self.assertEqual(c.devices.list(), [{'devEui': EUI}])
        c.devices.get(EUI)
        c.devices.readings(EUI, since='now-7d', limit=10)
        c.devices.provision(EUI, app_key='0' * 32, device_profile='Milesight EM310',
                            application='Lot B')
        self.assertTrue(c.devices.decommission(EUI)['removed'])
        c.devices.downlinks.list(EUI)
        c.devices.downlinks.flush(EUI)
        c.devices.commands.list(EUI)
        c.devices.commands.send(EUI, 'reboot')
        self.assertEqual([(r.method, r.url.path) for r in script.requests], [
            ('GET', '/api/v1/data/devices/health'),
            ('GET', f'/api/v1/data/devices/{EUI}'),
            ('GET', f'/api/v1/devices/{EUI}/readings'),
            ('POST', '/api/v1/provisioning/devices'),
            ('DELETE', f'/api/v1/provisioning/devices/{EUI}'),
            ('GET', f'/api/v1/devices/{EUI}/downlinks'),
            ('DELETE', f'/api/v1/devices/{EUI}/downlinks'),
            ('GET', f'/api/v1/devices/{EUI}/commands'),
            ('POST', f'/api/v1/devices/{EUI}/commands/reboot'),
        ])
        self.assertEqual(script.requests[2].url.params['since'], 'now-7d')
        self.assertEqual(body_of(script.requests[3]), {
            'devEui': EUI, 'appKey': '0' * 32, 'deviceProfile': 'Milesight EM310',
            'application': 'Lot B'})
        self.assertEqual(body_of(script.requests[8]), {'params': {}})


class Claiming(unittest.TestCase):
    def test_routes(self):
        tid = '9d3c1a7e-5f2b-4c8d-a1e0-7b6f5d4c3b2a'
        c, script, _ = client([
            ok({'devEui': EUI, 'created': True}, 201),
            ok({'devEui': EUI, 'claimCode': 'K7QH2M9XRB4TWNCP'}, 201),
            ok({'result': []}),
            ok({'result': [{'devEui': EUI, 'claimCode': 'K7QH2M9XRB4TWNCP'}]}, 201),
            ok({'result': []}),
            ok({'id': tid}, 201),
            ok({'id': tid, 'status': 'accepted'}),
        ])
        c.devices.claim(qr='LW:D0:0000000000000000:A84041000181C061:00000000:OABCDEF12',
                        application='Lot B')
        c.devices.release(EUI, confirm=EUI)
        c.devices.registry.list(status='unclaimed')
        c.devices.registry.import_devices(csv='DevEUI,AppKey', profile_id='A1B2C3D4')
        c.devices.transfers.list(direction='incoming', status='open')
        c.devices.transfers.offer('facilities', application='Lot B', confirm='Lot B')
        c.devices.transfers.accept(tid, confirm='Lot B')
        self.assertEqual([(r.method, r.url.path) for r in script.requests], [
            ('POST', '/api/v1/devices/claim'),
            ('POST', f'/api/v1/devices/{EUI}/release'),
            ('GET', '/api/v1/device-registry'),
            ('POST', '/api/v1/device-registry'),
            ('GET', '/api/v1/device-transfers'),
            ('POST', '/api/v1/device-transfers'),
            ('POST', f'/api/v1/device-transfers/{tid}/accept'),
        ])
        self.assertEqual(body_of(script.requests[0]), {
            'qr': 'LW:D0:0000000000000000:A84041000181C061:00000000:OABCDEF12', 'application': 'Lot B'})
        self.assertEqual(body_of(script.requests[1]), {'confirm': EUI})
        self.assertEqual(body_of(script.requests[3]), {'csv': 'DevEUI,AppKey', 'profileId': 'A1B2C3D4'})
        self.assertEqual(body_of(script.requests[5]), {
            'toOrg': 'facilities', 'confirm': 'Lot B', 'application': 'Lot B'})
        self.assertEqual(script.requests[4].url.params['direction'], 'incoming')


class DeviceTypes(unittest.TestCase):
    def test_routes(self):
        c, script, _ = client([
            ok({'result': []}),
            ok({'result': []}),
            ok({'oid': 'abc', 'source': ''}),
            ok({'deployed': True}),
            ok({'id': 't'}),
            ok({'id': 't'}),
        ])
        c.device_types.list()
        c.device_types.versions('t')
        c.device_types.version('t')
        c.device_types.deploy('t', device_profile_id='p')
        c.device_types.set_quantities('t', {'temp': {'quantity': 'temperature'}, 'old': None})
        c.device_types.set_value_aliases('t', {'type': {'OLD': 'NEW'}})
        self.assertEqual([(r.method, r.url.path) for r in script.requests], [
            ('GET', '/api/v1/device-types'),
            ('GET', '/api/v1/device-types/t/versions'),
            ('GET', '/api/v1/device-types/t/versions/HEAD'),
            ('POST', '/api/v1/device-types/t/deploy'),
            ('PUT', '/api/v1/device-types/t/quantities'),
            ('PATCH', '/api/v1/device-types/t'),
        ])
        self.assertEqual(body_of(script.requests[3]), {'deviceProfileId': 'p'})
        self.assertEqual(body_of(script.requests[4]),
                         {'temp': {'quantity': 'temperature'}, 'old': None})
        self.assertEqual(body_of(script.requests[5]), {'valueAliases': {'type': {'OLD': 'NEW'}}})


class Onboarding(unittest.TestCase):
    def test_routes(self):
        c, script, _ = client([
            ok({'result': []}),
            ok({'result': []}),
            ok({'id': 's1', 'status': 'identifying'}, 202),
            ok({'id': 's1'}),
            ok({'id': 's1', 'status': 'deploying'}),
            ok({'rows': [], 'problems': []}),
            ok({'id': 's1', 'status': 'abandoned'}),
            ok({'windowDays': 30}),
        ])
        c.onboarding.catalog('em310')
        c.onboarding.sessions.list()
        c.onboarding.sessions.start(datasheet_pdf=b'%PDF-1.7', vendor='Milesight')
        c.onboarding.sessions.get('s1')
        c.onboarding.accept('s1', field_schema={'temperature': {'quantity': 'temperature'}})
        c.onboarding.register_devices('s1', qr=['LW:D0:...'], dry_run=True)
        c.onboarding.abandon('s1')
        c.onboarding.metrics()
        self.assertEqual([(r.method, r.url.path) for r in script.requests], [
            ('GET', '/api/v1/onboarding/catalog'),
            ('GET', '/api/v1/onboarding/sessions'),
            ('POST', '/api/v1/onboarding/sessions'),
            ('GET', '/api/v1/onboarding/sessions/s1'),
            ('POST', '/api/v1/onboarding/sessions/s1/accept'),
            ('POST', '/api/v1/onboarding/sessions/s1/devices'),
            ('POST', '/api/v1/onboarding/sessions/s1/abandon'),
            ('GET', '/api/v1/onboarding/metrics'),
        ])
        self.assertEqual(body_of(script.requests[2]),
                         {'datasheetPdf': 'JVBERi0xLjc=', 'vendor': 'Milesight'})
        self.assertEqual(body_of(script.requests[5]), {'qr': ['LW:D0:...'], 'dryRun': True})

    def test_start_over_the_working_cap_is_not_retried(self):
        c, script, slept = client([ok({'error': '5 sessions are still working.'}, 429)])
        with self.assertRaises(pulzr.RateLimitError):
            c.onboarding.sessions.start(catalog={'source': 'parkeze', 'id': 'x'})
        self.assertEqual(len(script.requests), 1)
        self.assertEqual(slept, [])

    def test_watch_yields_until_end(self):
        frames = ''.join([
            ': open\n\n',
            f'event: session\ndata: {json.dumps({"id": "s1", "status": "waiting_for_uplink"})}\n\n',
            ': tick\n\n',
            f'event: join\ndata: {json.dumps({"devEui": EUI, "time": "t"})}\n\n',
            f'event: first_uplink\ndata: {json.dumps({"devEui": EUI, "secondsToFirstUplink": 41})}\n\n',
            'event: end\ndata: {"reason": "deadline"}\n\n',
            'event: session\ndata: {}\n\n',
        ])
        c, script, _ = client([sse(frames)])
        got = list(c.onboarding.watch('s1'))
        self.assertEqual([name for name, _ in got], ['session', 'join', 'first_uplink', 'end'])
        self.assertEqual(got[2][1]['secondsToFirstUplink'], 41)
        self.assertEqual(script.requests[0].url.path, '/api/v1/onboarding/sessions/s1/watch')


class Integrations(unittest.TestCase):
    def test_routes(self):
        iid, did = '6f1d2c3b-4a5e-4f60-9b7a-8c9d0e1f2a3b', '4e6a8c0e-2b4d-4f6a-8c0e-2b4d6f8a0c3e'
        c, script, _ = client([
            ok({'result': [{'id': 'influxdb'}]}),
            ok({'id': iid, 'secretsSet': ['token']}, 201),
            ok({'id': iid}),
            ok({'deliveryId': did, 'eventId': 'evt_1', 'request': {}}, 202),
            ok({'result': []}),
            ok({'id': did, 'status': 'pending'}, 202),
            ok({'result': [{'id': iid}]}),
            httpx.Response(204),
        ])
        self.assertEqual(c.integrations.templates(), [{'id': 'influxdb'}])
        c.integrations.create('influxdb', 'Fleet history', {'url': 'https://influx.example.com',
                                                            'bucket': 'b', 'token': 't'},
                              event_types=['uplink.received'])
        c.integrations.update(iid, settings={'bucket': 'fleet'}, enabled=True)
        c.integrations.test(iid, dev_eui=EUI)
        c.integrations.deliveries(iid, status='failed', limit=5)
        c.integrations.retry_delivery(did)
        c.integrations.list()
        self.assertIsNone(c.integrations.delete(iid))
        self.assertEqual([(r.method, r.url.path) for r in script.requests], [
            ('GET', '/api/v1/integrations/templates'),
            ('POST', '/api/v1/integrations'),
            ('PATCH', f'/api/v1/integrations/{iid}'),
            ('POST', f'/api/v1/integrations/{iid}/test'),
            ('GET', f'/api/v1/integrations/{iid}/deliveries'),
            ('POST', f'/api/v1/integrations/deliveries/{did}/retry'),
            ('GET', '/api/v1/integrations'),
            ('DELETE', f'/api/v1/integrations/{iid}'),
        ])
        self.assertEqual(body_of(script.requests[1]), {
            'template': 'influxdb', 'name': 'Fleet history',
            'settings': {'url': 'https://influx.example.com', 'bucket': 'b', 'token': 't'},
            'eventTypes': ['uplink.received']})
        self.assertEqual(body_of(script.requests[2]), {'settings': {'bucket': 'fleet'}, 'enabled': True})
        self.assertEqual(body_of(script.requests[3]), {'devEui': EUI})
        self.assertEqual(script.requests[4].url.params['status'], 'failed')


class Readings(unittest.TestCase):
    def test_latest_and_quantities(self):
        c, script, _ = client([ok({'result': [{'devEui': EUI, 'readings': {'temperature': 21.4}}]}),
                               ok({'result': [{'id': 'temperature'}]})])
        rows = c.readings.latest('temperature', application_id='app')
        self.assertEqual(rows[0]['readings']['temperature'], 21.4)
        self.assertEqual(c.quantities.list()[0]['id'], 'temperature')
        self.assertEqual(script.requests[0].url.params['applicationId'], 'app')



class Sql(unittest.TestCase):
    def test_query_and_limit(self):
        result = {'columns': [{'name': 'dev_eui', 'type': 'text'}], 'rows': [[EUI]],
                  'rowCount': 1, 'truncated': False, 'elapsedMs': 4}
        c, script, _ = client([ok(result), ok(result)])
        self.assertEqual(c.sql('select dev_eui from devices', limit=5000)['rows'], [[EUI]])
        c.sql('select 1')
        self.assertEqual([(r.method, r.url.path) for r in script.requests],
                         [('POST', '/api/v1/sql')] * 2)
        self.assertEqual(body_of(script.requests[0]), {'query': 'select dev_eui from devices', 'limit': 5000})
        # No limit sent means the server's default, not a null it must read.
        self.assertEqual(body_of(script.requests[1]), {'query': 'select 1'})

    def test_refused_carries_the_position(self):
        c, script, _ = client([ok({'error': 'column "foo" does not exist', 'position': 8}, 400)])
        with self.assertRaises(pulzr.ValidationError) as caught:
            c.sql('select foo from devices')
        self.assertEqual(caught.exception.body['position'], 8)
        self.assertEqual(len(script.requests), 1)

if __name__ == '__main__':
    unittest.main()
