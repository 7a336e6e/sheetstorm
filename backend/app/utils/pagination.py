"""Shared list contract: paging, whitelisted sort, escaped search, declared
filters and `focus` deep links for every list endpoint.

Request params
    page      int >= 1 (default 1; a non-integer is 400)
    per_page  int, clamped to 1..max_per_page (default 50, max 200)
    sort      `field` or `-field`, up to 2 comma-separated; each name must be
              in the endpoint's whitelist (400 `invalid_sort`). The row id is
              always appended as the final tie-breaker, so pages are stable.
              Legacy `order=asc|desc` applies when the sort is one bare field.
    q         free text (legacy alias `search`), stripped, <= 200 chars,
              LIKE wildcards escaped, ILIKE across the endpoint's columns.
    filters   endpoint-declared {name: (column, kind)}; bad values are 400.
    focus     row UUID: the response is the page that contains that row
              under the current sort/filters (`focus_found` says whether it
              was found; if not, the requested page is returned).

Response envelope (a superset of the previous ad-hoc shape)
    {items, total, page, per_page, pages, sort, focus_found?, **extra}

Whitelists map public names to SQL expressions, so client input never names
a column directly. The helpers only refine a query the endpoint already
scoped (organization / incident), so `focus` can never reach other rows.
"""
from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional, Sequence

from sqlalchemy import String, case, cast, func, or_, select
from werkzeug.exceptions import BadRequest

from app.utils.validation import parse_datetime

DEFAULT_PER_PAGE = 50
MAX_PER_PAGE = 200
MAX_Q_LENGTH = 200
MAX_SORT_FIELDS = 2
MAX_IN_VALUES = 50

_CONTROL_CHARS = re.compile(r'[\x00-\x1f\x7f]')
_TRUE = {'true', '1', 'yes', 'on'}
_FALSE = {'false', '0', 'no', 'off'}


class ListArgsError(BadRequest):
    """400 whose JSON `error` code is `code` (the global handler derives the
    code from the exception name)."""

    def __init__(self, message: str, code: str = 'bad_request'):
        super().__init__(message)
        self.error_code = code

    @property
    def name(self):  # werkzeug's `name` is a read-only property
        return self.error_code.replace('_', ' ')


@dataclass(frozen=True)
class ListArgs:
    page: int
    per_page: int
    sort: tuple  # ((name, descending), ...)
    q: Optional[str]
    focus: Optional[uuid.UUID]

    @property
    def sort_string(self) -> str:
        return ','.join(f"{'-' if desc else ''}{name}" for name, desc in self.sort)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def escape_like(s: str) -> str:
    """Escape LIKE metacharacters; use with `.ilike(..., escape='\\\\')`."""
    return s.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


def _int_arg(args, name, default):
    raw = args.get(name)
    if raw is None or raw == '':
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ListArgsError(f'{name} must be an integer')


def parse_page_args(args=None, *, default_per_page=DEFAULT_PER_PAGE, max_per_page=MAX_PER_PAGE):
    """(page, per_page) from the request: page >= 1, per_page clamped."""
    args = _request_args(args)
    page = max(1, _int_arg(args, 'page', 1))
    per_page = min(max_per_page, max(1, _int_arg(args, 'per_page', default_per_page)))
    return page, per_page


def parse_q(args=None, *, min_length=0, max_length=MAX_Q_LENGTH) -> Optional[str]:
    """Free-text `q` (or legacy `search`): control chars removed, stripped,
    length-checked. Empty -> None (unless min_length requires a value)."""
    args = _request_args(args)
    raw = args.get('q')
    if raw is None or raw == '':
        raw = args.get('search')
    q = _CONTROL_CHARS.sub('', raw or '').strip()
    if len(q) > max_length:
        raise ListArgsError(f'q must be at most {max_length} characters')
    if len(q) < min_length:
        raise ListArgsError(f'q must be at least {min_length} characters')
    return q or None


def _parse_sort(raw: str, sortable: Mapping[str, Any]):
    fields = [f.strip() for f in raw.split(',') if f.strip()]
    if not fields:
        raise ListArgsError('sort must name a field', 'invalid_sort')
    if len(fields) > MAX_SORT_FIELDS:
        raise ListArgsError(f'sort accepts at most {MAX_SORT_FIELDS} fields', 'invalid_sort')
    out = []
    for f in fields:
        desc = f.startswith('-')
        name = f[1:] if desc or f.startswith('+') else f
        if name not in sortable:
            raise ListArgsError(
                f"invalid sort field {name!r}; allowed: {', '.join(sorted(sortable))}", 'invalid_sort')
        if any(n == name for n, _ in out):
            raise ListArgsError(f'duplicate sort field {name!r}', 'invalid_sort')
        out.append((name, desc))
    return out


