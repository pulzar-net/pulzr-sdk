/**
 * Response and request shapes, from the routes in net-api/routes/. Objects the
 * API passes through from elsewhere -- a codec's decoded fields, a model's
 * tool input, the LNS's own records -- are left as `Record<string, unknown>`
 * rather than guessed at.
 */

import type {
  AnyEvent,
  CanonicalReading,
  EventType,
  FindingSeverity,
  FindingStatus,
  ToolClass,
} from './events.js';

export type Json = Record<string, unknown>;

// ── devices ─────────────────────────────────────────────────────────────────

export interface DeviceHealth {
  devEui: string;
  name: string | null;
  lastSeen: string;
  /** This device's threshold: missed reports of its interval, or with no
   *  interval its application's fixed one. */
  offlineAfterMinutes: number;
  /** Set on the device or estimated from its uplinks; null when neither. */
  reportIntervalSeconds: number | null;
  intervalBasis: 'set' | 'estimated' | 'application' | 'default';
  online: boolean;
  rssi: number | null;
  snr: number | null;
  applicationId: string | null;
}

/** Devices that have reported. One never heard from is absent, not offline. */
export interface DeviceHealthList {
  online: number;
  offline: number;
  result: DeviceHealth[];
}

export interface DeviceTypeRef {
  id: string;
  vendor: string;
  model: string;
}

export interface DeviceDetail {
  devEui: string;
  transport: 'lorawan' | 'ble';
  mac: string | null;
  name: string | null;
  applicationId: string | null;
  deviceProfileId: string | null;
  deviceType: DeviceTypeRef | null;
  totals: {
    uplinks: number;
    firstSeen: string | null;
    lastSeen: string | null;
    avgRssi: number | null;
    avgSnr: number | null;
    perHour: number | null;
  };
  latest: {
    time: string | null;
    rssi: number | null;
    snr: number | null;
    fPort: number | null;
    fCnt: number | null;
    gatewayId: string | null;
  } | null;
  fields: Array<{
    field: string;
    value: unknown;
    unit: string | null;
    description: string | null;
    undeclared: boolean;
    show: string | null;
    label: string | null;
    invert: boolean;
    favorite: boolean;
  }>;
}

export interface QueuedDownlink {
  id: string | null;
  fPort: number | null;
  confirmed: boolean;
  /** Base64. */
  data: string | null;
  isPending: boolean;
  fCntDown: number | null;
  expiresAt: string | null;
}

export interface DownlinkInput {
  fPort: number;
  /** Raw bytes, or base64 of them. Give this or `object`, not both. */
  data?: Uint8Array | string;
  /** Encoded by the device profile's codec. */
  object?: Json;
  confirmed?: boolean;
}

export interface SentCommand {
  id: number | string;
  sentAt: string | null;
  commandId: string;
  title: string;
  params: Record<string, number>;
  fPort: number | null;
  payload: string | null;
  confirmed: boolean | null;
  queueId: string | null;
  sentBy: string | null;
  /** A Bluetooth command's outcome as relayed by a gateway; null for LoRaWAN. */
  relay: Json | null;
}

export interface DeviceCommands {
  deviceType: DeviceTypeRef | null;
  transport: 'lorawan' | 'ble';
  /** Each command by id, with its arguments' bounds. */
  commands: Json[];
  sent: SentCommand[];
}

export type ProvisionInput =
  | {
      transport?: 'lorawan';
      devEui: string;
      joinEui?: string;
      appKey: string;
      deviceProfile: string;
      application?: string;
      name?: string;
      tags?: Record<string, string>;
    }
  | {
      transport: 'ble';
      mac: string;
      /** A Bluetooth device type, by id or "Vendor Model". */
      deviceType: string;
      application?: string;
      name?: string;
      description?: string;
      tags?: Record<string, string>;
      password?: string;
      minRssi?: number;
    };

