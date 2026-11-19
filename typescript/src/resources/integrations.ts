import type { Core } from '../core.js';
import type {
  DeliveryStatus,
  Integration,
  IntegrationDelivery,
  IntegrationInput,
  IntegrationRequest,
  IntegrationTemplate,
  IntegrationUpdate,
} from '../types.js';
import { seg } from '../util.js';

/** Events pushed into InfluxDB, Datacake, ThingsBoard, AWS IoT Core, Azure IoT Hub, Akenza, Ubidots, TagoIO or S3. */
export class Integrations {
  constructor(private readonly core: Core) {}

  /** Every target, with its settings as JSON Schema; `x-secret` marks a credential. */
  async templates(opts: { signal?: AbortSignal } = {}): Promise<IntegrationTemplate[]> {
    const page = await this.core.request<{ result: IntegrationTemplate[] }>('GET', '/api/v1/integrations/templates', opts);
    return page.result;
  }

  async list(opts: { signal?: AbortSignal } = {}): Promise<Integration[]> {
    const page = await this.core.request<{ result: Integration[] }>('GET', '/api/v1/integrations', opts);
    return page.result;
  }

  /** Org admin. Secrets go in `settings` and are never returned. */
  create(input: IntegrationInput, opts: { signal?: AbortSignal } = {}): Promise<Integration> {
    return this.core.request('POST', '/api/v1/integrations', { ...opts, body: input });
  }

  get(id: string, opts: { signal?: AbortSignal } = {}): Promise<Integration> {
    return this.core.request('GET', `/api/v1/integrations/${seg(id)}`, opts);
  }

  /** `settings` is merged over what is stored; a secret left out is kept. */
  update(id: string, changes: IntegrationUpdate, opts: { signal?: AbortSignal } = {}): Promise<Integration> {
    return this.core.request('PATCH', `/api/v1/integrations/${seg(id)}`, { ...opts, body: changes });
  }

  async delete(id: string, opts: { signal?: AbortSignal } = {}): Promise<void> {
    await this.core.request('DELETE', `/api/v1/integrations/${seg(id)}`, opts);
  }

  /** Queue a synthetic uplink to this integration alone; `request` is what will be sent, masked. */
  test(
    id: string,
    input: { devEui?: string } = {},
    opts: { signal?: AbortSignal } = {},
  ): Promise<{ deliveryId: string; eventId: string; request: IntegrationRequest }> {
    return this.core.request('POST', `/api/v1/integrations/${seg(id)}/test`, { ...opts, body: input });
  }

  /** Newest first. `limit` 1 to 200, default 50. */
  async deliveries(
    id: string,
    query: { status?: DeliveryStatus; limit?: number } = {},
    opts: { signal?: AbortSignal } = {},
  ): Promise<IntegrationDelivery[]> {
    const page = await this.core.request<{ result: IntegrationDelivery[] }>(
      'GET', `/api/v1/integrations/${seg(id)}/deliveries`, { ...opts, query: { ...query } });
    return page.result;
  }

  retryDelivery(deliveryId: string, opts: { signal?: AbortSignal } = {}): Promise<{ id: string; status: 'pending' }> {
    return this.core.request('POST', `/api/v1/integrations/deliveries/${seg(deliveryId)}/retry`, opts);
  }
}