def parse_list_args(*, sortable: Mapping[str, Any], default_sort: str,
                    default_per_page=DEFAULT_PER_PAGE, max_per_page=MAX_PER_PAGE,
                    args=None) -> ListArgs:
    """Parse page/per_page/sort/q/focus; raises ListArgsError (400)."""
    args = _request_args(args)
    page, per_page = parse_page_args(args, default_per_page=default_per_page, max_per_page=max_per_page)

    raw_sort = args.get('sort') or ''
    explicit = bool(raw_sort.strip())
    sort = _parse_sort(raw_sort if explicit else default_sort, sortable)

    order = (args.get('order') or '').strip().lower()
    if order:
        if order not in ('asc', 'desc'):
            raise ListArgsError('order must be asc or desc', 'invalid_sort')
        bare_single = len(sort) == 1 and (not explicit or not raw_sort.strip().startswith(('-', '+')))
        if bare_single:
            sort = [(sort[0][0], order == 'desc')]

    focus = None
    raw_focus = args.get('focus')
    if raw_focus:
        try:
            focus = uuid.UUID(str(raw_focus))
        except (ValueError, TypeError):
            raise ListArgsError('focus must be a UUID')

    return ListArgs(page=page, per_page=per_page, sort=tuple(sort), q=parse_q(args), focus=focus)


# ---------------------------------------------------------------------------
# Query building
# ---------------------------------------------------------------------------

def apply_search(query, columns: Sequence[Any], q: Optional[str]):
    """ILIKE `%q%` (escaped) across `columns`; non-text columns are cast."""
    if not q:
        return query
    pattern = f'%{escape_like(q)}%'
    clauses = []
    for col in columns:
        expr = col if isinstance(getattr(col, 'type', None), String) else cast(col, String)
        clauses.append(expr.ilike(pattern, escape='\\'))
    return query.filter(or_(*clauses))


SEVERITY_RANK = {'critical': 4, 'high': 3, 'medium': 2, 'low': 1}


def severity_rank(column):
    """Sort expression ranking critical > high > medium > low (also used for
    task priority, which shares the scale); unknown values rank lowest."""
    return case(SEVERITY_RANK, value=column, else_=0)


def enum(choices) -> tuple:
    """Filter kind: exact match restricted to `choices`."""
    return ('enum', tuple(choices))


def in_list(choices=None) -> tuple:
    """Filter kind: comma-separated list (optionally restricted to choices)."""
    return ('in', tuple(choices) if choices is not None else None)


def _parse_bool(name, raw):
    v = raw.strip().lower()
    if v in _TRUE:
        return True
    if v in _FALSE:
        return False
    raise ListArgsError(f'{name} must be true or false', 'invalid_filter')


def parse_uuid(name, raw):
    """A UUID query value, or 400 `invalid_filter`."""
    try:
        return uuid.UUID(raw.strip())
    except (ValueError, AttributeError):
        raise ListArgsError(f'{name} must be a UUID', 'invalid_filter')


