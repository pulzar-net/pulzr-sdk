"""The event log: paging, and the stream's parsing and resume.

The frames below are copied from what net-api/routes/events.py writes:
`retry:` and the `ready` event in one block, unnamed messages with the cursor
as `id:`, `: keep-alive` comments, `event: error` when the server gives up.
A reconnect must carry the last cursor in Last-Event-ID, or the stream
silently skips or repeats events.
"""

from __future__ import annotations

import json
import unittest

import pulzr
from pulzr._sse import SSEDecoder
from support import broken_sse, client, ok, sse


def envelope(n):
    return {'id': f'evt_{n:026d}', 'type': 'uplink.received', 'apiVersion': '2026-10-01',
            'createdAt': '2026-10-13T14:02:11.402Z', 'org': 'usc',
            'subject': 'a84041000181c061', 'data': {'n': n}}


def message(cursor, n):
    return f'id: {cursor}\ndata: {json.dumps(envelope(n))}\n\n'


def opening(cursor, retry=3000):
    return (f'retry: {retry}\nevent: ready\nid: {cursor}\n'
            f'data: {json.dumps({"cursor": cursor})}\n\n')


class Paging(unittest.TestCase):
    def test_list_params(self):
        c, script, _ = client([ok({'result': [], 'next': 'c0', 'hasMore': False})])
        page = c.events.list(after='c9', types=['device.offline', 'device.online'], limit=50)
        self.assertEqual(page['next'], 'c0')
        params = script.requests[0].url.params
        self.assertEqual(params['after'], 'c9')
        self.assertEqual(params['types'], 'device.offline,device.online')
        self.assertEqual(params['limit'], '50')
        self.assertNotIn('before', params)

    def test_iter_follows_next_until_caught_up(self):
        c, script, _ = client([
            ok({'result': [envelope(1), envelope(2)], 'next': 'c2', 'hasMore': True}),
            ok({'result': [envelope(3)], 'next': 'c3', 'hasMore': False}),
        ])
        got = [e['data']['n'] for e in c.events.iter(types='uplink.received', limit=2)]
        self.assertEqual(got, [1, 2, 3])
        self.assertNotIn('after', script.requests[0].url.params)
        self.assertEqual(script.requests[1].url.params['after'], 'c2')
        self.assertEqual(script.requests[1].url.params['types'], 'uplink.received')

    def test_iter_backward_uses_before(self):
        c, script, _ = client([
            ok({'result': [envelope(3)], 'next': 'c3', 'hasMore': True}),
            ok({'result': [envelope(2)], 'next': None, 'hasMore': False}),
        ])
        got = [e['data']['n'] for e in c.events.iter(before='now', limit=1)]
        self.assertEqual(got, [3, 2])
        self.assertEqual(script.requests[0].url.params['before'], 'now')
        self.assertEqual(script.requests[1].url.params['before'], 'c3')
        self.assertNotIn('after', script.requests[1].url.params)

    def test_get_and_types(self):
        c, script, _ = client([ok(envelope(1)),
                               ok({'result': [{'type': 'device.offline', 'description': 'x'}],
                                   'apiVersion': '2026-10-01'})])
        self.assertEqual(c.events.get('evt_1')['data'], {'n': 1})
        self.assertEqual(c.events.types()[0]['type'], 'device.offline')
        self.assertEqual(script.requests[0].url.path, '/api/v1/events/evt_1')


class Decoder(unittest.TestCase):
    def events(self, text):
        decoder = SSEDecoder()
        return decoder, list(decoder.iter_events(text.splitlines()))

    def test_multi_line_data_and_comments(self):
        decoder, got = self.events(': keep-alive\n\nevent: x\ndata: {"a":\ndata: 1}\nid: c1\n\n')
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0].event, 'x')
        self.assertEqual(json.loads(got[0].data), {'a': 1})
        self.assertEqual(got[0].id, 'c1')

    def test_retry_and_no_space_after_colon(self):
        decoder, got = self.events('retry: 1500\ndata:plain\n\n')
        self.assertEqual(decoder.retry, 1500)
        self.assertEqual(got[0].data, 'plain')
        self.assertEqual(got[0].event, 'message')

    def test_incomplete_block_dropped(self):
        _, got = self.events('data: first\n\ndata: half')
        self.assertEqual([e.data for e in got], ['first'])

    def test_crlf(self):
        decoder = SSEDecoder()
        got = list(decoder.iter_events(['event: run\r\n', 'data: {}\r\n', '\r\n']))
        self.assertEqual(got[0].event, 'run')


