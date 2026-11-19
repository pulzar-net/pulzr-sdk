/**
 * The event envelope and each event type's `data`, as the producers write
 * them (event-dispatch/ingest.py, net-api utils/events.py, gateway_outages.py,
 * onboarding.py, utils/agents.py, routes/agents.py). shared/events.py `TYPES`
 * is the list. `_check` at the bottom keeps EVENT_TYPES and EventDataMap
 * agreeing with each other; agreeing with the server is by hand.
 *
 * A field may be added to `data` under the same `apiVersion`, so consumers
 * should ignore fields they do not know rather than reject the event.
 */

export const API_VERSION = '2026-10-01';

export const EVENT_TYPES = [
  'uplink.received',
  'device.joined',
  'device.offline',
  'device.online',
  'device.created',
  'device.deleted',
  'device.claimed',
  'device.transferred_out',
  'device.transferred_in',
  'device.fair_use_exceeded',
  'device.event',
  'command.result',
  'gateway.offline',
  'gateway.online',
  'gateway.tunnel_key_changed',
  'onboarding.first_uplink',
  'agent.finding',
  'agent.action_requested',
  'firmware.deployment_finished',
] as const;

export type EventType = (typeof EVENT_TYPES)[number];

/** `data.device` on every device event. */
export interface EventDevice {
  devEui: string;
  name: string | null;
  applicationId: string | null;
  deviceTypeId: string | null;
}

/** One canonical reading: a decoded field on its quantity's scale. */
export interface CanonicalReading {
  quantity: string;
  /** Tells two probes of one quantity apart; null when there is one. */
  channel: string | null;
  value: number | boolean;
  unit: string;
  /** The codec field it came from. */
  field: string;
}

export interface EventGateway {
  gatewayId: string;
  name: string | null;
}

export type FindingSeverity = 'info' | 'warning' | 'critical';
export type FindingStatus = 'open' | 'acknowledged' | 'resolved';
export type ToolClass = 'read' | 'write' | 'destructive';

