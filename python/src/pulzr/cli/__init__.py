"""`pulzr`, the command line for Pulzr.

Built on the SDK in this package, not beside it: every hand-written verb is a
call to a resource method, so paging, retries, the error classes and the
event stream's resume are the SDK's, tested once, and the CLI cannot drift
from the library people embed. Where the SDK wraps nothing (the simulator)
the verb calls the route through `Client.request`, the same escape hatch the
SDK documents. `pulzr api` reaches everything else from the server's spec.

stdlib argparse and nothing else beyond httpx, so `pip install pulzr`
stays one dependency for the people who only want the library.

Exit codes: 0 done, 1 the API refused or could not be reached (its
`{"error": ...}` on stderr), 2 the command was wrong (argparse's own code),
130 interrupted.
"""

from __future__ import annotations

import contextlib
import os
import sys
from typing import Any, Callable, List, Mapping, Optional, Sequence, Set, TextIO

import httpx

from .._client import Client
from .._version import __version__
from ..errors import PulzrError
from . import output
from .config import Settings, UsageError, mask, resolve

__all__ = ['main', 'run']


class _Redacting:
    """A text stream that cannot carry the key: whatever is written through
    it, from any verb, error path or debug hook, has every known key
    replaced by its prefix. Belt and braces -- nothing should print it --
    but the cost of one path forgetting is a key in a CI log."""

    def __init__(self, inner: TextIO, secrets: Set[str]) -> None:
        self._inner = inner
        self._secrets = secrets

    def write(self, text: str) -> int:
        for secret in self._secrets:
            if secret and secret in text:
                text = text.replace(secret, mask(secret) or '')
        return self._inner.write(text)

    def flush(self) -> None:
        self._inner.flush()

    def isatty(self) -> bool:
        isatty = getattr(self._inner, 'isatty', None)
        return bool(isatty and isatty())


class Context:
    """What a command needs: settings, streams, and a client on demand."""

    def __init__(self, args: Any, env: Mapping[str, str], stdin: TextIO, out: _Redacting,
                 err: _Redacting, secrets: Set[str],
                 transport: Optional[httpx.BaseTransport],
                 sleep: Optional[Callable[[float], None]]) -> None:
        self.args = args
        self.env = env
        self.stdin = stdin
        self.out = out
        self.err = err
        self.secrets = secrets
        self.transport = transport
        self.sleep = sleep
        self.debug = bool(getattr(args, 'debug', False))
        self.settings: Settings = resolve({'base_url': getattr(args, 'base_url', None),
                                           'org': getattr(args, 'org', None)}, env)
        for key in (self.settings.api_key, self.settings.file.get('apiKey')):
            if isinstance(key, str) and key:
                secrets.add(key)
        self.fmt: str = getattr(args, 'output', None) or ('table' if out.isatty() else 'json')

    def client(self, api_key: Optional[str] = None) -> Client:
        key = api_key or self.settings.api_key
        if not key:
            raise UsageError('no API key: run `pulzr login` or set PULZR_API_KEY')
        self.secrets.add(key)
        client = Client(api_key=key, org=self.settings.org, base_url=self.settings.base_url,
                        transport=self.transport)
        client._http.headers['User-Agent'] = f'pulzr-cli/{__version__}'
        if self.sleep is not None:
            client._sleep = self.sleep
        if self.debug:
            client._http.event_hooks = {'request': [self._debug_request],
                                        'response': [self._debug_response]}
        return client

    def _debug_request(self, request: httpx.Request) -> None:
        self.err.write(f'> {request.method} {request.url}\n')
        for name, value in request.headers.items():
            if name.lower() == 'authorization':
                scheme, _, token = value.partition(' ')
                value = f'{scheme} {mask(token)}'
            self.err.write(f'> {name}: {value}\n')

    def _debug_response(self, response: httpx.Response) -> None:
        self.err.write(f'< {response.status_code} {response.reason_phrase}\n')
        for name in ('content-type', 'retry-after', 'x-request-id'):
            if name in response.headers:
                self.err.write(f'< {name}: {response.headers[name]}\n')

    def emit(self, data: Any, columns: Optional[Sequence[output.Column]] = None) -> None:
        if self.fmt == 'json':
            if data is not None:
                self.out.write(output.to_json(data) + '\n')
        else:
            output.show(data, self.out, columns)
        self.out.flush()

    def note(self, message: str) -> None:
        self.err.write(message.rstrip('\n') + '\n')
        self.err.flush()


def run(argv: Sequence[str], *, env: Optional[Mapping[str, str]] = None,
        stdin: Optional[TextIO] = None, stdout: Optional[TextIO] = None,
        stderr: Optional[TextIO] = None, transport: Optional[httpx.BaseTransport] = None,
        sleep: Optional[Callable[[float], None]] = None) -> int:
    """The CLI as a function: the streams, environment and transport are
    arguments so a test runs it without a terminal or a network."""
    from .commands import build_parser

    secrets: Set[str] = set()
    out = _Redacting(stdout or sys.stdout, secrets)
    err = _Redacting(stderr or sys.stderr, secrets)
    env = os.environ if env is None else env
    parser = build_parser()
    try:
        # argparse writes help and usage errors to sys.stdout/sys.stderr;
        # through the redacting streams like everything else.
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):  # type: ignore[type-var]
            args = parser.parse_args(list(argv))
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 2

    ctx = None
    try:
        ctx = Context(args, env, stdin or sys.stdin, out, err, secrets, transport, sleep)
        args.func(ctx, args)
        return 0
    except UsageError as e:
        err.write(f'pulzr: {e}\n')
        return 2
    except PulzrError as e:
        _api_error(ctx, e, err)
        return 1
    except KeyboardInterrupt:
        err.write('\n')
        return 130
    except BrokenPipeError:
        # The reader went away (`| head`): what it wanted it has. Python
        # would otherwise complain again while flushing stdout at exit.
        try:
            sys.stdout = open(os.devnull, 'w')
        except OSError:
            pass
        return 0


def _api_error(ctx: Optional[Context], e: PulzrError, err: _Redacting) -> None:
    if ctx is not None and ctx.fmt == 'json' and isinstance(e.body, dict):
        err.write(output.to_json(e.body) + '\n')
        return
    err.write(f'error: {e}\n')
    for detail in e.details:
        if detail != e.message:
            err.write(f'  {detail}\n')


def main(argv: Optional[List[str]] = None) -> int:
    return run(sys.argv[1:] if argv is None else argv)