export interface ProvisionResult {
  deviceId: string;
  devEui?: string;
  mac?: string;
  applicationId: string;
  deviceProfileId?: string;
  deviceTypeId?: string;
  /** False when the device already existed here and was updated. */
  created: boolean;
}

// ── readings ────────────────────────────────────────────────────────────────

export type Window = 'now-1h' | 'now-6h' | 'now-24h' | 'now-7d' | 'now-30d' | 'now-90d';
export type Aggregate = 'mean' | 'min' | 'max' | 'last' | 'count' | 'sum';

export interface Quantity {
  id: string;
  label: string;
  unit: string;
  kind: 'number' | 'boolean';
  description: string;
  units: string[];
  unitOptional: boolean;
  /** Devices in this org that have reported it. */
  devices: number;
  deviceTypes: Array<DeviceTypeRef & { fields: string[] }>;
}

export interface LatestReadings {
  devEui: string;
  name: string | null;
  applicationId: string | null;
  deviceType: DeviceTypeRef | null;
  lastSeen: string;
  /** Keyed `quantity` or `quantity.channel`. */
  readings: Record<string, number | boolean>;
  readingTimes: Record<string, string>;
  units: Record<string, string>;
  /** What the type can report, so an absent key reads "not recently", not "never". */
  reports: string[];
  location: { latitude: number; longitude: number; source: 'device' | 'gateway' } | null;
}

export interface LatestQuery {
  quantity?: string;
  channel?: string;
  applicationId?: string;
  devices?: string[];
  deviceTypeId?: string;
}

export interface SeriesQuery {
  quantity: string;
  channel?: string;
  from?: Window;
  /** `<n><s|m|h|d>`, e.g. `15m`; chosen from the window when omitted. */
  interval?: string;
  aggregate?: Aggregate;
  devices?: string[];
  applicationId?: string;
  groupBy?: 'device' | 'none';
}

export interface Series {
  quantity: string;
  channel: string | null;
  unit: string;
  kind: 'number' | 'boolean';
  aggregate: Aggregate;
  interval: string;
  groupBy: 'device' | 'none';
  from: string;
  to: string;
  /** DevEUIs when grouped by device, else `["value"]`. */
  keys: string[];
  names: Record<string, string | null>;
  /** Booleans are 0 and 1. */
  series: Array<{ t: string } & Record<string, number | null | string>>;
}

export interface DeviceReadings {
  devEui: string;
  name: string | null;
  deviceType: DeviceTypeRef | null;
  from: string;
  to: string;
  readings: Array<CanonicalReading & { key: string; label: string; time: string }>;
  rows: Array<{ time: string; readings: Record<string, number | boolean>; data: Json }>;
}

// ── device types ────────────────────────────────────────────────────────────

export interface FieldSchemaEntry {
  type?: string;
  unit?: string;
  description?: string;
  quantity?: string;
  channel?: string;
  [key: string]: unknown;
}

export interface DeviceType {
  id: string;
  vendor: string;
  model: string;
  description: string | null;
  fieldSchema: Record<string, FieldSchemaEntry> | null;
  occupancy: Json | null;
  /**
   * Text values its codec has renamed, `{field: {former: current}}`. Filters
   * match either spelling and query rows carry the current one.
   */
  valueAliases: Record<string, Record<string, string>>;
  display: Json;
  configSchema: Json | null;
  commands: Json[];
  transport: 'lorawan' | 'ble';
  /** Its own JavaScript, or a payload format whose decoder Pulzar ships. */
  decoder: 'javascript' | 'cayenne_lpp';
  bleEmit: Json | null;
  bleConfig: Json | null;
  bleDeployed: string | null;
  /** Another org's, shared with this one. */
  shared: boolean;
  /** What this org may do with it. Below `read`, nothing about its codec is returned. */
  access: 'use' | 'read' | 'edit' | 'own';
  owner: { alias: string; name: string };
  /** Shared with every org. */
  public: boolean;
  /** Short hash of the newest codec commit, or null when none is saved or it is not readable. */
  latest: string | null;
}

