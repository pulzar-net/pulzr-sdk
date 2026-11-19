"""The `pulzr` command line.

What is pinned, and why:

- The key never reaches stdout or stderr, on success, on a refusal, under
  --debug or in `config show`; and the file holding it is 0600 from its
  first byte. A key in a CI log acts as its owner until someone notices.
- Flags beat the environment beat the file, so a CI job's PULZR_API_KEY
  is not quietly replaced by a stored login.
- Each verb sends the request its route reads (method, path, query, body),
  checked against net-api/routes as the SDK's own tests are.
- `pulzr api` dispatches from a spec: path parameters into the path,
  the rest into the query, and the spec is cached per base URL for a day.
  tests/fixtures/openapi.json is cut from net-api/openapi/openapi.yaml, and
  Fixture below holds it to the real one when both are present.
- `events tail` resumes from the last cursor after a drop, and Ctrl-C ends
  it with 130 and the position to resume from.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import httpx

from pulzr.cli import commands, run
from pulzr.cli import spec as spec_module
from support import Scripted, broken_sse, ok, sse

KEY = 'pzk_3f9a1c2e_' + 'Q' * 40
OTHER_KEY = 'pzk_0badc0de_' + 'Z' * 40
EUI = 'a84041000181c061'
FIXTURE = Path(__file__).parent / 'fixtures' / 'openapi.json'
REAL_SPEC = Path(__file__).resolve().parents[3] / 'net-api' / 'openapi' / 'openapi.yaml'

ME = {'sub': 'u1', 'name': None, 'email': None, 'org': {'alias': 'usc'},
      'scopes': ['data:read', 'devices:read']}


class Stdin(io.StringIO):
    def __init__(self, text: str = '', tty: bool = False) -> None:
        super().__init__(text)
        self.tty = tty

    def isatty(self) -> bool:
        return self.tty


class Base(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(self.home), True)
        self.config = self.home / 'pulzr' / 'config.json'

    def env(self, **extra):
        env = {'PULZR_CONFIG': str(self.config), 'PULZR_BASE_URL': 'https://net.test'}
        env.update(extra)
        return {k: v for k, v in env.items() if v is not None}

    def cli(self, *argv, replies=(), env=None, stdin='', tty=False):
        script = Scripted(replies)
        out, err, slept = io.StringIO(), io.StringIO(), []
        code = run(list(argv), env=self.env(**(env or {})), stdin=Stdin(stdin, tty),
                   stdout=out, stderr=err, transport=httpx.MockTransport(script),
                   sleep=slept.append)
        return SimpleNamespace(code=code, out=out.getvalue(), err=err.getvalue(),
                               requests=script.requests, slept=slept)

    def store(self, data, mode=0o600):
        self.config.parent.mkdir(parents=True, exist_ok=True)
        self.config.write_text(json.dumps(data))
        os.chmod(str(self.config), mode)

    def keyed(self, *argv, **kwargs):
        env = dict(kwargs.pop('env', None) or {})
        env.setdefault('PULZR_API_KEY', KEY)
        return self.cli(*argv, env=env, **kwargs)

    def assertNoKey(self, result, *keys):
        for key in keys or (KEY,):
            self.assertNotIn(key, result.out)
            self.assertNotIn(key, result.err)
            # Nor any long piece of its secret half.
            self.assertNotIn(key[13:33], result.out + result.err)


# ── the key ──────────────────────────────────────────────────────────────────

class Login(Base):
    def test_key_from_stdin_checked_and_stored_0600(self):
        r = self.cli('login', '--key', '-', '-o', 'json', stdin=KEY + '\n', replies=[ok(ME)])
        self.assertEqual(r.code, 0, r.err)
        sent = r.requests[0]
        self.assertEqual((sent.method, sent.url.path), ('GET', '/api/v1/me'))
        self.assertEqual(sent.headers['Authorization'], f'Bearer {KEY}')
        self.assertEqual(stat.S_IMODE(self.config.stat().st_mode), 0o600)
        stored = json.loads(self.config.read_text())
        self.assertEqual(stored['apiKey'], KEY)
        self.assertEqual(stored['baseUrl'], 'https://net.test')
        shown = json.loads(r.out)
        self.assertEqual(shown['key'], 'pzk_3f9a1c2e_...')
        self.assertEqual(shown['org'], 'usc')
        self.assertNoKey(r)

    def test_prompt_is_hidden(self):
        with mock.patch.object(commands.getpass, 'getpass', return_value=KEY) as prompt:
            r = self.cli('login', replies=[ok(ME)], tty=True)
        self.assertEqual(r.code, 0, r.err)
        prompt.assert_called_once()
        self.assertEqual(json.loads(self.config.read_text())['apiKey'], KEY)
        self.assertNoKey(r)

    def test_no_terminal_and_no_stdin_flag_is_usage(self):
        r = self.cli('login')
        self.assertEqual(r.code, 2)
        self.assertFalse(self.config.exists())

    def test_key_on_the_command_line_refused_and_not_echoed(self):
        r = self.cli('login', '--key', KEY)
        self.assertEqual(r.code, 2)
        self.assertEqual(r.requests, [])
        self.assertNoKey(r)

    def test_refused_key_not_stored_and_not_echoed(self):
        r = self.cli('login', '--key', '-', stdin=KEY,
                     replies=[ok({'error': 'Invalid API key'}, 401)])
        self.assertEqual(r.code, 1)
        self.assertIn('Invalid API key', r.err)
        self.assertFalse(self.config.exists())
        self.assertNoKey(r)

    def test_existing_file_is_narrowed(self):
        self.store({'apiKey': KEY, 'baseUrl': 'https://net.test'}, mode=0o644)
        r = self.cli('config', 'show', '-o', 'json')
        self.assertEqual(r.code, 0, r.err)
        self.assertEqual(stat.S_IMODE(self.config.stat().st_mode), 0o600)

    def test_login_keeps_other_settings_and_stays_0600(self):
        self.store({'org': 'usc', 'apiKey': OTHER_KEY}, mode=0o640)
        r = self.cli('login', '--key', '-', stdin=KEY, replies=[ok(ME)])
        self.assertEqual(r.code, 0, r.err)
        stored = json.loads(self.config.read_text())
        self.assertEqual((stored['apiKey'], stored['org']), (KEY, 'usc'))
        self.assertEqual(stat.S_IMODE(self.config.stat().st_mode), 0o600)
        self.assertNoKey(r, KEY, OTHER_KEY)

    def test_env_key_named_when_it_will_win(self):
        r = self.cli('login', '--key', '-', stdin=KEY, replies=[ok(ME)],
                     env={'PULZR_API_KEY': OTHER_KEY})
        self.assertEqual(r.code, 0, r.err)
        self.assertIn('pzk_0badc0de_...', r.err)
        self.assertNoKey(r, KEY, OTHER_KEY)

    def test_logout(self):
        self.store({'apiKey': KEY, 'org': 'usc'})
        r = self.cli('logout')
        self.assertEqual(r.code, 0)
        self.assertEqual(json.loads(self.config.read_text()), {'org': 'usc'})
        self.assertIn('pzk_3f9a1c2e_...', r.err)
        self.assertNoKey(r)
        self.store({'apiKey': KEY})
        self.cli('logout')
        self.assertFalse(self.config.exists())


class Secrecy(Base):
    def test_config_show_both_formats(self):
        self.store({'apiKey': KEY})
        for fmt in ('json', 'table'):
            r = self.cli('config', 'show', '-o', fmt)
            self.assertEqual(r.code, 0, r.err)
            self.assertIn('pzk_3f9a1c2e_...', r.out)
            self.assertIn('config file', r.out)
            self.assertNoKey(r)

    def test_debug_masks_the_header(self):
        r = self.keyed('devices', 'list', '--debug', replies=[ok({'result': []})])
        self.assertEqual(r.code, 0, r.err)
        self.assertIn('> GET https://net.test/api/v1/data/devices/health', r.err)
        self.assertIn('Bearer pzk_3f9a1c2e_...', r.err)
        self.assertIn('< 200', r.err)
        self.assertNoKey(r)

    def test_error_that_echoes_the_key_is_redacted(self):
        for fmt in ('json', 'table'):
            r = self.keyed('webhooks', 'list', '-o', fmt,
                           replies=[ok({'error': f'Unknown key {KEY}'}, 401)])
            self.assertEqual(r.code, 1)
            self.assertIn('Unknown key pzk_3f9a1c2e_...', r.err)
            self.assertNoKey(r)

    def test_no_key_is_usage(self):
        r = self.cli('devices', 'list')
        self.assertEqual(r.code, 2)
        self.assertIn('pulzr login', r.err)
        self.assertEqual(r.requests, [])


class Precedence(Base):
    def test_env_key_beats_file(self):
        self.store({'apiKey': OTHER_KEY})
        r = self.keyed('devices', 'list', replies=[ok({'result': []})])
        self.assertEqual(r.requests[0].headers['Authorization'], f'Bearer {KEY}')
        r = self.cli('devices', 'list', replies=[ok({'result': []})])
        self.assertEqual(r.requests[0].headers['Authorization'], f'Bearer {OTHER_KEY}')

    def test_base_url_flag_env_file(self):
        self.store({'apiKey': KEY, 'baseUrl': 'https://file.test'})
        cases = [
            ((), {'PULZR_BASE_URL': None}, 'file.test'),
            ((), {'PULZR_BASE_URL': 'https://env.test'}, 'env.test'),
            (('--base-url', 'https://flag.test'), {'PULZR_BASE_URL': 'https://env.test'},
             'flag.test'),
        ]
        for flags, env, host in cases:
            r = self.cli('devices', 'list', *flags, env=env, replies=[ok({'result': []})])
            self.assertEqual(r.code, 0, r.err)
            self.assertEqual(r.requests[0].url.host, host)

    def test_org_flag_before_or_after_the_verb(self):
        for argv in (('--org', 'usc', 'devices', 'list'), ('devices', 'list', '--org', 'usc')):
            r = self.keyed(*argv, replies=[ok({'result': []})])
            self.assertEqual(r.requests[0].headers['X-Active-Org'], 'usc')
        r = self.keyed('devices', 'list', replies=[ok({'result': []})])
        self.assertNotIn('X-Active-Org', r.requests[0].headers)
        r = self.keyed('devices', 'list', env={'PULZR_ORG': 'env-org'},
                       replies=[ok({'result': []})])
        self.assertEqual(r.requests[0].headers['X-Active-Org'], 'env-org')


# ── the verbs ────────────────────────────────────────────────────────────────

def sent(r, i=0):
    request = r.requests[i]
    return request.method, request.url.path, dict(request.url.params)


def body(r, i=0):
    return json.loads(r.requests[i].content)


class Verbs(Base):
    def test_devices(self):
        r = self.keyed('devices', 'list', replies=[ok({'online': 1, 'offline': 0, 'result': [
            {'devEui': EUI, 'name': 'Bay 3', 'online': True, 'lastSeen': '2026-10-13T14:02:11+00:00',
             'rssi': -97, 'snr': 7.5}]})])
        self.assertEqual(sent(r), ('GET', '/api/v1/data/devices/health', {}))
        self.assertEqual(json.loads(r.out)[0]['devEui'], EUI)

        r = self.keyed('devices', 'get', EUI, replies=[ok({'devEui': EUI})])
        self.assertEqual(sent(r), ('GET', f'/api/v1/data/devices/{EUI}', {}))

        r = self.keyed('devices', 'readings', EUI, '--since', 'now-7d', '--limit', '5',
                       replies=[ok({'devEui': EUI, 'readings': [], 'rows': []})])
        self.assertEqual(sent(r), ('GET', f'/api/v1/devices/{EUI}/readings',
                                   {'since': 'now-7d', 'limit': '5'}))

    def test_readings(self):
        r = self.keyed('readings', 'latest', 'temperature', '--device', EUI,
                       '--device', 'a84041000181c062,a84041000181c063', '--application', 'app1',
                       replies=[ok({'result': []})])
        self.assertEqual(sent(r), ('GET', '/api/v1/readings/latest', {
            'quantity': 'temperature', 'applicationId': 'app1',
            'devices': f'{EUI},a84041000181c062,a84041000181c063'}))

        r = self.keyed('readings', 'series', 'temperature', '--since', 'now-7d', '--interval', '1h',
                       '--aggregate', 'max', '--group-by', 'device', '-o', 'table',
                       replies=[ok({'keys': [EUI], 'names': {EUI: 'Office 2F'}, 'series': [
                           {'t': '2026-10-12T18:00:00+00:00', EUI: 22.1}]})])
        self.assertEqual(sent(r), ('GET', '/api/v1/readings', {
            'quantity': 'temperature', 'from': 'now-7d', 'interval': '1h', 'aggregate': 'max',
            'groupBy': 'device'}))
        header, row = r.out.splitlines()
        self.assertEqual(header.split(), ['TIME', 'Office', '2F'])
        self.assertEqual(row.split(), ['2026-10-12T18:00:00+00:00', '22.1'])

    def test_webhooks(self):
        r = self.keyed('webhooks', 'list', replies=[ok({'result': []})])
        self.assertEqual(sent(r), ('GET', '/api/v1/webhooks', {}))

        r = self.keyed('webhooks', 'create', 'https://example.com/hook', '--event',
                       'device.offline,gateway.offline', '--event', 'uplink.received',
                       '--description', 'pager', '-o', 'table',
                       replies=[ok({'id': 'w1', 'secret': 'whsec_x'}, 201)])
        self.assertEqual(sent(r)[:2], ('POST', '/api/v1/webhooks'))
        self.assertEqual(body(r), {'url': 'https://example.com/hook', 'description': 'pager',
                                   'eventTypes': ['device.offline', 'gateway.offline',
                                                  'uplink.received']})
        self.assertIn('whsec_x', r.out)
        self.assertIn('shown once', r.err)

        r = self.keyed('webhooks', 'create', 'https://example.com/hook')
        self.assertEqual((r.code, r.requests), (2, []))

        r = self.keyed('webhooks', 'test', 'w1', replies=[ok({'deliveryId': 'd1', 'eventId': 'e'}, 202)])
        self.assertEqual(sent(r), ('POST', '/api/v1/webhooks/w1/test', {}))

    def test_onboarding(self):
        pdf = self.home / 'sheet.pdf'
        pdf.write_bytes(b'%PDF-1.7')
        r = self.keyed('onboarding', 'start', '--datasheet', str(pdf), '--vendor', 'Milesight',
                       replies=[ok({'id': 's1', 'status': 'identifying'}, 202)])
        self.assertEqual(sent(r)[:2], ('POST', '/api/v1/onboarding/sessions'))
        self.assertEqual(body(r), {'datasheetPdf': 'JVBERi0xLjc=', 'vendor': 'Milesight'})

        r = self.keyed('onboarding', 'start', '--catalog', 'parkeze:t1',
                       replies=[ok({'id': 's1'}, 202)])
        self.assertEqual(body(r), {'catalog': {'source': 'parkeze', 'id': 't1'}})
        self.assertEqual(self.keyed('onboarding', 'start').code, 2)

        r = self.keyed('onboarding', 'status', 's1', '-o', 'table',
                       replies=[ok({'id': 's1', 'status': 'waiting_for_uplink'})])
        self.assertEqual(sent(r), ('GET', '/api/v1/onboarding/sessions/s1', {}))
        self.assertIn('waiting_for_uplink', r.out)

        r = self.keyed('onboarding', 'status', 's1', '--watch', replies=[sse(
            'event: session\ndata: {"status": "waiting_for_uplink"}\n\n'
            'event: first_uplink\ndata: {"devEui": "a84041000181c061"}\n\n'
            'event: end\ndata: {"reason": "live"}\n\n')])
        self.assertEqual(sent(r), ('GET', '/api/v1/onboarding/sessions/s1/watch', {}))
        self.assertEqual([json.loads(line)['event'] for line in r.out.splitlines()],
                         ['session', 'first_uplink', 'end'])

        sheet = self.home / 'devices.csv'
        sheet.write_text(f'DevEUI,JoinEUI,AppKey,Name\n{EUI},{"0" * 16},{"1" * 32},Bay 3\n')
        r = self.keyed('onboarding', 'register', 's1', '--csv', f'@{sheet}', '--dry-run',
                       '--application', 'Lot B', replies=[ok({'rows': [], 'problems': []})])
        self.assertEqual(sent(r)[:2], ('POST', '/api/v1/onboarding/sessions/s1/devices'))
        self.assertEqual(body(r), {'csv': sheet.read_text(), 'application': 'Lot B',
                                   'dryRun': True})

        r = self.keyed('onboarding', 'register', 's1', '--qr', 'LW:D0:1:2:3', '--devices', '-',
                       stdin=json.dumps([{'devEui': EUI, 'appKey': '1' * 32}]),
                       replies=[ok({'result': [], 'session': {}}, 201)])
        self.assertEqual(body(r), {'qr': ['LW:D0:1:2:3'],
                                   'devices': [{'devEui': EUI, 'appKey': '1' * 32}]})

    def test_downlinks(self):
        r = self.keyed('downlinks', 'send', EUI, '--port', '10', '--hex', '01 02', '--confirmed',
                       replies=[ok({'id': 'q1'}, 201)])
        self.assertEqual(sent(r)[:2], ('POST', f'/api/v1/devices/{EUI}/downlinks'))
        self.assertEqual(body(r), {'fPort': 10, 'data': 'AQI=', 'confirmed': True})

        r = self.keyed('downlinks', 'send', EUI, '--port', '85', '--object', '{"reboot": true}',
                       replies=[ok({'id': 'q2'}, 201)])
        self.assertEqual(body(r), {'fPort': 85, 'object': {'reboot': True}, 'confirmed': False})

        r = self.keyed('downlinks', 'send', EUI, '--port', '1', '--base64', 'AQ==', '--hex', '01')
        self.assertEqual((r.code, r.requests), (2, []))
        r = self.keyed('downlinks', 'send', EUI, '--port', '1', '--base64', 'not base64!')
        self.assertEqual(r.code, 2)

    def test_agents(self):
        r = self.keyed('agents', 'run', 'a1', replies=[ok({'id': 'r1', 'status': 'queued'}, 202)])
        self.assertEqual(sent(r), ('POST', '/api/v1/agents/a1/run', {}))

        r = self.keyed('agents', 'findings', '--status', 'open', '--severity', 'critical',
                       replies=[ok({'result': []})])
        self.assertEqual(sent(r), ('GET', '/api/v1/agents/findings',
                                   {'status': 'open', 'severity': 'critical'}))

    def test_simulator(self):
        r = self.keyed('simulator', 'start', 'parking', '--count', '3', '--interval', '600', '--hours', '24',
                       '-o', 'table',
                       replies=[ok({'id': 'sim-1', 'expiresAt': '2026-11-17T04:00:00+00:00',
                                    'devices': [{'devEui': EUI, 'name': 'Parking sensor 1'}]}, 201)])
        self.assertEqual(sent(r)[:2], ('POST', '/api/v1/simulator/simulations'))
        self.assertEqual(body(r), {'preset': 'parking', 'count': 3, 'intervalSeconds': 600, 'expiresInHours': 24})
        self.assertIn(EUI, r.out)
        self.assertIn('sim-1', r.err)
        r = self.keyed('simulator', 'list', '-o', 'table',
                       replies=[ok({'result': [{'id': 'sim-1', 'name': 'Lot A', 'deviceTypeName': 'Simulated Lot A',
                                                'devices': [{}, {}], 'intervalSeconds': 900,
                                                'expiresAt': '2026-11-17T04:00:00+00:00'}]})])
        self.assertEqual(sent(r)[:2], ('GET', '/api/v1/simulator/simulations'))
        self.assertIn('Lot A', r.out)
        r = self.keyed('simulator', 'remove', 'sim-1', replies=[ok({'result': {'id': 'sim-1', 'removed': True}})])
        self.assertEqual(sent(r)[:2], ('DELETE', '/api/v1/simulator/simulations/sim-1'))


class Output(Base):
    ROWS = {'online': 1, 'offline': 1, 'result': [
        {'devEui': EUI, 'name': 'Bay 3', 'online': True, 'lastSeen': '2026-10-13T14:02:11+00:00',
         'rssi': -97, 'snr': 7.5, 'applicationId': 'app1'},
        {'devEui': 'a84041000181c062', 'name': None, 'online': False, 'lastSeen': None,
         'rssi': None, 'snr': None}]}

    def test_json_is_the_response(self):
        r = self.keyed('devices', 'list', '-o', 'json', replies=[ok(self.ROWS)])
        self.assertEqual(json.loads(r.out), self.ROWS['result'])

    def test_table_is_aligned_columns(self):
        r = self.keyed('devices', 'list', '-o', 'table', replies=[ok(self.ROWS)])
        lines = r.out.splitlines()
        self.assertEqual(lines[0].split(), ['DEV', 'EUI', 'NAME', 'ONLINE', 'LAST', 'SEEN',
                                            'RSSI', 'SNR'])
        self.assertEqual(lines[1].index('Bay 3'), lines[0].index('NAME'))
        self.assertEqual(lines[2].split()[:3], ['a84041000181c062', '-', 'false'])
        self.assertNotIn('\x1b', r.out)
        self.assertTrue(all(line == line.rstrip() for line in lines))

    def test_default_is_json_off_a_terminal(self):
        r = self.keyed('devices', 'list', replies=[ok(self.ROWS)])
        self.assertEqual(json.loads(r.out), self.ROWS['result'])

    def test_api_error_exit_1_body_on_stderr(self):
        refusal = {'error': 'No device with that EUI', 'details': ['devEui: unknown']}
        r = self.keyed('devices', 'get', EUI, '-o', 'json', replies=[ok(refusal, 404)])
        self.assertEqual((r.code, r.out), (1, ''))
        self.assertEqual(json.loads(r.err), refusal)
        r = self.keyed('devices', 'get', EUI, '-o', 'table', replies=[ok(refusal, 404)])
        self.assertEqual(r.err.splitlines(), ['error: 404 No device with that EUI',
                                              '  devEui: unknown'])

    def test_usage_errors_exit_2(self):
        self.assertEqual(self.keyed('devices', 'frobnicate').code, 2)
        self.assertEqual(self.keyed('readings', 'series').code, 2)
        self.assertEqual(self.keyed('devices', 'readings', EUI, '--since', 'yesterday').code, 2)


# ── events tail ──────────────────────────────────────────────────────────────

def envelope(n):
    return {'id': f'evt_{n:026d}', 'type': 'uplink.received', 'apiVersion': '2026-10-01',
            'createdAt': '2026-10-13T14:02:11.402Z', 'org': 'usc', 'subject': EUI,
            'data': {'n': n}}


def message(cursor, n):
    return f'id: {cursor}\ndata: {json.dumps(envelope(n))}\n\n'


def opening(cursor):
    return f'retry: 1500\nevent: ready\nid: {cursor}\ndata: {json.dumps({"cursor": cursor})}\n\n'


def interrupt(request):
    raise KeyboardInterrupt


class Tail(Base):
    def test_resumes_after_a_drop_and_ctrl_c_exits_130(self):
        r = self.keyed('events', 'tail', '--types', 'uplink.received', '--after', 'c0', replies=[
            broken_sse(opening('c0') + message('c1', 1) + ': keep-alive\n\n' + message('c2', 2)),
            sse(opening('c2') + message('c3', 3)),
            interrupt,
        ])
        self.assertEqual(r.code, 130)
        self.assertEqual([json.loads(line)['data']['n'] for line in r.out.splitlines()], [1, 2, 3])
        first, second, third = r.requests
        self.assertEqual(first.url.path, '/api/v1/events/stream')
        self.assertEqual(first.url.params['types'], 'uplink.received')
        self.assertEqual(first.headers['Last-Event-ID'], 'c0')
        self.assertEqual(second.headers['Last-Event-ID'], 'c2')
        self.assertEqual(third.headers['Last-Event-ID'], 'c3')
        self.assertEqual(r.slept, [1.5, 1.5])
        self.assertIn('resume with --after c3', r.err)
        self.assertNoKey(r)

    def test_table_is_one_line_per_event(self):
        r = self.keyed('events', 'tail', '-o', 'table',
                       replies=[sse(opening('c0') + message('c1', 1)), interrupt])
        self.assertEqual(r.code, 130)
        line, = r.out.splitlines()
        self.assertEqual(line.split()[:3], ['2026-10-13T14:02:11.402Z', 'uplink.received', EUI])


# ── pulzr api ──────────────────────────────────────────────────────────────

def spec_reply():
    return ok(json.loads(FIXTURE.read_text()))


class Api(Base):
    def test_path_params_query_and_spec_fetched_without_the_key(self):
        r = self.keyed('api', 'getDevice', '--param', f'devEui={EUI}',
                       replies=[spec_reply(), ok({'devEui': EUI})])
        self.assertEqual(r.code, 0, r.err)
        fetch, call = r.requests
        self.assertEqual(fetch.url.path, '/api/v1/openapi.json')
        self.assertNotIn('Authorization', fetch.headers)
        self.assertEqual((call.method, call.url.path), ('GET', f'/api/v1/data/devices/{EUI}'))
        self.assertEqual(call.headers['Authorization'], f'Bearer {KEY}')
        self.assertEqual(json.loads(r.out), {'devEui': EUI})

        r = self.keyed('api', 'getReadingSeries', '--param', 'quantity=temperature',
                       '--param', f'devices={EUI}', '--param', 'devices=a84041000181c062',
                       '--param', 'X-Active-Org=usc', replies=[ok({'series': []})])
        call, = r.requests
        self.assertEqual(dict(call.url.params), {'quantity': 'temperature',
                                                 'devices': f'{EUI},a84041000181c062'})
        self.assertEqual(call.headers['X-Active-Org'], 'usc')

    def test_path_param_escaped(self):
        r = self.keyed('api', 'getDevice', '--param', 'devEui=../webhooks',
                       replies=[spec_reply(), ok({})])
        self.assertEqual(r.requests[1].url.raw_path, b'/api/v1/data/devices/..%2Fwebhooks')

    def test_body_inline_file_and_stdin(self):
        payload = {'fPort': 10, 'data': 'AQI='}
        f = self.home / 'downlink.json'
        f.write_text(json.dumps(payload))
        for source, stdin in ((json.dumps(payload), ''), (f'@{f}', ''), ('-', json.dumps(payload))):
            self.config.parent.mkdir(parents=True, exist_ok=True)
            replies = [ok({'id': 'q1'}, 201)]
            if not list(self.config.parent.glob('openapi-*.json')):
                replies.insert(0, spec_reply())
            r = self.keyed('api', 'enqueueDownlink', '--param', f'devEui={EUI}', '--body', source,
                           stdin=stdin, replies=replies)
            self.assertEqual(r.code, 0, r.err)
            call = r.requests[-1]
            self.assertEqual((call.method, call.url.path),
                             ('POST', f'/api/v1/devices/{EUI}/downlinks'))
            self.assertEqual(json.loads(call.content), payload)

    def test_usage_errors(self):
        r = self.keyed('api', 'getDevise', replies=[spec_reply()])
        self.assertEqual(r.code, 2)
        self.assertIn('getDevice', r.err)
        r = self.keyed('api', 'getDevice')
        self.assertEqual(r.code, 2)
        self.assertIn('--param devEui=', r.err)
        r = self.keyed('api', 'getDevice', '--param', 'devEui')
        self.assertEqual(r.code, 2)
        r = self.keyed('api', 'enqueueDownlink', '--param', f'devEui={EUI}')
        self.assertEqual(r.code, 2)
        self.assertIn('needs a body', r.err)
        r = self.keyed('api', 'enqueueDownlink', '--param', f'devEui={EUI}', '--body', '{nope')
        self.assertEqual(r.code, 2)
        r = self.keyed('api', 'uploadDatasheet', '--param', 'deviceTypeId=t1', '--body', '{}')
        self.assertEqual(r.code, 2)
        self.assertIn('multipart/form-data', r.err)
        self.assertEqual(r.requests, [])

    def test_list(self):
        r = self.cli('api', '--list', '-o', 'table', replies=[spec_reply()])
        self.assertEqual(r.code, 0, r.err)
        rows = {line.split()[0]: line.split()[1:] for line in r.out.splitlines()[1:]}
        self.assertEqual(rows['getDevice'], ['GET', '/api/v1/data/devices/{devEui}', 'devices:read'])
        self.assertEqual(rows['enqueueDownlink'][2], 'downlinks:write')
        r = self.cli('api', '--list', 'webhook', '-o', 'json')
        self.assertEqual([op['operationId'] for op in json.loads(r.out)], ['listWebhooks'])

    def test_streams(self):
        r = self.keyed('api', 'streamEvents', '--param', 'types=uplink.received', replies=[
            spec_reply(), sse(opening('c0') + message('c1', 1) + 'event: end\nid: c1\ndata: {"reason": "deadline"}\n\n')])
        self.assertEqual(r.code, 0, r.err)
        self.assertEqual(r.requests[1].headers['Accept'], 'text/event-stream')
        lines = [json.loads(line) for line in r.out.splitlines()]
        self.assertEqual([(e['event'], e['id']) for e in lines],
                         [('ready', 'c0'), ('message', 'c1'), ('end', 'c1')])
        self.assertEqual(lines[1]['data']['data'], {'n': 1})

    def test_non_json_response_printed_as_is(self):
        r = self.cli('api', 'getOpenApiYaml', env={'PULZR_API_KEY': KEY},
                     replies=[spec_reply(), httpx.Response(200, text='openapi: 3.1.0\n',
                                                           headers={'Content-Type': 'application/yaml'})])
        self.assertEqual(r.code, 0, r.err)
        self.assertEqual(json.loads(r.out), 'openapi: 3.1.0\n')


class SpecCache(Base):
    def test_cached_per_base_url_for_a_day(self):
        r = self.cli('api', '--list', replies=[spec_reply()])
        self.assertEqual(r.code, 0, r.err)
        cached, = self.config.parent.glob('openapi-*.json')
        self.assertEqual(stat.S_IMODE(cached.stat().st_mode), 0o600)

        self.assertEqual(self.cli('api', '--list').requests, [])

        r = self.cli('api', '--list', '--base-url', 'https://other.test', replies=[spec_reply()])
        self.assertEqual(r.requests[0].url.host, 'other.test')
        self.assertEqual(len(list(self.config.parent.glob('openapi-*.json'))), 2)

        r = self.cli('api', '--list', '--refresh-spec', replies=[spec_reply()])
        self.assertEqual(len(r.requests), 1)

        data = json.loads(cached.read_text())
        data['fetchedAt'] -= spec_module.MAX_AGE + 1
        cached.write_text(json.dumps(data))
        r = self.cli('api', '--list', replies=[spec_reply()])
        self.assertEqual(len(r.requests), 1)

    def test_stale_copy_used_when_refresh_fails(self):
        self.cli('api', '--list', replies=[spec_reply()])
        r = self.cli('api', '--list', '--refresh-spec', replies=[httpx.ConnectError('refused')])
        self.assertEqual(r.code, 0, r.err)
        self.assertIn('using the copy from', r.err)
        self.assertIn('getDevice', r.out)

    def test_no_copy_and_no_server_is_exit_1(self):
        r = self.cli('api', '--list', replies=[httpx.ConnectError('refused')])
        self.assertEqual(r.code, 1)


class Fixture(unittest.TestCase):
    """tests/fixtures/openapi.json is cut from the real spec; held to it."""

    def test_matches_the_real_spec(self):
        try:
            import yaml
        except ImportError:
            self.skipTest('PyYAML is not installed')
        if not REAL_SPEC.exists():
            self.skipTest('not in the monorepo')
        loader = getattr(yaml, 'CSafeLoader', yaml.SafeLoader)
        real = spec_module.operations(yaml.load(REAL_SPEC.read_text(encoding='utf-8'), Loader=loader))
        by_id = {op.id: op for op in real}
        for op in spec_module.operations(json.loads(FIXTURE.read_text())):
            self.assertIn(op.id, by_id)
            have = by_id[op.id]
            self.assertEqual((op.method, op.path, op.scope, op.streams, op.body_types,
                              op.body_required),
                             (have.method, have.path, have.scope, have.streams, have.body_types,
                              have.body_required), op.id)
            self.assertEqual(sorted(op.parameters), sorted(have.parameters), op.id)


if __name__ == '__main__':
    unittest.main()