def apply_filters(query, filters: Mapping[str, tuple], args=None):
    """Apply declared filters. Kinds:

    eq                     column == value
    ilike                  column ILIKE %value% (escaped)
    int / uuid             typed equality (bad value -> 400)
    bool                   column == true/false
    flag                   `column` is a boolean clause applied when true;
                           false means "no filter" (e.g. unread_only)
    date_from / date_to    column >= / <= ISO-8601 datetime
    enum(choices)          equality, value must be one of choices
    in_list(choices=None)  comma-separated values -> IN (...)

    Missing or empty params are ignored, as before.
    """
    args = _request_args(args)
    for name, (column, kind) in filters.items():
        raw = args.get(name)
        if raw is None or raw == '':
            continue
        if isinstance(kind, tuple):
            kind, choices = kind
        else:
            choices = None

        if kind == 'eq':
            query = query.filter(column == raw)
        elif kind == 'ilike':
            query = query.filter(column.ilike(f'%{escape_like(raw)}%', escape='\\'))
        elif kind == 'int':
            try:
                value = int(raw)
            except ValueError:
                raise ListArgsError(f'{name} must be an integer', 'invalid_filter')
            query = query.filter(column == value)
        elif kind == 'uuid':
            query = query.filter(column == parse_uuid(name, raw))
        elif kind == 'bool':
            query = query.filter(column == _parse_bool(name, raw))
        elif kind == 'flag':
            if _parse_bool(name, raw):
                query = query.filter(column)
        elif kind in ('date_from', 'date_to'):
            value = parse_datetime(raw, name)
            query = query.filter(column >= value if kind == 'date_from' else column <= value)
        elif kind == 'enum':
            if raw not in choices:
                raise ListArgsError(
                    f"invalid {name} {raw!r}; allowed: {', '.join(choices)}", 'invalid_filter')
            query = query.filter(column == raw)
        elif kind == 'in':
            values = [v.strip() for v in raw.split(',') if v.strip()]
            if not values or len(values) > MAX_IN_VALUES:
                raise ListArgsError(f'{name} must list 1..{MAX_IN_VALUES} values', 'invalid_filter')
            if choices is not None:
                bad = [v for v in values if v not in choices]
                if bad:
                    raise ListArgsError(
                        f"invalid {name} {bad[0]!r}; allowed: {', '.join(choices)}", 'invalid_filter')
            query = query.filter(column.in_(values))
        else:  # programming error, not client input
            raise ValueError(f'unknown filter kind {kind!r} for {name}')
    return query


def order_clauses(la: ListArgs, sortable: Mapping[str, Any], id_col) -> list:
    """ORDER BY list: requested fields (NULLS LAST) then id ascending."""
    clauses = []
    for name, desc in la.sort:
        expr = sortable[name]
        clauses.append(expr.desc().nullslast() if desc else expr.asc().nullslast())
    clauses.append(id_col.asc())
    return clauses


def apply_sort(query, la: ListArgs, sortable: Mapping[str, Any], id_col):
    return query.order_by(None).order_by(*order_clauses(la, sortable, id_col))


def _focus_position(query, la: ListArgs, sortable, id_col) -> Optional[int]:
    """1-based row number of `la.focus` within the (scoped, filtered) query."""
    ranked = query.order_by(None).with_entities(
        id_col.label('row_id'),
        func.row_number().over(order_by=order_clauses(la, sortable, id_col)).label('rn'),
    ).subquery()
    stmt = select(ranked.c.rn).where(ranked.c.row_id == la.focus)
    return query.session.execute(stmt).scalar()


def paginate_response(query, la: ListArgs, *, serialize: Callable, sortable: Mapping[str, Any],
                      id_col, extra: Optional[dict] = None) -> dict:
    """Run the count + page queries and build the envelope.

    `query` must already be scoped and filtered (and searched); sorting is
    applied here so the focus lookup uses exactly the same order.
    """
    total = query.order_by(None).count()
    pages = math.ceil(total / la.per_page) if total else 0
    page = la.page

    focus_found = None
    if la.focus is not None:
        rn = _focus_position(query, la, sortable, id_col)
        focus_found = rn is not None
        if focus_found:
            page = math.ceil(rn / la.per_page)

    rows = apply_sort(query, la, sortable, id_col).limit(la.per_page).offset((page - 1) * la.per_page).all()

    body = {
        'items': [serialize(r) for r in rows],
        'total': total,
        'page': page,
        'per_page': la.per_page,
        'pages': pages,
        'sort': la.sort_string,
    }
    if focus_found is not None:
        body['focus_found'] = focus_found
    if extra:
        body.update(extra)
    return body


def list_response(query, *, sortable: Mapping[str, Any], default_sort: str, id_col,
                  serialize: Callable, search_columns: Sequence[Any] = (),
                  filters: Optional[Mapping[str, tuple]] = None,
                  default_per_page=DEFAULT_PER_PAGE, max_per_page=MAX_PER_PAGE,
                  extra: Optional[dict] = None, args=None) -> dict:
    """parse_list_args + apply_filters + apply_search + paginate_response."""
    la = parse_list_args(sortable=sortable, default_sort=default_sort,
                         default_per_page=default_per_page, max_per_page=max_per_page, args=args)
    if filters:
        query = apply_filters(query, filters, args)
    query = apply_search(query, search_columns, la.q)
    return paginate_response(query, la, serialize=serialize, sortable=sortable, id_col=id_col, extra=extra)


def _request_args(args):
    if args is not None:
        return args
    from flask import request
    return request.args
