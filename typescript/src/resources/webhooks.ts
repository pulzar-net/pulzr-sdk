import type { Core } from '../core.js';
import type { DeliveryStatus, Webhook, WebhookDelivery, WebhookInput, WebhookUpdate } from '../types.js';
import { seg } from '../util.js';

export class Webhooks {
  constructor(private readonly core: Core) {}

  async list(opts: { signal?: AbortSignal } = {}): Promise<Webhook[]> {
    const page = await this.core.request<{ result: Webhook[] }>('GET', '/api/v1/webhooks', opts);
    return page.result;
  }

  /** The response is the only time the signing secret is shown. Org admin. */
  create(input: WebhookInput, opts: { signal?: AbortSignal } = {}): Promise<Webhook & { secret: string }> {
    return this.core.request('POST', '/api/v1/webhooks', { ...opts, body: input });
  }

  get(id: string, opts: { signal?: AbortSignal } = {}): Promise<Webhook> {
    return this.core.request('GET', `/api/v1/webhooks/${seg(id)}`, opts);
  }

  /** Disabling abandons what the endpoint was still owed; enabling resets its failure count. */
  update(id: string, changes: WebhookUpdate, opts: { signal?: AbortSignal } = {}): Promise<Webhook> {
    return this.core.request('PATCH', `/api/v1/webhooks/${seg(id)}`, { ...opts, body: changes });
  }

  async delete(id: string, opts: { signal?: AbortSignal } = {}): Promise<void> {
    await this.core.request('DELETE', `/api/v1/webhooks/${seg(id)}`, opts);
  }

  /** A new secret. The old one keeps signing beside it until `previousSecretExpiresAt`. */
  rotateSecret(
    id: string,
    opts: { signal?: AbortSignal } = {},
  ): Promise<{ id: string; secret: string; previousSecretExpiresAt: string }> {
    return this.core.request('POST', `/api/v1/webhooks/${seg(id)}/rotate-secret`, opts);
  }

  /** Queue a `webhook.test` delivery to this endpoint alone. */
  test(id: string, opts: { signal?: AbortSignal } = {}): Promise<{ deliveryId: string; eventId: string }> {
    return this.core.request('POST', `/api/v1/webhooks/${seg(id)}/test`, opts);
  }

  /** Newest first. `limit` 1 to 200, default 50. */
  async deliveries(
    id: string,
    query: { status?: DeliveryStatus; limit?: number } = {},
    opts: { signal?: AbortSignal } = {},
  ): Promise<WebhookDelivery[]> {
    const page = await this.core.request<{ result: WebhookDelivery[] }>(
      'GET', `/api/v1/webhooks/${seg(id)}/deliveries`, { ...opts, query: { ...query } });
    return page.result;
  }

  retryDelivery(deliveryId: string, opts: { signal?: AbortSignal } = {}): Promise<{ id: string; status: 'pending' }> {
    return this.core.request('POST', `/api/v1/webhooks/deliveries/${seg(deliveryId)}/retry`, opts);
  }
}