class Stream(unittest.TestCase):
    def test_parses_and_reconnects_with_last_event_id(self):
        c, script, slept = client([
            broken_sse(opening('c0', retry=1500) + message('c1', 1) + ': keep-alive\n\n'
                       + message('c2', 2)),
            sse(opening('c2') + message('c3', 3)),
        ])
        stream = c.events.stream(types=['uplink.received'])
        got = [next(stream)['data']['n'] for _ in range(3)]
        stream.close()
        self.assertEqual(got, [1, 2, 3])

        first, second = script.requests
        self.assertEqual(first.url.path, '/api/v1/events/stream')
        self.assertEqual(first.url.params['types'], 'uplink.received')
        self.assertNotIn('Last-Event-ID', first.headers)
        self.assertEqual(second.headers['Last-Event-ID'], 'c2')
        self.assertNotIn('after', second.url.params)
        # The server's `retry: 1500`, not the default.
        self.assertEqual(slept, [1.5])
        self.assertEqual(stream.cursor, 'c3')

    def test_resumes_from_given_cursor(self):
        c, script, _ = client([sse(opening('c7') + message('c8', 8))])
        with c.events.stream(last_event_id='c7') as stream:
            self.assertEqual(next(stream)['data']['n'], 8)
        self.assertEqual(script.requests[0].headers['Last-Event-ID'], 'c7')

    def test_after_is_a_cursor_too(self):
        c, script, _ = client([sse(opening('c4') + message('c5', 5))])
        with c.events.stream(after='c4') as stream:
            next(stream)
        self.assertEqual(script.requests[0].headers['Last-Event-ID'], 'c4')

    def test_ready_alone_sets_the_resume_point(self):
        c, script, _ = client([
            sse(opening('c40')),
            sse(opening('c40') + message('c41', 41)),
        ])
        stream = c.events.stream()
        self.assertEqual(next(stream)['data']['n'], 41)
        stream.close()
        self.assertEqual(script.requests[1].headers['Last-Event-ID'], 'c40')

    def test_error_event_reconnects(self):
        c, script, slept = client([
            sse(opening('c0') + message('c1', 1)
                + 'event: error\ndata: {"error":"The stream stopped"}\n\n'),
            sse(opening('c1') + message('c2', 2)),
        ])
        stream = c.events.stream()
        self.assertEqual([next(stream)['data']['n'] for _ in range(2)], [1, 2])
        stream.close()
        self.assertEqual(script.requests[1].headers['Last-Event-ID'], 'c1')
        self.assertEqual(slept, [3.0])

    def test_server_error_backs_off_then_resumes(self):
        c, script, slept = client([
            broken_sse(opening('c0') + message('c1', 1)),
            ok({'error': 'down'}, 503),
            ok({'error': 'down'}, 503, {'Retry-After': '20'}),
            sse(opening('c1') + message('c2', 2)),
        ])
        stream = c.events.stream()
        self.assertEqual([next(stream)['data']['n'] for _ in range(2)], [1, 2])
        stream.close()
        self.assertEqual(len(script.requests), 4)
        self.assertTrue(all(r.headers['Last-Event-ID'] == 'c1' for r in script.requests[1:]))
        self.assertEqual(slept[0], 3.0)
        self.assertTrue(3.0 <= slept[1] <= 6.0, slept)
        self.assertEqual(slept[2], 20.0)

    def test_server_end_resumes_from_its_cursor(self):
        # utils/streams.py closes every stream after an hour with an `end`
        # naming the position, which may be past the last event sent.
        c, script, slept = client([
            sse(opening('c0') + message('c1', 1)
                + 'event: end\nid: c5\ndata: {"reason": "deadline"}\n\n'),
            sse(opening('c5') + message('c6', 6)),
        ])
        stream = c.events.stream()
        self.assertEqual([next(stream)['data']['n'] for _ in range(2)], [1, 6])
        stream.close()
        self.assertEqual(script.requests[1].headers['Last-Event-ID'], 'c5')
        self.assertEqual(slept, [3.0])

    def test_too_many_streams_waits_out_retry_after(self):
        c, script, slept = client([
            ok({'error': 'This organization already has 5 live streams open'}, 429,
               {'Retry-After': '30'}),
            sse(opening('c0') + message('c1', 1)),
        ])
        with c.events.stream(last_event_id='c0') as stream:
            self.assertEqual(next(stream)['data']['n'], 1)
        self.assertEqual(slept, [30.0])
        self.assertEqual([r.headers['Last-Event-ID'] for r in script.requests], ['c0', 'c0'])

    def test_gives_up_after_max_reconnects(self):
        c, script, _ = client([ok({'error': 'down'}, 503)] * 3)
        stream = c.events.stream(max_reconnects=2)
        with self.assertRaises(pulzr.ServerError):
            next(stream)
        self.assertEqual(len(script.requests), 3)

    def test_client_error_raises_at_once(self):
        c, script, slept = client([ok({'error': 'Last-Event-ID is not a cursor this server issued'},
                                      400)])
        with self.assertRaises(pulzr.ValidationError):
            next(c.events.stream(last_event_id='junk'))
        self.assertEqual(len(script.requests), 1)
        self.assertEqual(slept, [])

    def test_unknown_named_event_skipped(self):
        c, _, _ = client([sse(opening('c0') + 'event: future\ndata: {}\n\n' + message('c1', 1))])
        with c.events.stream() as stream:
            self.assertEqual(next(stream)['data']['n'], 1)


if __name__ == '__main__':
    unittest.main()
