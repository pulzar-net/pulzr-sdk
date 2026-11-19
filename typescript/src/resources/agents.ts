import type { Core } from '../core.js';
import { ConnectionError } from '../errors.js';
import type {
  Agent,
  AgentInput,
  AgentStreamEvent,
  AgentTemplates,
  Decision,
  Finding,
  FindingQuery,
  Run,
  RunDetail,
  SendInput,
  Thread,
  ThreadDetail,
} from '../types.js';
import type { FindingStatus } from '../events.js';
import { seg } from '../util.js';
import { namedEvents } from './stream.js';

const RUN_EVENTS = new Set([
  'run', 'text', 'thinking', 'tool_call', 'tool_result', 'approval_required', 'usage', 'done', 'error',
]);

/**
 * A run's events until `done`. The run belongs to the server, not to this
 * connection: if the connection drops it carries on and is stored, so a
 * stream that ends without `done` is reported as a ConnectionError and the
 * thread can be fetched to see how it finished.
 */
async function* runEvents(
  core: Core,
  path: string,
  body: unknown,
  signal: AbortSignal | undefined,
): AsyncGenerator<AgentStreamEvent, void, undefined> {
  const events = namedEvents<AgentStreamEvent>(core, 'POST', path, RUN_EVENTS, { body, ...(signal ? { signal } : {}) });
  for await (const event of events) {
    yield event;
    if (event.type === 'done') return;
  }
  if (signal?.aborted) return;
  throw new ConnectionError('The run stream ended before the run did; fetch the thread for its outcome');
}

export class Threads {
  constructor(private readonly core: Core) {}

  /** Yours, newest first. */
  async list(opts: { signal?: AbortSignal } = {}): Promise<Thread[]> {
    const page = await this.core.request<{ result: Thread[] }>('GET', '/api/v1/agent/threads', opts);
    return page.result;
  }

  create(input: { title?: string } = {}, opts: { signal?: AbortSignal } = {}): Promise<Thread> {
    return this.core.request('POST', '/api/v1/agent/threads', { ...opts, body: input });
  }

  /** The transcript, its runs, and any actions waiting for approval. */
  get(threadId: string, opts: { signal?: AbortSignal } = {}): Promise<ThreadDetail> {
    return this.core.request('GET', `/api/v1/agent/threads/${seg(threadId)}`, opts);
  }

  async delete(threadId: string, opts: { signal?: AbortSignal } = {}): Promise<void> {
    await this.core.request('DELETE', `/api/v1/agent/threads/${seg(threadId)}`, opts);
  }
}

export class Findings {
  constructor(private readonly core: Core) {}

  /** Newest first, up to 500. */
  async list(query: FindingQuery = {}, opts: { signal?: AbortSignal } = {}): Promise<Finding[]> {
    const page = await this.core.request<{ result: Finding[] }>(
      'GET', '/api/v1/agents/findings', { ...opts, query: { ...query } });
    return page.result;
  }

  update(findingId: string, status: FindingStatus, opts: { signal?: AbortSignal } = {}): Promise<Finding> {
    return this.core.request('POST', `/api/v1/agents/findings/${seg(findingId)}`, { ...opts, body: { status } });
  }
}

/**
 * The assistant (threads, `send`, `approve`, `cancel`) and background agents.
 * An agent's own key is refused here except for filing findings, so these
 * calls need a person's key.
 */
export class Agents {
  readonly threads: Threads;
  readonly findings: Findings;

  constructor(private readonly core: Core) {
    this.threads = new Threads(core);
    this.findings = new Findings(core);
  }

  /** Whether the assistant can answer. */
  status(opts: { signal?: AbortSignal } = {}): Promise<{ configured: boolean; model: string | null }> {
    return this.core.request('GET', '/api/v1/agent/status', opts);
  }

  /**
   * Send a message and stream the run it starts. The request is made when
   * iteration begins. A thread with a run still going answers ConflictError;
   * one awaiting approval has its pending actions declined by a new message.
   */
  send(threadId: string, input: SendInput, opts: { signal?: AbortSignal } = {}): AsyncGenerator<AgentStreamEvent, void, undefined> {
    return runEvents(this.core, `/api/v1/agent/threads/${seg(threadId)}/messages`, input, opts.signal);
  }

  /**
   * Decide every pending action of a run at once and stream it resuming. A
   * destructive action approved must carry its approval's `confirm` value.
   */
  approve(runId: string, decisions: Decision[], opts: { signal?: AbortSignal } = {}): AsyncGenerator<AgentStreamEvent, void, undefined> {
    return runEvents(this.core, `/api/v1/agent/runs/${seg(runId)}/approvals`, { decisions }, opts.signal);
  }

  cancel(runId: string, opts: { signal?: AbortSignal } = {}): Promise<Run> {
    return this.core.request('POST', `/api/v1/agent/runs/${seg(runId)}/cancel`, opts);
  }

  // ── background agents ──

  async list(opts: { signal?: AbortSignal } = {}): Promise<Agent[]> {
    const page = await this.core.request<{ result: Agent[] }>('GET', '/api/v1/agents', opts);
    return page.result;
  }

  /** Org admin. Fields left out come from `template` when one is named. */
  create(input: AgentInput, opts: { signal?: AbortSignal } = {}): Promise<Agent> {
    return this.core.request('POST', '/api/v1/agents', { ...opts, body: input });
  }

  get(agentId: string, opts: { signal?: AbortSignal } = {}): Promise<Agent> {
    return this.core.request('GET', `/api/v1/agents/${seg(agentId)}`, opts);
  }

  /** Any subset of the create fields. Org admin. */
  update(agentId: string, changes: AgentInput, opts: { signal?: AbortSignal } = {}): Promise<Agent> {
    return this.core.request('PUT', `/api/v1/agents/${seg(agentId)}`, { ...opts, body: changes });
  }

  /** Revokes the agent's key and cancels its queued runs. Org admin. */
  async delete(agentId: string, opts: { signal?: AbortSignal } = {}): Promise<void> {
    await this.core.request('DELETE', `/api/v1/agents/${seg(agentId)}`, opts);
  }

  /** Queue a run now; it starts when the worker picks it up. Org admin.
   *  ConflictError if one is already queued; RateLimitError once the org's
   *  daily token budget is spent. */
  run(agentId: string, opts: { signal?: AbortSignal } = {}): Promise<Run> {
    return this.core.request('POST', `/api/v1/agents/${seg(agentId)}/run`, opts);
  }

  /** The newest 50. */
  async runs(agentId: string, opts: { signal?: AbortSignal } = {}): Promise<Run[]> {
    const page = await this.core.request<{ result: Run[] }>('GET', `/api/v1/agents/${seg(agentId)}/runs`, opts);
    return page.result;
  }

  /** A background agent's run with its transcript and approvals. Org admin. */
  getRun(runId: string, opts: { signal?: AbortSignal } = {}): Promise<RunDetail> {
    return this.core.request('GET', `/api/v1/agents/runs/${seg(runId)}`, opts);
  }

  templates(opts: { signal?: AbortSignal } = {}): Promise<AgentTemplates> {
    return this.core.request('GET', '/api/v1/agents/templates', opts);
  }
}
