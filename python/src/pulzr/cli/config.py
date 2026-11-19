"""Where the CLI keeps the key, and which setting wins.

The key is the one thing here worth stealing: it acts as its owner in their
org until it is revoked. So the file is created 0600 by `os.open` and then
renamed into place, never written by `open()` and narrowed afterwards, which
leaves a moment in which it is world-readable. A file found with wider bits
(copied in by hand, restored from a backup) is narrowed before it is read.
Nothing prints the key: it is named everywhere by its `pzk_<prefix>_`
prefix, the way the console and the audit log name it.

There is no `--api-key` flag. A key on the command line lands in shell
history and in `ps` for every user on the machine; the environment and the
file do not.

Precedence is flag, then environment, then file, so a CI job's
PULZR_API_KEY is not overridden by a stored login on the same runner, and a
one-off `--base-url` needs no logout.
"""

from __future__ import annotations

import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from .._client import DEFAULT_BASE_URL
from .._client import env as env_var

_KEY = re.compile(r'^pzk_([0-9a-f]{8})_')


class UsageError(Exception):
    """Exit 2: the command, not the API, is wrong."""


def config_path(env: Mapping[str, str]) -> Path:
    named = env_var('PULZR_CONFIG', env)
    if named:
        return Path(named).expanduser()
    base = Path(env.get('XDG_CONFIG_HOME') or str(Path.home() / '.config')).expanduser()
    path = base / 'pulzr' / 'config.json'
    legacy = base / 'parkeze' / 'config.json'  # a login saved before the CLI was `pulzr`
    return legacy if not path.exists() and legacy.exists() else path


def mask(key: Optional[str]) -> Optional[str]:
    if not key:
        return None
    match = _KEY.match(key)
    return f'pzk_{match.group(1)}_...' if match else '(not a pzk_ key)'


def load(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    _narrow(path)
    try:
        data = json.loads(path.read_text(encoding='utf-8') or '{}')
    except ValueError as e:
        raise UsageError(f'{path} is not JSON ({e}); fix or delete it') from None
    if not isinstance(data, dict):
        raise UsageError(f'{path} is not a JSON object; fix or delete it')
    return data


def write_private(path: Path, text: str) -> None:
    """`text` at `path`, readable by this user alone from its first byte."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name(f'.{path.name}.{os.getpid()}.tmp')
    try:
        tmp.unlink()
    except FileNotFoundError:
        pass
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(text)
        os.replace(str(tmp), str(path))
    except BaseException:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise
    # A umask only removes bits, but a filesystem that ignores the mode on
    # create (some network mounts) is narrowed here.
    _narrow(path)


def save(path: Path, data: Dict[str, Any]) -> None:
    write_private(path, json.dumps(data, indent=2, sort_keys=True) + '\n')


def _narrow(path: Path) -> None:
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o077:
            os.chmod(str(path), 0o600)
    except OSError:
        pass


@dataclass
class Settings:
    """What a command runs with, and where each value came from, so
    `config show` can say why a setting is what it is."""

    path: Path
    file: Dict[str, Any]
    api_key: Optional[str]
    key_source: Optional[str]
    base_url: str
    base_url_source: str
    org: Optional[str]
    org_source: Optional[str]


def resolve(flags: Mapping[str, Any], env: Mapping[str, str]) -> Settings:
    path = config_path(env)
    file = load(path)

    def pick(flag: Optional[str], var: str, key: str):
        if flag and flags.get(flag):
            return flags[flag], 'flag'
        value = env_var(var, env)
        if value:
            return value, var
        if file.get(key):
            return file[key], 'config file'
        return None, None

    api_key, key_source = pick(None, 'PULZR_API_KEY', 'apiKey')
    base_url, base_source = pick('base_url', 'PULZR_BASE_URL', 'baseUrl')
    org, org_source = pick('org', 'PULZR_ORG', 'org')
    return Settings(path=path, file=file, api_key=api_key, key_source=key_source,
                    base_url=(base_url or DEFAULT_BASE_URL).rstrip('/'),
                    base_url_source=base_source or 'default', org=org, org_source=org_source)
