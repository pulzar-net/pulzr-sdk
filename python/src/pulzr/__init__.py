"""Python client for the Pulzr API. https://app.pulzr.net/docs"""

from . import mqtt, types, webhooks
from ._client import DEFAULT_BASE_URL, Client
from ._version import __version__
from .errors import (
    APIConnectionError,
    AuthenticationError,
    ConflictError,
    NotFoundError,
    PulzrError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
    SignatureVerificationError,
    ValidationError,
)
from .resources.agents import (
    AgentEvent,
    ApprovalRequiredEvent,
    DoneEvent,
    ErrorEvent,
    RunEvent,
    RunStream,
    TextEvent,
    ThinkingEvent,
    ToolCallEvent,
    ToolResultEvent,
    UnknownEvent,
    UsageEvent,
)
from .resources.events import EventStream
from .webhooks import construct_event, verify_signature

__all__ = [
    '__version__', 'Client', 'DEFAULT_BASE_URL', 'mqtt', 'types', 'webhooks',
    'verify_signature', 'construct_event',
    'PulzrError', 'APIConnectionError', 'AuthenticationError', 'PermissionDeniedError',
    'NotFoundError', 'ConflictError', 'ValidationError', 'RateLimitError', 'ServerError',
    'SignatureVerificationError',
    'EventStream', 'RunStream', 'AgentEvent', 'RunEvent', 'TextEvent', 'ThinkingEvent',
    'ToolCallEvent', 'ToolResultEvent', 'ApprovalRequiredEvent', 'UsageEvent', 'DoneEvent',
    'ErrorEvent', 'UnknownEvent',
]
