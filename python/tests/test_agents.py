"""Agent runs come back as typed events, one per SSE event name in
net-api/routes/agents.py, and a refusal raises before any streaming."""

from __future__ import annotations

import json
import unittest

import pulzr
from support import body_of, client, ok, sse


def frame(name, data):
    return f'event: {name}\ndata: {json.dumps(data)}\n\n'


RUN = ''.join([
    frame('run', {'runId': 'r1', 'threadId': 't1', 'status': 'running'}),
    ': ping\n\n',
    frame('thinking', {'delta': 'Checking the gateway'}),
    frame('text', {'delta': 'Lot B has '}),
    frame('text', {'delta': '14 bays.'}),
    frame('tool_call', {'id': 'tu1', 'name': 'list_devices', 'input': {'q': 'lot b'},
                        'class': 'read'}),
    frame('tool_result', {'id': 'tu1', 'name': 'list_devices', 'isError': False,
                          'summary': '14 devices', 'truncated': True}),
    frame('approval_required', {'runId': 'r1', 'approvals': [
        {'toolUseId': 'tu2', 'tool': 'delete_device', 'input': {}, 'class': 'destructive',
         'confirm': 'a84041000181c061', 'decision': None}]}),
    frame('usage', {'inputTokens': 10, 'outputTokens': 5, 'cacheReadTokens': 2,
                    'cacheWriteTokens': 1}),
    frame('something_new', {'x': 1}),
    frame('done', {'runId': 'r1', 'status': 'awaiting_approval', 'stopReason': 'tool_use'}),
])


class Send(unittest.TestCase):
    def test_typed_events(self):
        c, script, _ = client([sse(RUN)])
        stream = c.agents.send('t1', 'How many bays?', auto_approve_writes=True,
                               page_context={'path': '/devices', 'entities': {}})
        events = list(stream)
        self.assertEqual([e.type for e in events], [
            'run', 'thinking', 'text', 'text', 'tool_call', 'tool_result', 'approval_required',
            'usage', 'something_new', 'done'])

        run, thinking, _, _, call, result, approval, usage, unknown, done = events
        self.assertIsInstance(run, pulzr.RunEvent)
        self.assertEqual((run.run_id, run.thread_id, run.status), ('r1', 't1', 'running'))
        self.assertIsInstance(thinking, pulzr.ThinkingEvent)
        self.assertIsInstance(call, pulzr.ToolCallEvent)
        self.assertEqual((call.id, call.name, call.input, call.tool_class),
                         ('tu1', 'list_devices', {'q': 'lot b'}, 'read'))
        self.assertIsInstance(result, pulzr.ToolResultEvent)
        self.assertEqual((result.is_error, result.summary, result.truncated),
                         (False, '14 devices', True))
        self.assertIsInstance(approval, pulzr.ApprovalRequiredEvent)
        self.assertEqual(approval.approvals[0]['confirm'], 'a84041000181c061')
        self.assertIsInstance(usage, pulzr.UsageEvent)
        self.assertEqual((usage.input_tokens, usage.output_tokens, usage.cache_read_tokens,
                          usage.cache_write_tokens), (10, 5, 2, 1))
        self.assertIsInstance(unknown, pulzr.UnknownEvent)
        self.assertEqual(unknown.raw, {'x': 1})
        self.assertIsInstance(done, pulzr.DoneEvent)
        self.assertEqual((done.status, done.stop_reason), ('awaiting_approval', 'tool_use'))

        self.assertEqual(stream.text, 'Lot B has 14 bays.')
        self.assertEqual(stream.run_id, 'r1')

        sent = script.requests[0]
        self.assertEqual(sent.method, 'POST')
        self.assertEqual(sent.url.path, '/api/v1/agent/threads/t1/messages')
        self.assertEqual(body_of(sent), {'text': 'How many bays?', 'autoApproveWrites': True,
                                         'pageContext': {'path': '/devices', 'entities': {}}})

    def test_error_then_done(self):
        c, _, _ = client([sse(frame('run', {'runId': 'r2', 'threadId': 't1', 'status': 'running'})
                              + frame('error', {'error': 'The run failed'})
                              + frame('done', {'runId': 'r2', 'status': 'failed',
                                               'stopReason': None}))])
        done = None
        with c.agents.send('t1', 'hi') as stream:
            events = list(stream)
            done = events[-1]
        self.assertIsInstance(events[1], pulzr.ErrorEvent)
        self.assertEqual(events[1].error, 'The run failed')
        self.assertEqual(done.status, 'failed')

    def test_conflict_raises_at_send_and_is_not_retried(self):
        c, script, _ = client([ok({'error': 'A run in this conversation is still going'}, 409)])
        with self.assertRaises(pulzr.ConflictError):
            c.agents.send('t1', 'hi')
        self.assertEqual(len(script.requests), 1)

    def test_approve_streams_and_sends_decisions(self):
        c, script, _ = client([sse(frame('run', {'runId': 'r1', 'threadId': 't1',
                                                 'status': 'running'})
                                   + frame('done', {'runId': 'r1', 'status': 'completed',
                                                    'stopReason': 'end_turn'}))])
        decisions = [{'toolUseId': 'tu2', 'approve': True, 'confirm': 'a84041000181c061'}]
        done = c.agents.approve('r1', decisions).until_done()
        self.assertEqual(done.status, 'completed')
        self.assertEqual(script.requests[0].url.path, '/api/v1/agent/runs/r1/approvals')
        self.assertEqual(body_of(script.requests[0]), {'decisions': decisions})


