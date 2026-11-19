"""`pulzr api`: every operation in the server's own OpenAPI document.

The hand-written verbs cover what a technician does daily; this covers the
rest without a CLI release per route. It reads the spec the server publishes
at /api/v1/openapi.json rather than one bundled here, so a route deployed
today is callable today, and a CLI older than the server is not wrong about
it.

Cached beside the config, one file per base URL (production and a local
stack differ), for a day: long enough that a command does not cost two round
trips, short enough that a deploy shows up by tomorrow without anyone
knowing to pass `--refresh-spec`. When the fetch fails and a stale copy
exists, the stale copy is used with a warning; a network blip should not
take away a command that worked an hour ago.

What it does not do: multipart bodies (two datasheet and onboarding
uploads; the console and the SDK do those), and resume for a stream that
drops. `events tail` resumes; a stream here ends with the connection.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import httpx

from .._version import __version__
from ..errors import APIConnectionError, PulzrError, from_response
from .config import UsageError, write_private

SPEC_PATH = '/api/v1/openapi.json'
MAX_AGE = 24 * 3600

_METHODS = ('get', 'put', 'post', 'delete', 'patch', 'head', 'options')
_PLACEHOLDER = re.compile(r'\{([^}]+)\}')


@dataclass
class Operation:
    id: str
    method: str
    path: str
    scope: Optional[str]
    parameters: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    body_types: List[str] = field(default_factory=list)
    body_required: bool = False
    streams: bool = False


def cache_file(config_dir: Path, base_url: str) -> Path:
    digest = hashlib.sha256(base_url.encode()).hexdigest()[:16]
    return config_dir / f'openapi-{digest}.json'


def load(base_url: str, config_dir: Path, *, refresh: bool = False,
         transport: Optional[httpx.BaseTransport] = None,
         warn: Callable[[str], None] = lambda message: None,
         now: Callable[[], float] = time.time) -> Dict[str, Any]:
    path = cache_file(config_dir, base_url)
    cached = _read(path, base_url)
    if cached and not refresh and now() - cached['fetchedAt'] < MAX_AGE:
        return cached['spec']
    try:
        spec = fetch(base_url, transport)
    except PulzrError as e:
        if cached:
            fetched = time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(cached['fetchedAt']))
            warn(f'could not refresh the API spec ({e}); using the copy from {fetched}')
            return cached['spec']
        raise
    write_private(path, json.dumps({'baseUrl': base_url, 'fetchedAt': now(), 'spec': spec}))
    return spec


def fetch(base_url: str, transport: Optional[httpx.BaseTransport] = None) -> Dict[str, Any]:
    # Unauthenticated on the server, so no key is sent: `pulzr api --list`
    # works before login, and the key is not handed to anything that does
    # not need it.
    headers = {'User-Agent': f'pulzr-cli/{__version__}', 'Accept': 'application/json'}
    with httpx.Client(base_url=base_url, headers=headers, timeout=30.0,
                      transport=transport) as http:
        try:
            response = http.get(SPEC_PATH)
        except httpx.TransportError as e:
            raise APIConnectionError(f'GET {SPEC_PATH}: {e.__class__.__name__}: {e}') from e
        if response.status_code >= 400:
            raise from_response(response)
        try:
            spec = response.json()
        except ValueError:
            spec = None
    if not isinstance(spec, dict) or 'paths' not in spec:
        raise APIConnectionError(f'{base_url}{SPEC_PATH} is not an OpenAPI document')
    return spec


def _read(path: Path, base_url: str) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if (not isinstance(data, dict) or data.get('baseUrl') != base_url
            or not isinstance(data.get('spec'), dict)
            or not isinstance(data.get('fetchedAt'), (int, float))):
        return None
    return data


def _resolve(spec: Dict[str, Any], node: Any) -> Any:
    seen = 0
    while isinstance(node, dict) and isinstance(node.get('$ref'), str) and seen < 10:
        target: Any = spec
        for part in node['$ref'].lstrip('#/').split('/'):
            target = target.get(part.replace('~1', '/').replace('~0', '~'), {}) \
                if isinstance(target, dict) else {}
        node, seen = target, seen + 1
    return node


def operations(spec: Dict[str, Any]) -> List[Operation]:
    out = []
    for path, item in (spec.get('paths') or {}).items():
        item = _resolve(spec, item)
        shared = [_resolve(spec, p) for p in item.get('parameters') or []]
        for method in _METHODS:
            op = item.get(method)
            if not isinstance(op, dict) or not op.get('operationId'):
                continue
            params = {}
            for p in shared + [_resolve(spec, p) for p in op.get('parameters') or []]:
                if isinstance(p, dict) and p.get('name'):
                    params[p['name']] = p
            body = _resolve(spec, op.get('requestBody') or {})
            streams = any('text/event-stream' in (_resolve(spec, r).get('content') or {})
                          for status, r in (op.get('responses') or {}).items()
                          if str(status).startswith('2'))
            out.append(Operation(
                id=op['operationId'], method=method.upper(), path=path,
                scope=op.get('x-required-scope'), parameters=params,
                body_types=list((body.get('content') or {}).keys()),
                body_required=bool(body.get('required')), streams=streams))
    return out


def find(ops: List[Operation], operation_id: str) -> Operation:
    by_id = {op.id: op for op in ops}
    if operation_id in by_id:
        return by_id[operation_id]
    folded = {op.id.lower(): op for op in ops}
    if operation_id.lower() in folded:
        return folded[operation_id.lower()]
    close = difflib.get_close_matches(operation_id, list(by_id), n=5, cutoff=0.5)
    if not close:
        lowered = operation_id.lower()
        close = [op.id for op in ops if lowered in op.id.lower()][:5]
    hint = f"; did you mean {', '.join(close)}?" if close else '; `pulzr api --list` lists them'
    raise UsageError(f'no operation {operation_id!r}{hint}')


def placeholders(path: str) -> List[str]:
    return _PLACEHOLDER.findall(path)
