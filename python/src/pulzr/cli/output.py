"""JSON for programs, aligned columns for people.

The default follows stdout: a table on a terminal, JSON into a pipe or a
file, so `pulzr devices list | jq` works without a flag and nobody reads
JSON at a prompt unless they ask for it. JSON is the response as the API
sent it; a table is a chosen few columns of it and drops the rest, which is
why it is never the default for a pipe.

No colour and no symbols: status is a word in a column. A cell holding an
object or list is shown as compact JSON, cut at a width, because a table
that wraps is not a table.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Iterable, List, Optional, Sequence, TextIO, Tuple, Union

Getter = Union[str, Callable[[Any], Any]]
Column = Tuple[str, Getter]

_CELL_MAX = 60


def to_json(data: Any, *, indent: Optional[int] = 2) -> str:
    return json.dumps(data, indent=indent, ensure_ascii=False, default=str)


def cell(value: Any, limit: int = _CELL_MAX) -> str:
    if value is None:
        text = '-'
    elif isinstance(value, bool):
        text = 'true' if value else 'false'
    elif isinstance(value, (dict, list, tuple)):
        text = to_json(value, indent=None) if value else '-'
    else:
        text = str(value)
    text = ' '.join(text.split()) if '\n' in text or '\t' in text else text
    return text if len(text) <= limit else text[:limit - 3] + '...'


def _get(row: Any, getter: Getter) -> Any:
    if callable(getter):
        return getter(row)
    return row.get(getter) if isinstance(row, dict) else None


def table(rows: Iterable[Any], columns: Sequence[Column], out: TextIO) -> None:
    grid: List[List[str]] = [[header for header, _ in columns]]
    for row in rows:
        grid.append([cell(_get(row, getter)) for _, getter in columns])
    widths = [max(len(line[i]) for line in grid) for i in range(len(columns))]
    for line in grid:
        out.write('  '.join(text.ljust(width) for text, width in zip(line, widths)).rstrip() + '\n')


def pairs(data: dict, out: TextIO) -> None:
    """One object, a field per line."""
    if not data:
        return
    width = max(len(str(k)) for k in data)
    for key, value in data.items():
        # A path or URL cut short is useless; only nested values are cut.
        limit = 100 if isinstance(value, (dict, list, tuple)) else 10_000
        out.write(f'{str(key).ljust(width)}  {cell(value, limit)}'.rstrip() + '\n')


def auto_columns(rows: List[Any]) -> List[Column]:
    """Every scalar field of the first rows, in the order the API sent them."""
    keys: List[str] = []
    for row in rows[:20]:
        if not isinstance(row, dict):
            continue
        for key, value in row.items():
            if key not in keys and not isinstance(value, (dict, list)):
                keys.append(key)
    return [(k, k) for k in keys]


def show(data: Any, out: TextIO, columns: Optional[Sequence[Column]] = None) -> None:
    """A table of `data` without being told its shape: a list, a list under
    `result`, or one object."""
    if data is None:
        return
    if isinstance(data, dict) and isinstance(data.get('result'), list) and columns is None:
        data = data['result']
    if isinstance(data, list):
        if data and not isinstance(data[0], dict):
            for item in data:
                out.write(cell(item, 10_000) + '\n')
            return
        table(data, columns or auto_columns(data), out)
    elif isinstance(data, dict):
        pairs(data, out)
    else:
        out.write(str(data).rstrip('\n') + '\n')
