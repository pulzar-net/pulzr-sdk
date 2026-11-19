"""Shapes of what the API returns, for editors and type checkers.

TypedDicts rather than classes: responses stay the plain dicts the API sent,
so a field added server-side under the same `apiVersion` reaches the caller
without an SDK release. Most are `total=False` for the same reason a reader
should not assume every field is present on every route that returns one.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict, Union


class Envelope(TypedDict):
    """One event, the same on a webhook, the stream and the event log."""

    id: str
    type: str
    apiVersion: str
    createdAt: str
    org: str
    subject: Optional[str]
    data: Dict[str, Any]


class EventPage(TypedDict):
    result: List[Envelope]
    next: Optional[str]
    hasMore: bool


class EventType(TypedDict):
    type: str
    description: str


class DeviceTypeRef(TypedDict):
    id: str
    vendor: str
    model: str


class Location(TypedDict):
    latitude: float
    longitude: float
    source: str


class LatestReadings(TypedDict, total=False):
    devEui: str
    name: Optional[str]
    applicationId: Optional[str]
    deviceType: Optional[DeviceTypeRef]
    lastSeen: str
    readings: Dict[str, Union[float, bool]]
    readingTimes: Dict[str, str]
    units: Dict[str, Optional[str]]
    reports: List[str]
    location: Optional[Location]


class Series(TypedDict, total=False):
    quantity: str
    channel: Optional[str]
    unit: Optional[str]
    kind: str
    aggregate: str
    interval: str
    groupBy: str
    keys: List[str]
    names: Dict[str, str]
    series: List[Dict[str, Any]]


class SqlColumn(TypedDict):
    name: str
    type: str


class SqlResult(TypedDict):
    columns: List[SqlColumn]
    # Each row in the order of `columns`.
    rows: List[List[Any]]
    rowCount: int
    truncated: bool
    elapsedMs: int


class Quantity(TypedDict, total=False):
    id: str
    label: str
    unit: Optional[str]
    kind: str
    description: str
    units: List[str]
    unitOptional: bool
    devices: int
    deviceTypes: List[Dict[str, Any]]


class Webhook(TypedDict, total=False):
    id: str
    url: str
    description: Optional[str]
    eventTypes: List[str]
    applicationIds: List[str]
    enabled: bool
    disabledReason: Optional[str]
    disabledAt: Optional[str]
    consecutiveFailures: int
    failingSince: Optional[str]
    lastSuccessAt: Optional[str]
    lastFailureAt: Optional[str]
    previousSecretExpiresAt: Optional[str]
    lastDelivery: Optional[Dict[str, Any]]
    createdBy: Optional[str]
    createdAt: str
    updatedAt: str
    secret: str  # only on create


class WebhookDelivery(TypedDict, total=False):
    id: str
    endpointId: str
    eventId: str
    eventType: str
    status: str
    attempt: int
    maxAttempts: int
    nextAttemptAt: Optional[str]
    lastAttemptAt: Optional[str]
    latencyMs: Optional[int]
    error: Optional[str]
    request: Dict[str, Any]
    response: Dict[str, Any]
    createdAt: str


class IntegrationTemplate(TypedDict, total=False):
    id: str
    name: str
    description: str
    docs: str
    eventTypes: List[str]
    needsReadings: bool
    batches: bool
    settings: Dict[str, Any]  # JSON Schema; `x-secret` marks credentials


class Integration(TypedDict, total=False):
    id: str
    template: str
    templateName: str
    name: str
    settings: Dict[str, Any]
    secretsSet: Optional[List[str]]  # names only, never values
    eventTypes: List[str]
    applicationIds: List[str]
    enabled: bool
    disabledReason: Optional[str]
    disabledAt: Optional[str]
    consecutiveFailures: int
    failingSince: Optional[str]
    lastSuccessAt: Optional[str]
    lastFailureAt: Optional[str]
    lastDelivery: Optional[Dict[str, Any]]
    batchWaiting: Optional[int]
    createdBy: Optional[str]
    createdAt: str
    updatedAt: str


class IntegrationDelivery(TypedDict, total=False):
    id: str
    integrationId: str
    eventId: str
    eventType: str
    events: Optional[int]
    status: str
    attempt: int
    maxAttempts: int
    nextAttemptAt: Optional[str]
    lastAttemptAt: Optional[str]
    latencyMs: Optional[int]
    error: Optional[str]
    request: Dict[str, Any]
    response: Dict[str, Any]
    createdAt: str


class OnboardingSession(TypedDict, total=False):
    id: str
    status: str
    failure: Optional[str]
    vendor: Optional[str]
    model: Optional[str]
    transport: Optional[str]
    source: Optional[str]
    codec: Optional[Dict[str, Any]]
    verification: Optional[Dict[str, Any]]
    deviceTypeId: Optional[str]
    deviceProfileId: Optional[str]
    timeline: List[Dict[str, Any]]
    devices: List[Any]
    startedAt: str
    updatedAt: str
    registeredAt: Optional[str]
    firstJoinAt: Optional[str]
    firstUplinkAt: Optional[str]
    secondsToFirstUplink: Optional[float]


class Usage(TypedDict):
    inputTokens: int
    outputTokens: int
    cacheReadTokens: int
    cacheWriteTokens: int


class Run(TypedDict, total=False):
    id: str
    threadId: Optional[str]
    agentId: Optional[str]
    agentName: Optional[str]
    trigger: str
    triggerEventId: Optional[str]
    triggerSubject: Optional[str]
    status: str
    model: Optional[str]
    effort: str
    usage: Usage
    stopReason: Optional[str]
    error: Optional[str]
    createdAt: str
    startedAt: Optional[str]
    finishedAt: Optional[str]


# `class` is a keyword, hence the functional form.
Approval = TypedDict('Approval', {
    'toolUseId': str,
    'tool': str,
    'input': Dict[str, Any],
    'class': str,
    'confirm': Optional[str],
    'decision': Optional[str],
    'decidedBy': Optional[str],
    'decidedAt': Optional[str],
}, total=False)


class Decision(TypedDict, total=False):
    toolUseId: str
    approve: bool
    confirm: str


class Thread(TypedDict, total=False):
    id: str
    title: str
    pageContext: Optional[Dict[str, Any]]
    createdAt: str
    updatedAt: str
    lastRun: Optional[Dict[str, str]]
    # On get() only:
    messages: List[Dict[str, Any]]
    runs: List[Run]
    pending: Optional[Dict[str, Any]]


class Agent(TypedDict, total=False):
    id: str
    name: str
    template: Optional[str]
    instructions: str
    triggers: Dict[str, Any]
    autonomy: str
    scopes: List[str]
    effort: str
    enabled: bool
    owner: Optional[str]
    mine: bool
    keyPrefix: Optional[str]
    lastRunAt: Optional[str]
    nextRunAt: Optional[str]
    createdAt: str
    updatedAt: str
    openFindings: int
    lastRun: Optional[Run]
    # Why the org's agents are not being woken (the daily token budget is
    # spent), or None.
    held: Optional[str]


class Finding(TypedDict, total=False):
    id: str
    agentId: Optional[str]
    agentName: Optional[str]
    runId: Optional[str]
    severity: str
    title: str
    body: str
    subject: Optional[str]
    subjectPath: Optional[str]
    status: str
    createdAt: str
    updatedAt: str
    acknowledgedBy: Optional[str]
    resolvedBy: Optional[str]
    resolvedAt: Optional[str]


class MqttConnection(TypedDict, total=False):
    """GET /api/v1/mqtt/connection. The password is an API key: `data:read`
    to subscribe, `downlinks:write` to publish downlinks."""

    host: str
    port: int
    tls: bool
    username: str
    scopes: Dict[str, str]
    qos: int
    retained: bool
    topics: Dict[str, str]
    examples: Dict[str, str]
    # None when the server cannot ask the broker.
    connected: Optional[bool]
    sessions: List[Dict[str, Any]]
    lastAttempt: Optional[Dict[str, Any]]


class MulticastGroup(TypedDict, total=False):
    """A multicast group. `keys` only in the answer to its creation."""

    id: str
    name: str
    applicationId: str
    region: str
    groupType: str  # 'B' or 'C'
    dr: int
    frequency: int
    mcAddr: str
    fCnt: int
    pingSlotPeriodicity: int
    schedulingType: str
    devices: List[Dict[str, Any]]
    gateways: List[Dict[str, Any]]
    keys: Dict[str, str]


class Relay(TypedDict, total=False):
    devEui: str
    name: Optional[str]
    applicationId: str
    applicationName: Optional[str]
    deviceCount: int


class FirmwareImage(TypedDict, total=False):
    id: str
    name: str
    version: str
    filename: str
    sizeBytes: int
    sha256: str
    deviceTypeId: Optional[str]
    deviceType: Optional[Dict[str, str]]
    uploadedBy: str
    uploadedAt: str


class FirmwareDeployment(TypedDict, total=False):
    """`status` is draft, running, finished, failed or canceled; each device's
    `stage` the last step it answered, or completed or failed."""

    id: str
    name: str
    status: str
    imageId: str
    deviceTypeId: Optional[str]
    applicationId: str
    deviceProfileId: str
    region: Optional[str]
    params: Dict[str, Any]
    estimate: Optional[Dict[str, Any]]
    lnsJob: Optional[str]
    error: Optional[str]
    createdBy: str
    createdAt: str
    startedBy: Optional[str]
    startedAt: Optional[str]
    finishedAt: Optional[str]
    canceledAt: Optional[str]
    progress: Dict[str, int]
    devices: List[Dict[str, Any]]
