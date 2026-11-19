# Pulzar SDKs

Clients for the [Pulzar](https://pulzr.net) API: devices, readings, events,
webhooks, gateways, onboarding and agents.

| | Package | Install | Source |
|---|---|---|---|
| Python 3.9+ | [`pulzr`](https://pypi.org/project/pulzr/) | `pip install pulzr` | [`python/`](python) |
| TypeScript (Node 18+, browsers, Deno, Bun, Workers) | [`@pulzr/sdk`](https://www.npmjs.com/package/@pulzr/sdk) | `npm install @pulzr/sdk` | [`typescript/`](typescript) |

```python
import pulzr

client = pulzr.Client()  # PULZR_API_KEY
for device in client.readings.latest("temperature"):
    print(device["name"], device["readings"]["temperature"], device["units"]["temperature"])
```

```ts
import { PulzrClient } from '@pulzr/sdk';

const client = new PulzrClient({ apiKey: process.env.PULZR_API_KEY! });
const devices = await client.readings.latest({ quantity: 'temperature' });
```

The Python package also installs `pulzr`, a command line on the same client.

Documentation: https://app.pulzr.net/docs/sdks

Both verify webhook signatures against the same test vectors
([`fixtures/webhook-signatures.json`](fixtures/webhook-signatures.json)),
which the server generates from its own signing code.

## This repository

It is a copy of `sdk/` in Pulzar's platform repository, updated on every
change there, so the SDKs are versioned and tested with the API they call.
Issues are welcome here; a pull request is read here and applied there.

A new version in `python/src/pulzr/_version.py` or `typescript/package.json`
is tagged `python-v<version>` or `typescript-v<version>` and published to
PyPI or npm from this repository's Release workflow, with trusted publishing
(no stored tokens) and npm provenance.

MIT licensed.
