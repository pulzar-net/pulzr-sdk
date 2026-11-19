# pulzr

Python client for the Pulzar API. Python 3.9+, two dependencies (`httpx` and `tenacity`).

Full documentation: https://app.pulzr.net/docs

## Install

```bash
pip install pulzr
```

`pip install "pulzr[mqtt]"` adds paho-mqtt, for `pulzr.mqtt.Session`
(https://app.pulzr.net/docs/mqtt).

From a checkout of [pulzar-net/pulzr-sdk](https://github.com/pulzar-net/pulzr-sdk):

```bash
pip install ./python
```

## Quickstart

Create a key at Developers > API keys in the console (`/api-keys`). The key belongs to one org;
`org=` is only needed with a person's token that has several.

```python
import pulzr

client = pulzr.Client(api_key="pzk_...")  # or set PULZR_API_KEY

for device in client.readings.latest("temperature"):
    value = device["readings"]["temperature"]
    unit = device["units"]["temperature"]
    print(f'{device["name"]:<24} {value} {unit}  at {device["readingTimes"]["temperature"]}')

series = client.readings.series("temperature", since="now-24h", group_by="device")
```

Readings are canonical: the same quantity and unit whatever the vendor's
codec calls the field. `client.quantities.list()` is the catalog.

## Streaming events

```python
with client.events.stream(types=["device.offline", "gateway.offline"]) as stream:
    for event in stream:
        print(event["type"], event["subject"], event["createdAt"])
```

A dropped connection, or the server closing the stream (it does after an
hour), is reopened from the last position, so nothing is skipped or repeated.
An org may hold 5 streams open per server; past that the open is refused with
a 429 and retried after its `Retry-After`. To survive a restart, store `stream.cursor` and pass it
back as `last_event_id=`. Without one the stream starts at the end of the log.

To read the log instead: `client.events.iter(after=cursor)` pages forward
until caught up; `client.events.list(before="now")` is the newest page.

## Verifying webhooks

Verify the raw body bytes, before parsing them.

```python
import pulzr
from flask import Flask, abort, request

app = Flask(__name__)
SECRET = "whsec_..."  # shown once, when the webhook is created

@app.post("/pulzr")
def receive():
    try:
        event = pulzr.webhooks.construct_event(
            SECRET, request.get_data(), request.headers.get("Parkeze-Signature"))
    except pulzr.SignatureVerificationError:
        abort(400)
    # Delivery is at least once: deduplicate on event["id"].
    handle(event)
    return "", 204
```

During a secret rotation both secrets sign each delivery for 24 hours; pass
both while you redeploy: `construct_event([new, old], body, header)`.
`pulzr.webhooks.verify_signature(...)` returns a bool instead of raising.

## Devices

```python
client.devices.list()                                   # every device that has reported
client.devices.readings("a84041000181c061", since="now-7d")
client.devices.downlinks.enqueue("a84041000181c061", f_port=10, data=b"\x01")
client.devices.provision("a84041000181c061", app_key="...", device_profile="...")
```

## Agents

```python
thread = client.agents.threads.create()
stream = client.agents.send(thread["id"], "Which gateways went offline today?")
for event in stream:
    if isinstance(event, pulzr.TextEvent):
        print(event.delta, end="")
    elif isinstance(event, pulzr.ApprovalRequiredEvent):
        ...  # decide with client.agents.approve(event.run_id, decisions)
```

The run belongs to the server: closing the stream stops listening, not the
run. `client.agents.cancel(run_id)` stops it.

## Errors

Every failure raises a subclass of `pulzr.PulzrError` with `status`,
`message`, `details` and the response `body`:

| Status | Class |
|---|---|
| 400, 422 | `ValidationError` |
| 401 | `AuthenticationError` |
| 403 | `PermissionDeniedError` (missing scope or not an org admin) |
| 404 | `NotFoundError` |
| 409 | `ConflictError`; a quota refusal sets `resource` and `limit` |
| 429 | `RateLimitError` |
| 5xx | `ServerError` |
| no response | `APIConnectionError` |

GET, PUT and DELETE are retried on 429, 5xx and connection errors
(`max_retries=2`, exponential backoff, `Retry-After` honoured). POST and PATCH
are never retried: one that timed out may already have queued the downlink or
registered the device.

## Anything not wrapped

```python
client.request("GET", "/api/v1/data/devices/a84041000181c061/events")
```

## Command line

The package installs `pulzr`, built on this client:

```bash
pulzr login                      # prompts for the key; stored 0600, never printed
pulzr devices list
pulzr events tail --types device.offline
pulzr api --list                 # every operation in the server's spec
pulzr api getDevice --param devEui=a84041000181c061
```

Table on a terminal, JSON when piped (`-o json|table`). Exit 0 ok, 1 API
error, 2 usage error. Full reference: https://app.pulzr.net/docs/cli

## Tests

```bash
cd python && PYTHONPATH=src python -m unittest discover -s tests
```
