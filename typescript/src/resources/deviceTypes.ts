import type { Core } from '../core.js';
import type { CodecVersion, DeployResult, DeviceType, QuantityMapping } from '../types.js';
import { seg } from '../util.js';

export class DeviceTypes {
  constructor(private readonly core: Core) {}

  /** This org's types and the ones Pulzar publishes. */
  async list(opts: { signal?: AbortSignal } = {}): Promise<DeviceType[]> {
    const page = await this.core.request<{ result: DeviceType[] }>('GET', '/api/v1/device-types', opts);
    return page.result;
  }

  /** Codec history, newest first. */
  async versions(deviceTypeId: string, opts: { signal?: AbortSignal } = {}): Promise<CodecVersion[]> {
    const page = await this.core.request<{ result: CodecVersion[] }>(
      'GET', `/api/v1/device-types/${seg(deviceTypeId)}/versions`, opts);
    return page.result;
  }

  /**
   * Make a codec commit live: into a LoRaWAN device profile, or for a
   * Bluetooth type into the beacon decoder (no profile). The newest commit
   * unless `commit` names one. Org admin.
   */
  deploy(
    deviceTypeId: string,
    input: { deviceProfileId?: string; commit?: string } = {},
    opts: { signal?: AbortSignal } = {},
  ): Promise<DeployResult> {
    return this.core.request('POST', `/api/v1/device-types/${seg(deviceTypeId)}/deploy`, { ...opts, body: input });
  }

  /** Map fields to quantities; `null` removes a mapping. Org admin. */
  setQuantities(deviceTypeId: string, mapping: QuantityMapping, opts: { signal?: AbortSignal } = {}): Promise<DeviceType> {
    return this.core.request('PUT', `/api/v1/device-types/${seg(deviceTypeId)}/quantities`, { ...opts, body: mapping });
  }

  /**
   * Declare text values the codec has renamed, `{ type: { OLD: 'NEW' } }`, so
   * filters match uplinks stored under either spelling. Replaces the whole
   * set; `null` clears it. Org admin.
   */
  setValueAliases(
    deviceTypeId: string,
    aliases: Record<string, Record<string, string>> | null,
    opts: { signal?: AbortSignal } = {},
  ): Promise<DeviceType> {
    return this.core.request('PATCH', `/api/v1/device-types/${seg(deviceTypeId)}`, { ...opts, body: { valueAliases: aliases } });
  }
}
