import { Core, type ClientOptions } from './core.js';
import { Agents } from './resources/agents.js';
import { BasicStation } from './resources/basicStation.js';
import { DeviceTypes } from './resources/deviceTypes.js';
import { Devices } from './resources/devices.js';
import { Events } from './resources/events.js';
import { Firmware, MulticastGroups, Relays } from './resources/fleet.js';
import { Gateways } from './resources/gateways.js';
import { Integrations } from './resources/integrations.js';
import { Mqtt } from './resources/mqtt.js';
import { Onboarding } from './resources/onboarding.js';
import { Quantities, Readings } from './resources/readings.js';
import { Airtime, Coverage } from './resources/radio.js';
import { Sims } from './resources/sims.js';
import { Webhooks } from './resources/webhooks.js';
import type { SqlResult } from './types.js';

export class PulzrClient {
  readonly devices: Devices;
  readonly gateways: Gateways;
  readonly sims: Sims;
  readonly basicStation: BasicStation;
  readonly readings: Readings;
  readonly quantities: Quantities;
  readonly airtime: Airtime;
  readonly coverage: Coverage;
  readonly events: Events;
  readonly webhooks: Webhooks;
  readonly integrations: Integrations;
  readonly onboarding: Onboarding;
  readonly agents: Agents;
  readonly deviceTypes: DeviceTypes;
  readonly mqtt: Mqtt;
  readonly multicastGroups: MulticastGroups;
  readonly relays: Relays;
  readonly firmware: Firmware;
  /** The HTTP layer, for a route this client has no method for yet. */
  readonly http: Core;

  constructor(options: ClientOptions) {
    this.http = new Core(options);
    this.devices = new Devices(this.http);
    this.gateways = new Gateways(this.http);
    this.sims = new Sims(this.http);
    this.basicStation = new BasicStation(this.http);
    this.readings = new Readings(this.http);
    this.quantities = new Quantities(this.http);
    this.airtime = new Airtime(this.http);
    this.coverage = new Coverage(this.http);
    this.events = new Events(this.http);
    this.webhooks = new Webhooks(this.http);
    this.integrations = new Integrations(this.http);
    this.onboarding = new Onboarding(this.http);
    this.agents = new Agents(this.http);
    this.deviceTypes = new DeviceTypes(this.http);
    this.mqtt = new Mqtt(this.http);
    this.multicastGroups = new MulticastGroups(this.http);
    this.relays = new Relays(this.http);
    this.firmware = new Firmware(this.http);
  }

  /** One read-only SELECT over the org's own tables. `limit` caps the rows,
   *  default 1000, at most 10000; `truncated` says it was hit. A refused query
   *  throws ValidationError with `position` on `.body`. */
  sql(query: string, opts: { limit?: number; signal?: AbortSignal } = {}): Promise<SqlResult> {
    const { limit, ...rest } = opts;
    return this.http.request('POST', '/api/v1/sql', { ...rest, body: limit === undefined ? { query } : { query, limit } });
  }
}
