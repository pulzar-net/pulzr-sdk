# @pulzr/sdk

TypeScript client for the Pulzr API. ESM, no runtime dependencies, uses the global `fetch`: Node 18+, browsers, Deno, Bun, Workers.

Full documentation: https://app.pulzr.net/docs

## Install

```bash
npm install @pulzr/sdk
```

## Quickstart

Create a key under API keys in the console. It acts for one org.

```ts
import { PulzrClient } from '@pulzr/sdk';

const client = new PulzrClient({ apiKey: process.env.PULZR_API_KEY! });

const { result: devices, offline } = await client.devices.list();
console.log(`${devices.length} devices, ${offline} offline`);

for (const device of await client.readings.latest({ quantity: 'temperature' })) {
  console.log(device.name, device.readings.temperature, device.units.temperature);
}
```

Options: `apiKey` (required), `org` (alias, sent as `X-Active-Org`), `baseUrl` (default `https://app.pulzr.net`), `fetch`, `maxRetries` (default 2), `timeoutMs`.

Resources: `devices`, `readings`, `quantities`, `deviceTypes`, `events`, `webhooks`, `onboarding`, `agents`. Lists without paging resolve to the array; `events.list` resolves to a page `{ result, next, hasMore }`.

## Errors and retries

Every failure is a `PulzrError` with `status`, `message`, `details` and the parsed `body`. Subclasses: `ValidationError` (400, 422), `AuthenticationError` (401), `PermissionDeniedError` (403), `NotFoundError` (404), `ConflictError` (409, including quota refusals: see `body.resource` and `body.limit`), `RateLimitError` (429), `ServerError` (5xx), `ConnectionError` (no response, or `timeoutMs` passed).

GET, PUT and DELETE are retried after 429, 5xx or a network error, with exponential backoff and jitter, honouring `Retry-After`. POST and PATCH are never retried: a POST that timed out may have registered the device or queued the downlink.

## Events

Page through the log:

```ts
for await (const event of client.events.iterate({ types: ['device.offline'] })) {
  console.log(event.subject, event.createdAt);
}
```

Or hold a stream open. It reconnects by itself and resumes from where it stopped. Save `stream.cursor` and pass it back as `lastEventId` to resume after a restart.

```ts
const stream = client.events.stream({ types: ['device.offline', 'gateway.offline'] });

for await (const event of stream) {
  switch (event.type) {
    case 'device.offline':
      console.log(event.data.device.name, 'silent since', event.data.lastSeen);
      break;
    case 'gateway.offline':
      console.log(event.data.gateway.gatewayId, 'down since', event.data.since);
      break;
  }
  await saveCursor(stream.cursor);
}
```

Pass `signal` to stop it. Delivery is at-least-once across all transports: deduplicate on `event.id`.

## Webhooks

Verify against the raw body exactly as received. A body parsed and re-serialized will not verify.

Express:

```ts
import express from 'express';
import { constructEvent, WebhookSignatureError } from '@pulzr/sdk';

const app = express();

app.post('/pulzr', express.raw({ type: 'application/json' }), async (req, res) => {
  try {
    const event = await constructEvent(process.env.PULZR_WEBHOOK_SECRET!, req.body, req.get('Parkeze-Signature'));
    if (event.type === 'uplink.received') console.log(event.data.readings);
    res.sendStatus(204);
  } catch (error) {
    if (error instanceof WebhookSignatureError) return res.sendStatus(400);
    throw error;
  }
});
```

A fetch-style handler (Next.js route handlers, Cloudflare Workers, Deno, Bun):

```ts
import { verifyWebhook } from '@pulzr/sdk';

export async function POST(request: Request) {
  const body = await request.text();
  const ok = await verifyWebhook(process.env.PULZR_WEBHOOK_SECRET!, body, request.headers.get('Parkeze-Signature') ?? '');
  if (!ok) return new Response('bad signature', { status: 400 });
  const event = JSON.parse(body);
  // ...
  return new Response(null, { status: 204 });
}
```

The signature is rejected more than 300 s from the receiver's clock (`tolerance` changes it). During the 24 hours after a secret is rotated, pass both secrets as an array; either verifies. Any 2xx is success; 410 disables the webhook.

## Onboarding

```ts
const session = await client.onboarding.start({ catalog: { source: 'parkeze', id: deviceTypeId } });
for await (const update of client.onboarding.watch(session.id)) {
  if (update.type === 'session') console.log(update.data.status);
  if (update.type === 'first_uplink') break;
}
```

`registerDevices(id, { qr, dryRun: true })` parses QR codes, CSV or a label photo without registering anything.

## Agents

```ts
const thread = await client.agents.threads.create({ title: 'Lot B' });

for await (const event of client.agents.send(thread.id, { text: 'Which bays in lot B are offline?' })) {
  if (event.type === 'text') process.stdout.write(event.data.delta);
  if (event.type === 'approval_required') {
    // Decide every pending action at once. A destructive one needs its `confirm` value typed back.
  }
}
```

The request is made when iteration starts. The run continues on the server if the connection drops; fetch the thread with `agents.threads.get` for the stored transcript.
