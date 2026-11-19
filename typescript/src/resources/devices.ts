import type { Core } from '../core.js';
import type {
  ClaimInput,
  ClaimResult,
  DeviceCommands,
  DeviceTransfer,
  DeviceDetail,
  DeviceHealthList,
  DeviceReadings,
  DownlinkInput,
  ProvisionInput,
  ProvisionResult,
  QueuedDownlink,
  RegistryEntry,
  RegistryLabel,
  RegistryRow,
  SentCommand,
  TransferOffer,
  TransferStatus,
  Window,
} from '../types.js';
import { base64, seg } from '../util.js';
import type { DeviceLocation } from './radio.js';

export class Devices {
  constructor(private readonly core: Core) {}

  /** Every device that has reported, with whether it is online by its
   *  application's threshold. */
  list(opts: { signal?: AbortSignal } = {}): Promise<DeviceHealthList> {
    return this.core.request('GET', '/api/v1/data/devices/health', opts);
  }

  get(devEui: string, opts: { signal?: AbortSignal } = {}): Promise<DeviceDetail> {
    return this.core.request('GET', `/api/v1/data/devices/${seg(devEui)}`, opts);
  }

  /** Where a device is: its own fix, a position solved from the gateways
   *  that heard it (with `accuracyM` and `method`), or its gateway's. */
  location(devEui: string, query: { history?: number } = {}, opts: { signal?: AbortSignal } = {}): Promise<DeviceLocation> {
    return this.core.request('GET', `/api/v1/devices/${seg(devEui)}/location`, { ...opts, query: { ...query } });
  }

  /** Set where a device is by hand: a sensor mounted at a bay. Below the
   *  device's own fix, above a solved or gateway position. */
  setLocation(
    devEui: string,
    input: { latitude: number; longitude: number },
    opts: { signal?: AbortSignal } = {},
  ): Promise<DeviceLocation> {
    return this.core.request('PUT', `/api/v1/devices/${seg(devEui)}/location`, { ...opts, body: input });
  }

  /** Clear a hand-set position. */
  clearLocation(devEui: string, opts: { signal?: AbortSignal } = {}): Promise<void> {
    return this.core.request('DELETE', `/api/v1/devices/${seg(devEui)}/location`, opts);
  }

  /** Recent uplinks: canonical readings beside the codec's raw fields. */
  readings(
    devEui: string,
    query: { from?: Window; limit?: number } = {},
    opts: { signal?: AbortSignal } = {},
  ): Promise<DeviceReadings> {
    return this.core.request('GET', `/api/v1/devices/${seg(devEui)}/readings`, { ...opts, query: { ...query } });
  }

  /** Downlinks queued and not yet delivered. LoRaWAN only. */
  async downlinks(devEui: string, opts: { signal?: AbortSignal } = {}): Promise<QueuedDownlink[]> {
    const page = await this.core.request<{ result: QueuedDownlink[] }>(
      'GET', `/api/v1/devices/${seg(devEui)}/downlinks`, opts);
    return page.result;
  }

  /** A class A device receives it after its next uplink. */
  sendDownlink(devEui: string, input: DownlinkInput, opts: { signal?: AbortSignal } = {}): Promise<{ id: string | null }> {
    const body: Record<string, unknown> = { fPort: input.fPort, confirmed: input.confirmed ?? false };
    if (input.data !== undefined) body.data = base64(input.data);
    if (input.object !== undefined) body.object = input.object;
    return this.core.request('POST', `/api/v1/devices/${seg(devEui)}/downlinks`, { ...opts, body });
  }

  /** Drops the whole queue; the LNS has no remove-one. */
  flushDownlinks(devEui: string, opts: { signal?: AbortSignal } = {}): Promise<{ flushed: boolean }> {
    return this.core.request('DELETE', `/api/v1/devices/${seg(devEui)}/downlinks`, opts);
  }

  /** What the device can be told, and what it has been told. */
  commands(devEui: string, opts: { signal?: AbortSignal } = {}): Promise<DeviceCommands> {
    return this.core.request('GET', `/api/v1/devices/${seg(devEui)}/commands`, opts);
  }

  sendCommand(
    devEui: string,
    commandId: string,
    input: { params?: Record<string, number>; confirmed?: boolean } = {},
    opts: { signal?: AbortSignal } = {},
  ): Promise<SentCommand> {
    return this.core.request('POST', `/api/v1/devices/${seg(devEui)}/commands/${seg(commandId)}`, {
      ...opts,
      body: { params: input.params ?? {}, ...(input.confirmed === undefined ? {} : { confirmed: input.confirmed }) },
    });
  }

  /** Register a device, keys and all. A repeat for a device this org already
   *  has updates it (`created: false`). Org admin. */
  provision(input: ProvisionInput, opts: { signal?: AbortSignal } = {}): Promise<ProvisionResult> {
    return this.core.request('POST', '/api/v1/provisioning/devices', { ...opts, body: input });
  }