export interface CodecVersion {
  oid: string;
  shortOid: string;
  message: string;
  author: string;
  authorEmail: string | null;
  /** Unix seconds. */
  committedAt: number;
  parent: string | null;
  labels: string[];
}

export interface DeployResult {
  deployed: true;
  commit: string;
  shortOid: string;
  runtime?: 'ble';
}

/** `null` removes a field's mapping. */
export type QuantityMapping = Record<string, { quantity: string; unit?: string; channel?: string } | null>;

// ── events and webhooks ─────────────────────────────────────────────────────

export interface EventPage {
  result: AnyEvent[];
  /** Forward pages always carry the cursor to send next, even when empty. */
  next: string | null;
  hasMore: boolean;
}

export interface EventQuery {
  /** Oldest first, after this cursor. */
  after?: string;
  /** Newest first, before this cursor; `now` is the newest page. */
  before?: string;
  types?: EventType[];
  subject?: string;
  /** 1 to 500. */
  limit?: number;
}

export interface EventTypeInfo {
  type: EventType;
  description: string;
}

export type DeliveryStatus = 'pending' | 'failed' | 'succeeded' | 'abandoned';

export interface Webhook {
  id: string;
  url: string;
  description: string | null;
  eventTypes: EventType[];
  /** Empty: every application. */
  applicationIds: string[];
  enabled: boolean;
  disabledReason: string | null;
  disabledAt: string | null;
  consecutiveFailures: number;
  failingSince: string | null;
  lastSuccessAt: string | null;
  lastFailureAt: string | null;
  /** Until when the previous secret still signs, during a rotation. */
  previousSecretExpiresAt: string | null;
  lastDelivery: { status: DeliveryStatus; at: string | null; responseStatus: number | null } | null;
  createdBy: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface WebhookInput {
  url: string;
  eventTypes: EventType[];
  applicationIds?: string[];
  description?: string | null;
}

export interface WebhookUpdate {
  url?: string;
  eventTypes?: EventType[];
  applicationIds?: string[];
  description?: string | null;
  enabled?: boolean;
}

export interface WebhookDelivery {
  id: string;
  endpointId: string;
  eventId: string;
  eventType: string;
  status: DeliveryStatus;
  attempt: number;
  maxAttempts: number;
  nextAttemptAt: string | null;
  lastAttemptAt: string | null;
  latencyMs: number | null;
  error: string | null;
  request: { headers: Record<string, string> | null; body: Json | null };
  response: { status: number | null; body: string | null };
  createdAt: string;
}

// ── integrations ────────────────────────────────────────────────────────────

export type IntegrationTemplateId =
  | 'influxdb'
  | 'datacake'
  | 'thingsboard'
  | 'aws_iot_core'
  | 'azure_iot_hub'
  | 'akenza'
  | 'ubidots'
  | 'tagoio'
  | 's3';

export interface IntegrationTemplate {
  id: IntegrationTemplateId;
  name: string;
  description: string;
  /** The vendor's ingestion API reference the template follows. */
  docs: string;
  eventTypes: EventType[];
  /** An uplink with no canonical readings is not sent. */
  needsReadings: boolean;
  /** Deliveries carry many events (S3). */
  batches: boolean;
  /** JSON Schema; a property with `x-secret: true` is a credential. */
  settings: { type: 'object'; properties: Record<string, unknown>; required: string[] };
}

export interface Integration {
  id: string;
  template: IntegrationTemplateId;
  templateName: string;
  name: string;
  /** The non-secret settings. */
  settings: Record<string, unknown>;
  /** Names of the secret settings that are set, never their values. */
  secretsSet: string[] | null;
  eventTypes: EventType[];
  applicationIds: string[];
  enabled: boolean;
  disabledReason: string | null;
  disabledAt: string | null;
  consecutiveFailures: number;
  failingSince: string | null;
  lastSuccessAt: string | null;
  lastFailureAt: string | null;
  lastDelivery: { status: DeliveryStatus; at: string | null; responseStatus: number | null } | null;
  /** Events buffered for the next object, for a batching template. */
  batchWaiting: number | null;
  createdBy: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface IntegrationInput {
  template: IntegrationTemplateId;
  name: string;
  settings: Record<string, unknown>;
  eventTypes?: EventType[];
  applicationIds?: string[];
}

export interface IntegrationUpdate {
  name?: string;
  settings?: Record<string, unknown>;
  eventTypes?: EventType[];
  applicationIds?: string[];
  enabled?: boolean;
}

/** A request as rendered for a person, credentials masked as `****`. */
export interface IntegrationRequest {
  method: string;
  url: string;
  headers: Record<string, string>;
  body: string;
  bodyBytes: number;
}

export interface IntegrationDelivery {
  id: string;
  integrationId: string;
  eventId: string;
  /** The event type, `integration.test`, or `batch`. */
  eventType: string;
  /** How many events a batch carried. */
  events: number | null;
  status: DeliveryStatus;
  attempt: number;
  maxAttempts: number;
  nextAttemptAt: string | null;
  lastAttemptAt: string | null;
  latencyMs: number | null;
  error: string | null;
  request: { method: string | null; url: string | null; headers: Record<string, string> | null; body: string | null };
  response: { status: number | null; body: string | null };
  createdAt: string;
}

// ── onboarding ──────────────────────────────────────────────────────────────

export type OnboardingStatus =
  | 'identifying'
  | 'generating'
  | 'verifying'
  | 'ready'
  | 'deploying'
  | 'registering'
  | 'waiting_for_uplink'
  | 'live'
  | 'failed'
  | 'abandoned';

export interface CatalogHit {
  source: 'org' | 'parkeze' | 'repository';
  /** A device type id, or `vendor/device` for the repository. */
  id: string;
  vendor: string;
  model: string;
  transport: 'lorawan' | 'ble';
  description: string;
  /** A device registered now would decode. */
  ready: boolean;
  deviceProfileId: string | null;
  hasCodec: boolean | null;
}

export interface LorawanSettings {
  region: string;
  macVersion: string;
  regParamsRevision: string;
  supportsOtaa: boolean;
  supportsClassB: boolean;
  supportsClassC: boolean;
  uplinkIntervalSeconds: number;
}

export interface OnboardingSession {
  id: string;
  status: OnboardingStatus;
  failure: string | null;
  vendor: string | null;
  model: string | null;
  transport: 'lorawan' | 'ble' | null;
  source: 'catalog' | 'generated' | null;
  catalog: { source: CatalogHit['source']; id: string } | null;
  identity: Json | null;
  lorawan: LorawanSettings | null;
  codec: { source: string; fieldSchema: Record<string, FieldSchemaEntry>; testVectors: Json[]; notes: string } | null;
  verification: { vectors: Json[]; passed: number; total: number; replay: Json | null; at: string } | null;
  repairRounds: Array<{ round: number; at: string; failures: Json[]; passedBefore: number; total: number; notes: string }>;
  deviceTypeId: string | null;
  deviceProfileId: string | null;
  datasheetId: string | null;
  hasDatasheet: boolean;
  codecCommit: string | null;
  timeline: Array<{ step: string; status: OnboardingStatus; at: string; detail: Json | null }>;
  devices: string[];
  createdBy: string | null;
  startedAt: string;
  updatedAt: string;
  registeredAt: string | null;
  firstJoinAt: string | null;
  firstUplinkAt: string | null;
  secondsToFirstUplink: number | null;
}

/** Bytes, or base64 of them. */
export type Upload = Uint8Array | string;

export interface OnboardingStart {
  catalog?: { source: CatalogHit['source']; id: string };
  datasheetText?: string;
  datasheetPdf?: Upload;
  datasheetPdfFilename?: string;
  /** PNG or JPEG. */
  labelPhoto?: Upload;
  vendor?: string;
  model?: string;
  /** The payload format the board speaks. Needs `vendor` and `model`. */
  decoder?: 'cayenne_lpp';
}

export interface OnboardingAccept {
  lorawan?: Partial<LorawanSettings>;
  fieldSchema?: Record<string, { quantity?: string | null; channel?: string | null }>;
}

export interface OnboardingDevicesInput {
  devices?: Array<
    | { devEui: string; joinEui?: string; appKey: string; name?: string }
    | { qr: string; appKey: string; name?: string }
    | { mac: string; name?: string }
  >;
  /** LoRa Alliance TR005 texts, `LW:D0:...`. */
  qr?: string[];
  csv?: string;
  labelPhoto?: Upload;
  application?: string;
}

export interface ParsedDeviceRow {
  name: string | null;
  devEui?: string;
  joinEui?: string;
  appKey?: string;
  mac?: string | null;
  qr?: string;
  problem: string | null;
}

export interface DryRunResult {
  rows: ParsedDeviceRow[];
  problems: Array<{ row: number; devEui: string | null; error: string }>;
}

export interface RegisterResult {
  result: Array<{ devEui: string | null; ok: boolean; created?: boolean; error?: string }>;
  session: OnboardingSession;
}

export interface OnboardingMetricsBucket {
  started: number;
  live: number;
  medianSeconds: number | null;
  p90Seconds: number | null;
}

export interface OnboardingMetrics extends OnboardingMetricsBucket {
  windowDays: number;
  bySource: { catalog: OnboardingMetricsBucket; generated: OnboardingMetricsBucket };
}

export type OnboardingWatchEvent =
  | { type: 'session'; data: OnboardingSession }
  | { type: 'join'; data: { devEui: string; time: string } }
  | {
      type: 'uplink';
      data: {
        devEui: string;
        time: string;
        fPort: number | null;
        fCnt: number | null;
        rssi: number | null;
        snr: number | null;
        data: Json;
        readings: CanonicalReading[];
      };
    }
  | { type: 'first_uplink'; data: { devEui: string | null; time: string; secondsToFirstUplink: number | null } }
  | { type: 'end'; data: { reason: 'failed' | 'abandoned' | 'live' | 'deadline' } };

// ── agents ──────────────────────────────────────────────────────────────────

export type RunStatus = 'queued' | 'running' | 'awaiting_approval' | 'completed' | 'failed' | 'cancelled';
export type Effort = 'low' | 'medium' | 'high' | 'xhigh' | 'max';
export type Autonomy = 'observe' | 'propose' | 'act';

export interface Usage {
  inputTokens: number;
  outputTokens: number;
  cacheReadTokens: number;
  cacheWriteTokens: number;
}

export interface Run {
  id: string;
  threadId: string | null;
  agentId: string | null;
  agentName: string | null;
  trigger: 'interactive' | 'event' | 'schedule' | 'manual';
  triggerEventId: string | null;
  triggerSubject: string | null;
  status: RunStatus;
  model: string | null;
  effort: Effort | null;
  usage: Usage;
  stopReason: string | null;
  error: string | null;
  createdAt: string;
  startedAt: string | null;
  finishedAt: string | null;
}

export interface PageContext {
  path: string;
  entities?: {
    devEui?: string;
    gatewayId?: string;
    applicationId?: string;
    deviceTypeId?: string;
    dashboardId?: string;
    agentId?: string;
  };
}

export interface Thread {
  id: string;
  title: string;
  pageContext: PageContext | null;
  createdAt: string;
  updatedAt: string;
  lastRun: { id: string; status: RunStatus } | null;
}

/** Anthropic content blocks, stored as the model produced them. */
export type ContentBlock =
  | { type: 'text'; text: string }
  | { type: 'thinking'; thinking: string; signature: string }
  | { type: 'redacted_thinking'; [key: string]: unknown }
  | { type: 'tool_use'; id: string; name: string; input: Json }
  | {
      type: 'tool_result';
      tool_use_id: string;
      content: string | Array<{ type: 'text'; text: string }>;
      is_error?: boolean;
    }
  | { type: 'fallback'; [key: string]: unknown };

export interface Message {
  seq: number;
  role: 'user' | 'assistant';
  content: ContentBlock[];
  createdAt: string;
  runId: string | null;
}

export interface Approval {
  toolUseId: string;
  tool: string;
  input: Json;
  class: 'write' | 'destructive';
  /** Destructive only: what the person must type to approve it. */
  confirm: string | null;
  decision: 'approved' | 'denied' | null;
  decidedBy: string | null;
  decidedAt: string | null;
}

export interface ThreadDetail extends Thread {
  messages: Message[];
  runs: Run[];
  pending: { runId: string; approvals: Approval[] } | null;
}

export interface SendInput {
  text: string;
  pageContext?: PageContext;
  /** Writes run without asking; deletions still wait for a person. */
  autoApproveWrites?: boolean;
  effort?: Effort;
}

export interface Decision {
  toolUseId: string;
  approve: boolean;
  /** Required to approve a destructive action: its `confirm` value. */
  confirm?: string;
}

/** What `send` and `approve` stream, narrowed by `type`. */
export type AgentStreamEvent =
  | { type: 'run'; data: { runId: string; threadId: string | null; status: 'running' } }
  /** Markdown. Text after a `tool_result` begins a new assistant turn. */
  | { type: 'text'; data: { delta: string } }
  | { type: 'thinking'; data: { delta: string } }
  | { type: 'tool_call'; data: { id: string; name: string; input: Json; class: ToolClass } }
  | { type: 'tool_result'; data: { id: string; name: string; isError: boolean; summary: string; truncated: boolean } }
  | { type: 'approval_required'; data: { runId: string; approvals: Approval[] } }
  /** Run totals so far. */
  | { type: 'usage'; data: Usage }
  /** Always last. Refetch the thread for the stored transcript. */
  | { type: 'done'; data: { runId: string; status: RunStatus; stopReason: string | null } }
  | { type: 'error'; data: { error: string } };

export interface Triggers {
  events: Array<{ type: EventType; filter?: Record<string, string | number | boolean | Array<string | number | boolean>> }>;
  /** Five-field cron, UTC. */
  schedule: string | null;
  debounceMinutes: number;
}

export interface Agent {
  id: string;
  name: string;
  template: string | null;
  instructions: string;
  triggers: Triggers;
  autonomy: Autonomy;
  scopes: string[];
  effort: Effort;
  enabled: boolean;
  owner: string | null;
  mine: boolean;
  keyPrefix: string | null;
  lastRunAt: string | null;
  nextRunAt: string | null;
  createdAt: string;
  updatedAt: string;
  openFindings: number;
  lastRun: Run | null;
  /** Why scheduled and event runs are not starting (the org's daily token
   *  budget is spent), or null. */
  held: string | null;
}

export interface AgentInput {
  name?: string;
  template?: string;
  instructions?: string;
  triggers?: Partial<Triggers>;
  autonomy?: Autonomy;
  scopes?: string[];
  effort?: Effort;
  enabled?: boolean;
}

export interface AgentTemplate {
  id: string;
  name: string;
  description: string;
  instructions: string;
  triggers: Triggers;
  autonomy: Autonomy;
  scopes: string[];
  effort: Effort;
}

export interface AgentTemplates {
  result: AgentTemplate[];
  eventTypes: Array<{ type: EventType; description: string }>;
  scopes: { areas: Array<{ id: string; label: string }>; admin: string | null };
}

export interface RunDetail {
  run: Run;
  messages: Message[];
  approvals: Approval[];
}

export interface Finding {
  id: string;
  agentId: string | null;
  agentName: string | null;
  runId: string | null;
  severity: FindingSeverity;
  title: string;
  /** Markdown. */
  body: string;
  subject: string | null;
  /** Console path for the subject, e.g. `/devices/<eui>`. */
  subjectPath: string | null;
  status: FindingStatus;
  createdAt: string;
  updatedAt: string;
  acknowledgedBy: string | null;
  resolvedBy: string | null;
  resolvedAt: string | null;
}

export interface FindingQuery {
  status?: FindingStatus;
  severity?: FindingSeverity;
  agent?: string;
}

/** GET /api/v1/mqtt/connection. */
export interface MqttConnection {
  host: string;
  port: number;
  tls: boolean;
  /** The org alias: the MQTT username. The password is an API key. */
  username: string;
  scopes: { subscribe: string; publish: string };
  qos: number;
  retained: boolean;
  topics: Record<string, string>;
  examples: Record<string, string>;
  /** null when the server cannot ask the broker. */
  connected: boolean | null;
  sessions: Array<{ clientId: string; connectedAt: string; key: { name: string; prefix: string } }>;
  lastAttempt: { at: string; outcome: string; clientId: string | null; reason: string | null } | null;
}

/** What `down/push` and `down/command` are answered with on `down/ack`. */
export interface MqttAck {
  id: string;
  correlationId: string | null;
  devEui: string;
  kind: 'push' | 'command';
  ok: boolean;
  status: number;
  result: Record<string, unknown> | null;
  error: string | null;
}

/** A device the org is owner of record for. Never carries a code or a key. */
export interface RegistryEntry {
  id: string;
  devEui: string;
  joinEui: string;
  deviceTypeId: string | null;
  /** TR005 ProfileID: VendorID + ModelID. */
  profileId: string;
  serial: string | null;
  name: string | null;
  status: 'unclaimed' | 'claimed' | 'withdrawn';
  validUntil: string | null;
  claimedAt: string | null;
  keysRotated: boolean;
  released: boolean;
  createdBy: string | null;
  createdAt: string;
}

/** An entry in the one response that has its claim code in clear. */
export interface RegistryLabel extends RegistryEntry {
  claimCode: string;
  claimCodeGrouped: string;
  /** The TR005 text, `LW:D0:<JoinEUI>:<DevEUI>:<ProfileID>:O<code>`. */
  qr: string;
  qrSvg: string;
}

export interface RegistryRow {
  devEui: string;
  joinEui?: string;
  appKey: string;
  claimCode?: string;
  serial?: string;
  name?: string;
}

export type ClaimInput =
  | { qr: string; application?: string; deviceProfile?: string; name?: string }
  | { devEui: string; claimCode: string; application?: string; deviceProfile?: string; name?: string };

export interface ClaimResult {
  devEui: string;
  name: string;
  applicationId: string;
  deviceProfileId: string;
  created: boolean;
}

export type TransferStatus = 'offered' | 'accepting' | 'accepted' | 'declined' | 'cancelled' | 'expired' | 'failed';

export interface DeviceTransfer {
  id: string;
  direction: 'incoming' | 'outgoing';
  from: { alias: string; displayName: string };
  to: { alias: string; displayName: string };
  scope: 'device' | 'application';
  application: { id: string; name: string } | null;
  /** What both sides type: the DevEUI or the application name. */
  confirm: string;
  note: string | null;
  status: TransferStatus;
  offeredBy: string;
  offeredAt: string;
  expiresAt: string;
  decidedBy: string | null;
  decidedAt: string | null;
  toApplicationId: string | null;
  failure: string | null;
  deviceCount: number;
  devices: Array<{ devEui: string; name: string | null; transport: string;
    outcome: 'moved' | 'returned' | 'stranded' | 'skipped' | null }>;
}

export type TransferOffer =
  | { toOrg: string; confirm: string; devEui: string; expiresInDays?: number; note?: string }
  | { toOrg: string; confirm: string; application: string; expiresInDays?: number; note?: string };

export interface SqlResult {
  columns: { name: string; type: string }[];
  /** Each row in the order of `columns`: timestamps as ISO strings, jsonb as
   *  objects, bytea as hex. */
  rows: unknown[][];
  rowCount: number;
  truncated: boolean;
  elapsedMs: number;
}
