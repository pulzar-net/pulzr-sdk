"""The verbs, and the parser that reaches them.

Each verb is a thin call into the SDK and a choice of table columns; the
JSON form is always the response as the API sent it. Global flags are
accepted before or after the verb (`pulzr -o json devices list` and
`pulzr devices list -o json`), because people type them where they think
of them.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import getpass
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from .._client import DEFAULT_BASE_URL, decode, path
from .._sse import SSEDecoder
from .._version import __version__
from . import config, output, spec
from .config import UsageError, mask

_WINDOWS = ['now-1h', 'now-6h', 'now-24h', 'now-7d', 'now-30d', 'now-90d']


def _csv(values: Optional[List[str]]) -> Optional[List[str]]:
    """Repeated flags and comma lists alike: `--device a --device b,c`."""
    if not values:
        return None
    return [v.strip() for value in values for v in value.split(',') if v.strip()]


def _read_arg(value: str, stdin: Any, what: str) -> str:
    """`-` for stdin, `@file` for a file, anything else as given."""
    if value == '-':
        return stdin.read()
    if value.startswith('@'):
        try:
            return Path(value[1:]).expanduser().read_text(encoding='utf-8')
        except OSError as e:
            raise UsageError(f'{what}: cannot read {value[1:]}: {e.strerror}') from None
    return value


def _read_bytes(file: str, what: str) -> bytes:
    try:
        return Path(file).expanduser().read_bytes()
    except OSError as e:
        raise UsageError(f'{what}: cannot read {file}: {e.strerror}') from None


def _json_arg(value: str, stdin: Any, what: str) -> Any:
    text = _read_arg(value, stdin, what)
    try:
        return json.loads(text)
    except ValueError as e:
        raise UsageError(f'{what} is not JSON: {e}') from None


# ── account ──────────────────────────────────────────────────────────────────

def login(ctx: Any, args: Any) -> None:
    if args.key not in (None, '', '-'):
        raise UsageError('give the key on stdin (--key -) or at the prompt; a key on the '
                         'command line is kept in shell history')
    if args.key == '-':
        key = ctx.stdin.readline().strip()
    else:
        if not ctx.stdin.isatty():
            raise UsageError('no terminal to prompt on: pipe the key in with --key -')
        key = getpass.getpass('API key: ').strip()
    if not key:
        raise UsageError('no key given')
    if not key.startswith('pzk_'):
        raise UsageError('that is not an API key; they start pzk_ (Developers > API keys)')
    ctx.secrets.add(key)

    with ctx.client(api_key=key) as client:
        me = client.request('GET', '/api/v1/me')

    s = ctx.settings
    stored = dict(s.file)
    stored['apiKey'] = key
    if s.base_url != DEFAULT_BASE_URL:
        stored['baseUrl'] = s.base_url
    else:
        stored.pop('baseUrl', None)
    config.save(s.path, stored)

    org = (me or {}).get('org') or {}
    ctx.emit({'key': mask(key), 'org': org.get('alias'), 'name': (me or {}).get('name'),
              'scopes': (me or {}).get('scopes'), 'baseUrl': s.base_url, 'config': str(s.path)})
    if ctx.env.get('PULZR_API_KEY') and ctx.env['PULZR_API_KEY'] != key:
        ctx.note(f"PULZR_API_KEY ({mask(ctx.env['PULZR_API_KEY'])}) is set in this shell "
                 'and is used instead of the stored key')


def logout(ctx: Any, args: Any) -> None:
    s = ctx.settings
    stored = dict(s.file)
    key = stored.pop('apiKey', None)
    if not key:
        ctx.note(f'no key stored in {s.path}')
        return
    if stored:
        config.save(s.path, stored)
    else:
        s.path.unlink()
    ctx.note(f'removed {mask(key)} from {s.path}; it works until revoked at /api-keys')


def config_show(ctx: Any, args: Any) -> None:
    s = ctx.settings
    mode = None
    if s.path.exists():
        mode = oct(s.path.stat().st_mode & 0o777)
    ctx.emit({
        'config': str(s.path),
        'mode': mode,
        'key': mask(s.api_key),
        'keyFrom': s.key_source,
        'baseUrl': s.base_url,
        'baseUrlFrom': s.base_url_source,
        'org': s.org,
        'orgFrom': s.org_source,
        'output': ctx.fmt,
    })


# ── devices and readings ─────────────────────────────────────────────────────

def devices_list(ctx: Any, args: Any) -> None:
    with ctx.client() as client:
        rows = client.devices.list()
    ctx.emit(rows, [('DEV EUI', 'devEui'), ('NAME', 'name'), ('ONLINE', 'online'),
                    ('LAST SEEN', 'lastSeen'), ('RSSI', 'rssi'), ('SNR', 'snr')])


def devices_get(ctx: Any, args: Any) -> None:
    with ctx.client() as client:
        ctx.emit(client.devices.get(args.dev_eui))


def devices_readings(ctx: Any, args: Any) -> None:
    with ctx.client() as client:
        data = client.devices.readings(args.dev_eui, since=args.since, limit=args.limit)
    if ctx.fmt == 'json':
        ctx.emit(data)
    else:
        ctx.emit(data.get('readings') or [],
                 [('QUANTITY', 'quantity'), ('CHANNEL', 'channel'), ('VALUE', 'value'),
                  ('UNIT', 'unit'), ('FIELD', 'field'), ('TIME', 'time')])


def readings_latest(ctx: Any, args: Any) -> None:
    with ctx.client() as client:
        rows = client.readings.latest(args.quantity, channel=args.channel,
                                      devices=_csv(args.device),
                                      application_id=args.application,
                                      device_type_id=args.device_type)
    if ctx.fmt == 'json':
        ctx.emit(rows)
        return
    flat = []
    for device in rows:
        units = device.get('units') or {}
        times = device.get('readingTimes') or {}
        for key, value in (device.get('readings') or {}).items():
            flat.append({'devEui': device.get('devEui'), 'name': device.get('name'),
                         'quantity': key, 'value': value, 'unit': units.get(key),
                         'time': times.get(key)})
    ctx.emit(flat, [('DEV EUI', 'devEui'), ('NAME', 'name'), ('QUANTITY', 'quantity'),
                    ('VALUE', 'value'), ('UNIT', 'unit'), ('TIME', 'time')])


def readings_series(ctx: Any, args: Any) -> None:
    with ctx.client() as client:
        data = client.readings.series(args.quantity, channel=args.channel, since=args.since,
                                      interval=args.interval, aggregate=args.aggregate,
                                      group_by=args.group_by, devices=_csv(args.device),
                                      application_id=args.application)
    if ctx.fmt == 'json':
        ctx.emit(data)
        return
    names = data.get('names') or {}
    columns = [('TIME', 't')] + [(names.get(k) or k, k) for k in data.get('keys') or []]
    ctx.emit(data.get('series') or [], columns)


# ── events ───────────────────────────────────────────────────────────────────

def events_tail(ctx: Any, args: Any) -> None:
    client = ctx.client()
    stream = client.events.stream(types=_csv(args.types), subject=args.subject,
                                  after=args.after)
    try:
        for event in stream:
            if ctx.fmt == 'json':
                ctx.out.write(output.to_json(event, indent=None) + '\n')
            else:
                ctx.out.write('  '.join([
                    output.cell(event.get('createdAt')).ljust(24),
                    output.cell(event.get('type')).ljust(22),
                    output.cell(event.get('subject')).ljust(16),
                    output.cell(event.get('data'), 80),
                ]).rstrip() + '\n')
            ctx.out.flush()
    except KeyboardInterrupt:
        # The position, so the next tail picks up where this one stopped.
        if stream.cursor:
            ctx.note(f'resume with --after {stream.cursor}')
        raise
    finally:
        stream.close()
        client.close()


# ── webhooks ─────────────────────────────────────────────────────────────────

def webhooks_list(ctx: Any, args: Any) -> None:
    with ctx.client() as client:
        rows = client.webhooks.list()
    ctx.emit(rows, [('ID', 'id'), ('URL', 'url'), ('EVENTS', lambda w: ','.join(w.get('eventTypes') or [])),
                    ('ENABLED', 'enabled'), ('FAILURES', 'consecutiveFailures'),
                    ('LAST SUCCESS', 'lastSuccessAt')])


def webhooks_create(ctx: Any, args: Any) -> None:
    events = _csv(args.event)
    if not events:
        raise UsageError('name at least one event type with --event (`pulzr api listEventTypes`)')
    with ctx.client() as client:
        created = client.webhooks.create(args.url, events, application_ids=_csv(args.application),
                                         description=args.description)
    ctx.emit(created)
    if ctx.fmt != 'json':
        ctx.note('the secret is shown once; store it now')


def webhooks_test(ctx: Any, args: Any) -> None:
    with ctx.client() as client:
        ctx.emit(client.webhooks.test(args.webhook_id))


# ── onboarding ───────────────────────────────────────────────────────────────

_SESSION = [('ID', 'id'), ('STATUS', 'status'), ('VENDOR', 'vendor'), ('MODEL', 'model'),
            ('TRANSPORT', 'transport'), ('FAILURE', 'failure')]


def _session(ctx: Any, session: Dict[str, Any]) -> None:
    if ctx.fmt == 'json':
        ctx.emit(session)
    else:
        output.pairs({header: session.get(key) for header, key in _SESSION + [
            ('DEVICE TYPE', 'deviceTypeId'), ('DEVICES', 'devices'),
            ('FIRST UPLINK', 'firstUplinkAt'), ('UPDATED', 'updatedAt')]}, ctx.out)


def onboarding_start(ctx: Any, args: Any) -> None:
    catalog = None
    if args.catalog:
        source, sep, ident = args.catalog.partition(':')
        if not sep or not ident:
            raise UsageError('--catalog is SOURCE:ID, e.g. parkeze:3f1c2a9e-...')
        catalog = {'source': source, 'id': ident}
    text = _read_arg(args.text, ctx.stdin, '--text') if args.text else None
    pdf = _read_bytes(args.datasheet, '--datasheet') if args.datasheet else None
    photo = _read_bytes(args.photo, '--photo') if args.photo else None
    if not (catalog or text or pdf or photo):
        raise UsageError('start from --catalog, --datasheet, --text or --photo')
    with ctx.client() as client:
        session = client.onboarding.sessions.start(catalog=catalog, datasheet_pdf=pdf,
                                                   datasheet_text=text, label_photo=photo,
                                                   vendor=args.vendor, model=args.model)
    _session(ctx, session)


def onboarding_status(ctx: Any, args: Any) -> None:
    with ctx.client() as client:
        if not args.watch:
            _session(ctx, client.onboarding.sessions.get(args.session_id))
            return
        for event, data in client.onboarding.watch(args.session_id):
            if ctx.fmt == 'json':
                ctx.out.write(output.to_json({'event': event, 'data': data}, indent=None) + '\n')
            else:
                ctx.out.write(f'{event.ljust(14)}  {output.cell(data, 100)}\n')
            ctx.out.flush()


def onboarding_register(ctx: Any, args: Any) -> None:
    csv_text = _read_arg(args.csv, ctx.stdin, '--csv') if args.csv else None
    devices = _json_arg(args.devices, ctx.stdin, '--devices') if args.devices else None
    if devices is not None and not isinstance(devices, list):
        raise UsageError('--devices is a JSON list of {devEui, joinEui, appKey, name}')
    if not (csv_text or devices or args.qr):
        raise UsageError('give the devices with --csv, --devices or --qr')
    with ctx.client() as client:
        data = client.onboarding.register_devices(args.session_id, devices=devices, qr=args.qr,
                                                  csv=csv_text, application=args.application,
                                                  dry_run=args.dry_run)
    if ctx.fmt == 'json':
        ctx.emit(data)
    elif args.dry_run:
        ctx.emit(data.get('rows') or [], [('DEV EUI', 'devEui'), ('JOIN EUI', 'joinEui'),
                                          ('NAME', 'name'), ('MAC', 'mac'),
                                          ('PROBLEM', 'problem')])
    else:
        ctx.emit(data.get('result') or [], [('DEV EUI', 'devEui'), ('OK', 'ok'),
                                            ('CREATED', 'created'), ('ERROR', 'error')])


# ── downlinks ────────────────────────────────────────────────────────────────

def downlinks_send(ctx: Any, args: Any) -> None:
    given = [x for x in (args.hex, args.base64, args.object) if x is not None]
    if len(given) != 1:
        raise UsageError('give exactly one of --hex, --base64 or --object')
    data: Any = None
    obj = None
    if args.hex is not None:
        try:
            data = bytes.fromhex(re.sub(r'[\s:]', '', args.hex))
        except ValueError:
            raise UsageError('--hex is not hex') from None
    elif args.base64 is not None:
        try:
            base64.b64decode(args.base64, validate=True)
        except (binascii.Error, ValueError):
            raise UsageError('--base64 is not base64') from None
        data = args.base64
    else:
        obj = _json_arg(args.object, ctx.stdin, '--object')
    with ctx.client() as client:
        ctx.emit(client.devices.downlinks.enqueue(args.dev_eui, args.port, data=data, object=obj,
                                                  confirmed=args.confirmed))


# ── agents ───────────────────────────────────────────────────────────────────

def agents_run(ctx: Any, args: Any) -> None:
    with ctx.client() as client:
        ctx.emit(client.agents.run(args.agent_id))


def agents_findings(ctx: Any, args: Any) -> None:
    with ctx.client() as client:
        rows = client.agents.findings.list(status=args.status, severity=args.severity,
                                           agent=args.agent)
    ctx.emit(rows, [('ID', 'id'), ('SEVERITY', 'severity'), ('STATUS', 'status'),
                    ('TITLE', 'title'), ('SUBJECT', 'subject'), ('AGENT', 'agentName'),
                    ('CREATED', 'createdAt')])


# ── simulator ────────────────────────────────────────────────────────────────

_SIMULATION_COLUMNS = [('ID', 'id'), ('NAME', 'name'), ('TYPE', 'deviceTypeName'), ('DEVICES', 'count'),
                       ('INTERVAL S', 'intervalSeconds'), ('EXPIRES', 'expiresAt')]


def _simulation_rows(rows: list) -> list:
    return [{**r, 'count': len(r.get('devices') or [])} for r in rows]


def simulator_start(ctx: Any, args: Any) -> None:
    # The SDK does not wrap the simulator: it is for trying the network, not
    # for code. The route is called as documented; custom fields and
    # behaviours go through `pulzr api createSimulation`.
    body = {'preset': args.preset, 'deviceTypeId': args.type, 'count': args.count, 'name': args.name,
            'intervalSeconds': args.interval, 'utcOffsetMinutes': args.utc_offset,
            'expiresInHours': args.hours}
    with ctx.client() as client:
        data = client.request('POST', '/api/v1/simulator/simulations',
                              json={k: v for k, v in body.items() if v is not None})
    if ctx.fmt == 'json':
        ctx.emit(data)
        return
    ctx.emit(data.get('devices') or [], [('DEV EUI', 'devEui'), ('NAME', 'name')])
    ctx.note(f"simulation {data['id']}, expires {data['expiresAt']}")


def simulator_list(ctx: Any, args: Any) -> None:
    with ctx.client() as client:
        data = client.request('GET', '/api/v1/simulator/simulations')
    if ctx.fmt == 'json':
        ctx.emit(data)
        return
    ctx.emit(_simulation_rows(data.get('result') or []), _SIMULATION_COLUMNS)


def simulator_remove(ctx: Any, args: Any) -> None:
    with ctx.client() as client:
        data = client.request('DELETE', f'/api/v1/simulator/simulations/{args.simulation}')
    ctx.emit(data.get('result') or data)


# ── api ──────────────────────────────────────────────────────────────────────

def api(ctx: Any, args: Any) -> None:
    s = ctx.settings
    document = spec.load(s.base_url, s.path.parent, refresh=args.refresh_spec,
                         transport=ctx.transport, warn=lambda m: ctx.note(f'pulzr: {m}'))
    ops = spec.operations(document)

    if args.list:
        needle = (args.operation or '').lower()
        rows = [op for op in ops if needle in op.id.lower() or needle in op.path.lower()]
        ctx.emit([{'operationId': op.id, 'method': op.method, 'path': op.path,
                   'scope': op.scope} for op in rows],
                 [('OPERATION', 'operationId'), ('METHOD', 'method'), ('PATH', 'path'),
                  ('SCOPE', 'scope')])
        return
    if not args.operation:
        raise UsageError('name an operation, or --list them')

    op = spec.find(ops, args.operation)
    given: Dict[str, List[str]] = {}
    for item in args.param or []:
        name, sep, value = item.partition('=')
        if not sep or not name:
            raise UsageError(f'--param {item!r} is not NAME=VALUE')
        given.setdefault(name, []).append(value)

    url = op.path
    missing = []
    for name in spec.placeholders(op.path):
        values = given.pop(name, None)
        if not values:
            missing.append(name)
            continue
        url = url.replace('{' + name + '}', path('', values[-1])[1:])
    if missing:
        raise UsageError(f"{op.id} needs {', '.join('--param ' + m + '=...' for m in missing)}")

    headers = {'Accept': 'text/event-stream' if op.streams else 'application/json'}
    query: Dict[str, Any] = {}
    for name, values in given.items():
        declared = op.parameters.get(name) or {}
        if declared.get('in') == 'header':
            headers[name] = values[-1]
        else:
            query[name] = values if len(values) > 1 else values[0]

    body = None
    if args.body is not None:
        if op.body_types and 'application/json' not in op.body_types:
            raise UsageError(f"{op.id} takes {', '.join(op.body_types)}; --body sends JSON")
        body = _json_arg(args.body, ctx.stdin, '--body')
    elif op.body_required:
        raise UsageError(f'{op.id} needs a body: --body @file.json, --body - or --body \'{{...}}\'')

    with ctx.client() as client:
        response = client.send(op.method, url, params=query, json=body, headers=headers,
                               stream=op.streams)
        if not op.streams:
            ctx.emit(decode(response))
            return
        try:
            for event in SSEDecoder().iter_events(response.iter_lines()):
                try:
                    data = json.loads(event.data)
                except ValueError:
                    data = event.data
                if ctx.fmt == 'json':
                    ctx.out.write(output.to_json({'event': event.event, 'id': event.id,
                                                  'data': data}, indent=None) + '\n')
                else:
                    ctx.out.write(f'{event.event.ljust(14)}  {output.cell(data, 120)}\n')
                ctx.out.flush()
        finally:
            response.close()


# ── the parser ───────────────────────────────────────────────────────────────

class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # type: ignore[override]
        self.print_usage(sys.stderr)
        self.exit(2, f'pulzr: {message}\n')


def _globals(parser: argparse.ArgumentParser, suppress: bool) -> None:
    # On the top parser with real defaults, and again on every verb with
    # SUPPRESS, so a flag given after the verb is kept and one not given
    # there does not overwrite one given before it.
    d = argparse.SUPPRESS if suppress else None
    g = parser.add_argument_group('global options')
    g.add_argument('--org', default=d, help='org alias to act in (X-Active-Org); a key needs none')
    g.add_argument('-o', '--output', choices=['json', 'table'], default=d,
                   help='default: table on a terminal, json otherwise')
    g.add_argument('--base-url', default=d, help=f'API base URL (default {DEFAULT_BASE_URL})')
    g.add_argument('--debug', action='store_true', default=argparse.SUPPRESS if suppress else False,
                   help='requests and responses on stderr, key masked')


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog='pulzr', description='Pulzr from the command line.')
    parser.add_argument('--version', action='version', version=f'pulzr {__version__}')
    _globals(parser, suppress=False)
    top = parser.add_subparsers(dest='command', metavar='<command>', parser_class=_Parser)
    top.required = True

    def group(name: str, help: str) -> Any:
        p = top.add_parser(name, help=help)
        sub = p.add_subparsers(dest='verb', metavar='<verb>', parser_class=_Parser)
        sub.required = True
        return sub

    def verb(sub: Any, name: str, func: Any, help: str) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help)
        _globals(p, suppress=True)
        p.set_defaults(func=func)
        return p

    p = top.add_parser('login', help='store an API key, after checking it')
    _globals(p, suppress=True)
    p.add_argument('--key', nargs='?', const='', default=None, metavar='-',
                   help='read the key from stdin with `--key -`; otherwise it is prompted for')
    p.set_defaults(func=login)

    p = top.add_parser('logout', help='forget the stored key (it is not revoked)')
    _globals(p, suppress=True)
    p.set_defaults(func=logout)

    sub = group('config', 'the settings in use')
    verb(sub, 'show', config_show, 'settings, where each came from, the key by its prefix')

    sub = group('devices', 'devices that have reported')
    verb(sub, 'list', devices_list, 'every device that has reported, online or not')
    p = verb(sub, 'get', devices_get, 'one device: last uplink, fields, radio, location')
    p.add_argument('dev_eui', metavar='DEV_EUI')
    p = verb(sub, 'readings', devices_readings, "one device's recent canonical readings")
    p.add_argument('dev_eui', metavar='DEV_EUI')
    p.add_argument('--since', choices=_WINDOWS, help='window ending now (default now-24h)')
    p.add_argument('--limit', type=int, help='uplinks, 1-1000 (default 100)')

    sub = group('readings', 'canonical readings across devices')
    p = verb(sub, 'latest', readings_latest, "each device's newest readings")
    p.add_argument('quantity', nargs='?', metavar='QUANTITY', help='e.g. temperature')
    p.add_argument('--channel')
    p.add_argument('--device', action='append', metavar='DEV_EUI', help='repeat, or comma-separate')
    p.add_argument('--application', metavar='ID', help='application id')
    p.add_argument('--device-type', metavar='ID', help='device type id')
    p = verb(sub, 'series', readings_series, 'one quantity over time, bucketed')
    p.add_argument('quantity', metavar='QUANTITY')
    p.add_argument('--channel')
    p.add_argument('--since', choices=_WINDOWS, help='window ending now (default now-24h)')
    p.add_argument('--interval', help='bucket width, e.g. 15m, 1h, 1d')
    p.add_argument('--aggregate', choices=['mean', 'min', 'max', 'last', 'count', 'sum'])
    p.add_argument('--group-by', choices=['none', 'device'])
    p.add_argument('--device', action='append', metavar='DEV_EUI', help='repeat, or comma-separate')
    p.add_argument('--application', metavar='ID', help='application id')

    sub = group('events', 'the event log')
    p = verb(sub, 'tail', events_tail, 'follow events as they happen; Ctrl-C to stop')
    p.add_argument('--types', action='append', metavar='TYPE', help='repeat, or comma-separate')
    p.add_argument('--subject', metavar='ID', help='a device EUI or gateway id')
    p.add_argument('--after', metavar='CURSOR', help='resume after this position, backlog first')

    sub = group('webhooks', 'webhook endpoints')
    verb(sub, 'list', webhooks_list, 'every endpoint and its health')
    p = verb(sub, 'create', webhooks_create, 'add an endpoint (org admin); prints its secret once')
    p.add_argument('url', metavar='URL')
    p.add_argument('--event', action='append', metavar='TYPE', help='repeat, or comma-separate')
    p.add_argument('--application', action='append', metavar='ID', help='only these applications')
    p.add_argument('--description')
    p = verb(sub, 'test', webhooks_test, 'queue a webhook.test delivery to one endpoint')
    p.add_argument('webhook_id', metavar='WEBHOOK_ID')

    sub = group('onboarding', 'a sensor model from datasheet to first uplink')
    p = verb(sub, 'start', onboarding_start, 'start a session')
    p.add_argument('--catalog', metavar='SOURCE:ID', help='a catalog hit: org, parkeze or repository')
    p.add_argument('--datasheet', metavar='FILE.pdf')
    p.add_argument('--text', metavar='@FILE|-|TEXT', help='datasheet text')
    p.add_argument('--photo', metavar='FILE', help='label photo, PNG or JPEG')
    p.add_argument('--vendor')
    p.add_argument('--model')
    p = verb(sub, 'status', onboarding_status, 'where a session is')
    p.add_argument('session_id', metavar='SESSION_ID')
    p.add_argument('--watch', action='store_true', help='follow it until it ends')
    p = verb(sub, 'register', onboarding_register, "register the model's devices")
    p.add_argument('session_id', metavar='SESSION_ID')
    p.add_argument('--csv', metavar='@FILE|-', help='DevEUI, JoinEUI, AppKey, Name; header optional')
    p.add_argument('--devices', metavar='@FILE|-|JSON', help='JSON list of {devEui, joinEui, appKey, name}')
    p.add_argument('--qr', action='append', metavar='TEXT', help='TR005 QR text; repeat')
    p.add_argument('--application', metavar='ID|NAME')
    p.add_argument('--dry-run', action='store_true', help='parse and show the rows; register nothing')

    sub = group('downlinks', 'the downlink queue')
    p = verb(sub, 'send', downlinks_send, 'queue one downlink')
    p.add_argument('dev_eui', metavar='DEV_EUI')
    p.add_argument('--port', type=int, required=True, metavar='FPORT', help='1-223')
    p.add_argument('--hex', metavar='BYTES')
    p.add_argument('--base64', metavar='BYTES')
    p.add_argument('--object', metavar='@FILE|-|JSON', help="for the device profile's codec to encode")
    p.add_argument('--confirmed', action='store_true')

    sub = group('agents', 'background agents and their findings')
    p = verb(sub, 'run', agents_run, 'queue a run now (org admin)')
    p.add_argument('agent_id', metavar='AGENT_ID')
    p = verb(sub, 'findings', agents_findings, 'what agents have reported')
    p.add_argument('--status', choices=['open', 'acknowledged', 'resolved'])
    p.add_argument('--severity', choices=['info', 'warning', 'critical'])
    p.add_argument('--agent', metavar='AGENT_ID')

    sub = group('simulator', 'simulations: temporary devices with no hardware')
    p = verb(sub, 'start', simulator_start, 'start a simulation from a preset or a device type')
    p.add_argument('preset', nargs='?', metavar='PRESET',
                   help='parking, environment, door or water_level (`pulzr api listSimulatorPresets`)')
    p.add_argument('--type', metavar='DEVICE_TYPE_ID', help='simulate a device type instead of a preset')
    p.add_argument('--count', type=int, help='1-10 (default 1)')
    p.add_argument('--name', help='names the devices')
    p.add_argument('--interval', type=int, metavar='SECONDS', help='300-1800 (default 900)')
    p.add_argument('--utc-offset', type=int, metavar='MINUTES', help='whose day they follow')
    p.add_argument('--hours', type=int, help='until it expires, 1-720 (default 168)')
    verb(sub, 'list', simulator_list, 'the organization\'s simulations')
    p = verb(sub, 'remove', simulator_remove, 'remove a simulation and everything its devices stored')
    p.add_argument('simulation', metavar='SIMULATION_ID')

    p = top.add_parser('api', help='call any operation in the API spec')
    _globals(p, suppress=True)
    p.add_argument('operation', nargs='?', metavar='OPERATION_ID')
    p.add_argument('--param', action='append', metavar='NAME=VALUE',
                   help='path, query or header parameter; repeat')
    p.add_argument('--body', metavar='@FILE|-|JSON')
    p.add_argument('--list', action='store_true', help='list operations, filtered by OPERATION_ID')
    p.add_argument('--refresh-spec', action='store_true', help='fetch the spec even if cached')
    p.set_defaults(func=api)
    return parser