class Background(unittest.TestCase):
    def test_manual_run_refusals_are_not_retried(self):
        c, script, slept = client([
            ok({'error': 'This agent already has a run waiting to start'}, 409),
            ok({'error': 'The daily token budget is spent'}, 429, {'Retry-After': '5'}),
        ])
        with self.assertRaises(pulzr.ConflictError):
            c.agents.run('a1')
        with self.assertRaises(pulzr.RateLimitError) as caught:
            c.agents.run('a1')
        self.assertEqual(caught.exception.retry_after, 5.0)
        self.assertEqual(len(script.requests), 2)
        self.assertEqual(slept, [])

    def test_routes(self):
        c, script, _ = client([
            ok({'result': []}),
            ok({'id': 'a1'}, 201),
            ok({'id': 'a1'}),
            ok({'id': 'r9', 'status': 'queued'}, 202),
            ok({'result': []}),
            ok({'run': {}, 'messages': [], 'approvals': []}),
            ok({'id': 'f1', 'status': 'resolved'}),
            ok({'result': []}),
        ])
        c.agents.list()
        c.agents.create('Offline watch', template='offline-watch', autonomy='observe')
        c.agents.update('a1', enabled=False)
        c.agents.run('a1')
        c.agents.runs('a1')
        c.agents.get_run('r9')
        c.agents.findings.update('f1', 'resolved')
        c.agents.findings.list(status='open', severity='critical')
        self.assertEqual([(r.method, r.url.path) for r in script.requests], [
            ('GET', '/api/v1/agents'),
            ('POST', '/api/v1/agents'),
            ('PUT', '/api/v1/agents/a1'),
            ('POST', '/api/v1/agents/a1/run'),
            ('GET', '/api/v1/agents/a1/runs'),
            ('GET', '/api/v1/agents/runs/r9'),
            ('POST', '/api/v1/agents/findings/f1'),
            ('GET', '/api/v1/agents/findings'),
        ])
        self.assertEqual(body_of(script.requests[1]), {'name': 'Offline watch',
                                                       'template': 'offline-watch',
                                                       'autonomy': 'observe'})
        self.assertEqual(body_of(script.requests[2]), {'enabled': False})
        self.assertEqual(script.requests[7].url.params['severity'], 'critical')


if __name__ == '__main__':
    unittest.main()