export interface EventDataMap {
  'uplink.received': {
    device: EventDevice;
    /** Empty when the device's type maps no field to a quantity. */
    readings: CanonicalReading[];
    /** The codec's output exactly, in the vendor's own field names. */
    fields: Record<string, unknown>;
    radio: { rssi: number | null; snr: number | null; gatewayId: string | null; gatewayCount: number };
    fPort: number | null;
    fCnt: number | null;
    time: string | null;
  };
  'device.joined': { device: EventDevice; time: string | null };
  'device.offline': DeviceStateData;
  'device.online': DeviceStateData;
  'device.created': { device: EventDevice };
  'device.deleted': { device: EventDevice };
  'device.claimed': { device: EventDevice };
  /** In the org the device left. Its history stays there. */
  'device.transferred_out': { device: EventDevice; to: { alias: string }; transfer: string };
  /** In the org it arrived in, with its keys and session: no rejoin. */
  'device.transferred_in': { device: EventDevice; from: { alias: string }; transfer: string };
  /** At most once per device per UTC day. Nothing is dropped; this is a warning. */
  'device.fair_use_exceeded': {
    device: EventDevice;
    /** The UTC day, YYYY-MM-DD. */
    day: string;
    exceeded: Array<'uplinkAirtime' | 'downlinks'>;
    usage: { uplinks: number; uplinkAirtimeMs: number; downlinks: number };
    policy: FairUsePolicy;
  };
  /** An IP device's own event (device-link), named by its manifest. */
  'device.event': {
    device: EventDevice;
    name: string;
    severity: 'critical' | 'warning' | 'info';
    /** When it happened on the device, which may be before it was sent. */
    at: string;
    data: Record<string, unknown>;
  };
  /** An IP device's answer to a command, or `expired` when none came in time
   *  (the device runs nothing that arrives expired, so it did not happen). */
  'command.result': {
    device: EventDevice;
    command: string;
    id: number;
    result: 'ok' | 'refused' | 'failed' | 'expired';
    /** local_only, remote_false, unknown, invalid, busy, error, expired. */
    reason: string | null;
    response: { data?: unknown; detail?: string | null } | null;
    sentBy: string | null;
  };
  'gateway.offline': { gateway: EventGateway; since: string };
  'gateway.online': {
    gateway: EventGateway;
    outage: {
      silentFrom: string;
      backAt: string;
      bootedAt: string | null;
      cause: 'rebooted' | 'stayed_up' | 'unknown';
    };
  };
  /** Unexpected ones mean somebody else holds the gateway's claim secret. */
  'gateway.tunnel_key_changed': {
    gateway: EventGateway;
    previousAddress: string;
    address: string;
    /** False when the old key's tunnel was down, so it was given a new address. */
    addressKept: boolean;
  };
  'onboarding.first_uplink': {
    /** Every event's device, with what onboarding knows besides. */
    device: EventDevice & { vendor: string | null; model: string | null };
    /** The onboarding session's id. */
    session: string;
    secondsToFirstUplink: number | null;
  };
  'agent.finding': {
    agent: { id: string; name: string };
    run: string | null;
    finding: { id: string; severity: FindingSeverity; title: string; subject: string | null; status: FindingStatus };
  };
  'agent.action_requested': {
    agent: { id: string; name: string };
    run: string;
    /** Tool names only: the event log is read by every member, and the input
     *  may hold what only the agent's key could read. Open the run for it. */
    action: Array<{ tool: string; class: Exclude<ToolClass, 'read'> }>;
    /** The id of the "Approval needed" finding filed beside it. */
    finding: string;
  };
  'firmware.deployment_finished': {
    deployment: {
      id: string;
      name: string;
      applicationId: string;
      deviceProfileId: string;
      image: { name: string; version: string; sha256: string } | null;
    };
    /** `finished` when at least one device took the image. */
    status: 'finished' | 'failed';
    devices: { total: number; completed: number; failed: number };
    /** At most 100; `devices.failed` is the full count. */
    failures: Array<{ devEui: string; stage: FirmwareDeviceStage; error: string }>;
  };
}

export type FirmwareDeviceStage =
  | 'pending'
  | 'multicast_setup'
  | 'fragmentation_setup'
  | 'session'
  | 'status_check'
  | 'completed'
  | 'failed';

/** A plan's fair-use allowance, per device per UTC day. null is no limit. */
export interface FairUsePolicy {
  uplinkAirtimeSeconds: number | null;
  downlinks: number | null;
  mode: 'warn' | 'off';
}

export interface DeviceStateData {
  device: EventDevice;
  lastSeen: string | null;
  changedAt: string;
  offlineAfterMinutes: number | null;
}

/** Sent only to one webhook, by "Send test"; never in the event log. */
export interface WebhookTestData {
  webhook: { id: string; url: string };
}

export type WebhookEventDataMap = EventDataMap & { 'webhook.test': WebhookTestData };
export type WebhookEventType = keyof WebhookEventDataMap;

export interface EventEnvelope<T extends WebhookEventType = EventType> {
  /** `evt_` + a ULID. Delivery is at-least-once: deduplicate on this. */
  id: string;
  type: T;
  apiVersion: string;
  createdAt: string;
  /** The org's alias. */
  org: string;
  /** The device EUI or gateway id the event is about, when there is one. */
  subject: string | null;
  data: WebhookEventDataMap[T];
}

/** Any event from the log, narrowed by `type`. */
export type AnyEvent = { [T in EventType]: EventEnvelope<T> }[EventType];

/** Any body a webhook may receive, including a test delivery. */
export type WebhookEvent = { [T in WebhookEventType]: EventEnvelope<T> }[WebhookEventType];

// EVENT_TYPES and EventDataMap must name the same types.
type _Same<A, B> = [A] extends [B] ? ([B] extends [A] ? true : never) : never;
const _check: _Same<EventType, keyof EventDataMap> = true;
void _check;
