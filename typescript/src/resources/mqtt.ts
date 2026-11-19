import type { Core } from '../core.js';
import type { MqttConnection } from '../types.js';

/**
 * How to connect to the broker. Connecting is any MQTT client's job: this
 * package adds no dependency for it. Username the org alias, password the
 * API key, client id from `mqttClientId`; the topics and payloads are in
 * /docs/mqtt.
 *
 *   const info = await client.mqtt.connection();
 *   const broker = mqtt.connect(`mqtts://${info.host}:${info.port}`, {
 *     username: info.username, password: apiKey,
 *     clientId: mqttClientId(apiKey, 'cold-chain-1'), clean: false,
 *   });
 *   broker.subscribe(mqttTopics.all(info.username), { qos: 1 });
 */
export class Mqtt {
  constructor(private readonly core: Core) {}

  /** Host, port, username and this org's topics. Needs `data:read`. */
  connection(opts: { signal?: AbortSignal } = {}): Promise<MqttConnection> {
    return this.core.request('GET', '/api/v1/mqtt/connection', opts);
  }
}

/**
 * A client id the broker accepts for this key: the key's prefix (`pzk_` and
 * 8 hex, its first 12 characters), a dash, then `name` -- or a random suffix
 * for a session that need not outlast the process. The broker refuses any
 * other: a client id names a session the next connection under it resumes,
 * and the prefix makes it this key's alone.
 */
export function mqttClientId(apiKey: string, name?: string): string {
  const prefix = apiKey.slice(0, 12);
  if (!/^pzk_[0-9a-f]{8}$/.test(prefix)) {
    throw new Error('Not a Pulzar API key: expected pzk_<8 hex>_...');
  }
  if (name && name.startsWith(prefix)) return name;
  return `${prefix}-${name || randomSuffix()}`;
}

function randomSuffix(): string {
  // Only has to differ between processes; it is not a secret, so Node 18's
  // missing global crypto falls back to Math.random.
  const bytes = new Uint8Array(6);
  const crypto = (globalThis as { crypto?: Crypto }).crypto;
  if (crypto?.getRandomValues) crypto.getRandomValues(bytes);
  else bytes.forEach((_, i) => (bytes[i] = Math.floor(Math.random() * 256)));
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

/** The topic tree, the server's shapes exactly. `devEui` is lowercased. */
export const mqttTopics = {
  all: (org: string) => `v1/${org}/#`,
  uplink: (org: string, devEui: string) => `v1/${org}/devices/${devEui.toLowerCase()}/up`,
  deviceEvent: (org: string, devEui: string, type: string) =>
    `v1/${org}/devices/${devEui.toLowerCase()}/events/${type}`,
  push: (org: string, devEui: string) => `v1/${org}/devices/${devEui.toLowerCase()}/down/push`,
  command: (org: string, devEui: string) => `v1/${org}/devices/${devEui.toLowerCase()}/down/command`,
  ack: (org: string, devEui: string) => `v1/${org}/devices/${devEui.toLowerCase()}/down/ack`,
};