  /** Claim a device with the code on its label. Registered with keys nobody
   *  is shown. Wrong codes are counted; past the limit this is a 429. */
  claim(input: ClaimInput, opts: { signal?: AbortSignal } = {}): Promise<ClaimResult> {
    return this.core.request('POST', '/api/v1/devices/claim', { ...opts, body: input });
  }

  /** Remove a device from the org and list it in the registry with a new
   *  claim code, returned here only. `confirm` repeats the EUI. The AppKey is
   *  unchanged unless `appKey` gives the one the vendor's tool set. Org admin. */
  release(
    devEui: string,
    input: { confirm: string; appKey?: string; validDays?: number },
    opts: { signal?: AbortSignal } = {},
  ): Promise<RegistryLabel> {
    return this.core.request('POST', `/api/v1/devices/${seg(devEui)}/release`, { ...opts, body: input });
  }

  /** Devices the org is owner of record for. Org admin. */
  get registry(): DeviceRegistry {
    return new DeviceRegistry(this.core);
  }

  /** Offers of devices to and from other organizations. */
  get transfers(): DeviceTransfers {
    return new DeviceTransfers(this.core);
  }

  /** Remove a device. Succeeds with `removed: false` when it is already gone.
   *  Stored uplinks remain. Org admin. */
  async decommission(devEui: string, opts: { signal?: AbortSignal } = {}): Promise<{ devEui: string; removed: boolean }> {
    const answer = await this.core.request<{ result: { devEui: string; removed: boolean } }>(
      'DELETE', `/api/v1/provisioning/devices/${seg(devEui)}`, opts);
    return answer.result;
  }
}

export class DeviceRegistry {
  constructor(private readonly core: Core) {}

  async list(query: { status?: RegistryEntry['status'] } = {}, opts: { signal?: AbortSignal } = {}): Promise<RegistryEntry[]> {
    const page = await this.core.request<{ result: RegistryEntry[] }>('GET', '/api/v1/device-registry', { ...opts, query: { ...query } });
    return page.result;
  }

  /** All or nothing. Each code and its label is in this answer only. */
  async import(
    input: { devices?: RegistryRow[]; csv?: string; deviceType?: string; profileId?: string; validDays?: number },
    opts: { signal?: AbortSignal } = {},
  ): Promise<RegistryLabel[]> {
    const page = await this.core.request<{ result: RegistryLabel[] }>('POST', '/api/v1/device-registry', { ...opts, body: input });
    return page.result;
  }

  /** A new code for an unclaimed entry; the old one stops claiming. */
  newCode(entryId: string, opts: { signal?: AbortSignal } = {}): Promise<RegistryLabel> {
    return this.core.request('POST', `/api/v1/device-registry/${seg(entryId)}/code`, opts);
  }

  withdraw(entryId: string, input: { confirm: string }, opts: { signal?: AbortSignal } = {}): Promise<{ id: string; devEui: string; status: 'withdrawn' }> {
    return this.core.request('DELETE', `/api/v1/device-registry/${seg(entryId)}`, { ...opts, body: input });
  }
}

export class DeviceTransfers {
  constructor(private readonly core: Core) {}

  async list(
    query: { direction?: 'incoming' | 'outgoing'; status?: TransferStatus | 'open' } = {},
    opts: { signal?: AbortSignal } = {},
  ): Promise<DeviceTransfer[]> {
    const page = await this.core.request<{ result: DeviceTransfer[] }>('GET', '/api/v1/device-transfers', { ...opts, query: { ...query } });
    return page.result;
  }

  get(transferId: string, opts: { signal?: AbortSignal } = {}): Promise<DeviceTransfer> {
    return this.core.request('GET', `/api/v1/device-transfers/${seg(transferId)}`, opts);
  }

  /** Nothing moves until an admin of the other org accepts. */
  offer(input: TransferOffer, opts: { signal?: AbortSignal } = {}): Promise<DeviceTransfer> {
    return this.core.request('POST', '/api/v1/device-transfers', { ...opts, body: input });
  }

  /** The devices move in with their keys and session. A 502 means the LNS
   *  refused part way and every device moved was put back. */
  accept(
    transferId: string,
    input: { confirm: string; application?: string; profiles?: Record<string, string> },
    opts: { signal?: AbortSignal } = {},
  ): Promise<DeviceTransfer> {
    return this.core.request('POST', `/api/v1/device-transfers/${seg(transferId)}/accept`, { ...opts, body: input });
  }

  decline(transferId: string, opts: { signal?: AbortSignal } = {}): Promise<DeviceTransfer> {
    return this.core.request('POST', `/api/v1/device-transfers/${seg(transferId)}/decline`, opts);
  }

  cancel(transferId: string, opts: { signal?: AbortSignal } = {}): Promise<DeviceTransfer> {
    return this.core.request('POST', `/api/v1/device-transfers/${seg(transferId)}/cancel`, opts);
  }
}
