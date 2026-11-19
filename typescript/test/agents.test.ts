import assert from 'node:assert/strict';
import { test } from 'node:test';

import { ConflictError, ConnectionError, PulzrClient, RateLimitError, type AgentStreamEvent } from '../src/index.js';
import { KEY, collect, json, mockFetch, sse } from './helpers.js';

const frame = (event: string, data: unknown) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;

const RUN = [
  frame('run', { runId: 'r1', threadId: 't1', status: 'running' }),
  frame('thinking', { delta: 'Checking the gateway.' }),
  frame('text', { delta: 'Looking ' }),
  frame('text', { delta: 'now.' }),
  ': ping\n\n',
  frame('tool_call', { id: 'tu1', name: 'device_health', input: {}, class: 'read' }),
  frame('tool_result', { id: 'tu1', name: 'device_health', isError: false, summary: '3 devices', truncated: false }),
  frame('some_future_event', { x: 1 }),
  frame('usage', { inputTokens: 10, outputTokens: 5, cacheReadTokens: 0, cacheWriteTokens: 0 }),
  frame('done', { runId: 'r1', status: 'completed', stopReason: 'end_turn' }),
];

test('send posts the message and yields typed events until done', async () => {
  const fetch = mockFetch(() => sse(RUN));
  const client = new PulzrClient({ apiKey: KEY, org: 'usc', fetch });
  const events = await collect(client.agents.send('t1', { text: 'Is lot B up?', autoApproveWrites: false }));

  const call = fetch.calls[0]!;
  assert.equal(call.method, 'POST');
  assert.equal(call.url.pathname, '/api/v1/agent/threads/t1/messages');
  assert.equal(call.headers.get('accept'), 'text/event-stream');
  assert.deepEqual(call.body, { text: 'Is lot B up?', autoApproveWrites: false });

  assert.deepEqual(events.map((e) => e.type),
    ['run', 'thinking', 'text', 'text', 'tool_call', 'tool_result', 'usage', 'done']);

  let text = '';
  let tools = 0;
  for (const e of events) {
    switch (e.type) {
      case 'text':
        text += e.data.delta;
        break;
      case 'tool_call':
        assert.equal(e.data.class, 'read');
        tools++;
        break;
      case 'tool_result':
        assert.equal(e.data.summary, '3 devices');
        break;
      case 'done':
        assert.equal(e.data.status, 'completed');
        break;
      default:
        break;
    }
  }
  assert.equal(text, 'Looking now.');
  assert.equal(tools, 1);
});

test('approval_required then approve with a typed confirm', async () => {
  const approval = {
    toolUseId: 'tu9', tool: 'delete_device', input: { dev_eui: 'a840410000000001' }, class: 'destructive',
    confirm: 'a840410000000001', decision: null, decidedBy: null, decidedAt: null,
  };
  const fetch = mockFetch((_, i) => sse(i === 0
    ? [frame('run', { runId: 'r2', threadId: 't1', status: 'running' }),
       frame('approval_required', { runId: 'r2', approvals: [approval] }),
       frame('done', { runId: 'r2', status: 'awaiting_approval', stopReason: 'tool_use' })]
    : [frame('run', { runId: 'r2', threadId: 't1', status: 'running' }),
       frame('done', { runId: 'r2', status: 'completed', stopReason: 'end_turn' })]));
  const client = new PulzrClient({ apiKey: KEY, fetch });

  const pending: AgentStreamEvent[] = await collect(client.agents.send('t1', { text: 'Delete it' }));
  const asked = pending.find((e) => e.type === 'approval_required');
  assert.ok(asked && asked.type === 'approval_required');
  const decisions = asked.data.approvals.map((a) => ({
    toolUseId: a.toolUseId, approve: true, ...(a.confirm ? { confirm: a.confirm } : {}),
  }));
  const resumed = await collect(client.agents.approve('r2', decisions));

  assert.equal(fetch.calls[1]!.url.pathname, '/api/v1/agent/runs/r2/approvals');
  assert.deepEqual(fetch.calls[1]!.body, { decisions: [{ toolUseId: 'tu9', approve: true, confirm: 'a840410000000001' }] });
  assert.equal(resumed.at(-1)?.type, 'done');
});

test('a run already going is a ConflictError on first iteration, and is not retried', async () => {
  const fetch = mockFetch(() => json({ error: 'A run in this conversation is still going' }, 409));
  const client = new PulzrClient({ apiKey: KEY, fetch });
  await assert.rejects(collect(client.agents.send('t1', { text: 'hi' })), ConflictError);
  assert.equal(fetch.calls.length, 1);
});

test('a stream that ends without done is a ConnectionError', async () => {
  const fetch = mockFetch(() => sse([frame('run', { runId: 'r3', threadId: 't1', status: 'running' }),
    frame('text', { delta: 'half' })]));
  const client = new PulzrClient({ apiKey: KEY, fetch });
  const seen: string[] = [];
  await assert.rejects(async () => {
    for await (const e of client.agents.send('t1', { text: 'hi' })) seen.push(e.type);
  }, ConnectionError);
  assert.deepEqual(seen, ['run', 'text']);
});

test('nothing is sent until iteration starts', async () => {
  const fetch = mockFetch(() => sse(RUN));
  const client = new PulzrClient({ apiKey: KEY, fetch });
  const stream = client.agents.send('t1', { text: 'hi' });
  assert.equal(fetch.calls.length, 0);
  await collect(stream);
  assert.equal(fetch.calls.length, 1);
});

test('background agents and findings hit their routes', async () => {
  const fetch = mockFetch((call) => {
    if (call.url.pathname.endsWith('/run')) return json({ id: 'r9', status: 'queued' }, 202);
    if (call.url.pathname === '/api/v1/agents/findings') return json({ result: [{ id: 'f1' }] });
    if (call.url.pathname.startsWith('/api/v1/agents/findings/')) return json({ id: 'f1', status: 'resolved' });
    return json({ result: [] });
  });
  const client = new PulzrClient({ apiKey: KEY, fetch });
  await client.agents.run('a1');
  const findings = await client.agents.findings.list({ status: 'open', severity: 'critical' });
  await client.agents.findings.update('f1', 'resolved');
  assert.equal(findings.length, 1);
  assert.equal(fetch.calls[0]!.url.pathname, '/api/v1/agents/a1/run');
  assert.equal(fetch.calls[1]!.url.search, '?status=open&severity=critical');
  assert.deepEqual(fetch.calls[2]!.body, { status: 'resolved' });
});

test('a manual run past the daily budget is a RateLimitError, not retried', async () => {
  const fetch = mockFetch(() => json({ error: "The organization's agent token budget for today is used up" }, 429));
  const client = new PulzrClient({ apiKey: KEY, fetch });
  await assert.rejects(client.agents.run('a1'), RateLimitError);
  assert.equal(fetch.calls.length, 1);
});
