#!/usr/bin/env python3
"""Webhook signature vectors for both SDKs, made by the code that signs.

The SDKs reimplement `shared/events.verify` in two languages. A test each SDK
wrote against its own idea of the format would pass while all three
disagreed, so the vectors come from `events.sign` and the expected answer from
`events.verify`: the server is the reference and the SDKs are tested against
what it actually sends.

Deterministic -- fixed secrets and timestamps -- so `--check` can tell a stale
file from a current one.

    python sdk/fixtures/generate.py          # rewrite webhook-signatures.json
    python sdk/fixtures/generate.py --check  # exit 1 if it is out of date
"""

import base64
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'shared'))

import events  # noqa: E402

OUT = os.path.join(HERE, 'webhook-signatures.json')

T = 1792000000
NEW = 'whsec_' + '1f' * 24
OLD = 'whsec_' + 'a0' * 24
OTHER = 'whsec_' + '77' * 24

BODY = json.dumps(events.envelope(
    'evt_01K7ZQ8V3N4M2X9B6C5D7E8F0G', 'uplink.received', '2026-10-13T14:02:11.402Z',
    'usc', 'a84041000181c061',
    # The shape event-dispatch emits, so the vectors double as an example.
    {'device': {'devEui': 'a84041000181c061', 'name': 'Lot B 14',
                'applicationId': '5b3c1e9a-2f4d-4c8e-9a71-0d2b6c8e4f10',
                'deviceTypeId': '9e0f6a52-7c1b-4d3e-8f2a-6b5c4d3e2f1a'},
     'readings': [{'quantity': 'temperature', 'channel': None, 'value': 21.4,
                   'unit': '°C', 'field': 'TempC_SHT'},
                  {'quantity': 'occupancy', 'channel': None, 'value': True,
                   'unit': None, 'field': 'occupied'}],
     'fields': {'TempC_SHT': 21.4, 'occupied': True},
     'radio': {'rssi': -97, 'snr': 7.5, 'gatewayId': '0016c001f1500a5b', 'gatewayCount': 2},
     'fPort': 2, 'fCnt': 1442, 'time': '2026-10-13T14:02:11.120Z'},
), separators=(',', ':')).encode()

UNICODE = json.dumps({'id': 'evt_x', 'data': {'name': 'Bâtiment Zürich — 東'}},
                     ensure_ascii=False, separators=(',', ':')).encode()


def case(name, body, header, secret, now, expected_note):
    return {
        'name': name,
        'note': expected_note,
        'secret': secret,
        'body': body.decode(),
        'bodyBase64': base64.b64encode(body).decode(),
        'header': header,
        'now': now,
        'tolerance': events.TOLERANCE_SECONDS,
        'valid': events.verify(secret, body, header, now=now),
    }


def vectors():
    signed = events.sign(NEW, BODY, T)
    rotated = events.sign([NEW, OLD], BODY, T)
    out = [
        case('valid', BODY, signed, NEW, T + 5, 'one v1, inside tolerance'),
        case('valid-at-tolerance', BODY, signed, NEW, T + 300, 'exactly 300 s old is accepted'),
        case('expired', BODY, signed, NEW, T + 301, 'one second past tolerance'),
        case('from-the-future', BODY, signed, NEW, T - 301, 'timestamp ahead of the receiver by more than tolerance'),
        case('rotation-new-secret', BODY, rotated, NEW, T, 'two v1 during a rotation; receiver has the new secret'),
        case('rotation-old-secret', BODY, rotated, OLD, T, 'two v1 during a rotation; receiver still has the old secret'),
        case('wrong-secret', BODY, signed, OTHER, T, 'signed with a different secret'),
        case('tampered-body', BODY.replace(b'21.4', b'31.4'), signed, NEW, T, 'one byte of the body changed after signing'),
        case('unicode-body', UNICODE, events.sign(NEW, UNICODE, T), NEW, T, 'non-ASCII body; the MAC is over the UTF-8 bytes'),
        case('unknown-scheme-ignored', BODY, signed + ',v0=deadbeef', NEW, T, 'a scheme the receiver does not know is skipped'),
        case('no-v1', BODY, f't={T}', NEW, T, 'timestamp only'),
        case('no-timestamp', BODY, signed.split(',', 1)[1], NEW, T, 'v1 only'),
        case('malformed', BODY, 'not a signature', NEW, T, 'not key=value pairs'),
        case('timestamp-not-a-number', BODY, signed.replace(f't={T}', 't=soon'), NEW, T, 't is not an integer'),
    ]
    return {
        'generatedBy': 'sdk/fixtures/generate.py from shared/events.py',
        'header': events.SIGNATURE_HEADER,
        'cases': out,
    }


def render():
    return json.dumps(vectors(), indent=2, ensure_ascii=False) + '\n'


if __name__ == '__main__':
    text = render()
    if '--check' in sys.argv:
        current = open(OUT, encoding='utf-8').read() if os.path.exists(OUT) else ''
        if current != text:
            print('sdk/fixtures/webhook-signatures.json is stale: run python sdk/fixtures/generate.py')
            sys.exit(1)
        print('webhook fixtures: ok')
    else:
        with open(OUT, 'w', encoding='utf-8') as f:
            f.write(text)
        print(f'wrote {OUT}')
